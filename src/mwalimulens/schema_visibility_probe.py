"""Decision-only schema-visibility comparison; prepare by default, never submit or grade."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from mwalimulens.agent.candidate_contract import (
    DECISION_POLICY_ID,
    EvidenceSnapshot,
    ProposalRejected,
    ReviewDecision,
    review_messages,
    validate_decision,
)
from mwalimulens.agent.execution import atomic_json
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.structured_ollama import OllamaJsonGenerator
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT
from mwalimulens.mcp_server.service import _evidence_payload
from mwalimulens.multi_scenario_eval import SCENARIOS

EXPERIMENT_ID = "schema_visibility_v1"
SCHEMA_TEXT_PREFIX = "\n\nOutput contract (JSON Schema, identical to format):\n"
REQUEST_DEADLINE_SECONDS = 180
SAVED_TARGET = ("L001", "MATH-FRACTIONS")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProbeCase:
    ident: str
    snapshot: EvidenceSnapshot
    source: dict[str, Any]


def load_saved_snapshot(path: Path, target: tuple[str, str]) -> EvidenceSnapshot:
    """The saved digest covers canonical payload JSON, not the enclosing file bytes."""
    saved = json.loads(path.read_text(encoding="utf-8"))
    snapshot = EvidenceSnapshot.from_mcp(saved["payload"], target)
    if snapshot.sha256 != saved.get("sha256"):
        raise ValueError("Saved evidence snapshot hash mismatch")
    return snapshot


def case_snapshots(saved_path: Path) -> tuple[ProbeCase, ...]:
    """Select targets only; expected outcomes and rubric categories are never copied."""
    dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
    cases = []
    for scenario in SCENARIOS:
        target = (scenario.learner, scenario.competency)
        if target == SAVED_TARGET:
            snapshot = load_saved_snapshot(saved_path, target)
            source = {"kind": "saved_snapshot", "path": str(saved_path.resolve()),
                      "file_sha256": hashlib.sha256(saved_path.read_bytes()).hexdigest()}
        else:
            rows = [_evidence_payload(row) for row in dataset.competency_evidence(*target)]
            snapshot = EvidenceSnapshot.from_mcp({
                "learner_id": target[0], "competency_code": target[1],
                "evidence_count": len(rows), "evidence": rows,
            }, target)
            source = {"kind": "synthetic_domain_read", "path": str(DEFAULT_DATA_DIR),
                      "files_sha256": {
                          name: hashlib.sha256((DEFAULT_DATA_DIR / name).read_bytes()).hexdigest()
                          for name in ("learners.json", "learning_evidence.json")
                      }}
        cases.append(ProbeCase(scenario.ident, snapshot, source))
    if sum((case.snapshot.learner_id, case.snapshot.competency_code) == SAVED_TARGET
           for case in cases) != 1:
        raise ValueError("The comparison requires exactly one saved-evidence target")
    return tuple(cases)


def build_conditions(snapshot: EvidenceSnapshot) -> dict[str, dict[str, Any]]:
    schema = ReviewDecision.model_json_schema()
    messages_a = review_messages(snapshot)
    messages_b = [dict(message) for message in messages_a]
    messages_b[0]["content"] += SCHEMA_TEXT_PREFIX + _json(schema)
    return {
        "A": {"messages": messages_a, "format": schema},
        "B": {"messages": messages_b, "format": schema},
    }


def _provenance() -> dict[str, Any]:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=PROJECT_ROOT)

    return {
        "commit": git("rev-parse", "HEAD").decode().strip(),
        "working_tree_status": git("status", "--porcelain=v1").decode(),
        "tracked_diff_sha256": hashlib.sha256(git("diff", "HEAD", "--binary")).hexdigest(),
        "diagnostic_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generator_source_sha256": hashlib.sha256(
            (Path(__file__).parent / "agent" / "structured_ollama.py").read_bytes()
        ).hexdigest(),
    }


def prepare_comparison(
    saved_path: Path, *, output_root: Path, settings: OllamaSettings,
) -> tuple[Path, dict[str, Any], tuple[ProbeCase, ...]]:
    """Freeze all eight requests locally. No model connection or MCP state is created."""
    cases = case_snapshots(saved_path)
    provenance = _provenance()
    output_root = output_root.resolve()
    protected = (PROJECT_ROOT / "evidence", DEFAULT_DATA_DIR,
                 PROJECT_ROOT / "runtime" / "structured_review",
                 PROJECT_ROOT / "runtime" / "multi_scenario", saved_path.resolve().parent)
    if any(output_root == path or output_root.is_relative_to(path) for path in protected):
        raise ValueError("Diagnostic outputs must be separate from source and historical artifacts")
    output_root.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="cmp-", dir=output_root))
    plan = {
        "experiment_id": EXPERIMENT_ID, "decision_only": True,
        "application_workflow_test": False, "submission_enabled": False,
        "semantic_quality_verified": False, "status": "prepared",
        "prepared_at": datetime.now(UTC).isoformat(), **provenance,
        "decision_policy_id": DECISION_POLICY_ID,
        "policy_sha256": _sha(review_messages(cases[0].snapshot)[0]["content"]),
        "schema_sha256": _sha(_json(ReviewDecision.model_json_schema())),
        "hash_encoding": "UTF-8 json.dumps(sort_keys=True, ensure_ascii=False, allow_nan=False)",
        "model_identity": {"requested_name": settings.model_name, "digest": None,
                           "verified": False},
        "request_settings": {"base_url": settings.base_url, "stream": False,
                             "options": {"temperature": 0, "num_predict": 1024},
                             "keep_alive": settings.keep_alive},
        "limits": {"generation_requests": len(cases) * 2, "generation_requests_is_maximum": True,
                   "requests_per_condition": 1,
                   "request_deadline_seconds": REQUEST_DEADLINE_SECONDS, "retries": 0},
        "cases": [],
        "note": "Offline decisions only; no submission, teacher action or scenario grade.",
    }
    for index, case in enumerate(cases):
        case_dir = folder / case.ident
        atomic_json(case_dir / "evidence_snapshot.json", {
            "sha256": case.snapshot.sha256, "payload": json.loads(case.snapshot.payload_json),
        })
        for condition, request in build_conditions(case.snapshot).items():
            atomic_json(case_dir / f"{condition}.request.json", request)
        plan["cases"].append({
            "scenario": case.ident, "evidence_sha256": case.snapshot.sha256,
            "source": case.source, "order": ["A", "B"] if index % 2 == 0 else ["B", "A"],
        })
    atomic_json(folder / "plan.json", plan)
    return folder, plan, cases


class _BorrowedResponseStream(httpx.AsyncByteStream):
    """Let HTTPX read to EOF without closing the owned stream before capture."""

    def __init__(self, inner: httpx.AsyncByteStream):
        self.inner = inner

    async def __aiter__(self):
        async for chunk in self.inner:
            yield chunk

    async def aclose(self):
        pass


class _RecordingTransport(httpx.AsyncBaseTransport):
    """Borrowed by HTTPX; run_condition owns stream and transport cleanup."""

    def __init__(self, inner: httpx.AsyncBaseTransport):
        self.inner = inner
        self.request = None
        self.response = None
        self._response_stream = None
        self._close_attempted = False

    async def handle_async_request(self, request):
        self.request = json.loads(request.content)
        response = await self.inner.handle_async_request(request)
        self._response_stream = response.stream
        response.stream = _BorrowedResponseStream(self._response_stream)
        self.response = {"http_status": response.status_code, "body": None}
        await response.aread()
        try:
            body = response.json()
        except ValueError:
            body = response.text
        self.response = {"http_status": response.status_code, "body": body}
        return response

    async def aclose(self):
        # HTTPX exits its context before the generator parses output/records metrics.
        # Defer owned cleanup until run_condition has retained that outcome.
        pass

    async def close_owned(self):
        errors = []
        if self._close_attempted:
            return errors
        self._close_attempted = True
        for resource, owned in (
            ("response_stream", self._response_stream), ("transport", self.inner),
        ):
            if owned is not None:
                try:
                    await owned.aclose()
                except (asyncio.CancelledError, Exception) as exc:
                    errors.append((resource, exc))
        return errors


async def run_condition(
    case: ProbeCase, condition: str, *, settings: OllamaSettings,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """One generation and offline validation only. There is no submission callback."""
    request = build_conditions(case.snapshot)[condition]
    recording = _RecordingTransport(
        transport if transport is not None else httpx.AsyncHTTPTransport()
    )
    records: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID, "decision_only": True,
        "application_workflow_test": False, "submission_enabled": False,
        "scenario": case.ident, "condition": condition, "decision_policy_id": DECISION_POLICY_ID,
        "schema_sha256": _sha(_json(request["format"])), "evidence_sha256": case.snapshot.sha256,
        "status": "running", "raw_output": None, "parsed_output": None,
        "decision": None, "validation_issues": [], "error": None,
        "cleanup_errors": [], "stop_reason": None,
    }
    try:
        generator = OllamaJsonGenerator(
            model=settings.model_name, base_url=settings.base_url,
            deadline=asyncio.get_running_loop().time() + REQUEST_DEADLINE_SECONDS,
            request_limit=1, records=records, observe=lambda _event: None,
            keep_alive=settings.keep_alive, transport=recording,
        )
        result["raw_output"] = await generator(request["messages"], request["format"])
        try:
            result["decision"] = validate_decision(
                result["raw_output"], case.snapshot,
            ).model_dump(mode="json")
            result["status"] = "valid"
        except ProposalRejected as exc:
            result.update(status="invalid", validation_issues=exc.issues)
    except asyncio.CancelledError:
        result.update(status="interrupted", stop_reason="interrupted",
                      error={"type": "CancelledError"})
    except (TimeoutError, httpx.TimeoutException) as exc:
        result.update(status="timed_out", stop_reason="timed_out", error={
            "type": type(exc).__name__, "message": str(exc),
        })
    except Exception as exc:
        result.update(status="runtime_error", error={
            "type": type(exc).__name__, "message": str(exc),
        })
    finally:
        # Capture available evidence even when the generator rejects the response.
        # No cleanup exception can overwrite the request's outcome or metrics.
        if result["raw_output"] is None and recording.response:
            body = recording.response["body"]
            message = body.get("message") if isinstance(body, dict) else None
            if isinstance(message, dict) and isinstance(message.get("content"), str):
                result["raw_output"] = message["content"]
        if result["raw_output"] is not None:
            try:
                result["parsed_output"] = json.loads(result["raw_output"])
            except ValueError:
                pass
        result.update(actual_request=recording.request, provider_response=recording.response,
                      model_requests=records)
        cleanup_errors = await recording.close_owned()
        result["cleanup_errors"] = [
            {"resource": resource, "type": type(exc).__name__, "message": str(exc)}
            for resource, exc in cleanup_errors
        ]
        if cleanup_errors and result["stop_reason"] is None:
            if any(isinstance(exc, asyncio.CancelledError) for _, exc in cleanup_errors):
                result["stop_reason"] = "interrupted"
            elif any(isinstance(exc, (TimeoutError, httpx.TimeoutException))
                     for _, exc in cleanup_errors):
                result["stop_reason"] = "timed_out"
            else:
                result["stop_reason"] = "cleanup_error"
    return result


async def _model_identity(settings: OllamaSettings) -> dict[str, Any]:
    parsed = urlparse(settings.base_url)
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username or parsed.password
    ):
        raise ValueError("Diagnostic model identity requires a credential-free loopback URL")
    async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
        endpoint = parsed._replace(path="/api/tags", query="", fragment="").geturl()
        response = await client.get(endpoint)
        response.raise_for_status()
        models = response.json()["models"]
    name = settings.model_name
    matching = [item for item in models if item.get("name") in {name, name + ":latest"}]
    if len(matching) != 1 or not matching[0].get("digest"):
        raise ValueError("Cannot resolve requested model to one installed digest")
    return {"requested_name": name, "installed_name": matching[0]["name"],
            "digest": matching[0]["digest"], "verified": True}


async def run_comparison(folder, plan, cases, settings) -> dict[str, Any]:
    """At most eight generations; stop on timeout, cancellation or cleanup failure."""
    path = folder / "comparison.json"
    if path.exists() or any(folder.glob("*/*.decision.json")):
        raise FileExistsError("Refusing to overwrite diagnostic decisions")
    summary = {**plan, "status": "running", "results": [], "not_run": [],
               "stop_reason": None, "model_identity_after": None}
    schedule = [(case, condition) for index, case in enumerate(cases)
                for condition in (["A", "B"] if index % 2 == 0 else ["B", "A"])]
    atomic_json(path, summary)
    try:
        if len(cases) != 4 or len(plan["cases"]) != 4:
            raise ValueError("The diagnostic requires all four cases and at most eight requests")
        for case, entry in zip(cases, plan["cases"], strict=True):
            if entry["scenario"] != case.ident or sorted(entry["order"]) != ["A", "B"]:
                raise ValueError("Each case must run each condition exactly once")
            for condition, request in build_conditions(case.snapshot).items():
                saved = json.loads(
                    (folder / case.ident / f"{condition}.request.json").read_text(encoding="utf-8")
                )
                if saved != request:
                    raise ValueError("Prepared request differs from current policy/schema/evidence")
        schedule = [(case, condition) for case, entry in zip(cases, plan["cases"], strict=True)
                    for condition in entry["order"]]
        summary["model_identity"] = await _model_identity(settings)
        atomic_json(path, summary)
        for case, condition in schedule:
            result = await run_condition(case, condition, settings=settings)
            result["commit"] = plan["commit"]
            result["model_identity"] = summary["model_identity"]
            summary["results"].append(result)
            atomic_json(folder / case.ident / f"{condition}.decision.json", result)
            if result["stop_reason"] is not None:
                summary.update(status=result["stop_reason"], stop_reason=result["stop_reason"])
                return summary
            atomic_json(path, summary)
        summary["model_identity_after"] = await _model_identity(settings)
        summary["model_identity_stable"] = (
            summary["model_identity"] == summary["model_identity_after"]
        )
        summary["status"] = "completed"  # Completion is not correctness or a workflow pass.
    except asyncio.CancelledError:
        summary.update(status="interrupted", stop_reason="interrupted")
    except Exception as exc:
        summary.update(status="runtime_error", error={
            "type": type(exc).__name__, "message": str(exc),
        })
    finally:
        recorded = {(item["scenario"], item["condition"]) for item in summary["results"]}
        summary["not_run"] = [
            {"scenario": case.ident, "condition": condition, "status": "not_run",
             "reason": summary["stop_reason"] or summary["status"]}
            for case, condition in schedule if (case.ident, condition) not in recorded
        ]
        atomic_json(path, summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path,
                        default=PROJECT_ROOT / "runtime" / "schema_visibility")
    parser.add_argument("--run", action="store_true",
                        help="Explicitly run at most eight decision-only requests")
    args = parser.parse_args(argv)
    settings = OllamaSettings.from_env()
    folder, plan, cases = prepare_comparison(
        args.snapshot, output_root=args.output_dir, settings=settings,
    )
    print(f"Decision-only comparison: {folder}")
    if not args.run:
        print("Prepared all four scenarios; no model contacted or decision generated.")
        return 0
    summary = asyncio.run(run_comparison(folder, plan, cases, settings))
    print(f"Diagnostic execution: {summary['status']}; no application-workflow grade")
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
