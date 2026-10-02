"""Tests for local Qwen/Ollama configuration and open-weights run evidence."""

from __future__ import annotations

import json
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
from mwalimulens.agent.promote_open_weights_evidence import promote_open_weights_report
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
            "timestamp": "2026-10-02T09:00:00+00:00",
        }
    )
    candidate = {
        "review_id": "review-test",
        "status": "pending_teacher_review",
        "learner_id": "L001",
        "competency_code": "MATH-FRACTIONS",
        "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009"],
        "counter_evidence_ids": ["EV-008"],
    }
    store.record_pending_review_and_tool_call(
        candidate,
        {
            "tool_name": "flag_pattern_for_review",
            "status": "success",
            "timestamp": "2026-10-02T09:00:30+00:00",
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
            "timestamp": "2026-10-02T09:00:00+00:00",
        }
    )
    candidate = {
        "review_id": "review-forbidden",
        "status": "pending_teacher_review",
        "learner_id": "L001",
        "competency_code": "MATH-FRACTIONS",
    }
    store.record_pending_review_and_tool_call(
        candidate,
        {
            "tool_name": "flag_pattern_for_review",
            "status": "success",
            "timestamp": "2026-10-02T09:00:30+00:00",
        },
    )
    store.record_tool_call(
        {
            "tool_name": "record_teacher_review",
            "status": "success",
            "timestamp": "2026-10-02T09:00:45+00:00",
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
            "timestamp": "2026-10-02T09:00:00+00:00",
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


def test_open_weights_report_fails_for_non_local_endpoint(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")

    report = build_open_weights_report(
        settings=OllamaSettings(base_url="https://example.com/v1"),
        prompt="Synthetic remote task",
        final_output="No local execution.",
        state_store=store,
        started_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
    )

    assert report["status"] == "fail"
    assert report["checks"]["local_ollama_endpoint"] is False

def test_passing_open_weights_report_can_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    destination = tmp_path / "evidence.json"
    report = {
        "status": "pass",
        "provider": "ollama",
        "open_weights": True,
        "model": "qwen2.5:1.5b",
        "checks": {"safe": True, "complete": True},
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    promoted = promote_open_weights_report(
        source=source,
        destination=destination,
    )

    assert promoted == report
    assert destination.is_file()


def test_failed_open_weights_report_cannot_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    report = {
        "status": "fail",
        "provider": "ollama",
        "open_weights": True,
        "checks": {"safe": False},
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="status must be pass"):
        promote_open_weights_report(
            source=source,
            destination=tmp_path / "evidence.json",
        )



def test_open_weights_report_with_runtime_error_cannot_pass(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")

    report = build_open_weights_report(
        settings=OllamaSettings(),
        prompt="Synthetic failed model request",
        final_output="",
        state_store=store,
        started_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 2, 9, 1, tzinfo=UTC),
        error={"type": "ConnectionError", "message": "Ollama unavailable"},
    )

    assert report["status"] == "fail"
    assert report["error"]["type"] == "ConnectionError"
