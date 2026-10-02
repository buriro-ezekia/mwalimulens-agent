"""Deterministic tests for bounded Qwen workflow-completion recovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.open_weights_run import (
    COMPLETION_RECOVERY_PROMPT,
    _should_attempt_completion_recovery,
    run_open_weights_task,
)
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"


class _FakeResult:
    def __init__(self, output: str, history: list[str]) -> None:
        self.output = output
        self._history = history

    def all_messages(self) -> list[str]:
        return list(self._history)


class _RecoveringAgent:
    def __init__(self, state_store: JsonStateStore, *, recover: bool) -> None:
        self.state_store = state_store
        self.recover = recover
        self.calls: list[dict] = []

    async def run(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})

        if len(self.calls) == 1:
            self.state_store.record_tool_call(
                {
                    "call_id": "call-evidence",
                    "tool_name": "get_competency_evidence",
                    "status": "success",
                    "timestamp": "2026-10-02T10:00:00+00:00",
                    "inputs": {
                        "learner_id": "L001",
                        "competency_code": "MATH-FRACTIONS",
                    },
                    "output": {"evidence_count": 8},
                    "error": None,
                }
            )
            return _FakeResult(
                "The evidence supports a cautious candidate. "
                "Would you like me to flag it for review?",
                ["initial-history"],
            )

        assert prompt == COMPLETION_RECOVERY_PROMPT
        assert kwargs["message_history"] == ["initial-history"]

        if self.recover:
            candidate = {
                "review_id": "review-recovered",
                "status": "pending_teacher_review",
                "learner_id": "L001",
                "competency_code": "MATH-FRACTIONS",
                "claim": (
                    "Fraction performance is repeatedly strong "
                    "with mixed explanation evidence."
                ),
                "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009"],
                "counter_evidence_ids": ["EV-008"],
                "uncertainty": "Independent explanation evidence is mixed.",
                "suggested_teacher_question": "Does this pattern hold in an unfamiliar problem?",
                "created_at": "2026-10-02T10:00:30+00:00",
            }
            self.state_store.record_pending_review_and_tool_call(
                candidate,
                {
                    "call_id": "call-flag",
                    "tool_name": "flag_pattern_for_review",
                    "status": "success",
                    "timestamp": "2026-10-02T10:00:30+00:00",
                    "inputs": {
                        "learner_id": "L001",
                        "competency_code": "MATH-FRACTIONS",
                    },
                    "output": candidate,
                    "error": None,
                },
            )
            return _FakeResult("Candidate submitted for teacher review.", ["recovery-history"])

        return _FakeResult(
            "ABSTAIN: I will not submit a candidate.",
            ["recovery-history"],
        )


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_recovery_is_needed_after_evidence_only(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    store.record_tool_call(
        {
            "tool_name": "get_competency_evidence",
            "status": "success",
        }
    )

    assert _should_attempt_completion_recovery(store) is True


def test_recovery_is_not_allowed_after_failed_tool_call(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    store.record_tool_call(
        {
            "tool_name": "get_competency_evidence",
            "status": "error",
        }
    )

    assert _should_attempt_completion_recovery(store) is False


def test_recovery_is_not_needed_after_candidate_submission(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    store.record_tool_call(
        {
            "tool_name": "get_competency_evidence",
            "status": "success",
        }
    )
    store.record_tool_call(
        {
            "tool_name": "flag_pattern_for_review",
            "status": "success",
        }
    )

    assert _should_attempt_completion_recovery(store) is False


def test_recovery_is_not_allowed_after_forbidden_human_action(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    store.record_tool_call(
        {
            "tool_name": "get_competency_evidence",
            "status": "success",
        }
    )
    store.record_tool_call(
        {
            "tool_name": "record_teacher_review",
            "status": "success",
        }
    )

    assert _should_attempt_completion_recovery(store) is False


@pytest.mark.anyio
async def test_bounded_recovery_can_complete_pending_review(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.json"
    fake_agent = _RecoveringAgent(JsonStateStore(state_path), recover=True)

    monkeypatch.setattr(
        "mwalimulens.agent.open_weights_run.build_ollama_agent",
        lambda **_kwargs: fake_agent,
    )

    report = await run_open_weights_task(
        settings=OllamaSettings(),
        data_dir=FIXTURE_DIR,
        state_path=state_path,
        report_path=tmp_path / "report.json",
    )

    assert report["status"] == "pass"
    assert report["initial_output"].endswith("flag it for review?")
    assert report["final_output"] == "Candidate submitted for teacher review."
    assert report["completion_recovery"]["attempted"] is True
    assert report["completion_recovery"]["succeeded"] is True
    assert report["completion_recovery"]["output"] == report["final_output"]
    assert len(fake_agent.calls) == 2
    assert report["pending_review_count"] == 1


@pytest.mark.anyio
async def test_bounded_recovery_still_fails_if_model_abstains(monkeypatch, tmp_path) -> None:
    state_path = tmp_path / "state.json"
    fake_agent = _RecoveringAgent(JsonStateStore(state_path), recover=False)

    monkeypatch.setattr(
        "mwalimulens.agent.open_weights_run.build_ollama_agent",
        lambda **_kwargs: fake_agent,
    )

    report = await run_open_weights_task(
        settings=OllamaSettings(),
        data_dir=FIXTURE_DIR,
        state_path=state_path,
        report_path=tmp_path / "report.json",
    )

    assert report["status"] == "fail"
    assert report["completion_recovery"]["attempted"] is True
    assert report["completion_recovery"]["succeeded"] is False
    assert report["final_output"].startswith("ABSTAIN:")
    assert report["checks"]["submitted_candidate"] is False
    assert len(fake_agent.calls) == 2
