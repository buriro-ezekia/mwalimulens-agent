"""Tests for the fast judge-facing demo."""

from __future__ import annotations

from pathlib import Path

from mwalimulens.demo_run import (
    DEMO_CLAIM,
    build_demo_report,
    render_demo_html,
)
from mwalimulens.mcp_server.state import JsonStateStore


def _state(path: Path, *, claim: str = DEMO_CLAIM) -> JsonStateStore:
    store = JsonStateStore(path)
    store.record_tool_call(
        {
            "call_id": "call-1",
            "tool_name": "get_competency_evidence",
            "status": "success",
            "timestamp": "2026-10-04T08:00:00+00:00",
            "inputs": {
                "learner_id": "L001",
                "competency_code": "MATH-FRACTIONS",
            },
            "output": {"evidence_count": 1},
            "error": None,
        }
    )
    store.record_tool_call(
        {
            "call_id": "borrowed-1",
            "toolset_id": "borrowed-official-filesystem-mcp",
            "source": "borrowed_mcp",
            "tool_name": "read_text_file",
            "status": "success",
            "timestamp": "2026-10-04T08:00:01+00:00",
            "inputs": {"path": "reference.md"},
            "output": {"content": "not learner evidence"},
            "error": None,
        }
    )
    candidate = {
        "review_id": "review-demo",
        "status": "pending_teacher_review",
        "learner_id": "L001",
        "competency_code": "MATH-FRACTIONS",
        "claim": claim,
        "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009", "EV-011"],
        "counter_evidence_ids": ["EV-008"],
        "uncertainty": "Mixed explanation evidence.",
        "suggested_teacher_question": "Does this hold in unfamiliar work?",
        "created_at": "2026-10-04T08:00:02+00:00",
    }
    store.record_pending_review_and_tool_call(
        candidate,
        {
            "call_id": "call-2",
            "tool_name": "flag_pattern_for_review",
            "status": "success",
            "timestamp": "2026-10-04T08:00:02+00:00",
            "inputs": {},
            "output": candidate,
            "error": None,
        },
    )
    return store


def test_demo_report_preserves_human_gate(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    _state(state_path)

    report = build_demo_report(
        state_path=state_path,
        visible_tools=[
            {
                "get_learner_timeline",
                "get_competency_evidence",
                "flag_pattern_for_review",
                "read_text_file",
                "read_multiple_files",
                "list_directory",
                "search_files",
                "get_file_info",
                "list_allowed_directories",
            }
        ],
        final_output="Candidate prepared for human teacher review.",
        error=None,
    )

    assert report["status"] == "pass"
    assert report["pending_review_count"] == 1
    assert report["teacher_review_count"] == 0
    assert report["profile_update_count"] == 0
    assert all(report["checks"].values())


def test_demo_report_rejects_human_review_tool_visibility(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    _state(state_path)

    report = build_demo_report(
        state_path=state_path,
        visible_tools=[
            {
                "get_learner_timeline",
                "get_competency_evidence",
                "flag_pattern_for_review",
                "record_teacher_review",
                "read_text_file",
                "read_multiple_files",
                "list_directory",
                "search_files",
                "get_file_info",
                "list_allowed_directories",
            }
        ],
        final_output="Candidate prepared for human teacher review.",
        error=None,
    )

    assert report["status"] == "fail"
    assert report["checks"]["model_tool_surface_safe"] is False


def test_demo_html_is_self_contained_and_escapes_candidate(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    _state(
        state_path,
        claim="<script>alert('x')</script>",
    )

    report = build_demo_report(
        state_path=state_path,
        visible_tools=[
            {
                "get_learner_timeline",
                "get_competency_evidence",
                "flag_pattern_for_review",
                "read_text_file",
                "read_multiple_files",
                "list_directory",
                "search_files",
                "get_file_info",
                "list_allowed_directories",
            }
        ],
        final_output="Candidate prepared for human teacher review.",
        error=None,
    )
    html = render_demo_html(report)

    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
    assert "https://" not in html
    assert "Human decision gate" in html
