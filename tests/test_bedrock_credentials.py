"""Signing and login-provider support without reading credentials or contacting AWS."""

import json

import httpx
import pytest

from mwalimulens import bedrock_review as bedrock
from mwalimulens.agent.candidate_contract import decision_schema


def test_console_login_provider_and_crt_are_installed(tmp_path, monkeypatch):
    session = pytest.importorskip("botocore.session")
    pytest.importorskip("awscrt")
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "no-config"))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "no-credentials"))
    providers = session.Session().get_component("credential_provider").providers
    assert any(provider.METHOD == "login" for provider in providers)


def test_real_signing_with_dummy_session_credentials_does_not_persist_secrets(
    tmp_path,
    monkeypatch,
):
    import asyncio

    session = pytest.importorskip("botocore.session")
    credentials = pytest.importorskip("botocore.credentials")
    monkeypatch.setattr(
        session.Session,
        "get_credentials",
        lambda self: credentials.Credentials(
            "DUMMY_ACCESS_KEY",
            "DUMMY_SECRET_KEY",
            "DUMMY_SESSION_TOKEN",
        ),
    )
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "stopReason": "end_turn",
                "output": {
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "text": json.dumps(
                                    {
                                        "outcome": "abstain",
                                        "candidate": None,
                                        "abstention_reason": "Test only",
                                    }
                                )
                            }
                        ],
                    }
                },
            },
        )

    generator = bedrock.BedrockGenerator(
        tmp_path,
        "eu-north-1",
        transport=httpx.MockTransport(handle),
    )
    text = asyncio.run(
        generator(
            [
                {"role": "system", "content": "Return JSON."},
                {"role": "user", "content": "Fictional test input."},
            ],
            decision_schema(),
        )
    )
    assert json.loads(text)["outcome"] == "abstain"
    assert len(requests) == 1
    assert "AWS4-HMAC-SHA256" in requests[0].headers["Authorization"]
    assert requests[0].headers["X-Amz-Security-Token"] == "DUMMY_SESSION_TOKEN"
    for path in tmp_path.iterdir():
        for secret in (b"DUMMY_ACCESS_KEY", b"DUMMY_SECRET_KEY", b"DUMMY_SESSION_TOKEN"):
            assert secret not in path.read_bytes()
