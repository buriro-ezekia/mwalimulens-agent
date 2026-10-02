"""Tests for the PydanticAI orchestrator and strict MCP allowlist."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from mwalimulens.agent import (
    AGENT_INSTRUCTIONS,
    AGENT_MCP_TOOL_ALLOWLIST,
    build_agent,
)
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_agent_allowlist_is_exact_and_excludes_human_review() -> None:
    assert AGENT_MCP_TOOL_ALLOWLIST == {
        "get_learner_timeline",
        "get_competency_evidence",
        "flag_pattern_for_review",
    }
    assert "record_teacher_review" not in AGENT_MCP_TOOL_ALLOWLIST


def test_agent_instructions_preserve_evidence_and_human_boundaries() -> None:
    lowered = AGENT_INSTRUCTIONS.lower()

    assert "evidence ids" in lowered
    assert "counter-evidence" in lowered
    assert "uncertainty" in lowered
    assert "single score is not enough" in lowered
    assert "teacher decides" in lowered
    assert "no authority to perform the human review" in lowered


@pytest.mark.anyio
async def test_model_sees_only_agent_safe_mcp_tools(tmp_path) -> None:
    model = TestModel(call_tools=[], custom_output_text="done")
    agent = build_agent(
        model,
        data_dir=FIXTURE_DIR,
        state_path=tmp_path / "state.json",
    )

    result = await agent.run("Inspect the available learner-evidence tools.")

    assert result.output == "done"
    assert model.last_model_request_parameters is not None
    visible = {
        tool.name for tool in model.last_model_request_parameters.function_tools
    }
    assert visible == AGENT_MCP_TOOL_ALLOWLIST
    assert "record_teacher_review" not in visible


class _ReadThenSubmitCandidate:
    def __init__(self) -> None:
        self.step = 0
        self.visible_tools: list[set[str]] = []

    async def __call__(
        self,
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        del messages
        self.visible_tools.append({tool.name for tool in info.function_tools})

        if self.step == 0:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "get_competency_evidence",
                        {
                            "learner_id": "L001",
                            "competency_code": "MATH-FRACTIONS",
                        },
                    )
                ]
            )

        if self.step == 1:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "flag_pattern_for_review",
                        {
                            "learner_id": "L001",
                            "competency_code": "MATH-FRACTIONS",
                            "claim": (
                                "Fraction-equivalence evidence is repeatedly strong "
                                "across multiple terms."
                            ),
                            "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009"],
                            "counter_evidence_ids": ["EV-008"],
                            "uncertainty": (
                                "Open-ended explanation evidence remains mixed."
                            ),
                            "suggested_teacher_question": (
                                "Does this pattern hold in unfamiliar fraction problems?"
                            ),
                        },
                    )
                ]
            )

        return ModelResponse(parts=[TextPart("Candidate submitted for teacher review.")])


@pytest.mark.anyio
async def test_agent_can_retrieve_evidence_and_submit_but_not_review(tmp_path) -> None:
    scripted = _ReadThenSubmitCandidate()
    state_path = tmp_path / "state.json"
    agent = build_agent(
        FunctionModel(scripted),
        data_dir=FIXTURE_DIR,
        state_path=state_path,
    )

    result = await agent.run("Assess L001's longitudinal fraction evidence.")

    assert result.output == "Candidate submitted for teacher review."
    assert scripted.visible_tools
    assert all(
        visible == AGENT_MCP_TOOL_ALLOWLIST for visible in scripted.visible_tools
    )

    state = JsonStateStore(state_path)
    assert len(state.pending_reviews()) == 1
    assert state.pending_reviews()[0]["status"] == "pending_teacher_review"
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()

    audited = [item["tool_name"] for item in state.tool_calls()]
    assert audited == [
        "get_competency_evidence",
        "flag_pattern_for_review",
    ]



class _AttemptForbiddenTeacherReview:
    def __init__(self) -> None:
        self.step = 0

    async def __call__(
        self,
        messages: list[ModelMessage],
        info: AgentInfo,
    ) -> ModelResponse:
        del messages
        assert "record_teacher_review" not in {
            tool.name for tool in info.function_tools
        }

        if self.step == 0:
            self.step += 1
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "record_teacher_review",
                        {
                            "review_id": "review-invented",
                            "reviewer_id": "agent-must-not-decide",
                            "decision": "approve",
                            "reason": "This call must never be dispatched.",
                        },
                    )
                ]
            )

        return ModelResponse(parts=[TextPart("Human review tool is unavailable to the agent.")])


@pytest.mark.anyio
async def test_invented_human_review_call_is_not_dispatched(tmp_path) -> None:
    state_path = tmp_path / "state.json"
    agent = build_agent(
        FunctionModel(_AttemptForbiddenTeacherReview()),
        data_dir=FIXTURE_DIR,
        state_path=state_path,
    )

    result = await agent.run("Try to approve a learner pattern yourself.")

    assert result.output == "Human review tool is unavailable to the agent."

    state = JsonStateStore(state_path)
    assert state.teacher_reviews() == ()
    assert state.profile_updates() == ()
    assert all(
        call["tool_name"] != "record_teacher_review"
        for call in state.tool_calls()
    )
