"""Local teacher-facing review of fictional learner evidence (not authenticated)."""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import secrets
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "runtime" / "teacher_portal"
REVIEWER = "simulated-teacher-not-authenticated"
MAX_POST_BYTES = 8192
CONFIRM_TTL = 600


def h(value: Any) -> str:
    return escape(str(value) if value is not None else "—", quote=True)


@dataclass
class Case:
    state: Any
    service: Any
    candidate: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    run_dir: Path
    mode: str
    report: dict[str, Any] | None = None
    analysis_status: str = "candidate"
    stage: str = "complete"
    abstention_reason: str = ""
    analysis_error: str = ""
    request_count: int = 0
    worker_active: bool = False
    opened_as: str = "New case in this session"


def create_case(root: Path, mode: str = "seeded") -> Case:
    """Start an isolated case; MCP mode runs genuine MCP calls, not live Qwen."""
    if mode not in {"seeded", "mcp"}:
        raise ValueError("Unknown analysis mode")
    from mwalimulens.domain import load_synthetic_dataset
    from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
    from mwalimulens.mcp_server.service import EducationToolService
    from mwalimulens.mcp_server.state import JsonStateStore

    dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
    if not dataset.learners or any(not x.synthetic for x in dataset.learners):
        raise ValueError("Only fictional learner data is permitted")
    root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="case-", dir=root))
    state = JsonStateStore(run_dir / "state.json")
    service = EducationToolService(dataset, state)
    report = None
    if mode == "mcp":
        from mwalimulens.demo_run import run_demo
        report = asyncio.run(run_demo(
            state_path=state.path, report_path=run_dir / "demo_run.json",
            html_path=run_dir / "mcp_trace.html",
            stderr_path=run_dir / "borrowed_stderr.log",
        ))
        if report.get("status") != "pass" or len(state.pending_reviews()) != 1:
            raise RuntimeError("MCP analysis failed; inspect the isolated run report")
        candidate = state.pending_reviews()[0]
    else:
        from mwalimulens.teacher_review_demo import CANDIDATE
        candidate = service.flag_pattern_for_review(**CANDIDATE)
    evidence = service.get_competency_evidence("L001", "MATH-FRACTIONS")["evidence"]
    return Case(state, service, candidate, evidence, run_dir, mode, report)


def _evidence_type(value: Any) -> str:
    """Use readable labels without changing the underlying evidence type."""
    labels = {"assessment": "Assessment", "practical_task": "Practical task",
              "observation": "Observation", "attendance": "Attendance"}
    return labels.get(str(value), str(value).replace("_", " ").capitalize())

def _brand() -> str:
    return (
        '<a class="brand" href="/" aria-label="MwalimuLens learner review">'
        '<span class="brand-mark" aria-hidden="true">ML</span>'
        '<span class="brand-name">MwalimuLens<span>Teacher workspace</span></span></a>'
    )

def _evidence_links(identifiers: list[str], *, counter: bool = False) -> str:
    style = " counter" if counter else ""
    return "".join(
        f'<a class="evidence-link{style}" href="#evidence-{h(ident)}">{h(ident)}</a>'
        for ident in identifiers
    ) or '<span class="hint">None recorded</span>'

def _evidence(case: Case) -> str:
    candidate = case.candidate or {}
    supporting = set(candidate.get("supporting_evidence_ids", []))
    opposing = set(candidate.get("counter_evidence_ids", []))
    rows = []
    for item in case.evidence:
        ident = item["evidence_id"]
        role = "Counter-evidence" if ident in opposing else (
            "Supporting" if ident in supporting else "Context"
        )
        cls = "counter" if ident in opposing else "support" if ident in supporting else ""
        score = item.get("score")
        score_text = f"{score * 100:.0f}%" if isinstance(score, (float, int)) else "—"
        rows.append(
            f'<tr id="evidence-{h(ident)}" class="{cls}">'
            f'<th scope="row" data-label="Record"><code>{h(ident)}</code></th>'
            f'<td data-label="Term">{h(item["term_id"])}</td>'
            f'<td data-label="Type">{h(_evidence_type(item["evidence_type"]))}</td>'
            f'<td data-label="Score" class="score">{h(score_text)}</td>'
            f'<td data-label="Observation" class="observation">'
            f'{h(item.get("observation") or "No observation recorded.")}</td>'
            f'<td data-label="Role"><span class="tag {cls}">{role}</span></td></tr>'
        )
    return "".join(rows)


def _trend(case: Case) -> str:
    bars = []
    for item in case.evidence:
        score = item.get("score")
        if isinstance(score, (float, int)):
            practical = item["evidence_type"] == "practical_task"
            cls = " practical" if practical else ""
            bars.append(
                '<div class="trend">'
                f'<div class="trend-label"><span>{h(item["term_id"])}</span>'
                f'<small>{h(_evidence_type(item["evidence_type"]))} · '
                f'{h(item["evidence_id"])}</small></div>'
                f'<div class="track{cls}" aria-hidden="true">'
                f'<div style="width:{score * 100:.1f}%"></div></div>'
                f'<strong>{score * 100:.0f}%</strong></div>'
            )
    return "".join(bars) or '<p class="hint">No scored tasks are recorded for this case.</p>'


def _audit(case: Case) -> str:
    return "".join(
        f'<tr><td><code>{h(e.get("tool_name"))}</code></td>'
        f'<td>{h(e.get("status"))}</td><td>{h(e.get("timestamp"))}</td></tr>'
        for e in case.state.tool_calls()
    )


def _model_validation() -> str:
    """Show separately committed model evidence without claiming live inference."""
    path = ROOT / "evidence" / "open_weights_run.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Expected a JSON report")
        model = report.get("model", "unknown")
        status = report.get("status", "unknown")
        tool_names = report.get("audited_tool_names") or []
        if not isinstance(tool_names, list):
            tool_names = []
        return (
            f'<p><b>Committed model:</b> {h(model)} · <b>Recorded status:</b> '
            f'{h(status)} · <b>Audited tool names:</b> {len(tool_names)}</p>'
            '<p class="hint">This is previously committed Qwen validation evidence, '
            'not a live model run in this browser session.</p>'
        )
    except (OSError, ValueError):
        return '<p class="hint">Separate Qwen validation evidence is unavailable locally.</p>'


def _review_form(case: Case, token: str) -> str:
    if case.candidate is None or case.analysis_status != "candidate":
        return '<p class="hint">There is no completed candidate to review.</p>'
    if not case.state.pending_reviews():
        review = case.state.teacher_reviews()[-1]
        decision = {"approve": "Approved", "edit": "Revised", "reject": "Rejected"}.get(
            review["decision"], str(review["decision"]).title(),
        )
        return (
            '<div class="result" role="status"><span class="result-label">Review recorded</span>'
            f'<h3>{h(decision)} by simulated teacher</h3>'
            '<dl class="review-details">'
            f'<dt>Reason</dt><dd>{h(review["reason"])}</dd>'
            f'<dt>Final wording</dt><dd>{h(review.get("final_claim"))}</dd>'
            f'<dt>Synthetic profile notes</dt><dd>{len(case.state.profile_updates())}</dd>'
            '</dl></div><p class="hint">Start a new practice case to review another example.</p>'
        )
    return f'''<form class="decision-form" method="post" action="/review/preview">
<input type="hidden" name="csrf" value="{h(token)}">
<fieldset><legend>Choose a decision</legend><div class="choices">
<label><input type="radio" name="decision" value="approve" required>
<span><b>Approve</b><small>Retain the finding.</small></span></label>
<label><input type="radio" name="decision" value="edit">
<span><b>Revise</b><small>Adjust the wording.</small></span></label>
<label><input type="radio" name="decision" value="reject">
<span><b>Reject</b><small>Do not add a note.</small></span></label>
</div></fieldset>
<div class="form-field"><label for="reason">Reason for your decision <span>*</span></label>
<p id="reason-help" class="field-help">Refer to the evidence and any remaining uncertainty.</p>
<textarea id="reason" name="reason" required maxlength="1200" rows="4"
aria-describedby="reason-help" placeholder="Explain the evidence behind your decision."></textarea>
</div>
<div class="form-field revision-field"><label for="edited">Revised wording <span>*</span></label>
<p id="edited-help" class="field-help">Required when revising. Keep the finding provisional.</p>
<textarea id="edited" name="edited_claim" maxlength="1200" rows="4"
aria-describedby="edited-help" placeholder="Write the wording you want to retain."></textarea></div>
<div class="decision-next"><span class="step-dot" aria-hidden="true">2</span>
<p>Check your decision on the next page.<br><strong>Nothing is saved until you confirm.</strong></p>
</div><button class="button primary full-width" type="submit">Review decision
<span aria-hidden="true">→</span></button>
<p class="form-disclosure">Reviewer identity is simulated, not authenticated.</p></form>'''

