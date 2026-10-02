"""Executable open-weights Qwen/Ollama challenge run and evidence report."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mwalimulens.agent.ollama import OllamaSettings, build_ollama_agent
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


async def run_open_weights_task(
    *,
    settings: OllamaSettings | None = None,
    prompt: str = DEFAULT_OPEN_WEIGHTS_TASK,
    data_dir: Path = DEFAULT_DATA_DIR,
    state_path: Path = DEFAULT_OPEN_WEIGHTS_STATE_PATH,
    report_path: Path = DEFAULT_OPEN_WEIGHTS_REPORT_PATH,
) -> dict[str, Any]:
    """Run one local Qwen task and always persist judge-inspectable evidence."""

    settings = settings or OllamaSettings.from_env()
    state_path = state_path.resolve()
    report_path = report_path.resolve()

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)

    started_at = datetime.now(UTC)
    initial_output = ""
    final_output = ""
    recovery_attempted = False
    recovery_output: str | None = None
    error: dict[str, str] | None = None
    state_store = JsonStateStore(state_path)

    try:
        agent = build_ollama_agent(
            settings=settings,
            data_dir=data_dir,
            state_path=state_path,
        )
        async with agent:
            result = await agent.run(
                prompt,
                model_settings={"temperature": 0},
            )
            initial_output = str(result.output)
            final_output = initial_output

            if _should_attempt_completion_recovery(state_store):
                recovery_attempted = True
                recovery_result = await agent.run(
                    COMPLETION_RECOVERY_PROMPT,
                    message_history=result.all_messages(),
                    model_settings={"temperature": 0},
                )
                recovery_output = str(recovery_result.output)
                final_output = recovery_output
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

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
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
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
) -> dict[str, Any]:
    """Build a compact report from auditable state; never store hidden reasoning."""

    tool_calls = state_store.tool_calls()
    tool_names = [item.get("tool_name") for item in tool_calls]
    pending_reviews = state_store.pending_reviews()
    teacher_reviews = state_store.teacher_reviews()
    profile_updates = state_store.profile_updates()

    target_retrieval = any(
        (
            item.get("tool_name") == "get_competency_evidence"
            and item.get("inputs", {}).get("learner_id") == "L001"
            and item.get("inputs", {}).get("competency_code") == "MATH-FRACTIONS"
        )
        or (
            item.get("tool_name") == "get_learner_timeline"
            and item.get("inputs", {}).get("learner_id") == "L001"
        )
        for item in tool_calls
    )
    target_candidates = [
        item
        for item in pending_reviews
        if item.get("learner_id") == "L001"
        and item.get("competency_code") == "MATH-FRACTIONS"
    ]

    checks = {
        "local_ollama_endpoint": _is_local_endpoint(settings.base_url),
        "qwen_model": "qwen" in settings.model_name.lower(),
        "retrieved_target_evidence": target_retrieval,
        "submitted_candidate": "flag_pattern_for_review" in tool_names,
        "tool_calls_succeeded": bool(tool_calls)
        and all(item.get("status") == "success" for item in tool_calls),
        "forbidden_teacher_review_absent": "record_teacher_review" not in tool_names,
        "pending_teacher_review_created": len(pending_reviews) >= 1,
        "candidate_matches_task": bool(target_candidates),
        "candidate_cites_support_and_counter": any(
            bool(item.get("supporting_evidence_ids"))
            and bool(item.get("counter_evidence_ids"))
            for item in target_candidates
        ),
        "final_output_present": bool(final_output.strip()),
        "teacher_review_absent": len(teacher_reviews) == 0,
        "profile_update_absent": len(profile_updates) == 0,
    }

    status = "pass" if error is None and all(checks.values()) else "fail"
    recovery_succeeded = (
        recovery_attempted and "flag_pattern_for_review" in tool_names
    )

    return {
        "status": status,
        "provider": "ollama",
        "open_weights": True,
        "model": settings.model_name,
        "base_url": settings.base_url,
        "started_at": _iso_timestamp(started_at),
        "finished_at": _iso_timestamp(finished_at),
        "prompt": prompt,
        "initial_output": initial_output if initial_output is not None else final_output,
        "final_output": final_output,
        "completion_recovery": {
            "attempted": recovery_attempted,
            "succeeded": recovery_succeeded,
            "prompt": COMPLETION_RECOVERY_PROMPT if recovery_attempted else None,
            "output": recovery_output,
        },
        "agent_tool_allowlist": sorted(AGENT_MCP_TOOL_ALLOWLIST),
        "audited_tool_names": tool_names,
        "tool_call_summary": [
            {
                "tool_name": item.get("tool_name"),
                "status": item.get("status"),
                "timestamp": item.get("timestamp"),
            }
            for item in tool_calls
        ],
        "pending_reviews": list(pending_reviews),
        "pending_review_count": len(pending_reviews),
        "teacher_review_count": len(teacher_reviews),
        "profile_update_count": len(profile_updates),
        "checks": checks,
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
        help="Ollama model name; defaults to MWALIMULENS_OLLAMA_MODEL or qwen2.5:1.5b.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Ollama OpenAI-compatible base URL; defaults to http://localhost:11434/v1.",
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
    )

    report = asyncio.run(
        run_open_weights_task(
            settings=settings,
            report_path=args.report,
        )
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
