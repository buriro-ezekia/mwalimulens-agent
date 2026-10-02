"""In-process protocol contract tests for the custom Education MCP server."""

from __future__ import annotations

from pathlib import Path

import pytest
from mcp import Client

from mwalimulens.mcp_server.server import build_server
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "data" / "synthetic"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def mcp_client(tmp_path):
    state_path = tmp_path / "mcp-state.json"
    server = build_server(data_dir=FIXTURE_DIR, state_path=state_path)
    async with Client(server, raise_exceptions=True) as client:
        yield client, JsonStateStore(state_path)


@pytest.mark.anyio
async def test_server_negotiates_current_protocol_and_lists_four_tools(mcp_client) -> None:
    client, _ = mcp_client

    result = await client.list_tools()
    names = {tool.name for tool in result.tools}

    assert client.protocol_version == "2026-07-28"
    assert names == {
        "get_learner_timeline",
        "get_competency_evidence",
        "flag_pattern_for_review",
        "record_teacher_review",
    }


@pytest.mark.anyio
async def test_timeline_tool_returns_structured_content(mcp_client) -> None:
    client, state_store = mcp_client

    result = await client.call_tool("get_learner_timeline", {"learner_id": "L001"})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["learner"]["learner_id"] == "L001"
    assert result.structured_content["evidence_count"] == 11
    assert len(state_store.tool_calls()) == 1


@pytest.mark.anyio
async def test_action_tool_persists_pending_review_not_approval(mcp_client) -> None:
    client, state_store = mcp_client

    result = await client.call_tool(
        "flag_pattern_for_review",
        {
            "learner_id": "L001",
            "competency_code": "MATH-FRACTIONS",
            "claim": "Fraction-equivalence evidence is repeatedly strong across terms.",
            "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009"],
            "counter_evidence_ids": ["EV-008"],
            "uncertainty": "Open-ended explanation evidence is mixed.",
            "suggested_teacher_question": "Does this hold in an unfamiliar problem?",
        },
    )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["status"] == "pending_teacher_review"

    reviews = state_store.pending_reviews()
    assert len(reviews) == 1
    assert reviews[0]["status"] == "pending_teacher_review"
    assert "approved" not in reviews[0]["status"]


@pytest.mark.anyio
async def test_tool_failure_returns_error_and_is_audited(mcp_client) -> None:
    client, state_store = mcp_client

    result = await client.call_tool("get_learner_timeline", {"learner_id": "L999"})

    assert result.is_error is True
    calls = state_store.tool_calls()
    assert len(calls) == 1
    assert calls[0]["status"] == "error"
    assert calls[0]["error"]["type"] == "KeyError"


async def _flag_candidate(client):
    result = await client.call_tool(
        "flag_pattern_for_review",
        {
            "learner_id": "L001",
            "competency_code": "MATH-FRACTIONS",
            "claim": "Fraction-equivalence evidence is repeatedly strong across terms.",
            "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009"],
            "counter_evidence_ids": ["EV-008"],
            "uncertainty": "Open-ended explanation evidence is mixed.",
            "suggested_teacher_question": "Does this hold in an unfamiliar problem?",
        },
    )
    assert result.is_error is False
    assert result.structured_content is not None
    return result.structured_content["review_id"]


@pytest.mark.anyio
async def test_teacher_approve_creates_human_gated_profile_update(mcp_client) -> None:
    client, state_store = mcp_client
    review_id = await _flag_candidate(client)

    result = await client.call_tool(
        "record_teacher_review",
        {
            "review_id": review_id,
            "reviewer_id": "teacher-mcp-001",
            "decision": "approve",
            "reason": "Approved after reviewing the cited evidence.",
        },
    )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["teacher_review"]["decision"] == "approve"
    assert result.structured_content["profile_update"] is not None
    assert len(state_store.teacher_reviews()) == 1
    assert len(state_store.profile_updates()) == 1


@pytest.mark.anyio
async def test_teacher_edit_uses_human_revised_claim(mcp_client) -> None:
    client, state_store = mcp_client
    review_id = await _flag_candidate(client)
    edited_claim = "Evidence is promising, with mixed open-ended explanation evidence."

    result = await client.call_tool(
        "record_teacher_review",
        {
            "review_id": review_id,
            "reviewer_id": "teacher-mcp-002",
            "decision": "edit",
            "reason": "The teacher narrowed the claim to reflect the counter-evidence.",
            "edited_claim": edited_claim,
        },
    )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["teacher_review"]["final_claim"] == edited_claim
    assert result.structured_content["profile_update"]["claim"] == edited_claim
    assert state_store.profile_updates()[0]["claim"] == edited_claim


@pytest.mark.anyio
async def test_teacher_reject_creates_no_profile_update(mcp_client) -> None:
    client, state_store = mcp_client
    review_id = await _flag_candidate(client)

    result = await client.call_tool(
        "record_teacher_review",
        {
            "review_id": review_id,
            "reviewer_id": "teacher-mcp-003",
            "decision": "reject",
            "reason": "The evidence is too mixed for a learner-profile statement.",
        },
    )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["teacher_review"]["decision"] == "reject"
    assert result.structured_content["profile_update"] is None
    assert state_store.profile_updates() == ()
