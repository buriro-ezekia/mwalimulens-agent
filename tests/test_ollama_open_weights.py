"""Tests for local Qwen/Ollama configuration and open-weights run evidence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic_ai.models.ollama import OllamaModel

from mwalimulens.agent.ollama import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    OllamaSettings,
    build_ollama_model,
)
from mwalimulens.agent.open_weights_run import build_open_weights_report
from mwalimulens.mcp_server.state import JsonStateStore


def test_ollama_settings_defaults(monkeypatch) -> None:
    monkeypatch.delenv("MWALIMULENS_OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("MWALIMULENS_OLLAMA_BASE_URL", raising=False)

    settings = OllamaSettings.from_env()

    assert settings.model_name == DEFAULT_OLLAMA_MODEL
    assert settings.base_url == DEFAULT_OLLAMA_BASE_URL


def test_ollama_settings_can_be_overridden_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MWALIMULENS_OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("MWALIMULENS_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    settings = OllamaSettings.from_env()

    assert settings.model_name == "qwen2.5:3b"
    assert settings.base_url == "http://127.0.0.1:11434/v1"


def test_ollama_settings_reject_invalid_base_url() -> None:
    with pytest.raises(ValueError, match="absolute http"):
        OllamaSettings(base_url="localhost:11434/v1")


def test_ollama_model_builds_without_network_request() -> None:
    model = build_ollama_model(OllamaSettings())

    assert isinstance(model, OllamaModel)
    assert model.model_name == DEFAULT_OLLAMA_MODEL


def test_open_weights_report_passes_for_safe_complete_task(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    store.record_tool_call(
        {
            "tool_name": "get_competency_evidence",
            "status": "success",
        }
    )
    candidate = {
        "review_id": "review-test",
        "status": "pending_teacher_review",
    }
    store.record_pending_review_and_tool_call(
        candidate,
        {
            "tool_name": "flag_pattern_for_review",
            "status": "success",
        },
    )

    report = build_open_weights_report(
        settings=OllamaSettings(),
        prompt="Synthetic test task",
        final_output="Candidate submitted.",
        state_store=store,
        started_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )

    assert report["status"] == "pass"
    assert report["pending_review_count"] == 1
    assert report["teacher_review_count"] == 0
    assert report["profile_update_count"] == 0
    assert all(report["checks"].values())


def test_open_weights_report_fails_if_human_tool_was_called(tmp_path) -> None:
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
    store.record_tool_call(
        {
            "tool_name": "record_teacher_review",
            "status": "success",
        }
    )

    report = build_open_weights_report(
        settings=OllamaSettings(),
        prompt="Synthetic forbidden-call task",
        final_output="Invalid run.",
        state_store=store,
        started_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )

    assert report["status"] == "fail"
    assert report["checks"]["forbidden_teacher_review_absent"] is False


def test_open_weights_report_fails_without_pending_candidate(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    store.record_tool_call(
        {
            "tool_name": "get_competency_evidence",
            "status": "success",
        }
    )

    report = build_open_weights_report(
        settings=OllamaSettings(),
        prompt="Synthetic incomplete task",
        final_output="Evidence retrieved only.",
        state_store=store,
        started_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )

    assert report["status"] == "fail"
    assert report["checks"]["submitted_candidate"] is False
    assert report["checks"]["pending_teacher_review_created"] is False
