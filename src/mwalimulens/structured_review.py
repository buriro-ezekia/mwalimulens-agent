"""Opt-in structured proposals with application-owned, validated MCP submission."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from mwalimulens.agent.candidate_contract import EvidenceSnapshot, decide_and_submit
from mwalimulens.agent.execution import ExecutionLimits, atomic_json
from mwalimulens.agent.ollama import OllamaSettings, prewarm_ollama_async
from mwalimulens.agent.open_weights_run import _pending_cancellation, build_open_weights_report
from mwalimulens.agent.orchestrator import build_agent_mcp_client
from mwalimulens.agent.structured_ollama import OllamaJsonGenerator
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import SCENARIOS, grade_scenario, run_suite, scenario_by_id

MODE = "structured_proposal_v1"


async def run_structured_case(
    scenario, *, state_path: Path, report_path: Path, result_path: Path,
    settings: OllamaSettings | None = None, execution_limits: ExecutionLimits | None = None,
    data_dir: Path = DEFAULT_DATA_DIR,
) -> dict[str, Any]:
    """Run a new isolated case; expected outcomes are used ONLY by grading."""

    settings = settings or OllamaSettings.from_env()
    limits = execution_limits or ExecutionLimits()
    state_path, report_path, result_path = (
        path.resolve() for path in (state_path, report_path, result_path)
    )
    snapshot_path = state_path.with_name("evidence_snapshot.json")
    progress_path = report_path.with_suffix(".progress.json")
    artifact_paths = (state_path, report_path, result_path, snapshot_path, progress_path)
    if len(set(artifact_paths)) != len(artifact_paths):
        raise ValueError("All review artifact paths must be different")
    if any(path.exists() for path in artifact_paths):
        raise FileExistsError("Refusing to overwrite existing review evidence")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    store = JsonStateStore(state_path)
    target = (scenario.learner, scenario.competency)
    start = datetime.now(UTC)
    started = perf_counter()
    deadline = asyncio.get_running_loop().time() + limits.deadline_seconds
    events: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    stages: list[dict[str, Any]] = []
    active_stage: str | None = "retrieval"
    snapshot: EvidenceSnapshot | None = None
    outcome: dict[str, Any] = {}
    error = None
    termination = None
    cancellation = None
    cleanup_error = None
    primary_exception: BaseException | None = None
    deadline_scope: asyncio.Timeout | None = None
    final_output = ""
    submission_attempted = False

    def raw_report(text: str, stage_error=None) -> dict[str, Any]:
        report = build_open_weights_report(
            settings=settings, prompt="Native structured competency review; see evidence snapshot.",
            final_output=text, state_store=store, started_at=start,
            finished_at=datetime.now(UTC), error=stage_error,
            evaluation_target=target, expected_outcome=scenario.expected,
            prompt_style="scenario", allow_candidate_action=False,
        )
        report["agent_tool_allowlist"] = []
        report["application_mcp_allowlist"] = [
            "get_competency_evidence", "flag_pattern_for_review",
        ]
        report["submission_actor"] = "application_controller"
        report["model_tool_selection_evaluated"] = False
        return report

    def observe(event: dict[str, Any]) -> None:
        nonlocal active_stage
        events.append(dict(event))
        kind = event["event"]
        if kind == "proposal_started":
            active_stage = "initial" if event["attempt"] == 1 else "proposal_repair"
        if kind == "proposal_invalid":
            rejected = {"type": "ProposalRejected", "message": "; ".join(event["issues"])}
            stages.append({"stage": active_stage, **raw_report("", rejected)})
        if kind == "submission_started":
            active_stage = "submission"
        atomic_json(progress_path, {
            "workflow_mode": MODE, "status": "fail" if termination else "in_progress",
            "active_stage": active_stage,
            "active_stage_outcome": "unknown", "events": events,
            "model_requests": requests, "outcome_stages": stages,
            "evidence_sha256": snapshot.sha256 if snapshot else None,
        })

    def capture_failure(exc: BaseException, *, during_stage: bool = False) -> None:
        nonlocal cancellation, termination, error, cleanup_error, primary_exception
        interrupted = (
            exc if isinstance(exc, asyncio.CancelledError) else _pending_cancellation(exc)
        )
        expired = deadline_scope is not None and deadline_scope.expired()
        # Outside the timeout scope its cancellation has been consumed. Any
        # remaining cancellation is external, including one during teardown.
        if interrupted is not None and (not during_stage or not expired):
            cancellation = interrupted
        if primary_exception is not None:
            if exc is not primary_exception and not (expired and isinstance(exc, TimeoutError)):
                cleanup_error = {"type": type(exc).__name__, "message": str(exc)}
            return
        primary_exception = exc
        reason = "deadline_exceeded" if expired else "cancelled" if cancellation else "error"
        termination = {"reason": reason, "active_stage": active_stage}
        error = {"type": type(exc).__name__, "message": str(exc) or reason}
        observe({"event": "workflow_interrupted", "reason": reason})

    async def audited_call(client, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        before = len(store.tool_calls())
        await client.call_tool(name, arguments)
        new_calls = store.tool_calls()[before:]
        if len(new_calls) != 1:
            raise ValueError("MCP call did not produce exactly one audit record")
        event = new_calls[0]
        if event.get("tool_name") != name or event.get("status") != "success":
            raise ValueError("MCP operation did not succeed")
        if event.get("inputs") != arguments or not isinstance(event.get("output"), dict):
            raise ValueError("MCP audit does not match the requested operation")
        return event["output"]

    try:
        async with asyncio.timeout_at(deadline) as deadline_scope:
            if settings.keep_alive is not None:
                await prewarm_ollama_async(settings)
            async with build_agent_mcp_client(data_dir=data_dir, state_path=state_path) as client:
                try:
                    observe({"event": "retrieval_started"})
                    payload = await audited_call(client, "get_competency_evidence", {
                        "learner_id": target[0], "competency_code": target[1],
                    })
                    snapshot = EvidenceSnapshot.from_mcp(payload, target)
                    atomic_json(snapshot_path, {
                        "sha256": snapshot.sha256, "payload": json.loads(snapshot.payload_json),
                    })
                    observe({"event": "retrieval_completed", "evidence_sha256": snapshot.sha256})
                    generator = OllamaJsonGenerator(
                        model=settings.model_name, base_url=settings.base_url, deadline=deadline,
                        request_limit=limits.request_limit, records=requests, observe=observe,
                        keep_alive=settings.keep_alive,
                    )

                    async def submit(arguments):
                        nonlocal submission_attempted
                        if submission_attempted:
                            raise RuntimeError("A second application submission is not authorised")
                        submission_attempted = True
                        return await audited_call(client, "flag_pattern_for_review", arguments)

                    outcome = await decide_and_submit(
                        snapshot, generate=generator, submit=submit, observe=observe,
                        request_limit=limits.request_limit,
                    )
                    final_output = outcome.get("final_output", "")
                    if outcome["status"] == "invalid_proposal":
                        error = {"type": "ProposalRejected", "message": "Proposal repair exhausted"}
                    else:
                        stage = "initial" if len(outcome["attempts"]) == 1 else "proposal_repair"
                        stages.append({"stage": stage, **raw_report(final_output)})
                    active_stage = None
                except BaseException as exc:
                    # Persist the original interruption before MCP teardown can replace it.
                    capture_failure(exc, during_stage=True)
                    raise
    except BaseException as exc:
        capture_failure(exc)
        if not isinstance(exc, Exception) and cancellation is None:
            raise
    report = raw_report(final_output, error)
    report.update({
        "workflow_mode": MODE,
        "submission_actor": "application_controller",
        "model_tool_selection_evaluated": False,
        "proposal_attempts": outcome.get("attempts", []),
        "proposal_status": outcome.get("status", "interrupted" if termination else "unknown"),
        "outcome_stages": stages, "events": events, "model_requests": requests,
        "model_request_count_observed": len(requests),
        "active_stage": active_stage, "active_stage_outcome": "unknown" if active_stage else None,
        "termination": termination, "cleanup_error": cleanup_error,
        "evidence_sha256": snapshot.sha256 if snapshot else None,
        "execution_limits": {"request_limit": limits.request_limit,
                             "deadline_seconds": limits.deadline_seconds,
                             "proposal_attempt_limit": min(2, limits.request_limit)},
        "timing": {"total_wall_seconds": round(perf_counter() - started, 3)},
        "note": "System workflow result, not autonomous model tool-selection accuracy.",
    })
    evaluated = grade_scenario(report, scenario, data_dir=data_dir)
    evaluated.update({
        "workflow_mode": MODE, "model_tool_selection_evaluated": False,
        "submission_actor": "application_controller", "termination": termination,
        "active_stage": active_stage, "active_stage_outcome": report["active_stage_outcome"],
        "proposal_status": report["proposal_status"],
        "outcome_stages": [
            {"stage": item["stage"], **grade_scenario(item, scenario, data_dir=data_dir)}
            for item in stages
        ],
    })
    atomic_json(report_path, report)
    atomic_json(result_path, evaluated)
    atomic_json(progress_path, report)
    if cancellation is not None:
        raise cancellation
    return evaluated


def _structured_subprocess(command, **kwargs):
    """Reuse the existing outer watchdog, selecting the explicit structured worker."""

    expected = "mwalimulens.multi_scenario_eval"
    if len(command) < 3 or command[1:3] != ["-m", expected]:
        raise ValueError("Unexpected evaluation subprocess command")
    child = [*command]
    child[2] = "mwalimulens.structured_review"
    return subprocess.run(child, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", nargs="+", choices=[s.ident for s in SCENARIOS],
                        default=["longitudinal-pattern"])
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--request-limit", type=int, default=6)
    parser.add_argument("--deadline-seconds", type=float, default=540)
    parser.add_argument("--output-dir", type=Path,
                        default=PROJECT_ROOT / "runtime" / "structured_review")
    parser.add_argument("--single-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", choices=[s.ident for s in SCENARIOS], help=argparse.SUPPRESS)
    for name in ("state", "report", "result"):
        parser.add_argument("--" + name, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.single_run:
        if not all((args.scenario, args.state, args.report, args.result)):
            parser.error("The isolated worker needs scenario, state, report and result")
        result = asyncio.run(run_structured_case(
            scenario_by_id(args.scenario), state_path=args.state, report_path=args.report,
            result_path=args.result,
            execution_limits=ExecutionLimits(args.request_limit, args.deadline_seconds),
        ))
        return 0 if result["status"] == "pass" else 2
    report = run_suite(
        output_root=args.output_dir, timeout=args.timeout, scenarios=tuple(args.scenarios),
        request_limit=args.request_limit, deadline_seconds=args.deadline_seconds,
        runner=_structured_subprocess,
    )
    report["workflow_mode"] = MODE
    report["model_tool_selection_evaluated"] = False
    path = Path(report["summary_path"])
    atomic_json(path, {key: value for key, value in report.items() if key != "summary_path"})
    print(f"Mode: {MODE}; validated application submission, not autonomous tool selection")
    print(f"Summary: {path}")
    print(f"Structural passes: {report['passed']}/{report['scenario_count']}")
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
