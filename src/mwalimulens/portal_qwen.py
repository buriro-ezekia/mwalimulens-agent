"""One isolated Qwen workflow for the local portal, with verified saved outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mwalimulens.agent.candidate_contract import (
    DECISION_POLICY_ID,
    OUTCOME_DECISION_SCHEMA_ID,
    EvidenceSnapshot,
    decision_schema,
    decision_schema_metadata,
    review_messages,
    validate_decision,
)
from mwalimulens.agent.execution import atomic_json
from mwalimulens.mcp_server.server import PROJECT_ROOT

WORKER_TIMEOUT_SECONDS = 240
TERMINATE_TIMEOUT_SECONDS = 2
KILL_TIMEOUT_SECONDS = 2
JOIN_TIMEOUT_SECONDS = 5
TARGET = ("L001", "MATH-FRACTIONS")
MODEL = "qwen2.5:3b"
BASE_URL = "http://127.0.0.1:11434/v1"
MODE = "structured_proposal_v1"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant in saved artefact: {value}")


def _read_object(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_ARTIFACT_BYTES:
        raise ValueError(f"Saved {path.name} exceeds the portal's size limit")
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError(f"Saved {path.name} exceeds the portal's size limit")
    value = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise ValueError(f"Saved {path.name} must contain a JSON object")
    return value


def _optional_object(path: Path) -> dict[str, Any] | None:
    try:
        return _read_object(path)
    except (OSError, UnicodeError, ValueError):
        return None


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _view(status: str, stage: str, **values: Any) -> dict[str, Any]:
    return {
        "status": status, "stage": stage, "report": None, "candidate": None,
        "evidence": [], "abstention_reason": None, "error": None, "request_count": 0,
        **values,
    }


class QwenJob:
    """Own one bounded worker; terminal validation and its UI result are frozen once."""

    def __init__(self, output_root: Path):
        root = Path(output_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.run_dir = Path(tempfile.mkdtemp(prefix="qwen-", dir=root))
        self.state_path = self.run_dir / "state.json"
        self._report_path = self.run_dir / "report.json"
        self._result_path = self.run_dir / "result.json"
        self._job_path = self.run_dir / "portal_job.json"
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._started = False
        self._closed = False
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._terminal: dict[str, Any] | None = None
        self._active = _view("running", "queued")
        self._exit_code: int | None = None
        self._command = [
            sys.executable, "-m", "mwalimulens.structured_review", "--single-run",
            "--scenario", "longitudinal-pattern", "--state", str(self.state_path),
            "--report", str(self._report_path), "--result", str(self._result_path),
            "--decision-schema", OUTCOME_DECISION_SCHEMA_ID,
            "--request-limit", "1", "--deadline-seconds", "210",
        ]
        self._persist(self._active)

    def _persist(self, view: dict[str, Any]) -> None:
        atomic_json(self._job_path, {
            "artifact_version": "portal_qwen_job_v1", "updated_at": datetime.now(UTC).isoformat(),
            "status": view["status"], "stage": view["stage"], "error": view["error"],
            "request_count": view["request_count"], "worker_exit_code": self._exit_code,
            "worker_active": self._worker_active(),
            "command": self._command, "cwd": str(PROJECT_ROOT), "model": MODEL,
            "base_url": BASE_URL, "prewarm": False,
            "worker_timeout_seconds": WORKER_TIMEOUT_SECONDS,
            "provider_computation_stopped": "unknown",
        })

    def start(self) -> None:
        """Launch once in a background thread; repeated starts never retry inference."""
        with self._lock:
            if self._started or self._closed:
                return
            self._started = True
            self._thread = threading.Thread(target=self._run, name="portal-qwen", daemon=True)
            try:
                self._thread.start()
            except RuntimeError as exc:
                self._thread = None
                self._set_terminal(self._error_view(f"Could not start the Qwen worker: {exc}"))

    def _set_terminal(self, view: dict[str, Any]) -> None:
        with self._lock:
            if self._terminal is not None:
                return
            self._terminal = deepcopy(view)
            try:
                self._persist(view)
            except OSError as exc:
                self._terminal = _view(
                    "error", "error", report=view["report"], evidence=view["evidence"],
                    request_count=view["request_count"],
                    error=f"Could not save the Qwen job status: {exc}",
                )

    def _stop_worker(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except OSError:
            if process.poll() is not None:
                return
        try:
            process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
        except OSError:
            return
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=KILL_TIMEOUT_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                # Retain the error result; no claim is made about provider-side computation.
                pass

    def _worker_active(self) -> bool:
        with self._lock:
            process, thread = self._process, self._thread
        if process is not None:
            try:
                return process.poll() is None
            except OSError:
                return True
        return thread is not None and thread.is_alive()

    def _available_evidence(self) -> list[dict[str, Any]] | None:
        saved = _optional_object(self.run_dir / "evidence_snapshot.json")
        if saved is not None:
            try:
                snapshot = EvidenceSnapshot.from_mcp(saved.get("payload"), TARGET)
                if snapshot.sha256 == saved.get("sha256"):
                    return snapshot.records
            except (TypeError, ValueError):
                pass
        return None

    def _copy_view(self, view: dict[str, Any]) -> dict[str, Any]:
        copied = deepcopy(view)
        copied["worker_active"] = self._worker_active()
        return copied

    def _error_view(self, message: str, *, stage: str = "error") -> dict[str, Any]:
        with self._lock:
            previous = deepcopy(self._active)
        report = (
            _optional_object(self._report_path)
            or _optional_object(self.run_dir / "report.progress.json") or previous["report"]
        )
        requests = report.get("model_requests") if isinstance(report, dict) else None
        count = len(requests) if isinstance(requests, list) else previous["request_count"]
        evidence = self._available_evidence()
        return _view(
            "error", stage, error=message,
            report=report, evidence=evidence if evidence is not None else previous["evidence"],
            request_count=count,
        )

    def _run(self) -> None:
        process = None
        try:
            if self._stop.is_set():
                return
            environment = os.environ.copy()
            environment.pop("MWALIMULENS_OLLAMA_KEEP_ALIVE", None)
            environment["MWALIMULENS_OLLAMA_MODEL"] = MODEL
            environment["MWALIMULENS_OLLAMA_BASE_URL"] = BASE_URL
            with (
                (self.run_dir / "stdout.txt").open("xb") as stdout,
                (self.run_dir / "stderr.txt").open("xb") as stderr,
            ):
                process = subprocess.Popen(
                    self._command, cwd=PROJECT_ROOT, env=environment,
                    stdout=stdout, stderr=stderr, shell=False,
                )
                with self._lock:
                    self._process = process
                if self._stop.is_set():
                    self._stop_worker(process)
                    return
                try:
                    self._exit_code = process.wait(timeout=WORKER_TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    with self._lock:
                        self._active["stage"] = "stopping"
                    self._stop_worker(process)
                    self._set_terminal(self._error_view(
                        "The Qwen workflow exceeded its 240-second worker limit.",
                    ))
                    return
                if not self._stop.is_set():
                    self._set_terminal(self._completed(self._exit_code))
        except Exception as exc:
            if process is not None:
                with self._lock:
                    self._active["stage"] = "stopping"
                self._stop_worker(process)
            self._set_terminal(self._error_view(f"Qwen workflow could not complete: {exc}"))

    def snapshot(self) -> dict[str, Any]:
        """Read current progress; completed candidate validation is never repeated."""
        with self._lock:
            if self._terminal is not None:
                return self._copy_view(self._terminal)
        progress = _optional_object(self.run_dir / "report.progress.json")
        evidence = self._available_evidence()
        with self._lock:
            if self._terminal is not None:
                return self._copy_view(self._terminal)
            if progress is not None:
                stage = progress.get("active_stage")
                stage = stage if isinstance(stage, str) else None
                if self._active["stage"] != "stopping":
                    self._active["stage"] = {
                        "retrieval": "retrieval", "initial": "generation",
                        "proposal_repair": "validation", "submission": "submission",
                    }.get(stage, self._active["stage"])
                events = progress.get("events")
                if (self._active["stage"] != "stopping" and isinstance(events, list)
                        and events and isinstance(events[-1], dict)):
                    if events[-1].get("event") in {"request_finished", "proposal_valid"}:
                        self._active["stage"] = "validation"
                requests = progress.get("model_requests")
                if isinstance(requests, list):
                    self._active["request_count"] = len(requests)
                self._active["report"] = progress
            if evidence is not None:
                self._active["evidence"] = evidence
            return self._copy_view(self._active)

    def close(self) -> None:
        """Stop the owned worker with bounded waits; never resurrect a late candidate."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stop.set()
            self._active["stage"] = "stopping"
            process, thread = self._process, self._thread
        if process is not None:
            self._stop_worker(process)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=JOIN_TIMEOUT_SECONDS)
        self._set_terminal(self._error_view("The Qwen workflow was stopped.", stage="stopped"))

    def _completed(self, exit_code: int) -> dict[str, Any]:
        report = _read_object(self._report_path)
        result = _read_object(self._result_path)
        proposals = _read_object(self.run_dir / "proposals.json")
        saved = _read_object(self.run_dir / "evidence_snapshot.json")
        state = _read_object(self.state_path)
        snapshot = EvidenceSnapshot.from_mcp(saved.get("payload"), TARGET)
        _require(snapshot.sha256 == saved.get("sha256"), "Saved evidence hash mismatch")
        metadata = decision_schema_metadata(OUTCOME_DECISION_SCHEMA_ID)
        for artifact in (report, result, proposals):
            _require(all(artifact.get(key) == value for key, value in metadata.items()),
                     "Saved decision schema differs from the portal contract")
            _require(artifact.get("decision_policy_id") == DECISION_POLICY_ID
                     and artifact.get("workflow_mode") == MODE,
                     "Saved workflow or policy differs from the portal contract")
        for artifact in (report, proposals):
            _require(artifact.get("evidence_sha256") == snapshot.sha256,
                     "Workflow evidence hash does not match its snapshot")
        _require(report.get("evaluation_target") == {
            "learner_id": TARGET[0], "competency_code": TARGET[1],
        }, "Workflow target does not match the portal case")
        _require(report.get("model") == MODEL and report.get("base_url") == BASE_URL,
                 "Workflow model or endpoint differs from the portal settings")
        _require(report.get("ollama_keep_alive") is None
                 and (report.get("preload") or {}).get("attempted") is False,
                 "The portal does not authorise prewarm generation")
        _require(all(report.get(key) is None for key in ("error", "termination", "cleanup_error"))
                 and result.get("termination") is None and report.get("active_stage") is None,
                 "Workflow reported an error, interruption or incomplete stage")
        _require(report.get("execution_limits") == {
            "request_limit": 1, "proposal_attempt_limit": 1, "deadline_seconds": 210,
        }, "Workflow execution limits differ from the portal budget")
        requests = report.get("model_requests")
        _require(isinstance(requests, list) and len(requests) == 1
                 and isinstance(requests[0], dict)
                 and report.get("model_request_count_observed") == 1,
                 "Workflow must contain exactly one native request")
        _require(requests[0].get("request") == 1 and requests[0].get("status") == "returned"
                 and requests[0].get("mode") == "native_json_schema"
                 and requests[0].get("requested_tool_names") == [],
                 "The native model request did not complete normally")
        _require(not (report.get("completion_recovery") or {}).get("attempted")
                 and not (report.get("grounding_correction") or {}).get("attempted"),
                 "The portal does not authorise recovery or correction requests")
        attempts = proposals.get("attempts")
        _require(proposals.get("artifact_version") == "structured_proposals_v1"
                 and isinstance(attempts, list) and len(attempts) == 1
                 and isinstance(attempts[0], dict), "Expected one captured proposal")
        attempt = attempts[0]
        raw = attempt.get("raw_output")
        _require(attempt.get("attempt") == 1 and attempt.get("status") == "returned"
                 and isinstance(raw, str), "The captured proposal did not return raw JSON")
        _require(hashlib.sha256(raw.encode("utf-8")).hexdigest()
                 == attempt.get("raw_output_sha256"), "Saved proposal output hash mismatch")
        _require(attempt.get("generation_input") == {
            "messages": review_messages(snapshot),
            "format": decision_schema(OUTCOME_DECISION_SCHEMA_ID),
        }, "Saved generation inputs differ from the current policy, schema or evidence")
        decision = validate_decision(raw, snapshot)
        _require(report.get("proposal_attempts") == [
            {"attempt": 1, "status": "valid", "outcome": decision.outcome},
        ], "Recorded proposal validation does not match the saved output")
        pending, teacher, profiles, calls = (
            state.get(key) for key in (
                "pending_reviews", "teacher_reviews", "profile_updates", "tool_calls",
            )
        )
        _require(all(isinstance(items, list) and all(isinstance(item, dict) for item in items)
                     for items in (pending, teacher, profiles, calls)), "Invalid saved MCP state")
        _require(not teacher and not profiles and report.get("teacher_review_count") == 0
                 and report.get("profile_update_count") == 0,
                 "Generation must not record teacher decisions or profile updates")
        names = [call.get("tool_name") for call in calls]
        expected_names = ["get_competency_evidence"]
        if decision.outcome == "candidate":
            expected_names.append("flag_pattern_for_review")
        _require(names == expected_names and all(call.get("status") == "success" for call in calls),
                 "MCP audit does not match the permitted workflow")
        _require(calls[0].get("inputs") == {
            "learner_id": TARGET[0], "competency_code": TARGET[1],
        } and calls[0].get("output") == saved["payload"],
                 "Retrieval audit differs from the snapshot")
        _require(report.get("audited_tool_names") == names
                 and report.get("pending_reviews") == pending
                 and report.get("pending_review_count") == len(pending)
                 and report.get("candidate_submission_audited_attempt_count") == len(calls) - 1,
                 "Report counts do not match the saved MCP audit")
        _require(report.get("agent_tool_allowlist") == []
                 and report.get("submission_actor") == "application_controller"
                 and report.get("model_tool_selection_evaluated") is False,
                 "Model authority differs from the structured portal workflow")
        if decision.outcome == "abstain":
            _require(exit_code == 2 and report.get("proposal_status") == "abstained"
                     and result.get("proposal_status") == "abstained" and not pending
                     and report.get("status") == result.get("status") == "fail",
                     "Abstention did not finish with its expected acceptance result")
            return _view("abstained", "complete", report=report, evidence=snapshot.records,
                         abstention_reason=decision.abstention_reason, request_count=1)
        _require(exit_code == 0 and report.get("status") == result.get("status") == "pass"
                 and report.get("proposal_status") == result.get("proposal_status") == "submitted"
                 and len(pending) == 1, "Candidate workflow did not finish successfully")
        candidate = pending[0]
        arguments = decision.candidate.model_dump(mode="json")
        _require(candidate.get("status") == "pending_teacher_review"
                 and isinstance(candidate.get("review_id"), str) and bool(candidate["review_id"])
                 and all(candidate.get(key) == value for key, value in arguments.items()),
                 "Saved pending candidate does not match the validated proposal")
        _require(calls[1].get("inputs") == arguments and calls[1].get("output") == candidate,
                 "Submission audit does not confirm the saved candidate")
        return _view("candidate", "complete", report=report, candidate=candidate,
                     evidence=snapshot.records, request_count=1)
