"""Tests for the reproducible challenge evaluation suite."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mwalimulens.evals import run_evaluations
from mwalimulens.promote_evals import promote_eval_report

ROOT = Path(__file__).resolve().parents[1]


def test_eval_suite_has_current_passes_and_historical_failures(tmp_path) -> None:
    report = run_evaluations(report_path=tmp_path / "evals.json")

    assert report["status"] == "pass"
    assert report["summary"] == {
        "total_cases": 13,
        "current_regression_cases": 11,
        "current_pass": 11,
        "current_fail": 0,
        "historical_failure_cases": 2,
        "historical_fail_preserved": 2,
    }

    by_id = {case["id"]: case for case in report["cases"]}
    assert by_id["E01"]["result"] == "PASS"
    assert by_id["E11"]["result"] == "PASS"
    assert by_id["E12"]["result"] == "FAIL"
    assert by_id["E13"]["result"] == "FAIL"


def test_eval_suite_writes_reproducible_json(tmp_path) -> None:
    path = tmp_path / "evals.json"
    report = run_evaluations(report_path=path)

    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_passing_eval_report_can_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    destination = tmp_path / "evidence.json"
    report = run_evaluations(report_path=source)

    promoted = promote_eval_report(source=source, destination=destination)

    assert promoted == report
    assert destination.is_file()


def test_eval_promotion_rejects_current_failure(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    report = run_evaluations(report_path=source)
    report["status"] = "fail"
    report["summary"]["current_fail"] = 1
    source.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="status must be pass"):
        promote_eval_report(source=source, destination=tmp_path / "evidence.json")


def test_evals_markdown_contains_at_least_eight_explicit_tasks() -> None:
    content = (ROOT / "EVALS.md").read_text(encoding="utf-8")

    ids = {f"E{index:02d}" for index in range(1, 14)}
    assert all(eval_id in content for eval_id in ids)
    assert content.count("| PASS |") >= 11
    assert content.count("**FAIL**") >= 2
    assert "Evaluation limitations" in content
