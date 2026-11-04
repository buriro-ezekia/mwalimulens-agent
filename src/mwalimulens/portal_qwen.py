"""One isolated Qwen workflow for the local portal, with verified saved outcomes."""

from __future__ import annotations

import hashlib
import json
import os
import re
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


def saved_run_path(output_root: Path, run_id: str) -> Path:
    """Resolve an immediate local job directory, never a browser-supplied path."""
    root = output_root.expanduser().resolve()
    _require(isinstance(run_id, str) and re.fullmatch(r"qwen-[A-Za-z0-9_-]+", run_id)
             is not None, "Choose a saved Qwen review ID")
    path = root / run_id
    _require(not path.is_symlink() and path.is_dir() and path.resolve() == path,
             "Saved review is not a local job directory")
    return path


def saved_reviews(output_root: Path) -> list[dict[str, str]]:
    """List job labels without treating their metadata as validated outcomes."""
    root = output_root.expanduser().resolve()
    if not root.exists():
        return []
    rows = []
    for path in sorted(root.glob("qwen-*"), reverse=True):
        try:
            saved_run_path(root, path.name)
            manifest = path / "portal_job.json"
            data = None if manifest.is_symlink() else _optional_object(manifest)
            rows.append({"run_id": path.name, "status": str((data or {}).get("status", "unknown")),
                         "updated_at": str((data or {}).get("updated_at", "—"))})
        except (OSError, ValueError):
            continue
    return rows


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


