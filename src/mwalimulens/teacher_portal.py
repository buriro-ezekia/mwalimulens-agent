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
    candidate: dict[str, Any]
    evidence: list[dict[str, Any]]
    run_dir: Path
    mode: str
    report: dict[str, Any] | None = None


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


def _evidence(case: Case) -> str:
    supporting = set(case.candidate["supporting_evidence_ids"])
    opposing = set(case.candidate["counter_evidence_ids"])
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
            f'<tr class="{cls}"><td><code>{h(ident)}</code></td>'
            f'<td>{h(item["term_id"])}</td><td>{h(item["evidence_type"])}</td>'
            f'<td>{h(score_text)}</td><td>{h(item.get("observation") or "—")}</td>'
            f'<td><span class="tag {cls}">{role}</span></td></tr>'
        )
    return "".join(rows)


def _trend(case: Case) -> str:
    bars = []
    for item in case.evidence:
        score = item.get("score")
        if isinstance(score, (float, int)):
            bars.append(
                f'<div class="trend"><span>{h(item["term_id"])}</span>'
                f'<div class="track"><div style="width:{score * 100:.1f}%"></div></div>'
                f'<strong>{score * 100:.0f}%</strong></div>'
            )
    return "".join(bars)


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
    if not case.state.pending_reviews():
        review = case.state.teacher_reviews()[-1]
        return (
            '<div class="result" role="status"><h3>Review recorded</h3>'
            f'<p><b>Decision:</b> {h(review["decision"].title())}</p>'
            f'<p><b>Reason:</b> {h(review["reason"])}</p>'
            f'<p><b>Final wording:</b> {h(review.get("final_claim"))}</p>'
            f'<p><b>Synthetic profile notes:</b> {len(case.state.profile_updates())}</p>'
            '</div>'
        )
    return f'''<form method="post" action="/review/preview">
<input type="hidden" name="csrf" value="{h(token)}">
<fieldset><legend>What is your decision?</legend><div class="choices">
<label><input type="radio" name="decision" value="approve" required>
<b>Approve</b><small>Accept a provisional note.</small></label>
<label><input type="radio" name="decision" value="edit">
<b>Revise</b><small>Improve the wording.</small></label>
<label><input type="radio" name="decision" value="reject">
<b>Reject</b><small>Keep the record unchanged.</small></label>
</div></fieldset>
<label for="reason">Reason for your decision *</label>
<textarea id="reason" name="reason" required maxlength="1200" rows="3"
placeholder="Explain your decision using the evidence."></textarea>
<label for="edited">Revised wording (required only when revising)</label>
<textarea id="edited" name="edited_claim" maxlength="1200" rows="3"
placeholder="Write the wording you want to retain."></textarea>
<p class="hint">A confirmation step is required. This is a simulated reviewer, not
an authenticated teacher.</p><button class="primary">Review decision</button></form>'''

CSS = """
:root{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;color:#1b304a;
background:#f4f7fa;font-size:15px}*{box-sizing:border-box}body{margin:0}
main{max-width:1180px;margin:auto;padding:22px 20px 50px}
header{background:#182d50;color:white;border-radius:16px;padding:28px 32px}
header p{color:#d8e6f2;max-width:790px;line-height:1.5}
.eyebrow{font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#a6c6d6}
h1{font-size:33px;margin:8px 0 10px}.toolbar{display:flex;gap:10px;flex-wrap:wrap}
button{font:inherit;font-weight:650;cursor:pointer;border-radius:8px;padding:10px 16px;
border:1px solid #bbc9d7;background:white;color:#1b304a}
button.primary{background:#087e79;border-color:#087e79;color:white}
button.light{background:transparent;color:white;border-color:#9eb6cb}
button:hover,button:focus-visible{outline:2px solid #4bb8a9;outline-offset:2px}
.card{background:white;border:1px solid #dce4ec;border-radius:14px;padding:21px;
margin-top:17px;box-shadow:0 4px 16px #12233d07;min-width:0}
h2{font-size:20px;margin:0 0 7px}h3{font-size:17px}
.hint{font-size:13px;color:#56687b;line-height:1.5}
.notice{background:#fff6e7;border-left:4px solid #cb8b2b;border-radius:6px;
margin-top:15px;padding:12px 15px;font-size:13px}
.flash{background:#eaf6f2;border-left:4px solid #087e79;padding:12px;margin-top:12px}
.error{background:#fff0eb;border-left:4px solid #a93226;padding:12px;margin-top:12px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:17px}
.metric{background:white;border:1px solid #dce4ec;border-radius:12px;padding:14px}
.metric strong{display:block;font-size:27px}.metric span{font-size:12px;color:#56687b}
.grid{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(310px,1fr);gap:17px}
.grid .card{margin-top:17px}.summary{border-left:4px solid #087e79;padding:3px 14px;margin:14px 0}
.counter-note{background:#fff7e8;border-radius:8px;padding:12px 14px}
.tag{font-size:12px;padding:3px 8px;background:#edf2f6;border-radius:15px;white-space:nowrap}
.tag.counter{background:#fff0d8;color:#88530b}.tag.support{background:#e6f4ec;color:#116b4a}
.status{display:inline-block;border-radius:20px;background:#fff0d8;color:#85550b;
padding:5px 11px;font-size:12px;font-weight:700}
.status.done{background:#e6f4ec;color:#116b4a}
.trend{display:grid;grid-template-columns:90px 1fr 44px;align-items:center;gap:9px;
margin:10px 0;font-size:13px}.track{background:#e8eef4;height:11px;border-radius:10px;
overflow:hidden}.track div{background:#087e79;height:100%;border-radius:10px}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #e4eaf0}
th{background:#eef2f6;color:#516278}tr.counter{background:#fffbf3}
fieldset{border:0;padding:0;margin:16px 0}legend{font-weight:700;margin-bottom:12px}
.choices{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}
.choices label{border:1px solid #cdd8e2;border-radius:9px;padding:12px;cursor:pointer}
.choices label:has(input:checked){border:2px solid #087e79;background:#eaf6f2}
.choices b,.choices small{display:block}.choices small{font-size:12px;color:#56687b}
form>label{display:block;font-weight:650;margin:14px 0 6px}
textarea{width:100%;font:inherit;border:1px solid #acbdce;border-radius:8px;
padding:10px;resize:vertical}textarea:focus-visible{outline:2px solid #087e79}
.result{background:#eaf6f2;padding:15px;border-radius:8px}
details summary{cursor:pointer;font-weight:700;padding:8px 0}
footer{color:#56687b;font-size:12px;margin-top:22px}
@media(max-width:850px){.grid{grid-template-columns:1fr}}
@media(max-width:570px){main{padding:12px}header{padding:21px}h1{font-size:27px}
.metrics,.choices{grid-template-columns:1fr}}
"""


