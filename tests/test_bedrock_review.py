"""Offline Bedrock HTTP replay; no credentials, paid inference or educator verdict."""

import asyncio
import json
import re
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import httpx
import pytest
from fastmcp import Client

from mwalimulens import bedrock_review as bedrock
from mwalimulens.agent.orchestrator import EDUCATION_MCP_CLIENT_MODE
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, build_server
from mwalimulens.teacher_portal import TeacherPortal, make_handler, render_portal
from mwalimulens.teacher_review_demo import CANDIDATE


@pytest.fixture
def setup(tmp_path, monkeypatch):
    directory = tmp_path / "bedrock-test"
    server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=directory / "state.json")
    monkeypatch.setattr(
        bedrock,
        "build_agent_mcp_client",
        lambda **kw: Client(
            server,
            mode=EDUCATION_MCP_CLIENT_MODE,
        ),
    )
    return directory


def replay(directory, text, *, stop="end_turn", status=200):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={
                "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
                "stopReason": stop,
                "usage": {"inputTokens": 500, "outputTokens": 100},
            },
        )

    generator = bedrock.BedrockGenerator(
        directory,
        "eu-north-1",
        transport=httpx.MockTransport(handle),
        signer=lambda url, body: {"Content-Type": "application/json"},
    )
    return generator, calls


def decision():
    return json.dumps({"outcome": "candidate", "candidate": CANDIDATE, "abstention_reason": None})


def test_candidate_can_be_revised_and_reopened_without_inference(setup):
    generator, calls = replay(setup, decision())
    result = asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    assert result["outcome"]["status"] == "submitted"
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    assert payload["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0, "topP": 1}
    assert "toolConfig" not in payload
    assert "Decision JSON Schema:" in payload["messages"][0]["content"][0]["text"]
    assert (setup / "request.json").read_bytes() == calls[0].content
    case = bedrock.open_case(setup)
    assert len(case.state.pending_reviews()) == 1
    assert case.state.teacher_reviews() == case.state.profile_updates() == ()
    page = render_portal(case, "token")
    assert "Hosted Bedrock review" in page
    reason = "Retain uncertainty about independent explanation."
    wording = "Recorded scores rose; independent explanation needs further assessment."
    portal = TeacherPortal(setup.parent, case)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(portal))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False
        ) as browser:

            def post(path, fields):
                return browser.post(
                    path,
                    content=urlencode(fields),
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )

            preview = post(
                "/review/preview",
                {
                    "csrf": portal.token,
                    "decision": "edit",
                    "reason": reason,
                    "edited_claim": wording,
                },
            )
            assert preview.status_code == 200
            assert case.state.teacher_reviews() == case.state.profile_updates() == ()
            nonce = re.search(r'name="nonce" value="([^"]+)"', preview.text)[1]
            confirmed = post("/review/submit", {"csrf": portal.token, "nonce": nonce})
            assert confirmed.status_code == 200
            repeated = post("/review/submit", {"csrf": portal.token, "nonce": nonce})
            assert repeated.status_code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    reopened = bedrock.open_case(setup)
    assert reopened.run_dir == case.run_dir
    assert reopened.candidate["review_id"] == case.candidate["review_id"]
    assert reopened.state.teacher_reviews()[0]["reason"] == reason
    assert reopened.state.teacher_reviews()[0]["final_claim"] == wording
    assert len(reopened.state.profile_updates()) == 1
    assert len(calls) == 1
    page = render_portal(reopened, "token")
    assert reason in page and wording in page
    with pytest.raises(ValueError, match="already resolved"):
        reopened.service.record_teacher_review(
            review_id=case.candidate["review_id"],
            reviewer_id="simulated-teacher-not-authenticated",
            decision="edit",
            reason=reason,
            edited_claim=wording,
        )


@pytest.mark.parametrize("kind", ["missing-id", "fenced", "abstain", "truncated", "denied"])
def test_non_candidates_keep_raw_response_and_never_create_profile(setup, kind):
    text, stop, status = decision(), "end_turn", 200
    if kind == "missing-id":
        item = json.loads(text)
        del item["candidate"]["learner_id"]
        text = json.dumps(item)
    elif kind == "fenced":
        text = "```json\n" + text + "\n```"
    elif kind == "abstain":
        text = json.dumps(
            {
                "outcome": "abstain",
                "candidate": None,
                "abstention_reason": "Task comparability remains uncertain.",
            }
        )
    elif kind == "truncated":
        stop = "max_tokens"
    else:
        status = 403
    generator, calls = replay(setup, text, stop=stop, status=status)
    result = asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    assert len(calls) == 1
    case = bedrock.open_case(setup)
    assert case.candidate is None
    assert case.state.review_candidates() == ()
    assert case.state.profile_updates() == case.state.teacher_reviews() == ()
    assert (
        json.loads((setup / "response.txt").read_bytes())["output"]["message"]["content"][0]["text"]
        == text
    )
    assert result["outcome"]["status"] != "submitted"
    assert 'action="/review/preview"' not in render_portal(case, "token")
    with pytest.raises(RuntimeError, match="One Bedrock request"):
        asyncio.run(generator([], {}))