CSS = """
:root{font-family:system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
font-size:15px;color:#203449;background:#f3f6f8;line-height:1.55;
--ink:#183049;--muted:#586b7d;--line:#dce4ea;--teal:#087b72;--navy:#182f4c}
*{box-sizing:border-box}body{margin:0}button,input,textarea{font:inherit}
a{color:var(--teal);text-underline-offset:3px}p{margin:0 0 12px}
h1,h2,h3{color:var(--ink);line-height:1.25;margin:0}h1{font-size:30px;
font-weight:720;letter-spacing:-.8px}h2{font-size:19px;font-weight:700}
h3{font-size:16px}code{font-family:ui-monospace,Consolas,monospace;font-size:.88em}
button,a,input,textarea,summary{touch-action:manipulation}
:focus-visible{outline:3px solid #087b72;outline-offset:4px}
main{max-width:1424px;margin:auto;padding:0 36px 48px}
.skip-link{position:absolute;left:16px;top:-70px;z-index:10;background:white;padding:12px}
.skip-link:focus{top:10px}.sr-only{position:absolute;width:1px;height:1px;padding:0;
margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:24px;
min-height:92px;border-bottom:1px solid var(--line);margin-bottom:28px}
.brand{display:inline-flex;align-items:center;gap:12px;text-decoration:none;color:var(--ink)}
.brand-mark{width:44px;height:44px;display:grid;place-items:center;background:var(--navy);
color:white;border-radius:12px;font-weight:750;font-size:16px;letter-spacing:-1px}
.brand-name{font-size:19px;font-weight:750;letter-spacing:-.4px;line-height:1.2}
.brand-name span{display:block;font-size:11px;letter-spacing:1px;text-transform:uppercase;
font-weight:550;color:var(--muted);margin-top:5px}
.toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.toolbar form{margin:0}
.case-identity{margin:0 0 20px;overflow-wrap:anywhere;font-size:13px}
.case-identity .hint{margin:6px 0}
.button,button{display:inline-flex;align-items:center;justify-content:center;gap:12px;
min-height:44px;padding:10px 16px;border:1px solid #b9c8d4;border-radius:9px;
background:white;color:var(--ink);font-weight:650;line-height:1.4;cursor:pointer;
text-decoration:none;font-size:13px}button:hover,.button:hover{background:#edf3f5}
button.primary,.button.primary{background:var(--teal);border-color:var(--teal);color:white}
button.primary:hover{background:#05665e}.full-width{width:100%;justify-content:space-between}
button:disabled{opacity:.55;cursor:wait}
.page-heading{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}
.eyebrow{color:var(--teal);font-size:11px;letter-spacing:1.5px;text-transform:uppercase;
font-weight:750;margin-bottom:8px}.page-heading p{color:var(--muted);margin-top:10px;
max-width:680px;font-size:14px}.step-nav{display:flex;gap:6px;margin-top:9px;flex-shrink:0}
.step-nav a{display:inline-flex;align-items:center;gap:7px;min-height:40px;padding:8px 10px;
font-size:12px;color:#42596d;text-decoration:none;border-radius:8px;font-weight:600}
.step-nav a:hover{background:#e7eff1}.step-nav span{display:grid;place-items:center;
width:22px;height:22px;background:#e3eced;border-radius:50%;color:#1a625e;font-size:11px}
.demo-notice{display:flex;align-items:center;gap:12px;background:#eef3f5;
border:1px solid #dce5e9;border-radius:9px;padding:10px 14px;margin:10px 0 20px;
color:#506378;font-size:12px}.notice-label{font-weight:700;color:#324c63;white-space:nowrap}
.demo-notice p{margin:0;line-height:1.5}.mode-line{display:block;font-size:11px;color:#5a6d7d;
margin-top:2px}.notice-icon{display:grid;place-items:center;width:23px;height:23px;
border:1px solid #9eafbc;border-radius:50%;font-weight:750;font-size:12px;flex-shrink:0}
.flash,.error{padding:14px 16px;margin:16px 0;border-radius:9px;overflow-wrap:anywhere}
.flash{background:#e8f5ef;border:1px solid #aed8c6;color:#205b45}
.error{background:#fff0eb;border:1px solid #e7b5a8;color:#8b3024}
.case-strip{display:flex;align-items:center;justify-content:space-between;gap:24px;
padding:19px 22px;background:var(--navy);color:white;border-radius:13px;margin-bottom:22px}
.learner{display:flex;gap:13px;align-items:center;min-width:0}.avatar{width:44px;height:44px;
display:grid;place-items:center;border-radius:50%;background:#304b65;color:#dfebf1;
font-size:19px;font-weight:650;flex-shrink:0}.learner h2{color:white;font-size:18px}
.learner h2 span{font-weight:450;font-size:12px;color:#c4d2df;margin-left:5px}
.learner p{font-size:12px;color:#d4e0e9;margin:3px 0 0}.metrics{display:flex;gap:28px}
.metric{min-width:92px;padding-left:24px;border-left:1px solid #405671}
.metric strong{display:block;font-size:25px;font-weight:700;line-height:1.15}
.metric span{display:block;font-size:11px;color:#d4e0e9;margin-top:5px}
.workspace-grid{display:grid;grid-template-columns:minmax(0,1fr) 370px;gap:22px;align-items:start}
.analysis-column{display:grid;gap:20px;min-width:0}
.card{background:white;border:1px solid var(--line);
border-radius:12px;padding:24px;min-width:0;box-shadow:0 3px 10px #162a3b03}
.card:target{outline:2px solid #15857c;outline-offset:4px}
.section-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;
margin-bottom:18px}.section-heading h2{display:flex;align-items:center;gap:10px}
.section-number{font-size:10px;color:#52796f;border:1px solid #c7dbd5;background:#eff6f3;
width:26px;height:26px;display:inline-grid;place-items:center;border-radius:7px;font-weight:700}
.status{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
color:#855214;background:#fff3dc;border:1px solid #f1dfbc;border-radius:20px;padding:5px 10px}
.status::before{content:'';width:5px;height:5px;background:currentColor;border-radius:50%}
.status.done{color:#22604c;background:#e9f4ef;border-color:#bfd9cc}
.subtle{font-size:12px;color:var(--muted)}.hint{font-size:12px;color:var(--muted);line-height:1.65}
.finding{padding:18px 20px;background:#f4f9f7;border-left:3px solid var(--teal);
border-radius:0 8px 8px 0}.finding h3{color:#356958;font-size:11px;text-transform:uppercase;
letter-spacing:.8px;margin-bottom:9px}.finding p{font-size:17px;line-height:1.65;margin:0;
color:#213f3b;overflow-wrap:anywhere}.counter-note{padding:17px 20px;margin-top:16px;
background:#fff8ec;border:1px solid #f0e2c9;border-radius:8px}.counter-note h3{color:#785324;
font-size:13px}.counter-note p{font-size:13px;margin:7px 0 0;overflow-wrap:anywhere}
.teacher-question{margin:16px 0 0;padding-top:16px;border-top:1px solid var(--line)}
.teacher-question h3{font-size:12px;color:var(--muted);font-weight:650;margin-bottom:6px}
.teacher-question p{font-size:14px;margin:0;overflow-wrap:anywhere}
.citations{display:grid;gap:10px;margin-top:20px}.citation-row{display:flex;align-items:center;
flex-wrap:wrap;gap:6px}.citation-row>span{font-size:11px;color:var(--muted);min-width:115px}
.evidence-link{display:inline-flex;align-items:center;min-height:30px;padding:3px 9px;
border:1px solid #c7ded5;border-radius:6px;background:#f3f9f6;color:#20644e;
font-size:11px;font-family:ui-monospace,Consolas,monospace;text-decoration:none}
.evidence-link:hover{background:#e2f1e9}.evidence-link.counter{color:#84571b;
border-color:#ead7b6;background:#fff9ef}.trend-note{margin-top:-9px}
.legend{display:flex;flex-wrap:wrap;gap:18px;font-size:11px;color:var(--muted);margin:12px 0 18px}
.legend span{display:flex;align-items:center;gap:7px}.legend i{width:9px;height:9px;
border-radius:2px;background:var(--teal)}.legend i.practical{background:#6c8197}
.trend{display:grid;grid-template-columns:145px minmax(0,1fr) 42px;align-items:center;
gap:14px;padding:8px 0}.trend-label{font-size:12px;color:#31485f}
.trend-label span{font-weight:650}
.trend-label small{display:block;font-size:10px;color:var(--muted)}
.track{background:#edf2f5;height:9px;border-radius:4px;overflow:hidden}
.track>div{height:100%;background:var(--teal);border-radius:4px}
.track.practical>div{background:#6c8197}.trend strong{font-size:12px;text-align:right;
font-variant-numeric:tabular-nums}.chart-note{margin:16px 0 0;padding-top:14px;
border-top:1px solid var(--line)}.table-wrap{overflow-x:auto;min-width:0;border-radius:7px}
table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}
caption{text-align:left;color:var(--muted);font-size:12px;padding:0 0 14px}
th,td{padding:12px 8px;vertical-align:top;border-bottom:1px solid #e8edf1}
thead th{background:#f2f6f8;color:#506477;font-size:10px;font-weight:700;
letter-spacing:.4px;text-transform:uppercase}tbody th{font-weight:550}
tbody tr:last-child>td,tbody tr:last-child>th{border-bottom:0}
tbody tr.counter{background:#fffbf3}tbody tr:target{background:#eaf6f1;outline:2px solid #33897c;
outline-offset:-2px}tbody td.observation{width:38%;min-width:140px;line-height:1.65}
.score{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:650}
.tag{display:inline-block;font-size:10px;line-height:1.5;padding:3px 7px;border-radius:5px;
background:#eef3f6;color:#516a7f;white-space:nowrap}.tag.support{background:#e9f4ee;color:#28654d}
.tag.counter{background:#fff0d6;color:#82541b}.decision-panel{position:sticky;top:20px}
.decision-panel .card{padding:22px;border-top:3px solid var(--teal)}
.decision-panel .section-heading{margin-bottom:12px}.decision-panel .hint{margin-bottom:0}
fieldset{border:0;padding:0;margin:22px 0 20px;min-width:0}legend{font-size:12px;
font-weight:700;margin-bottom:10px;padding:0}.choices{display:grid;gap:8px}
.choices label{display:flex;align-items:center;gap:11px;border:1px solid #d3dee5;
border-radius:8px;padding:12px;cursor:pointer;background:#fff}
.choices label:hover{border-color:#82aaa2;background:#f8fbfa}
.choices label:has(input:checked){border-color:var(--teal);background:#eef7f3;
box-shadow:inset 0 0 0 1px var(--teal)}.choices input{accent-color:var(--teal);width:16px;
height:16px;flex-shrink:0;margin:0}.choices b{display:block;font-size:12px;line-height:1.3}
.choices small{display:block;font-size:11px;color:var(--muted);margin-top:3px}
.form-field{margin-top:17px}.form-field>label{display:block;font-size:12px;font-weight:700}
.form-field label span{color:#a45722}.field-help{font-size:11px;color:var(--muted);
margin:5px 0 8px;line-height:1.5}textarea{width:100%;min-height:105px;border:1px solid #b8c8d3;
border-radius:7px;padding:11px 12px;resize:vertical;background:#fcfdfd;color:var(--ink);
font-size:13px;line-height:1.65}textarea::placeholder{color:#687b8b}
.decision-next{display:flex;align-items:flex-start;gap:9px;padding:17px 0}
.step-dot{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;
background:#edf3f5;color:#607587;font-size:10px;flex-shrink:0}
.decision-next p{font-size:11px;line-height:1.65;margin:0;color:var(--muted)}
.decision-next strong{font-weight:600;color:#354f64}.form-disclosure{font-size:10px;
text-align:center;margin:12px 0 0;color:var(--muted)}
@supports selector(:has(*)){
.decision-form:not(:has(input[value="edit"]:checked)) .revision-field{display:none}}
.result{padding:18px;border:1px solid #bcd9ce;background:#eff8f3;border-radius:9px;
overflow-wrap:anywhere}.result-label{font-size:10px;letter-spacing:.7px;text-transform:uppercase;
color:#356b55;font-weight:700}.result h3{margin-top:8px;font-size:17px;color:#28563f}
.review-details{margin:18px 0 0}.review-details dt{font-size:11px;color:var(--muted);
font-weight:650;margin-top:15px}.review-details dd{margin:4px 0 0;font-size:13px;
white-space:pre-wrap;overflow-wrap:anywhere}.result+.hint{margin-top:14px}
.audit-card{padding:0;box-shadow:none}.audit-card summary{cursor:pointer;padding:17px 22px;
font-size:12px;font-weight:650;color:#496076;min-height:52px}
.audit-content{padding:0 22px 22px}.audit-content h3{font-size:14px;margin:12px 0}
.audit-content p{font-size:12px}.audit-content td{overflow-wrap:anywhere}
.confirm-shell{max-width:780px;margin:0 auto}.confirm-shell .card{padding:28px}
.confirm-shell h1{margin-bottom:10px}.confirm-heading{margin:28px 0 22px}
.confirm-heading p{font-size:14px;color:var(--muted)}.confirm-status{display:inline-block;
font-size:11px;font-weight:650;padding:4px 9px;border-radius:5px;background:#fff3df;color:#835717;
margin-bottom:12px}.confirmation-note{border:1px solid #d5e4e5;background:#f2f7f7;
border-radius:8px;font-size:12px;padding:14px 16px;margin:24px 0;line-height:1.7}
.confirm-shell .toolbar{padding-top:20px;border-top:1px solid var(--line)}
section,aside,[id^="evidence-"]{scroll-margin-top:24px}
@media(min-width:1021px) and (max-height:780px){.decision-panel{position:static}}
@media(max-width:1200px){main{padding:0 24px 40px}.workspace-grid{
grid-template-columns:minmax(0,1fr) 335px;gap:18px}.card{padding:20px}
.step-nav a{padding:7px}.trend{grid-template-columns:130px minmax(0,1fr) 38px;gap:10px}}
@media(max-width:1020px){.workspace-grid{grid-template-columns:minmax(0,1fr)}
.decision-panel{position:static}.page-heading{display:block}.step-nav{margin:5px 0 16px}
.decision-panel .card{padding:24px}.choices{grid-template-columns:repeat(3,minmax(0,1fr))}
.decision-form .form-field{max-width:none}.case-strip{gap:20px}.metrics{gap:15px}
.metric{padding-left:17px;min-width:75px}}
@media(max-width:640px){:root{font-size:14px}main{padding:0 16px 30px}.topbar{min-height:76px;
flex-wrap:wrap;gap:16px;padding:18px 0;margin-bottom:22px}.topbar>.toolbar{width:100%}
.topbar>.toolbar form{flex:1}.topbar>.toolbar button{width:100%;padding:10px 9px;font-size:11px}
h1{font-size:27px}.page-heading p{font-size:13px}.step-nav{justify-content:space-between;gap:2px}
.step-nav a{font-size:11px;padding:6px}.demo-notice{align-items:flex-start;padding:11px;
font-size:11px;gap:8px}.demo-notice .notice-label{display:block;margin-bottom:3px}
.notice-icon{width:20px;height:20px;font-size:10px;margin-top:1px}.mode-line{margin-top:4px}
.case-strip{display:block;padding:18px}.metrics{margin-top:19px;padding-top:16px;
border-top:1px solid #405671;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.metric{min-width:0;padding:0 7px;border:0}.metric:first-child{padding-left:0}
.metric strong{font-size:24px}.metric span{font-size:10px}.card{padding:18px}
.section-heading{align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:15px}
h2{font-size:17px}.section-number{width:23px;height:23px}.status{font-size:10px}
.finding{padding:15px}.finding p{font-size:15px}.counter-note{padding:15px}
.teacher-question p{font-size:13px}.citations{margin-top:16px}.citation-row>span{width:100%}
.trend{grid-template-columns:112px minmax(0,1fr) 34px;gap:8px;padding:8px 0}
.trend-label{font-size:11px}.trend-label small{font-size:9px}.trend strong{font-size:11px}
.evidence-table,.evidence-table tbody{display:block}.evidence-table thead{position:absolute;
width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap}
.evidence-table caption{display:block}.evidence-table tr{display:grid;
grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--line);border-radius:8px;
margin:0 0 12px;padding:10px;background:#fff}.evidence-table tr.counter{background:#fffbf3}
.evidence-table th[scope="row"],.evidence-table td{display:block;padding:5px 7px;border:0;
min-width:0;width:auto;font-size:12px}.evidence-table [data-label]::before{
content:attr(data-label);display:block;font-size:10px;color:var(--muted);font-weight:500;
margin-bottom:3px}.evidence-table td.observation{grid-column:1/-1;min-width:0;width:auto}
.evidence-table td:last-child{grid-column:1/-1}.evidence-table .tag{font-size:10px}
.decision-panel .card{padding:18px}.choices{grid-template-columns:minmax(0,1fr)}
.choices label{min-height:64px}.choices b{font-size:13px}.choices small{font-size:12px}
textarea{font-size:16px}.decision-form .full-width{font-size:14px;min-height:48px}
.confirm-shell .card{padding:20px}.confirm-shell .toolbar,.confirm-shell .toolbar form{
width:100%}.confirm-shell .toolbar button{width:100%}.review-details dd{font-size:14px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
@media print{body{background:#fff}main{padding:0;max-width:none}.topbar .toolbar,.step-nav,
.skip-link,.decision-form{display:none}.workspace-grid{display:block}.decision-panel{
position:static}.card{box-shadow:none;break-inside:avoid;margin-bottom:16px}.case-strip{
background:white;color:#183049;border:1px solid #ccd6dd}.learner h2,.learner p,.metric span{
color:#183049}.evidence-link{color:#183049}a{text-decoration:none}}
"""


