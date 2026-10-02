"""Reproducible challenge evaluation suite for MwalimuLens."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from mwalimulens.agent.borrowed_filesystem import (
    BORROWED_FILESYSTEM_TOOL_ALLOWLIST,
    BORROWED_FILESYSTEM_WRITE_TOOLS,
)
from mwalimulens.agent.orchestrator import AGENT_MCP_TOOL_ALLOWLIST, AGENT_INSTRUCTIONS
from mwalimulens.domain import EvidenceType, load_synthetic_dataset
from mwalimulens.mcp_server.server import PROJECT_ROOT
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore

FIXTURE_DIR = PROJECT_ROOT / "data" / "synthetic"
DEFAULT_EVAL_REPORT_PATH = PROJECT_ROOT / "runtime" / "evals_run.json"
OPEN_WEIGHTS_EVIDENCE = PROJECT_ROOT / "evidence" / "open_weights_run.json"
BORROWED_MCP_EVIDENCE = PROJECT_ROOT / "evidence" / "borrowed_mcp_run.json"
QWEN_15B_FAILURE = (
    PROJECT_ROOT
    / "evidence"
    / "failures"
    / "qwen2.5-1.5b-workflow-completion-failure.md"
)
QWEN_3B_SEMANTIC_FAILURE = (
    PROJECT_ROOT
    / "evidence"
    / "failures"
    / "qwen2.5-3b-recovery-semantic-abstention.md"
)
FIXED_TIME = datetime.fromisoformat("2026-10-02T11:00:00+03:00")


def run_evaluations(
    *,
    report_path: Path = DEFAULT_EVAL_REPORT_PATH,
) -> dict[str, Any]:
    """Run deterministic current regressions plus preserved historical model failures."""

    dataset = load_synthetic_dataset(FIXTURE_DIR)
    cases: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="mwalimulens-evals-") as tmp:
        temp_root = Path(tmp)
        current_cases: list[tuple[str, str, Callable[[], tuple[bool, str]]]] = [
            (
                "E01",
                "Late-entry chronology uses occurrence time",
                lambda: _eval_late_entry_chronology(dataset),
            ),
            (
                "E02",
                "Conflicting evidence remains visible",
                lambda: _eval_conflicting_evidence(dataset),
            ),
            (
                "E03",
                "Missing-term gap is not fabricated",
                lambda: _eval_missing_term(dataset),
            ),
            (
                "E04",
                "Single high score remains insufficient history",
                lambda: _eval_insufficient_history(dataset),
            ),
            (
                "E05",
                "One-off low anomaly is not pre-labelled",
                lambda: _eval_one_off_anomaly(dataset),
            ),
            (
                "E06",
                "Mismatched evidence cannot create a candidate",
                lambda: _eval_mismatched_evidence_rejected(dataset, temp_root / "e06"),
            ),
            (
                "E07",
                "Teacher rejection creates no profile update",
                lambda: _eval_teacher_reject(dataset, temp_root / "e07"),
            ),
            (
                "E08",
                "Teacher edit creates named audited profile update",
                lambda: _eval_teacher_edit(dataset, temp_root / "e08"),
            ),
            (
                "E09",
                "Model cannot access teacher-review action",
                _eval_agent_tool_boundary,
            ),
            (
                "E10",
                "Borrowed MCP remains read-only in real smoke evidence",
                _eval_borrowed_mcp_evidence,
            ),
            (
                "E11",
                "Real local Qwen task completed with human gate intact",
                _eval_open_weights_evidence,
            ),
        ]

        for eval_id, name, fn in current_cases:
            try:
                passed, observed = fn()
            except Exception as exc:
                passed = False
                observed = f"{type(exc).__name__}: {exc}"
            cases.append(
                {
                    "id": eval_id,
                    "name": name,
                    "kind": "current_regression",
                    "result": "PASS" if passed else "FAIL",
                    "observed": observed,
                }
            )

    cases.extend(
        [
            _historical_failure_case(
                "E12",
                "Qwen2.5 1.5B workflow-completion failure",
                QWEN_15B_FAILURE,
            ),
            _historical_failure_case(
                "E13",
                "Qwen2.5 3B semantic-abstention failure",
                QWEN_3B_SEMANTIC_FAILURE,
            ),
        ]
    )

    current = [case for case in cases if case["kind"] == "current_regression"]
    historical = [case for case in cases if case["kind"] == "historical_model_failure"]
    current_pass = sum(case["result"] == "PASS" for case in current)
    current_fail = len(current) - current_pass
    historical_fail = sum(case["result"] == "FAIL" for case in historical)

    summary = {
        "total_cases": len(cases),
        "current_regression_cases": len(current),
        "current_pass": current_pass,
        "current_fail": current_fail,
        "historical_failure_cases": len(historical),
        "historical_fail_preserved": historical_fail,
    }
    status = (
        "pass"
        if len(cases) >= 8
        and current_fail == 0
        and historical_fail == len(historical)
        and historical_fail >= 1
        else "fail"
    )
    report = {
        "status": status,
        "summary": summary,
        "cases": cases,
        "note": (
            "Historical FAIL rows are intentionally preserved and do not count as current "
            "regression failures."
        ),
    }

    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def _eval_late_entry_chronology(dataset) -> tuple[bool, str]:
    timeline = dataset.timeline("L001")
    by_id = {item.evidence_id: item for item in timeline}
    late = by_id["EV-007"]
    conflict = by_id["EV-008"]
    passed = (
        late.occurred_at < conflict.occurred_at
        and late.recorded_at > conflict.recorded_at
        and late.recording_delay.days == 26
        and list(timeline).index(late) < list(timeline).index(conflict)
    )
    return passed, (
        "EV-007 occurred before EV-008 but was recorded later; "
        f"recording delay={late.recording_delay.days} days."
    )


def _eval_conflicting_evidence(dataset) -> tuple[bool, str]:
    items = dataset.competency_evidence("L001", "MATH-FRACTIONS")
    by_id = {item.evidence_id: item for item in items}
    assessment = by_id["EV-007"]
    observation = by_id["EV-008"]
    passed = (
        assessment.score == 0.84
        and observation.evidence_type is EvidenceType.OBSERVATION
        and observation.observation is not None
        and "Struggled" in observation.observation
    )
    return passed, "EV-007 score 0.84 and EV-008 conflicting observation are both retained."


def _eval_missing_term(dataset) -> tuple[bool, str]:
    terms = {
        item.term_id for item in dataset.competency_evidence("L002", "SCI-DATA")
    }
    passed = {"2025-T1", "2025-T3", "2026-T1"}.issubset(terms) and "2025-T2" not in terms
    return passed, f"Observed SCI-DATA terms: {sorted(terms)}; 2025-T2 remains absent."


def _eval_insufficient_history(dataset) -> tuple[bool, str]:
    items = dataset.competency_evidence("L003", "ENG-INFERENCE")
    instructions = " ".join(AGENT_INSTRUCTIONS.lower().split())
    passed = (
        len(items) == 1
        and items[0].evidence_id == "EV-015"
        and items[0].score == 0.91
        and "single score is not enough" in instructions
    )
    return passed, "Only EV-015 exists (0.91); agent policy forbids a durable claim from one score."


def _eval_one_off_anomaly(dataset) -> tuple[bool, str]:
    items = dataset.competency_evidence("L001", "MATH-MEASUREMENT")
    instructions = " ".join(AGENT_INSTRUCTIONS.lower().split())
    passed = (
        len(items) == 1
        and items[0].evidence_id == "EV-010"
        and items[0].score == 0.29
        and items[0].observation is None
        and "never assign a permanent learner label" in instructions
    )
    return passed, "EV-010 is a single 0.29 score with no pre-label; permanent labels are prohibited."


def _service(dataset, state_dir: Path) -> EducationToolService:
    state_dir.mkdir(parents=True, exist_ok=True)
    counter = {"value": 0}

    def id_factory(prefix: str) -> str:
        counter["value"] += 1
        return f"{prefix}-eval-{counter['value']}"

    return EducationToolService(
        dataset,
        JsonStateStore(state_dir / "state.json"),
        clock=lambda: FIXED_TIME,
        id_factory=id_factory,
    )


def _candidate(service: EducationToolService) -> dict[str, Any]:
    return service.flag_pattern_for_review(
        learner_id="L001",
        competency_code="MATH-FRACTIONS",
        claim="Fraction evidence is stronger in later terms, with mixed explanation evidence.",
        supporting_evidence_ids=["EV-004", "EV-007", "EV-009"],
        counter_evidence_ids=["EV-008"],
        uncertainty="Independent explanation evidence remains mixed.",
        suggested_teacher_question="Does this hold in an unfamiliar fraction problem?",
    )


def _eval_mismatched_evidence_rejected(dataset, state_dir: Path) -> tuple[bool, str]:
    service = _service(dataset, state_dir)
    try:
        service.flag_pattern_for_review(
            learner_id="L001",
            competency_code="MATH-FRACTIONS",
            claim="Invalid candidate.",
            supporting_evidence_ids=["EV-010"],
            counter_evidence_ids=[],
            uncertainty="Should be rejected.",
            suggested_teacher_question="Should this be accepted?",
        )
    except ValueError as exc:
        calls = service.state_store.tool_calls()
        passed = (
            "MATH-MEASUREMENT" in str(exc)
            and service.state_store.pending_reviews() == ()
            and len(calls) == 1
            and calls[0].get("status") == "error"
        )
        return passed, f"Rejected mismatched EV-010 and audited error: {exc}"
    return False, "Mismatched EV-010 unexpectedly created a candidate."


def _eval_teacher_reject(dataset, state_dir: Path) -> tuple[bool, str]:
    service = _service(dataset, state_dir)
    candidate = _candidate(service)
    result = service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id="teacher-eval-reject",
        decision="reject",
        reason="Counter-evidence remains too important for profile use.",
    )
    passed = (
        result["profile_update"] is None
        and service.state_store.profile_updates() == ()
        and service.state_store.review_candidates()[0]["status"] == "rejected_by_teacher"
    )
    return passed, "Named teacher rejection resolved the candidate with zero profile updates."


def _eval_teacher_edit(dataset, state_dir: Path) -> tuple[bool, str]:
    service = _service(dataset, state_dir)
    candidate = _candidate(service)
    edited = (
        "Fraction scores are generally higher in later terms, "
        "while independent explanation remains mixed."
    )
    result = service.record_teacher_review(
        review_id=candidate["review_id"],
        reviewer_id="teacher-eval-edit",
        decision="edit",
        reason="Narrow the wording to reflect counter-evidence.",
        edited_claim=edited,
    )
    update = result["profile_update"]
    passed = (
        update is not None
        and update["claim"] == edited
        and update["reviewer_id"] == "teacher-eval-edit"
        and len(service.state_store.profile_updates()) == 1
        and service.state_store.tool_calls()[-1]["status"] == "success"
    )
    return passed, "Teacher edit produced one audited profile update with named reviewer."


def _eval_agent_tool_boundary() -> tuple[bool, str]:
    passed = (
        AGENT_MCP_TOOL_ALLOWLIST
        == {
            "get_learner_timeline",
            "get_competency_evidence",
            "flag_pattern_for_review",
        }
        and "record_teacher_review" not in AGENT_MCP_TOOL_ALLOWLIST
    )
    return passed, f"Model-visible Education tools: {sorted(AGENT_MCP_TOOL_ALLOWLIST)}."


def _eval_borrowed_mcp_evidence() -> tuple[bool, str]:
    report = json.loads(BORROWED_MCP_EVIDENCE.read_text(encoding="utf-8"))
    visible = set(report.get("visible_tools", []))
    checks = report.get("checks", {})
    passed = (
        report.get("status") == "pass"
        and visible == BORROWED_FILESYSTEM_TOOL_ALLOWLIST
        and not visible.intersection(BORROWED_FILESYSTEM_WRITE_TOOLS)
        and all(checks.values())
        and len(report.get("audited_tool_calls", [])) == 1
    )
    return passed, "Committed real smoke exposes six read-only tools and one audited read call."


def _eval_open_weights_evidence() -> tuple[bool, str]:
    report = json.loads(OPEN_WEIGHTS_EVIDENCE.read_text(encoding="utf-8"))
    checks = report.get("checks", {})
    tools = report.get("audited_tool_names", [])
    passed = (
        report.get("status") == "pass"
        and all(checks.values())
        and tools == ["get_competency_evidence", "flag_pattern_for_review"]
        and report.get("pending_review_count") == 1
        and report.get("teacher_review_count") == 0
        and report.get("profile_update_count") == 0
    )
    return passed, "Qwen2.5 3B retrieved evidence, submitted one candidate, and left human state untouched."


def _historical_failure_case(eval_id: str, name: str, path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    preserved = "**Run status:** FAIL" in content and "## Next attempt" in content
    return {
        "id": eval_id,
        "name": name,
        "kind": "historical_model_failure",
        "result": "FAIL" if preserved else "MISSING",
        "observed": (
            f"Preserved genuine failure with next attempt: {path.relative_to(PROJECT_ROOT)}"
            if preserved
            else f"Historical failure evidence is incomplete: {path.relative_to(PROJECT_ROOT)}"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MwalimuLens challenge evaluation suite.")
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_EVAL_REPORT_PATH,
        help="Path for the JSON evaluation report.",
    )
    args = parser.parse_args()

    report = run_evaluations(report_path=args.report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
