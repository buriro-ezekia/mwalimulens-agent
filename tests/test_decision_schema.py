"""Schema/runtime agreement is structural; none of these tests establish model judgement."""

from __future__ import annotations

import asyncio
import hashlib
import itertools
import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from mwalimulens.agent.candidate_contract import (
    DECISION_POLICY_ID,
    DECISION_SCHEMA_IDS,
    DEFAULT_DECISION_SCHEMA_ID,
    OUTCOME_DECISION_SCHEMA_ID,
    EvidenceSnapshot,
    ProposalRejected,
    ReviewDecision,
    decide_and_submit,
    decision_schema,
    decision_schema_metadata,
    review_messages,
    validate_decision,
)


def candidate():
    return {
        "learner_id": "TEST-LEARNER", "competency_code": "TEST-COMPETENCY",
        "claim": "Recorded performance differs, while explanation remains uncertain.",
        "supporting_evidence_ids": ["E-A", "E-B"],
        "counter_evidence_ids": ["E-C"],
        "uncertainty": "These different tasks do not establish independent mastery.",
        "suggested_teacher_question": "Can the learner explain a comparable task unaided?",
    }


def snapshot():
    rows = [{
        "learner_id": "TEST-LEARNER", "competency_code": "TEST-COMPETENCY",
        "evidence_id": ident, "term_id": term, "source_ref": f"synthetic://{ident}",
        "occurred_at": "2025-01-01T00:00:00Z",
    } for ident, term in [("E-A", "T1"), ("E-B", "T2"), ("E-C", "T2")]]
    return EvidenceSnapshot.from_mcp({
        "learner_id": "TEST-LEARNER", "competency_code": "TEST-COMPETENCY",
        "evidence_count": 3, "evidence": rows,
    }, ("TEST-LEARNER", "TEST-COMPETENCY"))


def candidate_decision(reason=None):
    return {"outcome": "candidate", "candidate": candidate(), "abstention_reason": reason}


def test_observed_string_null_is_schema_valid_in_v1_but_rejected_in_v2():
    # Reproduces the observed cross-field shape without changing the saved response.
    value = candidate_decision("null")
    original = deepcopy(value)
    assert Draft202012Validator(decision_schema()).is_valid(value)
    with pytest.raises(ValidationError):
        ReviewDecision.model_validate_json(json.dumps(value))
    assert not Draft202012Validator(decision_schema(OUTCOME_DECISION_SCHEMA_ID)).is_valid(value)
    assert value == original


def test_legacy_default_and_schema_fingerprint_remain_unchanged():
    assert DEFAULT_DECISION_SCHEMA_ID == "review_decision_v1"
    assert decision_schema() == ReviewDecision.model_json_schema()
    encoded = json.dumps(decision_schema(), sort_keys=True, ensure_ascii=False, allow_nan=False)
    assert decision_schema_metadata()["decision_schema_sha256"] == hashlib.sha256(
        encoded.encode("utf-8")
    ).hexdigest()
    assert DECISION_POLICY_ID == "provisional_review_v2"


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_schemas_are_valid_and_all_candidate_fields_are_preserved(schema_id):
    schema = decision_schema(schema_id)
    Draft202012Validator.check_schema(schema)
    assert schema["$defs"] == ReviewDecision.model_json_schema()["$defs"]
    assert set(schema["$defs"]["CandidateProposal"]["required"]) == set(candidate())
    assert schema["$defs"]["CandidateProposal"]["additionalProperties"] is False
    assert Draft202012Validator(schema).is_valid(candidate_decision())
    assert Draft202012Validator(schema).is_valid({
        "outcome": "abstain", "candidate": None,
        "abstention_reason": "Comparability prevents a defensible description.",
    })


@pytest.mark.parametrize("outcome,payload,reason", list(itertools.product(
    ["candidate", "abstain", "approve"], [None, candidate(), "null"],
    [None, "null", "Comparability is insufficient.", "", 0],
)))
def test_v2_cross_field_matrix_matches_runtime_contract(outcome, payload, reason):
    value = {"outcome": outcome, "candidate": payload, "abstention_reason": reason}
    try:
        ReviewDecision.model_validate_json(json.dumps(value))
        accepted = True
    except ValidationError:
        accepted = False
    assert Draft202012Validator(decision_schema(OUTCOME_DECISION_SCHEMA_ID)).is_valid(
        value
    ) is accepted


@pytest.mark.parametrize("field", ["outcome", "candidate", "abstention_reason"])
def test_missing_root_fields_are_not_default_filled(field):
    value = candidate_decision()
    del value[field]
    assert not Draft202012Validator(decision_schema(OUTCOME_DECISION_SCHEMA_ID)).is_valid(value)


@pytest.mark.parametrize("field", list(candidate()))
def test_missing_candidate_fields_are_not_default_filled(field):
    value = candidate_decision()
    del value["candidate"][field]
    assert not Draft202012Validator(decision_schema(OUTCOME_DECISION_SCHEMA_ID)).is_valid(value)


