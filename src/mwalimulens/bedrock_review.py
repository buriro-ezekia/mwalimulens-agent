"""One explicitly authorised Bedrock request, existing MCP gate and teacher workspace."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from mwalimulens.agent.candidate_contract import (
    OUTCOME_DECISION_SCHEMA_ID,
    EvidenceSnapshot,
    decide_and_submit,
    validate_decision,
)
from mwalimulens.agent.execution import atomic_json
from mwalimulens.agent.orchestrator import build_agent_mcp_client
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.portal_qwen import _validate_saved_human_state

MODEL = "qwen.qwen3-32b-v1:0"
FILES = (
    "request.json",
    "response.txt",
    "evidence_snapshot.json",
    "proposals.json",
    "generation-state.json",
    "result.json",
)


class BedrockGenerator:
    """Signed asynchronous Converse call; no retries, tools or response repairs."""

    def __init__(self, directory: Path, region: str, *, transport=None, signer=None):
        import re

        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region):
            raise ValueError("An explicit AWS region is required")
        self.directory, self.region = directory, region
        self.transport, self.signer = transport, signer
        self.used = False

    def sign(self, url, body):
        # Optional dependency and credentials are resolved only for an authorised run.
        from botocore.auth import SigV4Auth
        from botocore.awsrequest import AWSRequest
        from botocore.session import Session

        credentials = Session().get_credentials()
        if credentials is None:
            raise ValueError("Configure AWS credentials outside the application")
        request = AWSRequest(
            method="POST", url=url, data=body, headers={"Content-Type": "application/json"}
        )
        SigV4Auth(credentials.get_frozen_credentials(), "bedrock", self.region).add_auth(request)
        return dict(request.headers.items())

    async def __call__(self, messages, schema):
        if self.used:
            raise RuntimeError("One Bedrock request is permitted; automatic retry is disabled")
        self.used = True
        if [m["role"] for m in messages] != ["system", "user"]:
            raise ValueError("Expected one system instruction and one evidence message")
        payload = {
            "system": [{"text": messages[0]["content"]}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "text": "Evidence snapshot:\n"
                            + messages[1]["content"]
                            + "\n\nDecision JSON Schema:\n"
                            + json.dumps(schema, ensure_ascii=False)
                        }
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": 1024, "temperature": 0, "topP": 1},
        }
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        (self.directory / "request.json").write_bytes(body)
        url = (
            f"https://bedrock-runtime.{self.region}.amazonaws.com/model/"
            f"{quote(MODEL, safe='')}/converse"
        )
        headers = (self.signer or self.sign)(url, body)
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self.transport, trust_env=False, timeout=httpx.Timeout(180, connect=10)
            ) as client:
                response = await client.post(url, content=body, headers=headers)
            # Preserve HTTP body before status, stop-reason or decision validation.
            (self.directory / "response.txt").write_bytes(response.content)
            atomic_json(
                self.directory / "provider-metrics.json",
                {
                    "http_status": response.status_code,
                    "seconds": perf_counter() - started,
                    "request_id": response.headers.get("x-amzn-requestid"),
                },
            )
            response.raise_for_status()
            data = response.json()
            atomic_json(
                self.directory / "provider-metrics.json",
                {
                    "http_status": response.status_code,
                    "seconds": perf_counter() - started,
                    "request_id": response.headers.get("x-amzn-requestid"),
                    "usage": data.get("usage"),
                    "metrics": data.get("metrics"),
                    "stop_reason": data.get("stopReason"),
                },
            )
            if data.get("stopReason") != "end_turn":
                raise ValueError("Bedrock did not complete a normal text turn")
            if data["output"]["message"].get("role") != "assistant":
                raise ValueError("Expected an assistant response")
            content = data["output"]["message"]["content"]
            if not content or any(set(block) != {"text"} for block in content):
                raise ValueError("Only text decision blocks are accepted; no tools or reasoning")
            return "".join(block["text"] for block in content)
        finally:
            # Timeout/disconnect leaves the remote outcome unknown; never retry automatically.
            if not (self.directory / "provider-metrics.json").exists():
                atomic_json(
                    self.directory / "provider-metrics.json",
                    {
                        "seconds": perf_counter() - started,
                        "remote_outcome": "unknown",
                    },
                )


async def run_case(directory: Path, region: str, *, generator=None):
    """Retrieve through MCP, validate one response and submit only a complete candidate."""
    directory.mkdir(parents=True, exist_ok=False)
    state = JsonStateStore(directory / "state.json")
    events, attempts = [], []
    outcome: dict[str, Any] = {"status": "error"}
    error = None
    generator = generator or BedrockGenerator(directory, region)
    try:
        async with build_agent_mcp_client(
            data_dir=DEFAULT_DATA_DIR,
            state_path=state.path,
        ) as client:
            await client.call_tool(
                "get_competency_evidence",
                {
                    "learner_id": "L001",
                    "competency_code": "MATH-FRACTIONS",
                },
            )
            snapshot = EvidenceSnapshot.from_mcp(
                state.tool_calls()[-1]["output"],
                ("L001", "MATH-FRACTIONS"),
            )
            atomic_json(
                directory / "evidence_snapshot.json",
                {
                    "sha256": snapshot.sha256,
                    "payload": json.loads(snapshot.payload_json),
                },
            )

            async def generate(messages, schema):
                item = {"messages": messages, "schema": schema, "raw_output": None}
                attempts.append(item)
                atomic_json(directory / "proposals.json", {"attempts": attempts})
                text = await generator(messages, schema)
                item["raw_output"] = text
                atomic_json(directory / "proposals.json", {"attempts": attempts})
                return text

            async def submit(arguments):
                await client.call_tool("flag_pattern_for_review", arguments)
                return state.tool_calls()[-1]["output"]

            async with asyncio.timeout(210):
                outcome = await decide_and_submit(
                    snapshot,
                    generate=generate,
                    submit=submit,
                    observe=events.append,
                    request_limit=1,
                    decision_schema_id=OUTCOME_DECISION_SCHEMA_ID,
                )
    except Exception as exc:
        # Provider exception strings may contain account identifiers. Retain type only.
        error = type(exc).__name__
    finally:
        generation = (
            json.loads(state.path.read_text(encoding="utf-8"))
            if state.path.exists()
            else {
                "pending_reviews": [],
                "teacher_reviews": [],
                "profile_updates": [],
                "tool_calls": [],
            }
        )
        atomic_json(directory / "generation-state.json", generation)
        result = {
            "case_id": directory.name,
            "provider": "bedrock",
            "model": MODEL,
            "region": region,
            "schema_delivery": "prompt_text",
            "reasoning_configuration": "provider_default; non-text blocks rejected",
            "recorded_at": datetime.now(UTC).isoformat(),
            "outcome": outcome,
            "error_type": error,
            "events": events,
            "request_limit": 1,
            "semantic_quality_verified": False,
            "educator_moderation_verified": False,
        }
        atomic_json(directory / "result.json", result)
        names = (*FILES, "provider-metrics.json")
        atomic_json(
            directory / "receipt.json",
            {
                "case_id": directory.name,
                "sha256": {
                    name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                    for name in names
                    if (directory / name).exists()
                },
                "note": "Local consistency hashes, not signed provider provenance",
            },
        )
    return result


def open_case(directory: Path):
    """Verify original generation and one audited teacher decision without inference."""
    from mwalimulens.teacher_portal import Case

    directory = directory.resolve()
    receipt = json.loads((directory / "receipt.json").read_text(encoding="utf-8"))
    allowed = set(FILES) | {"provider-metrics.json"}
    if (
        receipt.get("case_id") != directory.name
        or not {
            "generation-state.json",
            "result.json",
        }.issubset(receipt["sha256"])
        or not set(receipt["sha256"]).issubset(allowed)
    ):
        raise ValueError("Invalid Bedrock receipt")
    for name, digest in receipt["sha256"].items():
        path = directory / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Saved Bedrock artefacts changed")
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    if result["case_id"] != directory.name or result["provider"] != "bedrock":
        raise ValueError("Saved provider or case identity differs")
    generation = json.loads((directory / "generation-state.json").read_text(encoding="utf-8"))
    state = JsonStateStore(directory / "state.json")
    if state.path.is_symlink():
        raise ValueError("Linked state is not permitted")
    current = (
        json.loads(state.path.read_text(encoding="utf-8")) if state.path.exists() else generation
    )
    if current.get("tool_calls", [])[: len(generation["tool_calls"])] != generation["tool_calls"]:
        raise ValueError("Original MCP audit changed")
    _validate_saved_human_state(generation, current)
    status = result["outcome"]["status"]
    candidate = generation["pending_reviews"][0] if status == "submitted" else None
    evidence = []
    if "evidence_snapshot.json" in receipt["sha256"]:
        payload = json.loads((directory / "evidence_snapshot.json").read_text(encoding="utf-8"))[
            "payload"
        ]
        evidence = payload["evidence"]
        if candidate:
            attempts = json.loads((directory / "proposals.json").read_text(encoding="utf-8"))[
                "attempts"
            ]
            decision = validate_decision(
                attempts[0]["raw_output"],
                EvidenceSnapshot.from_mcp(
                    payload,
                    ("L001", "MATH-FRACTIONS"),
                ),
            )
            if decision.candidate is None or any(
                candidate.get(k) != v for k, v in decision.candidate.model_dump().items()
            ):
                raise ValueError("Saved candidate differs from model proposal")
    dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
    return Case(
        state,
        EducationToolService(dataset, state),
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--open", type=Path, metavar="SAVED_CASE_DIRECTORY")
    parser.add_argument("--region")
    parser.add_argument("--credit-and-region-confirmed", action="store_true")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "runtime" / "bedrock")
    args = parser.parse_args(argv)
    if args.run:
        if not args.region or not args.credit_and_region_confirmed:
            parser.error("A permitted region and confirmed credit coverage are required for --run")
        # Validate region before creating any case or resolving credentials.
        BedrockGenerator(Path(), args.region)
        args.output_root.mkdir(parents=True, exist_ok=True)
        directory = args.output_root / ("bedrock-" + uuid4().hex)
        result = asyncio.run(run_case(directory, args.region))
        print(json.dumps({"directory": str(directory), **result}, indent=2))
        return 0 if result["outcome"]["status"] == "submitted" else 2
    from mwalimulens.teacher_portal import TeacherPortal, serve

    case = open_case(args.open)
    serve(TeacherPortal(case.run_dir.parent, case), open_browser=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
