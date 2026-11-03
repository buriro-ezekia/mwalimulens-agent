"""Synthetic-only teacher review demonstration and human decision boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.teacher_review_demo import run_review_demo


def _answers(*values: str):
    iterator = iter(values)

    def read(_prompt):
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc

    return read


def _run(tmp_path: Path, *answers: str, prepare_only: bool = False):
    return run_review_demo(
        output_root=tmp_path,
        prepare_only=prepare_only,
        open_browser=False,
        input_fn=_answers(*answers),
    )


def test_prepare_only_keeps_human_gate_untouched(tmp_path) -> None:
    result = _run(tmp_path, prepare_only=True)
    state = JsonStateStore(Path(result["state_path"]))
    html = Path(result["before_html"]).read_text(encoding="utf-8")

    assert result["status"] == "pending_teacher_review"
    assert result["after_html"] is None
    assert len(state.pending_reviews()) == 1
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()
    assert [event["tool_name"] for event in state.tool_calls()] == [
        "get_competency_evidence", "flag_pattern_for_review"
    ]
    assert "EV-008" in html
    assert "Counter-evidence" in html
    assert "not authenticated" in html
    assert "no LLM inference is claimed" in html


@pytest.mark.parametrize(
    ("decision", "inputs", "status", "profile_count"),
    [
        ("approve", ["approve", "Supported with caution.", "REVIEW"],
         "approved_by_teacher", 1),
        ("edit", ["edit", "Revise for uncertainty.", "Still uncertain.", "REVIEW"],
         "edited_by_teacher", 1),
        ("reject", ["reject", "Counter-evidence is too strong.", "REVIEW"],
         "rejected_by_teacher", 0),
    ],
)
def test_review_decisions_are_audited_and_gated(
    tmp_path, decision, inputs, status, profile_count
) -> None:
    result = _run(tmp_path, *inputs)
    state = JsonStateStore(Path(result["state_path"]))
    html = Path(result["after_html"]).read_text(encoding="utf-8")

    assert result["status"] == status
    assert result["teacher_review_count"] == 1
    assert result["profile_update_count"] == profile_count
    assert state.pending_reviews() == ()
    assert len(state.teacher_reviews()) == 1
    assert len(state.profile_updates()) == profile_count
    assert state.teacher_reviews()[0]["decision"] == decision
    assert state.teacher_reviews()[0]["reviewer_id"] == (
        "simulated-teacher-not-authenticated"
    )
    assert state.tool_calls()[-1]["tool_name"] == "record_teacher_review"
    assert status in html
    assert "not authenticated" in html
    summary = json.loads(
        (Path(result["run_directory"]) / "result.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == status


def test_cancelled_review_does_not_update_profile(tmp_path) -> None:
    result = _run(tmp_path, "approve", "Looks promising.", "NO")
    state = JsonStateStore(Path(result["state_path"]))
    assert result["status"] == "pending_teacher_review"
    assert result["after_html"] is None
    assert len(state.pending_reviews()) == 1
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()
    assert len(state.tool_calls()) == 2


def test_missing_input_cancels_safely(tmp_path) -> None:
    result = _run(tmp_path)
    state = JsonStateStore(Path(result["state_path"]))
    assert result["status"] == "pending_teacher_review"
    assert state.teacher_reviews() == ()


def test_invalid_choice_and_blank_reason_are_reprompted(tmp_path) -> None:
    result = _run(tmp_path, "maybe", "edit", "", "Uncertainty remains.", "Reworded.", "REVIEW")
    state = JsonStateStore(Path(result["state_path"]))
    assert result["status"] == "edited_by_teacher"
    assert state.teacher_reviews()[0]["final_claim"] == "Reworded."


def test_teacher_wording_is_html_escaped(tmp_path) -> None:
    result = _run(
        tmp_path,
        "edit",
        "Reason <script>alert('unsafe')</script>",
        "Claim <img src=x onerror=alert(1)>",
        "REVIEW",
    )
    html = Path(result["after_html"]).read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<script>alert" not in html
    assert "<img src=x" not in html


def test_runs_are_isolated_in_fresh_state(tmp_path) -> None:
    first = _run(tmp_path, "reject", "Not enough evidence.", "REVIEW")
    second = _run(tmp_path, prepare_only=True)
    assert first["run_directory"] != second["run_directory"]
    assert len(JsonStateStore(Path(first["state_path"])).teacher_reviews()) == 1
    assert JsonStateStore(Path(second["state_path"])).teacher_reviews() == ()


def test_static_view_cannot_record_a_decision(tmp_path) -> None:
    result = _run(tmp_path, prepare_only=True)
    html = Path(result["before_html"]).read_text(encoding="utf-8")
    assert "<form" not in html
    assert "<script" not in html
    assert "http://" not in html
    assert "https://" not in html
    assert "static page" in html
