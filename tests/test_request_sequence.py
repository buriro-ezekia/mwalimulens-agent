"""Request audit checkpoints and prompt comparison must not weaken review gates."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic_ai.models.ollama import OllamaModel

from mwalimulens.agent.ollama import OllamaSettings, build_ollama_model
from mwalimulens.agent.open_weights_run import (
    CONCISE_OPEN_WEIGHTS_TASK,
    DEFAULT_OPEN_WEIGHTS_TASK,
    build_open_weights_report,
    run_open_weights_task,
)
from mwalimulens.mcp_server.state import JsonStateStore


def test_concise_prompt_preserves_citations_and_teacher_authority() -> None:
    assert CONCISE_OPEN_WEIGHTS_TASK != DEFAULT_OPEN_WEIGHTS_TASK
    for required in (
        "flag_pattern_for_review",
        "counter-evidence",
        "uncertainty",
        "teacher",
    ):
        assert required in CONCISE_OPEN_WEIGHTS_TASK


def test_request_sequence_records_mcp_checkpoint_without_leaking_evidence(
    monkeypatch,
) -> None:
    async def fake_request(self, *args, **kwargs):
        return SimpleNamespace(usage=SimpleNamespace(
            input_tokens=200, output_tokens=80, total_tokens=280,
        ))

    monkeypatch.setattr(OllamaModel, "request", fake_request)
    calls = []
    records = []
    model = build_ollama_model(
        OllamaSettings(), records=records,
        audit_snapshot=lambda: tuple(calls),
    )
    asyncio.run(model.request([], None, None))
    calls.append("get_competency_evidence")
    asyncio.run(model.request([], None, None))
    calls.append("flag_pattern_for_review")

    assert records[0]["audited_tools_before"] == []
    assert records[0]["audited_tools_after"] == []
    assert records[1]["audited_tools_before"] == ["get_competency_evidence"]
    assert "claim" not in json.dumps(records)
    assert "response" not in json.dumps(records)
    assert records[1]["output_tokens"] == 80


def test_report_carries_prompt_style_without_changing_gates(tmp_path) -> None:
    now = datetime(2026, 10, 26, tzinfo=UTC)
    store = JsonStateStore(tmp_path / "state.json")
    report = build_open_weights_report(
        settings=OllamaSettings(),
        prompt=CONCISE_OPEN_WEIGHTS_TASK,
        prompt_style="concise",
        final_output="Insufficient evidence.",
        state_store=store,
        started_at=now, finished_at=now,
    )
    assert report["prompt_style"] == "concise"
    assert report["status"] == "fail"
    assert report["checks"]["pending_teacher_review_created"] is False
    assert report["checks"]["teacher_review_absent"] is True
    assert report["checks"]["profile_update_absent"] is True


def test_invalid_prompt_style_rejected_without_deleting_state(tmp_path) -> None:
    state = tmp_path / "existing.json"
    state.write_text('{"do_not_touch":true}', encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown prompt style"):
        asyncio.run(run_open_weights_task(
            prompt_style="unknown", state_path=state,
            report_path=tmp_path / "report.json",
        ))
    assert json.loads(state.read_text(encoding="utf-8"))["do_not_touch"]


def test_concise_mode_rejects_an_uncontrolled_custom_prompt(tmp_path) -> None:
    with pytest.raises(ValueError, match="cannot override"):
        asyncio.run(run_open_weights_task(
            prompt_style="concise", prompt="Anything goes",
            state_path=tmp_path / "state.json",
            report_path=tmp_path / "report.json",
        ))

def test_scenario_recovery_targets_correct_learner_without_answers():
    from mwalimulens.agent.open_weights_run import _recovery_prompt

    prompt = _recovery_prompt("scenario", ("L002", "SCI-DATA"))
    assert "L002" in prompt
    assert "SCI-DATA" in prompt
    assert "L001" not in prompt
    assert "EV-014" not in prompt
    assert "two exact supporting" in prompt
    assert "counter-evidence" in prompt


def test_explicit_scenario_abstention_is_not_oracle_retried(
    tmp_path, monkeypatch,
):
    from types import SimpleNamespace

    from mwalimulens.agent import open_weights_run

    attempts = []

    class Agent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def run(self, prompt, **_kwargs):
            attempts.append(prompt)
            return SimpleNamespace(
                output="ABSTAIN: Insufficient history.",
                all_messages=lambda: [],
            )

    monkeypatch.setattr(open_weights_run, "build_ollama_agent",
                        lambda **_kwargs: Agent())
    monkeypatch.setattr(
        open_weights_run, "_should_attempt_completion_recovery",
        lambda _store: True,
    )
    report = asyncio.run(run_open_weights_task(
        prompt="Review hypothetical evidence.",
        prompt_style="scenario",
        evaluation_target=("L001", "MATH-FRACTIONS"),
        expected_outcome="candidate",
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
    ))
    assert len(attempts) == 1
    assert report["completion_recovery"]["attempted"] is False
    assert report["status"] == "fail"
