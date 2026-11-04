"""Real in-process MCP validates structured workflow; inference is mocked, not Qwen."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import replace

import pytest
from fastmcp import Client

from mwalimulens import structured_review
from mwalimulens.agent.candidate_contract import (
    DECISION_POLICY_ID,
    EvidenceSnapshot,
    review_messages,
)
from mwalimulens.agent.execution import ExecutionLimits
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.orchestrator import EDUCATION_MCP_CLIENT_MODE
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import SCENARIOS, scenario_by_id


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


def assert_policy_metadata(args):
    for path in (
        args["report_path"], args["result_path"],
        args["report_path"].with_suffix(".progress.json"),
    ):
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["decision_policy_id"] == DECISION_POLICY_ID
        for stage in report["outcome_stages"]:
            assert stage["decision_policy_id"] == DECISION_POLICY_ID


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
    assert_policy_metadata(args)


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
    assert_policy_metadata(args)


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
    assert_policy_metadata(args)


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
    assert_policy_metadata(args)


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
    assert_policy_metadata(args)


def test_existing_files_are_not_overwritten(setup_case, monkeypatch):
    args, _store = setup_case
    args["state_path"].write_text('{"historical":true}', encoding="utf-8")
    with pytest.raises(FileExistsError):
        asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), **args,
        ))
    assert args["state_path"].read_text(encoding="utf-8") == '{"historical":true}'


@pytest.mark.parametrize(
    "name", ["evidence_snapshot.json", "report.progress.json", "proposals.json"],
)
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


@pytest.mark.parametrize(
    "name", ["evidence_snapshot.json", "report.progress.json", "proposals.json"],
)
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


def abstention(reason):
    return {"outcome": "abstain", "candidate": None, "abstention_reason": reason}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda case: case.ident)
def test_shared_policy_preserves_complete_source_evidence(
    setup_case, monkeypatch, scenario,
):
    args, store = setup_case
    source_before = {
        path: path.read_bytes()
        for path in DEFAULT_DATA_DIR.rglob("*") if path.is_file()
    }
    calls = fake_generator(monkeypatch, [abstention(
        "The available records do not support a defensible bounded statement."
    )])
    asyncio.run(structured_review.run_structured_case(scenario, **args))

    payload = store.tool_calls()[0]["output"]
    snapshot = EvidenceSnapshot.from_mcp(
        payload, (scenario.learner, scenario.competency),
    )
    unrelated = EvidenceSnapshot.from_mcp({
        "learner_id": "UNRELATED", "competency_code": "OTHER",
        "evidence_count": 0, "evidence": [],
    }, ("UNRELATED", "OTHER"))
    assert len(calls) == 1
    assert calls[0][0] == [
        review_messages(unrelated)[0],
        {"role": "user", "content": snapshot.payload_json},
    ]
    policy = calls[0][0][0]["content"]
    for identifier in (scenario.ident, scenario.learner, scenario.competency):
        assert identifier not in policy
    for row in snapshot.records:
        for field in ("evidence_id", "term_id", "source_ref"):
            assert row[field] not in policy
        if row["score"] is not None:
            assert str(row["score"]) not in policy
    for field in ("claim", "uncertainty", "suggested_teacher_question"):
        assert proposal()["candidate"][field] not in policy
    saved = json.loads(
        args["state_path"].with_name("evidence_snapshot.json").read_text(encoding="utf-8")
    )
    assert saved == {"sha256": snapshot.sha256, "payload": payload}
    assert {
        path: path.read_bytes()
        for path in DEFAULT_DATA_DIR.rglob("*") if path.is_file()
    } == source_before
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()
    assert_policy_metadata(args)


def test_expected_outcome_and_scenario_labels_cannot_change_model_input(
    setup_case, monkeypatch,
):
    args, _store = setup_case
    original = scenario_by_id("longitudinal-pattern")
    changed = replace(
        original, expected="abstain",
        ident="HIDDEN_SCENARIO_LABEL", category="HIDDEN_CATEGORY_LABEL",
    )
    calls = fake_generator(monkeypatch, [abstention(
        "Comparability of these tasks prevents a defensible statement."
    )])
    first = asyncio.run(structured_review.run_structured_case(original, **args))

    changed_args = dict(args)
    for key in ("state_path", "report_path", "result_path"):
        changed_args[key] = args[key].parent / "changed" / args[key].name
    server = build_server(
        data_dir=DEFAULT_DATA_DIR, state_path=changed_args["state_path"],
    )
    monkeypatch.setattr(
        structured_review, "build_agent_mcp_client",
        lambda **_kw: Client(server, mode=EDUCATION_MCP_CLIENT_MODE),
    )
    second = asyncio.run(structured_review.run_structured_case(changed, **changed_args))

    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert "HIDDEN_SCENARIO_LABEL" not in json.dumps(calls)
    assert "HIDDEN_CATEGORY_LABEL" not in json.dumps(calls)
    assert first["status"] == "fail"
    assert second["status"] == "pass"
    assert first["proposal_status"] == second["proposal_status"] == "abstained"


@pytest.mark.parametrize("reason", [
    "Comparability of these tasks prevents a defensible statement.",
    "Insufficient consistent improvement or independent mastery to determine "
    "a candidate based on the provided evidence.",
    "The available observations do not support a defensible bounded statement.",
])
def test_valid_abstention_is_not_retried_to_satisfy_expected_candidate(
    setup_case, monkeypatch, reason,
):
    args, store = setup_case
    calls = fake_generator(monkeypatch, [abstention(reason)])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    report = json.loads(args["report_path"].read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert result["status"] == "fail"
    assert result["proposal_status"] == "abstained"
    assert report["final_output"] == "ABSTAIN: " + reason
    assert report["proposal_attempts"] == [
        {"attempt": 1, "status": "valid", "outcome": "abstain"},
    ]
    assert [call["tool_name"] for call in store.tool_calls()] == [
        "get_competency_evidence",
    ]
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()


def test_cli_summary_records_decision_policy_without_running_a_model(tmp_path, monkeypatch):
    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr(structured_review, "run_suite", lambda **_kw: {
        "summary_path": str(summary_path), "status": "fail",
        "passed": 0, "scenario_count": 1,
    })
    assert structured_review.main(["--output-dir", str(tmp_path)]) == 2
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["decision_policy_id"] == DECISION_POLICY_ID
    assert summary["workflow_mode"] == "structured_proposal_v1"
    assert summary["model_tool_selection_evaluated"] is False


def test_in_progress_checkpoint_identifies_policy_before_model_response(setup_case, monkeypatch):
    args, _store = setup_case

    class InspectCheckpoint:
        def __init__(self, **_kwargs):
            pass

        async def __call__(self, _messages, _schema):
            checkpoint = json.loads(
                args["report_path"].with_suffix(".progress.json").read_text(encoding="utf-8")
            )
            assert checkpoint["status"] == "in_progress"
            assert checkpoint["decision_policy_id"] == DECISION_POLICY_ID
            return json.dumps(abstention("No defensible bounded statement is supported."))

    monkeypatch.setattr(structured_review, "OllamaJsonGenerator", InspectCheckpoint)
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    assert result["proposal_status"] == "abstained"


def test_raw_proposals_preserve_invalid_and_repaired_outputs_outside_telemetry(
    setup_case, monkeypatch,
):
    args, store = setup_case
    raw_outputs = [
        '  {"outcome": "candidate", "abstention_reason": "null", "candidate": {}}\n',
        json.dumps(proposal(), indent=2) + "\n",
    ]
    inputs = []

    class Generate:
        def __init__(self, **_kwargs):
            pass

        async def __call__(self, messages, schema):
            saved = json.loads(args["state_path"].with_name("proposals.json").read_text())
            assert saved["attempts"][-1]["status"] == "started"
            inputs.append(json.loads(json.dumps({"messages": messages, "format": schema})))
            return raw_outputs[len(inputs) - 1]

    monkeypatch.setattr(structured_review, "OllamaJsonGenerator", Generate)
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    saved = json.loads(args["state_path"].with_name("proposals.json").read_text())
    assert [attempt["raw_output"] for attempt in saved["attempts"]] == raw_outputs
    assert [attempt["generation_input"] for attempt in saved["attempts"]] == inputs
    assert [attempt["raw_output_sha256"] for attempt in saved["attempts"]] == [
        hashlib.sha256(raw.encode()).hexdigest() for raw in raw_outputs
    ]
    assert result["status"] == "pass"
    assert len(store.pending_reviews()) == 1
    report = json.loads(args["report_path"].read_text())
    assert saved["evidence_sha256"] == report["evidence_sha256"]
    assert saved["decision_schema_sha256"] == report["decision_schema_sha256"]
    assert "generation_input" not in json.dumps(report["model_requests"])
    assert "raw_output" not in json.dumps(report["events"])


def test_interrupted_generation_has_no_fabricated_raw_proposal(setup_case, monkeypatch):
    args, store = setup_case
    fake_generator(monkeypatch, [RuntimeError("Provider failed before returning")])
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    attempt = json.loads(args["state_path"].with_name("proposals.json").read_text())["attempts"][0]
    assert result["status"] == "fail"
    assert attempt["status"] == "started"
    assert attempt["raw_output"] is None
    assert "raw_output_sha256" not in attempt
    assert store.pending_reviews() == ()


def test_proposal_persistence_failure_prevents_candidate_submission(setup_case, monkeypatch):
    args, store = setup_case
    calls = fake_generator(monkeypatch, [proposal()])
    real_write = structured_review.atomic_json

    def write(path, payload):
        if path.name == "proposals.json" and payload["attempts"][-1]["status"] == "returned":
            raise OSError("Synthetic disk failure")
        real_write(path, payload)

    monkeypatch.setattr(structured_review, "atomic_json", write)
    result = asyncio.run(structured_review.run_structured_case(
        scenario_by_id("longitudinal-pattern"), **args,
    ))
    assert len(calls) == 1
    assert result["status"] == "fail"
    assert store.pending_reviews() == store.teacher_reviews() == store.profile_updates() == ()