def _document(title: str, content: str, *, refresh: bool = False) -> str:
    reload_page = '<meta http-equiv="refresh" content="2;url=/">' if refresh else ""
    return (
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="same-origin">'
        f'<title>{h(title)}</title>{reload_page}<style>{CSS}</style></head>'
        '<body><a class="skip-link" href="#main-content">Skip to review content</a>'
        f'<main id="main-content">{content}</main></body></html>'
    )


def _toolbar(token: str, *, qwen_enabled: bool, run_nonce: str, busy: bool) -> str:
    disabled = ' disabled aria-disabled="true"' if busy else ""
    qwen = f'''<form method="post" action="/case/start">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="mode" value="qwen">
<input type="hidden" name="run_nonce" value="{h(run_nonce)}">
<button type="submit"{disabled} title="One local model request; up to four minutes">
Run local Qwen review</button></form>''' if qwen_enabled else ""
    return f'''<div class="toolbar"><form method="post" action="/case/start">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="mode" value="seeded">
<button type="submit"{disabled}><span aria-hidden="true">+</span> New practice case</button></form>
<form method="post" action="/case/start">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="mode" value="mcp">
<button class="primary" type="submit"{disabled}>Run MCP evidence analysis
<span aria-hidden="true">→</span></button></form>{qwen}</div>'''


