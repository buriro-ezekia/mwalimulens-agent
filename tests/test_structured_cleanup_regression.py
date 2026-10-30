"""Replay teardown masking an earlier interruption; never call real Ollama."""

from __future__ import annotations

import asyncio
import json

import pytest

from mwalimulens import structured_review
from mwalimulens.agent.execution import ExecutionLimits
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import scenario_by_id


def test_cleanup_error_cannot_swallow_original_cancellation(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    service = EducationToolService(
        load_synthetic_dataset(DEFAULT_DATA_DIR), JsonStateStore(state_path)
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, kind, exc, traceback):
            if exc is not None:
                raise RuntimeError("Synthetic cleanup failure") from exc

        async def call_tool(self, name, arguments):
            assert name == "get_competency_evidence"
            return service.get_competency_evidence(**arguments)

    class Generator:
        def __init__(self, **_kwargs):
            pass

        async def __call__(self, *_args):
            raise asyncio.CancelledError()

    monkeypatch.setattr(structured_review, "build_agent_mcp_client", lambda **kw: Client())
    monkeypatch.setattr(structured_review, "OllamaJsonGenerator", Generator)
    report_path = tmp_path / "report.json"
    result_path = tmp_path / "result.json"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), state_path=state_path,
            report_path=report_path, result_path=result_path, settings=OllamaSettings(),
        ))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["termination"]["reason"] == "cancelled"
    assert report["cleanup_error"]["type"] == "RuntimeError"
    assert report["status"] == "fail"
    assert report["active_stage_outcome"] == "unknown"
    assert result_path.exists()
    assert service.state_store.pending_reviews() == ()
    assert service.state_store.teacher_reviews() == service.state_store.profile_updates() == ()


@pytest.mark.parametrize("mask", [False, True])
def test_external_cancel_after_deadline_persists_result(tmp_path, monkeypatch, mask):
    teardown = asyncio.Event()
    service = EducationToolService(
        load_synthetic_dataset(DEFAULT_DATA_DIR), JsonStateStore(tmp_path / "state.json")
    )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            teardown.set()
            try:
                await asyncio.Event().wait()
            finally:
                if mask:
                    raise RuntimeError("Synthetic cleanup failure")

        async def call_tool(self, name, arguments):
            return service.get_competency_evidence(**arguments)

    class Generator:
        def __init__(self, **_kwargs):
            pass

        async def __call__(self, *_args):
            await asyncio.Event().wait()

    monkeypatch.setattr(structured_review, "build_agent_mcp_client", lambda **kw: Client())
    monkeypatch.setattr(structured_review, "OllamaJsonGenerator", Generator)

    async def exercise():
        task = asyncio.create_task(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), state_path=tmp_path / "state.json",
            report_path=tmp_path / "report.json", result_path=tmp_path / "result.json",
            settings=OllamaSettings(), execution_limits=ExecutionLimits(2, 0.05),
        ))
        await asyncio.wait_for(teardown.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    for name in ("report.json", "result.json"):
        report = json.loads((tmp_path / name).read_text(encoding="utf-8"))
        assert report["status"] == "fail"
        assert report["termination"]["reason"] == "deadline_exceeded"
        assert report["active_stage_outcome"] == "unknown"
    assert service.state_store.pending_reviews() == ()
