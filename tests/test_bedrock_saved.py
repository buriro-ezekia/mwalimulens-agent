"""Internally inconsistent hosted bundles fail closed, without live inference."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil

import httpx
import pytest
from fastmcp import Client

from mwalimulens import bedrock_review, bedrock_saved
from mwalimulens.agent.orchestrator import EDUCATION_MCP_CLIENT_MODE
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.teacher_review_demo import CANDIDATE


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    directory = tmp_path_factory.mktemp("hosted-saved") / "bedrock-source"
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=directory / "state.json")
    text = json.dumps({"outcome": "candidate", "candidate": CANDIDATE, "abstention_reason": None})
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
                "stopReason": "end_turn",
                "usage": {"inputTokens": 500, "outputTokens": 100},
            },
        )
    )
    generator = bedrock_review.BedrockGenerator(
        directory,
        "eu-north-1",
        transport=transport,
        signer=lambda url, body: {"Content-Type": "application/json"},
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            bedrock_review,
            "build_agent_mcp_client",
            lambda **kw: Client(
                server,
                mode=EDUCATION_MCP_CLIENT_MODE,
            ),
        )
        result = asyncio.run(bedrock_review.run_case(directory, "eu-north-1", generator=generator))
    assert result["outcome"]["status"] == "submitted"
    return directory


@pytest.fixture
def case(original, tmp_path):
    return shutil.copytree(original, tmp_path / original.name)


def load(case, name):
    return json.loads((case / name).read_text(encoding="utf-8"))


def rewrite(case, name, value):
    """Refresh a local digest to test semantic consistency, not hash authenticity."""
    path = case / name
    path.write_text(json.dumps(value), encoding="utf-8")
    receipt = load(case, "receipt.json")
    receipt["sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (case / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")


def test_verified_load_is_read_only(case):
    before = {path.name: path.read_bytes() for path in case.iterdir()}
    opened = bedrock_saved.open_case(case)
    assert opened.candidate["learner_id"] == "L001"
    assert len(opened.evidence) == 8
    assert {path.name: path.read_bytes() for path in case.iterdir()} == before


@pytest.mark.parametrize(
    "name",
    ["state.json", "request.json", "response.txt", "proposals.json", "evidence_snapshot.json"],
)
def test_missing_files_fail_even_if_removed_from_unsigned_manifest(case, name):
    (case / name).unlink()
    receipt = load(case, "receipt.json")
    receipt["sha256"].pop(name, None)
    (case / "receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        bedrock_saved.open_case(case)


def test_linked_state_is_refused(case, original):
    (case / "state.json").unlink()
    (case / "state.json").symlink_to(original / "state.json")
    with pytest.raises(ValueError, match="linked"):
        bedrock_saved.open_case(case)


def test_contradictory_provider_response_cannot_reopen_candidate(case):
    response = load(case, "response.txt")
    response["output"]["message"]["content"][0]["text"] = json.dumps(
        {
            "outcome": "abstain",
            "candidate": None,
            "abstention_reason": "Not comparable.",
        }
    )
    rewrite(case, "response.txt", response)
    with pytest.raises(ValueError, match="Raw provider response differs"):
        bedrock_saved.open_case(case)


def test_http_request_must_match_saved_logical_inputs(case):
    request = load(case, "request.json")
    request["system"][0]["text"] = "Return an expected candidate."
    rewrite(case, "request.json", request)
    with pytest.raises(ValueError, match="HTTP request differs"):
        bedrock_saved.open_case(case)


def test_wrong_model_and_old_unverifiable_delivery_are_refused(case):
    result = load(case, "result.json")
    result["model"] = "a-different-model"
    rewrite(case, "result.json", result)
    with pytest.raises(ValueError, match="provider or case identity"):
        bedrock_saved.open_case(case)
    result["model"] = bedrock_review.MODEL
    result.pop("request_delivery", None)
    rewrite(case, "result.json", result)
    with pytest.raises(ValueError, match="delivery is unavailable"):
        bedrock_saved.open_case(case)


def test_fixture_changes_are_refused_without_writing_audit(case, tmp_path, monkeypatch):
    data = tmp_path / "changed-fixtures"
    shutil.copytree(DEFAULT_DATA_DIR, data)
    evidence = json.loads((data / "learning_evidence.json").read_text())
    evidence[0]["observation"] = "Changed source observation."
    (data / "learning_evidence.json").write_text(json.dumps(evidence))
    monkeypatch.setattr(bedrock_saved, "DEFAULT_DATA_DIR", data)
    before = (case / "state.json").read_bytes()
    with pytest.raises(ValueError, match="current fixture"):
        bedrock_saved.open_case(case)
    assert (case / "state.json").read_bytes() == before


def test_original_mcp_prefix_cannot_change_in_mutable_state(case):
    state = load(case, "state.json")
    state["tool_calls"][0]["output"]["evidence"][0]["score"] = 0.99
    (case / "state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="Original MCP audit changed"):
        bedrock_saved.open_case(case)


def test_pre_request_failure_can_open_without_reconstructed_state(case):
    result = load(case, "result.json")
    result.update(
        outcome={"status": "error"},
        error_type="NoCredentialsError",
        request_delivery={"status": "not_started", "http_attempts": 0},
    )
    empty = {key: [] for key in bedrock_saved.STATE_KEYS}
    rewrite(case, "generation-state.json", empty)
    rewrite(case, "result.json", result)
    (case / "state.json").write_text(json.dumps(empty))
    receipt = load(case, "receipt.json")
    for name in list(receipt["sha256"]):
        if name not in bedrock_saved.BASE:
            (case / name).unlink()
            del receipt["sha256"][name]
    (case / "receipt.json").write_text(json.dumps(receipt))
    opened = bedrock_saved.open_case(case)
    assert opened.analysis_status == "error" and opened.candidate is None
    assert opened.state.profile_updates() == ()