def _validate_saved_human_state(generation: dict[str, Any], state: dict[str, Any]) -> None:
    """Accept only the unchanged result or one consistent simulated human decision."""
    from mwalimulens.mcp_server.service import _resolve_final_claim

    if state == generation:
        return
    pending = generation["pending_reviews"]
    _require(len(pending) == 1, "An abstention cannot have a human decision")
    calls = state.get("tool_calls")
    _require(isinstance(calls, list) and len(calls) == len(generation["tool_calls"]) + 1,
             "Saved review has unexpected later audit actions")
    event = calls[-1]
    _require(isinstance(event, dict) and event.get("tool_name") == "record_teacher_review"
             and event.get("status") == "success" and event.get("error") is None,
             "Saved review has no successful human decision audit")
    inputs, output = event.get("inputs"), event.get("output")
    _require(isinstance(inputs, dict) and isinstance(output, dict),
             "Invalid saved human decision audit")
    original = pending[0]
    decision = inputs.get("decision")
    reason = inputs.get("reason")
    _require(decision in {"approve", "edit", "reject"}
             and inputs.get("review_id") == original["review_id"]
             and inputs.get("reviewer_id") == "simulated-teacher-not-authenticated"
             and isinstance(reason, str) and bool(reason.strip()),
             "Saved human decision does not match the simulated portal contract")
    final = _resolve_final_claim(decision=decision, original_claim=original["claim"],
                                edited_claim=inputs.get("edited_claim"))
    review = output.get("teacher_review")
    profile = output.get("profile_update")
    _require(isinstance(review, dict) and isinstance(review.get("teacher_review_id"), str)
             and bool(review["teacher_review_id"]), "Invalid saved teacher review")
    timestamp = event.get("timestamp")
    _require(isinstance(timestamp, str), "Missing human decision timestamp")
    parsed = datetime.fromisoformat(timestamp)
    _require(parsed.tzinfo is not None, "Human decision timestamp must include a timezone")
    shared = {key: original[key] for key in (
        "review_id", "learner_id", "competency_code", "supporting_evidence_ids",
        "counter_evidence_ids",
    )}
    expected_review = {**shared, "teacher_review_id": review["teacher_review_id"],
                       "reviewer_id": inputs["reviewer_id"], "decision": decision,
                       "reason": reason, "original_claim": original["claim"],
                       "final_claim": final, "reviewed_at": timestamp}
    _require(review == expected_review, "Human decision fields differ from their audit inputs")
    expected_profile = None
    if decision != "reject":
        _require(isinstance(profile, dict) and isinstance(profile.get("profile_update_id"), str)
                 and bool(profile["profile_update_id"]), "Missing saved synthetic profile note")
        expected_profile = {**shared, "profile_update_id": profile["profile_update_id"],
                            "teacher_review_id": review["teacher_review_id"],
                            "reviewer_id": inputs["reviewer_id"], "decision": decision,
                            "claim": final, "recorded_at": timestamp}
    _require(profile == expected_profile, "Synthetic profile note differs from the human decision")
    statuses = {"approve": "approved_by_teacher", "edit": "edited_by_teacher",
                "reject": "rejected_by_teacher"}
    resolved = {**original, "status": statuses[decision],
                "resolved_at": timestamp, "teacher_review_id": review["teacher_review_id"]}
    _require(state == {"pending_reviews": [resolved], "teacher_reviews": [expected_review],
                       "profile_updates": [expected_profile] if expected_profile else [],
                       "tool_calls": calls}, "Saved state differs from its audited human decision")


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

    @classmethod
    def open_saved(cls, output_root: Path, run_id: str) -> QwenJob:
        """Load a detached result without creating files, a thread or a process."""
        job = cls.__new__(cls)
        job.run_dir = saved_run_path(output_root, run_id)
        job.state_path = job.run_dir / "state.json"
        job._report_path = job.run_dir / "report.json"
        job._result_path = job.run_dir / "result.json"
        job._job_path = job.run_dir / "portal_job.json"
        job._lock = threading.RLock()
        job._stop = threading.Event()
        job._started = job._closed = True
        job._process = job._thread = None
        job._terminal = None
        job._active = _view("error", "error")
        job._exit_code = None
        job._command = []
        try:
            for name in ("portal_job.json", "state.json", "report.json", "result.json",
                         "proposals.json", "evidence_snapshot.json", "report.progress.json"):
                _require(not (job.run_dir / name).is_symlink(),
                         "Saved review contains a linked artefact")
            metadata = _read_object(job._job_path)
            _require(metadata.get("artifact_version") == "portal_qwen_job_v1",
                     "Unsupported saved job metadata")
            _require(metadata.get("model") == MODEL and metadata.get("base_url") == BASE_URL
                     and metadata.get("prewarm") is False and metadata.get("error") is None
                     and metadata.get("worker_timeout_seconds") == WORKER_TIMEOUT_SECONDS,
                     "Saved job settings differ from the portal contract")
            _require(metadata.get("status") in {"candidate", "abstained"}
                     and metadata.get("stage") == "complete"
                     and metadata.get("worker_active") is False,
                     "This saved attempt has no completed outcome to reopen; "
                     "it cannot be resumed or attached to a worker")
            state = _read_object(job.state_path)
            report = _read_object(job._report_path)
            # The report captures generation-time state; later human decisions are
            # checked separately rather than changing or regrading that report.
            call_count = len(report.get("audited_tool_names") or [])
            calls = state.get("tool_calls")
            _require(isinstance(calls, list), "Invalid saved MCP audit")
            generation = {"pending_reviews": report.get("pending_reviews"),
                          "teacher_reviews": [], "profile_updates": [],
                          "tool_calls": calls[:call_count]}
            view = job._completed(metadata.get("worker_exit_code"), state=generation)
            from mwalimulens.domain import load_synthetic_dataset
            from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
            from mwalimulens.mcp_server.service import _evidence_payload

            dataset = load_synthetic_dataset(DEFAULT_DATA_DIR)
            fictional = dataset.learners and all(learner.synthetic for learner in dataset.learners)
            _require(bool(fictional)
                     and view["evidence"] == [
                         _evidence_payload(row) for row in dataset.competency_evidence(*TARGET)
                     ], "Saved evidence differs from the current fictional fixture")
            _validate_saved_human_state(generation, state)
            _require(metadata.get("status") == view["status"]
                     and metadata.get("request_count") == view["request_count"],
                     "Saved job label differs from its verified outcome")
            job._terminal = view
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError) as exc:
            # Do not read further artefacts after a rejected path or malformed bundle.
            job._terminal = _view(
                "error", "saved_error", error=f"Saved review could not be verified: {exc}",
            )
        return job

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

    def _completed(self, exit_code: int, *, state: dict[str, Any] | None = None) -> dict[str, Any]:
        report = _read_object(self._report_path)
        result = _read_object(self._result_path)
        proposals = _read_object(self.run_dir / "proposals.json")
        saved = _read_object(self.run_dir / "evidence_snapshot.json")
        if state is None:
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
