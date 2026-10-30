"""Real in-process MCP validates structured workflow; inference is mocked, not Qwen."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastmcp import Client

from mwalimulens import structured_review
from mwalimulens.agent.execution import ExecutionLimits
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.orchestrator import EDUCATION_MCP_CLIENT_MODE
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import scenario_by_id


def proposal():
    return {
        "outcome": "candidate", "abstention_reason": None,
        "candidate": {
            "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
            "claim": "Recorded fraction scores increased, while explanation remained mixed.",
            "supporting_evidence_ids": ["EV-001", "EV-004", "EV-007"],
            "counter_evidence_ids": ["EV-008"],
            "uncertainty": "Independent explanation still needs verification on a new task.",
            "suggested_teacher_question": "Can the learner explain a new task unaided?",
        },
    }


@pytest.fixture
def setup_case(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=state_path)
    monkeypatch.setattr(
        structured_review, "build_agent_mcp_client",
        lambda **_kw: Client(server, mode=EDUCATION_MCP_CLIENT_MODE),
    )
    settings = OllamaSettings()
    args = {
        "state_path": state_path, "report_path": tmp_path / "report.json",
        "result_path": tmp_path / "result.json", "settings": settings,
    }
    return args, JsonStateStore(state_path)


def fake_generator(monkeypatch, responses):
    calls = []

    class Generate:
        def __init__(self, **_kw):
            pass

        async def __call__(self, messages, schema):
            calls.append((messages, schema))
            response = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(response, BaseException):
                raise response
            return json.dumps(response)

    monkeypatch.setattr(structured_review, "OllamaJsonGenerator", Generate)
    return calls


def test_native_proposal_causes_one_real_mcp_action_after_validation(setup_case, monkeypatch):
    args, store = setup_case
    calls = fake_generator(monkeypatch, [proposal()])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    assert result["status"] == "pass"
    assert result["model_tool_selection_evaluated"] is False
    assert result["submission_actor"] == "application_controller"
    assert len(calls) == 1
    assert "EV-008" in calls[0][0][1]["content"]
    assert len(store.pending_reviews()) == 1
    assert store.teacher_reviews() == store.profile_updates() == ()
    assert [x["tool_name"] for x in store.tool_calls()] == [
        "get_competency_evidence", "flag_pattern_for_review",
    ]
    raw = json.loads(args["report_path"].read_text(encoding="utf-8"))
    assert raw["workflow_mode"] == "structured_proposal_v1"
    assert raw["outcome_stages"][0]["stage"] == "initial"
    assert raw["proposal_attempts"][0]["status"] == "valid"


def test_missing_claim_and_question_never_reach_mcp_until_model_repairs(setup_case, monkeypatch):
    args, store = setup_case
    bad = proposal()
    del bad["candidate"]["claim"]
    del bad["candidate"]["suggested_teacher_question"]
    calls = fake_generator(monkeypatch, [bad, proposal()])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    assert len(calls) == 2
    assert result["status"] == "pass"
    assert [(x["stage"], x["status"]) for x in result["outcome_stages"]] == [
        ("initial", "fail"), ("proposal_repair", "pass"),
    ]
    assert len(store.pending_reviews()) == 1
    assert len(store.tool_calls()) == 2
    assert store.teacher_reviews() == store.profile_updates() == ()


def test_repeated_invalid_proposal_does_not_write_candidate(setup_case, monkeypatch):
    args, store = setup_case
    bad = proposal()
    del bad["candidate"]["claim"]
    fake_generator(monkeypatch, [bad])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    assert result["status"] == "fail"
    assert result["proposal_status"] == "invalid_proposal"
    assert store.pending_reviews() == ()
    assert [x["tool_name"] for x in store.tool_calls()] == ["get_competency_evidence"]


def test_explicit_single_assessment_abstention_does_not_submit(setup_case, monkeypatch):
    args, store = setup_case
    fake_generator(monkeypatch, [{
        "outcome": "abstain", "candidate": None,
        "abstention_reason": "Only one term is recorded; cross-term comparison is unavailable.",
    }])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("single-assessment"), **args,
    ))
    assert result["status"] == "pass"
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()


def test_shared_one_request_budget_does_not_reset_for_proposal_repair(setup_case, monkeypatch):
    args, store = setup_case
    bad = proposal()
    del bad["candidate"]["claim"]
    calls = fake_generator(monkeypatch, [bad, proposal()])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
        execution_limits=ExecutionLimits(request_limit=1),
    ))
    assert result["status"] == "fail"
    assert len(calls) == 1
    assert store.pending_reviews() == ()


def test_cancelled_inference_preserves_failed_result_and_propagates(setup_case, monkeypatch):
    args, store = setup_case
    fake_generator(monkeypatch, [asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), **args,
        ))
    report = json.loads(args["report_path"].read_text(encoding="utf-8"))
    assert report["status"] == "fail"
    assert report["termination"]["reason"] == "cancelled"
    assert report["active_stage_outcome"] == "unknown"
    assert args["result_path"].exists()
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()


def test_existing_files_are_not_overwritten(setup_case, monkeypatch):
    args, _store = setup_case
    args["state_path"].write_text('{"historical":true}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), **args,
        ))
    assert args["state_path"].read_text(encoding="utf-8") == '{"historical":true}'


@pytest.mark.parametrize("name", ["evidence_snapshot.json", "report.progress.json"])
def test_existing_derived_artifacts_are_not_overwritten(setup_case, monkeypatch, name):
    args, store = setup_case
    historical = args["state_path"].with_name(name)
    historical.write_bytes(b'{"historical":true}')
    calls = fake_generator(monkeypatch, [proposal()])
    with pytest.raises(FileExistsError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), **args,
        ))
    assert historical.read_bytes() == b'{"historical":true}'
    assert calls == []
    assert store.tool_calls() == ()


@pytest.mark.parametrize("name", ["evidence_snapshot.json", "report.progress.json"])
def test_explicit_paths_cannot_alias_derived_artifacts(setup_case, monkeypatch, name):
    args, store = setup_case
    args["result_path"] = args["state_path"].with_name(name)
    calls = fake_generator(monkeypatch, [proposal()])
    with pytest.raises(ValueError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), **args,
        ))
    assert calls == []
    assert store.tool_calls() == ()
