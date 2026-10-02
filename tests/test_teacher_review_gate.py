"""Tests for the explicit human teacher review gate."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"
FIXED_TIME = datetime.fromisoformat("2026-10-02T11:00:00+03:00")


def _service(tmp_path):
    counter = {"value": 0}

    def id_factory(prefix: str) -> str:
        counter["value"] += 1
        return f"{prefix}-gate-{counter['value']}"

    return EducationToolService(
        load_synthetic_dataset(FIXTURE_DIR),
        JsonStateStore(tmp_path / "state.json"),
        clock=lambda: FIXED_TIME,
        id_factory=id_factory,
    )


def _candidate(service: EducationToolService) -> dict:
    return service.flag_pattern_for_review(
        learner_id="L001",
        competency_code="MATH-FRACTIONS",
        claim="Fraction-equivalence performance is repeatedly strong across terms.",
        supporting_evidence_ids=["EV-004", "EV-007", "EV-009"],
        counter_evidence_ids=["EV-008"],
        uncertainty="Open-ended explanation evidence is mixed.",
        suggested_teacher_question="Does this also appear in an unfamiliar problem?",
    )


def test_approve_records_named_teacher_and_creates_profile_update(tmp_path) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)

    result = service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id="teacher-001",
        decision="approve",
        reason="The evidence is sufficient for a provisional learner-profile note.",
    )

    teacher_review = result["teacher_review"]
    profile_update = result["profile_update"]

    assert teacher_review["reviewer_id"] == "teacher-001"
    assert teacher_review["decision"] == "approve"
    assert teacher_review["original_claim"] == candidate["claim"]
    assert teacher_review["final_claim"] == candidate["claim"]

    assert profile_update is not None
    assert profile_update["claim"] == candidate["claim"]
    assert profile_update["reviewer_id"] == "teacher-001"
    assert profile_update["supporting_evidence_ids"] == ["EV-004", "EV-007", "EV-009"]
    assert profile_update["counter_evidence_ids"] == ["EV-008"]

    assert service.state_store.pending_reviews() == ()
    resolved = service.state_store.review_candidates()[0]
    assert resolved["status"] == "approved_by_teacher"
    assert len(service.state_store.teacher_reviews()) == 1
    assert len(service.state_store.profile_updates()) == 1


def test_edit_requires_and_persists_teacher_edited_claim(tmp_path) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)
    edited = (
        "Fraction-equivalence evidence is promising across terms, "
        "but explanation evidence remains mixed."
    )

    result = service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id="teacher-002",
        decision="edit",
        reason="The original claim was too strong given the open-ended observation.",
        edited_claim=edited,
    )

    teacher_review = result["teacher_review"]
    profile_update = result["profile_update"]

    assert teacher_review["decision"] == "edit"
    assert teacher_review["original_claim"] == candidate["claim"]
    assert teacher_review["final_claim"] == edited
    assert profile_update is not None
    assert profile_update["claim"] == edited
    assert service.state_store.review_candidates()[0]["status"] == "edited_by_teacher"


def test_reject_records_decision_without_profile_update(tmp_path) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)

    result = service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id="teacher-003",
        decision="reject",
        reason="The counter-evidence makes the pattern too uncertain for profile use.",
    )

    assert result["teacher_review"]["decision"] == "reject"
    assert result["teacher_review"]["final_claim"] is None
    assert result["profile_update"] is None
    assert service.state_store.profile_updates() == ()
    assert service.state_store.review_candidates()[0]["status"] == "rejected_by_teacher"


def test_edit_without_edited_claim_is_rejected_and_audited(tmp_path) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)

    with pytest.raises(ValueError, match="edited_claim must be a non-empty string"):
        service.record_teacher_review(
            review_id=candidate["review_id"],
            reviewer_id="teacher-004",
            decision="edit",
            reason="Teacher wants to revise the wording.",
        )

    assert len(service.state_store.pending_reviews()) == 1
    assert service.state_store.teacher_reviews() == ()
    assert service.state_store.profile_updates() == ()
    assert service.state_store.tool_calls()[-1]["status"] == "error"


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_edited_claim_is_forbidden_outside_edit(decision, tmp_path) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)

    with pytest.raises(ValueError, match="only allowed when decision is edit"):
        service.record_teacher_review(
            review_id=candidate["review_id"],
            reviewer_id="teacher-005",
            decision=decision,
            reason="Decision rationale.",
            edited_claim="This should not be accepted.",
        )

    assert service.state_store.profile_updates() == ()


def test_duplicate_teacher_review_is_blocked_and_audited(tmp_path) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)

    service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id="teacher-006",
        decision="approve",
        reason="Approved after checking the cited evidence.",
    )

    with pytest.raises(ValueError, match="already resolved"):
        service.record_teacher_review(
            review_id=candidate["review_id"],
            reviewer_id="teacher-007",
            decision="reject",
            reason="A second decision must not overwrite the first.",
        )

    assert len(service.state_store.teacher_reviews()) == 1
    assert len(service.state_store.profile_updates()) == 1
    assert service.state_store.tool_calls()[-1]["status"] == "error"


def test_unknown_review_id_fails_without_profile_update(tmp_path) -> None:
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="unknown review_id"):
        service.record_teacher_review(
            review_id="review-missing",
            reviewer_id="teacher-008",
            decision="approve",
            reason="Should not be accepted.",
        )

    assert service.state_store.teacher_reviews() == ()
    assert service.state_store.profile_updates() == ()
    assert service.state_store.tool_calls()[-1]["status"] == "error"


@pytest.mark.parametrize(
    ("reviewer_id", "reason", "message"),
    [
        ("", "Reason supplied.", "reviewer_id must be a non-empty string"),
        ("teacher-009", "", "reason must be a non-empty string"),
    ],
)
def test_reviewer_identity_and_reason_are_mandatory(
    reviewer_id,
    reason,
    message,
    tmp_path,
) -> None:
    service = _service(tmp_path)
    candidate = _candidate(service)

    with pytest.raises(ValueError, match=message):
        service.record_teacher_review(
            review_id=candidate["review_id"],
            reviewer_id=reviewer_id,
            decision="approve",
            reason=reason,
        )

    assert service.state_store.profile_updates() == ()


def test_old_runtime_state_is_backward_compatible(tmp_path) -> None:
    path = tmp_path / "legacy-state.json"
    path.write_text(
        json.dumps(
            {
                "tool_calls": [],
                "pending_reviews": [
                    {
                        "review_id": "review-legacy",
                        "status": "pending_teacher_review",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    store = JsonStateStore(path)

    assert store.pending_reviews()[0]["review_id"] == "review-legacy"
    assert store.teacher_reviews() == ()
    assert store.profile_updates() == ()
