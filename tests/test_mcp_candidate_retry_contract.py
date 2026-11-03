"""Exercise real MCP schema rejection and bounded model retries without Ollama."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client
from pydantic_ai import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import RetryPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from mwalimulens.agent import orchestrator
from mwalimulens.mcp_server.server import build_server
from mwalimulens.mcp_server.state import JsonStateStore

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "data" / "synthetic"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def in_process_agent(tmp_path, monkeypatch):
    """Keep production filtering/retries; replace only the stdio transport."""

    state_path = tmp_path / "state.json"
    server = build_server(data_dir=FIXTURE_DIR, state_path=state_path)
    monkeypatch.setattr(
        orchestrator,
        "build_agent_mcp_client",
        lambda **_kwargs: Client(server, mode=orchestrator.EDUCATION_MCP_CLIENT_MODE),
    )

    def build(model):
        return orchestrator.build_agent(
            model,
            data_dir=FIXTURE_DIR,
            state_path=state_path,
            tool_error_behavior="retry",
        )

    return build, JsonStateStore(state_path)


def _candidate():
    return {
        "learner_id": "L002",
        "competency_code": "SCI-DATA",
        "claim": "Recorded assessment scores changed slightly across two terms.",
        "supporting_evidence_ids": ["EV-012", "EV-013"],
        "counter_evidence_ids": ["EV-014"],
        "uncertainty": "The later observation still records support with explaining trends.",
        "suggested_teacher_question": "Can the learner explain a new data trend independently?",
    }


def _assert_missing_question_retry(messages, state):
    retries = [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]
    assert len(retries) == 1
    assert retries[0].tool_name == "flag_pattern_for_review"
    assert "suggested_teacher_question" in str(retries[0].content)
    assert "Field required" in str(retries[0].content)
    # Argument validation occurs before the application service is entered.
    # Absence of an audit error therefore does not mean a clean first pass.
    assert [call["tool_name"] for call in state.tool_calls()] == [
        "get_competency_evidence"
    ]
    assert state.pending_reviews() == ()
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()


@pytest.mark.anyio
async def test_model_receives_complete_required_candidate_schema(in_process_agent):
    build, state = in_process_agent
    model = TestModel(call_tools=[], custom_output_text="Inspecting the tool contract.")

    await build(model).run("Inspect available tools.")

    parameters = model.last_model_request_parameters
    assert parameters is not None
    tools = {tool.name: tool for tool in parameters.function_tools}
    assert set(tools) == orchestrator.AGENT_MCP_TOOL_ALLOWLIST
    assert "record_teacher_review" not in tools
    schema = tools["flag_pattern_for_review"].parameters_json_schema
    assert set(schema["properties"]) == set(_candidate())
    assert set(schema["required"]) == set(_candidate())
    for field in ("supporting_evidence_ids", "counter_evidence_ids"):
        assert schema["properties"][field]["type"] == "array"
        assert schema["properties"][field]["items"]["type"] == "string"
    assert state.tool_calls() == ()


@pytest.mark.anyio
async def test_missing_question_can_be_corrected_once_without_human_review(in_process_agent):
    build, state = in_process_agent
    step = 0

    async def respond(messages, info):
        nonlocal step
        assert {tool.name for tool in info.function_tools} == (
            orchestrator.AGENT_MCP_TOOL_ALLOWLIST
        )
        current = step
        step += 1
        if current == 0:
            return ModelResponse(parts=[ToolCallPart(
                "get_competency_evidence",
                {"learner_id": "L002", "competency_code": "SCI-DATA"},
            )])
        if current == 1:
            incomplete = _candidate()
            del incomplete["suggested_teacher_question"]
            return ModelResponse(parts=[ToolCallPart("flag_pattern_for_review", incomplete)])
        if current == 2:
            _assert_missing_question_retry(messages, state)
            return ModelResponse(parts=[ToolCallPart("flag_pattern_for_review", _candidate())])
        assert current == 3
        return ModelResponse(parts=[TextPart("Candidate submitted for teacher review.")])

    result = await build(FunctionModel(respond)).run("Review L002 SCI-DATA evidence.")

    assert step == 4
    assert result.output == "Candidate submitted for teacher review."
    assert len(state.pending_reviews()) == 1
    assert state.pending_reviews()[0]["status"] == "pending_teacher_review"
    assert state.pending_reviews()[0]["suggested_teacher_question"] == (
        _candidate()["suggested_teacher_question"]
    )
    assert [call["tool_name"] for call in state.tool_calls()] == [
        "get_competency_evidence", "flag_pattern_for_review"
    ]
    assert all(call["status"] == "success" for call in state.tool_calls())
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()


@pytest.mark.anyio
async def test_repeated_incomplete_candidate_exhausts_retry_and_stays_failed(in_process_agent):
    build, state = in_process_agent
    step = 0

    async def respond(messages, info):
        nonlocal step
        assert "record_teacher_review" not in {tool.name for tool in info.function_tools}
        current = step
        step += 1
        if current == 0:
            return ModelResponse(parts=[ToolCallPart(
                "get_competency_evidence",
                {"learner_id": "L002", "competency_code": "SCI-DATA"},
            )])
        assert current in {1, 2}
        if current == 2:
            _assert_missing_question_retry(messages, state)
        incomplete = _candidate()
        del incomplete["suggested_teacher_question"]
        return ModelResponse(parts=[ToolCallPart("flag_pattern_for_review", incomplete)])

    with pytest.raises(UnexpectedModelBehavior, match="flag_pattern_for_review"):
        await build(FunctionModel(respond)).run("Review L002 SCI-DATA evidence.")

    assert step == 3
    assert [call["tool_name"] for call in state.tool_calls()] == [
        "get_competency_evidence"
    ]
    assert state.pending_reviews() == ()
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()
