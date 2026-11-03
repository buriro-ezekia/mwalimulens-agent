"""Offline execution limits, durable progress and immutable MCP retrievals."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastmcp import Client
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models.ollama import OllamaModel

from mwalimulens.agent import open_weights_run, orchestrator
from mwalimulens.agent.execution import ExecutionLimits, atomic_json
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import run_one, run_suite, scenario_by_id


def test_cancellation_persists_unknown_active_stage_and_propagates(tmp_path, monkeypatch):
    entered = asyncio.Event()
    closed = []

    class SlowAgent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.append(True)

        async def run(self, *_args, **_kwargs):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(open_weights_run, "build_ollama_agent", lambda **kw: SlowAgent())

    async def exercise():
        task = asyncio.create_task(open_weights_run.run_open_weights_task(
            state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
        ))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert closed == [True]
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "fail"
    assert report["termination"]["reason"] == "cancelled"
    assert report["active_stage"] == "initial"
    assert report["active_stage_outcome"] == "unknown"
    assert report["outcome_stages"] == []


@pytest.mark.parametrize("interrupt", ["deadline", "cancel"])
def test_teardown_error_cannot_mask_interrupted_stage(tmp_path, monkeypatch, interrupt):
    entered = asyncio.Event()

    class Agent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            raise RuntimeError("Synthetic teardown failure")

        async def run(self, *_args, **_kwargs):
            entered.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(open_weights_run, "build_ollama_agent", lambda **kw: Agent())

    async def exercise():
        task = asyncio.create_task(open_weights_run.run_open_weights_task(
            state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
            execution_limits=ExecutionLimits(6, 0.05 if interrupt == "deadline" else 10),
        ))
        if interrupt == "cancel":
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task

    asyncio.run(exercise())
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "fail"
    assert report["termination"]["reason"] == (
        "deadline_exceeded" if interrupt == "deadline" else "cancelled"
    )
    assert report["active_stage_outcome"] == "unknown"
    assert report["outcome_stages"] == []
    assert report["cleanup_error"]["message"] == "Synthetic teardown failure"


@pytest.mark.parametrize("interrupt", ["deadline", "cancel"])
@pytest.mark.parametrize("phase", ["agent", "preload"])
def test_interruption_during_teardown_cannot_be_masked(
    tmp_path, monkeypatch, interrupt, phase,
):
    entered_teardown = asyncio.Event()

    class Agent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            entered_teardown.set()
            try:
                await asyncio.Event().wait()
            finally:
                raise RuntimeError("Synthetic interrupted teardown failure")

        async def run(self, *_args, **_kwargs):
            return SimpleNamespace(
                output="ABSTAIN: No defensible claim.", all_messages=lambda: [],
            )

    async def preload(_settings):
        async with Agent():
            pass

    monkeypatch.setattr(open_weights_run, "build_ollama_agent", lambda **kw: Agent())
    monkeypatch.setattr(open_weights_run, "prewarm_ollama_async", preload)

    async def exercise():
        task = asyncio.create_task(open_weights_run.run_open_weights_task(
            settings=open_weights_run.OllamaSettings(
                keep_alive="30m" if phase == "preload" else None,
            ),
            state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
            execution_limits=ExecutionLimits(6, 0.05 if interrupt == "deadline" else 10),
        ))
        if interrupt == "cancel":
            await entered_teardown.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task

    asyncio.run(exercise())
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "fail"
    assert report["termination"]["reason"] == (
        "deadline_exceeded" if interrupt == "deadline" else "cancelled"
    )
    assert report["active_stage"] is None
    assert report["active_stage_outcome"] is None
    assert len(report["outcome_stages"]) == (1 if phase == "agent" else 0)
    if phase == "agent":
        assert report["outcome_stages"][0]["final_output"] == "ABSTAIN: No defensible claim."
    else:
        assert report["preload"]["status"] == "interrupted"
    assert report["cleanup_error"]["message"] == "Synthetic interrupted teardown failure"


@pytest.mark.parametrize("first_reason", ["request_budget_exhausted", "deadline_exceeded"])
def test_later_cancellation_propagates_without_replacing_first_termination(
    tmp_path, monkeypatch, first_reason,
):
    entered_teardown = asyncio.Event()

    class Agent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            entered_teardown.set()
            await asyncio.Event().wait()

        async def run(self, *_args, **_kwargs):
            if first_reason == "request_budget_exhausted":
                raise UsageLimitExceeded("Synthetic exhausted budget")
            await asyncio.Event().wait()

    monkeypatch.setattr(open_weights_run, "build_ollama_agent", lambda **kw: Agent())

    async def exercise():
        task = asyncio.create_task(open_weights_run.run_open_weights_task(
            state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
            execution_limits=ExecutionLimits(
                6, 0.05 if first_reason == "deadline_exceeded" else 10,
            ),
        ))
        await entered_teardown.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["status"] == "fail"
    assert report["termination"]["reason"] == first_reason
    assert report["active_stage_outcome"] == "unknown"
    assert report["outcome_stages"] == []


def test_completed_stage_is_on_disk_before_recovery_finishes(tmp_path, monkeypatch):
    calls = 0

    class Agent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def run(self, *_args, **_kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                checkpoint = json.loads((tmp_path / "report.progress.json").read_text())
                assert checkpoint["active_stage"] == "grounding_correction"
                assert checkpoint["outcome_stages"][0]["final_output"] == (
                    "ABSTAIN: The evidence spans only two terms."
                )
            return SimpleNamespace(
                output=("ABSTAIN: The evidence spans only two terms." if calls == 1
                        else "ABSTAIN: No defensible claim."), all_messages=lambda: [],
            )

    monkeypatch.setattr(open_weights_run, "build_ollama_agent", lambda **kw: Agent())
    report = asyncio.run(open_weights_run.run_open_weights_task(
        prompt="Review fictional evidence", prompt_style="scenario",
        evaluation_target=("L002", "SCI-DATA"),
        state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
    ))
    assert calls == 2
    assert report["error"] is None


def controlled_model(tmp_path, monkeypatch, actions, *, stdio=False):
    """Use the real Agent, MCP tools, telemetry and limits; fake only inference."""
    state_path = tmp_path / "state.json"
    if not stdio:
        server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=state_path)
        monkeypatch.setattr(orchestrator, "build_agent_mcp_client", lambda **kw: Client(
            server, mode=orchestrator.EDUCATION_MCP_CLIENT_MODE,
        ))
    calls = []
    stopped = []

    async def respond(_self, messages, *_args, **_kwargs):
        index = len(calls)
        calls.append(messages)
        action = actions[index]
        if action == "hang":
            try:
                await asyncio.Event().wait()
            finally:
                stopped.append(True)
        if action == "retrieve":
            return ModelResponse(parts=[ToolCallPart("get_competency_evidence", {
                "learner_id": "L002", "competency_code": "SCI-DATA",
            }, tool_call_id=f"read-{index}")])
        if action == "candidate":
            return ModelResponse(parts=[ToolCallPart("flag_pattern_for_review", {
                "learner_id": "L002", "competency_code": "SCI-DATA",
                "claim": "Recorded scores differ slightly across two terms.",
                "supporting_evidence_ids": ["EV-012", "EV-013"],
                "counter_evidence_ids": ["EV-014"],
                "uncertainty": "Later explanation still required support.",
                "suggested_teacher_question": "Can the learner explain a new trend unaided?",
            })])
        return ModelResponse(parts=[TextPart(action)])

    monkeypatch.setattr(OllamaModel, "request", respond)
    return calls, stopped, JsonStateStore(state_path)


@pytest.mark.parametrize(
    ("budget", "active", "completed"),
    [(1, "initial", 0), (2, "grounding_correction", 1), (4, "completion_recovery", 2)],
)
def test_request_budget_is_shared_across_all_three_stages(
    tmp_path, monkeypatch, budget, active, completed,
):
    calls, _, state = controlled_model(tmp_path, monkeypatch, [
        "retrieve", "ABSTAIN: Only two terms have evidence.",
        "retrieve", "I will submit a candidate.",
    ])
    result = asyncio.run(run_one(
        scenario_by_id("conflicting-evidence"), state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json", result_path=tmp_path / "result.json",
        execution_limits=ExecutionLimits(budget, 10),
    ))
    report = json.loads((tmp_path / "report.json").read_text())
    assert len(calls) == budget
    assert result["status"] == "fail"
    assert result["termination"]["reason"] == "request_budget_exhausted"
    assert result["active_stage"] == active
    assert result["active_stage_outcome"] == "unknown"
    assert [s["stage"] for s in report["outcome_stages"]] == [
        "initial", "grounding_correction",
    ][:completed]
    assert [r["stage"] for r in report["model_requests"]] == [
        "initial", "initial", "grounding_correction", "grounding_correction",
    ][:budget]
    assert [r["status"] for r in report["retrieval_events"]] == (
        ["retrieved", "snapshot_reused"] if budget == 4 else ["retrieved"]
    )
    assert len(state.tool_calls()) == 1
    # Full evidence, including source references, survives in recovery history.
    if budget > 1:
        history = str(calls[-1])
        for item in state.tool_calls()[0]["output"]["evidence"]:
            assert item["evidence_id"] in history
            assert item["source_ref"] in history
    assert state.pending_reviews() == state.teacher_reviews() == state.profile_updates() == ()
    saved_result = json.loads((tmp_path / "result.json").read_text())
    assert saved_result["termination"] == result["termination"]


@pytest.mark.parametrize("interrupt", ["deadline", "cancel"])
def test_interrupted_recovery_keeps_completed_stages_and_unknown_outcome(
    tmp_path, monkeypatch, interrupt,
):
    deadlines = []
    timeout_at = asyncio.timeout_at

    def observe_deadline(when):
        deadlines.append(when)
        return timeout_at(when)

    monkeypatch.setattr(asyncio, "timeout_at", observe_deadline)
    calls, stopped, state = controlled_model(tmp_path, monkeypatch, [
        "retrieve", "ABSTAIN: Only two terms have evidence.",
        "retrieve", "I will submit a candidate.", "hang",
    ])
    async def exercise():
        task = asyncio.create_task(run_one(
            scenario_by_id("conflicting-evidence"), state_path=tmp_path / "state.json",
            report_path=tmp_path / "report.json", result_path=tmp_path / "result.json",
            execution_limits=ExecutionLimits(6, 1 if interrupt == "deadline" else 10),
        ))
        if interrupt == "cancel":
            while len(calls) < 5 and not task.done():
                await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            return json.loads((tmp_path / "result.json").read_text())
        return await task

    result = asyncio.run(exercise())
    assert len(calls) == 5
    assert stopped == [True]
    assert result["status"] == "fail"
    assert result["termination"]["reason"] == (
        "deadline_exceeded" if interrupt == "deadline" else "cancelled"
    )
    assert result["active_stage"] == "completion_recovery"
    assert result["active_stage_outcome"] == "unknown"
    assert len(result["outcome_stages"]) == 2
    last = result["model_requests"][-1]
    assert last["status"] == "interrupted"
    assert "requested_tool_names" not in last
    assert last["stage"] == "completion_recovery"
    assert not state.pending_reviews()
    assert len(deadlines) == 1


def test_budget_exhaustion_after_candidate_never_approves_it(tmp_path, monkeypatch):
    calls, _, state = controlled_model(tmp_path, monkeypatch, ["retrieve", "candidate"])
    result = asyncio.run(run_one(
        scenario_by_id("conflicting-evidence"), state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json", execution_limits=ExecutionLimits(2, 10),
    ))
    assert len(calls) == 2
    assert result["status"] == "fail"
    assert result["termination"]["reason"] == "request_budget_exhausted"
    assert result["outcome_stages"] == []
    assert state.pending_reviews()[0]["status"] == "pending_teacher_review"
    assert state.teacher_reviews() == state.profile_updates() == ()


def test_legitimate_abstention_remains_possible_with_shared_budget(tmp_path, monkeypatch):
    _, _, state = controlled_model(tmp_path, monkeypatch, [
        "retrieve", "ABSTAIN: These observations do not support a defensible claim.",
    ])
    report = asyncio.run(open_weights_run.run_open_weights_task(
        prompt="Review fictional evidence", prompt_style="scenario",
        evaluation_target=("L002", "SCI-DATA"), expected_outcome="abstain",
        state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
        execution_limits=ExecutionLimits(2, 10),
    ))
    assert report["termination"] is None
    assert report["status"] == "pass"
    assert report["completion_recovery"]["attempted"] is False
    assert state.pending_reviews() == ()


def test_atomic_checkpoint_failure_preserves_previous_document(tmp_path, monkeypatch):
    path = tmp_path / "checkpoint.json"
    atomic_json(path, {"completed": "initial"})
    with pytest.raises(TypeError):
        atomic_json(path, {"unsupported": object()})
    assert json.loads(path.read_text()) == {"completed": "initial"}
    assert list(tmp_path.glob("*.tmp")) == []


def test_cancellation_closes_real_mcp_subprocess_and_saves_result(tmp_path, monkeypatch):
    from mcp.client import stdio

    processes = []
    spawn = stdio._create_platform_compatible_process

    async def capture(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", capture)
    calls, stopped, state = controlled_model(
        tmp_path, monkeypatch, ["retrieve", "hang"], stdio=True,
    )

    async def exercise():
        task = asyncio.create_task(run_one(
            scenario_by_id("conflicting-evidence"), state_path=tmp_path / "state.json",
            report_path=tmp_path / "report.json", result_path=tmp_path / "result.json",
            execution_limits=ExecutionLimits(6, 20),
        ))
        try:
            async with asyncio.timeout(15):
                while len(calls) < 2:
                    await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())
    assert stopped == [True]
    assert len(processes) == 1
    assert processes[0].returncode is not None
    assert state.teacher_reviews() == state.profile_updates() == ()
    for name in ("report.json", "result.json"):
        saved = json.loads((tmp_path / name).read_text())
        assert saved["status"] == "fail"
        assert saved["termination"]["reason"] == "cancelled"
        assert saved["active_stage_outcome"] == "unknown"


def test_suite_leaves_persistence_margin_and_forwards_one_budget(tmp_path):
    import subprocess

    def runner(command, **kwargs):
        assert kwargs["timeout"] == 60
        assert command[command.index("--deadline-seconds") + 1] == "30"
        assert command[command.index("--request-limit") + 1] == "3"
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="")

    result = run_suite(
        output_root=tmp_path, scenarios=("longitudinal-pattern",),
        timeout=60, request_limit=3, runner=runner,
    )
    assert result["status"] == "fail"
    with pytest.raises(ValueError, match="at least 30 seconds"):
        run_suite(output_root=tmp_path, timeout=60, deadline_seconds=59, runner=runner)


def test_preload_is_cancelled_without_leaving_a_worker_thread(tmp_path, monkeypatch):
    from mwalimulens.agent import ollama

    closed = []

    class SlowHTTPClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            closed.append(True)

        async def post(self, *_args, **_kwargs):
            await asyncio.Event().wait()

    monkeypatch.setattr(ollama, "DefaultAsyncHttpxClient", SlowHTTPClient)
    report = asyncio.run(open_weights_run.run_open_weights_task(
        settings=ollama.OllamaSettings(keep_alive="30m"),
        state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
        execution_limits=ExecutionLimits(2, 0.05),
    ))
    assert closed == [True]
    assert report["termination"]["reason"] == "deadline_exceeded"
    assert report["model_requests"] == []
    assert report["status"] == "fail"
    assert report["preload"]["attempted"] is True
    assert report["preload"]["status"] == "interrupted"