def _mode_text(case: Case) -> str:
    if case.mode == "demo":
        return "Authored Qwen workflow demonstration; no model inference or MCP client calls"
    if case.mode == "qwen":
        return "Local Qwen review; one bounded model request"
    return ("Live MCP calls with a deterministic model; no Qwen inference" if case.mode == "mcp"
            else "Seeded fictional case; no MCP client or model inference")


def _case_identity(case: Case) -> str:
    label = {"seeded": "Practice case", "mcp": "Deterministic MCP case",
             "qwen": "Local Qwen review", "demo": "Authored demonstration"}[case.mode]
    disclosure = ("Authored example; not a Qwen result. " if case.mode == "demo" else "")
    return (f'<div class="case-identity"><strong>{h(label)}</strong> · '
            f'Case ID: <code>{h(case.run_dir.name)}</code>'
            f'<p class="hint">{disclosure}{h(case.opened_as)}. '
            '<a href="/saved">Saved Qwen reviews</a> · '
            '<a href="/demos">Demonstration cases</a></p></div>')


def demonstration_case(root: Path, *, scenario: str | None = None,
                       run_id: str | None = None) -> Case:
    from mwalimulens.portal_demo import create_demonstration, open_demonstration

    record = (open_demonstration(root, run_id) if run_id is not None
              else create_demonstration(root, scenario))
    return Case(
        record.state, record.service, record.candidate, record.evidence, record.run_dir, "demo",
        analysis_status=record.scenario, stage="complete" if record.verified else "saved_error",
        analysis_error=record.error,
        opened_as=("Saved demonstration reopened; no model request was made" if run_id is not None
                   else "New authored demonstration; no model request was made"),
    )


def render_demonstrations(portal: TeacherPortal) -> str:
    from mwalimulens.portal_demo import saved_demonstrations

    disabled = ' disabled aria-disabled="true"' if portal._busy() else ""
    actions = "".join(
        f'<form method="post" action="/demo/start">'
        f'<input type="hidden" name="csrf" value="{h(portal.token)}">'
        f'<input type="hidden" name="scenario" value="{scenario}">'
        f'<button type="submit"{disabled}>New {scenario} demonstration</button></form>'
        for scenario in ("candidate", "error")
    )
    rows = "".join(
        f'<tr><td><code>{h(row["run_id"])}</code></td><td>{h(row["scenario"])}</td>'
        f'<td>{h(row["created_at"])}</td><td><form method="post" action="/demo/open">'
        f'<input type="hidden" name="csrf" value="{h(portal.token)}">'
        f'<input type="hidden" name="run_id" value="{h(row["run_id"])}">'
        f'<button type="submit"{disabled}>Open demonstration</button></form></td></tr>'
        for row in saved_demonstrations(portal.output_root)
    )
    return _document("MwalimuLens | Demonstration cases", f'''
<header class="topbar">{_brand()}<a class="button" href="/">Back to current case</a></header>
<section class="card"><h1>Demonstration cases</h1>
<p><strong>Authored examples, not Qwen results.</strong> No model inference or MCP client
is used. Each case has separate fictional state and keeps its demonstration label.</p>
<p>The candidate example uses the teacher confirmation process. The error example
simulates an unavailable model service and offers no decision controls.</p>
<div class="toolbar">{actions}</div></section>
<section class="card"><h2>Saved demonstration cases</h2>
<p class="hint">Opening checks the original fixture and any recorded simulated decision.
Actual model attempts are listed separately under <a href="/saved">Saved Qwen reviews</a>.
Timestamps include their UTC offset.</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="Saved demonstration cases">
<table><caption>Authored local examples</caption><thead><tr>
<th>Case ID</th><th>Authored scenario</th><th>Created</th><th>Action</th></tr></thead>
<tbody>{rows or '<tr><td colspan="4">No demonstration cases saved yet.</td></tr>'}
</tbody></table></div></section>''')


