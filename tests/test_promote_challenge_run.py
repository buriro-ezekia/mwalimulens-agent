"""Tests for promotion of consolidated one-command challenge evidence."""

from __future__ import annotations

import json

import pytest

from mwalimulens.promote_challenge_run import (
    REQUIRED_CHALLENGE_CHECKS,
    promote_challenge_report,
)


def test_passing_challenge_report_can_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    destination = tmp_path / "evidence.json"
    report = {
        "status": "pass",
        "model": "qwen2.5:3b",
        "checks": {name: True for name in REQUIRED_CHALLENGE_CHECKS},
        "components": {
            "open_weights": {"status": "pass"},
            "borrowed_mcp": {"status": "pass"},
            "evaluations": {"status": "pass"},
        },
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    promoted = promote_challenge_report(source=source, destination=destination)

    assert promoted == report
    assert destination.is_file()


def test_failed_challenge_report_cannot_be_promoted(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    report = {
        "status": "fail",
        "checks": {name: False for name in REQUIRED_CHALLENGE_CHECKS},
        "components": {},
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="status must be pass"):
        promote_challenge_report(source=source, destination=tmp_path / "evidence.json")



def test_promotion_rejects_non_default_model(tmp_path) -> None:
    source = tmp_path / "runtime.json"
    report = {
        "status": "pass",
        "model": "qwen2.5:1.5b",
        "checks": {name: True for name in REQUIRED_CHALLENGE_CHECKS},
        "components": {
            "open_weights": {"status": "pass"},
            "borrowed_mcp": {"status": "pass"},
            "evaluations": {"status": "pass"},
        },
    }
    source.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="default model"):
        promote_challenge_report(source=source, destination=tmp_path / "evidence.json")
