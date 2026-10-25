"""Offline, synthetic-only human review sandbox for the Nairobi demonstration.

This is not an authenticated teacher portal, a model tool or a live MCP run.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import webbrowser
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any

from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "runtime" / "nairobi_review_sandbox"
SIMULATED_REVIEWER = "simulated-teacher-not-authenticated"

# Fictional evidence IDs are validated by the existing EducationToolService.
CANDIDATE: dict[str, Any] = {
    "learner_id": "L001",
    "competency_code": "MATH-FRACTIONS",
    "claim": "Fraction performance improved across terms, but explanation remains mixed.",
    "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009", "EV-011"],
    "counter_evidence_ids": ["EV-008"],
    "uncertainty": "Independent explanation in an open-ended task remains uncertain.",
    "suggested_teacher_question": (
        "Can the learner explain their method on an unfamiliar fraction problem?"
    ),
}


def _safe(value: Any) -> str:
    return escape(str(value) if value is not None else "—", quote=True)


def _score(value: Any) -> str:
    return f"{value * 100:.0f}%" if isinstance(value, (int, float)) else "—"


def render_review_page(
    *,
    candidate: dict[str, Any],
    evidence: list[dict[str, Any]],
    state: JsonStateStore,
) -> str:
    """Render an escaped, self-contained before/after view of real sandbox state."""

    current = state.review_candidate(candidate["review_id"])
    reviews = state.teacher_reviews()
    updates = state.profile_updates()
    support = set(candidate["supporting_evidence_ids"])
    counter = set(candidate["counter_evidence_ids"])
    evidence_rows = []
    for item in evidence:
        evidence_id = item["evidence_id"]
        role = "Counter-evidence" if evidence_id in counter else (
            "Supporting" if evidence_id in support else "Context"
        )
        evidence_rows.append(
            "<tr>"
            f"<td><code>{_safe(evidence_id)}</code></td>"
            f"<td>{_safe(item['term_id'])}</td>"
            f"<td>{_safe(item['evidence_type'])}</td>"
            f"<td>{_safe(_score(item.get('score')))}</td>"
            f"<td>{_safe(item.get('observation'))}</td>"
            f"<td>{_safe(role)}</td></tr>"
        )
    audit_rows = [
        "<tr>"
        f"<td><code>{_safe(event.get('tool_name'))}</code></td>"
        f"<td>{_safe(event.get('status'))}</td>"
        f"<td>{_safe(event.get('timestamp'))}</td></tr>"
        for event in state.tool_calls()
    ]
    decision_html = "<p>No human decision has been recorded. The candidate is pending.</p>"
    if reviews:
        review = reviews[-1]
        outcome = (
            "One synthetic profile note was created after the simulated human decision."
            if updates else "No learner-profile note was created."
        )
        decision_html = (
            f"<p><strong>Decision:</strong> {_safe(review['decision'])}</p>"
            f"<p><strong>Reason:</strong> {_safe(review['reason'])}</p>"
            f"<p><strong>Final wording:</strong> {_safe(review.get('final_claim'))}</p>"
            f"<p>{_safe(outcome)}</p>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MwalimuLens — synthetic teacher review</title>
<style>
:root {{ font-family: system-ui, sans-serif; color: #18253a; background: #f5f7fb; }}
* {{ box-sizing: border-box; }} body {{ margin: 0; }}
main {{ max-width: 1120px; margin: auto; padding: 28px 20px 50px; }}
header {{ background: #172b4d; color: white; padding: 24px; border-radius: 14px; }}
header p {{ max-width: 820px; line-height: 1.55; }}
.notice {{ border-left: 5px solid #b46b00; padding: 14px; background: #fff5e4;
  margin: 20px 0; line-height: 1.5; }}
.card {{ background: white; padding: 20px; border-radius: 12px; margin-top: 18px;
  border: 1px solid #dbe2eb; }}
.metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px; margin-top: 18px; }}
.metric {{ padding: 14px; background: white; border: 1px solid #dbe2eb;
  border-radius: 10px; }}
.metric strong {{ display: block; font-size: 27px; }}
.metric span {{ font-size: 13px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th, td {{ padding: 10px; border-bottom: 1px solid #e1e6ed;
  text-align: left; vertical-align: top; }}
th {{ background: #eef2f8; }} .scroll {{ overflow-x: auto; }}
code {{ overflow-wrap: anywhere; }} footer {{ margin-top: 22px; color: #526078; }}
</style></head><body><main>
<header><p>MWALIMULENS · NAIROBI REFINEMENT · SYNTHETIC ONLY</p>
<h1>Teacher decision gate</h1>
<p>Evidence and a provisional candidate are displayed for a simulated human decision.
This static page reflects the actual local state; it cannot approve or reject anything.</p>
</header>
<div class="notice"><strong>Demonstration boundary:</strong> All learner records are fictional.
The reviewer identity is simulated and <strong>not authenticated</strong>. This is not a
production teacher portal and has no public write endpoint. The candidate was seeded for
this isolated review demonstration; no LLM inference is claimed in this run.</div>
<div class="metrics">
<div class="metric"><strong>{len(state.pending_reviews())}</strong>
<span>Pending candidates</span></div>
<div class="metric"><strong>{len(reviews)}</strong><span>Simulated teacher decisions</span></div>
<div class="metric"><strong>{len(updates)}</strong><span>Synthetic profile updates</span></div>
</div>
<section class="card"><h2>Candidate: {_safe(current['status'])}</h2>
<p><strong>Learner:</strong> L001 (fictional) · <strong>Competency:</strong>
{_safe(current['competency_code'])}</p>
<p><strong>Claim:</strong> {_safe(current['claim'])}</p>
<p><strong>Uncertainty:</strong> {_safe(current['uncertainty'])}</p>
<p><strong>Teacher question:</strong> {_safe(current['suggested_teacher_question'])}</p>
<p><strong>Supporting IDs:</strong> {_safe(', '.join(current['supporting_evidence_ids']))}</p>
<p><strong>Counter-evidence IDs:</strong> {_safe(', '.join(current['counter_evidence_ids']))}</p>
</section>
<section class="card"><h2>Longitudinal evidence</h2><div class="scroll"><table>
<thead><tr><th>Evidence ID</th><th>Term</th><th>Type</th><th>Score</th>
<th>Observation</th><th>Role</th></tr></thead><tbody>
{''.join(evidence_rows)}
</tbody></table></div></section>
<section class="card"><h2>Human review outcome</h2>{decision_html}</section>
<section class="card"><h2>Local audit trail</h2><div class="scroll"><table>
<thead><tr><th>Action</th><th>Status</th><th>Timestamp</th></tr></thead><tbody>
{''.join(audit_rows)}
</tbody></table></div></section>
<footer>Offline, synthetic-only review sandbox. Original challenge evidence is unchanged.</footer>
</main></body></html>"""