def test_extra_fields_and_empty_abstention_are_not_permitted():
    schema = Draft202012Validator(decision_schema(OUTCOME_DECISION_SCHEMA_ID))
    assert not schema.is_valid({**candidate_decision(), "approved": True})
    value = candidate_decision()
    value["candidate"]["approved"] = True
    assert not schema.is_valid(value)
    assert not schema.is_valid({"outcome": "abstain", "candidate": None, "abstention_reason": ""})


def test_complete_branches_do_not_mix_anyof_with_properties_at_same_level():
    schema = decision_schema(OUTCOME_DECISION_SCHEMA_ID)
    assert "properties" not in schema and "type" not in schema
    assert len(schema["anyOf"]) == 2
    assert [branch["properties"]["outcome"]["const"] for branch in schema["anyOf"]] == [
        "candidate", "abstain",
    ]
    assert all(branch["additionalProperties"] is False for branch in schema["anyOf"])


def test_returned_schema_mutation_cannot_change_next_call_or_legacy():
    before = decision_schema_metadata(OUTCOME_DECISION_SCHEMA_ID)
    schema = decision_schema(OUTCOME_DECISION_SCHEMA_ID)
    schema["$defs"].clear()
    schema["anyOf"].clear()
    assert decision_schema_metadata(OUTCOME_DECISION_SCHEMA_ID) == before
    assert decision_schema() == ReviewDecision.model_json_schema()
    assert before["decision_schema_sha256"] != decision_schema_metadata()["decision_schema_sha256"]


@pytest.mark.parametrize("field,value", [
    ("learner_id", "OTHER"),
    ("supporting_evidence_ids", ["E-A", "UNKNOWN"]),
    ("supporting_evidence_ids", ["E-A", "E-A"]),
    ("supporting_evidence_ids", ["E-B", "E-C"]),
    ("counter_evidence_ids", ["E-A"]),
    ("claim", " "),
])
def test_wire_schema_does_not_replace_existing_evidence_and_runtime_checks(field, value):
    item = candidate_decision()
    item["candidate"][field] = value
    # JSON Schema cannot know evidence membership, comparability or stripped whitespace.
    assert Draft202012Validator(decision_schema(OUTCOME_DECISION_SCHEMA_ID)).is_valid(item)
    with pytest.raises(ProposalRejected):
        validate_decision(json.dumps(item), snapshot())


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_invalid_output_never_normalised_or_submitted_even_if_provider_ignores_schema(schema_id):
    sent, actions = [], []
    bad_text = json.dumps(candidate_decision("null"))

    async def generate(messages, schema):
        sent.append((deepcopy(messages), deepcopy(schema)))
        schema.clear()  # A callback must not corrupt the next repair's schema.
        return bad_text

    async def submit(args):
        actions.append(args)
        raise AssertionError("Invalid response reached submission")

    result = asyncio.run(decide_and_submit(
        snapshot(), generate=generate, submit=submit, observe=lambda event: None,
        decision_schema_id=schema_id,
    ))
    assert result["status"] == "invalid_proposal"
    assert len(sent) == 2 and not actions
    assert sent[0][1] == sent[1][1] == decision_schema(schema_id)
    assert sent[0][0] == review_messages(snapshot())
    assert sent[1][0][-2] == {"role": "assistant", "content": bad_text}
    assert all(attempt["status"] == "invalid" for attempt in result["attempts"])


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_genuine_abstention_stops_after_one_proposal_without_side_effect(schema_id):
    calls = []

    async def generate(messages, schema):
        calls.append((messages, schema))
        return json.dumps({"outcome": "abstain", "candidate": None,
                           "abstention_reason": "Comparability prevents a bounded interpretation."})

    async def submit(_args):
        raise AssertionError("An abstention must not be submitted")

    result = asyncio.run(decide_and_submit(
        snapshot(), generate=generate, submit=submit, observe=lambda event: None,
        decision_schema_id=schema_id,
    ))
    assert result["status"] == "abstained" and len(calls) == 1
    assert calls[0] == (review_messages(snapshot()), decision_schema(schema_id))


def test_unknown_schema_stops_before_generation_or_submission():
    async def forbidden(*_args):
        raise AssertionError("Unknown schema must not perform work")

    with pytest.raises(ValueError, match="Unknown decision schema"):
        asyncio.run(decide_and_submit(
            snapshot(), generate=forbidden, submit=forbidden, observe=lambda event: None,
            decision_schema_id="unknown",
        ))


@pytest.mark.parametrize("schema_id", DECISION_SCHEMA_IDS)
def test_valid_candidate_submission_preserves_authored_content(schema_id):
    actions = []

    async def generate(messages, schema):
        assert messages == review_messages(snapshot())
        assert schema == decision_schema(schema_id)
        return json.dumps(candidate_decision())

    async def submit(args):
        actions.append(deepcopy(args))
        return {**args, "review_id": "test-review", "status": "pending_teacher_review"}

    result = asyncio.run(decide_and_submit(
        snapshot(), generate=generate, submit=submit, observe=lambda event: None,
        decision_schema_id=schema_id,
    ))
    assert result["status"] == "submitted" and actions == [candidate()]
    assert result["review"]["status"] == "pending_teacher_review"
