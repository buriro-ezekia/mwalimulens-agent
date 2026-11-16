"""Verify saved hosted cases before exposing any teacher decision controls."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from mwalimulens.agent.candidate_contract import (
    OUTCOME_DECISION_SCHEMA_ID,
    EvidenceSnapshot,
    ProposalRejected,
    decision_schema,
    validate_decision,
)
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService, _evidence_payload
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.portal_qwen import _validate_saved_human_state

TARGET = ("L001", "MATH-FRACTIONS")
BASE = {"generation-state.json", "result.json"}
COMPLETE = BASE | {
    "request.json",
    "response.txt",
    "evidence_snapshot.json",
    "proposals.json",
    "provider-metrics.json",
}
STATE_KEYS = {"pending_reviews", "teacher_reviews", "profile_updates", "tool_calls"}


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _bytes(path: Path) -> bytes:
    _require(not path.is_symlink() and path.is_file(), f"Missing or linked artefact: {path.name}")
    _require(path.stat().st_size <= 8 * 1024 * 1024, "Oversized saved artefact")
    return path.read_bytes()


def _object(data: bytes) -> dict[str, Any]:
    def invalid_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")

    value = json.loads(data, parse_constant=invalid_constant)
    _require(isinstance(value, dict), "Saved records must be JSON objects")
    return value


def _state(value: dict[str, Any]) -> None:
    _require(
        set(value) == STATE_KEYS
        and all(
            isinstance(value[key], list) and all(isinstance(item, dict) for item in value[key])
            for key in STATE_KEYS
        ),
        "Invalid saved state structure",
    )


def open_case(directory: Path):
    """Return a read-only verified case; mutable state must never be reconstructed."""
    try:
        return _open_case(directory)
    except (OSError, KeyError, TypeError, IndexError, AttributeError, UnicodeError) as exc:
        raise ValueError("Saved Bedrock case is incomplete or inconsistent") from exc


def _open_case(directory: Path):
    from mwalimulens.bedrock_review import MODEL
    from mwalimulens.teacher_portal import Case

    directory = directory.resolve()
    receipt = _object(_bytes(directory / "receipt.json"))
    hashes = receipt.get("sha256")
    _require(
        receipt.get("case_id") == directory.name and isinstance(hashes, dict),
        "Invalid Bedrock receipt",
    )
    _require(BASE.issubset(hashes) and set(hashes).issubset(COMPLETE), "Incomplete Bedrock receipt")
    raw = {}
    for name, digest in hashes.items():
        raw[name] = _bytes(directory / name)
        _require(
            isinstance(digest, str) and hashlib.sha256(raw[name]).hexdigest() == digest,
            "Saved Bedrock artefacts changed",
        )
    _require(
        all(not (directory / name).exists() or name in hashes for name in COMPLETE),
        "Saved artefact is omitted from receipt",
    )
    result = _object(raw["result.json"])
    generation = _object(raw["generation-state.json"])
    current = _object(_bytes(directory / "state.json"))
    _state(generation)
    _state(current)
    _require(
        result.get("case_id") == directory.name
        and result.get("provider") == "bedrock"
        and result.get("model") == MODEL
        and result.get("request_limit") == 1,
        "Saved provider or case identity differs",
    )
    delivery = result.get("request_delivery")
    _require(isinstance(delivery, dict), "Saved request delivery is unavailable")
    attempts_count = delivery.get("http_attempts")
    delivery_status = delivery.get("status")
    _require(
        type(attempts_count) is int
        and attempts_count in {0, 1}
        and delivery_status in {"not_started", "in_flight", "returned", "unknown"}
        and ((delivery_status == "not_started") == (attempts_count == 0)),
        "Invalid request delivery record",
    )
    status = result["outcome"]["status"]
    _require(
        status in {"submitted", "abstained", "invalid_proposal", "error"}, "Unknown Bedrock outcome"
    )
    if delivery_status == "returned" or status != "error":
        _require(set(hashes) == COMPLETE, "Returned observation has incomplete provenance")
    if status != "error":
        _require(
            delivery_status == "returned" and result.get("error_type") is None,
            "Completed outcome conflicts with request delivery",
        )
    _require(
        not generation["teacher_reviews"] and not generation["profile_updates"],
        "Generation cannot contain a teacher decision or profile note",
    )
    calls = generation["tool_calls"]
    snapshot = None
    evidence = []
    if "evidence_snapshot.json" in raw:
        source = _object(raw["evidence_snapshot.json"])
        snapshot = EvidenceSnapshot.from_mcp(source["payload"], TARGET)
        _require(source.get("sha256") == snapshot.sha256, "Evidence snapshot digest differs")
        _require(
            bool(calls)
            and calls[0].get("tool_name") == "get_competency_evidence"
            and calls[0].get("status") == "success"
            and calls[0].get("inputs")
            == dict(zip(("learner_id", "competency_code"), TARGET, strict=True))
            and calls[0].get("output") == source["payload"],
            "Saved evidence differs from its MCP retrieval",
        )
        dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
        _require(
            all(learner.synthetic for learner in dataset.learners),
            "Only fictional fixtures are permitted",
        )
        expected = {
            "learner_id": TARGET[0],
            "competency_code": TARGET[1],
            "evidence": [_evidence_payload(row) for row in dataset.competency_evidence(*TARGET)],
        }
        expected["evidence_count"] = len(expected["evidence"])
        _require(source["payload"] == expected, "Saved evidence differs from current fixture")
        evidence = source["payload"]["evidence"]
    else:
        dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)

    raw_output = None
    if "proposals.json" in raw:
        attempts = _object(raw["proposals.json"])["attempts"]
        _require(
            isinstance(attempts, list) and len(attempts) == 1 and snapshot is not None,
            "Expected one snapshot-bound proposal",
        )
        attempt = attempts[0]
        messages, schema = attempt["messages"], attempt["schema"]
        _require(
            isinstance(messages, list)
            and len(messages) == 2
            and [item.get("role") for item in messages] == ["system", "user"]
            and all(isinstance(item.get("content"), str) and item["content"] for item in messages)
            and json.loads(messages[1]["content"]) == json.loads(snapshot.payload_json)
            and schema == decision_schema(OUTCOME_DECISION_SCHEMA_ID),
            "Logical proposal inputs differ from the snapshot or schema",
        )
        raw_output = attempt.get("raw_output")
        _require(raw_output is None or isinstance(raw_output, str), "Invalid raw decision")
        if "request.json" in raw:
            request = _object(raw["request.json"])
            user_text = request["messages"][0]["content"][0]["text"]
            prefix = "Evidence snapshot:\n" + messages[1]["content"] + "\n\nDecision JSON Schema:\n"
            _require(
                isinstance(user_text, str)
                and user_text.startswith(prefix)
                and json.loads(user_text[len(prefix) :]) == schema,
                "Saved HTTP request differs from logical generation inputs",
            )
            # The persisted logical schema uses sorted keys; compare schema objects,
            # not its non-semantic JSON property ordering inside the HTTP prompt.
            expected_request = {
                "system": [{"text": messages[0]["content"]}],
                "messages": [{"role": "user", "content": [{"text": user_text}]}],
                "inferenceConfig": {"maxTokens": 1024, "temperature": 0, "topP": 1},
            }
            _require(
                request == expected_request,
                "Saved HTTP request differs from logical generation inputs",
            )
    else:
        _require("request.json" not in raw, "HTTP request has no logical proposal record")

    metrics = _object(raw["provider-metrics.json"]) if "provider-metrics.json" in raw else {}
    if "response.txt" in raw:
        _require(
            delivery_status == "returned" and type(metrics.get("http_status")) is int,
            "HTTP response conflicts with delivery metrics",
        )
        try:
            response = _object(raw["response.txt"])
        except ValueError:
            _require(
                status == "error" and raw_output is None,
                "Malformed provider response cannot yield a decision",
            )
            response = {}
        if raw_output is not None:
            message = response["output"]["message"]
            content = message["content"]
            _require(
                200 <= metrics["http_status"] < 300
                and response.get("stopReason") == "end_turn"
                and message.get("role") == "assistant"
                and content
                and all(
                    isinstance(block, dict)
                    and set(block) == {"text"}
                    and isinstance(block["text"], str)
                    for block in content
                )
                and "".join(block["text"] for block in content) == raw_output
                and metrics.get("stop_reason") == response.get("stopReason")
                and metrics.get("usage") == response.get("usage")
                and metrics.get("metrics") == response.get("metrics"),
                "Raw provider response differs from saved decision or metrics",
            )
    else:
        _require(raw_output is None, "Decision has no provider response")

    candidate = None
    if status == "submitted":
        _require(
            snapshot is not None and raw_output is not None,
            "Submitted outcome has no verified decision",
        )
        decision = validate_decision(raw_output, snapshot)
        _require(
            decision.candidate is not None and len(generation["pending_reviews"]) == 1,
            "Submitted outcome has no single model candidate",
        )
        candidate = generation["pending_reviews"][0]
        _require(
            all(
                candidate.get(key) == value
                for key, value in decision.candidate.model_dump().items()
            )
            and candidate.get("status") == "pending_teacher_review"
            and result["outcome"].get("review") == candidate
            and len(calls) == 2
            and calls[1].get("tool_name") == "flag_pattern_for_review"
            and calls[1].get("status") == "success"
            and calls[1].get("inputs") == decision.candidate.model_dump()
            and calls[1].get("output") == candidate,
            "Saved candidate differs from its model decision or MCP submission",
        )
    else:
        _require(
            not generation["pending_reviews"]
            and all(call.get("tool_name") == "get_competency_evidence" for call in calls),
            "Non-candidate outcome contains candidate actions",
        )
        if status == "abstained":
            decision = validate_decision(raw_output, snapshot)
            _require(
                decision.outcome == "abstain"
                and result["outcome"].get("final_output")
                == "ABSTAIN: " + decision.abstention_reason,
                "Abstention differs from the raw decision",
            )
        elif status == "invalid_proposal":
            try:
                validate_decision(raw_output, snapshot)
            except ProposalRejected:
                pass
            else:
                raise ValueError("Rejected outcome contains a valid decision")
    _require(current["tool_calls"][: len(calls)] == calls, "Original MCP audit changed")
    _validate_saved_human_state(generation, current)
    store = JsonStateStore(directory / "state.json")
    return Case(
        store,
        EducationToolService(dataset, store),
        candidate,
        evidence,
        directory,
        "bedrock",
        report=result,
        analysis_status="candidate"
        if candidate
        else ("abstained" if status == "abstained" else "error"),
        abstention_reason=result["outcome"].get("final_output", ""),
        analysis_error=result.get("error_type") or "Response rejected by validation",
        opened_as="Saved Bedrock case reopened; no model request was made",
    )
