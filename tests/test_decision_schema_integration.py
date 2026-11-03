"""Real MCP, mocked inference: contract versioning must not change teacher authority."""

from __future__ import annotations

import asyncio
import json
import subprocess
from copy import deepcopy

import pytest
from fastmcp import Client

from mwalimulens import structured_review
from mwalimulens.agent.candidate_contract import (
    DECISION_POLICY_ID,
    DECISION_SCHEMA_IDS,
    DEFAULT_DECISION_SCHEMA_ID,
    OUTCOME_DECISION_SCHEMA_ID,
    decision_schema,
    decision_schema_metadata,
)
from mwalimulens.agent.execution import ExecutionLimits
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.orchestrator import EDUCATION_MCP_CLIENT_MODE
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import scenario_by_id


def proposal(reason=None):
    return {
        "outcome": "candidate", "abstention_reason": reason,
        "candidate": {
            "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
            "claim": "Later recorded scores were higher, while explanation remained mixed.",
            "supporting_evidence_ids": ["EV-001", "EV-004", "EV-007"],
            "counter_evidence_ids": ["EV-008"],
            "uncertainty": "Independent reasoning needs verification on comparable new tasks.",
            "suggested_teacher_question": "Can the learner justify an unfamiliar task unaided?",
        },
    }


@pytest.fixture
def case_setup(tmp_path, monkeypatch):
    paths = {name: tmp_path / f"{name.removesuffix('_path')}.json" for name in (
        "state_path", "report_path", "result_path",
    )}
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=paths["state_path"])
    monkeypatch.setattr(structured_review, "build_agent_mcp_client", lambda **_kw: Client(
        server, mode=EDUCATION_MCP_CLIENT_MODE,
    ))
    return {**paths, "settings": OllamaSettings()}, JsonStateStore(paths["state_path"])


def install_generator(monkeypatch, outputs, inspect=None):
    calls = []

    class Generator:
        def __init__(self, **_kw):
            pass

        async def __call__(self, messages, schema):
            calls.append((deepcopy(messages), deepcopy(schema)))
            if inspect is not None:
                inspect()
            output = outputs[min(len(calls) - 1, len(outputs) - 1)]
            if isinstance(output, BaseException):
                raise output
            return json.dumps(output)

    monkeypatch.setattr(structured_review, "OllamaJsonGenerator", Generator)
    return calls


def assert_metadata(args, schema_id):
    expected = decision_schema_metadata(schema_id)
    for path in (args["report_path"], args["result_path"],
                 args["report_path"].with_suffix(".progress.json")):
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert all(saved[key] == value for key, value in expected.items())
        assert saved["decision_policy_id"] == DECISION_POLICY_ID
        for stage in saved["outcome_stages"]:
            assert all(stage[key] == value for key, value in expected.items())
            assert stage["decision_policy_id"] == DECISION_POLICY_ID


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_mcp_submission_and_all_artifacts_identify_exact_wire_schema(
    case_setup, monkeypatch, schema_id,
):
    args, store = case_setup

    def inspect_checkpoint():
        checkpoint = json.loads(
            args["report_path"].with_suffix(".progress.json").read_text(encoding="utf-8")
        )
        assert checkpoint["status"] == "in_progress"
        for key, value in decision_schema_metadata(schema_id).items():
            assert checkpoint[key] == value

    calls = install_generator(monkeypatch, [proposal()], inspect_checkpoint)
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args, decision_schema_id=schema_id,
    ))
    assert result["status"] == "pass"
    assert calls[0][1] == decision_schema(schema_id)
    assert len(store.pending_reviews()) == 1
    assert store.teacher_reviews() == store.profile_updates() == ()
    assert [event["tool_name"] for event in store.tool_calls()] == [
        "get_competency_evidence", "flag_pattern_for_review",
    ]
    assert store.tool_calls()[1]["inputs"] == proposal()["candidate"]
    assert result["submission_actor"] == "application_controller"
    assert result["model_tool_selection_evaluated"] is False
    assert result["semantic_quality_verified"] is False
    assert_metadata(args, schema_id)


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_provider_ignoring_schema_cannot_make_string_null_reach_mcp(
    case_setup, monkeypatch, schema_id,
):
    args, store = case_setup
    calls = install_generator(monkeypatch, [proposal("null")])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args, decision_schema_id=schema_id,
    ))
    assert result["status"] == "fail" and result["proposal_status"] == "invalid_proposal"
    assert len(calls) == 2
    assert all(stage["status"] == "fail" for stage in result["outcome_stages"])
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()
    assert [event["tool_name"] for event in store.tool_calls()] == ["get_competency_evidence"]
    assert_metadata(args, schema_id)


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_single_term_abstention_remains_valid_with_no_write(case_setup, monkeypatch, schema_id):
    args, store = case_setup
    calls = install_generator(monkeypatch, [{
        "outcome": "abstain", "candidate": None,
        "abstention_reason": "One recorded term cannot support a cross-term description.",
    }])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("single-assessment"), **args, decision_schema_id=schema_id,
    ))
    assert result["status"] == "pass" and result["proposal_status"] == "abstained"
    assert len(calls) == 1
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()
    assert_metadata(args, schema_id)


