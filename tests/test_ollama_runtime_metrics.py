"""Opt-in Ollama model retention and request metrics are locally testable."""

from __future__ import annotations

import asyncio
import io
import json
from types import SimpleNamespace

import pytest
from pydantic_ai.models.ollama import OllamaModel

from mwalimulens.agent.ollama import (
    OllamaSettings,
    TimedOllamaModel,
    build_ollama_model,
    prewarm_ollama,
)


def test_keep_alive_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("MWALIMULENS_OLLAMA_KEEP_ALIVE", raising=False)
    settings = OllamaSettings.from_env()
    assert settings.keep_alive is None
    assert prewarm_ollama(settings)["status"] == "disabled"


def test_keep_alive_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("MWALIMULENS_OLLAMA_KEEP_ALIVE", "30m")
    assert OllamaSettings.from_env().keep_alive == "30m"


@pytest.mark.parametrize("value", ["", "0", "-1", "90m", "2h", "5x"])
def test_rejects_indefinite_or_oversized_retention(value) -> None:
    with pytest.raises(ValueError, match="keep_alive"):
        OllamaSettings(keep_alive=value)


def test_preload_only_allows_local_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaSettings(
            base_url="https://example.com/v1",
            keep_alive="30m",
        )


def test_native_preload_uses_empty_prompt_and_requested_retention(monkeypatch) -> None:
    calls = []

    def fake_open(request, timeout):
        calls.append({
            "url": request.full_url,
            "method": request.get_method(),
            "payload": json.loads(request.data),
            "timeout": timeout,
        })
        return io.BytesIO(b'{"model":"qwen2.5:3b","done":true,"done_reason":"load"}')

    monkeypatch.setattr("mwalimulens.agent.ollama.urlopen", fake_open)
    result = prewarm_ollama(OllamaSettings(keep_alive="30m"))
    assert result["status"] == "pass"
    assert result["attempted"]
    assert result["seconds"] >= 0
    assert calls[0]["url"] == "http://localhost:11434/api/generate"
    assert calls[0]["method"] == "POST"
    assert calls[0]["timeout"] == 90
    assert calls[0]["payload"] == {
        "model": "qwen2.5:3b",
        "prompt": "",
        "stream": False,
        "keep_alive": "30m",
    }


def test_invalid_preload_response_fails_closed(monkeypatch) -> None:
    def fake_open(*args, **kwargs):
        return io.BytesIO(b'{"model":"different","done":true}')

    monkeypatch.setattr("mwalimulens.agent.ollama.urlopen", fake_open)
    with pytest.raises(RuntimeError, match="requested model"):
        prewarm_ollama(OllamaSettings(keep_alive="30m"))


def test_model_requests_capture_token_counts_without_content(monkeypatch) -> None:
    async def fake_request(self, *args, **kwargs):
        return SimpleNamespace(usage=SimpleNamespace(
            input_tokens=120,
            output_tokens=45,
            total_tokens=165,
        ))

    monkeypatch.setattr(OllamaModel, "request", fake_request)
    records = []
    model = build_ollama_model(OllamaSettings(), records=records)
    assert isinstance(model, TimedOllamaModel)
    asyncio.run(model.request([], None, None))

    assert len(records) == 1
    assert records[0]["status"] == "pass"
    assert records[0]["input_tokens"] == 120
    assert records[0]["output_tokens"] == 45
    assert records[0]["total_tokens"] == 165
    assert records[0]["seconds"] >= 0
    assert "response" not in records[0]
    assert "prompt" not in records[0]


def test_failed_model_request_still_has_timing(monkeypatch) -> None:
    async def broken_request(self, *args, **kwargs):
        raise TimeoutError("request failed")

    monkeypatch.setattr(OllamaModel, "request", broken_request)
    records = []
    model = build_ollama_model(OllamaSettings(), records=records)
    with pytest.raises(TimeoutError):
        asyncio.run(model.request([], None, None))

    assert records[0]["status"] == "error"
    assert records[0]["error_type"] == "TimeoutError"
    assert records[0]["seconds"] >= 0

def test_run_report_exposes_only_request_metadata(tmp_path) -> None:
    from datetime import UTC, datetime

    from mwalimulens.agent.open_weights_run import build_open_weights_report
    from mwalimulens.mcp_server.state import JsonStateStore

    now = datetime(2026, 10, 26, tzinfo=UTC)
    report = build_open_weights_report(
        settings=OllamaSettings(keep_alive="30m"),
        prompt="Synthetic learner task",
        final_output="No candidate.",
        state_store=JsonStateStore(tmp_path / "state.json"),
        started_at=now,
        finished_at=now,
        preload={
            "attempted": True,
            "status": "pass",
            "seconds": 1.2,
            "requested_keep_alive": "30m",
        },
        model_requests=[{
            "request": 1,
            "status": "pass",
            "seconds": 18.1,
            "input_tokens": 450,
            "output_tokens": 70,
            "total_tokens": 520,
        }],
    )
    assert report["model_request_count_observed"] == 1
    assert report["ollama_keep_alive"] == "30m"
    assert report["preload"]["status"] == "pass"
    assert report["model_requests"][0]["output_tokens"] == 70
    assert report["model_requests"][0]["seconds"] == 18.1
    assert report["teacher_review_count"] == 0
    assert report["profile_update_count"] == 0
    assert report["status"] == "fail"


def test_runner_captures_preload_and_model_request_metrics(tmp_path, monkeypatch) -> None:
    from mwalimulens.agent import open_weights_run

    observed = []

    class FakeAgent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def run(self, _prompt, **_kwargs):
            observed.append("ran")
            request_records[0].append({
                "request": 1,
                "status": "pass",
                "seconds": 10.0,
                "input_tokens": 40,
                "output_tokens": 20,
                "total_tokens": 60,
            })
            return SimpleNamespace(output="Evidence pending.")

    request_records = []

    def fake_builder(*, records, **_kwargs):
        assert records is not None
        request_records.append(records)
        return FakeAgent()

    monkeypatch.setattr(open_weights_run, "build_ollama_agent", fake_builder)
    monkeypatch.setattr(
        open_weights_run, "prewarm_ollama",
        lambda settings: {
            "attempted": True,
            "status": "pass",
            "seconds": 0.5,
            "requested_keep_alive": settings.keep_alive,
        },
    )
    report = asyncio.run(open_weights_run.run_open_weights_task(
        settings=OllamaSettings(keep_alive="30m"),
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
    ))
    assert observed == ["ran"]
    assert report["preload"]["status"] == "pass"
    assert report["model_request_count_observed"] == 1
    assert report["model_requests"][0]["input_tokens"] == 40
    assert report["status"] == "fail"
    assert report["teacher_review_count"] == 0