def _ask(input_fn: Callable[[str], str], prompt: str) -> str | None:
    try:
        value = input_fn(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return value


def _nonempty(input_fn: Callable[[str], str], prompt: str) -> str | None:
    while True:
        value = _ask(input_fn, prompt)
        if value is None or value.lower() in {"cancel", "quit"}:
            return None
        if value:
            return value
        print("Please enter a non-empty response, or type cancel.")


def _choice(input_fn: Callable[[str], str]) -> str | None:
    while True:
        value = _ask(input_fn, "Decision (approve/edit/reject, or cancel): ")
        if value is None or value.lower() in {"cancel", "quit"}:
            return None
        if value.lower() in {"approve", "edit", "reject"}:
            return value.lower()
        print("Choose approve, edit, reject, or cancel.")


def run_review_demo(
    *,
    output_root: Path = DEFAULT_OUTPUT,
    prepare_only: bool = False,
    open_browser: bool = True,
    input_fn: Callable[[str], str] = input,
    browser_open: Callable[[str], Any] = webbrowser.open,
) -> dict[str, Any]:
    """Create fresh synthetic state and require explicit terminal consent to review."""

    dataset = load_synthetic_dataset(ROOT / "data" / "synthetic")
    if not dataset.learners or any(not learner.synthetic for learner in dataset.learners):
        raise ValueError("The review sandbox requires exclusively synthetic learners")

    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="review-", dir=output_root))
    state = JsonStateStore(run_dir / "state.json")
    service = EducationToolService(dataset, state)
    evidence = service.get_competency_evidence("L001", "MATH-FRACTIONS")["evidence"]
    candidate = service.flag_pattern_for_review(**CANDIDATE)

    before = run_dir / "before.html"
    before.write_text(
        render_review_page(candidate=candidate, evidence=evidence, state=state),
        encoding="utf-8",
    )
    result: dict[str, Any] = {
        "status": "pending_teacher_review",
        "run_directory": str(run_dir),
        "state_path": str(state.path),
        "before_html": str(before),
        "after_html": None,
        "review_id": candidate["review_id"],
        "teacher_review_count": 0,
        "profile_update_count": 0,
    }
    print("Synthetic-only review sandbox. No real learner data or authenticated teacher.")
    print("No model inference or MCP client call is performed in this review-only demo.")
    print(f"Evidence and pending candidate: {before}")
    if open_browser:
        browser_open(before.as_uri())
        print("Return to this terminal to choose a simulated teacher decision.")
    if prepare_only:
        return result

    decision = _choice(input_fn)
    if decision is None:
        print("Review cancelled. Candidate remains pending.")
        return result
    reason = _nonempty(input_fn, "Reason for this decision (or cancel): ")
    if reason is None:
        print("Review cancelled. Candidate remains pending.")
        return result
    edited_claim = None
    if decision == "edit":
        edited_claim = _nonempty(input_fn, "Revised claim (or cancel): ")
        if edited_claim is None:
            print("Review cancelled. Candidate remains pending.")
            return result

    print("Simulated reviewer only; this is not an authenticated teacher action.")
    confirmation = _ask(input_fn, "Type REVIEW to record this simulated decision: ")
    if confirmation != "REVIEW":
        print("Review cancelled. Candidate remains pending.")
        return result

    service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id=SIMULATED_REVIEWER,
        decision=decision,
        reason=reason,
        edited_claim=edited_claim,
    )
    after = run_dir / "after.html"
    after.write_text(
        render_review_page(candidate=candidate, evidence=evidence, state=state),
        encoding="utf-8",
    )
    result.update(
        status=state.review_candidate(candidate["review_id"])["status"],
        after_html=str(after),
        teacher_review_count=len(state.teacher_reviews()),
        profile_update_count=len(state.profile_updates()),
    )
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Simulated decision: {decision}")
    print(f"Teacher decisions: {result['teacher_review_count']}")
    print(f"Synthetic profile updates: {result['profile_update_count']}")
    print(f"Reviewed state: {after}")
    if open_browser:
        browser_open(after.as_uri())
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_review_demo(
            output_root=args.output_dir,
            prepare_only=args.prepare_only,
            open_browser=not args.no_open,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"Review sandbox failed: {exc}", file=sys.stderr)
        return 2
    return 0 if result["status"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