def _demonstration_validation(case: Case) -> str:
    count = "Not verified" if case.stage == "saved_error" else "0"
    return (
        '<h3>Authored demonstration record</h3><dl class="review-details">'
        f'<dt>Model requests / MCP client calls</dt><dd>{count} / {count}</dd>'
        f'<dt>Local records</dt><dd>{h(case.run_dir)}</dd></dl>'
        '<p class="hint">This example is authored for presentation practice, '
        'not generated by Qwen. '
        'The audit records direct local review-service actions using fictional evidence. '
        'It does not measure model reasoning, provider availability or tool selection.</p>'
    )


def open_qwen_case(root: Path, run_id: str) -> tuple[Case, Any]:
    """Reopen local records without seeding a case or calling an MCP service."""
    from mwalimulens.domain import load_synthetic_dataset
    from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
    from mwalimulens.mcp_server.service import EducationToolService
    from mwalimulens.mcp_server.state import JsonStateStore
    from mwalimulens.portal_qwen import QwenJob

    dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
    if not dataset.learners or any(not learner.synthetic for learner in dataset.learners):
        raise ValueError("Only fictional learner data is permitted")
    job = QwenJob.open_saved(root, run_id)
    state = JsonStateStore(job.state_path)
    case = Case(state, EducationToolService(dataset, state), None, [], job.run_dir, "qwen",
                opened_as="Saved review reopened; no model request was made")
    return case, job


def render_saved_reviews(portal: TeacherPortal) -> str:
    from mwalimulens.portal_qwen import saved_reviews

    disabled = ' disabled aria-disabled="true"' if portal._busy() else ""
    rows = "".join(
        f'<tr><td><code>{h(row["run_id"])}</code></td><td>{h(row["status"])}</td>'
        f'<td>{h(row["updated_at"])}</td><td><form method="post" action="/case/open">'
        f'<input type="hidden" name="csrf" value="{h(portal.token)}">'
        f'<input type="hidden" name="run_id" value="{h(row["run_id"])}">'
        f'<button type="submit"{disabled}>Open saved review</button></form></td></tr>'
        for row in saved_reviews(portal.output_root)
    )
    return _document("MwalimuLens | Saved Qwen reviews", f'''
<header class="topbar">{_brand()}<a class="button" href="/">Back to current case</a></header>
<section class="card"><h1>Saved Qwen reviews</h1>
<p>Open an existing local attempt without making another model request.
Saved labels are checked against the complete records when opened.</p>
<p class="hint">Only reviews under the current output folder are listed. Timestamps include
their UTC offset. An unfinished attempt cannot be resumed here.</p>
<div class="table-wrap"><table><caption>Local attempts</caption><thead><tr>
<th>Case ID</th><th>Saved label</th><th>Last job update</th><th>Action</th></tr></thead>
<tbody>{rows or '<tr><td colspan="4">No saved Qwen reviews in this output folder.</td></tr>'}
</tbody></table></div></section>''')


def _qwen_validation(case: Case) -> str:
    report = case.report or {}
    requests = report.get("model_requests") or []
    request = requests[0] if isinstance(requests, list) and requests else {}
    request = request if isinstance(request, dict) else {}
    request_count = "Not verified" if case.stage == "saved_error" else case.request_count
    return (
        '<h3>Current local Qwen attempt</h3>'
        '<dl class="review-details">'
        f'<dt>Requested model</dt><dd>{h(report.get("model", "qwen2.5:3b"))}</dd>'
        f'<dt>Model requests recorded</dt><dd>{h(request_count)}</dd>'
        f'<dt>Request duration (seconds)</dt><dd>{h(request.get("seconds"))}</dd>'
        f'<dt>Input / output tokens</dt><dd>{h(request.get("input_tokens"))} / '
        f'{h(request.get("output_tokens"))}</dd>'
        f'<dt>Proposal outcome</dt><dd>'
        f'{h(report.get("proposal_status", case.analysis_status))}</dd>'
        f'<dt>Policy</dt><dd>{h(report.get("decision_policy_id"))}</dd>'
        f'<dt>Schema</dt><dd>{h(report.get("decision_schema_id"))}</dd>'
        f'<dt>Evidence hash</dt><dd><code>{h(report.get("evidence_sha256"))}</code></dd>'
        f'<dt>Local artefacts</dt><dd>{h(case.run_dir)}</dd></dl>'
        '<p class="hint">One request maximum, with no prewarm or repair. '
        'The internal deadline is 210 seconds and the outer timeout is 240 seconds. '
        'The application controls MCP calls; autonomous model tool selection is not assessed. '
        'Semantic quality remains unverified.</p>'
    )


def _noncandidate_portal(case: Case, token: str, *, toolbar: str,
                         message: str, error: str) -> str:
    running = case.analysis_status == "running"
    abstained = case.analysis_status == "abstained"
    heading = ("Local Qwen review in progress" if running else
               "No finding proposed" if abstained else "Local Qwen review could not be completed")
    if case.mode == "demo":
        heading = ("Demonstration error" if case.stage != "saved_error" else
                   "Saved demonstration could not be verified")
    stages = {
        "queued": "Starting the local review", "retrieval": "Retrieving source evidence",
        "generation": "Waiting for the local model", "validation": "Checking the model response",
        "submission": "Recording a pending candidate", "initial": "Waiting for the local model",
    }
    detail = (
        stages.get(case.stage, "The local review is running") if running else
        case.abstention_reason if abstained else
        case.analysis_error or "No completed, verified candidate is available from this attempt."
    )
    explanation = (
        "Allow up to four minutes for this local attempt. One model request is allowed. "
        "This page refreshes to show progress; "
        "refreshing does not start another request." if running else
        "The model abstained. No candidate was created, and there is no decision to confirm."
        if abstained else
        "Review is disabled for this attempt. Any partial progress is retained "
        "in its local artefacts. "
        "A timeout does not establish that the model service has stopped computing."
    )
    if case.mode == "demo":
        explanation = (
            "This is an authored error example, not an observed Qwen failure. "
            "There is no candidate to review."
            if case.stage != "saved_error" else
            "Review is disabled because these saved demonstration records could not be verified."
        )
    validation = (_demonstration_validation(case) if case.mode == "demo"
                  else _qwen_validation(case))
    try:
        if case.stage == "saved_error":
            # Rejected artefacts (including linked state) must not be read by rendering.
            raise ValueError("Saved state was not verified")
        counts = [len(case.state.pending_reviews()), len(case.state.teacher_reviews()),
                  len(case.state.profile_updates())]
        audit = _audit(case)
    except (OSError, ValueError, KeyError, TypeError):
        counts, audit = [None, None, None], ""
    metrics = "".join(
        f'<div class="metric"><strong>{h(value)}</strong><span>{label}</span></div>'
        for value, label in zip(counts, (
            "Unverified pending records" if counts[0] else "Awaiting review",
            "Teacher decisions (simulated)", "Synthetic profile notes",
        ), strict=True)
    )
    notification = f'<div class="flash" role="status">{h(message)}</div>' if message else ""
    problem = f'<div class="error" role="alert">{h(error)}</div>' if error else ""
    content = f'''<header class="topbar">{_brand()}{toolbar}</header>
<div class="page-heading"><div><div class="eyebrow">Evidence-led teacher review</div>
<h1>Learner Progress Review</h1>
<p>Read the source records and the outcome of this local attempt.</p>
</div><nav class="step-nav" aria-label="Review sections"><a href="#summary">Summary</a>
<a href="#evidence">Evidence</a><a href="#decision">Decision</a></nav></div>
<div class="demo-notice"><p><strong>Demonstration environment:</strong>
fictional learner evidence only. Reviewer identity is simulated, not authenticated.
<span class="mode-line">{h(_mode_text(case))}.</span>
</p></div>{_case_identity(case)}{notification}{problem}
<section class="case-strip" aria-label="Current learner and review status">
<div class="learner"><span class="avatar" aria-hidden="true">A</span><div>
<h2>Amani <span>(fictional)</span></h2><p>Mathematics · Fractions</p></div></div>
<div class="metrics">{metrics}</div></section>
<div class="workspace-grid"><div class="analysis-column">
<section id="summary" class="card" aria-live="polite"><h2>{h(heading)}</h2>
<div class="finding"><h3>{'Progress' if running else 'Reason'}</h3><p>{h(detail)}</p></div>
<p class="hint">{h(explanation)}</p></section>
<section class="card"><h2>Progress across terms</h2>{_trend(case)}
<p class="hint">These are fictional source records, not a model finding. Different tasks
are not necessarily directly comparable.</p></section>
<section id="evidence" class="card"><h2>Source evidence</h2>
<p class="hint">{'Source records for this case; retrieval may still be in progress.' if running
else 'Review the source records independently of the model outcome.'}</p>
<div class="table-wrap"><table class="evidence-table">
<caption>Chronological fictional records</caption>
<thead><tr><th>ID</th><th>Term</th><th>Type</th><th>Score</th><th>Observation</th><th>Role</th></tr></thead>
<tbody>{_evidence(case)}</tbody></table></div></section>
<section class="card audit-card"><details><summary>Technical evidence and audit trail</summary>
<div class="audit-content">{validation}<div class="table-wrap"><table>
<caption>Audited actions for this attempt</caption><thead><tr><th>Action</th><th>Result</th>
<th>Timestamp</th></tr></thead><tbody>{audit}</tbody></table></div></div></details></section></div>
<aside id="decision" class="decision-panel" aria-labelledby="decision-title"><section class="card">
<h2 id="decision-title">Teacher's decision</h2><p class="hint">There is no completed candidate
to approve, revise or reject. The model cannot approve its own candidate.</p>
</section></aside></div>'''
    title = "MwalimuLens | Demonstration case" if case.mode == "demo" else (
        "MwalimuLens | Local Qwen review"
    )
    return _document(title, content,
                     refresh=running or case.worker_active)


