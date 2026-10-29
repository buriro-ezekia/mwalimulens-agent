"""Multi-scenario acceptance tests use only fictional fixtures, never live Qwen."""

from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.open_weights_run import build_open_weights_report
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import (
    SCENARIOS,
    diagnose_saved_suite,
    evidence_preflight,
    grade_scenario,
    main,
    run_one,
    run_suite,
    scenario_by_id,
    scenario_prompt,
    select_scenarios,
    validate_scenario_fixtures,
)


def make_service(tmp_path):
    state = JsonStateStore(tmp_path / "state.json")
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR), state)
    return state, service


def make_report(state, scenario, *, response):
    time = datetime(2026, 10, 29, tzinfo=UTC)
    return build_open_weights_report(
        settings=OllamaSettings(),
        prompt=scenario_prompt(scenario),
        prompt_style="scenario",
        final_output=response,
        state_store=state,
        started_at=time,
        finished_at=time,
        evaluation_target=(scenario.learner, scenario.competency),
        expected_outcome=scenario.expected,
    )


def test_four_fixture_scenarios_are_genuinely_distinct():
    validate_scenario_fixtures()
    assert len(SCENARIOS) == 4
    assert {case.category for case in SCENARIOS} == {
        "supported", "mixed", "sparse", "missing",
    }


def test_scenario_prompt_does_not_give_away_expected_outcome():
    for scenario in SCENARIOS:
        text = scenario_prompt(scenario)
        assert scenario.learner in text
        assert scenario.competency in text
        assert "ABSTAIN:" in text
        assert "flag_pattern_for_review" in text
        assert "get_competency_evidence" in text
        assert "pending_teacher_review" not in text


@pytest.mark.parametrize("ident", ["single-assessment", "missing-competency"])
def test_sparse_and_missing_evidence_require_explicit_abstention(tmp_path, ident):
    scenario = scenario_by_id(ident)
    state, service = make_service(tmp_path)
    service.get_competency_evidence(scenario.learner, scenario.competency)
    report = make_report(
        state, scenario, response="ABSTAIN: No defensible cross-term history.",
    )
    assert report["status"] == "pass"
    assert grade_scenario(report, scenario)["status"] == "pass"
    assert len(state.pending_reviews()) == 0
    assert not state.profile_updates()


def test_unqualified_abstention_does_not_pass(tmp_path):
    scenario = scenario_by_id("single-assessment")
    state, service = make_service(tmp_path)
    service.get_competency_evidence(scenario.learner, scenario.competency)
    report = make_report(state, scenario, response="Maybe later.")
    assert report["status"] == "fail"
    assert grade_scenario(report, scenario)["status"] == "fail"


@pytest.mark.parametrize(
    ("ident", "supports", "counter"),
    [
        ("longitudinal-pattern", ["EV-004", "EV-007"], ["EV-008"]),
        ("conflicting-evidence", ["EV-012", "EV-013"], ["EV-014"]),
    ],
)
def test_supported_and_conflicted_candidates_remain_human_gated(
    tmp_path, ident, supports, counter,
):
    scenario = scenario_by_id(ident)
    state, service = make_service(tmp_path)
    service.get_competency_evidence(scenario.learner, scenario.competency)
    service.flag_pattern_for_review(
        learner_id=scenario.learner,
        competency_code=scenario.competency,
        claim="Assessment performance improved across the observed terms.",
        supporting_evidence_ids=supports,
        counter_evidence_ids=counter,
        uncertainty="Independent explanation has not been established.",
        suggested_teacher_question="Can the learner explain a new example unaided?",
    )
    report = make_report(state, scenario, response="Candidate submitted.")
    assert report["status"] == "pass"
    grade = grade_scenario(report, scenario)
    assert grade["status"] == "pass"
    assert grade["manual_semantic_review_required"]
    assert grade["semantic_quality_verified"] is False
    assert len(state.pending_reviews()) == 1
    assert not state.teacher_reviews()
    assert not state.profile_updates()


def test_single_term_support_does_not_satisfy_longitudinal_rubric(tmp_path):
    scenario = scenario_by_id("longitudinal-pattern")
    state, service = make_service(tmp_path)
    service.get_competency_evidence(scenario.learner, scenario.competency)
    service.flag_pattern_for_review(
        learner_id=scenario.learner,
        competency_code=scenario.competency,
        claim="Two observations were recorded together.",
        supporting_evidence_ids=["EV-001", "EV-002"],
        counter_evidence_ids=["EV-008"],
        uncertainty="A trend cannot be inferred from this term alone.",
        suggested_teacher_question="Would later term work support this observation?",
    )
    report = make_report(state, scenario, response="Candidate submitted.")
    assert report["status"] == "pass"
    checked = grade_scenario(report, scenario)
    assert checked["status"] == "fail"
    assert not checked["checks"]["supporting_evidence_spans_terms"]