def _document(title: str, content: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="referrer" content="no-referrer">'
        f'<title>{h(title)}</title><style>{CSS}</style></head>'
        f'<body><main>{content}</main></body></html>'
    )


def render_portal(case: Case, token: str, *, message: str = "", error: str = "") -> str:
    """Responsive, self-contained, escaped teacher workflow page."""
    current = case.state.review_candidate(case.candidate["review_id"])
    pending = len(case.state.pending_reviews())
    reviews = len(case.state.teacher_reviews())
    updates = len(case.state.profile_updates())
    mode = (
        "Live MCP calls with a deterministic model; no Qwen inference"
        if case.mode == "mcp" else "Seeded fictional case; no MCP client or model inference"
    )
    status = "Awaiting teacher review" if pending else "Reviewed by simulated teacher"
    status_class = "" if pending else " done"
    notification = f'<div class="flash" role="status">{h(message)}</div>' if message else ""
    problem = f'<div class="error" role="alert">{h(error)}</div>' if error else ""
    tool_count = len(case.state.tool_calls())
    content = f'''<header><div class="eyebrow">MwalimuLens · Teacher workspace</div>
<h1>Learner Progress Review</h1><p>Explore evidence across school terms, weigh uncertainty,
and make a considered decision. The agent proposes; the teacher decides.</p>
<div class="toolbar"><form method="post" action="/case/start">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="mode" value="seeded">
<button class="light">New practice case</button></form>
<form method="post" action="/case/start">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="mode" value="mcp">
<button class="light">Run MCP evidence analysis</button>
</form></div></header>
<div class="notice"><strong>Demonstration environment:</strong> fictional learner evidence only.
Reviewer identity is simulated, not authenticated. This runs locally on your computer,
not as a public school service. <strong>{h(mode)}.</strong></div>
{notification}{problem}
<div class="metrics"><div class="metric"><strong>{pending}</strong>
<span>Awaiting review</span></div>
<div class="metric"><strong>{reviews}</strong><span>Teacher decisions (simulated)</span></div>
<div class="metric"><strong>{updates}</strong><span>Synthetic profile notes</span></div></div>
<div class="grid"><section class="card"><h2>Evidence summary</h2>
<p class="hint">Learner: Amani (fictional) · Mathematics · Fractions</p>
<span class="status{status_class}">{h(status)}</span>
<div class="summary"><h3>Provisional finding</h3><p>{h(current["claim"])}</p></div>
<div class="counter-note"><b>What still needs attention</b>
<p>{h(current["uncertainty"])}</p><p><b>Teacher question:</b>
{h(current["suggested_teacher_question"])}</p></div>
<p class="hint">Evidence supporting the finding: 
{h(', '.join(current['supporting_evidence_ids']))}<br>
Contradictory evidence: {h(', '.join(current['counter_evidence_ids']))}</p></section>
<section class="card"><h2>Progress across terms</h2>
<p class="hint">Scores describe assessed tasks, not a permanent ability label.</p>
{_trend(case)}<p class="hint">Quantitative progress must be interpreted alongside
classroom observations and practical work.</p></section></div>
<section class="card"><h2>Evidence record</h2><p class="hint">Chronological records,
including contradictory observations.</p><div class="table-wrap"><table>
<thead><tr><th>ID</th><th>Term</th><th>Type</th><th>Score</th><th>Observation</th>
<th>Role</th></tr></thead><tbody>{_evidence(case)}</tbody></table></div></section>
<section class="card"><h2>Teacher's decision</h2>
<p class="hint">Review the evidence before recording a decision.
The model cannot approve its own candidate.</p>{_review_form(case, token)}</section>
<section class="card"><details><summary>Technical evidence and audit trail</summary>
<h3>Separate local-model validation</h3>{_model_validation()}
<p class="hint">{h(mode)}. {tool_count} audited action(s). The human-review
service is not exposed to the model's MCP tool allowlist.</p>
<div class="table-wrap"><table><thead><tr><th>Action</th><th>Result</th><th>Timestamp</th>
</tr></thead><tbody>{_audit(case)}</tbody></table></div></details></section>
<footer>Offline-friendly local application · no external assets · synthetic learner data only.
Original challenge evidence and published video remain unchanged.</footer>'''
    return _document("MwalimuLens | Learner Progress Review", content)


