"""Dataset loading and deterministic longitudinal retrieval."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mwalimulens.domain.evidence import EvidenceType, LearningEvidence
from mwalimulens.domain.learners import Learner


@dataclass(frozen=True, slots=True)
class LongitudinalDataset:
    """Validated learners and evidence with deterministic retrieval semantics."""

    learners: tuple[Learner, ...]
    evidence: tuple[LearningEvidence, ...]

    def __post_init__(self) -> None:
        learner_ids = [learner.learner_id for learner in self.learners]
        if len(learner_ids) != len(set(learner_ids)):
            raise ValueError("learner_id values must be unique")

        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")

        known_learners = set(learner_ids)
        unknown = sorted(
            {item.learner_id for item in self.evidence if item.learner_id not in known_learners}
        )
        if unknown:
            raise ValueError(f"evidence references unknown learners: {unknown}")

    def learner(self, learner_id: str) -> Learner:
        """Return one learner or fail explicitly when the identifier is unknown."""

        for learner in self.learners:
            if learner.learner_id == learner_id:
                return learner
        raise KeyError(f"unknown learner_id: {learner_id}")

    def timeline(self, learner_id: str) -> tuple[LearningEvidence, ...]:
        """Return evidence in event chronology, not data-entry chronology."""

        self.learner(learner_id)
        items = (item for item in self.evidence if item.learner_id == learner_id)
        return tuple(sorted(items, key=_chronology_key))

    def competency_evidence(
        self,
        learner_id: str,
        competency_code: str,
    ) -> tuple[LearningEvidence, ...]:
        """Return chronologically ordered evidence for one learner competency."""

        if not isinstance(competency_code, str) or not competency_code.strip():
            raise ValueError("competency_code must be a non-empty string")
        return tuple(
            item
            for item in self.timeline(learner_id)
            if item.competency_code == competency_code
        )


def load_synthetic_dataset(directory: Path) -> LongitudinalDataset:
    """Load and validate the committed challenge fixtures."""

    learners_raw = _read_json_list(directory / "learners.json")
    evidence_raw = _read_json_list(directory / "learning_evidence.json")

    learners = tuple(Learner(**row) for row in learners_raw)
    if any(not learner.synthetic for learner in learners):
        raise ValueError("challenge fixture dataset must contain synthetic learners only")

    evidence = tuple(_parse_evidence(row) for row in evidence_raw)
    return LongitudinalDataset(learners=learners, evidence=evidence)


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path.name} must contain a JSON list")
    if not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"{path.name} must contain JSON objects")
    return payload


def _parse_evidence(row: dict[str, Any]) -> LearningEvidence:
    payload = dict(row)
    payload["evidence_type"] = EvidenceType(payload["evidence_type"])
    payload["occurred_at"] = _parse_datetime(payload["occurred_at"], "occurred_at")
    payload["recorded_at"] = _parse_datetime(payload["recorded_at"], "recorded_at")
    return LearningEvidence(**payload)


def _parse_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO-8601 datetime") from exc


def _chronology_key(item: LearningEvidence) -> tuple[datetime, datetime, str]:
    return item.occurred_at, item.recorded_at, item.evidence_id
