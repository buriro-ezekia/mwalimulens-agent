"""Executable open-weights Qwen/Ollama challenge run and evidence report."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import urlparse

from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.usage import RunUsage, UsageLimits

from mwalimulens.agent.execution import ExecutionLimits, atomic_json
from mwalimulens.agent.grounding import correction_prompt, verify_abstention_terms
from mwalimulens.agent.ollama import (
    DEFAULT_OLLAMA_MODEL,
    OllamaSettings,
    build_ollama_agent,
    prewarm_ollama_async,
)
from mwalimulens.agent.orchestrator import (
    AGENT_MCP_TOOL_ALLOWLIST,
    CANDIDATE_REVIEW_POLICY,
)
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore

DEFAULT_OPEN_WEIGHTS_STATE_PATH = PROJECT_ROOT / "runtime" / "open_weights_state.json"
DEFAULT_OPEN_WEIGHTS_REPORT_PATH = PROJECT_ROOT / "runtime" / "open_weights_run.json"

COMPLETION_RECOVERY_PROMPT = f"""
You have already retrieved evidence for the original learner task, but you did not complete the
workflow action.

{CANDIDATE_REVIEW_POLICY}

For this recovery turn, do not use "strong enough for a permanent label" as the threshold. A
permanent label is prohibited and is not what flag_pattern_for_review does. A qualified candidate
such as "scores improved across terms while independent explanation remained inconsistent" is
appropriate when the retrieved evidence supports it.

Choose exactly one outcome:

1. If you can support a bounded cross-term pattern with at least two concrete supporting evidence
   IDs from the retrieved evidence and at least one relevant counter-evidence ID, call
   flag_pattern_for_review now. Include the qualified claim, those evidence IDs, explicit
   uncertainty, and a useful teacher question.
2. If those conditions are not met, do not call the action tool. Return a final response beginning
   with "ABSTAIN:" and identify the missing evidence condition.

Do not ask the user for permission again. Do not call or attempt any teacher-review action. Do not
invent evidence IDs.
""".strip()

CONCISE_OPEN_WEIGHTS_TASK = """
Assess fictional learner L001 on MATH-FRACTIONS across terms using MCP evidence.

Retrieve competency evidence before forming a conclusion. If it supports a bounded
longitudinal pattern, call flag_pattern_for_review with at least two exact supporting
evidence IDs, relevant counter-evidence IDs, explicit uncertainty and one useful
teacher question. Preserve mixed evidence; never invent IDs or infer a permanent trait.
If evidence is insufficient, abstain without calling the action tool.

Keep the final response concise. Do not repeat all retrieved observations in prose.
The candidate remains pending teacher review; never approve, edit, reject, rank,
permanently label, assign a pathway or modify a learner profile.
""".strip()

PROMPT_STYLES = {
    "baseline": None,
    "concise": CONCISE_OPEN_WEIGHTS_TASK,
    "scenario": None,
}

SCENARIO_RECOVERY_PROMPT = """
The evidence tools have been called, but no pending review candidate was created.
Reconsider the evidence you already retrieved for learner {learner_id}, competency
{competency_code}. Compare dated assessment scores and check qualitative observations
for limitations. A provisional pattern is not a permanent label.

If a bounded longitudinal statement is defensible, submit it using
flag_pattern_for_review with at least two exact supporting IDs from different
terms, relevant counter-evidence IDs, uncertainty and a teacher question.
Otherwise reply beginning with ABSTAIN: and identify the specific missing evidence. Do not
invent evidence, ask for permission or use the teacher-review tool.
""".strip()

SCENARIO_READ_ONLY_RECOVERY_PROMPT = """
The candidate action is unavailable in this run for learner {learner_id}, competency
{competency_code}. Your previous response did not meet the final-response contract.
Using only the retrieved evidence, respond beginning with ABSTAIN: and explain the
specific missing evidence condition. Do not place an introduction before ABSTAIN:.
Do not invent evidence or attempt any candidate or teacher-review action.
""".strip()


def _recovery_prompt(
    prompt_style: str, evaluation_target: tuple[str, str], *,
    allow_candidate_action: bool = True,
) -> str:
    """Use the original recovery for legacy runs and a target-specific one for scenarios."""

    if prompt_style != "scenario":
        return COMPLETION_RECOVERY_PROMPT
    template = (
        SCENARIO_RECOVERY_PROMPT if allow_candidate_action
        else SCENARIO_READ_ONLY_RECOVERY_PROMPT
    )
    return template.format(
        learner_id=evaluation_target[0], competency_code=evaluation_target[1]
    )


DEFAULT_OPEN_WEIGHTS_TASK = """
Assess learner L001's longitudinal MATH-FRACTIONS evidence.