def test_run_suite_persists_each_scenario_result_without_model_calls(
    tmp_path, monkeypatch,
):
    def fake_runner(command, **kwargs):
        output = command[command.index("--result") + 1]

        Path(output).write_text(
            json.dumps({"status": "pass", "checks": {"test": True}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="Synthetic", stderr="")

    monkeypatch.setattr("mwalimulens.multi_scenario_eval.validate_scenario_fixtures",
                        lambda: None)
    result = run_suite(output_root=tmp_path, runner=fake_runner)
    assert result["status"] == "pass"
    assert result["passed"] == 4
    assert result["semantic_quality_verified"] is False
    stored = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert stored["scenario_count"] == 4


def test_run_suite_does_not_hide_timeout(tmp_path, monkeypatch):
    def timeout_runner(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 600)

    monkeypatch.setattr("mwalimulens.multi_scenario_eval.validate_scenario_fixtures",
                        lambda: None)
    result = run_suite(output_root=tmp_path, runner=timeout_runner)
    assert result["status"] == "fail"
    assert result["failed"] == len(SCENARIOS)
    assert all(item["returncode"] is None for item in result["results"])
    assert all("Timeout" in item["failure"] for item in result["results"])


def test_unknown_scenario_is_rejected():
    with pytest.raises(ValueError, match="Unknown scenario"):
        scenario_by_id("not-a-scenario")

def test_scenario_prompt_distinguishes_numeric_and_qualitative_evidence():
    prompt = scenario_prompt(scenario_by_id("conflicting-evidence"))
    assert "assessment scores" in prompt
    assert "classroom observation" in prompt
    assert "observation has no score" in prompt
    assert "counter-evidence" in prompt
    assert "consistent improvement" in prompt
    assert "EV-014" not in prompt
    assert "72%" not in prompt
    assert "75%" not in prompt


def test_shared_prompt_requires_abstention_when_only_one_term():
    for scenario in SCENARIOS:
        text = scenario_prompt(scenario)
        assert "fewer than two distinct terms" in text
        assert "ABSTAIN:" in text
        assert "two or more supporting evidence IDs" in text
        assert "counter_evidence_ids" in text
        assert scenario.expected not in text.split("Apply this decision process")[0]


def test_counter_evidence_omission_remains_a_failure(tmp_path):
    scenario = scenario_by_id("conflicting-evidence")
    state, service = make_service(tmp_path)
    service.get_competency_evidence(scenario.learner, scenario.competency)
    service.flag_pattern_for_review(
        learner_id=scenario.learner,
        competency_code=scenario.competency,
        claim="Recorded assessments differ slightly over terms.",
        supporting_evidence_ids=["EV-012", "EV-013"],
        counter_evidence_ids=[],
        uncertainty="One later observation calls for further explanation.",
        suggested_teacher_question="Can the learner explain the trend independently?",
    )
    report = make_report(state, scenario, response="Candidate submitted.")
    assert report["status"] == "fail"
    grade = grade_scenario(report, scenario)
    assert grade["status"] == "fail"
    assert grade["checks"]["counter_evidence_present"] is False


def test_saved_diagnostics_identify_actual_errors_without_changing_results(tmp_path):
    directory = tmp_path / "suite"
    directory.mkdir()
    (directory / "summary.json").write_text(
        json.dumps({"status": "fail"}), encoding="utf-8"
    )
    for scenario in SCENARIOS:
        folder = directory / scenario.ident
        folder.mkdir()
        (folder / "result.json").write_text(
            json.dumps({"status": "fail", "checks": {"submitted": False}}),
            encoding="utf-8",
        )
        error = (
            {"type": "ToolError", "message": "Required teacher question missing"}
            if scenario.ident == "longitudinal-pattern" else None
        )
        tools = (
            [{"tool_name": "flag_pattern_for_review", "status": "error"}]
            if scenario.ident == "single-assessment" else []
        )
        (folder / "report.json").write_text(json.dumps({
            "error": error,
            "tool_call_summary": tools,
            "pending_reviews": [],
            "final_output": "ABSTAIN: insufficient evidence",
        }), encoding="utf-8")
    result = diagnose_saved_suite(directory)
    by_name = {item["scenario"]: item for item in result["cases"]}
    assert by_name["longitudinal-pattern"]["classification"] == (
        "model_or_tool_exception"
    )
    assert by_name["longitudinal-pattern"]["model_error_type"] == "ToolError"
    assert by_name["single-assessment"]["classification"] == (
        "candidate_attempted_when_abstention_required"
    )
    assert (directory / "summary.json").read_text(
        encoding="utf-8"
    ) == json.dumps({"status": "fail"})


def test_source_derived_preflight_matches_real_synthetic_records():
    observed = {
        case.ident: evidence_preflight(case) for case in SCENARIOS
    }
    assert observed["longitudinal-pattern"]["distinct_term_count"] >= 3
    assert observed["conflicting-evidence"]["distinct_term_count"] == 3
    assert observed["single-assessment"]["distinct_term_count"] == 1
    assert observed["missing-competency"]["distinct_term_count"] == 0
    for case in SCENARIOS:
        assert observed[case.ident]["longitudinal_eligible"] == (
            observed[case.ident]["distinct_term_count"] >= 2
        )


@pytest.mark.parametrize("has_stages", [False, True])
def test_diagnose_preserves_saved_stages_and_request_history_without_regrading(
    tmp_path, monkeypatch, has_stages,
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Diagnostics must not run or regrade the model")

    monkeypatch.setattr("mwalimulens.multi_scenario_eval.run_open_weights_task", forbidden)
    monkeypatch.setattr("mwalimulens.multi_scenario_eval.grade_scenario", forbidden)
    (tmp_path / "summary.json").write_text('{"status": "fail"}', encoding="utf-8")
    folder = tmp_path / "conflicting-evidence"
    folder.mkdir()
    report = {
        "status": "fail", "initial_output": "ABSTAIN: only two terms.",
        "final_output": "I will now call flag_pattern_for_review.",
        "pending_reviews": [], "candidate_action_available": True,
        "agent_tool_allowlist": ["get_competency_evidence", "flag_pattern_for_review"],
        "grounding_correction": {"attempted": True, "verified_term_count": 3},
        "completion_recovery": {"attempted": True, "succeeded": False},
    }
    evaluated = {"status": "fail", "checks": {"exactly_one_candidate": False}}
    if has_stages:
        report.update({
            "outcome_stages_note": "Stages are agent runs, not individual requests.",
            "outcome_stages": [
                {"stage": "initial", "status": "fail",
                 "checks": {"submitted_candidate": False},
                 "model_requests_observed_through": 3},
                {"stage": "completion_recovery", "status": "fail",
                 "model_requests_observed_through": 4},
            ],
            "model_request_count_observed": 4,
            "model_requests": [
                {"request": index, "requested_tool_names": names,
                 "retry_feedback_count": retries}
                for index, names, retries in [
                    (1, ["get_competency_evidence"], 0),
                    (2, ["flag_pattern_for_review"], 0),
                    (3, [], 1), (4, [], 1),
                ]
            ],
        })
        evaluated["outcome_stages"] = [
            {"stage": "initial", "status": "fail",
             "checks": {"exactly_one_candidate": False}},
        ]
    for name, payload in [("report", report), ("result", evaluated)]:
        (folder / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    diagnostic = diagnose_saved_suite(tmp_path)
    case = next(item for item in diagnostic["cases"] if item["scenario"] == folder.name)
    assert case["report_outcome_stages"] == report.get("outcome_stages", [])
    assert case["result_outcome_stages"] == evaluated.get("outcome_stages", [])
    assert case["model_requests"] == report.get("model_requests", [])
    for key in (
        "initial_output", "grounding_correction", "completion_recovery",
        "candidate_action_available", "agent_tool_allowlist", "pending_reviews",
        "model_request_count_observed", "outcome_stages_note",
    ):
        assert case[key] == report.get(key)
    assert "do not sum" in case["request_metadata_note"]
    assert case["status"] == "fail"
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_action_gate_uses_data_not_expected_label(
    scenario, tmp_path, monkeypatch
):
    captured = {}

    async def fake_model_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "fail",
            "evaluation_target": {
                "learner_id": scenario.learner,
                "competency_code": scenario.competency,
            },
            "pending_reviews": [],
            "audited_tool_names": [],
            "tool_call_summary": [],
            "teacher_review_count": 0,
            "profile_update_count": 0,
        }

    monkeypatch.setattr(
        "mwalimulens.multi_scenario_eval.run_open_weights_task",
        fake_model_run,
    )
    result = asyncio.run(run_one(
        scenario,
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
    ))
    facts = evidence_preflight(scenario)
    assert captured["allow_candidate_action"] == facts["longitudinal_eligible"]
    assert result["evidence_preflight"] == facts
    assert captured["prompt_style"] == "scenario"
    assert result["status"] == "fail"


def test_focused_selection_is_ordered_without_changing_defaults():
    assert select_scenarios() == SCENARIOS
    cases = select_scenarios(("conflicting-evidence", "longitudinal-pattern"))
    assert [case.ident for case in cases] == [
        "conflicting-evidence", "longitudinal-pattern",
    ]
    with pytest.raises(ValueError, match="Duplicate"):
        select_scenarios(("longitudinal-pattern", "longitudinal-pattern"))
    with pytest.raises(ValueError, match="at least one"):
        select_scenarios(())
    with pytest.raises(ValueError, match="Unknown scenario"):
        select_scenarios(("not-in-suite",))


def test_focused_suite_runs_two_only_and_preserves_original_stage_grades(
    tmp_path, monkeypatch,
):
    seen = []

    def fake_runner(command, **_kwargs):
        scenario = command[command.index("--scenario") + 1]
        seen.append(scenario)
        destination = Path(command[command.index("--result") + 1])
        destination.write_text(json.dumps({
            "status": "pass",
            "checks": {"no_teacher_decision": True},
            "outcome_stages": [
                {"stage": "initial", "status": "fail"},
                {"stage": "grounding_correction", "status": "pass"},
            ],
        }), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    result = run_suite(
        output_root=tmp_path,
        runner=fake_runner,
        scenarios=("longitudinal-pattern", "conflicting-evidence"),
    )
    assert seen == ["longitudinal-pattern", "conflicting-evidence"]
    assert result["status"] == "pass"
    assert result["selection_mode"] == "focused"
    assert result["scenario_count"] == 2
    assert result["total_available_scenarios"] == 4
    assert result["first_stage_passed"] == 0
    assert result["first_stage_unknown"] == 0
    assert result["passed"] == 2
    assert all(item["first_stage_status"] == "fail" for item in result["results"])
    directory = Path(result["summary_path"]).parent
    assert not (directory / "single-assessment").exists()
    assert not (directory / "missing-competency").exists()
    diagnostic = diagnose_saved_suite(directory)
    assert [case["scenario"] for case in diagnostic["cases"]] == seen
    stored = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))
    assert stored["selected_scenarios"] == seen


def test_focused_suite_does_not_hide_failed_scenario(tmp_path):
    def failed_runner(command, **_kwargs):
        report = Path(command[command.index("--result") + 1])
        report.write_text(json.dumps({
            "status": "fail",
            "checks": {"candidate_created": False},
            "outcome_stages": [{"stage": "initial", "status": "fail"}],
        }), encoding="utf-8")
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="")

    result = run_suite(
        output_root=tmp_path, runner=failed_runner,
        scenarios=("conflicting-evidence",),
    )
    assert result["status"] == "fail"
    assert result["failed"] == 1
    assert result["passed"] == 0
    assert result["results"][0]["first_stage_status"] == "fail"
    assert result["results"][0]["failure"] == "Scenario process exit code 2"


def test_cli_forwards_focused_selection_without_starting_qwen(
    monkeypatch, tmp_path, capsys,
):
    observed = {}

    def fake_suite(**kwargs):
        observed.update(kwargs)
        return {
            "summary_path": str(tmp_path / "summary.json"),
            "status": "pass",
            "selection_mode": "focused",
            "scenario_count": 2,
            "total_available_scenarios": 4,
            "first_stage_passed": 1,
            "passed": 2,
        }

    monkeypatch.setattr("mwalimulens.multi_scenario_eval.run_suite", fake_suite)
    code = main([
        "--scenarios", "longitudinal-pattern", "conflicting-evidence",
        "--timeout", "600", "--output-dir", str(tmp_path),
    ])
    assert code == 0
    assert observed["scenarios"] == (
        "longitudinal-pattern", "conflicting-evidence",
    )
    output = capsys.readouterr().out
    assert "focused (2/4 cases)" in output
    assert "Initial-stage passes: 1" in output
