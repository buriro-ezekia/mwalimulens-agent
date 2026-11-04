"""Saved decision diagnosis never establishes educational correctness or takes action."""

from __future__ import annotations

import hashlib
import json
import socket
import sys
from copy import deepcopy

import pytest

from mwalimulens import saved_review_diagnostics as diagnostics
from mwalimulens.agent.candidate_contract import (
    DEFAULT_DECISION_SCHEMA_ID,
    OUTCOME_DECISION_SCHEMA_ID,
    EvidenceSnapshot,
    decision_schema,
    review_messages,
)
from mwalimulens.agent.structured_ollama import OllamaJsonGenerator
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService, _evidence_payload


@pytest.fixture
def snapshot():
    target = ("L001", "MATH-FRACTIONS")
    rows = load_synthetic_dataset(DEFAULT_DATA_DIR).competency_evidence(*target)
    return EvidenceSnapshot.from_mcp({
        "learner_id": target[0], "competency_code": target[1],
        "evidence_count": len(rows), "evidence": [_evidence_payload(row) for row in rows],
    }, target)


def candidate(reason=None):
    return {"outcome": "candidate", "abstention_reason": reason, "candidate": {
        "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
        "claim": "Recorded performance differs across terms; explanation remains mixed.",
        "supporting_evidence_ids": ["EV-001", "EV-004"],
        "counter_evidence_ids": ["EV-008"],
        "uncertainty": "Different tasks do not establish independent explanation.",
        "suggested_teacher_question": "Can the learner explain a new fraction task unaided?",
    }}


def request(snapshot, schema_id=DEFAULT_DECISION_SCHEMA_ID):
    return {"messages": review_messages(snapshot), "format": decision_schema(schema_id)}


