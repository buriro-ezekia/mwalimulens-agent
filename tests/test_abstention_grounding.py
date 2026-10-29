"""Factual abstention verification never uses hidden expected labels."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mwalimulens.agent.grounding import correction_prompt, verify_abstention_terms
from mwalimulens.agent.open_weights_run import run_open_weights_task


def test_detects_false_two_term_claim_for_three_term_science_case():
    facts = verify_abstention_terms(
        "ABSTAIN: The evidence spans only two terms (2025-T1 and 2025-T3) "
        "and does not include a term from 2026-T1.",
        "L002",
        "SCI-DATA",
    )
    assert facts["verified_term_count"] == 3
    assert facts["verified_term_ids"] == ["2025-T1", "2025-T3", "2026-T1"]
    assert "incorrect_exact_term_count" in facts["factual_contradictions"]
    assert "incorrect_claim_that_existing_term_is_missing" in (
        facts["factual_contradictions"]
    )


def test_grounded_single_term_abstention_requires_no_correction():
    facts = verify_abstention_terms(
        "ABSTAIN: Only one distinct term has evidence for this learner.",
        "L003",
        "ENG-INFERENCE",
    )
    assert facts["verified_term_count"] == 1
    assert facts["factual_contradictions"] == []


def test_grounded_missing_evidence_requires_no_correction():
    facts = verify_abstention_terms(
        "ABSTAIN: No evidence exists for this competency.",
        "L002",
        "MATH-FRACTIONS",
    )
    assert facts["verified_term_count"] == 0
    assert facts["factual_contradictions"] == []


def test_recovery_message_does_not_reveal_hidden_expected_outcome():
    facts = verify_abstention_terms(
        "ABSTAIN: There are only two terms.", "L002", "SCI-DATA"
    )
    text = correction_prompt("L002", "SCI-DATA", facts)
    assert "2026-T1" in text
    assert "Otherwise respond ABSTAIN:" in text
    assert "EV-014" not in text
    assert "must submit" not in text


def test_scenario_runner_preserves_initial_false_abstention_and_correction(
    tmp_path, monkeypatch,
):
    from mwalimulens.agent import open_weights_run

    calls = []
    class FakeAgent:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def run(self, prompt, **_kwargs):
            calls.append(prompt)
            return SimpleNamespace(
                output=(
                    "ABSTAIN: There are only two terms."
                    if len(calls) == 1 else
                    "ABSTAIN: Insufficient evidence for a defensible claim."
                ),
                all_messages=lambda: [],
            )

    monkeypatch.setattr(
        open_weights_run, "build_ollama_agent", lambda **_kwargs: FakeAgent()
    )
    report = asyncio.run(run_open_weights_task(
        prompt="Evaluate the fictional evidence.",
        prompt_style="scenario",
        evaluation_target=("L002", "SCI-DATA"),
        expected_outcome="candidate",
        state_path=tmp_path / "state.json",
        report_path=tmp_path / "report.json",
    ))
    assert len(calls) == 2
    assert report["grounding_correction"]["attempted"] is True
    assert "only two terms" in report["initial_output"]
    assert report["grounding_correction"]["original_abstention"] == report[
        "initial_output"
    ]
    assert report["status"] == "fail"
    assert report["teacher_review_count"] == 0