def test_tampering_and_existing_case_refused(setup):
    generator, _ = replay(setup, decision())
    asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    with pytest.raises(FileExistsError):
        asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    (setup / "response.txt").write_text("altered")
    with pytest.raises(ValueError, match="changed"):
        bedrock.open_case(setup)


def test_run_requires_explicit_credit_and_region_confirmation():
    with pytest.raises(SystemExit) as exc:
        bedrock.main(["--run", "--region", "eu-north-1"])
    assert exc.value.code == 2


def test_region_validated_without_credentials():
    with pytest.raises(ValueError):
        bedrock.BedrockGenerator(Path(), "https://attacker.invalid")


def test_timeout_preserves_unknown_remote_outcome_without_retry(setup):
    calls = []

    def disconnect(request):
        calls.append(request)
        raise httpx.ReadTimeout("provider response not received")

    generator = bedrock.BedrockGenerator(
        setup,
        "eu-north-1",
        transport=httpx.MockTransport(disconnect),
        signer=lambda url, body: {"Content-Type": "application/json"},
    )
    result = asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    assert len(calls) == 1
    assert result["error_type"] == "ReadTimeout"
    metrics = json.loads((setup / "provider-metrics.json").read_text())
    assert metrics["request_delivery"] == {"status": "unknown", "http_attempts": 1}
    case = bedrock.open_case(setup)
    assert case.candidate is None
    assert case.state.review_candidates() == case.state.profile_updates() == ()


def test_signing_failure_records_zero_http_attempts(setup):
    calls = []

    def no_credentials(url, body):
        raise ValueError("No external credentials")

    generator = bedrock.BedrockGenerator(
        setup,
        "eu-north-1",
        signer=no_credentials,
        transport=httpx.MockTransport(lambda request: calls.append(request)),
    )
    result = asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    assert calls == []
    assert result["request_delivery"] == {"status": "not_started", "http_attempts": 0}
    assert result["outcome"]["status"] == "error"
    page = render_portal(bedrock.open_case(setup), "token")
    assert "HTTP attempts: 0" in page
    assert "One request;" not in page
    assert "one bounded request" not in page


def test_deadline_covers_mcp_startup_without_model_request(setup, monkeypatch):
    class SlowClient:
        async def __aenter__(self):
            await asyncio.sleep(5)

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(bedrock, "build_agent_mcp_client", lambda **kw: SlowClient())
    result = asyncio.run(bedrock.run_case(setup, "eu-north-1", deadline_seconds=0.01))
    assert result["termination"]["reason"] == "deadline_exceeded"
    assert result["outcome"]["status"] == "error"
    assert result["request_delivery"]["http_attempts"] == 0
    case = bedrock.open_case(setup)
    assert case.state.profile_updates() == case.state.pending_reviews() == ()
    assert case.candidate is None


def test_cancelled_generation_is_saved_and_propagated(setup):
    async def cancel(messages, schema):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=cancel))
    result = json.loads((setup / "result.json").read_text())
    assert result["termination"]["reason"] == "cancelled"
    assert result["error_type"] is not None
    assert result["outcome"]["status"] == "error"
    assert bedrock.open_case(setup).candidate is None


def test_teardown_error_does_not_report_success(setup, monkeypatch):
    real_client_factory = bedrock.build_agent_mcp_client

    class FailingExit:
        async def __aenter__(self):
            self.client = real_client_factory()
            return await self.client.__aenter__()

        async def __aexit__(self, *args):
            await self.client.__aexit__(*args)
            raise RuntimeError("Cleanup failed")

    monkeypatch.setattr(bedrock, "build_agent_mcp_client", lambda **kw: FailingExit())
    generator, calls = replay(setup, decision())
    result = asyncio.run(bedrock.run_case(setup, "eu-north-1", generator=generator))
    assert len(calls) == 1
    assert result["outcome"]["status"] == "error"
    assert result["termination"]["outcome_before_interruption"]["status"] == "submitted"
    with pytest.raises(ValueError, match="Non-candidate outcome contains candidate actions"):
        bedrock.open_case(setup)


def test_cli_refuses_unverifiable_case_without_opening_workspace(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        bedrock.main(["--open", str(tmp_path / "missing")])
    assert exc.value.code == 2
    assert "no workspace was opened" in capsys.readouterr().err
