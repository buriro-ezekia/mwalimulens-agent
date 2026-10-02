"""Atomic local state for MCP audit events and human review workflow."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStateStore:
    """Persist MCP workflow state in one atomic JSON document."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def tool_calls(self) -> tuple[dict[str, Any], ...]:
        """Return a snapshot of audited tool calls."""

        with self._lock:
            state = self._load()
            return tuple(dict(item) for item in state["tool_calls"])

    def review_candidates(self) -> tuple[dict[str, Any], ...]:
        """Return every candidate, including those already resolved by a teacher."""

        with self._lock:
            state = self._load()
            return tuple(dict(item) for item in state["pending_reviews"])

    def pending_reviews(self) -> tuple[dict[str, Any], ...]:
        """Return only candidates still awaiting teacher review."""

        return tuple(
            item
            for item in self.review_candidates()
            if item.get("status") == "pending_teacher_review"
        )

    def teacher_reviews(self) -> tuple[dict[str, Any], ...]:
        """Return recorded human review decisions."""

        with self._lock:
            state = self._load()
            return tuple(dict(item) for item in state["teacher_reviews"])

    def profile_updates(self) -> tuple[dict[str, Any], ...]:
        """Return profile updates created only through approved/edited reviews."""

        with self._lock:
            state = self._load()
            return tuple(dict(item) for item in state["profile_updates"])

    def review_candidate(self, review_id: str) -> dict[str, Any]:
        """Return one candidate by review ID."""

        with self._lock:
            state = self._load()
            for item in state["pending_reviews"]:
                if item.get("review_id") == review_id:
                    return dict(item)
        raise ValueError(f"unknown review_id: {review_id}")

    def record_tool_call(self, event: dict[str, Any]) -> None:
        """Append one tool-call audit event."""

        with self._lock:
            state = self._load()
            state["tool_calls"].append(event)
            self._write(state)

    def record_pending_review_and_tool_call(
        self,
        review: dict[str, Any],
        event: dict[str, Any],
    ) -> None:
        """Atomically persist a pending review and its successful action audit."""

        with self._lock:
            state = self._load()
            state["pending_reviews"].append(review)
            state["tool_calls"].append(event)
            self._write(state)

    def record_teacher_review_action(
        self,
        *,
        review_id: str,
        teacher_review: dict[str, Any],
        profile_update: dict[str, Any] | None,
        event: dict[str, Any],
    ) -> None:
        """Atomically resolve a candidate and persist the human-gated consequences."""

        with self._lock:
            state = self._load()

            candidate_index = next(
                (
                    index
                    for index, item in enumerate(state["pending_reviews"])
                    if item.get("review_id") == review_id
                ),
                None,
            )
            if candidate_index is None:
                raise ValueError(f"unknown review_id: {review_id}")

            candidate = state["pending_reviews"][candidate_index]
            if candidate.get("status") != "pending_teacher_review":
                raise ValueError(f"review_id already resolved: {review_id}")
            if any(
                item.get("review_id") == review_id for item in state["teacher_reviews"]
            ):
                raise ValueError(f"review_id already resolved: {review_id}")

            resolved_candidate = dict(candidate)
            resolved_candidate["status"] = (
                f"{teacher_review['decision']}_by_teacher"
            )
            resolved_candidate["resolved_at"] = teacher_review["reviewed_at"]
            resolved_candidate["teacher_review_id"] = teacher_review["teacher_review_id"]
            state["pending_reviews"][candidate_index] = resolved_candidate

            state["teacher_reviews"].append(teacher_review)
            if profile_update is not None:
                state["profile_updates"].append(profile_update)
            state["tool_calls"].append(event)
            self._write(state)

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return _empty_state()

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("MCP state must be a JSON object")

        state = _empty_state()
        for key in state:
            value = payload.get(key, [])
            if not isinstance(value, list):
                raise ValueError(f"MCP state field {key} must be a list")
            if not all(isinstance(item, dict) for item in value):
                raise ValueError(f"MCP state entries in {key} must be JSON objects")
            state[key] = [dict(item) for item in value]

        return state

    def _write(self, state: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _empty_state() -> dict[str, list[dict[str, Any]]]:
    return {
        "tool_calls": [],
        "pending_reviews": [],
        "teacher_reviews": [],
        "profile_updates": [],
    }
