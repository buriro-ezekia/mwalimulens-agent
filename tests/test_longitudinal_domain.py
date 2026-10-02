"""Tests for the evidence-first longitudinal domain."""

from datetime import datetime
from pathlib import Path

import pytest

from mwalimulens.domain import EvidenceType, LearningEvidence, load_synthetic_dataset

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"


@pytest.fixture(scope="module")
def dataset():
    return load_synthetic_dataset(FIXTURE_DIR)


def test_synthetic_fixture_loads_with_unique_ids(dataset) -> None:
    assert len(dataset.learners) == 3
    assert len(dataset.evidence) == 15
    assert len({item.evidence_id for item in dataset.evidence}) == len(dataset.evidence)
    assert all(learner.synthetic for learner in dataset.learners)


def test_timeline_uses_event_chronology_not_record_entry_order(dataset) -> None:
    timeline = dataset.timeline("L001")
    occurred = [item.occurred_at for item in timeline]
    assert occurred == sorted(occurred)

    late = next(item for item in timeline if item.evidence_id == "EV-007")
    conflicting = next(item for item in timeline if item.evidence_id == "EV-008")
    assert late.occurred_at < conflicting.occurred_at
    assert late.recorded_at > conflicting.recorded_at


def test_late_entry_provenance_is_preserved(dataset) -> None:
    item = next(item for item in dataset.evidence if item.evidence_id == "EV-007")
    assert item.recording_delay.days == 26
    assert item.term_id == "2025-T3"


def test_conflicting_quantitative_and_qualitative_evidence_is_preserved(dataset) -> None:
    items = dataset.competency_evidence("L001", "MATH-FRACTIONS")
    high_assessment = next(item for item in items if item.evidence_id == "EV-007")
    counter_observation = next(item for item in items if item.evidence_id == "EV-008")

    assert high_assessment.score == 0.84
    assert counter_observation.evidence_type is EvidenceType.OBSERVATION
    assert counter_observation.observation is not None
    assert "Struggled" in counter_observation.observation


def test_missing_term_gap_is_not_filled_in(dataset) -> None:
    terms = {item.term_id for item in dataset.competency_evidence("L002", "SCI-DATA")}
    assert "2025-T1" in terms
    assert "2025-T2" not in terms
    assert "2025-T3" in terms


def test_single_high_score_remains_insufficient_history_fixture(dataset) -> None:
    items = dataset.competency_evidence("L003", "ENG-INFERENCE")
    assert len(items) == 1
    assert items[0].score == 0.91
    assert items[0].observation is None


def test_fixture_does_not_prelabel_cases_the_agent_must_infer(dataset) -> None:
    by_id = {item.evidence_id: item for item in dataset.evidence}
    assert by_id["EV-010"].observation is None
    assert by_id["EV-013"].observation is None
    assert by_id["EV-015"].observation is None


def test_missing_attendance_remains_an_absence_not_a_fabricated_record(dataset) -> None:
    terms = {item.term_id for item in dataset.competency_evidence("L001", "ATTENDANCE")}
    assert terms == {"2025-T1", "2025-T2"}


def test_unknown_learner_fails_explicitly(dataset) -> None:
    with pytest.raises(KeyError, match="unknown learner_id"):
        dataset.timeline("L999")


def test_invalid_score_is_rejected() -> None:
    with pytest.raises(ValueError, match="score must be between"):
        LearningEvidence(
            evidence_id="EV-X",
            learner_id="L001",
            term_id="2026-T1",
            subject="Mathematics",
            competency_code="MATH-TEST",
            evidence_type=EvidenceType.ASSESSMENT,
            occurred_at=datetime.fromisoformat("2026-03-01T10:00:00+03:00"),
            recorded_at=datetime.fromisoformat("2026-03-01T11:00:00+03:00"),
            source_ref="synthetic://test/invalid-score",
            score=1.2,
        )


def test_empty_evidence_payload_is_rejected() -> None:
    with pytest.raises(ValueError, match="score, an observation, or both"):
        LearningEvidence(
            evidence_id="EV-X",
            learner_id="L001",
            term_id="2026-T1",
            subject="Mathematics",
            competency_code="MATH-TEST",
            evidence_type=EvidenceType.OBSERVATION,
            occurred_at=datetime.fromisoformat("2026-03-01T10:00:00+03:00"),
            recorded_at=datetime.fromisoformat("2026-03-01T11:00:00+03:00"),
            source_ref="synthetic://test/empty",
        )


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        LearningEvidence(
            evidence_id="EV-X",
            learner_id="L001",
            term_id="2026-T1",
            subject="Mathematics",
            competency_code="MATH-TEST",
            evidence_type=EvidenceType.ASSESSMENT,
            occurred_at=datetime.fromisoformat("2026-03-01T10:00:00"),
            recorded_at=datetime.fromisoformat("2026-03-01T11:00:00+03:00"),
            source_ref="synthetic://test/naive-time",
            score=0.5,
        )