Use the MCP evidence tools rather than relying on prior assumptions. Retrieve the competency
evidence, compare the evidence across terms, identify supporting evidence and counter-evidence,
and state uncertainty explicitly. A single result is not enough for a durable claim.

If the longitudinal evidence supports a cautious candidate pattern, call flag_pattern_for_review
with concrete evidence IDs, counter-evidence IDs, uncertainty, and a useful teacher question.
This creates only a provisional pending candidate, not a permanent label or profile update. Mixed
evidence should be represented as counter-evidence and uncertainty rather than used as an automatic
reason to abstain. Do not ask for permission again before this bounded action.

Do not attempt to approve, edit or reject the candidate: that is reserved for the human teacher.
""".strip()


def _pending_cancellation(exc: BaseException) -> asyncio.CancelledError | None:
    """Recover task cancellation hidden by an exception during async cleanup."""

    task = asyncio.current_task()
    if task is None or not task.cancelling():
        return None
    pending = [exc]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, asyncio.CancelledError):
            return current
        pending.extend(item for item in (current.__cause__, current.__context__) if item)
        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
    return None


async def run_open_weights_task(
    *,
    settings: OllamaSettings | None = None,
    prompt: str = DEFAULT_OPEN_WEIGHTS_TASK,
    prompt_style: str = "baseline",
    evaluation_target: tuple[str, str] = ("L001", "MATH-FRACTIONS"),
    expected_outcome: str = "candidate",
    allow_candidate_action: bool = True,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_OPEN_WEIGHTS_STATE_PATH,
    report_path: Path = DEFAULT_OPEN_WEIGHTS_REPORT_PATH,
    execution_limits: ExecutionLimits | None = None,
) -> dict[str, Any]:
    """Run one local Qwen task and always persist judge-inspectable evidence."""

    settings = settings or OllamaSettings.from_env()
    execution_limits = execution_limits or ExecutionLimits()
    usage = RunUsage()
    usage_limits = UsageLimits(request_limit=execution_limits.request_limit)
    deadline = asyncio.get_running_loop().time() + execution_limits.deadline_seconds
    if expected_outcome not in {"candidate", "abstain"}:
        raise ValueError("Unknown expected outcome")
    if len(evaluation_target) != 2 or not all(
        isinstance(part, str) and part.strip() for part in evaluation_target
    ):
        raise ValueError("Evaluation target needs learner and competency IDs")
    if prompt_style not in PROMPT_STYLES:
        raise ValueError("Unknown prompt style")
    if prompt_style == "concise":
        if prompt != DEFAULT_OPEN_WEIGHTS_TASK:
            raise ValueError("Concise mode cannot override a custom prompt")
        prompt = CONCISE_OPEN_WEIGHTS_TASK
    if prompt_style == "scenario" and prompt == DEFAULT_OPEN_WEIGHTS_TASK:
        raise ValueError("Scenario mode requires an explicit custom task prompt")
    state_path = state_path.resolve()
    report_path = report_path.resolve()

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    request_trace_path = (
        state_path.with_name("model_requests.jsonl")
        if prompt_style == "scenario" else None
    )
    if request_trace_path is not None:
        request_trace_path.unlink(missing_ok=True)

    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    timings: dict[str, float | None] = {
        "agent_build_seconds": None,
        "initial_agent_run_seconds": None,
        "recovery_agent_run_seconds": None,
    }
    initial_output = ""
    final_output = ""
    recovery_attempted = False
    recovery_output: str | None = None
    grounding_correction: dict[str, Any] = {
        "attempted": False, "original_abstention": None,
        "factual_contradictions": [], "verified_term_count": None, "output": None,
    }
    error: dict[str, str] | None = None
    state_store = JsonStateStore(state_path)
    model_requests: list[dict[str, Any]] = []
    preload: dict[str, Any] = {
        "attempted": False, "status": "disabled", "seconds": None,
    }
    outcome_stages: list[dict[str, Any]] = []
    active_stage: str | None = None
    termination: dict[str, Any] | None = None
    cancellation: asyncio.CancelledError | None = None
    cleanup_error: dict[str, str] | None = None
    request_events: list[dict[str, Any]] = []
    retrieval_events: list[dict[str, Any]] = []
    progress_path = report_path.with_suffix(".progress.json")

    def checkpoint() -> None:
        atomic_json(progress_path, {
            "status": "in_progress" if termination is None else "fail",
            "outcome_stages": outcome_stages, "active_stage": active_stage,
            "active_stage_outcome": "unknown" if active_stage else None,
            "initial_output": initial_output, "last_completed_output": final_output,
            "model_requests": model_requests, "request_events": request_events,
            "retrieval_events": retrieval_events, "termination": termination,
            "cleanup_error": cleanup_error,
            "grounding_correction": grounding_correction,
            "request_limit": execution_limits.request_limit,
            "deadline_seconds": execution_limits.deadline_seconds,
        })

    def request_event(event: dict[str, Any]) -> None:
        request_events.append(event)
        checkpoint()

    def record_termination(exc: BaseException, *, during_stage: bool = False) -> None:
        nonlocal termination, error, cancellation
        interrupted = exc if isinstance(exc, asyncio.CancelledError) else _pending_cancellation(exc)
        if interrupted is not None and (not during_stage or not deadline_scope.expired()):
            # Outside the timeout context its own cancellation has been consumed;
            # external cancellation must propagate even after an earlier limit failure.
            cancellation = interrupted
        if termination is not None:
            return
        reason = (
            "deadline_exceeded" if deadline_scope.expired() else
            "cancelled" if interrupted is not None else
            "request_budget_exhausted" if isinstance(exc, UsageLimitExceeded) else
            "request_timeout"
        )
        termination = {"reason": reason, "active_stage": active_stage}
        error = {"type": type(exc).__name__, "message": str(exc) or reason}
        checkpoint()

    async def run_stage(agent, prompt, **kwargs):
        checkpoint()
        try:
            return await agent.run(
                prompt, usage=usage, usage_limits=usage_limits, **kwargs,
            )
        except (TimeoutError, UsageLimitExceeded, asyncio.CancelledError) as exc:
            # Save interruption before MCP teardown can raise a different exception.
            record_termination(exc, during_stage=True)
            raise

    def record_stage(output: str) -> None:
        nonlocal active_stage
        # Snapshot now: later candidate creation must not rewrite the initial outcome.
        snapshot = build_open_weights_report(
            settings=settings, prompt=prompt, final_output=output,
            state_store=state_store, started_at=started_at,
            finished_at=datetime.now(UTC), error=error,
            prompt_style=prompt_style, evaluation_target=evaluation_target,
            expected_outcome=expected_outcome,
            allow_candidate_action=allow_candidate_action,
        )
        outcome_stages.append({
            "stage": active_stage,
            "model_requests_observed_through": len(model_requests),
            **{key: snapshot[key] for key in (
                "status", "checks", "evaluation_target", "final_output",
                "audited_tool_names", "tool_call_summary", "pending_reviews",
                "pending_review_count", "teacher_review_count", "profile_update_count",
                "candidate_submission_deduplicated_count",
                "candidate_submission_audited_attempt_count", "error",
            )},
        })
        if error is None:
            active_stage = None
        checkpoint()

    try:
        async with asyncio.timeout_at(deadline) as deadline_scope:
            if settings.keep_alive is not None:
                preload = {
                    "attempted": True, "status": "running", "seconds": None,
                    "requested_keep_alive": settings.keep_alive,
                }
                preload = await prewarm_ollama_async(settings)

            build_clock = perf_counter()
            agent = build_ollama_agent(
                settings=settings,
                data_dir=data_dir,
                state_path=state_path,
                records=model_requests,
                audit_snapshot=lambda: tuple(
                    item.get("tool_name") for item in state_store.tool_calls()
                ),
                trace_path=request_trace_path,
                stage_snapshot=lambda: active_stage,
                on_request_event=request_event,
                competency_review_target=evaluation_target if prompt_style == "scenario" else None,
                retrieval_events=retrieval_events,
                tool_error_behavior="retry" if prompt_style == "scenario" else "error",
                allow_candidate_action=allow_candidate_action,
            )
            timings["agent_build_seconds"] = round(perf_counter() - build_clock, 3)
            async with agent:
                active_stage = "initial"
                initial_clock = perf_counter()
                try:
                    result = await run_stage(
                        agent,
                        prompt,
                        model_settings={"temperature": 0},
                    )
                finally:
                    timings["initial_agent_run_seconds"] = round(
                        perf_counter() - initial_clock, 3
                    )
                initial_output = str(result.output)
                final_output = initial_output
                record_stage(final_output)
                active_stage = None

                if prompt_style == "scenario" and final_output.strip().upper().startswith(
                    "ABSTAIN:"
                ):
                    facts = verify_abstention_terms(
                        final_output, evaluation_target[0], evaluation_target[1], data_dir
                    )
                    grounding_correction.update({
                        "original_abstention": final_output,
                        "factual_contradictions": facts["factual_contradictions"],
                        "verified_term_count": facts["verified_term_count"],
                        "verified_term_ids": facts["verified_term_ids"],
                    })
                    if facts["factual_contradictions"]:
                        grounding_correction["attempted"] = True
                        active_stage = "grounding_correction"
                        correction_started = perf_counter()
                        try:
                            result = await run_stage(
                                agent,
                                correction_prompt(
                                    evaluation_target[0], evaluation_target[1], facts
                                ),
                                message_history=result.all_messages(),
                                model_settings={"temperature": 0},
                            )
                            final_output = str(result.output)
                            grounding_correction["output"] = final_output
                            record_stage(final_output)
                            active_stage = None
                        finally:
                            grounding_correction["duration_seconds"] = round(
                                perf_counter() - correction_started, 3
                            )

                should_recover = _should_attempt_completion_recovery(state_store)
                if prompt_style == "scenario":
                    # An explicit abstention must remain an observed outcome, not
                    # be repaired using the evaluation's hidden expected label.
                    should_recover = (
                        should_recover
                        and not final_output.strip().upper().startswith("ABSTAIN:")
                    )
                elif expected_outcome != "candidate":
                    should_recover = False

                if should_recover:
                    recovery_attempted = True
                    active_stage = "completion_recovery"
                    recovery_clock = perf_counter()
                    try:
                        recovery_result = await run_stage(
                            agent,
                            _recovery_prompt(
                                prompt_style, evaluation_target,
                                allow_candidate_action=allow_candidate_action,
                            ),
                            message_history=result.all_messages(),
                            model_settings={"temperature": 0},
                        )
                    finally:
                        timings["recovery_agent_run_seconds"] = round(
                            perf_counter() - recovery_clock, 3
                        )
                    recovery_output = str(recovery_result.output)
                    final_output = recovery_output
                    record_stage(final_output)
                    active_stage = None
    except (TimeoutError, UsageLimitExceeded, asyncio.CancelledError) as exc:
        if preload["status"] == "running":
            preload["status"] = "interrupted"
        record_termination(exc)
    except Exception as exc:
        if deadline_scope.expired() or _pending_cancellation(exc) is not None:
            # The interruption may first occur in preload/MCP __aexit__, after
            # run_stage has returned, and be masked by a cleanup exception.
            record_termination(exc)
        if termination is not None and preload["status"] == "running":
            preload["status"] = "interrupted"
        elif settings.keep_alive is not None and preload["status"] in {"disabled", "running"}:
            preload = {
                "attempted": True,
                "status": "error",
                "seconds": None,
                "requested_keep_alive": settings.keep_alive,
            }
        if termination is not None:
            cleanup_error = {"type": type(exc).__name__, "message": str(exc)}
            checkpoint()
        else:
            error = {"type": type(exc).__name__, "message": str(exc)}
            if active_stage is not None:
                record_stage("")

    timings["total_wall_seconds"] = round(perf_counter() - started_clock, 3)
    finished_at = datetime.now(UTC)
    report = build_open_weights_report(
        settings=settings,
        prompt=prompt,
        initial_output=initial_output,
        final_output=final_output,
        recovery_attempted=recovery_attempted,
        recovery_output=recovery_output,
        state_store=state_store,
        started_at=started_at,
        finished_at=finished_at,
        error=error,
        timings=timings,
        model_requests=model_requests,
        preload=preload,
        prompt_style=prompt_style,
        evaluation_target=evaluation_target,
        expected_outcome=expected_outcome,
        allow_candidate_action=allow_candidate_action,
        grounding_correction=grounding_correction,
        outcome_stages=outcome_stages,
    )
    report.update({
        "termination": termination, "active_stage": active_stage,
        "cleanup_error": cleanup_error,
        "active_stage_outcome": "unknown" if termination and active_stage else None,
        "request_events": request_events, "retrieval_events": retrieval_events,
        "model_requests_used": usage.requests,
        "execution_limits": {"request_limit": execution_limits.request_limit,
                             "deadline_seconds": execution_limits.deadline_seconds},
    })
    atomic_json(report_path, report)
    atomic_json(progress_path, report)
    if cancellation is not None:
        raise cancellation
    return report


def build_open_weights_report(
    *,
    settings: OllamaSettings,
    prompt: str,
    final_output: str,
    state_store: JsonStateStore,
    started_at: datetime,
    finished_at: datetime,
    initial_output: str | None = None,
    recovery_attempted: bool = False,
    recovery_output: str | None = None,
    error: dict[str, str] | None = None,
    timings: dict[str, float | None] | None = None,
    model_requests: list[dict[str, Any]] | None = None,
    preload: dict[str, Any] | None = None,
    prompt_style: str = "baseline",
    evaluation_target: tuple[str, str] = ("L001", "MATH-FRACTIONS"),
    expected_outcome: str = "candidate",
    allow_candidate_action: bool = True,
    grounding_correction: dict[str, Any] | None = None,
    outcome_stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact report from auditable state; never store hidden reasoning."""

    learner_id, competency_code = evaluation_target
    tool_calls = state_store.tool_calls()
    tool_names = [item.get("tool_name") for item in tool_calls]
    pending_reviews = state_store.pending_reviews()
    teacher_reviews = state_store.teacher_reviews()
    profile_updates = state_store.profile_updates()

    target_retrieval = any(
        (
            item.get("tool_name") == "get_competency_evidence"
            and item.get("inputs", {}).get("learner_id") == learner_id
            and item.get("inputs", {}).get("competency_code") == competency_code
        )
        or (
            item.get("tool_name") == "get_learner_timeline"
            and item.get("inputs", {}).get("learner_id") == learner_id
        )
        for item in tool_calls
    )
    target_candidates = [
        item
        for item in pending_reviews
        if item.get("learner_id") == learner_id
        and item.get("competency_code") == competency_code
    ]

    checks = {
        "local_ollama_endpoint": _is_local_endpoint(settings.base_url),
        "qwen_model": "qwen" in settings.model_name.lower(),
        "retrieved_target_evidence": target_retrieval,
        "submitted_candidate": (
            "flag_pattern_for_review" in tool_names if expected_outcome == "candidate"
            else "flag_pattern_for_review" not in tool_names
        ),
        "tool_calls_succeeded": bool(tool_calls)
        and all(item.get("status") == "success" for item in tool_calls),
        "forbidden_teacher_review_absent": "record_teacher_review" not in tool_names,
        "pending_teacher_review_created": (
            len(pending_reviews) >= 1 if expected_outcome == "candidate"
            else len(pending_reviews) == 0
        ),
        "candidate_matches_task": (
            bool(target_candidates) if expected_outcome == "candidate"
            else len(target_candidates) == 0
        ),
        "candidate_cites_support_and_counter": (
            any(
                len(item.get("supporting_evidence_ids") or []) >= 2
                and bool(item.get("counter_evidence_ids"))
                for item in target_candidates
            ) if expected_outcome == "candidate" else not target_candidates
        ),
        "final_output_present": bool(final_output.strip()),
        "teacher_review_absent": len(teacher_reviews) == 0,
        "profile_update_absent": len(profile_updates) == 0,
    }

    if expected_outcome == "abstain":
        checks["explicit_abstention"] = final_output.strip().upper().startswith("ABSTAIN:")
    status = "pass" if error is None and all(checks.values()) else "fail"
    recovery_succeeded = recovery_attempted and status == "pass"
    visible_tools = set(AGENT_MCP_TOOL_ALLOWLIST)
    if prompt_style == "scenario":
        visible_tools.discard("get_learner_timeline")
    if not allow_candidate_action:
        visible_tools.discard("flag_pattern_for_review")

    return {
        "status": status,
        "provider": "ollama",
        "open_weights": True,
        "model": settings.model_name,
        "evaluation_target": {
            "learner_id": learner_id, "competency_code": competency_code,
        },
        "expected_outcome": expected_outcome,
        "candidate_action_available": allow_candidate_action,
        "grounding_correction": grounding_correction or {
            "attempted": False, "factual_contradictions": [],
        },
        "base_url": settings.base_url,
        "started_at": _iso_timestamp(started_at),
        "finished_at": _iso_timestamp(finished_at),
        "prompt": prompt,
        "initial_output": initial_output if initial_output is not None else final_output,
        "final_output": final_output,
        "outcome_stages": list(outcome_stages or []),
        "outcome_stages_note": (
            "Each stage is an agent run and may include tool retries. Stage checks are "
            "structural report checks; the scenario evaluator applies its full rubric "
            "separately. Neither establishes semantic correctness."
        ),
        "completion_recovery": {
            "attempted": recovery_attempted,
            "succeeded": recovery_succeeded,
            "prompt": (
                _recovery_prompt(
                    prompt_style, evaluation_target,
                    allow_candidate_action=allow_candidate_action,
                )
                if recovery_attempted else None
            ),
            "output": recovery_output,
            "success_criterion": "all_report_checks",
        },
        "agent_tool_allowlist": sorted(visible_tools),
        "audited_tool_names": tool_names,
        "candidate_submission_audited_attempt_count": sum(
            item.get("tool_name") == "flag_pattern_for_review" for item in tool_calls
        ),
        "candidate_submission_deduplicated_count": sum(
            item.get("tool_name") == "flag_pattern_for_review"
            and item.get("duplicate_submission") is True for item in tool_calls
        ),
        "tool_call_summary": [
            {
                "tool_name": item.get("tool_name"),
                "status": item.get("status"),
                "timestamp": item.get("timestamp"),
                "duration_seconds": item.get("duration_seconds"),
                "duplicate_submission": item.get("duplicate_submission", False),
            }
            for item in tool_calls
        ],
        "pending_reviews": list(pending_reviews),
        "pending_review_count": len(pending_reviews),
        "teacher_review_count": len(teacher_reviews),
        "profile_update_count": len(profile_updates),
        "checks": checks,
        "ollama_keep_alive": settings.keep_alive,
        "preload": preload or {
            "attempted": False, "status": "disabled", "seconds": None,
        },
        "model_requests": list(model_requests or []),
        "model_request_count_observed": len(model_requests or []),
        "prompt_style": prompt_style,
        "timing": {
            **(timings or {}),
            "agent_run_includes_model_and_mcp": True,
            "model_only_seconds": None,
            "model_load_seconds": None,
            "per_request_wall_seconds_available": True,
            "measurement_note": (
                "Agent-run time includes model inference, MCP tool execution and "
                "orchestration. Model-only and loading time are not yet measured."
            ),
        },
        "error": error,
        "note": "No chain-of-thought is stored in this run report.",
    }


