"""Multi-scenario acceptance tests use only fictional fixtures, never live Qwen."""

from __future__ import annotations

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
    grade_scenario,
    run_suite,
    scenario_by_id,
    scenario_prompt,
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
