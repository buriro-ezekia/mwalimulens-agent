"""Inspect historical failures without model calls, file changes or revised grades."""

import hashlib
import json

import pytest

from mwalimulens import multi_scenario_eval as evaluation
from mwalimulens.agent.candidate_contract import EvidenceSnapshot, decision_schema, review_messages


def save(folder, name, payload):
    (folder / name).write_text(json.dumps(payload), encoding="utf-8-sig")


def forbid(*_args, **_kwargs):
    pytest.fail("Saved diagnostics must not invoke a model, suite or grader")


def test_standalone_historical_abstention_keeps_failure_and_unknown_schema(tmp_path, monkeypatch):
    report = {
        "workflow_mode": "structured_proposal_v1", "decision_policy_id": "provisional_review_v2",
        "status": "fail", "expected_outcome": "candidate", "proposal_status": "abstained",
        "proposal_attempts": [{"attempt": 1, "outcome": "abstain", "status": "valid"}],
        "final_output": "ABSTAIN: Insufficient consistent improvement or independent mastery.",
        "timing": {"total_wall_seconds": 104.843},
    }
    evaluated = {"status": "fail", "checks": {"exactly_one_candidate": False, "safe": True}}
    save(tmp_path, "report.json", report)
    save(tmp_path, "result.json", evaluated)
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    for name in ("run_open_weights_task", "run_suite", "grade_scenario"):
        monkeypatch.setattr(evaluation, name, forbid)
    result = evaluation.diagnose_saved_case(tmp_path)
    assert result["original_status"] == "fail"
    assert result["recorded_decision"]["interpretation"] == "recorded_valid_abstention"
    assert result["recorded_decision"]["decision_schema_id"] is None
    assert result["files"]["report.json"]["recorded"] == report
    assert result["files"]["result.json"]["recorded"] == evaluated
    assert result["files"]["report.json"]["sha256"] == hashlib.sha256(
        before[tmp_path / "report.json"]
    ).hexdigest()
    assert result["semantic_assessment"] == "unknown"
    assert evaluation.main(["--diagnose-case", str(tmp_path)]) == 0
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_missing_final_report_is_unknown_not_abstention(tmp_path):
    save(tmp_path, "result.json", {"status": "fail", "failure": "Timeout after 240 seconds"})
    result = evaluation.diagnose_saved_case(tmp_path)
    assert result["files"]["report.json"]["status"] == "unavailable"
    assert result["recorded_decision"]["interpretation"] == "unknown"
    assert result["original_status"] == "fail"


@pytest.fixture
def saved_proposal(tmp_path):
    snapshot = EvidenceSnapshot.from_mcp({
        "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
        "evidence_count": 0, "evidence": [],
    }, ("L001", "MATH-FRACTIONS"))
    raw = ' {"outcome":"abstain","candidate":null,"abstention_reason":"No records."}\n'
    save(tmp_path, "evidence_snapshot.json", {
        "sha256": snapshot.sha256, "payload": json.loads(snapshot.payload_json),
    })
    save(tmp_path, "report.json", {"evidence_sha256": snapshot.sha256, "status": "pass"})
    proposal = {
        "evidence_sha256": snapshot.sha256,
        "attempts": [{
            "attempt": 1, "status": "returned", "raw_output": raw,
            "raw_output_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "generation_input": {
                "messages": review_messages(snapshot),
                "format": decision_schema("review_decision_outcome_v2"),
            },
        }],
    }
    save(tmp_path, "proposals.json", proposal)
    return proposal


def test_saved_sidecar_validates_independent_layers_without_semantic_grade(
    tmp_path, saved_proposal,
):
    result = evaluation.diagnose_saved_case(tmp_path)
    diagnostic = result["proposal_diagnostics"][0]
    for layer in ("json", "wire_schema", "outcome_contract", "source_validation"):
        assert diagnostic[layer]["status"] == "valid"
    assert diagnostic["abstention_reason"] == "No records."
    assert diagnostic["semantic_assessment"] == "unknown"
    assert diagnostic["semantic_quality_verified"] is False
    assert result["files"]["proposals.json"]["recorded"] == saved_proposal


@pytest.mark.parametrize("tamper", ["raw_output", "request_evidence", "snapshot", "report_hash"])
def test_sidecar_provenance_mismatch_fails_without_fallback_run(
    tmp_path, saved_proposal, monkeypatch, tamper,
):
    if tamper == "raw_output":
        saved_proposal["attempts"][0]["raw_output"] += " "
    elif tamper == "request_evidence":
        saved_proposal["attempts"][0]["generation_input"]["messages"][1]["content"] = "{}"
    elif tamper == "snapshot":
        saved = json.loads((tmp_path / "evidence_snapshot.json").read_text(encoding="utf-8-sig"))
        saved["sha256"] = "incorrect"
        save(tmp_path, "evidence_snapshot.json", saved)
    else:
        save(tmp_path, "report.json", {"evidence_sha256": "incorrect"})
    save(tmp_path, "proposals.json", saved_proposal)
    monkeypatch.setattr(evaluation, "run_suite", forbid)
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    assert evaluation.main(["--diagnose-case", str(tmp_path)]) == 2
    assert {path: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_supplied_malformed_report_fails_without_model_fallback(tmp_path, monkeypatch):
    (tmp_path / "report.json").write_text("not JSON", encoding="utf-8")
    monkeypatch.setattr(evaluation, "run_suite", forbid)
    assert evaluation.main(["--diagnose-case", str(tmp_path)]) == 2


def test_historical_snapshot_is_verified_without_new_sidecar(tmp_path, saved_proposal):
    (tmp_path / "proposals.json").unlink()
    save(tmp_path, "report.json", {"evidence_sha256": "incorrect"})
    assert evaluation.main(["--diagnose-case", str(tmp_path)]) == 2


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_json_numeric_values_are_rejected(tmp_path, constant):
    (tmp_path / "report.json").write_text('{"value": ' + constant + "}")
    assert evaluation.main(["--diagnose-case", str(tmp_path)]) == 2