def _should_attempt_completion_recovery(state_store: JsonStateStore) -> bool:
    tool_calls = state_store.tool_calls()
    retrieved_evidence = any(
        item.get("tool_name")
        in {"get_learner_timeline", "get_competency_evidence"}
        and item.get("status") == "success"
        for item in tool_calls
    )
    submitted_candidate = any(
        item.get("tool_name") == "flag_pattern_for_review"
        and item.get("status") == "success"
        for item in tool_calls
    )
    forbidden_action = any(
        item.get("tool_name") == "record_teacher_review"
        for item in tool_calls
    )
    has_tool_error = any(item.get("status") == "error" for item in tool_calls)
    return (
        retrieved_evidence
        and not submitted_candidate
        and not forbidden_action
        and not has_tool_error
    )


def _is_local_endpoint(base_url: str) -> bool:
    hostname = (urlparse(base_url).hostname or "").lower()
    return hostname in {"localhost", "127.0.0.1", "::1"}


def _iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("run timestamps must be timezone-aware")
    return value.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the MwalimuLens local Qwen/Ollama challenge task."
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "Ollama model name; defaults to MWALIMULENS_OLLAMA_MODEL "
            f"or {DEFAULT_OLLAMA_MODEL}."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Ollama OpenAI-compatible base URL; defaults to http://localhost:11434/v1.",
    )
    parser.add_argument(
        "--prompt-style", choices=sorted(PROMPT_STYLES), default="baseline",
        help="Opt-in concise analysis prompt; baseline remains default.",
    )
    parser.add_argument(
        "--keep-alive",
        default=None,
        help="Optional local Ollama preload duration, e.g. 30m (max 1h).",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_OPEN_WEIGHTS_REPORT_PATH,
        help="Path for the JSON run-evidence report.",
    )
    args = parser.parse_args()

    env_settings = OllamaSettings.from_env()
    settings = OllamaSettings(
        model_name=args.model or env_settings.model_name,
        base_url=args.base_url or env_settings.base_url,
        keep_alive=args.keep_alive or env_settings.keep_alive,
    )

    report = asyncio.run(
        run_open_weights_task(
            settings=settings,
            report_path=args.report,
            prompt_style=args.prompt_style,
        )
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
