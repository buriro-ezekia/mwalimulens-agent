"""Tests for the consolidated one-command challenge report."""

from __future__ import annotations

from datetime import UTC, datetime

from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.challenge_run import (
    build_challenge_report,
    ollama_tags_url,
    preflight_ollama,
)


def test_ollama_tags_url_uses_same_local_server() -> None:
    assert (
        ollama_tags_url("http://localhost:11434/v1")
        == "http://localhost:11434/api/tags"
    )


def test_ollama_preflight_requires_requested_model() -> None:
    settings = OllamaSettings(model_name="qwen2.5:3b")

    def fake_fetch(_url: str, _timeout: float):
        return {"models": [{"name": "qwen2.5:3b"}]}

    result = preflight_ollama(settings, fetch_json=fake_fetch)

    assert result["status"] == "pass"
    assert result["model"] == "qwen2.5:3b"
    assert "qwen2.5:3b" in result["models_found"]


def test_ollama_preflight_reports_missing_model() -> None:
    settings = OllamaSettings(model_name="qwen2.5:3b")

    def fake_fetch(_url: str, _timeout: float):
        return {"models": [{"name": "qwen2.5:1.5b"}]}

    result = preflight_ollama(settings, fetch_json=fake_fetch)

    assert result["status"] == "fail"
    assert result["remediation"] == (
        "Run ollama pull qwen2.5:3b once, then rerun this command."
    )


def test_challenge_report_passes_only_with_human_gate_preserved(monkeypatch) -> None:
    monkeypatch.setattr(
        "mwalimulens.challenge_run.runtime_environment",
        lambda: {"python": "test"},
    )
    settings = OllamaSettings(model_name="qwen2.5:3b")
    started = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)
    finished = datetime(2026, 10, 4, 6, 1, tzinfo=UTC)

    report = build_challenge_report(
        settings=settings,
        preflight={"status": "pass"},
        open_weights={
            "status": "pass",
            "pending_review_count": 1,
            "teacher_review_count": 0,
            "profile_update_count": 0,
            "error": None,
        },
        borrowed_mcp={
            "status": "pass",
            "visible_tools": ["read_text_file"],
            "audited_tool_calls": [{"tool_name": "read_text_file"}],
            "error": None,
        },
        evals={
            "status": "pass",
            "summary": {
                "current_pass": 11,
                "historical_fail_preserved": 2,
            },
        },
        started_at=started,
        finished_at=finished,
    )

    assert report["status"] == "pass"
    assert all(report["checks"].values())


def test_challenge_report_fails_if_agent_crosses_human_gate(monkeypatch) -> None:
    monkeypatch.setattr(
        "mwalimulens.challenge_run.runtime_environment",
        lambda: {"python": "test"},
    )
    settings = OllamaSettings(model_name="qwen2.5:3b")
    timestamp = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)

    report = build_challenge_report(
        settings=settings,
        preflight={"status": "pass"},
        open_weights={
            "status": "pass",
            "pending_review_count": 1,
            "teacher_review_count": 1,
            "profile_update_count": 1,
        },
        borrowed_mcp={"status": "pass", "audited_tool_calls": []},
        evals={"status": "pass"},
        started_at=timestamp,
        finished_at=timestamp,
    )

    assert report["status"] == "fail"
    assert report["checks"]["human_gate_preserved"] is False



def test_ollama_preflight_rejects_non_local_endpoint() -> None:
    settings = OllamaSettings(
        model_name="qwen2.5:3b",
        base_url="https://example.com/v1",
    )

    result = preflight_ollama(settings, fetch_json=lambda _url, _timeout: {})

    assert result["status"] == "fail"
    assert "local machine" in result["error"]
