"""Timing telemetry checks preserve learner evidence and human-review semantics."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.open_weights_run import build_open_weights_report
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore

ROOT = Path(__file__).resolve().parents[1]


def test_education_reads_include_nonnegative_duration(tmp_path) -> None:
    service = EducationToolService(
        load_synthetic_dataset(ROOT / "data" / "synthetic"),
        JsonStateStore(tmp_path / "state.json"),
    )
    service.get_competency_evidence("L001", "MATH-FRACTIONS")
    event = service.state_store.tool_calls()[-1]
    assert event["status"] == "success"
    assert isinstance(event["duration_seconds"], float)
    assert event["duration_seconds"] >= 0


def test_pending_action_remains_unreviewed_with_duration(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    service = EducationToolService(
        load_synthetic_dataset(ROOT / "data" / "synthetic"),
        store,
    )
    service.flag_pattern_for_review(
        learner_id="L001",
        competency_code="MATH-FRACTIONS",
        claim="Improvement with uncertainty.",
        supporting_evidence_ids=["EV-004", "EV-007"],
        counter_evidence_ids=["EV-008"],
        uncertainty="Explanation remains mixed.",
        suggested_teacher_question="Does this carry into new problems?",
    )
    event = store.tool_calls()[-1]
    assert event["duration_seconds"] >= 0
    assert len(store.pending_reviews()) == 1
    assert store.teacher_reviews() == ()
    assert store.profile_updates() == ()


def test_failed_tool_call_records_duration_without_state_change(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    service = EducationToolService(
        load_synthetic_dataset(ROOT / "data" / "synthetic"),
        store,
    )
    try:
        service.get_competency_evidence("MISSING", "MATH-FRACTIONS")
    except KeyError:
        pass
    else:
        raise AssertionError("Expected missing learner error")
    event = store.tool_calls()[-1]
    assert event["status"] == "error"
    assert event["duration_seconds"] >= 0
    assert store.pending_reviews() == ()


def test_report_includes_stage_timings_without_claiming_model_only_latency(tmp_path) -> None:
    store = JsonStateStore(tmp_path / "state.json")
    now = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    report = build_open_weights_report(
        settings=OllamaSettings(),
        prompt="Synthetic task",
        final_output="No candidate.",
        state_store=store,
        started_at=now,
        finished_at=now,
        timings={
            "agent_build_seconds": 0.1,
            "initial_agent_run_seconds": 3.2,
            "recovery_agent_run_seconds": None,
            "total_wall_seconds": 3.5,
        },
    )
    assert report["timing"]["initial_agent_run_seconds"] == 3.2
    assert report["timing"]["model_only_seconds"] is None
    assert report["timing"]["model_load_seconds"] is None
    assert report["timing"]["agent_run_includes_model_and_mcp"] is True
    assert report["status"] == "fail"