def render_portal(case: Case, token: str, *, message: str = "", error: str = "",
                  qwen_enabled: bool = False, run_nonce: str = "", busy: bool = False) -> str:
    """Render the evidence and review controls without changing application state."""
    toolbar = _toolbar(token, qwen_enabled=qwen_enabled, run_nonce=run_nonce, busy=busy)
    if case.candidate is None or case.analysis_status != "candidate":
        return _noncandidate_portal(case, token, toolbar=toolbar, message=message, error=error)
    current = case.state.review_candidate(case.candidate["review_id"])
    pending = len(case.state.pending_reviews())
    reviews = len(case.state.teacher_reviews())
    updates = len(case.state.profile_updates())
    mode = _mode_text(case)
    status = "Awaiting teacher review" if pending else "Reviewed by simulated teacher"
    status_class = "" if pending else " done"
    notification = f'<div class="flash" role="status">{h(message)}</div>' if message else ""
    problem = f'<div class="error" role="alert">{h(error)}</div>' if error else ""
    tool_count = len(case.state.tool_calls())
    record_count = len(case.evidence)
    term_count = len({row["term_id"] for row in case.evidence})
    support = _evidence_links(current["supporting_evidence_ids"])
    counter = _evidence_links(current["counter_evidence_ids"], counter=True)
    validation = (_demonstration_validation(case) if case.mode == "demo" else
                  _qwen_validation(case) if case.mode == "qwen" else
                  '<h3>Separate local-model validation</h3>' + _model_validation())
    content = f'''<header class="topbar">{_brand()}
{toolbar}</header>
<div class="page-heading"><div><div class="eyebrow">Evidence-led teacher review</div>
<h1>Learner Progress Review</h1>
<p>Review the records, consider the uncertainty and decide what to retain.</p></div>
<nav class="step-nav" aria-label="Review sections">
<a href="#summary"><span>1</span> Summary</a>
<a href="#evidence"><span>2</span> Evidence</a>
<a href="#decision"><span>3</span> Decision</a></nav></div>
<div class="demo-notice"><span class="notice-icon" aria-hidden="true">i</span>
<p><strong class="notice-label">Demonstration environment:</strong> fictional learner evidence only.
Reviewer identity is simulated, not authenticated.<span class="mode-line">{h(mode)}.</span></p>
</div>{_case_identity(case)}{notification}{problem}
<section class="case-strip" aria-label="Current learner and review status">
<div class="learner"><span class="avatar" aria-hidden="true">A</span><div>
<h2>Amani <span>(fictional)</span></h2><p>Mathematics · Fractions</p></div></div>
<div class="metrics">
<div class="metric"><strong>{pending}</strong><span>Awaiting review</span></div>
<div class="metric"><strong>{reviews}</strong><span>Teacher decisions (simulated)</span></div>
<div class="metric"><strong>{updates}</strong><span>Synthetic profile notes</span></div></div>
</section><div class="workspace-grid"><div class="analysis-column">
<section id="summary" class="card" aria-labelledby="summary-title">
<div class="section-heading"><h2 id="summary-title"><span class="section-number"
aria-hidden="true">01</span> Evidence summary</h2>
<span class="status{status_class}">{h(status)}</span></div>
<div class="finding"><h3>Provisional finding</h3><p>{h(current["claim"])}</p></div>
<div class="counter-note"><h3>What still needs attention</h3>
<p>{h(current["uncertainty"])}</p></div>
<div class="teacher-question"><h3>Teacher question</h3>
<p>{h(current["suggested_teacher_question"])}</p></div>
<div class="citations"><div class="citation-row"><span>Supporting evidence</span>{support}</div>
<div class="citation-row"><span>Counter-evidence</span>{counter}</div></div></section>
<section class="card" aria-labelledby="progress-title"><div class="section-heading">
<h2 id="progress-title">Progress across terms</h2><span class="subtle">{term_count} terms</span>
</div><p class="hint trend-note">Scores describe assessed tasks, not a permanent ability label.</p>
<div class="legend" aria-label="Score types"><span><i aria-hidden="true"></i>Assessment</span>
<span><i class="practical" aria-hidden="true"></i>Practical task</span></div>
{_trend(case)}<p class="hint chart-note">Read each score alongside its task and classroom
observations. Different tasks are not necessarily directly comparable.</p></section>
<section id="evidence" class="card" aria-labelledby="evidence-title">
<div class="section-heading"><h2 id="evidence-title"><span class="section-number"
aria-hidden="true">02</span> Evidence record</h2>
<span class="subtle">{record_count} records · {term_count} terms</span></div>
<div class="table-wrap"><table class="evidence-table">
<caption>Chronological records, including contradictory observations.</caption>
<thead><tr><th scope="col">ID</th><th scope="col">Term</th><th scope="col">Type</th>
<th scope="col">Score</th><th scope="col">Observation</th><th scope="col">Role</th></tr></thead>
<tbody>{_evidence(case)}</tbody></table></div></section>
<section class="card audit-card"><details><summary>Technical evidence and audit trail</summary>
<div class="audit-content">{validation}
<p class="hint">{h(mode)}. {tool_count} audited action(s). The human-review service
is not exposed to the model's MCP tool allowlist.</p>
<div class="table-wrap" tabindex="0" role="region" aria-label="Technical audit records">
<table><caption class="sr-only">Audited actions for this case</caption><thead><tr>
<th scope="col">Action</th><th scope="col">Result</th><th scope="col">Timestamp</th>
</tr></thead><tbody>{_audit(case)}</tbody></table></div></div></details></section></div>
<aside id="decision" class="decision-panel" aria-labelledby="decision-title"><section class="card">
<div class="section-heading"><h2 id="decision-title"><span class="section-number"
aria-hidden="true">03</span> Teacher's decision</h2></div>
<p class="hint">Review the evidence before recording a decision.
The model cannot approve its own candidate.</p>
{_review_form(case, token)}</section></aside></div>'''
    return _document("MwalimuLens | Learner Progress Review", content)


