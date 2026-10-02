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
from mwalimulens.agent.orchestrator import AGENT_MCP_TOOL_ALLOWLIST
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore

DEFAULT_OPEN_WEIGHTS_STATE_PATH = PROJECT_ROOT / "runtime" / "open_weights_state.json"
DEFAULT_OPEN_WEIGHTS_REPORT_PATH = PROJECT_ROOT / "runtime" / "open_weights_run.json"

DEFAULT_OPEN_WEIGHTS_TASK = """
Assess learner L001's longitudinal MATH-FRACTIONS evidence.

Use the MCP evidence tools rather than relying on prior assumptions. Retrieve the competency
evidence, compare the evidence across terms, identify supporting evidence and counter-evidence,
and state uncertainty explicitly. A single result is not enough for a durable claim.

If the longitudinal evidence supports a cautious candidate pattern, call flag_pattern_for_review
with concrete evidence IDs, counter-evidence IDs, uncertainty, and a useful teacher question.
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
    final_output = ""
    error: dict[str, str] | None = None

    try:
        agent = build_ollama_agent(
            settings=settings,
            data_dir=data_dir,
            state_path=state_path,
        )
        result = await agent.run(
            prompt,
            model_settings={"temperature": 0},
        )
        final_output = str(result.output)
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    finished_at = datetime.now(UTC)
    report = build_open_weights_report(
        settings=settings,
        prompt=prompt,
        final_output=final_output,
        state_store=JsonStateStore(state_path),
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
    error: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a compact report from auditable state; never store hidden reasoning."""

    tool_calls = state_store.tool_calls()
    tool_names = [item.get("tool_name") for item in tool_calls]
    pending_reviews = state_store.pending_reviews()
    teacher_reviews = state_store.teacher_reviews()
    profile_updates = state_store.profile_updates()

    checks = {
        "local_ollama_endpoint": _is_local_endpoint(settings.base_url),
        "qwen_model": "qwen" in settings.model_name.lower(),
        "retrieved_evidence": any(
            name in {"get_learner_timeline", "get_competency_evidence"}
            for name in tool_names
        ),
        "submitted_candidate": "flag_pattern_for_review" in tool_names,
        "tool_calls_succeeded": bool(tool_calls)
        and all(item.get("status") == "success" for item in tool_calls),
        "forbidden_teacher_review_absent": "record_teacher_review" not in tool_names,
        "pending_teacher_review_created": len(pending_reviews) >= 1,
        "candidate_matches_task": any(
            item.get("learner_id") == "L001"
            and item.get("competency_code") == "MATH-FRACTIONS"
            for item in pending_reviews
        ),
        "teacher_review_absent": len(teacher_reviews) == 0,
        "profile_update_absent": len(profile_updates) == 0,
    }

    status = "pass" if error is None and all(checks.values()) else "fail"

    return {
        "status": status,
        "provider": "ollama",
        "open_weights": True,
        "model": settings.model_name,
        "base_url": settings.base_url,
        "started_at": _iso_timestamp(started_at),
        "finished_at": _iso_timestamp(finished_at),
        "prompt": prompt,
        "final_output": final_output,
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
