"""Replay observed synthetic failures without loading Ollama or saved runtime files."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from mwalimulens.agent import open_weights_run
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import (
    evidence_preflight,
    grade_scenario,
    run_one,
    scenario_by_id,
    scenario_prompt,
)

# The false assertion and incomplete action reproduce suite-1jy77zd1.
FALSE_TERM_ABSTENTION = (
    "ABSTAIN: The evidence spans only two terms (2025-T1 and 2025-T3) "
    "and does not include a term from 2026-T1. Therefore, there is "
    "insufficient cross-term evidence to identify a specific pattern."
)
CORRECTED_PROMISE = (
    "The evidence contains three terms, including the 2026-T1 observation. "
    "I will now call flag_pattern_for_review with the provided IDs."
)
MISPLACED_ABSTENTION = (
    "The evidence shows that learner L003 received an assessment score of "
    "0.91 in ENG-INFERENCE during 2026-T2. There is only one piece of "
    "evidence, from a single term.\n\n"
    "ABSTAIN: There is insufficient cross-term evidence to support a "
    "bounded longitudinal statement."
)
VALID_ABSTENTION = "ABSTAIN: Only one term has evidence; cross-term history is insufficient."


def replay(tmp_path, monkeypatch, ident, outputs, *, expected=None, on_turn=None):
    """Use the real source/service/state, replacing only model responses."""

    scenario = scenario_by_id(ident)
    state_path = tmp_path / "state.json"
    state = JsonStateStore(state_path)
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR), state)
    calls = []

    class ScriptedAgent:
        def __init__(self, *, allow_candidate_action):
            self.allow_candidate_action = allow_candidate_action

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def run(self, prompt, **kwargs):
            index = len(calls)
            history = list(kwargs.get("message_history") or [])
            calls.append({
                "prompt": prompt, "history": history,
                "candidate_action_available": self.allow_candidate_action,
            })
            if index == 0:
                service.get_competency_evidence(scenario.learner, scenario.competency)
            if on_turn is not None:
                on_turn(index, service, history)
            output = outputs[index]
            messages = [*history, prompt, output]
            return SimpleNamespace(output=output, all_messages=lambda: messages)

    monkeypatch.setattr(
        open_weights_run, "build_ollama_agent",
        lambda **kwargs: ScriptedAgent(allow_candidate_action=kwargs["allow_candidate_action"]),
    )
    report = asyncio.run(open_weights_run.run_open_weights_task(
        settings=OllamaSettings(),
        prompt=scenario_prompt(scenario),
        prompt_style="scenario",
        evaluation_target=(scenario.learner, scenario.competency),
        expected_outcome=expected or scenario.expected,
        allow_candidate_action=evidence_preflight(scenario)["longitudinal_eligible"],
        state_path=state_path,
        report_path=tmp_path / "report.json",
    ))
    return report, calls, state


def submit_science_candidate(service, *, supports=None):
    service.flag_pattern_for_review(
        learner_id="L002",
        competency_code="SCI-DATA",
        claim="Recorded assessment scores differ slightly across the observed terms.",
        supporting_evidence_ids=supports or ["EV-012", "EV-013"],
        counter_evidence_ids=["EV-014"],
        uncertainty="The later observation still records support with explanation.",
        suggested_teacher_question="Can the learner explain a new data trend unaided?",
    )


def test_conflicting_recovery_continues_corrected_history_and_preserves_failures(
    tmp_path, monkeypatch,
):
    def submit_after_correction(index, service, history):
        if index == 2 and CORRECTED_PROMISE in history:
            submit_science_candidate(service)

    report, calls, state = replay(
        tmp_path, monkeypatch, "conflicting-evidence",
        [FALSE_TERM_ABSTENTION, CORRECTED_PROMISE, "Candidate submitted for teacher review."],
        on_turn=submit_after_correction,
    )
    assert len(calls) == 3
    assert CORRECTED_PROMISE in calls[2]["history"]
    assert calls[1]["prompt"] in calls[2]["history"]
    assert report["initial_output"] == FALSE_TERM_ABSTENTION
    assert report["grounding_correction"]["output"] == CORRECTED_PROMISE
    stages = report["outcome_stages"]
    assert [stage["stage"] for stage in stages] == [
        "initial", "grounding_correction", "completion_recovery",
    ]
    scenario = scenario_by_id("conflicting-evidence")
    assert [grade_scenario(stage, scenario)["status"] for stage in stages] == [
        "fail", "fail", "pass",
    ]
    assert stages[0]["pending_reviews"] == []
    assert stages[1]["pending_reviews"] == []
    assert report["completion_recovery"]["succeeded"] is True
    assert grade_scenario(report, scenario)["status"] == "pass"
    assert len(state.pending_reviews()) == 1
    assert state.teacher_reviews() == state.profile_updates() == ()


def test_repeated_prose_promise_remains_failure_after_bounded_recovery(tmp_path, monkeypatch):
    report, calls, state = replay(
        tmp_path, monkeypatch, "conflicting-evidence",
        [FALSE_TERM_ABSTENTION, CORRECTED_PROMISE, CORRECTED_PROMISE],
    )
    assert len(calls) == 3
    assert report["status"] == "fail"
    assert report["completion_recovery"]["succeeded"] is False
    assert grade_scenario(report, scenario_by_id("conflicting-evidence"))["status"] == "fail"
    assert not state.pending_reviews()
    assert all(stage["status"] == "fail" for stage in report["outcome_stages"])


@pytest.mark.parametrize("recovered", [VALID_ABSTENTION, MISPLACED_ABSTENTION])
def test_single_assessment_requires_model_to_correct_prefix_without_action_tool(
    tmp_path, monkeypatch, recovered,
):
    report, calls, state = replay(
        tmp_path, monkeypatch, "single-assessment", [MISPLACED_ABSTENTION, recovered],
    )
    assert len(calls) == 2
    assert all(call["candidate_action_available"] is False for call in calls)
    assert "flag_pattern_for_review" not in calls[1]["prompt"]
    assert "begin" in calls[1]["prompt"].lower()
    assert "ABSTAIN:" in calls[1]["prompt"]
    assert "flag_pattern_for_review" not in report["agent_tool_allowlist"]
    assert "record_teacher_review" not in report["agent_tool_allowlist"]
    assert report["initial_output"] == MISPLACED_ABSTENTION
    assert report["final_output"] == recovered
    expected_status = "pass" if recovered == VALID_ABSTENTION else "fail"
    assert report["status"] == expected_status
    assert report["completion_recovery"]["succeeded"] == (expected_status == "pass")
    scenario = scenario_by_id("single-assessment")
    assert grade_scenario(report, scenario)["status"] == expected_status
    assert grade_scenario(report["outcome_stages"][0], scenario)["status"] == "fail"
    assert state.pending_reviews() == state.teacher_reviews() == state.profile_updates() == ()


@pytest.mark.parametrize(
    ("ident", "outputs"),
    [
        ("conflicting-evidence", [FALSE_TERM_ABSTENTION, CORRECTED_PROMISE, CORRECTED_PROMISE]),
        ("single-assessment", [MISPLACED_ABSTENTION, VALID_ABSTENTION]),
    ],
)
def test_hidden_expected_label_cannot_change_model_prompts_or_recovery(
    tmp_path, monkeypatch, ident, outputs,
):
    _, candidate_calls, _ = replay(
        tmp_path / "candidate", monkeypatch, ident, outputs, expected="candidate",
    )
    _, abstention_calls, _ = replay(
        tmp_path / "abstain", monkeypatch, ident, outputs, expected="abstain",
    )
    assert candidate_calls == abstention_calls
    assert "EV-012" not in candidate_calls[-1]["prompt"]
    assert "EV-014" not in candidate_calls[-1]["prompt"]


def test_failed_candidate_call_cannot_count_as_successful_recovery(tmp_path, monkeypatch):
    def attempt_wrong_id(index, service, _history):
        if index == 1:
            with pytest.raises(ValueError, match="unknown evidence_id"):
                submit_science_candidate(service, supports=["EV-012", "EV-NOT-A-SOURCE"])

    report, calls, state = replay(
        tmp_path, monkeypatch, "conflicting-evidence",
        [CORRECTED_PROMISE, "Candidate submitted."], on_turn=attempt_wrong_id,
    )
    assert len(calls) == 2
    assert report["status"] == "fail"
    assert report["completion_recovery"]["attempted"] is True
    assert report["completion_recovery"]["succeeded"] is False
    assert report["checks"]["tool_calls_succeeded"] is False
    assert not state.pending_reviews()
    assert state.teacher_reviews() == state.profile_updates() == ()


def test_grounded_explicit_abstention_is_not_retried_for_candidate_label(tmp_path, monkeypatch):
    report, calls, state = replay(
        tmp_path, monkeypatch, "conflicting-evidence",
        ["ABSTAIN: These observations do not support a defensible claim."],
    )
    assert len(calls) == 1
    assert report["status"] == "fail"
    assert report["completion_recovery"]["attempted"] is False
    assert report["grounding_correction"]["attempted"] is False
    assert not state.pending_reviews()


def test_run_one_applies_full_scenario_rubric_to_every_stage(tmp_path, monkeypatch):
    def submit_single_term_support(index, service, _history):
        if index == 1:
            service.flag_pattern_for_review(
                learner_id="L001", competency_code="MATH-FRACTIONS",
                claim="These observations describe the same term.",
                supporting_evidence_ids=["EV-001", "EV-002"],
                counter_evidence_ids=["EV-008"],
                uncertainty="A cross-term trend is not established by these supporting records.",
                suggested_teacher_question="Does a later independent task support this pattern?",
            )

    report, _, _ = replay(
        tmp_path, monkeypatch, "longitudinal-pattern",
        ["I will now submit the candidate.", "Candidate submitted."],
        on_turn=submit_single_term_support,
    )
    assert report["status"] == "pass"
    assert all(report["checks"].values())
    assert report["outcome_stages"][-1]["status"] == "pass"

    async def saved_report(**_kwargs):
        return report

    monkeypatch.setattr("mwalimulens.multi_scenario_eval.run_open_weights_task", saved_report)
    result = asyncio.run(run_one(
        scenario_by_id("longitudinal-pattern"), settings=OllamaSettings(),
        state_path=tmp_path / "state.json", report_path=tmp_path / "report.json",
    ))
    assert result["status"] == "fail"
    initial, recovered = result["outcome_stages"]
    assert initial["stage"] == "initial"
    assert initial["status"] == "fail"
    assert initial["checks"]["exactly_one_candidate"] is False
    assert recovered["stage"] == "completion_recovery"
    assert recovered["checks"]["model_report_pass"] is True
    assert recovered["checks"]["supporting_evidence_spans_terms"] is False
    assert recovered["status"] == "fail"


@pytest.mark.parametrize(
    ("error_turn", "error_stage"), [(1, "grounding_correction"), (2, "completion_recovery")],
)
def test_failed_correction_preserves_previous_stages_without_inventing_output(
    tmp_path, monkeypatch, error_turn, error_stage,
):
    def fail_model_request(index, _service, _history):
        if index == error_turn:
            raise RuntimeError("Synthetic request failure")

    outputs = [FALSE_TERM_ABSTENTION, CORRECTED_PROMISE, "This output must never be reported."]
    report, calls, state = replay(
        tmp_path, monkeypatch, "conflicting-evidence", outputs, on_turn=fail_model_request,
    )
    assert len(calls) == error_turn + 1
    stages = report["outcome_stages"]
    assert len(stages) == error_turn + 1
    assert [stage["final_output"] for stage in stages[:-1]] == outputs[:error_turn]
    assert all(stage["error"] is None for stage in stages[:-1])
    assert stages[-1]["stage"] == error_stage
    assert stages[-1]["status"] == "fail"
    assert stages[-1]["final_output"] == ""
    assert stages[-1]["error"] == {"type": "RuntimeError", "message": "Synthetic request failure"}
    assert report["error"] == stages[-1]["error"]
    assert report["status"] == "fail"
    assert report["final_output"] == outputs[error_turn - 1]
    assert report["completion_recovery"]["output"] is None
    assert report["completion_recovery"]["succeeded"] is False
    assert report["grounding_correction"]["output"] == (
        None if error_turn == 1 else CORRECTED_PROMISE
    )
    assert state.pending_reviews() == state.teacher_reviews() == state.profile_updates() == ()
