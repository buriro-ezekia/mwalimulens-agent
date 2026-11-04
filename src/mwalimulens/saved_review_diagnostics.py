"""Inspect saved decisions offline without generating, submitting or regrading them."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mwalimulens.agent.candidate_contract import (
    EvidenceSnapshot,
    ProposalRejected,
    ReviewDecision,
    validate_decision,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


def _parse(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_constant)


def _status(status: str, *issues: str) -> dict[str, Any]:
    return {"status": status, "issues": list(issues)}


def _validation_issues(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(part) for part in item['loc']) or 'decision'}: {item['type']}"
        for item in exc.errors(include_input=False, include_url=False)
    ]


def _wire_validation(value: Any, schema: Any) -> dict[str, Any]:
    # This dependency is optional for the application and loaded only for this analysis.
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry
        from referencing.exceptions import NoSuchResource
    except ImportError:
        return _status(
            "unavailable",
            "Wire-schema validation requires jsonschema; install development dependencies "
            "with: python -m pip install -e '.[dev]'",
        )

    def refuse_retrieval(uri: str):
        raise NoSuchResource(ref=uri)

    def external_references(node: Any) -> list[str]:
        if isinstance(node, list):
            return [ref for item in node for ref in external_references(item)]
        if not isinstance(node, dict):
            return []
        refs = [
            value for key, value in node.items()
            if key in {"$ref", "$dynamicRef"} and isinstance(value, str)
            and value and not value.startswith("#")
        ]
        return refs + [ref for item in node.values() for ref in external_references(item)]

    try:
        Draft202012Validator.check_schema(schema)
        if external_references(schema):
            return _status("error", "External schema references are disabled for offline analysis")
        validator = Draft202012Validator(schema, registry=Registry(retrieve=refuse_retrieval))
        issues = [
            f"{'.'.join(str(part) for part in item.absolute_path) or 'decision'}: "
            f"{item.validator}"
            for item in validator.iter_errors(value)
        ]
        return {"status": "invalid" if issues else "valid", "issues": issues}
    except Exception as exc:
        return _status("error", f"Cannot validate saved schema offline: {type(exc).__name__}")


def _check_snapshot(snapshot: EvidenceSnapshot) -> EvidenceSnapshot:
    if not all(
        isinstance(value, str) and value.strip()
        for value in (snapshot.learner_id, snapshot.competency_code)
    ):
        raise ValueError("Saved snapshot must identify its learner and competency")
    verified = EvidenceSnapshot.from_mcp(
        _parse(snapshot.payload_json), (snapshot.learner_id, snapshot.competency_code),
    )
    if verified.sha256 != snapshot.sha256:
        raise ValueError("Saved evidence snapshot hash mismatch")
    return verified


def diagnose_decision(
    raw_output: str | None, request: dict | None, snapshot: EvidenceSnapshot | None,
) -> dict[str, Any]:
    """Return independent validation layers; semantic quality always remains unknown.

    The request must contain the actual saved ``format`` schema. If messages are
    present, the first user message must contain the unchanged evidence snapshot;
    later repair feedback is permitted. No missing input is reconstructed.
    """

    result: dict[str, Any] = {
        "diagnostic_version": "saved_review_diagnostics_v1",
        "json": _status("unavailable", "No raw response supplied"),
        "wire_schema": _status("unavailable", "Raw response and saved format schema required"),
        "outcome_contract": _status("unavailable", "No raw response supplied"),
        "source_validation": _status("unavailable", "Valid outcome and verified snapshot required"),
        "request_validation": _status("unavailable", "No saved request supplied"),
        "request_evidence_alignment": _status(
            "unavailable", "Request messages and snapshot required",
        ),
        "snapshot_validation": _status("unavailable", "No saved evidence snapshot supplied"),
        "parsed_output": None, "decision_outcome": None, "abstention_reason": None,
        "schema_runtime_mismatch": False,
        "semantic_assessment": "unknown", "manual_semantic_review_required": True,
        "semantic_quality_verified": False,
        "provenance": {
            "raw_output_sha256": None, "request_canonical_sha256": None,
            "wire_schema_canonical_sha256": None, "evidence_sha256": None,
            "outcome_contract_canonical_sha256": _sha(
                _canonical(ReviewDecision.model_json_schema()),
            ),
            "runtime_validator": "mwalimulens.agent.candidate_contract.validate_decision",
            "validation_basis": "Current runtime validation; no saved grade is recomputed",
            "hash_encoding": "UTF-8; canonical JSON uses sort_keys=True, "
            "ensure_ascii=False, allow_nan=False and standard spacing",
        },
    }
    verified_snapshot = None
    if snapshot is not None:
        try:
            verified_snapshot = _check_snapshot(snapshot)
            result["snapshot_validation"] = _status("valid")
            result["provenance"]["evidence_sha256"] = verified_snapshot.sha256
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            result["snapshot_validation"] = _status("invalid", str(exc))

    schema = None
    if request is not None:
        try:
            if not isinstance(request, dict):
                raise ValueError("Saved request must be a JSON object")
            result["provenance"]["request_canonical_sha256"] = _sha(_canonical(request))
            schema = request.get("format")
            if not isinstance(schema, (dict, bool)):
                raise ValueError("Saved request must contain its exact JSON Schema in format")
            result["provenance"]["wire_schema_canonical_sha256"] = _sha(_canonical(schema))
            result["request_validation"] = _status("valid")
        except (TypeError, ValueError) as exc:
            result["request_validation"] = _status("invalid", str(exc))
            schema = None
        if isinstance(request, dict) and "messages" in request:
            try:
                messages = request["messages"]
                if not isinstance(messages, list) or not all(
                    isinstance(message, dict) for message in messages
                ):
                    raise ValueError("Saved request messages must be a list of objects")
                user = next(
                    (message for message in messages if message.get("role") == "user"), None,
                )
                if user is None or not isinstance(user.get("content"), str):
                    raise ValueError("Saved request must contain a user evidence JSON message")
                evidence = _parse(user["content"])
                if not isinstance(evidence, dict):
                    raise ValueError("Saved request user evidence must be a JSON object")
                if verified_snapshot is not None:
                    if _canonical(evidence) != _canonical(_parse(verified_snapshot.payload_json)):
                        raise ValueError("Saved request user evidence does not match the snapshot")
                    result["request_evidence_alignment"] = _status("valid")
            except (TypeError, ValueError) as exc:
                result["request_evidence_alignment"] = _status("invalid", str(exc))

    if raw_output is None:
        return result
    if not isinstance(raw_output, str):
        result["json"] = _status("invalid", "Raw response must be text")
        return result
    result["provenance"]["raw_output_sha256"] = _sha(raw_output.encode("utf-8"))
    try:
        result["parsed_output"] = _parse(raw_output)
        result["json"] = _status("valid")
    except ValueError as exc:
        result["json"] = _status("invalid", str(exc))
    if result["json"]["status"] == "valid" and schema is not None:
        result["wire_schema"] = _wire_validation(result["parsed_output"], schema)
    try:
        decision = ReviewDecision.model_validate_json(raw_output)
        if result["json"]["status"] != "valid":
            result["outcome_contract"] = _status("unavailable", "Strict JSON parsing failed")
            return result
        result["outcome_contract"] = _status("valid")
        result["decision_outcome"] = decision.outcome
        # Preserve the raw field, including whitespace; never replace it with normalised output.
        result["abstention_reason"] = result["parsed_output"].get("abstention_reason")
    except ValidationError as exc:
        result["outcome_contract"] = {
            "status": "invalid", "issues": _validation_issues(exc),
        }
    result["schema_runtime_mismatch"] = (
        result["wire_schema"]["status"] == "valid"
        and result["outcome_contract"]["status"] == "invalid"
    )
    if (
        result["outcome_contract"]["status"] == "valid" and verified_snapshot is not None
        and result["request_evidence_alignment"]["status"] != "invalid"
    ):
        try:
            validate_decision(raw_output, verified_snapshot)
            result["source_validation"] = _status("valid")
        except ProposalRejected as exc:
            result["source_validation"] = {"status": "invalid", "issues": exc.issues}
    return result


def load_saved_snapshot(saved: Any) -> EvidenceSnapshot:
    """Verify a parsed saved {sha256, payload} object, including its evidence target."""
    if not isinstance(saved, dict) or not isinstance(saved.get("payload"), dict):
        raise ValueError("Saved snapshot must contain sha256 and an evidence payload object")
    payload = saved["payload"]
    target = (payload.get("learner_id"), payload.get("competency_code"))
    if not all(isinstance(value, str) and value.strip() for value in target):
        raise ValueError("Saved snapshot must identify its learner and competency")
    snapshot = EvidenceSnapshot.from_mcp(payload, target)
    if snapshot.sha256 != saved.get("sha256"):
        raise ValueError("Saved evidence snapshot hash mismatch")
    return snapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--response", type=Path, help="Exact saved raw response text")
    parser.add_argument("--request", type=Path, help="Saved request JSON containing format")
    parser.add_argument("--snapshot", type=Path, help="Saved {sha256, payload} evidence JSON")
    args = parser.parse_args(argv)
    try:
        supplied = {
            name: path.read_bytes() for name in ("response", "request", "snapshot")
            if (path := getattr(args, name)) is not None
        }
        response = supplied["response"].decode("utf-8") if "response" in supplied else None
        request = _parse(supplied["request"].decode("utf-8")) if "request" in supplied else None
        if "request" in supplied and not isinstance(request, dict):
            raise ValueError("Saved request must be a JSON object")
        snapshot = (
            load_saved_snapshot(_parse(supplied["snapshot"].decode("utf-8")))
            if "snapshot" in supplied else None
        )
        result = diagnose_decision(response, request, snapshot)
        for name in ("request_validation", "request_evidence_alignment", "snapshot_validation"):
            if result[name]["status"] == "invalid":
                raise ValueError("; ".join(result[name]["issues"]))
        result["provenance"]["input_file_sha256"] = {
            name: _sha(data) for name, data in supplied.items()
        }
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        print(f"Cannot inspect saved decision: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    if result["wire_schema"]["status"] == "error" or (
        request is not None and response is not None
        and result["wire_schema"]["status"] == "unavailable"
        and result["json"]["status"] == "valid"
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
