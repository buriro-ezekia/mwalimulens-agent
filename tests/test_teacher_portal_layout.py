"""Presentation regressions: responsive evidence, truthful modes and unchanged review state."""
from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from mwalimulens.teacher_portal import (
    Case,
    _evidence,
    _trend,
    render_confirmation,
    render_portal,
)


class Tags(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


@pytest.fixture
def case(tmp_path):
    candidate = {
        "review_id": "layout-case", "status": "pending_teacher_review",
        "claim": "Recorded scores differ; independent explanation remains uncertain.",
        "supporting_evidence_ids": ["EV-004", "EV-011"],
        "counter_evidence_ids": ["EV-008"],
        "uncertainty": "Different tasks limit direct score comparisons.",
        "suggested_teacher_question": "Can the learner explain an unfamiliar task unaided?",
    }
    reviews, updates, calls = [], [], []
    state = SimpleNamespace(
        candidate=candidate, reviews=reviews, updates=updates, calls=calls,
        review_candidate=lambda _ident: dict(candidate),
        pending_reviews=lambda: (candidate,) if not reviews else (),
        teacher_reviews=lambda: tuple(reviews),
        profile_updates=lambda: tuple(updates),
        tool_calls=lambda: tuple(calls),
    )
    evidence = [
        {"evidence_id": "EV-004", "term_id": "2025-T2", "evidence_type": "assessment",
         "score": .78, "observation": None},
        {"evidence_id": "EV-008", "term_id": "2025-T3", "evidence_type": "observation",
         "score": None, "observation": "Independent explanation needs checking."},
        {"evidence_id": "EV-011", "term_id": "2026-T2", "evidence_type": "practical_task",
         "score": .81, "observation": "Explained an equivalence in the practical task."},
    ]
    return Case(state, None, candidate, evidence, tmp_path, "seeded")


@pytest.mark.parametrize("mode", ["seeded", "mcp"])
@pytest.mark.parametrize("decision", [None, "approve", "edit", "reject"])
def test_footer_absent_and_disclosures_retained(case, mode, decision):
    case.mode = mode
    if decision:
        case.state.reviews.append({"decision": decision, "reason": "A fictional check.",
                                   "final_claim": "A revised finding."})
        if decision != "reject":
            case.state.updates.append({"claim": "A revised finding."})
    before = deepcopy((case.state.candidate, case.state.reviews, case.state.updates))
    html = render_portal(case, "test-token")
    assert "<footer" not in html
    assert "Offline-friendly local application" not in html
    assert "Original challenge evidence and published video remain unchanged." not in html
    assert "fictional learner evidence only" in html
    assert "Reviewer identity is simulated, not authenticated." in html
    assert "The model cannot approve its own candidate." in html
    assert "Technical evidence and audit trail" in html
    expected = ("Live MCP calls with a deterministic model; no Qwen inference"
                if mode == "mcp" else "Seeded fictional case; no MCP client or model inference")
    assert expected in html
    assert before == (case.state.candidate, case.state.reviews, case.state.updates)


def test_landmarks_and_section_links_are_real_targets(case):
    parsed = Tags(render_portal(case, "token"))
    assert ("html", {"lang": "en-GB"}) in parsed.tags
    ids = [attrs["id"] for _, attrs in parsed.tags if "id" in attrs]
    assert len(ids) == len(set(ids))
    for tag, attrs in parsed.tags:
        if tag == "a" and attrs.get("href", "").startswith("#"):
            assert attrs["href"][1:] in ids
    assert {"main-content", "summary", "evidence", "decision"} <= set(ids)
    assert any(tag == "aside" and attrs.get("aria-labelledby") == "decision-title"
               for tag, attrs in parsed.tags)


def test_scores_keep_record_ids_types_values_and_order(case):
    html = _trend(case)
    assert "78%" in html and "81%" in html
    assert "Assessment · EV-004" in html and "Practical task · EV-011" in html
    assert html.index("EV-004") < html.index("EV-011")
    assert "EV-008" not in html  # An unscored observation is not converted into a zero score.
    assert 'class="track practical"' in html


def test_evidence_preserves_unscored_rows_and_responsive_labels(case):
    html = _evidence(case)
    parsed = Tags(html)
    rows = [attrs["id"] for tag, attrs in parsed.tags if tag == "tr"]
    assert rows == ["evidence-EV-004", "evidence-EV-008", "evidence-EV-011"]
    assert {"Record", "Term", "Type", "Score", "Observation", "Role"} <= {
        attrs["data-label"] for _, attrs in parsed.tags if "data-label" in attrs
    }
    assert "Independent explanation needs checking." in html
    assert "Counter-evidence" in html
    assert "Practical task" in html and "practical_task" not in html


def test_case_counts_are_computed_not_hard_coded(case):
    html = render_portal(case, "token")
    assert "3 records · 3 terms" in html
    assert '<strong>1</strong><span>Awaiting review</span>' in html
    assert '<strong>0</strong><span>Teacher decisions (simulated)</span>' in html


def test_forms_keep_post_routes_and_csrf_without_executable_assets(case):
    parsed = Tags(render_portal(case, "token"))
    forms = [attrs for tag, attrs in parsed.tags if tag == "form"]
    assert [form["action"] for form in forms] == [
        "/case/start", "/case/start", "/review/preview",
    ]
    assert all(form["method"] == "post" for form in forms)
    tokens = [attrs for tag, attrs in parsed.tags
              if tag == "input" and attrs.get("name") == "csrf"]
    assert len(tokens) == len(forms) and all(x["value"] == "token" for x in tokens)
    assert not any(tag in {"script", "iframe", "object", "embed", "link", "img"}
                   for tag, _ in parsed.tags)
    assert not any(name.startswith("on") for _, attrs in parsed.tags for name in attrs)


@pytest.mark.parametrize("field", ["claim", "uncertainty", "suggested_teacher_question"])
def test_candidate_text_is_escaped_in_new_layout(case, field):
    case.candidate[field] = '<img src=x onerror="alert(1)">'
    html = render_portal(case, "token")
    assert "&lt;img" in html
    assert "<img" not in html


def test_evidence_text_and_identifiers_are_escaped(case):
    case.evidence[0]["observation"] = '<script>alert("x")</script>'
    case.evidence[0]["evidence_id"] = 'bad" onmouseover="alert(1)'
    html = _evidence(case)
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert not any("onmouseover" in attrs for _, attrs in Tags(html).tags)


@pytest.mark.parametrize("decision", ["approve", "edit", "reject"])
def test_confirmation_is_explicit_escaped_and_does_not_write(case, decision):
    before = deepcopy((case.state.reviews, case.state.updates))
    html = render_confirmation(case, "token", "once", decision, "<unsafe>", "<revised>")
    assert "Not saved yet" in html and "Confirm simulated decision" in html
    assert 'action="/review/submit"' in html
    assert 'name="nonce" value="once"' in html
    assert "&lt;unsafe&gt;" in html and "<unsafe>" not in html
    assert ("&lt;revised&gt;" in html) is (decision == "edit")
    if decision == "edit":
        assert "Revise this finding?" in html
    if decision == "reject":
        assert "No profile note will be created." in html
    assert before == (case.state.reviews, case.state.updates)


def test_empty_score_list_has_explicit_message(case):
    for row in case.evidence:
        row["score"] = None
    assert "No scored tasks are recorded" in _trend(case)