def render_confirmation(case: Case, token: str, nonce: str, decision: str,
                        reason: str, edited: str) -> str:
    outcome = "No profile note will be created." if decision == "reject" else (
        "One synthetic profile note will be created after this simulated human decision."
    )
    content = f'''<header><div class="eyebrow">MwalimuLens · Human review</div>
<h1>Confirm your decision</h1><p>Check the decision and rationale before
recording them in the local audit trail.</p></header>
<section class="card"><h2>{h(decision.title())} this finding?</h2>
<p><b>Provisional finding:</b> {h(case.candidate['claim'])}</p>
<p><b>Your rationale:</b> {h(reason)}</p>
{f'<p><b>Revised wording:</b> {h(edited)}</p>' if decision == 'edit' else ''}
<p class="notice">{h(outcome)} The reviewer is simulated and not authenticated.</p>
<div class="toolbar"><form method="post" action="/review/submit">
<input type="hidden" name="csrf" value="{h(token)}">
<input type="hidden" name="nonce" value="{h(nonce)}">
<button class="primary">Confirm simulated decision</button></form>
<form method="get" action="/"><button>Go back without saving</button></form></div>
</section>'''
    return _document("MwalimuLens | Confirm review", content)

class TeacherPortal:
    """Single-user local HTTP interface with a per-session CSRF token."""

    def __init__(self, output_root: Path, case: Case) -> None:
        self.output_root = output_root
        self.case = case
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.confirmations: dict[str, tuple[float, str, str, str, str]] = {}

    def _new_case(self, mode: str) -> None:
        replacement = create_case(self.output_root, mode)
        self.case = replacement
        self.confirmations.clear()


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
            self.send_header("Referrer-Policy", "no-referrer")
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
            if not hmac.compare_digest(fields.get("csrf", ""), portal.token):
                self._bad("Form token is invalid", 403)
                return None
            return fields

        def do_GET(self) -> None:
            if not self._trusted():
                return
            if self.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if self.path != "/":
                self.send_error(404)
                return
            with portal.lock:
                self._send(render_portal(portal.case, portal.token))

        def do_POST(self) -> None:
            if not self._trusted():
                return
            if self.path not in {"/case/start", "/review/preview", "/review/submit"}:
                self.send_error(404)
                return
            fields = self._fields()
            if fields is None:
                return
            with portal.lock:
                if self.path == "/case/start":
                    mode = fields.get("mode", "")
                    if mode not in {"seeded", "mcp"}:
                        self._bad("Unsupported analysis mode")
                        return
                    try:
                        portal._new_case(mode)
                    except (OSError, RuntimeError, ValueError) as exc:
                        self._send(render_portal(portal.case, portal.token,
                                                 error=f"Analysis failed: {exc}"), 422)
                        return
                    self._send(render_portal(portal.case, portal.token,
                                             message="A fresh fictional case is ready."))
                    return

                if self.path == "/review/preview":
                    if not portal.case.state.pending_reviews():
                        self._bad("This case has already been reviewed", 409)
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
                    self._send(render_portal(portal.case, portal.token,
                                             error=f"Review could not be recorded: {exc}"), 409)
                    return
                self._send(render_portal(portal.case, portal.token,
                                         message="Your simulated decision has been recorded."))

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--initial-mode", choices=("seeded", "mcp"), default="seeded")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    try:
        root = args.output_dir.expanduser().resolve()
        portal = TeacherPortal(root, create_case(root, args.initial_mode))
        serve(portal, port=args.port, open_browser=not args.no_open)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Teacher workspace could not start: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
