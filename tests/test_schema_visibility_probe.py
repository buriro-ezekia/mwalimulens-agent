"""Mocked transport proves diagnostic isolation, not improved live-model judgement."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import replace

import httpx
import pytest

from mwalimulens import schema_visibility_probe as probe
from mwalimulens.agent import candidate_contract
from mwalimulens.agent.candidate_contract import (
    DECISION_POLICY_ID,
    EvidenceSnapshot,
    ReviewDecision,
    review_messages,
)
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.structured_ollama import OllamaJsonGenerator
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService, _evidence_payload
from mwalimulens.mcp_server.state import JsonStateStore


def abstention():
    return {"outcome": "abstain", "candidate": None, "abstention_reason": (
        "Comparability prevents a defensible statement about consistent improvement "
        "or independent mastery."
    )}


def candidate():
    return {"outcome": "candidate", "abstention_reason": None, "candidate": {
        "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
        "claim": "Recorded performance changed while independent explanation remains mixed.",
        "supporting_evidence_ids": ["EV-001", "EV-004"],
        "counter_evidence_ids": ["EV-008"],
        "uncertainty": "The observations do not establish independent explanation.",
        "suggested_teacher_question": "Can the learner explain a new task unaided?",
    }}


@pytest.fixture
def saved_snapshot(tmp_path):
    target = ("L001", "MATH-FRACTIONS")
    rows = load_synthetic_dataset(DEFAULT_DATA_DIR).competency_evidence(*target)
    snapshot = EvidenceSnapshot.from_mcp({
        "learner_id": target[0], "competency_code": target[1],
        "evidence_count": len(rows), "evidence": [_evidence_payload(row) for row in rows],
    }, target)
    path = tmp_path / "historical" / "saved.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "sha256": snapshot.sha256, "payload": json.loads(snapshot.payload_json),
    }), encoding="utf-8")
    return path, snapshot


def transport_returning(output, seen):
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "qwen2.5:3b", "done": True, "done_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(output)},
            "prompt_eval_count": 50, "eval_count": 30,
        })
    return httpx.MockTransport(handler)


def test_saved_hash_is_verified_and_tampering_rejected(saved_snapshot):
    path, snapshot = saved_snapshot
    assert probe.load_saved_snapshot(path, ("L001", "MATH-FRACTIONS")) == snapshot
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["payload"]["evidence"][0]["observation"] = "Changed source observation."
    path.write_text(json.dumps(saved), encoding="utf-8")
    with pytest.raises(ValueError, match="(?i)hash|sha256"):
        probe.load_saved_snapshot(path, ("L001", "MATH-FRACTIONS"))


def test_b_adds_only_exact_format_schema_text_to_unchanged_policy(saved_snapshot):
    _, snapshot = saved_snapshot
    conditions = probe.build_conditions(snapshot)
    original = review_messages(snapshot)
    schema = ReviewDecision.model_json_schema()
    a, b = conditions["A"], conditions["B"]
    assert a == {"messages": original, "format": schema}
    suffix = probe.SCHEMA_TEXT_PREFIX + json.dumps(
        schema, sort_keys=True, ensure_ascii=False, allow_nan=False,
    )
    assert b == {"messages": [
        {"role": "system", "content": original[0]["content"] + suffix}, original[1],
    ], "format": schema}
    assert json.loads(b["messages"][0]["content"].split(probe.SCHEMA_TEXT_PREFIX)[1]) == schema
    assert review_messages(snapshot) == original
    assert DECISION_POLICY_ID == "provisional_review_v2"


def test_all_controls_have_identical_evidence_and_policy_across_conditions(saved_snapshot):
    path, snapshot = saved_snapshot
    cases = probe.case_snapshots(path)
    assert [case.ident for case in cases] == [item.ident for item in probe.SCENARIOS]
    assert cases[0].snapshot == snapshot
    assert len(cases) == 4
    assert len(cases[2].snapshot.records) == 1
    assert cases[3].snapshot.records == []
    for case in cases:
        a, b = (probe.build_conditions(case.snapshot)[key] for key in ("A", "B"))
        assert a["messages"][0] == review_messages(snapshot)[0]
        assert a["messages"][1] == b["messages"][1] == {
            "role": "user", "content": case.snapshot.payload_json,
        }
        assert a["format"] == b["format"] == ReviewDecision.model_json_schema()


def test_expected_outcomes_and_categories_cannot_enter_model_input(saved_snapshot, monkeypatch):
    path, _ = saved_snapshot
    before = [probe.build_conditions(case.snapshot) for case in probe.case_snapshots(path)]
    monkeypatch.setattr(probe, "SCENARIOS", tuple(
        replace(case, expected="HIDDEN_EXPECTED_LABEL", category="HIDDEN_CATEGORY_LABEL")
        for case in probe.SCENARIOS
    ))
    after = [probe.build_conditions(case.snapshot) for case in probe.case_snapshots(path)]
    assert after == before
    assert "HIDDEN_" not in json.dumps(after)
    for conditions in after:
        messages = json.dumps(conditions["A"]["messages"])
        assert candidate()["candidate"]["claim"] not in messages
        assert candidate()["candidate"]["suggested_teacher_question"] not in messages


@pytest.mark.parametrize("case_index", range(4))
def test_http_requests_differ_only_in_schema_visibility_and_match_production(
    saved_snapshot, case_index,
):
    path, _ = saved_snapshot
    case = probe.case_snapshots(path)[case_index]
    settings = OllamaSettings(keep_alive="10m")
    seen = []

    async def exercise():
        results = [await probe.run_condition(
            case, condition, settings=settings, transport=transport_returning(abstention(), seen),
        ) for condition in ("A", "B")]
        gateway = OllamaJsonGenerator(
            model=settings.model_name, base_url=settings.base_url,
            deadline=asyncio.get_running_loop().time() + 10, request_limit=1,
            records=[], observe=lambda _event: None, keep_alive=settings.keep_alive,
            transport=transport_returning(abstention(), seen),
        )
        await gateway(review_messages(case.snapshot), ReviewDecision.model_json_schema())
        return results

    results = asyncio.run(exercise())
    assert len(seen) == 3
    assert seen[0] == seen[2]
    assert seen[0]["format"] == seen[1]["format"]
    without_suffix = json.loads(json.dumps(seen[1]))
    without_suffix["messages"][0]["content"] = without_suffix["messages"][0]["content"].split(
        probe.SCHEMA_TEXT_PREFIX,
    )[0]
    assert without_suffix == seen[0]
    assert "tools" not in seen[0] and "tools" not in seen[1]
    for index, result in enumerate(results):
        assert result["status"] == "valid"
        assert result["decision"] == abstention()
        assert result["validation_issues"] == []
        assert result["actual_request"] == seen[index]
        assert len(result["model_requests"]) == 1


@pytest.mark.parametrize("condition", ["A", "B"])
@pytest.mark.parametrize("invalid", [False, True])
def test_candidates_are_retained_offline_without_submission_or_retries(
    saved_snapshot, monkeypatch, condition, invalid,
):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Decision-only diagnostic must never enter an application action")

    monkeypatch.setattr(candidate_contract, "decide_and_submit", forbidden)
    monkeypatch.setattr(EducationToolService, "flag_pattern_for_review", forbidden)
    monkeypatch.setattr(EducationToolService, "record_teacher_review", forbidden)
    monkeypatch.setattr(JsonStateStore, "record_pending_review_and_tool_call", forbidden)
    monkeypatch.setattr(JsonStateStore, "record_teacher_review_action", forbidden)
    assert "submit" not in inspect.signature(probe.run_condition).parameters
    path, _ = saved_snapshot
    output = candidate()
    if invalid:
        output["candidate"]["supporting_evidence_ids"][0] = "UNKNOWN-EVIDENCE"
    seen = []
    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], condition, settings=OllamaSettings(),
        transport=transport_returning(output, seen),
    ))
    assert len(seen) == 1
    assert result["raw_output"] == json.dumps(output)
    assert result["parsed_output"] == output
    assert result["status"] == ("invalid" if invalid else "valid")
    assert result["decision"] == (None if invalid else output)
    assert bool(result["validation_issues"]) is invalid
    if invalid:
        assert "unknown_or_out_of_scope_evidence_ids" in result["validation_issues"]


@pytest.mark.parametrize("body", [
    {"done": True, "done_reason": "length", "message": {"content": json.dumps(candidate())}},
    {"done": True, "message": {"content": json.dumps(candidate()), "tool_calls": [{"x": 1}]}},
])
def test_native_runtime_rejections_preserve_output_without_retry(saved_snapshot, body):
    path, _ = saved_snapshot
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=body)

    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], "B", settings=OllamaSettings(),
        transport=httpx.MockTransport(respond),
    ))
    assert len(seen) == 1
    assert result["status"] == "runtime_error"
    assert result["raw_output"] == body["message"]["content"]
    assert result["parsed_output"] == candidate()
    assert result["decision"] is None
    assert result["provider_response"] == {"http_status": 200, "body": body}


def test_preparation_is_offline_and_preserves_source_evidence(
    saved_snapshot, tmp_path, monkeypatch,
):
    path, _ = saved_snapshot
    source_before = {
        item: item.read_bytes() for item in DEFAULT_DATA_DIR.rglob("*") if item.is_file()
    }
    saved_before = path.read_bytes()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Preparation must not run a model")

    monkeypatch.setattr(probe, "OllamaJsonGenerator", forbidden)
    output_dir, plan, cases = probe.prepare_comparison(
        path, output_root=tmp_path / "new-output", settings=OllamaSettings(),
    )
    assert plan["decision_policy_id"] == DECISION_POLICY_ID
    assert plan["decision_only"] is True
    assert [entry["order"] for entry in plan["cases"]] == [
        ["A", "B"], ["B", "A"], ["A", "B"], ["B", "A"],
    ]
    assert json.loads((output_dir / "plan.json").read_text(encoding="utf-8")) == plan
    for case in cases:
        saved = json.loads((output_dir / case.ident / "evidence_snapshot.json").read_text(
            encoding="utf-8",
        ))
        assert saved["sha256"] == case.snapshot.sha256
        for condition, request in probe.build_conditions(case.snapshot).items():
            assert json.loads((output_dir / case.ident / f"{condition}.request.json").read_text(
                encoding="utf-8",
            )) == request
    assert path.read_bytes() == saved_before
    assert {item: item.read_bytes() for item in source_before} == source_before


def test_comparison_records_eight_offline_decisions_without_grading(
    saved_snapshot, tmp_path, monkeypatch,
):
    path, _ = saved_snapshot
    settings = OllamaSettings()
    folder, plan, cases = probe.prepare_comparison(
        path, output_root=tmp_path / "out", settings=settings,
    )
    identity = {"requested_name": settings.model_name, "digest": "test-digest", "verified": True}
    identity_calls, seen = [], []
    original = probe.run_condition

    async def identify(_settings):
        identity_calls.append(True)
        return identity

    async def decide(case, condition, *, settings):
        return await original(case, condition, settings=settings,
                              transport=transport_returning(abstention(), seen))

    monkeypatch.setattr(probe, "_model_identity", identify)
    monkeypatch.setattr(probe, "run_condition", decide)
    summary = asyncio.run(probe.run_comparison(folder, plan, cases, settings))
    assert summary["status"] == "completed"
    assert len(seen) == len(summary["results"]) == 8
    assert len(identity_calls) == 2
    assert summary["model_identity_stable"] is True
    assert summary["limits"]["retries"] == 0
    assert summary["limits"]["request_deadline_seconds"] == 180
    assert [item["condition"] for item in summary["results"]] == list("ABBAABBA")
    for item in summary["results"]:
        assert item["commit"] == plan["commit"]
        assert item["model_identity"] == identity
        assert item["schema_sha256"] == plan["schema_sha256"]
        assert item["decision_policy_id"] == plan["decision_policy_id"]
        assert item["decision_only"] and not item["application_workflow_test"]
        assert not item["submission_enabled"]
        assert "grade" not in item and "expected_outcome" not in item
        assert item["actual_request"]["options"] == plan["request_settings"]["options"]
    saved = (folder / "comparison.json").read_bytes()
    with pytest.raises(FileExistsError):
        asyncio.run(probe.run_comparison(folder, plan, cases, settings))
    assert (folder / "comparison.json").read_bytes() == saved
    assert len(seen) == 8


@pytest.mark.parametrize("tamper", ["request", "order"])
def test_prepared_input_drift_or_extra_requests_stop_before_network(
    saved_snapshot, tmp_path, monkeypatch, tamper,
):
    path, _ = saved_snapshot
    settings = OllamaSettings()
    folder, plan, cases = probe.prepare_comparison(
        path, output_root=tmp_path / "out", settings=settings,
    )
    if tamper == "request":
        request = folder / cases[0].ident / "B.request.json"
        payload = json.loads(request.read_text(encoding="utf-8"))
        payload["messages"][0]["content"] += "changed"
        request.write_text(json.dumps(payload), encoding="utf-8")
    else:
        plan["cases"][0]["order"].append("A")

    async def forbidden(_settings):
        pytest.fail("Invalid preparation must stop before any network call")

    monkeypatch.setattr(probe, "_model_identity", forbidden)
    result = asyncio.run(probe.run_comparison(folder, plan, cases, settings))
    assert result["status"] == "runtime_error"
    assert result["error"]["type"] == "ValueError"
    assert result["results"] == []


def test_cancellation_is_persisted_and_stops_remaining_requests(
    saved_snapshot, tmp_path, monkeypatch,
):
    path, _ = saved_snapshot
    settings = OllamaSettings()
    folder, plan, cases = probe.prepare_comparison(
        path, output_root=tmp_path / "out", settings=settings,
    )
    seen = []
    original = probe.run_condition

    async def identify(_settings):
        return {"digest": "test-digest"}

    def cancel(request):
        seen.append(request)
        raise asyncio.CancelledError()

    async def decide(case, condition, *, settings):
        return await original(case, condition, settings=settings,
                              transport=httpx.MockTransport(cancel))

    monkeypatch.setattr(probe, "_model_identity", identify)
    monkeypatch.setattr(probe, "run_condition", decide)
    result = asyncio.run(probe.run_comparison(folder, plan, cases, settings))
    assert result["status"] == "interrupted"
    assert len(seen) == len(result["results"]) == 1
    assert len(result["not_run"]) == 7
    assert all(item["status"] == "not_run" for item in result["not_run"])
    assert json.loads((folder / "comparison.json").read_text(encoding="utf-8")) == result


def test_saved_target_is_preserved_when_scenario_order_changes(saved_snapshot, monkeypatch):
    path, snapshot = saved_snapshot
    monkeypatch.setattr(probe, "SCENARIOS", tuple(reversed(probe.SCENARIOS)))
    saved_case = next(case for case in probe.case_snapshots(path) if case.source["kind"] ==
                      "saved_snapshot")
    assert saved_case.snapshot == snapshot


def test_preparation_rejects_historical_output_root(saved_snapshot):
    path, _ = saved_snapshot
    before = path.read_bytes()
    with pytest.raises(ValueError, match="separate"):
        probe.prepare_comparison(path, output_root=path.parent, settings=OllamaSettings())
    assert path.read_bytes() == before


class CleanupTransport(httpx.MockTransport):
    def __init__(self, handler, cleanup_error=None):
        super().__init__(handler)
        self.cleanup_error = cleanup_error
        self.close_count = 0

    async def aclose(self):
        self.close_count += 1
        if self.cleanup_error is not None:
            raise self.cleanup_error
        await super().aclose()


@pytest.mark.parametrize("cleanup_error", [
    None, RuntimeError("cleanup failed"), TimeoutError("cleanup deadline"),
])
def test_completed_response_survives_cleanup_and_transport_is_closed_once(
    saved_snapshot, cleanup_error,
):
    path, _ = saved_snapshot
    seen = []
    transport = CleanupTransport(transport_returning(abstention(), seen).handler, cleanup_error)
    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], "A", settings=OllamaSettings(), transport=transport,
    ))
    assert transport.close_count == 1
    assert result["status"] == "valid"
    assert result["error"] is None
    assert result["decision"] == result["parsed_output"] == abstention()
    assert result["raw_output"] == json.dumps(abstention())
    assert result["actual_request"] == seen[0]
    assert result["provider_response"]["body"]["message"]["content"] == result["raw_output"]
    assert result["model_requests"][0]["status"] == "returned"
    assert result["model_requests"][0]["input_tokens"] == 50
    assert result["model_requests"][0]["output_tokens"] == 30
    assert "seconds" in result["model_requests"][0]
    if cleanup_error:
        assert result["cleanup_errors"] == [{
            "resource": "transport", "type": type(cleanup_error).__name__,
            "message": str(cleanup_error),
        }]
        assert result["stop_reason"] == (
            "timed_out" if isinstance(cleanup_error, TimeoutError) else "cleanup_error"
        )
    else:
        assert result["cleanup_errors"] == []
        assert result["stop_reason"] is None


@pytest.mark.parametrize("request_error,status", [
    (TimeoutError("deadline"), "timed_out"),
    (httpx.ReadTimeout("read timeout"), "timed_out"),
    (asyncio.CancelledError(), "interrupted"),
])
@pytest.mark.parametrize("cleanup_error", [
    RuntimeError("cleanup failed"), TimeoutError("cleanup deadline"), asyncio.CancelledError(),
])
def test_cleanup_cannot_replace_request_timeout_or_cancellation(
    saved_snapshot, request_error, status, cleanup_error,
):
    path, _ = saved_snapshot

    def fail(_request):
        raise request_error

    transport = CleanupTransport(fail, cleanup_error)
    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], "B", settings=OllamaSettings(), transport=transport,
    ))
    assert transport.close_count == 1
    assert result["status"] == status
    assert result["stop_reason"] == status
    assert result["error"]["type"] == type(request_error).__name__
    assert result["cleanup_errors"][0]["type"] == type(cleanup_error).__name__
    assert result["actual_request"] is not None
    assert result["provider_response"] is None
    assert result["raw_output"] is result["parsed_output"] is result["decision"] is None
    assert len(result["model_requests"]) == 1


@pytest.mark.parametrize("failure", ["timeout", "httpx_timeout", "cleanup_cancel", "cleanup_error"])
def test_comparison_stops_and_records_not_run_after_timeout_or_cleanup_failure(
    saved_snapshot, tmp_path, monkeypatch, failure,
):
    path, _ = saved_snapshot
    settings = OllamaSettings()
    folder, plan, cases = probe.prepare_comparison(
        path, output_root=tmp_path / "out", settings=settings,
    )
    seen, identity_calls = [], []
    original = probe.run_condition

    async def identify(_settings):
        identity_calls.append(True)
        return {"digest": "test-digest"}

    def respond(request):
        # Preserve one earlier completed decision, then interrupt the comparison.
        if len(seen) == 1 and failure in {"timeout", "httpx_timeout"}:
            seen.append(json.loads(request.content))
            error = TimeoutError if failure == "timeout" else httpx.ReadTimeout
            raise error("request timed out")
        return transport_returning(abstention(), seen).handler(request)

    async def decide(case, condition, *, settings):
        cleanup_error = None
        if len(seen) == 1:
            if failure == "cleanup_cancel":
                cleanup_error = asyncio.CancelledError()
            elif failure == "cleanup_error":
                cleanup_error = RuntimeError("cleanup failed")
        return await original(case, condition, settings=settings,
                              transport=CleanupTransport(respond, cleanup_error))

    monkeypatch.setattr(probe, "_model_identity", identify)
    monkeypatch.setattr(probe, "run_condition", decide)
    result = asyncio.run(probe.run_comparison(folder, plan, cases, settings))
    expected = {"timeout": "timed_out", "httpx_timeout": "timed_out",
                "cleanup_cancel": "interrupted", "cleanup_error": "cleanup_error"}[failure]
    assert result["status"] == expected
    assert len(seen) == len(result["results"]) == 2
    assert len(identity_calls) == 1  # No post-interruption provider call.
    assert result["results"][0]["status"] == "valid"
    assert result["results"][1]["status"] == (
        "valid" if failure.startswith("cleanup") else "timed_out"
    )
    expected_remaining = [
        (case.ident, condition) for case, entry in zip(cases, plan["cases"], strict=True)
        for condition in entry["order"]
    ][2:]
    assert [(item["scenario"], item["condition"]) for item in result["not_run"]] == (
        expected_remaining
    )
    assert all(item["status"] == "not_run" for item in result["not_run"])
    for item in result["results"]:
        saved = folder / item["scenario"] / f"{item['condition']}.decision.json"
        assert json.loads(saved.read_text(encoding="utf-8")) == item
    assert json.loads((folder / "comparison.json").read_text(encoding="utf-8")) == result


def test_comparison_continues_after_completed_invalid_response(
    saved_snapshot, tmp_path, monkeypatch,
):
    path, _ = saved_snapshot
    settings = OllamaSettings()
    folder, plan, cases = probe.prepare_comparison(
        path, output_root=tmp_path / "out", settings=settings,
    )
    seen = []
    original = probe.run_condition

    async def identify(_settings):
        return {"digest": "test-digest"}

    async def decide(case, condition, *, settings):
        output = {"unexpected": "completed but schema-invalid"} if not seen else abstention()
        return await original(case, condition, settings=settings,
                              transport=transport_returning(output, seen))

    monkeypatch.setattr(probe, "_model_identity", identify)
    monkeypatch.setattr(probe, "run_condition", decide)
    result = asyncio.run(probe.run_comparison(folder, plan, cases, settings))
    assert result["status"] == "completed"
    assert len(seen) == len(result["results"]) == 8
    assert result["results"][0]["status"] == "invalid"
    assert result["results"][0]["validation_issues"]
    assert all(item["status"] == "valid" for item in result["results"][1:])
    assert result["not_run"] == []


def test_transport_is_closed_when_generator_construction_fails(saved_snapshot):
    path, _ = saved_snapshot
    seen = []
    transport = CleanupTransport(transport_returning(abstention(), seen).handler)
    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], "A", transport=transport,
        settings=OllamaSettings(base_url="http://not-loopback.invalid/v1"),
    ))
    assert seen == []
    assert transport.close_count == 1
    assert result["status"] == "runtime_error"
    assert result["error"]["type"] == "ValueError"
    assert result["model_requests"] == []
    assert result["cleanup_errors"] == []


@pytest.mark.parametrize("body,status", [
    ({"done": True, "message": {"content": '{"unexpected": "invalid decision"}'}}, "invalid"),
    ({"done": True, "done_reason": "length", "message": {
        "content": json.dumps(abstention()),
    }}, "runtime_error"),
])
def test_cleanup_failure_preserves_rejected_response_and_original_outcome(
    saved_snapshot, body, status,
):
    path, _ = saved_snapshot
    transport = CleanupTransport(
        lambda _request: httpx.Response(200, json=body), RuntimeError("cleanup failed"),
    )
    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], "A", settings=OllamaSettings(), transport=transport,
    ))
    assert transport.close_count == 1
    assert result["status"] == status
    assert result["raw_output"] == body["message"]["content"]
    assert result["parsed_output"] == json.loads(body["message"]["content"])
    assert result["provider_response"] == {"http_status": 200, "body": body}
    assert result["decision"] is None
    if status == "invalid":
        assert result["validation_issues"]
        assert result["error"] is None
    else:
        assert result["error"]["type"] == "ValueError"
    assert result["cleanup_errors"][0]["type"] == "RuntimeError"


def test_response_stream_cleanup_cannot_discard_completed_body(saved_snapshot):
    path, _ = saved_snapshot
    body = {"done": True, "message": {"content": json.dumps(abstention())},
            "prompt_eval_count": 50, "eval_count": 30}

    class Stream(httpx.AsyncByteStream):
        close_count = 0

        async def __aiter__(self):
            yield json.dumps(body).encode()

        async def aclose(self):
            self.close_count += 1
            raise RuntimeError("stream cleanup failed")

    stream = Stream()
    transport = CleanupTransport(
        lambda _request: httpx.Response(200, stream=stream),
        RuntimeError("transport cleanup failed"),
    )
    result = asyncio.run(probe.run_condition(
        probe.case_snapshots(path)[0], "A", settings=OllamaSettings(), transport=transport,
    ))
    assert stream.close_count == transport.close_count == 1
    assert result["status"] == "valid"
    assert result["error"] is None
    assert result["decision"] == result["parsed_output"] == abstention()
    assert result["raw_output"] == body["message"]["content"]
    assert result["provider_response"] == {"http_status": 200, "body": body}
    assert result["model_requests"][0]["status"] == "returned"
    assert result["model_requests"][0]["input_tokens"] == 50
    assert result["model_requests"][0]["output_tokens"] == 30
    assert [item["message"] for item in result["cleanup_errors"]] == [
        "stream cleanup failed", "transport cleanup failed",
    ]
    assert [item["resource"] for item in result["cleanup_errors"]] == [
        "response_stream", "transport",
    ]
    assert result["stop_reason"] == "cleanup_error"
