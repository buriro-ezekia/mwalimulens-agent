"""The exact missing-field failure cannot reach the submission callback."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from mwalimulens.agent.candidate_contract import (
    EvidenceSnapshot,
    ProposalRejected,
    ReviewDecision,
    decide_and_submit,
    validate_decision,
)
from mwalimulens.agent.structured_ollama import OllamaJsonGenerator


def snapshot():
    rows = [
        {"evidence_id": ident, "term_id": term, "learner_id": "L001",
         "competency_code": "MATH-FRACTIONS", "source_ref": f"synthetic://{ident}",
         "occurred_at": "2025-01-01T00:00:00Z", "observation": note}
        for ident, term, note in [
            ("EV-A", "2025-T1", None), ("EV-B", "2025-T2", None),
            ("EV-C", "2025-T2", "Needed help explaining the method."),
        ]
    ]
    return EvidenceSnapshot.from_mcp({
        "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
        "evidence_count": len(rows), "evidence": rows,
    }, ("L001", "MATH-FRACTIONS"))


def candidate():
    return {
        "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
        "claim": "Recorded performance changed while independent explanation remains mixed.",
        "supporting_evidence_ids": ["EV-A", "EV-B"],
        "counter_evidence_ids": ["EV-C"],
        "uncertainty": "The observations do not establish independent explanation.",
        "suggested_teacher_question": "Can the learner explain a new task unaided?",
    }


def encoded(value=None):
    return json.dumps({"outcome": "candidate", "candidate": value or candidate(),
                       "abstention_reason": None})


@pytest.mark.parametrize("field", list(candidate()))
def test_each_mcp_argument_is_required_not_default_filled(field):
    item = candidate()
    del item[field]
    with pytest.raises(ProposalRejected):
        validate_decision(encoded(item), snapshot())


def test_schema_requires_the_complete_decision_and_all_seven_candidate_fields():
    schema = ReviewDecision.model_json_schema()
    assert set(schema["required"]) == {"outcome", "candidate", "abstention_reason"}
    assert set(schema["$defs"]["CandidateProposal"]["required"]) == set(candidate())
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["CandidateProposal"]["additionalProperties"] is False


@pytest.mark.parametrize("field,value", [
    ("claim", ""), ("suggested_teacher_question", "   "),
    ("learner_id", "L002"), ("competency_code", "OTHER"),
    ("supporting_evidence_ids", ["EV-A", "EV-A"]),
    ("supporting_evidence_ids", ["EV-B", "EV-C"]),
    ("supporting_evidence_ids", ["EV-A", "EV-UNKNOWN"]),
    ("counter_evidence_ids", []), ("counter_evidence_ids", ["EV-A"]),
])
def test_invalid_values_and_evidence_fail_before_action(field, value):
    item = candidate()
    item[field] = value
    with pytest.raises(ProposalRejected):
        validate_decision(encoded(item), snapshot())


@pytest.mark.parametrize("text", [
    "I will submit the candidate now.", '{"outcome": "candidate"',
    '{"outcome":"abstain","candidate":null,"abstention_reason":null}',
    '{"outcome":"approved","candidate":null,"abstention_reason":"Done"}',
])
def test_prose_truncated_json_or_invalid_decision_cannot_be_accepted(text):
    with pytest.raises(ProposalRejected):
        validate_decision(text, snapshot())


def test_complete_candidate_preserves_all_authored_fields():
    result = validate_decision(encoded(), snapshot())
    assert result.candidate.model_dump() == candidate()


def test_complete_snapshot_is_immutable_and_target_scoped():
    source = snapshot()
    altered = json.loads(source.payload_json)
    altered["evidence"][0]["learner_id"] = "OTHER"
    with pytest.raises(ValueError):
        EvidenceSnapshot.from_mcp(altered, ("L001", "MATH-FRACTIONS"))
    assert source.records[0]["learner_id"] == "L001"


def test_missing_claim_and_question_repaired_by_model_not_code():
    sent, actions, events = [], [], []
    bad = candidate()
    del bad["claim"]
    del bad["suggested_teacher_question"]

    async def generate(messages, schema):
        sent.append(list(messages))
        return encoded(bad) if len(sent) == 1 else encoded()

    async def submit(arguments):
        actions.append(arguments)
        return {**arguments, "review_id": "review-test", "status": "pending_teacher_review"}

    result = asyncio.run(decide_and_submit(
        snapshot(), generate=generate, submit=submit, observe=events.append,
    ))
    assert result["status"] == "submitted"
    assert [a["status"] for a in result["attempts"]] == ["invalid", "valid"]
    assert actions == [candidate()]
    assert "candidate.claim: missing" in sent[1][-1]["content"]
    assert "candidate.suggested_teacher_question: missing" in sent[1][-1]["content"]
    assert sent[1][1]["content"] == sent[0][1]["content"]


def test_repeated_missing_fields_stay_failure_with_zero_submissions():
    actions = []
    bad = candidate()
    del bad["claim"]

    async def generate(*_args):
        return encoded(bad)

    async def submit(arguments):
        actions.append(arguments)
        raise AssertionError("Invalid proposal must not be submitted")

    result = asyncio.run(decide_and_submit(
        snapshot(), generate=generate, submit=submit, observe=lambda _event: None,
    ))
    assert result["status"] == "invalid_proposal"
    assert len(result["attempts"]) == 2
    assert not actions


def test_genuine_abstention_remains_permitted_even_for_multiple_terms():
    async def generate(*_args):
        return json.dumps({"outcome": "abstain", "candidate": None,
                           "abstention_reason": "Comparability of these tasks is unclear."})

    async def submit(_arguments):
        raise AssertionError("Abstention must never dispatch a candidate")

    result = asyncio.run(decide_and_submit(
        snapshot(), generate=generate, submit=submit, observe=lambda _event: None,
    ))
    assert result["status"] == "abstained"
    assert result["final_output"].startswith("ABSTAIN:")
    assert len(result["attempts"]) == 1


def test_ambiguous_submission_failure_is_not_blindly_retried():
    actions = []

    async def generate(*_args):
        return encoded()

    async def submit(arguments):
        actions.append(arguments)
        raise TimeoutError("MCP response uncertain")

    with pytest.raises(TimeoutError):
        asyncio.run(decide_and_submit(
            snapshot(), generate=generate, submit=submit, observe=lambda _event: None,
        ))
    assert len(actions) == 1


def test_native_gateway_sends_schema_and_exposes_no_action_tools():
    seen, events, records = [], [], []

    def transport(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": encoded()},
            "prompt_eval_count": 80, "eval_count": 40})

    async def exercise():
        gateway = OllamaJsonGenerator(
            model="qwen2.5:3b", base_url="http://localhost:11434/v1",
            deadline=asyncio.get_running_loop().time() + 5, request_limit=1,
            records=records, observe=events.append, transport=httpx.MockTransport(transport),
        )
        assert await gateway([], ReviewDecision.model_json_schema()) == encoded()
        with pytest.raises(RuntimeError):
            await gateway([], ReviewDecision.model_json_schema())

    asyncio.run(exercise())
    assert seen[0]["format"] == ReviewDecision.model_json_schema()
    assert "tools" not in seen[0]
    assert len(seen) == 1
    assert records[0]["status"] == "returned"
    assert [x["event"] for x in events] == ["request_started", "request_finished"]
    assert "claim" not in json.dumps(events)


@pytest.mark.parametrize("body", [
    {"done": False},
    {"done": True, "done_reason": "length", "message": {"content": encoded()}},
    {"done": True, "message": {"content": encoded(), "tool_calls": [{"x": 1}]}},
])
def test_gateway_refuses_incomplete_or_action_outputs(body):
    async def exercise():
        gateway = OllamaJsonGenerator(
            model="qwen2.5:3b", base_url="http://localhost:11434/v1",
            deadline=asyncio.get_running_loop().time() + 5, request_limit=2,
            records=[], observe=lambda _event: None,
            transport=httpx.MockTransport(lambda _req: httpx.Response(200, json=body)),
        )
        with pytest.raises(ValueError):
            await gateway([], ReviewDecision.model_json_schema())
    asyncio.run(exercise())
