"""Audited application service exposed by the Education MCP server."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from mwalimulens.domain import LearningEvidence, LongitudinalDataset
from mwalimulens.mcp_server.state import JsonStateStore

Clock = Callable[[], datetime]
IdFactory = Callable[[str], str]
REVIEW_DECISIONS = frozenset({"approve", "edit", "reject"})


class EducationToolService:
    """Deterministic evidence tools plus human-bounded workflow actions."""

    def __init__(
        self,
        dataset: LongitudinalDataset,
        state_store: JsonStateStore,
        *,
        clock: Clock | None = None,
        id_factory: IdFactory | None = None,
    ) -> None:
        self.dataset = dataset
        self.state_store = state_store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid4()}")

    def get_learner_timeline(self, learner_id: str) -> dict[str, Any]:
        """Return one learner's evidence ordered by when each event occurred."""

        inputs = {"learner_id": learner_id}
        try:
            learner = self.dataset.learner(learner_id)
            evidence = self.dataset.timeline(learner_id)
            output = {
                "learner": {
                    "learner_id": learner.learner_id,
                    "display_name": learner.display_name,
                    "year_group": learner.year_group,
                    "school_context": learner.school_context,
                    "synthetic": learner.synthetic,
                },
                "evidence_count": len(evidence),
                "evidence": [_evidence_payload(item) for item in evidence],
            }
        except Exception as exc:
            self._audit_error("get_learner_timeline", inputs, exc)
            raise

        self._audit_success("get_learner_timeline", inputs, output)
        return output

    def get_competency_evidence(
        self,
        learner_id: str,
        competency_code: str,
    ) -> dict[str, Any]:
        """Return evidence for one learner and competency in event chronology."""

        inputs = {"learner_id": learner_id, "competency_code": competency_code}
        try:
            evidence = self.dataset.competency_evidence(learner_id, competency_code)
            output = {
                "learner_id": learner_id,
                "competency_code": competency_code,
                "evidence_count": len(evidence),
                "evidence": [_evidence_payload(item) for item in evidence],
            }
        except Exception as exc:
            self._audit_error("get_competency_evidence", inputs, exc)
            raise

        self._audit_success("get_competency_evidence", inputs, output)
        return output

    def flag_pattern_for_review(
        self,
        learner_id: str,
        competency_code: str,
        claim: str,
        supporting_evidence_ids: list[str],
        counter_evidence_ids: list[str],
        uncertainty: str,
        suggested_teacher_question: str,
    ) -> dict[str, Any]:
        """Create a pending teacher-review record without changing a learner profile."""

        inputs = {
            "learner_id": learner_id,
            "competency_code": competency_code,
            "claim": claim,
            "supporting_evidence_ids": supporting_evidence_ids,
            "counter_evidence_ids": counter_evidence_ids,
            "uncertainty": uncertainty,
            "suggested_teacher_question": suggested_teacher_question,
        }

        try:
            self.dataset.learner(learner_id)
            competency_code = _require_text(competency_code, "competency_code")
            claim = _require_text(claim, "claim")
            uncertainty = _require_text(uncertainty, "uncertainty")
            suggested_teacher_question = _require_text(
                suggested_teacher_question,
                "suggested_teacher_question",
            )
            supporting = _normalise_evidence_ids(
                supporting_evidence_ids,
                "supporting_evidence_ids",
                require_one=True,
            )
            counter = _normalise_evidence_ids(
                counter_evidence_ids,
                "counter_evidence_ids",
                require_one=False,
            )
            overlap = sorted(set(supporting).intersection(counter))
            if overlap:
                raise ValueError(
                    "supporting and counter evidence must not overlap: "
                    + ", ".join(overlap)
                )

            self._validate_candidate_evidence(
                learner_id=learner_id,
                competency_code=competency_code,
                evidence_ids=(*supporting, *counter),
            )

            created_at = self._timestamp()
            review = {
                "review_id": self._id_factory("review"),
                "status": "pending_teacher_review",
                "learner_id": learner_id,
                "competency_code": competency_code,
                "claim": claim,
                "supporting_evidence_ids": list(supporting),
                "counter_evidence_ids": list(counter),
                "uncertainty": uncertainty,
                "suggested_teacher_question": suggested_teacher_question,
                "created_at": created_at,
            }
            event = self._success_event(
                tool_name="flag_pattern_for_review",
                inputs=inputs,
                output=review,
                timestamp=created_at,
            )
            self.state_store.record_pending_review_and_tool_call(review, event)
        except Exception as exc:
            self._audit_error("flag_pattern_for_review", inputs, exc)
            raise

        return review

    def record_teacher_review(
        self,
        review_id: str,
        reviewer_id: str,
        decision: str,
        reason: str,
        edited_claim: str | None = None,
    ) -> dict[str, Any]:
        """Resolve one pending candidate through an explicit named teacher decision."""

        inputs = {
            "review_id": review_id,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "reason": reason,
            "edited_claim": edited_claim,
        }

        try:
            review_id = _require_text(review_id, "review_id")
            reviewer_id = _require_text(reviewer_id, "reviewer_id")
            reason = _require_text(reason, "reason")
            decision = _normalise_decision(decision)
            candidate = self.state_store.review_candidate(review_id)

            if candidate.get("status") != "pending_teacher_review":
                raise ValueError(f"review_id already resolved: {review_id}")

            original_claim = _require_text(candidate.get("claim"), "candidate claim")
            final_claim = _resolve_final_claim(
                decision=decision,
                original_claim=original_claim,
                edited_claim=edited_claim,
            )

            reviewed_at = self._timestamp()
            teacher_review = {
                "teacher_review_id": self._id_factory("teacher-review"),
                "review_id": review_id,
                "reviewer_id": reviewer_id,
                "decision": decision,
                "reason": reason,
                "original_claim": original_claim,
                "final_claim": final_claim,
                "learner_id": candidate["learner_id"],
                "competency_code": candidate["competency_code"],
                "supporting_evidence_ids": list(candidate["supporting_evidence_ids"]),
                "counter_evidence_ids": list(candidate["counter_evidence_ids"]),
                "reviewed_at": reviewed_at,
            }

            profile_update = None
            if decision in {"approve", "edit"}:
                profile_update = {
                    "profile_update_id": self._id_factory("profile-update"),
                    "teacher_review_id": teacher_review["teacher_review_id"],
                    "review_id": review_id,
                    "learner_id": candidate["learner_id"],
                    "competency_code": candidate["competency_code"],
                    "claim": final_claim,
                    "supporting_evidence_ids": list(
                        candidate["supporting_evidence_ids"]
                    ),
                    "counter_evidence_ids": list(candidate["counter_evidence_ids"]),
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "recorded_at": reviewed_at,
                }

            output = {
                "teacher_review": teacher_review,
                "profile_update": profile_update,
            }
            event = self._success_event(
                tool_name="record_teacher_review",
                inputs=inputs,
                output=output,
                timestamp=reviewed_at,
            )
            self.state_store.record_teacher_review_action(
                review_id=review_id,
                teacher_review=teacher_review,
                profile_update=profile_update,
                event=event,
            )
        except Exception as exc:
            self._audit_error("record_teacher_review", inputs, exc)
            raise

        return output

    def _validate_candidate_evidence(
        self,
        *,
        learner_id: str,
        competency_code: str,
        evidence_ids: tuple[str, ...],
    ) -> None:
        by_id = {item.evidence_id: item for item in self.dataset.evidence}
        for evidence_id in evidence_ids:
            item = by_id.get(evidence_id)
            if item is None:
                raise ValueError(f"unknown evidence_id: {evidence_id}")
            if item.learner_id != learner_id:
                raise ValueError(
                    f"evidence {evidence_id} belongs to learner {item.learner_id}, "
                    f"not {learner_id}"
                )
            if item.competency_code != competency_code:
                raise ValueError(
                    f"evidence {evidence_id} has competency {item.competency_code}, "
                    f"not {competency_code}"
                )

    def _audit_success(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
    ) -> None:
        self.state_store.record_tool_call(
            self._success_event(
                tool_name=tool_name,
                inputs=inputs,
                output=output,
                timestamp=self._timestamp(),
            )
        )

    def _success_event(
        self,
        *,
        tool_name: str,
        inputs: dict[str, Any],
        output: dict[str, Any],
        timestamp: str,
    ) -> dict[str, Any]:
        return {
            "call_id": self._id_factory("call"),
            "tool_name": tool_name,
            "status": "success",
            "timestamp": timestamp,
            "inputs": inputs,
            "output": output,
            "error": None,
        }

    def _audit_error(
        self,
        tool_name: str,
        inputs: dict[str, Any],
        exc: Exception,
    ) -> None:
        event = {
            "call_id": self._id_factory("call"),
            "tool_name": tool_name,
            "status": "error",
            "timestamp": self._timestamp(),
            "inputs": inputs,
            "output": None,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        self.state_store.record_tool_call(event)

    def _timestamp(self) -> str:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("MCP audit clock must return a timezone-aware datetime")
        return value.isoformat()


def _evidence_payload(item: LearningEvidence) -> dict[str, Any]:
    return {
        "evidence_id": item.evidence_id,
        "learner_id": item.learner_id,
        "term_id": item.term_id,
        "subject": item.subject,
        "competency_code": item.competency_code,
        "evidence_type": item.evidence_type.value,
        "occurred_at": item.occurred_at.isoformat(),
        "recorded_at": item.recorded_at.isoformat(),
        "source_ref": item.source_ref,
        "score": item.score,
        "observation": item.observation,
    }


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _normalise_decision(value: str) -> str:
    decision = _require_text(value, "decision").lower()
    if decision not in REVIEW_DECISIONS:
        raise ValueError("decision must be one of: approve, edit, reject")
    return decision


def _resolve_final_claim(
    *,
    decision: str,
    original_claim: str,
    edited_claim: str | None,
) -> str | None:
    if decision == "edit":
        return _require_text(edited_claim, "edited_claim")
    if edited_claim is not None:
        raise ValueError("edited_claim is only allowed when decision is edit")
    if decision == "approve":
        return original_claim
    return None


def _normalise_evidence_ids(
    values: list[str],
    field_name: str,
    *,
    require_one: bool,
) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise TypeError(f"{field_name} must be a list")

    normalised = tuple(_require_text(value, field_name) for value in values)
    if require_one and not normalised:
        raise ValueError(f"{field_name} must contain at least one evidence ID")
    if len(normalised) != len(set(normalised)):
        raise ValueError(f"{field_name} must not contain duplicate evidence IDs")
    return normalised
