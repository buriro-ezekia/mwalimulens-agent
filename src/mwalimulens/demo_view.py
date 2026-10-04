"""Self-contained HTML rendering for the judge-facing demo."""

from __future__ import annotations

from html import escape
from typing import Any


def render_demo_html(report: dict[str, Any]) -> str:
    """Render a self-contained browser page from a demo report."""

    learner = report["learner"]
    candidate = report.get("candidate") or {}
    evidence_rows = "".join(_render_evidence_row(row) for row in report["evidence"])
    tool_rows = "".join(_render_tool_row(call) for call in report["tool_calls"])
    eval_summary = report["evaluation_validation"].get("summary") or {}
    qwen = report["real_qwen_validation"]

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
section {{ scroll-margin-top: 80px; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 28px 24px 48px; }}
nav {{
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 12px 0;
  background: #f4f7fb;
}}
nav a {{ color: #14213d; padding: 8px 10px; border-radius: 8px; font-size: 14px; }}
nav a:hover, nav a:focus-visible {{ background: #dce5f5; }}
code {{ overflow-wrap: anywhere; }}
.hero {{
  background: #14213d;
  color: white;
  border-radius: 22px;
  padding: 28px;
  box-shadow: 0 18px 50px rgba(20, 33, 61, .16);
}}
.eyebrow {{
  text-transform: uppercase;
  letter-spacing: .12em;
  font-size: 12px;
  opacity: .72;
}}
h1 {{ margin: 8px 0 10px; font-size: 38px; }}
.hero p {{ max-width: 780px; margin: 0; line-height: 1.55; color: #dce5f5; }}
.hero .mode-note {{ margin-top: 16px; font-size: 14px; }}
.badges {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 20px; }}
.badge {{
  display: inline-flex;
  border-radius: 999px;
  padding: 7px 11px;
  background: rgba(255, 255, 255, .1);
  font-size: 13px;
}}
.grid {{
  display: grid;
  gap: 18px;
  grid-template-columns: 1.35fr .9fr;
  margin-top: 18px;
}}
.card {{
  min-width: 0;
  background: white;
  border: 1px solid #e3e8f0;
  border-radius: 18px;
  padding: 20px;
  box-shadow: 0 8px 28px rgba(33, 46, 71, .06);
}}
.card h2 {{ margin: 0 0 6px; font-size: 19px; }}
.muted {{ color: #68758a; font-size: 14px; line-height: 1.5; }}
.kpis {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-top: 18px;
}}
.kpi {{ background: #f6f8fc; border-radius: 14px; padding: 12px; }}
.kpi strong {{ display: block; font-size: 22px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
th, td {{
  padding: 10px 8px;
  border-bottom: 1px solid #edf0f5;
  text-align: left;
  vertical-align: top;
}}
th {{
  color: #68758a;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .05em;
}}
.role {{ font-weight: 650; }}
.role-supporting {{ color: #18794e; }}
.role-counter {{ color: #a4422c; }}
.role-neutral {{ color: #68758a; }}
.tool {{ display: flex; gap: 10px; align-items: flex-start; margin: 11px 0; }}
.tool strong {{ overflow-wrap: anywhere; }}
.dot {{
  flex-shrink: 0;
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 50%;
  background: #2c7a7b;
}}
.candidate {{ border-left: 4px solid #d9a441; }}
.gate {{ border-left: 4px solid #18794e; }}
.limit {{ border-left: 4px solid #7a5af8; }}
.validation {{
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}}
.validation > div {{ background: #f6f8fc; border-radius: 14px; padding: 14px; }}
#validation {{ grid-column: 1 / -1; }}
.pass {{ color: #18794e; font-weight: 700; }}
.fail {{ color: #a4422c; font-weight: 700; }}
.table-scroll {{ overflow-x: auto; }}
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
  <div class="eyebrow">
    African Agentic AI Design Challenge · Education — The Long View
  </div>
  <h1>MwalimuLens</h1>
  <p>
    Longitudinal learner evidence, grounded in cited records. The agent surfaces a cautious
    pattern; the teacher decides what it means.
  </p>
  <div class="badges">
    <span class="badge">Deterministic fast demo · live MCP</span>
    <span class="badge">Human review required</span>
    <span class="badge">Synthetic learner data</span>
  </div>
  <p class="mode-note">
    This deterministic sequence makes real MCP calls. Open-weights validation is a separate
    committed run; no Qwen inference runs in this demo.
  </p>
</section>

<nav aria-label="Demo sections">
  <a href="#evidence">Evidence</a>
  <a href="#activity">MCP activity</a>
  <a href="#candidate">Candidate</a>
  <a href="#gate">Human gate</a>
  <a href="#validation">Separate validation</a>
  <a href="#limitation">Limitation</a>
</nav>

<section class="kpis">
  <div class="kpi">
    <span class="muted">Learner</span>
    <strong>{escape(learner["display_name"])}</strong>
  </div>
  <div class="kpi">
    <span class="muted">Evidence items</span>
    <strong>{len(report["evidence"])}</strong>
  </div>
  <div class="kpi">
    <span class="muted">Audited tool calls</span>
    <strong>{len(report["tool_calls"])}</strong>
  </div>
  <div class="kpi">
    <span class="muted">Profile updates</span>
    <strong>{report["profile_update_count"]}</strong>
  </div>
</section>

<div class="grid">
<section class="card" id="evidence">
  <h2>Evidence timeline · MATH-FRACTIONS</h2>
  <p class="muted">
    The agent sees the evidence in event chronology, including counter-evidence.
  </p>
  <div class="table-scroll">
  <table>
    <thead>
      <tr><th>Term</th><th>Evidence</th><th>Type</th><th>Value</th><th>Role</th></tr>
    </thead>
    <tbody>{evidence_rows}</tbody>
  </table>
  </div>
</section>

<section class="card" id="activity">
  <h2>Visible MCP activity</h2>
  <p class="muted">
    These calls were made in this fast demo. The human review action is not model-visible.
  </p>
  {tool_rows}
  <p class="muted">
    The borrowed read-only Filesystem MCP reads a teaching reference, not learner evidence.
  </p>
</section>

<section class="card candidate" id="candidate">
  <h2>Candidate pattern</h2>
  <p class="muted">
    <strong>Status:</strong> <code>{escape(str(candidate.get("status", "No candidate")))}</code>
  </p>
  <p><strong>{escape(str(candidate.get("claim", "No candidate created")))}</strong></p>
  <p class="muted">{escape(str(candidate.get("uncertainty", "")))}</p>
  <p class="muted">
    <strong>Teacher question:</strong>
    {escape(str(candidate.get("suggested_teacher_question", "")))}
  </p>
</section>

<section class="card gate" id="gate">
  <h2>Human decision gate</h2>
  <p class="muted">
    The agent stops here. Approve, edit and reject remain separate teacher actions.
    <code>record_teacher_review</code> is not model-visible.
  </p>
  <div class="validation">
    <div>
      <span class="muted">Pending candidates</span><br>
      <strong>{report["pending_review_count"]}</strong>
    </div>
    <div>
      <span class="muted">Teacher decisions</span><br>
      <strong>{report["teacher_review_count"]}</strong>
    </div>
    <div>
      <span class="muted">Profile updates</span><br>
      <strong>{report["profile_update_count"]}</strong>
    </div>
  </div>
</section>

<section class="card" id="validation">
  <h2>Separate committed validation</h2>
  <p class="muted">
    These results come from committed evidence files, not the deterministic live demo above.
  </p>
  <div class="validation">
    <div>
      <span class="muted">Real Qwen run</span><br>
      {_render_status(qwen["status"])}<br>
      <small>{escape(str(qwen.get("model", "Unknown model")))}</small><br>
      <code>evidence/open_weights_run.json</code>
    </div>
    <div>
      <span class="muted">One-command run</span><br>
      {_render_status(report["challenge_validation"]["status"])}<br>
      <code>evidence/challenge_run.json</code>
    </div>
    <div>
      <span class="muted">Committed evals</span><br>
      <span class="pass">{eval_summary.get("current_pass", 0)} PASS</span><br>
      <small>
        {eval_summary.get("historical_fail_preserved", 0)} historical failures preserved
      </small>
      <br><code>evidence/evals_run.json</code>
    </div>
  </div>
</section>

<section class="card limit" id="limitation">
  <h2>What this demo does not claim</h2>
  <p class="muted">{escape(report["limitation"])}</p>
  <p class="muted">This synthetic prototype has not been validated in real classrooms.</p>
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
    if call.get("source") == "borrowed_mcp":
        source = "Borrowed read-only Filesystem MCP"
    else:
        source = "Custom Education MCP"

    return (
        '<div class="tool"><span class="dot"></span><div>'
        f"<strong>{escape(str(call.get('tool_name')))}</strong><br>"
        f"<span class=\"muted\">{escape(source)} · "
        f"{escape(str(call.get('status', '')).upper())}</span>"
        "</div></div>"
    )


def _render_status(status: Any) -> str:
    result = str(status).upper()
    css_class = "pass" if result == "PASS" else "fail"
    return f'<span class="{css_class}">{escape(result)}</span>'
