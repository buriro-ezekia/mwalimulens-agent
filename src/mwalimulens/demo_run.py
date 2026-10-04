"""Fast judge-facing demo using the real MCP boundaries."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import webbrowser
from html import escape
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

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.unlink(missing_ok=True)
    stderr_path.unlink(missing_ok=True)

    scripted = _JudgeDemoModel()
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

    error: dict[str, str] | None = None
    final_output = ""
    try:
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
    tool_names = [call.get("tool_name") for call in calls]

    qwen = _read_json(OPEN_WEIGHTS_EVIDENCE)
    challenge = _read_json(CHALLENGE_EVIDENCE)
    evals = _read_json(EVAL_EVIDENCE)

    checks = {
        "education_evidence_retrieved": "get_competency_evidence" in tool_names,
        "borrowed_reference_read": any(
            call.get("tool_name") == "read_text_file"
            and call.get("source") == "borrowed_mcp"
            and call.get("status") == "success"
            for call in calls
        ),
        "candidate_created": "flag_pattern_for_review" in tool_names
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


def render_demo_html(report: dict[str, Any]) -> str:
    """Render a self-contained browser page from a demo report."""

    learner = report["learner"]
    candidate = report.get("candidate") or {}
    evidence_rows = "".join(_render_evidence_row(row) for row in report["evidence"])
    tool_rows = "".join(_render_tool_row(call) for call in report["tool_calls"])
    eval_summary = report["evaluation_validation"].get("summary") or {}

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MwalimuLens judge demo</title>
<style>
:root {{
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI";
  color: #172033;
  background: #f4f7fb;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 28px 24px 48px; }}
.hero {{
  background: #14213d;
  color: white;
  border-radius: 22px;
  padding: 28px;
  box-shadow: 0 18px 50px rgba(20, 33, 61, .16);
}}
.eyebrow {{ text-transform: uppercase; letter-spacing: .12em; font-size: 12px; opacity: .72; }}
h1 {{ margin: 8px 0 10px; font-size: 38px; }}
.hero p {{ max-width: 780px; margin: 0; line-height: 1.55; color: #dce5f5; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }}
.badge {{
  display: inline-flex;
  border-radius: 999px;
  padding: 7px 11px;
  background: rgba(255, 255, 255, .1);
  font-size: 13px;
}}
.grid {{ display: grid; gap: 18px; grid-template-columns: 1.35fr .9fr; margin-top: 18px; }}
.card {{
  background: white;
  border: 1px solid #e3e8f0;
  border-radius: 18px;
  padding: 20px;
  box-shadow: 0 8px 28px rgba(33, 46, 71, .06);
}}
.card h2 {{ margin: 0 0 6px; font-size: 19px; }}
.muted {{ color: #68758a; font-size: 14px; line-height: 1.5; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 18px; }}
.kpi {{ background: #f6f8fc; border-radius: 14px; padding: 12px; }}
.kpi strong {{ display: block; font-size: 22px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
th, td {{ padding: 10px 8px; border-bottom: 1px solid #edf0f5; text-align: left; vertical-align: top; }}
th {{ color: #68758a; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; }}
.role {{ font-weight: 650; }}
.role-supporting {{ color: #18794e; }}
.role-counter {{ color: #a4422c; }}
.role-neutral {{ color: #68758a; }}
.tool {{ display: flex; gap: 10px; align-items: flex-start; margin: 11px 0; }}
.dot {{ width: 10px; height: 10px; margin-top: 6px; border-radius: 50%; background: #2c7a7b; }}
.candidate {{ border-left: 4px solid #d9a441; }}
.gate {{ border-left: 4px solid #18794e; }}
.limit {{ border-left: 4px solid #7a5af8; }}
.validation {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
.validation > div {{ background: #f6f8fc; border-radius: 14px; padding: 14px; }}
.pass {{ color: #18794e; font-weight: 700; }}
footer {{ margin-top: 20px; color: #68758a; font-size: 13px; }}
@media (max-width: 860px) {{
  .grid, .kpis, .validation {{ grid-template-columns: 1fr; }}
  h1 {{ font-size: 30px; }}
}}
</style>
</head>
<body>
<main>
<section class="hero">
  <div class="eyebrow">African Agentic AI Design Challenge · Education — The Long View</div>
  <h1>MwalimuLens</h1>
  <p>
    Longitudinal learner evidence, grounded in cited records. The agent surfaces a cautious
    pattern; the teacher decides what it means.
  </p>
  <div class="badges">
    <span class="badge">Fast live MCP demo</span>
    <span class="badge">Real Qwen2.5 3B validation: PASS</span>
    <span class="badge">Human review required</span>
    <span class="badge">Synthetic learner data</span>
  </div>
</section>

<section class="kpis">
  <div class="kpi"><span class="muted">Learner</span><strong>{escape(learner["display_name"])}</strong></div>
  <div class="kpi"><span class="muted">Evidence items</span><strong>{len(report["evidence"])}</strong></div>
  <div class="kpi"><span class="muted">Audited tool calls</span><strong>{len(report["tool_calls"])}</strong></div>
  <div class="kpi"><span class="muted">Profile updates</span><strong>{report["profile_update_count"]}</strong></div>
</section>

<div class="grid">
<section class="card">
  <h2>Evidence timeline · MATH-FRACTIONS</h2>
  <p class="muted">The agent sees the evidence in event chronology, including counter-evidence.</p>
  <table>
    <thead><tr><th>Term</th><th>Evidence</th><th>Type</th><th>Value</th><th>Role</th></tr></thead>
    <tbody>{evidence_rows}</tbody>
  </table>
</section>

<section class="card">
  <h2>Visible MCP activity</h2>
  <p class="muted">
    These calls were made in this fast demo. The human review action is not model-visible.
  </p>
  {tool_rows}
</section>

<section class="card candidate">
  <h2>Candidate pattern — pending review</h2>
  <p><strong>{escape(str(candidate.get("claim", "No candidate created")))}</strong></p>
  <p class="muted">{escape(str(candidate.get("uncertainty", "")))}</p>
  <p class="muted"><strong>Teacher question:</strong> {escape(str(candidate.get("suggested_teacher_question", "")))}</p>
</section>

<section class="card gate">
  <h2>Human decision gate</h2>
  <p class="muted">
    The agent stops here. Approve, edit and reject remain separate teacher actions.
  </p>
  <div class="validation">
    <div><span class="muted">Pending candidates</span><br><strong>1</strong></div>
    <div><span class="muted">Teacher decisions</span><br><strong>{report["teacher_review_count"]}</strong></div>
    <div><span class="muted">Profile updates</span><br><strong>{report["profile_update_count"]}</strong></div>
  </div>
</section>

<section class="card">
  <h2>Independent validation</h2>
  <div class="validation">
    <div><span class="muted">Real Qwen run</span><br><span class="pass">{escape(str(report["real_qwen_validation"]["status"]).upper())}</span><br><small>qwen2.5:3b</small></div>
    <div><span class="muted">One-command run</span><br><span class="pass">{escape(str(report["challenge_validation"]["status"]).upper())}</span></div>
    <div><span class="muted">Current evals</span><br><span class="pass">{eval_summary.get("current_pass", 0)} PASS</span><br><small>{eval_summary.get("historical_fail_preserved", 0)} historical failures preserved</small></div>
  </div>
</section>

<section class="card limit">
  <h2>What this demo does not claim</h2>
  <p class="muted">{escape(report["limitation"])}</p>
  <p class="muted">
    MwalimuLens does not rank learners, assign pathways or turn one score into a permanent label.
  </p>
</section>
</div>

<footer>
  Status: <strong>{escape(report["status"].upper())}</strong> ·
  The detailed JSON report is saved beside this page in the runtime directory.
</footer>
</main>
</body>
</html>
"""


def _render_evidence_row(row: dict[str, Any]) -> str:
    value = (
        f"{float(row['score']) * 100:.0f}%"
        if row.get("score") is not None
        else escape(str(row.get("observation") or "—"))
    )
    role = escape(str(row["role"]))
    return (
        "<tr>"
        f"<td>{escape(str(row['term_id']))}</td>"
        f"<td>{escape(str(row['evidence_id']))}</td>"
        f"<td>{escape(str(row['type']))}</td>"
        f"<td>{value}</td>"
        f"<td class=\"role role-{role}\">{role}</td>"
        "</tr>"
    )


def _render_tool_row(call: dict[str, Any]) -> str:
    source = "Borrowed Filesystem MCP" if call.get("source") == "borrowed_mcp" else "Education MCP"
    return (
        '<div class="tool"><span class="dot"></span><div>'
        f"<strong>{escape(str(call.get('tool_name')))}</strong><br>"
        f"<span class=\"muted\">{escape(source)} · "
        f"{escape(str(call.get('status', '')).upper())}</span>"
        "</div></div>"
    )


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
