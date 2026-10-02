"""Longitudinal learning evidence primitives."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class EvidenceType(StrEnum):
    """Supported evidence categories in the challenge domain."""

    ASSESSMENT = "assessment"
    OBSERVATION = "observation"
    PRACTICAL_TASK = "practical_task"
    ATTENDANCE = "attendance"


@dataclass(frozen=True, slots=True)
class LearningEvidence:
    """One immutable item of evidence about a learner at a point in time.

    occurred_at records when the learning event happened.
    recorded_at records when the institution entered it. Keeping both allows the
    dataset to represent late-entered results without rewriting chronology.
    """

    evidence_id: str
    learner_id: str
    term_id: str
    subject: str
    competency_code: str
    evidence_type: EvidenceType
    occurred_at: datetime
    recorded_at: datetime
    source_ref: str
    score: float | None = None
    observation: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "evidence_id",
            "learner_id",
            "term_id",
            "subject",
            "competency_code",
            "source_ref",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")

        if not isinstance(self.evidence_type, EvidenceType):
            raise TypeError("evidence_type must be an EvidenceType")

        for field_name in ("occurred_at", "recorded_at"):
            value = getattr(self, field_name)
            if not isinstance(value, datetime):
                raise TypeError(f"{field_name} must be a datetime")
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")

        if self.recorded_at < self.occurred_at:
            raise ValueError("recorded_at cannot be earlier than occurred_at")

        if self.score is not None:
            if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
                raise TypeError("score must be numeric when supplied")
            if not 0.0 <= float(self.score) <= 1.0:
                raise ValueError("score must be between 0.0 and 1.0")

        if self.observation is not None:
            if not isinstance(self.observation, str) or not self.observation.strip():
                raise ValueError("observation must be non-empty when supplied")

        if self.score is None and self.observation is None:
            raise ValueError("evidence must contain a score, an observation, or both")

    @property
    def recording_delay(self) -> timedelta:
        """Elapsed time between the event and institutional record entry."""

        return self.recorded_at - self.occurred_at
