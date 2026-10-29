"""Complete MCP evidence once per review, with observable duplicate attempts."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastmcp import Client
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from mwalimulens.agent import orchestrator
from mwalimulens.agent.retrieval import CompetencyReviewToolset
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.mcp_server.state import JsonStateStore


def test_simultaneous_repeated_calls_use_one_complete_mcp_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=path)
    monkeypatch.setattr(orchestrator, "build_agent_mcp_client", lambda **kw: Client(
        server, mode=orchestrator.EDUCATION_MCP_CLIENT_MODE,
    ))
    events = []
    seen = []

    async def respond(messages, info):
        assert {t.name for t in info.function_tools} == {
            "get_competency_evidence", "flag_pattern_for_review",
        }
        seen.append(messages)
        if len(seen) == 1:
            return ModelResponse(parts=[
                ToolCallPart("get_competency_evidence", {
                    "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
                }, tool_call_id=f"read-{i}") for i in range(2)
            ])
        return ModelResponse(parts=[TextPart("ABSTAIN: No defensible claim.")])

    agent = orchestrator.build_agent(
        FunctionModel(respond), state_path=path,
        competency_review_target=("L001", "MATH-FRACTIONS"), retrieval_events=events,
    )
    asyncio.run(agent.run("Review fictional L001 fractions."))
    state = JsonStateStore(path)
    assert len(state.tool_calls()) == 1
    assert [e["status"] for e in events] == ["retrieved", "snapshot_reused"]
    payload = state.tool_calls()[0]["output"]
    source = load_synthetic_dataset(DEFAULT_DATA_DIR).competency_evidence("L001", "MATH-FRACTIONS")
    assert payload["evidence_count"] == len(source) == 8
    assert {item["evidence_id"] for item in payload["evidence"]} == {
        item.evidence_id for item in source
    }
    for item in payload["evidence"]:
        assert item["source_ref"] in str(seen[-1])
        assert item["occurred_at"] in str(seen[-1])
    assert state.pending_reviews() == state.teacher_reviews() == state.profile_updates() == ()


def test_failed_retrieval_is_not_cached_or_hidden():
    calls = []

    class Wrapped:
        async def call_tool(self, *_args):
            calls.append(True)
            if len(calls) == 1:
                raise ValueError("Synthetic retrieval failure")
            return {"evidence": []}

    async def exercise():
        policy = CompetencyReviewToolset(Wrapped(), ("L002", "SCI-DATA"))
        args = {"learner_id": "L002", "competency_code": "SCI-DATA"}
        ctx = SimpleNamespace(tool_call_id="read")
        with pytest.raises(ValueError, match="Synthetic"):
            await policy.call_tool("get_competency_evidence", args, ctx, None)
        assert not policy.snapshots
        result = await policy.call_tool("get_competency_evidence", args, ctx, None)
        assert result == {"evidence": []}
        assert [e["status"] for e in policy.events] == ["unsuccessful", "retrieved"]

    asyncio.run(exercise())
    assert len(calls) == 2


def test_broader_timeline_use_case_retains_real_tool(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=path)
    monkeypatch.setattr(orchestrator, "build_agent_mcp_client", lambda **kw: Client(
        server, mode=orchestrator.EDUCATION_MCP_CLIENT_MODE,
    ))
    model = TestModel(call_tools=[], custom_output_text="Inspect tools")
    asyncio.run(orchestrator.build_agent(model, state_path=path).run("Review a timeline"))
    assert "get_learner_timeline" in {
        t.name for t in model.last_model_request_parameters.function_tools
    }


@pytest.mark.parametrize("history_mode", ["absent", "changed", "intact"])
def test_references_require_complete_matching_history(tmp_path, monkeypatch, history_mode):
    path = tmp_path / "state.json"
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=path)
    monkeypatch.setattr(orchestrator, "build_agent_mcp_client", lambda **kw: Client(
        server, mode=orchestrator.EDUCATION_MCP_CLIENT_MODE,
    ))
    seen = []

    async def respond(messages, _info):
        seen.append(deepcopy(messages))
        if len(seen) % 2:
            return ModelResponse(parts=[ToolCallPart("get_competency_evidence", {
                "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
            })])
        return ModelResponse(parts=[TextPart("ABSTAIN: No defensible claim.")])

    async def exercise():
        agent = orchestrator.build_agent(
            FunctionModel(respond), state_path=path,
            competency_review_target=("L001", "MATH-FRACTIONS"),
        )
        async with agent:
            first = await agent.run("First review")
            history = first.all_messages() if history_mode != "absent" else []
            if history_mode == "changed":
                for message in history:
                    if isinstance(message, ModelRequest):
                        for part in message.parts:
                            if isinstance(part, ToolReturnPart):
                                # Change the original container in place to test cache isolation.
                                if isinstance(part.content, (dict, list)):
                                    part.content.clear()
                                else:
                                    part.content = {"evidence": []}
            await agent.run("Next review", message_history=history)

    asyncio.run(exercise())
    calls = JsonStateStore(path).tool_calls()
    assert len(calls) == (1 if history_mode == "intact" else 2)
    assert "EV-008" in str(seen[-1])


def test_wrong_learner_or_competency_never_reuses_snapshot():
    from pydantic_ai import ModelRetry

    class Wrapped:
        async def call_tool(self, *_args):
            return {"evidence": [{"evidence_id": "EV-012"}]}

    async def exercise():
        policy = CompetencyReviewToolset(Wrapped(), ("L002", "SCI-DATA"))
        ctx = SimpleNamespace(tool_call_id="read", run_id="run", run_step=1, messages=[])
        await policy.call_tool("get_competency_evidence", {
            "learner_id": "L002", "competency_code": "SCI-DATA",
        }, ctx, None)
        for learner, competency in [("L001", "SCI-DATA"), ("L002", "MATH-FRACTIONS")]:
            with pytest.raises(ModelRetry):
                await policy.call_tool("get_competency_evidence", {
                    "learner_id": learner, "competency_code": competency,
                }, ctx, None)
        assert [event["status"] for event in policy.events] == [
            "retrieved", "rejected_target", "rejected_target",
        ]

    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["source", "session"])
def test_snapshot_cannot_outlive_its_source_session(change):
    class Wrapped:
        def __init__(self):
            self.calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

        async def call_tool(self, *_args):
            self.calls += 1
            return {"evidence": [{"evidence_id": "EV-012"}], "revision": self.calls}

    async def exercise():
        source = Wrapped()
        policy = CompetencyReviewToolset(source, ("L002", "SCI-DATA"))
        args = {"learner_id": "L002", "competency_code": "SCI-DATA"}
        ctx = SimpleNamespace(tool_call_id="read", run_id="first", run_step=1, messages=[])
        async with policy:
            result = await policy.call_tool("get_competency_evidence", args, ctx, None)
            ctx.messages = [ModelRequest(parts=[ToolReturnPart(
                "get_competency_evidence", result, tool_call_id="read",
            )])]
            ctx.run_id = "second"
            if change == "source":
                policy.wrapped = Wrapped()
                refreshed = await policy.call_tool("get_competency_evidence", args, ctx, None)
                assert "snapshot_reused" not in refreshed
                assert policy.wrapped.calls == 1
        assert not policy.snapshots
        if change == "session":
            async with policy:
                refreshed = await policy.call_tool("get_competency_evidence", args, ctx, None)
                assert "snapshot_reused" not in refreshed
                assert source.calls == 2

    asyncio.run(exercise())