@pytest.fixture(autouse=True)
def forbid_actions(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Saved diagnosis must not use network, submit or record a human action")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(OllamaJsonGenerator, "__call__", forbidden)
    monkeypatch.setattr(EducationToolService, "flag_pattern_for_review", forbidden)
    monkeypatch.setattr(EducationToolService, "record_teacher_review", forbidden)


@pytest.mark.parametrize("schema_id,wire_status,mismatch", [
    (DEFAULT_DECISION_SCHEMA_ID, "valid", True),
    (OUTCOME_DECISION_SCHEMA_ID, "invalid", False),
])
def test_observed_string_null_separates_wire_and_outcome_contract(
    snapshot, schema_id, wire_status, mismatch,
):
    output, saved_request = candidate("null"), request(snapshot, schema_id)
    original = deepcopy((output, saved_request))
    raw = json.dumps(output)
    result = diagnostics.diagnose_decision(raw, saved_request, snapshot)
    assert result["json"]["status"] == "valid"
    assert result["wire_schema"]["status"] == wire_status
    assert result["outcome_contract"]["status"] == "invalid"
    assert result["source_validation"]["status"] == "unavailable"
    assert result["schema_runtime_mismatch"] is mismatch
    assert result["parsed_output"]["abstention_reason"] == "null"
    assert result["provenance"]["raw_output_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert (output, saved_request) == original


@pytest.mark.parametrize("field,value,issue", [
    ("supporting_evidence_ids", ["EV-001", "UNKNOWN"], "unknown_or_out_of_scope_evidence_ids"),
    ("supporting_evidence_ids", ["EV-001", "EV-001"], "duplicate_evidence_ids"),
    ("counter_evidence_ids", ["EV-001"], "overlapping_evidence_roles"),
    ("supporting_evidence_ids", ["EV-007", "EV-008"], "support_does_not_span_two_terms"),
    ("learner_id", "L002", "candidate_target_mismatch"),
])
def test_source_guard_failure_is_not_an_outcome_schema_mismatch(snapshot, field, value, issue):
    output = candidate()
    output["candidate"][field] = value
    result = diagnostics.diagnose_decision(
        json.dumps(output), request(snapshot, OUTCOME_DECISION_SCHEMA_ID), snapshot,
    )
    assert result["wire_schema"]["status"] == "valid"
    assert result["outcome_contract"]["status"] == "valid"
    assert result["source_validation"]["status"] == "invalid"
    assert issue in result["source_validation"]["issues"]
    assert result["schema_runtime_mismatch"] is False


@pytest.mark.parametrize("reason", [
    "Insufficient consistent improvement or independent mastery to determine a candidate.",
    "The records do not permit a defensible bounded description because task comparability "
    "is unresolved, although multiple terms are present.",
    "Only a single observation is available.",
    "  Independent mastery is uncertain.  ",
])
def test_valid_abstentions_keep_exact_reason_and_semantic_unknown(snapshot, reason):
    output = {"outcome": "abstain", "candidate": None, "abstention_reason": reason}
    result = diagnostics.diagnose_decision(json.dumps(output), request(snapshot), snapshot)
    assert all(result[layer]["status"] == "valid" for layer in (
        "json", "wire_schema", "outcome_contract", "source_validation",
    ))
    assert result["decision_outcome"] == "abstain"
    assert result["abstention_reason"] == reason
    assert result["semantic_assessment"] == "unknown"
    assert result["manual_semantic_review_required"] is True
    assert result["semantic_quality_verified"] is False
    assert result["schema_runtime_mismatch"] is False


@pytest.mark.parametrize("raw", ['{"outcome":', "ABSTAIN: no usable records.", "NaN"])
def test_malformed_or_prose_response_is_not_reconstructed(snapshot, raw):
    result = diagnostics.diagnose_decision(raw, request(snapshot), snapshot)
    assert result["json"]["status"] == "invalid"
    assert result["wire_schema"]["status"] == "unavailable"
    assert result["decision_outcome"] is None
    assert result["schema_runtime_mismatch"] is False
    assert result["semantic_assessment"] == "unknown"


def test_missing_inputs_stay_unavailable():
    result = diagnostics.diagnose_decision(None, None, None)
    for layer in ("json", "wire_schema", "outcome_contract", "source_validation"):
        assert result[layer]["status"] == "unavailable"
    assert result["schema_runtime_mismatch"] is False


def test_abstention_on_real_single_observation_snapshot_remains_semantically_unknown():
    target = ("L003", "ENG-INFERENCE")
    rows = load_synthetic_dataset(DEFAULT_DATA_DIR).competency_evidence(*target)
    assert len(rows) == 1
    sparse = EvidenceSnapshot.from_mcp({
        "learner_id": target[0], "competency_code": target[1],
        "evidence_count": len(rows), "evidence": [_evidence_payload(row) for row in rows],
    }, target)
    output = {"outcome": "abstain", "candidate": None,
              "abstention_reason": "Only one recorded observation is available."}
    result = diagnostics.diagnose_decision(json.dumps(output), request(sparse), sparse)
    assert result["source_validation"]["status"] == "valid"
    assert result["semantic_assessment"] == "unknown"
    assert result["semantic_quality_verified"] is False


@pytest.mark.parametrize("saved_request", [{}, {"format": "json"}, [], {"format": None}])
def test_malformed_saved_request_does_not_guess_schema(snapshot, saved_request):
    result = diagnostics.diagnose_decision(json.dumps(candidate()), saved_request, snapshot)
    assert result["request_validation"]["status"] == "invalid"
    assert result["wire_schema"]["status"] == "unavailable"
    assert result["outcome_contract"]["status"] == "valid"


@pytest.mark.parametrize("schema", [
    {"$ref": "https://example.invalid/decision.json"},
    {"$ref": "file:///tmp/decision.json"},
    {"$dynamicRef": "https://example.invalid/decision.json"},
])
def test_external_reference_is_refused_without_network(snapshot, schema):
    result = diagnostics.diagnose_decision(json.dumps(candidate()), {"format": schema}, snapshot)
    assert result["wire_schema"]["status"] == "error"
    assert "disabled" in result["wire_schema"]["issues"][0]
    assert result["schema_runtime_mismatch"] is False


def test_invalid_format_schema_is_a_diagnostic_error(snapshot):
    result = diagnostics.diagnose_decision(
        json.dumps(candidate()), {"format": {"type": 123}}, snapshot,
    )
    assert result["wire_schema"]["status"] == "error"
    assert result["schema_runtime_mismatch"] is False


def test_missing_optional_jsonschema_has_actionable_error(snapshot, monkeypatch):
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    result = diagnostics.diagnose_decision(json.dumps(candidate()), request(snapshot), snapshot)
    assert result["wire_schema"]["status"] == "unavailable"
    assert "pip install -e '.[dev]'" in result["wire_schema"]["issues"][0]
    assert result["outcome_contract"]["status"] == result["source_validation"]["status"] == "valid"


def test_saved_request_evidence_must_match_snapshot(snapshot):
    saved_request = request(snapshot)
    payload = json.loads(saved_request["messages"][1]["content"])
    payload["evidence"][0]["observation"] = "Altered evidence"
    saved_request["messages"][1]["content"] = json.dumps(payload)
    result = diagnostics.diagnose_decision(json.dumps(candidate()), saved_request, snapshot)
    assert result["request_evidence_alignment"]["status"] == "invalid"
    assert result["source_validation"]["status"] == "unavailable"
    assert result["outcome_contract"]["status"] == "valid"


@pytest.mark.parametrize("messages", [None, [], ["invalid"], [{"role": "user", "content": "bad"}]])
def test_malformed_request_messages_are_reported(snapshot, messages):
    result = diagnostics.diagnose_decision(
        json.dumps(candidate()), {"format": decision_schema(), "messages": messages}, snapshot,
    )
    assert result["request_evidence_alignment"]["status"] == "invalid"
    assert result["source_validation"]["status"] == "unavailable"


def test_repair_feedback_is_permitted_after_matching_user_evidence(snapshot):
    saved_request = request(snapshot)
    saved_request["messages"] += [
        {"role": "assistant", "content": "Earlier rejected output"},
        {"role": "user", "content": "Repair the structural error."},
    ]
    result = diagnostics.diagnose_decision(json.dumps(candidate()), saved_request, snapshot)
    assert result["request_evidence_alignment"]["status"] == "valid"
    assert result["source_validation"]["status"] == "valid"


def saved_files(tmp_path, snapshot):
    files = {name: tmp_path / filename for name, filename in (
        ("response", "response.txt"), ("request", "request.json"), ("snapshot", "snapshot.json"),
    )}
    files["response"].write_bytes((json.dumps(candidate()) + "\r\n").encode())
    files["request"].write_text(json.dumps(request(snapshot)), encoding="utf-8")
    files["snapshot"].write_text(json.dumps({
        "sha256": snapshot.sha256, "payload": json.loads(snapshot.payload_json),
    }), encoding="utf-8")
    return files


def arguments(files):
    return [item for name, path in files.items() for item in ("--" + name, str(path))]


def test_cli_prints_diagnosis_and_hashes_exact_input_bytes_without_writes(
    tmp_path, snapshot, capsys,
):
    files = saved_files(tmp_path, snapshot)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert diagnostics.main(arguments(files)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["source_validation"]["status"] == "valid"
    assert result["provenance"]["input_file_sha256"] == {
        name: hashlib.sha256(before[path]).hexdigest() for name, path in files.items()
    }
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


@pytest.mark.parametrize("bad_input", ["digest", "target", "request", "message", "missing"])
def test_cli_fails_bad_provided_evidence_paths_or_requests(
    tmp_path, snapshot, capsys, bad_input,
):
    files = saved_files(tmp_path, snapshot)
    if bad_input in {"digest", "target"}:
        saved = json.loads(files["snapshot"].read_text(encoding="utf-8"))
        if bad_input == "digest":
            saved["sha256"] = "0" * 64
        else:
            saved["payload"]["learner_id"] = "L002"
        files["snapshot"].write_text(json.dumps(saved), encoding="utf-8")
    elif bad_input == "request":
        files["request"].write_text("null", encoding="utf-8")
    elif bad_input == "message":
        saved = request(snapshot)
        saved["messages"][1]["content"] = "{}"
        files["request"].write_text(json.dumps(saved), encoding="utf-8")
    else:
        files["response"] = tmp_path / "does-not-exist.txt"
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    assert diagnostics.main(arguments(files)) == 2
    assert "Cannot inspect saved decision" in capsys.readouterr().err
    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before


def test_cli_with_no_inputs_reports_unavailable(capsys):
    assert diagnostics.main([]) == 0
    assert json.loads(capsys.readouterr().out)["json"]["status"] == "unavailable"


@pytest.mark.parametrize("name", ["request", "snapshot"])
def test_cli_rejects_non_json_constants_in_saved_inputs(tmp_path, snapshot, capsys, name):
    files = saved_files(tmp_path, snapshot)
    files[name].write_text('{"unexpected": NaN}', encoding="utf-8")
    assert diagnostics.main(arguments(files)) == 2
    assert "Non-JSON numeric constant" in capsys.readouterr().err


def test_public_snapshot_loader_checks_hash_and_target(snapshot):
    saved = {"sha256": snapshot.sha256, "payload": json.loads(snapshot.payload_json)}
    assert diagnostics.load_saved_snapshot(saved) == snapshot
    saved["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        diagnostics.load_saved_snapshot(saved)
    saved["payload"]["learner_id"] = ""
    with pytest.raises(ValueError, match="identify"):
        diagnostics.load_saved_snapshot(saved)
