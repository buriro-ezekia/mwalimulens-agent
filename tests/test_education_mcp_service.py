"""Service and persistence tests for the custom Education MCP tools."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"
FIXED_TIME = datetime.fromisoformat("2026-10-02T10:00:00+03:00")


def _service(tmp_path):
    counter = {"value": 0}

    def id_factory(prefix: str) -> str:
        counter["value"] += 1
        return f"{prefix}-test-{counter['value']}"

    return EducationToolService(
        load_synthetic_dataset(FIXTURE_DIR),
        JsonStateStore(tmp_path / "state.json"),
        clock=lambda: FIXED_TIME,
        id_factory=id_factory,
    )


def test_timeline_read_is_structured_and_audited(tmp_path) -> None:
    service = _service(tmp_path)

    result = service.get_learner_timeline("L001")

    assert result["learner"]["learner_id"] == "L001"
    assert result["evidence_count"] == 11
    assert result["evidence"][0]["evidence_id"] == "EV-001"
    assert result["evidence"][-1]["evidence_id"] == "EV-011"

    calls = service.state_store.tool_calls()
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "get_learner_timeline"
    assert calls[0]["status"] == "success"
    assert calls[0]["timestamp"] == FIXED_TIME.isoformat()


def test_failed_read_is_also_audited(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(KeyError, match="unknown learner_id"):
        service.get_learner_timeline("L999")

    calls = service.state_store.tool_calls()
    assert len(calls) == 1
    assert calls[0]["status"] == "error"
    assert calls[0]["error"]["type"] == "KeyError"
    assert calls[0]["output"] is None


def test_competency_read_preserves_source_evidence(tmp_path) -> None:
    service = _service(tmp_path)

    result = service.get_competency_evidence("L001", "MATH-FRACTIONS")

    assert result["evidence_count"] == 8
    assert {item["evidence_id"] for item in result["evidence"]} == {
        "EV-001",
        "EV-002",
        "EV-004",
        "EV-005",
        "EV-007",
        "EV-008",
        "EV-009",
        "EV-011",
    }


def test_flag_pattern_creates_pending_review_and_action_audit(tmp_path) -> None:
    service = _service(tmp_path)

    result = service.flag_pattern_for_review(
        learner_id="L001",
        competency_code="MATH-FRACTIONS",
        claim="Fraction-equivalence performance is repeatedly strong across terms.",
        supporting_evidence_ids=["EV-004", "EV-007", "EV-009"],
        counter_evidence_ids=["EV-008"],
        uncertainty="Open-ended explanation evidence is mixed.",
        suggested_teacher_question=(
            "Does this pattern also appear when the learner explains an unfamiliar problem?"
        ),
    )

    assert result["status"] == "pending_teacher_review"
    assert result["review_id"].startswith("review-test-")

    reviews = service.state_store.pending_reviews()
    calls = service.state_store.tool_calls()
    assert len(reviews) == 1
    assert reviews[0] == result
    assert len(calls) == 1
    assert calls[0]["tool_name"] == "flag_pattern_for_review"
    assert calls[0]["output"] == result


def test_flag_rejects_unknown_evidence_without_creating_review(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="unknown evidence_id"):
        service.flag_pattern_for_review(
            learner_id="L001",
            competency_code="MATH-FRACTIONS",
            claim="Candidate claim",
            supporting_evidence_ids=["EV-999"],
            counter_evidence_ids=[],
            uncertainty="Uncertain.",
            suggested_teacher_question="What should the teacher verify?",
        )

    assert service.state_store.pending_reviews() == ()
    calls = service.state_store.tool_calls()
    assert len(calls) == 1
    assert calls[0]["status"] == "error"


def test_flag_rejects_other_learners_evidence(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="belongs to learner L002"):
        service.flag_pattern_for_review(
            learner_id="L001",
            competency_code="SCI-DATA",
            claim="Candidate claim",
            supporting_evidence_ids=["EV-012"],
            counter_evidence_ids=[],
            uncertainty="Uncertain.",
            suggested_teacher_question="What should the teacher verify?",
        )


def test_flag_rejects_mismatched_competency(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="has competency MATH-MEASUREMENT"):
        service.flag_pattern_for_review(
            learner_id="L001",
            competency_code="MATH-FRACTIONS",
            claim="Candidate claim",
            supporting_evidence_ids=["EV-010"],
            counter_evidence_ids=[],
            uncertainty="Uncertain.",
            suggested_teacher_question="What should the teacher verify?",
        )


def test_flag_rejects_overlapping_support_and_counter_evidence(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="must not overlap"):
        service.flag_pattern_for_review(
            learner_id="L001",
            competency_code="MATH-FRACTIONS",
            claim="Candidate claim",
            supporting_evidence_ids=["EV-004"],
            counter_evidence_ids=["EV-004"],
            uncertainty="Uncertain.",
            suggested_teacher_question="What should the teacher verify?",
        )