def test_opt_in_keeps_original_repair_budget(case_setup, monkeypatch):
    args, store = case_setup
    calls = install_generator(monkeypatch, [proposal("null"), proposal()])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
        decision_schema_id=OUTCOME_DECISION_SCHEMA_ID, execution_limits=ExecutionLimits(1, 540),
    ))
    assert result["status"] == "fail" and len(calls) == 1
    assert store.pending_reviews() == ()
    assert_metadata(args, OUTCOME_DECISION_SCHEMA_ID)


def test_valid_model_authored_repair_keeps_initial_failure(case_setup, monkeypatch):
    args, store = case_setup
    calls = install_generator(monkeypatch, [proposal("null"), proposal()])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
        decision_schema_id=OUTCOME_DECISION_SCHEMA_ID,
    ))
    assert len(calls) == 2
    assert [(stage["stage"], stage["status"]) for stage in result["outcome_stages"]] == [
        ("initial", "fail"), ("proposal_repair", "pass"),
    ]
    assert len(store.pending_reviews()) == 1
    assert store.teacher_reviews() == store.profile_updates() == ()
    assert_metadata(args, OUTCOME_DECISION_SCHEMA_ID)


def test_default_still_uses_legacy_schema(case_setup, monkeypatch):
    args, _store = case_setup
    calls = install_generator(monkeypatch, [proposal()])
    asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    assert calls[0][1] == decision_schema(DEFAULT_DECISION_SCHEMA_ID)
    assert_metadata(args, DEFAULT_DECISION_SCHEMA_ID)


def test_unknown_schema_stops_before_creating_output_or_contacting_mcp(tmp_path, monkeypatch):
    def forbidden(**_kw):
        pytest.fail("Unknown schema must fail before MCP")

    monkeypatch.setattr(structured_review, "build_agent_mcp_client", forbidden)
    with pytest.raises(ValueError, match="Unknown decision schema"):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), state_path=tmp_path / "state.json",
            report_path=tmp_path / "report.json", result_path=tmp_path / "result.json",
            settings=OllamaSettings(), decision_schema_id="unreviewed",
        ))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_cancelled_stage_keeps_schema_provenance(case_setup, monkeypatch, schema_id):
    args, store = case_setup
    install_generator(monkeypatch, [asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), **args, decision_schema_id=schema_id,
        ))
    result = json.loads(args["result_path"].read_text(encoding="utf-8"))
    assert result["status"] == "fail" and result["active_stage_outcome"] == "unknown"
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()
    assert_metadata(args, schema_id)


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_cli_forwards_schema_to_child_and_records_summary(tmp_path, monkeypatch, schema_id):
    observed = {}

    def fake_suite(**kwargs):
        observed.update(kwargs)
        return {"summary_path": str(tmp_path / "summary.json"), "status": "fail",
                "passed": 0, "scenario_count": 1}

    def fake_run(command, **kwargs):
        observed["command"] = command
        return subprocess.CompletedProcess(command, 2)

    monkeypatch.setattr(structured_review, "run_suite", fake_suite)
    monkeypatch.setattr(structured_review.subprocess, "run", fake_run)
    assert structured_review.main([
        "--decision-schema", schema_id, "--output-dir", str(tmp_path),
    ]) == 2
    child = ["python", "-m", "mwalimulens.multi_scenario_eval", "--single-run"]
    observed["runner"](child, timeout=600)
    assert observed["command"][-2:] == ["--decision-schema", schema_id]
    assert child[2] == "mwalimulens.multi_scenario_eval"  # No mutation of the parent's command.
    saved = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert all(saved[key] == val for key, val in decision_schema_metadata(schema_id).items())
    assert saved["decision_policy_id"] == DECISION_POLICY_ID
    assert saved["model_tool_selection_evaluated"] is False