def render_confirmation(case: Case, token: str, nonce: str, decision: str,
                        reason: str, edited: str) -> str:
    if case.candidate is None or case.analysis_status != "candidate":
        raise ValueError("No completed candidate is available for confirmation")
    outcome = "No profile note will be created." if decision == "reject" else (
        "One synthetic profile note will be created after this simulated human decision."
    )
    label = {"approve": "Approve", "edit": "Revise", "reject": "Reject"}.get(
        decision, decision.title(),
    )
    revised = (
        f'<dt>Revised wording</dt><dd>{h(edited)}</dd>' if decision == "edit" else ""
    )
    content = f'''<header class="topbar">{_brand()}
<a class="button" href="/">← Back to evidence</a></header>
<div class="confirm-shell"><div class="confirm-heading">
<div class="eyebrow">Human review · confirmation</div><h1>Confirm your decision</h1>
<p>Check the finding and your rationale before recording the decision.</p></div>
<section class="card" aria-labelledby="confirmation-title">
{_case_identity(case)}
<span class="confirm-status">Not saved yet</span>
<h2 id="confirmation-title">{h(label)} this finding?</h2>
<dl class="review-details"><dt>Provisional finding</dt><dd>{h(case.candidate['claim'])}</dd>
<dt>Your rationale</dt><dd>{h(reason)}</dd>{revised}</dl>
<p class="confirmation-note">{h(outcome)} The reviewer is simulated and not authenticated.</p>
<div class="toolbar"><form method="post" action="/review/submit">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="nonce" value="{h(nonce)}">
<button class="primary" type="submit">Confirm simulated decision</button></form>
<a class="button" href="/">Go back without saving</a></div>
</section></div>'''
    return _document("MwalimuLens | Confirm review", content)

class TeacherPortal:
    """Single-user local HTTP interface with a per-session CSRF token."""

    def __init__(self, output_root: Path, case: Case, *, qwen_enabled: bool = False,
                 qwen_job_factory=None) -> None:
        self.output_root = output_root
        self.case = case
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.confirmations: dict[str, tuple[float, str, str, str, str]] = {}
        self.qwen_enabled = qwen_enabled
        self.run_nonce = secrets.token_urlsafe(32)
        self.qwen_job = None
        self.qwen_job_factory = qwen_job_factory

    def _sync_qwen(self) -> None:
        """Read progress and completed output without starting or mutating a workflow."""
        if self.qwen_job is None:
            return
        view = self.qwen_job.snapshot()
        status = view.get("status")
        if status not in {"running", "candidate", "abstained", "error"}:
            status = "error"
        self.case.analysis_status = status
        self.case.worker_active = bool(view.get("worker_active", status == "running"))
        self.case.stage = str(view.get("stage") or "queued")
        self.case.report = view.get("report")
        self.case.candidate = view.get("candidate") if status == "candidate" else None
        self.case.abstention_reason = str(view.get("abstention_reason") or "")
        self.case.analysis_error = str(view.get("error") or "")
        self.case.request_count = int(view.get("request_count") or 0)
        if view.get("evidence"):
            self.case.evidence = view["evidence"]

    def _busy(self) -> bool:
        return self.qwen_job is not None and (
            self.case.analysis_status == "running" or self.case.worker_active
        )

    def _page(self, *, message: str = "", error: str = "") -> str:
        return render_portal(
            self.case, self.token, message=message, error=error,
            qwen_enabled=self.qwen_enabled, run_nonce=self.run_nonce, busy=self._busy(),
        )

    def _start_qwen(self) -> None:
        from mwalimulens.domain import load_synthetic_dataset
        from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
        from mwalimulens.mcp_server.service import EducationToolService, _evidence_payload
        from mwalimulens.mcp_server.state import JsonStateStore

        dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
        if not dataset.learners or any(not learner.synthetic for learner in dataset.learners):
            raise ValueError("Only fictional learner data is permitted")
        factory = self.qwen_job_factory
        if factory is None:
            from mwalimulens.portal_qwen import QwenJob

            factory = QwenJob
        job = factory(self.output_root)
        store = JsonStateStore(job.state_path)
        evidence = [
            _evidence_payload(row)
            for row in dataset.competency_evidence("L001", "MATH-FRACTIONS")
        ]
        replacement = Case(
            store, EducationToolService(dataset, store), None, evidence, job.run_dir, "qwen",
            analysis_status="running", stage="queued",
        )
        if self.qwen_job is not None:
            self.qwen_job.close()
        self.case = replacement
        self.qwen_job = job
        self.confirmations.clear()
        self.run_nonce = secrets.token_urlsafe(32)
        try:
            job.start()
        except (OSError, RuntimeError, ValueError):
            self.qwen_job = None
            self.case.analysis_status = "error"
            self.case.analysis_error = (
                "The local Qwen attempt could not start. Check its local artefacts."
            )
            try:
                job.close()
            except (OSError, RuntimeError, ValueError):
                pass  # A failed cleanup must not restore a reviewable candidate.
            raise
        self._sync_qwen()

    def _new_case(self, mode: str) -> None:
        self._replace_case(create_case(self.output_root, mode))

    def _replace_case(self, replacement: Case, job=None) -> None:
        """Switch completed cases and invalidate controls from the previous view."""
        if self.qwen_job is not None:
            self.qwen_job.close()
        self.qwen_job = job
        self.case = replacement
        self.confirmations.clear()
        self.run_nonce = secrets.token_urlsafe(32)

    def _open_saved(self, run_id: str) -> None:
        replacement, job = open_qwen_case(self.output_root, run_id)
        self._replace_case(replacement, job)
        self._sync_qwen()

    def close(self) -> None:
        """Stop the owned worker when the local application is closed."""
        with self.lock:
            if self.qwen_job is not None:
                self.qwen_job.close()
                self._sync_qwen()


