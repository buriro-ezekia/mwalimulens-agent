"""Fast judge-facing demo using the real MCP boundaries."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import webbrowser
from pathlib import Path
from typing import Any

from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from mwalimulens.agent.borrowed_filesystem import (
    BORROWED_FILESYSTEM_TOOL_ALLOWLIST,
    DEFAULT_BORROWED_MCP_STDERR,
    DEFAULT_REFERENCE_DIR,
    build_borrowed_filesystem_toolset,
)
from mwalimulens.agent.orchestrator import AGENT_MCP_TOOL_ALLOWLIST, build_agent
from mwalimulens.demo_view import render_demo_html
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.state import JsonStateStore

DEFAULT_DEMO_STATE_PATH = PROJECT_ROOT / "runtime" / "demo_state.json"
DEFAULT_DEMO_REPORT_PATH = PROJECT_ROOT / "runtime" / "demo_run.json"
DEFAULT_DEMO_HTML_PATH = PROJECT_ROOT / "runtime" / "mwalimulens_demo.html"
DEFAULT_DEMO_STDERR_PATH = PROJECT_ROOT / "runtime" / "demo_borrowed_mcp_stderr.log"
REFERENCE_FILE = DEFAULT_REFERENCE_DIR / "math_fractions_reference.md"
OPEN_WEIGHTS_EVIDENCE = PROJECT_ROOT / "evidence" / "open_weights_run.json"
CHALLENGE_EVIDENCE = PROJECT_ROOT / "evidence" / "challenge_run.json"
EVAL_EVIDENCE = PROJECT_ROOT / "evidence" / "evals_run.json"

DEMO_CLAIM = (
    "Fraction performance improved across terms, while independent explanation remained mixed."
)
DEMO_UNCERTAINTY = (
    "Scores rose across terms, but EV-008 shows difficulty justifying an open-ended method "
    "independently."
)
DEMO_QUESTION = (
    "Does the learner show the same improvement when explaining an unfamiliar fraction problem?"
)


class _JudgeDemoModel:
    """Deterministic model that drives a short, inspectable MCP sequence."""

    def __init__(self) -> None:
        self.step = 0
        self.visible_tools: list[set[str]] = []

    async def __call__(
        self,
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        del messages
        self.visible_tools.append({tool.name for tool in info.function_tools})

        if self.step == 0:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "get_competency_evidence",
                        {
                            "learner_id": "L001",
                            "competency_code": "MATH-FRACTIONS",
                        },
                    )
                ]
            )

        if self.step == 1:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "read_text_file",
                        {"path": str(REFERENCE_FILE.resolve())},
                    )
                ]
            )

        if self.step == 2:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "flag_pattern_for_review",
                        {
                            "learner_id": "L001",
                            "competency_code": "MATH-FRACTIONS",
                            "claim": DEMO_CLAIM,
                            "supporting_evidence_ids": [
                                "EV-004",
                                "EV-007",
                                "EV-009",
                                "EV-011",
                            ],
                            "counter_evidence_ids": ["EV-008"],
                            "uncertainty": DEMO_UNCERTAINTY,
                            "suggested_teacher_question": DEMO_QUESTION,
                        },
                    )
                ]
            )

        return ModelResponse(
            parts=[TextPart("Candidate prepared for human teacher review.")]
        )


async def run_demo(
    *,
    state_path: Path = DEFAULT_DEMO_STATE_PATH,
    report_path: Path = DEFAULT_DEMO_REPORT_PATH,
    html_path: Path = DEFAULT_DEMO_HTML_PATH,
    stderr_path: Path = DEFAULT_DEMO_STDERR_PATH,
) -> dict[str, Any]:
    """Run the fast MCP demo and write its JSON and HTML artefacts."""

    os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
    state_path = state_path.resolve()
    report_path = report_path.resolve()
    html_path = html_path.resolve()
    stderr_path = stderr_path.resolve()

    for path in (state_path, report_path, html_path, stderr_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    stderr_path.unlink(missing_ok=True)

    scripted = _JudgeDemoModel()
    error: dict[str, str] | None = None
    final_output = ""
    try:
        borrowed = build_borrowed_filesystem_toolset(
            state_path=state_path,
            stderr_path=stderr_path,
        )
        agent = build_agent(
            FunctionModel(scripted),
            data_dir=DEFAULT_DATA_DIR,
            state_path=state_path,
            additional_toolsets=[borrowed],
        )
        result = await agent.run(
            "Show the longitudinal fraction pattern and prepare it for teacher review."
        )
        final_output = str(result.output)
    except Exception as exc:
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    report = build_demo_report(
        state_path=state_path,
        visible_tools=scripted.visible_tools,
        final_output=final_output,
        error=error,
    )

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    html_path.write_text(render_demo_html(report), encoding="utf-8")
    return report


def build_demo_report(
    *,
    state_path: Path,
    visible_tools: list[set[str]],
    final_output: str,
    error: dict[str, str] | None,
) -> dict[str, Any]:
    """Build one compact demo payload from audited state and committed evidence."""

    dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
    learner = dataset.learner("L001")
    evidence = dataset.competency_evidence("L001", "MATH-FRACTIONS")
    state = JsonStateStore(state_path)
    calls = list(state.tool_calls())
    pending = list(state.pending_reviews())
    teacher_reviews = list(state.teacher_reviews())
    profile_updates = list(state.profile_updates())

    candidate = pending[0] if len(pending) == 1 else None
    support_ids = set(candidate.get("supporting_evidence_ids", [])) if candidate else set()
    counter_ids = set(candidate.get("counter_evidence_ids", [])) if candidate else set()

    combined_visible = sorted(set().union(*visible_tools)) if visible_tools else []
    expected_visible = AGENT_MCP_TOOL_ALLOWLIST.union(
        BORROWED_FILESYSTEM_TOOL_ALLOWLIST
    )
    successful_tools = {
        call.get("tool_name")
        for call in calls
        if call.get("status") == "success"
    }

    qwen = _read_json(OPEN_WEIGHTS_EVIDENCE)
    challenge = _read_json(CHALLENGE_EVIDENCE)
    evals = _read_json(EVAL_EVIDENCE)

    checks = {
        "education_evidence_retrieved": "get_competency_evidence" in successful_tools,
        "borrowed_reference_read": any(
            call.get("tool_name") == "read_text_file"
            and call.get("source") == "borrowed_mcp"
            and call.get("status") == "success"
            for call in calls
        ),
        "candidate_created": "flag_pattern_for_review" in successful_tools
        and candidate is not None,
        "human_gate_untouched": len(teacher_reviews) == 0
        and len(profile_updates) == 0,
        "model_tool_surface_safe": set(combined_visible) == expected_visible
        and "record_teacher_review" not in combined_visible,
        "real_qwen_evidence_passed": qwen.get("status") == "pass"
        and qwen.get("model") == "qwen2.5:3b",
        "challenge_evidence_passed": challenge.get("status") == "pass",
        "evaluation_evidence_passed": evals.get("status") == "pass",
        "final_output_present": bool(final_output.strip()),
    }

    rows = []
    for item in evidence:
        role = "supporting" if item.evidence_id in support_ids else "neutral"
        if item.evidence_id in counter_ids:
            role = "counter"
        rows.append(
            {
                "evidence_id": item.evidence_id,
                "term_id": item.term_id,
                "type": item.evidence_type.value,
                "score": item.score,
                "observation": item.observation,
                "occurred_at": item.occurred_at.isoformat(),
                "role": role,
            }
        )

    return {
        "status": "pass" if error is None and all(checks.values()) else "fail",
        "mode": "fast_deterministic_demo",
        "learner": {
            "learner_id": learner.learner_id,
            "display_name": learner.display_name,
            "year_group": learner.year_group,
            "synthetic": learner.synthetic,
        },
        "competency_code": "MATH-FRACTIONS",
        "evidence": rows,
        "candidate": candidate,
        "tool_calls": calls,
        "visible_tools": combined_visible,
        "pending_review_count": len(pending),
        "teacher_review_count": len(teacher_reviews),
        "profile_update_count": len(profile_updates),
        "final_output": final_output,
        "checks": checks,
        "real_qwen_validation": {
            "status": qwen.get("status"),
            "model": qwen.get("model"),
            "audited_tool_names": qwen.get("audited_tool_names", []),
        },
        "challenge_validation": {
            "status": challenge.get("status"),
            "model": challenge.get("model"),
        },
        "evaluation_validation": {
            "status": evals.get("status"),
            "summary": evals.get("summary"),
        },
        "limitation": (
            "This demo uses synthetic learner data and a deterministic model for recording speed. "
            "The separate committed Qwen2.5 3B evidence validates the open-weights path."
        ),
        "error": error,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return payload


def print_demo_summary(report: dict[str, Any], html_path: Path) -> None:
    """Print the short recording-oriented summary."""

    print("MwalimuLens judge demo")
    print(f"  Education evidence retrieval: {_check(report, 'education_evidence_retrieved')}")
    print(f"  Borrowed reference read: {_check(report, 'borrowed_reference_read')}")
    print(f"  Candidate pending review: {_check(report, 'candidate_created')}")
    print(f"  Human gate untouched: {_check(report, 'human_gate_untouched')}")
    print(f"  Real Qwen validation: {_check(report, 'real_qwen_evidence_passed')}")
    print(f"DEMO RUN: {report['status'].upper()}")
    print(f"Open: {html_path.resolve()}")


def _check(report: dict[str, Any], name: str) -> str:
    return "PASS" if report.get("checks", {}).get(name) else "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the fast judge-facing MwalimuLens demo.")
    parser.add_argument("--report", type=Path, default=DEFAULT_DEMO_REPORT_PATH)
    parser.add_argument("--html", type=Path, default=DEFAULT_DEMO_HTML_PATH)
    parser.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Open the generated self-contained HTML page in the default browser.",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_demo(
            report_path=args.report,
            html_path=args.html,
        )
    )
    print_demo_summary(report, args.html)
    if args.open and report["status"] == "pass":
        webbrowser.open(args.html.resolve().as_uri())
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
