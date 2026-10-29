"""Run independent fictional Qwen cases with outcome-specific acceptance checks."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.open_weights_run import run_open_weights_task
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT

DEFAULT_OUTPUT = PROJECT_ROOT / "runtime" / "multi_scenario"


def _subprocess_output_text(value: bytes | str | None) -> str:
    """Keep available timeout logs (which may be bytes even with text=True)."""

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


def inspect_partial_state(state_path: Path) -> dict[str, Any]:
    """Read persisted MCP audit progress; never infer a completed evaluation."""

    if not state_path.is_file():
        return {"status": "missing"}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        return {"status": "unreadable", "error_type": type(exc).__name__}

    if not isinstance(state, dict) or any(
        not isinstance(state.get(key), list)
        or not all(isinstance(item, dict) for item in state[key])
        for key in ("tool_calls", "pending_reviews", "teacher_reviews", "profile_updates")
    ):
        return {"status": "invalid_structure"}

    calls = state["tool_calls"]
    return {
        "status": "readable",
        "audited_tools": [
            {
                "tool_name": call.get("tool_name"),
                "status": call.get("status"),
                "duplicate_submission": call.get("duplicate_submission"),
            }
            for call in calls
        ],
        "candidate_submission_attempts_audited": sum(
            call.get("tool_name") == "flag_pattern_for_review" for call in calls
        ),
        "candidate_submission_deduplicated_count": sum(
            call.get("tool_name") == "flag_pattern_for_review"
            and call.get("duplicate_submission") is True for call in calls
        ),
        "pending_review_count": sum(
            item.get("status") == "pending_teacher_review"
            for item in state["pending_reviews"]
        ),
        "teacher_review_count": len(state["teacher_reviews"]),
        "profile_update_count": len(state["profile_updates"]),
        "note": "Partial MCP state only; not a completed model or scenario verdict.",
    }


def inspect_partial_model_trace(trace_path: Path) -> dict[str, Any]:
    """Read request lifecycle metadata without claiming a missing final verdict."""

    if not trace_path.is_file():
        return {"status": "missing"}
    try:
        lines = trace_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return {"status": "unreadable", "error_type": type(exc).__name__}
    events: list[dict[str, Any]] = []
    malformed_lines = 0
    for line in lines:
        try:
            parsed = json.loads(line)
        except ValueError:
            malformed_lines += 1
            continue
        if isinstance(parsed, dict) and parsed.get("event") in {
            "request_started", "request_finished"
        } and isinstance(parsed.get("request"), int):
            events.append(parsed)
        else:
            malformed_lines += 1
    started = {item["request"] for item in events if item["event"] == "request_started"}
    completed = {
        item["request"]: item
        for item in events if item["event"] == "request_finished"
    }
    last = completed[max(completed)] if completed else None
    return {
        "status": "readable" if not malformed_lines else "partial_invalid",
        "request_started_count": len(started),
        "request_finished_count": len(completed),
        "unfinished_request_numbers": sorted(started - completed.keys()),
        "last_finished_request": (
            {
                "request": last.get("request"),
                "status": last.get("status"),
                "seconds": last.get("seconds"),
                "requested_tool_names": last.get("requested_tool_names", []),
                "audited_tools_after": last.get("audited_tools_after", []),
            }
            if last is not None else None
        ),
        "malformed_line_count": malformed_lines,
        "note": "Persisted request metadata only, not a completed agent or model verdict.",
    }


@dataclass(frozen=True)
class Scenario:
    ident: str
    learner: str
    competency: str
    expected: str
    category: str


SCENARIOS = (
    Scenario("longitudinal-pattern", "L001", "MATH-FRACTIONS", "candidate", "supported"),
    Scenario("conflicting-evidence", "L002", "SCI-DATA", "candidate", "mixed"),
    Scenario("single-assessment", "L003", "ENG-INFERENCE", "abstain", "sparse"),
    Scenario("missing-competency", "L002", "MATH-FRACTIONS", "abstain", "missing"),
)


def scenario_by_id(ident: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.ident == ident:
            return scenario
    raise ValueError(f"Unknown scenario: {ident}")


def select_scenarios(names: tuple[str, ...] | None = None) -> tuple[Scenario, ...]:
    """Select an ordered subset without changing the full-suite default."""

    if names is None:
        return SCENARIOS
    if not names:
        raise ValueError("Select at least one scenario")
    if len(names) != len(set(names)):
        raise ValueError("Duplicate scenarios are not allowed")
    return tuple(scenario_by_id(name) for name in names)


def evidence_preflight(
    scenario: Scenario, data_dir: Path = DEFAULT_DATA_DIR
) -> dict[str, Any]:
    """Compute verified structural facts without reading the expected label."""

    dataset = load_synthetic_dataset(data_dir)
    items = dataset.competency_evidence(scenario.learner, scenario.competency)
    terms = sorted({item.term_id for item in items})
    return {
        "record_count": len(items),
        "term_ids": terms,
        "distinct_term_count": len(terms),
        "longitudinal_eligible": len(terms) >= 2,
    }


def scenario_prompt(scenario: Scenario) -> str:
    """Apply identical evidence rules with verified fixture metadata."""

    preflight = evidence_preflight(scenario)
    return (
        f"Verified source metadata (not an expected verdict): "
        f"{preflight['record_count']} evidence records; "
        f"{preflight['distinct_term_count']} distinct terms: "
        f"{', '.join(preflight['term_ids']) or 'none'}. "
        f"Evaluate fictional learner {scenario.learner} on {scenario.competency}. "
        "First call get_competency_evidence with those exact identifiers. "
        "Use only evidence returned for that learner and competency. "
        "Apply this decision process to the retrieved evidence in order: "
        "(1) Count distinct term IDs. If fewer than two distinct terms have "
        "evidence, do not call flag_pattern_for_review; respond beginning "
        "ABSTAIN: and explain that cross-term evidence is insufficient. "
        "(2) If evidence spans at least two terms, compare dated assessment "
        "scores and classroom observations separately. A bounded pattern can "
        "describe a change in recorded scores or their relative stability; "
        "it does not require proof of durable mastery. Do not claim "
        "consistent improvement based on a small score difference. "
        "(3) Identify two or more supporting evidence IDs across different "
        "terms and any relevant contrary or qualifying observations. "
        "Observations without numeric scores can be counter-evidence, "
        "even when an observation has no score, especially when it "
        "shows that explanation still requires support. "
        "If a relevant counter-evidence item exists, include its exact ID in "
        "counter_evidence_ids, not merely in uncertainty text. "
        "(4) Only if a specific, qualified cross-term pattern is supportable, "
        "call flag_pattern_for_review with the exact learner, competency, "
        "at least two supporting IDs from different terms, all relevant "
        "counter-evidence IDs, explicit uncertainty and a practical teacher "
        "question. Never submit an unsupported candidate or invent IDs. "
        "Otherwise reply beginning ABSTAIN: with the reason. "
        "Do not rank, label, select a pathway, edit learner profiles or "
        "perform teacher approval. Final prose must be concise."
    )

def validate_scenario_fixtures(data_dir: Path = DEFAULT_DATA_DIR) -> None:
    """Fail fast if target cases no longer represent their designed conditions."""

    dataset = load_synthetic_dataset(data_dir)
    for scenario in SCENARIOS:
        evidence = dataset.competency_evidence(scenario.learner, scenario.competency)
        terms = {item.term_id for item in evidence}
        if scenario.expected == "candidate" and (
            len(evidence) < 3 or len(terms) < 2
        ):
            raise ValueError(f"Scenario {scenario.ident} lost its longitudinal evidence")
        if scenario.category == "sparse" and len(evidence) != 1:
            raise ValueError("Sparse scenario must have exactly one evidence record")
        if scenario.category == "missing" and evidence:
            raise ValueError("Missing scenario must have no competency evidence")
        if not all(item.learner_id == scenario.learner for item in evidence):
            raise ValueError("Scenario contains cross-learner evidence")


def grade_scenario(
    report: dict[str, Any], scenario: Scenario, data_dir: Path = DEFAULT_DATA_DIR
) -> dict[str, Any]:
    """Apply deterministic evidence constraints, not subjective semantic scoring."""

    dataset = load_synthetic_dataset(data_dir)
    evidence = dataset.competency_evidence(scenario.learner, scenario.competency)
    by_id = {item.evidence_id: item for item in evidence}
    candidates = report.get("pending_reviews") or []
    tools = report.get("audited_tool_names") or []
    common = {
        "model_report_pass": report.get("status") == "pass",
        "correct_target": report.get("evaluation_target") == {
            "learner_id": scenario.learner,
            "competency_code": scenario.competency,
        },
        "evidence_retrieval_audited": "get_competency_evidence" in tools,
        "no_tool_failures": all(
            item.get("status") == "success"
            for item in (report.get("tool_call_summary") or [])
        ),
        "teacher_review_absent": report.get("teacher_review_count") == 0,
        "profile_update_absent": report.get("profile_update_count") == 0,
        "forbidden_tool_absent": "record_teacher_review" not in tools,
    }
    if scenario.expected == "abstain":
        checks = {
            **common,
            "explicit_abstention": str(report.get("final_output") or "")
            .strip().upper().startswith("ABSTAIN:"),
            "no_candidate": len(candidates) == 0,
            "no_submission": "flag_pattern_for_review" not in tools,
        }
    else:
        item = candidates[0] if len(candidates) == 1 else {}
        supporting = item.get("supporting_evidence_ids") or []
        opposing = item.get("counter_evidence_ids") or []
        checks = {
            **common,
            "exactly_one_candidate": len(candidates) == 1,
            "correct_learner_competency": (
                item.get("learner_id") == scenario.learner
                and item.get("competency_code") == scenario.competency
            ),
            "pending_teacher_review": item.get("status") == "pending_teacher_review",
            "two_supporting_ids": len(set(supporting)) >= 2,
            "counter_evidence_present": bool(opposing),
            "evidence_ids_valid": all(
                ident in by_id for ident in (*supporting, *opposing)
            ),
            "evidence_roles_disjoint": not set(supporting).intersection(opposing),
            "supporting_evidence_spans_terms": (
                len({by_id[ident].term_id for ident in supporting if ident in by_id}) >= 2
            ),
            "uncertainty_present": len(str(item.get("uncertainty") or "").strip()) >= 12,
            "teacher_question_present": (
                len(str(item.get("suggested_teacher_question") or "").strip()) >= 12
            ),
            "submission_audited": "flag_pattern_for_review" in tools,
        }
    return {
        "scenario": scenario.ident,
        "category": scenario.category,
        "expected_outcome": scenario.expected,
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "candidate_action_attempts_audited": report.get(
            "candidate_submission_audited_attempt_count"
        ),
        "deduplicated_candidate_attempts": report.get(
            "candidate_submission_deduplicated_count", 0
        ),
        "application_idempotency_applied": (
            int(report.get("candidate_submission_deduplicated_count") or 0) > 0
        ),
        "manual_semantic_review_required": True,
        "semantic_quality_verified": False,
    }


async def run_one(
    scenario: Scenario, *, state_path: Path, report_path: Path,
    settings: OllamaSettings | None = None,
) -> dict[str, Any]:
    validate_scenario_fixtures()
    preflight = evidence_preflight(scenario)
    raw = await run_open_weights_task(
        settings=settings or OllamaSettings.from_env(),
        prompt=scenario_prompt(scenario),
        prompt_style="scenario",
        evaluation_target=(scenario.learner, scenario.competency),
        expected_outcome=scenario.expected,
        allow_candidate_action=preflight["longitudinal_eligible"],
        state_path=state_path,
        report_path=report_path,
    )
    result = grade_scenario(raw, scenario)
    result["outcome_stages"] = [
        {"stage": stage["stage"], **grade_scenario(stage, scenario)}
        for stage in raw.get("outcome_stages", [])
    ]
    result["evidence_preflight"] = preflight
    result["model_report_path"] = str(report_path)
    return result


def run_suite(
    *, output_root: Path = DEFAULT_OUTPUT, timeout: int = 600,
    scenarios: tuple[str, ...] | None = None, runner=None,
) -> dict[str, Any]:
    """Save every selected subprocess outcome without skipping failures."""

    selected = select_scenarios(scenarios)
    if not 60 <= timeout <= 3600:
        raise ValueError("timeout must be between 60 and 3600 seconds")
    validate_scenario_fixtures()
    root = output_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix="suite-", dir=root))
    runner = runner or subprocess.run
    records = []
    for scenario in selected:
        folder = directory / scenario.ident
        folder.mkdir()
        state = folder / "state.json"
        report_path = folder / "report.json"
        result_path = folder / "result.json"
        cmd = [
            sys.executable, "-m", "mwalimulens.multi_scenario_eval", "--single-run",
            "--scenario", scenario.ident, "--state", str(state),
            "--report", str(report_path), "--result", str(result_path),
        ]
        started = time.monotonic()
        failure = None
        completed = None
        partial_stdout = ""
        partial_stderr = ""
        try:
            completed = runner(
                cmd, cwd=PROJECT_ROOT, capture_output=True, text=True,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            failure = f"Timeout after {timeout} seconds"
            partial_stdout = _subprocess_output_text(exc.stdout)
            partial_stderr = _subprocess_output_text(exc.stderr)
        except OSError as exc:
            failure = f"Process error: {type(exc).__name__}"
        (folder / "stdout.txt").write_text(
            (completed.stdout or "") if completed else partial_stdout,
            encoding="utf-8",
        )
        (folder / "stderr.txt").write_text(
            (completed.stderr or "") if completed else partial_stderr,
            encoding="utf-8",
        )
        record = {
            "scenario": scenario.ident,
            "expected_outcome": scenario.expected,
            "status": "fail",
            "first_stage_status": "unknown",
            "duration_seconds": round(time.monotonic() - started, 2),
            "returncode": completed.returncode if completed else None,
            "failure": failure,
            "partial_progress": inspect_partial_state(state),
            "partial_model_requests": inspect_partial_model_trace(
                folder / "model_requests.jsonl"
            ),
        }
        if result_path.is_file():
            try:
                evaluated = json.loads(result_path.read_text(encoding="utf-8"))
                record["checks"] = evaluated.get("checks")
                record["outcome_stages"] = evaluated.get("outcome_stages", [])
                record["application_idempotency_applied"] = evaluated.get(
                    "application_idempotency_applied", False
                )
                record["deduplicated_candidate_attempts"] = evaluated.get(
                    "deduplicated_candidate_attempts", 0
                )
                initial = next(
                    (
                        stage for stage in record["outcome_stages"]
                        if stage.get("stage") == "initial"
                    ), None
                )
                if initial is not None:
                    record["first_stage_status"] = initial.get("status", "unknown")
                if completed and completed.returncode == 0:
                    record["status"] = evaluated["status"]
            except (OSError, ValueError, KeyError):
                record["failure"] = "Invalid scenario result"
        elif failure is None:
            record["failure"] = "Scenario result missing"
        if completed and completed.returncode != 0 and record["failure"] is None:
            record["failure"] = f"Scenario process exit code {completed.returncode}"
        records.append(record)
        print(f"{scenario.ident}: {record['status']} "
              f"({record['duration_seconds']}s; "
              f"initial={record['first_stage_status']})", flush=True)
    summary = {
        "status": "pass" if all(item["status"] == "pass" for item in records) else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "selection_mode": "focused" if scenarios is not None else "full",
        "selected_scenarios": [scenario.ident for scenario in selected],
        "scenario_count": len(selected),
        "total_available_scenarios": len(SCENARIOS),
        "first_stage_passed": sum(
            item["first_stage_status"] == "pass" for item in records
        ),
        "first_stage_unknown": sum(
            item["first_stage_status"] == "unknown" for item in records
        ),
        "passed": sum(item["status"] == "pass" for item in records),
        "failed": sum(item["status"] != "pass" for item in records),
        "model": OllamaSettings.from_env().model_name,
        "results": records,
        "manual_semantic_review_required": True,
        "semantic_quality_verified": False,
        "limitations": (
            "One attempt per fictional scenario; do not infer deployment readiness."
        ),
    }
    path = directory / "summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return {"summary_path": str(path), **summary}


def diagnose_saved_suite(directory: Path) -> dict[str, Any]:
    """Inspect existing run evidence without rerunning Qwen or changing grades."""

    root = Path(directory).expanduser().resolve()
    summary_path = root / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    result = {"suite": str(root), "cases": [], "original_status": summary["status"]}
    names = summary.get("selected_scenarios")
    selected = select_scenarios(tuple(names)) if names is not None else SCENARIOS
    summary_records = {
        record.get("scenario"): record for record in summary.get("results", [])
        if isinstance(record, dict)
    }
    for scenario in selected:
        folder = root / scenario.ident
        entry: dict[str, Any] = {"scenario": scenario.ident}
        result_file, report_file = folder / "result.json", folder / "report.json"
        if not result_file.is_file() or not report_file.is_file():
            saved = summary_records.get(scenario.ident, {})
            failure = saved.get("failure")
            is_timeout = isinstance(failure, str) and failure.startswith(
                "Timeout after "
            )
            entry.update({
                "classification": (
                    "timeout_without_final_report" if is_timeout else "missing_report"
                ),
                "status": "unknown",
                "recorded_suite_status": saved.get("status"),
                "failure": failure,
                "partial_progress": inspect_partial_state(folder / "state.json"),
                "partial_model_requests": inspect_partial_model_trace(
                    folder / "model_requests.jsonl"
                ),
                "final_report_available": report_file.is_file(),
                "scenario_result_available": result_file.is_file(),
            })
            result["cases"].append(entry)
            continue
        evaluated = json.loads(result_file.read_text(encoding="utf-8"))
        report = json.loads(report_file.read_text(encoding="utf-8"))
        failed = [
            name for name, passed in (evaluated.get("checks") or {}).items()
            if passed is False
        ]
        calls = report.get("tool_call_summary") or []
        names = [item.get("tool_name") for item in calls]
        error = report.get("error") or {}
        candidates = report.get("pending_reviews") or []
        response = str(report.get("final_output") or "").strip()
        if error:
            reason = "model_or_tool_exception"
        elif scenario.expected == "abstain" and (
            "flag_pattern_for_review" in names or candidates
        ):
            reason = "candidate_attempted_when_abstention_required"
        elif scenario.expected == "candidate" and not candidates:
            reason = "candidate_not_created"
        elif "counter_evidence_present" in failed:
            reason = "counter_evidence_missing"
        elif failed:
            reason = "other_acceptance_failure"
        else:
            reason = "passed"
        entry.update({
            "status": evaluated.get("status"),
            "classification": reason,
            "failed_checks": failed,
            "model_error_type": error.get("type"),
            "model_error_message": error.get("message"),
            "tool_calls": [
                {"name": item.get("tool_name"), "status": item.get("status")}
                for item in calls
            ],
            "candidate_count": len(candidates),
            "candidate_ids": [
                {
                    "support": item.get("supporting_evidence_ids"),
                    "counter": item.get("counter_evidence_ids"),
                }
                for item in candidates
            ],
            "response": response,
            # Preserve the two different rubrics and cumulative request boundaries.
            # Never regrade saved stages using today's code or source fixtures.
            "report_outcome_stages": report.get("outcome_stages", []),
            "result_outcome_stages": evaluated.get("outcome_stages", []),
            "outcome_stages_note": report.get("outcome_stages_note"),
            "initial_output": report.get("initial_output"),
            "grounding_correction": report.get("grounding_correction"),
            "completion_recovery": report.get("completion_recovery"),
            "candidate_action_available": report.get("candidate_action_available"),
            "agent_tool_allowlist": report.get("agent_tool_allowlist"),
            "pending_reviews": candidates,
            "model_request_count_observed": report.get("model_request_count_observed"),
            "model_requests": report.get("model_requests", []),
            "request_metadata_note": (
                "An initial stage is an agent run, not the first model request. "
                "retry_feedback_count counts feedback in each request's history; "
                "do not sum it across requests. Requested tools may fail before service audit."
            ),
            "recovery": {
                "attempted": (report.get("completion_recovery") or {}).get("attempted"),
                "succeeded": (report.get("completion_recovery") or {}).get("succeeded"),
            },
        })
        result["cases"].append(entry)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--scenarios", nargs="+", choices=[case.ident for case in SCENARIOS],
        help="Run only the named scenarios (default: all four).",
    )
    parser.add_argument("--diagnose", type=Path,
                        help="Inspect an existing suite without running Qwen.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--single-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", choices=[s.ident for s in SCENARIOS])
    parser.add_argument("--state", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.diagnose is not None:
        try:
            diagnostic = diagnose_saved_suite(args.diagnose)
        except (OSError, KeyError, ValueError) as exc:
            print(f"Cannot inspect saved suite: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(diagnostic, indent=2, ensure_ascii=False))
        return 0
    if args.single_run:
        if not all((args.scenario, args.state, args.report, args.result)):
            parser.error("--single-run requires scenario, state, report and result")
        result = asyncio.run(run_one(
            scenario_by_id(args.scenario),
            state_path=args.state, report_path=args.report,
        ))
        args.result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"Scenario {args.scenario}: {result['status']}")
        return 0 if result["status"] == "pass" else 2
    report = run_suite(
        output_root=args.output_dir, timeout=args.timeout,
        scenarios=tuple(args.scenarios) if args.scenarios is not None else None,
    )
    print(f"Summary: {report['summary_path']}")
    print(f"Scope: {report['selection_mode']} "
          f"({report['scenario_count']}/{report['total_available_scenarios']} cases)")
    print(f"Initial-stage passes: {report['first_stage_passed']}")
    print(f"Final passes: {report['passed']}/{report['scenario_count']}")
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