def make_handler(portal: TeacherPortal):
    """Construct an isolated handler, with no shared global writable state."""

    class Handler(BaseHTTPRequestHandler):
        server_version = "MwalimuLensLocal/1.0"
        sys_version = ""

        def log_message(self, _format: str, *_args: Any) -> None:
            return  # Avoid logging URLs, tokens or free-text review rationale.

        def _trusted(self) -> bool:
            address = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != address:
                self.send_error(HTTPStatus.FORBIDDEN, "Invalid local host")
                return False
            if self.command == "POST":
                origin = self.headers.get("Origin")
                if origin is not None and origin != f"http://{address}":
                    self.send_error(HTTPStatus.FORBIDDEN, "Cross-origin request blocked")
                    return False
                site = self.headers.get("Sec-Fetch-Site")
                if site is not None and site not in {"same-origin", "none"}:
                    self.send_error(HTTPStatus.FORBIDDEN, "Cross-site request blocked")
                    return False
            return True

        def _send(self, body: str, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("Content-Security-Policy",
                             "default-src 'none'; style-src 'unsafe-inline'; "
                             "form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(encoded)

        def _bad(self, message: str, status: int = 400) -> None:
            self._send(_document("MwalimuLens | Request error",
                                 f'<div class="error" role="alert">{h(message)}</div>'
                                 '<p><a href="/">Return to the learner review</a></p>'), status)

        def _fields(self) -> dict[str, str] | None:
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != (
                "application/x-www-form-urlencoded"
            ):
                self._bad("Unsupported form encoding", 415)
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._bad("Invalid request size")
                return None
            if not 0 < length <= MAX_POST_BYTES:
                self._bad("Form is too large or empty", 413)
                return None
            try:
                payload = self.rfile.read(length).decode("utf-8", errors="strict")
                parsed = parse_qs(payload, keep_blank_values=True, max_num_fields=12,
                                  strict_parsing=True)
            except (UnicodeDecodeError, ValueError):
                self._bad("Invalid form data")
                return None
            if any(len(values) != 1 for values in parsed.values()):
                self._bad("Ambiguous form data")
                return None
            fields = {key: values[0] for key, values in parsed.items()}
            if not hmac.compare_digest(
                fields.get("csrf", "").encode("utf-8"), portal.token.encode("utf-8"),
            ):
                self._bad("Form token is invalid", 403)
                return None
            return fields

        def do_GET(self) -> None:
            if not self._trusted():
                return
            # A browser may include an empty query when submitting a GET form.
            # Ignore query text for read-only routes; POST routing stays exact.
            path = self.path.partition("?")[0]
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path not in {"/", "/saved", "/demos"}:
                self.send_error(404)
                return
            with portal.lock:
                portal._sync_qwen()
                self._send(render_saved_reviews(portal) if path == "/saved" else
                           render_demonstrations(portal) if path == "/demos" else portal._page())

        def do_POST(self) -> None:
            if not self._trusted():
                return
            if self.path not in {
                "/case/start", "/case/open", "/review/preview", "/review/submit",
                "/demo/start", "/demo/open",
            }:
                self.send_error(404)
                return
            fields = self._fields()
            if fields is None:
                return
            with portal.lock:
                portal._sync_qwen()
                if portal._busy():
                    self._bad("A local Qwen review is already running. Wait for its outcome.", 409)
                    return
                if self.path in {"/demo/start", "/demo/open"}:
                    try:
                        options = ({"run_id": fields.get("run_id", "")}
                                   if self.path == "/demo/open" else
                                   {"scenario": fields.get("scenario", "")})
                        replacement = demonstration_case(portal.output_root, **options)
                        portal._replace_case(replacement)
                    except (OSError, RuntimeError, ValueError) as exc:
                        self._bad(f"Demonstration could not be opened: {exc}", 422)
                        return
                    self._send(portal._page())
                    return
                if self.path == "/case/open":
                    try:
                        portal._open_saved(fields.get("run_id", ""))
                    except (OSError, ValueError) as exc:
                        self._bad(f"Saved review could not be opened: {exc}", 422)
                        return
                    self._send(portal._page())
                    return
                if self.path == "/case/start":
                    mode = fields.get("mode", "")
                    if mode not in {"seeded", "mcp", "qwen"}:
                        self._bad("Unsupported analysis mode")
                        return
                    if mode == "qwen":
                        if not portal.qwen_enabled:
                            self._bad("Local Qwen review is not enabled for this session.", 403)
                            return
                        if not hmac.compare_digest(
                            fields.get("run_nonce", "").encode("utf-8"),
                            portal.run_nonce.encode("utf-8"),
                        ):
                            self._bad("This model request has expired or already been used.", 409)
                            return
                        previous_case = portal.case
                        try:
                            portal._start_qwen()
                        except (OSError, RuntimeError, ValueError):
                            if portal.case is not previous_case:
                                self._send(portal._page(), 422)
                            else:
                                self._bad(
                                    "The Qwen attempt could not start; "
                                    "the previous case remains.", 422,
                                )
                            return
                        self._send(portal._page(), 202 if portal._busy() else 200)
                        return
                    try:
                        portal._new_case(mode)
                    except (OSError, RuntimeError, ValueError) as exc:
                        self._send(portal._page(error=f"Analysis failed: {exc}"), 422)
                        return
                    self._send(portal._page(message="A fresh fictional case is ready."))
                    return

                if self.path == "/review/preview":
                    if (portal.case.candidate is None or portal.case.analysis_status != "candidate"
                            or not portal.case.state.pending_reviews()):
                        self._bad("There is no pending, completed candidate to review.", 409)
                        return
                    decision = fields.get("decision", "").strip().lower()
                    reason = fields.get("reason", "").strip()
                    edited = fields.get("edited_claim", "").strip()
                    if decision not in {"approve", "edit", "reject"}:
                        self._bad("Choose approve, revise or reject")
                        return
                    if not reason or len(reason) > 1200:
                        self._bad("Provide a reason of at most 1200 characters")
                        return
                    if decision == "edit" and (not edited or len(edited) > 1200):
                        self._bad("Revised wording is required for Revise")
                        return
                    if decision != "edit":
                        edited = ""
                    nonce = secrets.token_urlsafe(32)
                    portal.confirmations.clear()
                    portal.confirmations[nonce] = (
                        time.monotonic(), portal.case.candidate["review_id"],
                        decision, reason, edited,
                    )
                    self._send(render_confirmation(portal.case, portal.token, nonce,
                                                   decision, reason, edited))
                    return

                nonce = fields.get("nonce", "")
                if portal.case.candidate is None or portal.case.analysis_status != "candidate":
                    self._bad("There is no completed candidate to confirm.", 409)
                    return
                confirmation = portal.confirmations.pop(nonce, None)
                if confirmation is None:
                    self._bad("Confirmation expired or already used", 409)
                    return
                timestamp, review_id, decision, reason, edited = confirmation
                if time.monotonic() - timestamp > CONFIRM_TTL:
                    self._bad("Confirmation expired; review the decision again", 409)
                    return
                if review_id != portal.case.candidate["review_id"]:
                    self._bad("The review case has changed", 409)
                    return
                try:
                    portal.case.service.record_teacher_review(
                        review_id=review_id, reviewer_id=REVIEWER,
                        decision=decision, reason=reason,
                        edited_claim=edited if decision == "edit" else None,
                    )
                except (ValueError, KeyError) as exc:
                    self._send(portal._page(error=f"Review could not be recorded: {exc}"), 409)
                    return
                self._send(portal._page(message="Your simulated decision has been recorded."))

    return Handler


def serve(portal: TeacherPortal, *, port: int = 0,
          open_browser: bool = True) -> None:
    """Serve only on the IPv4 loopback interface; never on the network."""
    with ThreadingHTTPServer(("127.0.0.1", port), make_handler(portal)) as server:
        server.daemon_threads = True
        url = f"http://127.0.0.1:{server.server_port}/"
        print(f"MwalimuLens local teacher workspace: {url}", flush=True)
        print("Fictional data only. Reviewer identity is simulated; no public access.")
        print("Press Ctrl+C to stop the local application.")
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass
        finally:
            portal.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=0)
    initial = parser.add_mutually_exclusive_group()
    initial.add_argument("--initial-mode", choices=("seeded", "mcp"), default="seeded")
    initial.add_argument("--open-qwen", metavar="CASE_ID",
                         help="Reopen a saved Qwen review under --output-dir without inference.")
    initial.add_argument("--demo", choices=("candidate", "error"),
                         help="Open a fresh authored demonstration without inference.")
    initial.add_argument("--open-demo", metavar="CASE_ID",
                         help="Reopen an authored demo-* case under --output-dir.")
    parser.add_argument("--enable-qwen", action="store_true",
                        help="Enable explicit, bounded local Qwen requests in the browser.")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    try:
        root = args.output_dir.expanduser().resolve()
        if args.open_qwen is not None:
            case, job = open_qwen_case(root, args.open_qwen)
            portal = TeacherPortal(root, case, qwen_enabled=args.enable_qwen)
            portal.qwen_job = job
            portal._sync_qwen()
        elif args.demo is not None or args.open_demo is not None:
            case = demonstration_case(root, scenario=args.demo, run_id=args.open_demo)
            portal = TeacherPortal(root, case, qwen_enabled=args.enable_qwen)
        else:
            case = create_case(root, args.initial_mode)
            case.opened_as = "Automatically opened at startup"
            portal = TeacherPortal(root, case, qwen_enabled=args.enable_qwen)
        serve(portal, port=args.port, open_browser=not args.no_open)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Teacher workspace could not start: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
