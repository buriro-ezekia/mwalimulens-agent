"""Atomic local state for MCP audit events and pending teacher review."""

from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Any


class JsonStateStore:
    """Persist tool audit events and pending reviews in one atomic JSON document."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def tool_calls(self) -> tuple[dict[str, Any], ...]:
        """Return a snapshot of audited tool calls."""

        with self._lock:
            state = self._load()
            return tuple(dict(item) for item in state["tool_calls"])

    def pending_reviews(self) -> tuple[dict[str, Any], ...]:
        """Return a snapshot of pending teacher-review records."""

        with self._lock:
            state = self._load()
            return tuple(dict(item) for item in state["pending_reviews"])

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

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if not self.path.exists():
            return {"tool_calls": [], "pending_reviews": []}

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("MCP state must be a JSON object")

        tool_calls = payload.get("tool_calls")
        pending_reviews = payload.get("pending_reviews")
        if not isinstance(tool_calls, list) or not isinstance(pending_reviews, list):
            raise ValueError("MCP state must contain tool_calls and pending_reviews lists")
        if not all(isinstance(item, dict) for item in (*tool_calls, *pending_reviews)):
            raise ValueError("MCP state entries must be JSON objects")

        return {
            "tool_calls": [dict(item) for item in tool_calls],
            "pending_reviews": [dict(item) for item in pending_reviews],
        }

    def _write(self, state: dict[str, list[dict[str, Any]]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
