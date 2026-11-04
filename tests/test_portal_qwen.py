"""Portal job lifecycle and genuine MCP artefacts, with subprocess/inference mocked."""

from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import threading
from copy import deepcopy

import pytest
from fastmcp import Client

from mwalimulens import portal_qwen, structured_review
from mwalimulens.agent.candidate_contract import OUTCOME_DECISION_SCHEMA_ID
from mwalimulens.agent.execution import ExecutionLimits, atomic_json
from mwalimulens.agent.ollama import OllamaSettings
from mwalimulens.agent.orchestrator import EDUCATION_MCP_CLIENT_MODE
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR, PROJECT_ROOT, build_server
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.multi_scenario_eval import scenario_by_id


def candidate():
    return {"outcome": "candidate", "abstention_reason": None, "candidate": {
        "learner_id": "L001", "competency_code": "MATH-FRACTIONS",
        "claim": "Recorded fraction scores increased, while explanation remained mixed.",
        "supporting_evidence_ids": ["EV-001", "EV-004", "EV-007"],
        "counter_evidence_ids": ["EV-008"],
        "uncertainty": "Independent explanation needs verification on an unfamiliar task.",
        "suggested_teacher_question": "Can the learner explain an unfamiliar task unaided?",
    }}


def abstention():
    return {"outcome": "abstain", "candidate": None,
            "abstention_reason": "Task comparability prevents even a bounded description."}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Portal job tests must never connect to a model or network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(structured_review, "prewarm_ollama_async", forbidden)


@pytest.fixture
def write_case(monkeypatch):
    """Exercise the real structured controller and in-process MCP server."""
    def write(job, output=None):
        response = deepcopy(candidate() if output is None else output)
        server = build_server(data_dir=DEFAULT_DATA_DIR, state_path=job.state_path)
        monkeypatch.setattr(structured_review, "build_agent_mcp_client", lambda **_kw: Client(
            server, mode=EDUCATION_MCP_CLIENT_MODE,
        ))

        class Generate:
            def __init__(self, *, records, observe, **_kwargs):
                self.records, self.observe = records, observe

            async def __call__(self, _messages, _schema):
                record = {"request": 1, "status": "running", "mode": "native_json_schema",
                          "requested_tool_names": []}
                self.records.append(record)
                self.observe({"event": "request_started", **record})
                record.update(status="returned", input_tokens=100, output_tokens=30)
                self.observe({"event": "request_finished", **record})
                return json.dumps(response)

        monkeypatch.setattr(structured_review, "OllamaJsonGenerator", Generate)
        result = asyncio.run(structured_review.run_structured_case(
            scenario_by_id("longitudinal-pattern"), state_path=job.state_path,
            report_path=job.run_dir / "report.json", result_path=job.run_dir / "result.json",
            settings=OllamaSettings(model_name=portal_qwen.MODEL, base_url=portal_qwen.BASE_URL),
            execution_limits=ExecutionLimits(1, 210),
            decision_schema_id=OUTCOME_DECISION_SCHEMA_ID,
        ))
        return 0 if result["status"] == "pass" else 2

    return write


class Process:
    def __init__(self):
        self.returncode = None
        self.waiting = threading.Event()
        self.done = threading.Event()
        self.waits = []
        self.terminated = 0
        self.killed = 0
        self.outer_timeout = False
        self.ignore_terminate = False

    def poll(self):
        return self.returncode

    def finish(self, code):
        self.returncode = code
        self.done.set()

    def wait(self, timeout):
        self.waits.append(timeout)
        if timeout == portal_qwen.WORKER_TIMEOUT_SECONDS:
            self.waiting.set()
            if self.outer_timeout:
                raise subprocess.TimeoutExpired("mocked worker", timeout)
            assert self.done.wait(3), "Test did not release its mocked worker"
        elif not self.done.is_set():
            raise subprocess.TimeoutExpired("mocked worker", timeout)
        return self.returncode

    def terminate(self):
        self.terminated += 1
        if not self.ignore_terminate:
            self.finish(-15)

    def kill(self):
        self.killed += 1
        self.finish(-9)


@pytest.fixture
def process(monkeypatch):
    child = Process()
    child.launches = []

    def launch(command, **kwargs):
        child.launches.append((command, kwargs))
        kwargs["stdout"].write(b"mocked worker stdout\n")
        kwargs["stderr"].write(b"mocked worker stderr\n")
        return child

    monkeypatch.setattr(portal_qwen.subprocess, "Popen", launch)
    return child


def finish(job, process, code):
    process.finish(code)
    job._thread.join(timeout=3)
    assert not job._thread.is_alive()
    return job.snapshot()


def update(job, filename, change):
    path = job.run_dir / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    change(payload)
    atomic_json(path, payload)


@pytest.fixture
def saved_job(tmp_path, write_case, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Reopening must never start inference or a worker")

    monkeypatch.setattr(portal_qwen.subprocess, "Popen", forbidden)

    def build(output=None):
        job = portal_qwen.QwenJob(tmp_path)
        job._exit_code = write_case(job, output)
        job._set_terminal(job._completed(job._exit_code))
        return job

    return build


def saved_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("output,status", [(candidate(), "candidate"),
                                           (abstention(), "abstained")])
def test_reopen_complete_result_is_read_only_and_never_restarts(
    saved_job, tmp_path, output, status,
):
    from mwalimulens.teacher_portal import TeacherPortal, open_qwen_case

    job = saved_job(output)
    before = saved_bytes(tmp_path)
    for _ in range(2):
        case, reopened = open_qwen_case(tmp_path, job.run_dir.name)
        portal = TeacherPortal(tmp_path, case)
        portal.qwen_job = reopened
        portal._sync_qwen()
        assert case.analysis_status == status
        html = portal._page()
        assert job.run_dir.name in html and "no model request was made" in html
        assert "Separate local-model validation" not in html
        assert ("/review/preview" in html) == (status == "candidate")
        reopened.start()
        portal.close()
    assert saved_bytes(tmp_path) == before


@pytest.mark.parametrize("decision,notes", [("approve", 1), ("edit", 1), ("reject", 0)])
def test_reopen_retains_audited_teacher_decision_without_duplicate_notes(
    saved_job, tmp_path, decision, notes,
):
    from mwalimulens.teacher_portal import REVIEWER, TeacherPortal, open_qwen_case

    job = saved_job()
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR),
                                   JsonStateStore(job.state_path))
    service.record_teacher_review(
        job.snapshot()["candidate"]["review_id"], REVIEWER, decision,
        "EV-008 leaves independent explanation uncertain.",
        "Scores differ; independent explanation needs checking." if decision == "edit" else None,
    )
    before = saved_bytes(tmp_path)
    case, reopened = open_qwen_case(tmp_path, job.run_dir.name)
    portal = TeacherPortal(tmp_path, case)
    portal.qwen_job = reopened
    portal._sync_qwen()
    assert case.analysis_status == "candidate", case.analysis_error
    assert len(case.state.pending_reviews()) == 0
    assert len(case.state.teacher_reviews()) == 1
    assert len(case.state.profile_updates()) == notes
    html = portal._page()
    assert "Review recorded" in html and "/review/preview" not in html
    portal.close()
    assert saved_bytes(tmp_path) == before


@pytest.mark.parametrize("filename,change", [
    ("proposals.json", lambda data: data["attempts"][0].update(raw_output="{}")),
    ("evidence_snapshot.json", lambda data: data.update(sha256="wrong")),
    ("report.json", lambda data: data.update(model="different-model")),
    ("portal_job.json", lambda data: data.update(status="abstained")),
    ("portal_job.json", lambda data: data.update(status="running", stage="initial")),
    ("portal_job.json", lambda data: data.update(worker_active=True)),
    ("portal_job.json", lambda data: data.update(prewarm=True)),
    ("state.json", lambda data: data.update(profile_updates=[{"claim": "unapproved"}])),
])
def test_reopen_inconsistent_records_never_expose_candidate(saved_job, tmp_path, filename, change):
    job = saved_job()
    update(job, filename, change)
    before = saved_bytes(tmp_path)
    reopened = portal_qwen.QwenJob.open_saved(tmp_path, job.run_dir.name)
    assert reopened.snapshot()["status"] == "error"
    assert reopened.snapshot()["candidate"] is None
    reopened.close()
    assert saved_bytes(tmp_path) == before


@pytest.mark.parametrize("change", [
    lambda data: data["profile_updates"][0].update(claim="Altered note"),
    lambda data: data["teacher_reviews"][0].update(reason="Altered reason"),
    lambda data: data["pending_reviews"][0].update(status="pending_teacher_review"),
    lambda data: data["tool_calls"][-1]["inputs"].update(reviewer_id="someone-else"),
])
def test_reopen_rejects_inconsistent_human_records(saved_job, tmp_path, change):
    from mwalimulens.teacher_portal import REVIEWER

    job = saved_job()
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR),
                                   JsonStateStore(job.state_path))
    service.record_teacher_review(job.snapshot()["candidate"]["review_id"], REVIEWER,
                                  "approve", "Retain uncertainty for further assessment.")
    update(job, "state.json", change)
    view = portal_qwen.QwenJob.open_saved(tmp_path, job.run_dir.name).snapshot()
    assert view["status"] == "error"


def test_reopen_missing_or_malformed_artifacts_are_read_only_errors(saved_job, tmp_path):
    job = saved_job()
    for path in (job.run_dir / "result.json", job.run_dir / "portal_job.json"):
        path.unlink()
        before = saved_bytes(tmp_path)
        reopened = portal_qwen.QwenJob.open_saved(tmp_path, job.run_dir.name)
        assert reopened.snapshot()["status"] == "error"
        reopened.close()
        assert saved_bytes(tmp_path) == before


@pytest.mark.parametrize("run_id", ["../qwen-outside", "qwen-test/../../other", "case-test", ""])
def test_saved_review_ids_cannot_select_arbitrary_paths(tmp_path, run_id):
    with pytest.raises(ValueError):
        portal_qwen.QwenJob.open_saved(tmp_path, run_id)


def test_saved_reviews_reject_linked_directories_and_artifacts(saved_job, tmp_path):
    job = saved_job()
    link = tmp_path / "qwen-link"
    link.symlink_to(job.run_dir, target_is_directory=True)
    assert [row["run_id"] for row in portal_qwen.saved_reviews(tmp_path)] == [job.run_dir.name]
    with pytest.raises(ValueError):
        portal_qwen.QwenJob.open_saved(tmp_path, link.name)
    report = job.run_dir / "report.json"
    outside = tmp_path / "outside.json"
    report.rename(outside)
    report.symlink_to(outside)
    view = portal_qwen.QwenJob.open_saved(tmp_path, job.run_dir.name).snapshot()
    assert view["status"] == "error"


def test_saved_review_rejects_directory_redirect_even_within_output_root(
    tmp_path, monkeypatch,
):
    from pathlib import Path

    original = Path.resolve
    path = tmp_path / "qwen-selected"
    path.mkdir()
    other = tmp_path / "qwen-another"
    other.mkdir()
    # A Windows junction need not report itself as a symbolic link.
    monkeypatch.setattr(Path, "resolve", lambda self, *args, **kwargs:
                        other if self == path else original(self, *args, **kwargs))
    with pytest.raises(ValueError, match="not a local job directory"):
        portal_qwen.saved_run_path(tmp_path, path.name)


def test_cli_reopens_saved_abstention_without_creating_a_practice_case(
    saved_job, tmp_path, monkeypatch,
):
    from mwalimulens import teacher_portal

    job = saved_job(abstention())
    before = saved_bytes(tmp_path)
    captured = []
    monkeypatch.setattr(teacher_portal, "serve", lambda portal, **_kwargs: captured.append(portal))
    assert teacher_portal.main([
        "--output-dir", str(tmp_path), "--open-qwen", job.run_dir.name, "--no-open",
    ]) == 0
    assert captured[0].case.analysis_status == "abstained"
    assert captured[0].case.run_dir == job.run_dir
    assert captured[0].qwen_enabled is False
    captured[0].close()
    assert saved_bytes(tmp_path) == before


def test_saved_review_cannot_be_reopened_against_changed_fixture(
    saved_job, tmp_path, monkeypatch,
):
    from mwalimulens.mcp_server import service

    job = saved_job(abstention())
    original = service._evidence_payload
    monkeypatch.setattr(service, "_evidence_payload", lambda row: {
        **original(row), "observation": "Changed fictional fixture",
    })
    view = portal_qwen.QwenJob.open_saved(tmp_path, job.run_dir.name).snapshot()
    assert view["status"] == "error" and "current fictional fixture" in view["error"]


def test_constructor_reserves_only_unique_job_directory_not_worker_state(tmp_path):
    one, two = portal_qwen.QwenJob(tmp_path), portal_qwen.QwenJob(tmp_path)
    assert one.run_dir != two.run_dir
    assert one.state_path == one.run_dir / "state.json"
    assert sorted(path.name for path in one.run_dir.iterdir()) == ["portal_job.json"]
    assert one.snapshot() == {
        "status": "running", "stage": "queued", "report": None, "candidate": None,
        "evidence": [], "abstention_reason": None, "error": None, "request_count": 0,
        "worker_active": False,
    }
    one.close()
    two.close()


def test_nonblocking_start_pins_one_safe_worker_and_separate_logs(
    tmp_path, monkeypatch, process,
):
    monkeypatch.setenv("MWALIMULENS_OLLAMA_KEEP_ALIVE", "30m")
    monkeypatch.setenv("MWALIMULENS_OLLAMA_MODEL", "another-model")
    monkeypatch.setenv("MWALIMULENS_OLLAMA_BASE_URL", "https://example.invalid/v1")
    job = portal_qwen.QwenJob(tmp_path)
    starters = [threading.Thread(target=job.start) for _ in range(3)]
    for thread in starters:
        thread.start()
    for thread in starters:
        thread.join(timeout=1)
        assert not thread.is_alive()
    assert process.waiting.wait(2)
    assert len(process.launches) == 1
    command, kwargs = process.launches[0]
    assert command == [
        sys.executable, "-m", "mwalimulens.structured_review", "--single-run",
        "--scenario", "longitudinal-pattern", "--state", str(job.state_path),
        "--report", str(job.run_dir / "report.json"),
        "--result", str(job.run_dir / "result.json"),
        "--decision-schema", OUTCOME_DECISION_SCHEMA_ID,
        "--request-limit", "1", "--deadline-seconds", "210",
    ]
    assert kwargs["cwd"] == PROJECT_ROOT
    assert kwargs["shell"] is False
    assert "MWALIMULENS_OLLAMA_KEEP_ALIVE" not in kwargs["env"]
    assert kwargs["env"]["MWALIMULENS_OLLAMA_MODEL"] == "qwen2.5:3b"
    assert kwargs["env"]["MWALIMULENS_OLLAMA_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert kwargs["stdout"].name != kwargs["stderr"].name
    job.close()
    assert (job.run_dir / "stdout.txt").read_bytes() == b"mocked worker stdout\n"
    assert (job.run_dir / "stderr.txt").read_bytes() == b"mocked worker stderr\n"


@pytest.mark.parametrize("output,code,status", [(candidate(), 0, "candidate"),
                                                (abstention(), 2, "abstained")])
def test_terminal_result_uses_validated_decision_not_expected_candidate_grade(
    tmp_path, process, write_case, output, code, status,
):
    job = portal_qwen.QwenJob(tmp_path)
    assert write_case(job, output) == code
    job.start()
    assert process.waiting.wait(2)
    active = job.snapshot()
    assert active["status"] == "running"
    assert active["candidate"] is None
    assert len(active["evidence"]) == 8
    view = finish(job, process, code)
    assert view["status"] == status
    assert view["request_count"] == 1
    assert view["error"] is None
    assert len(view["evidence"]) == 8
    if status == "abstained":
        assert view["report"]["status"] == "fail"
        assert view["candidate"] is None
        assert view["abstention_reason"] == output["abstention_reason"]
    else:
        assert view["candidate"]["claim"] == output["candidate"]["claim"]
        assert view["candidate"]["status"] == "pending_teacher_review"
    saved_job = json.loads((job.run_dir / "portal_job.json").read_text(encoding="utf-8"))
    assert saved_job["status"] == status
    job.close()
    assert job.snapshot() == view


@pytest.mark.parametrize("bad", [
    "raw_hash", "snapshot_hash", "evidence_hash", "schema", "policy", "audit",
    "state_candidate", "teacher", "profile", "request_count", "cleanup", "termination",
    "missing_report", "missing_sidecar", "candidate_nonzero", "result_failure",
])
def test_inconsistent_or_failed_pipeline_never_offers_partial_candidate(
    tmp_path, process, write_case, bad,
):
    job = portal_qwen.QwenJob(tmp_path)
    write_case(job)
    if bad == "raw_hash":
        update(job, "proposals.json", lambda p: p["attempts"][0].update(raw_output_sha256="bad"))
    elif bad == "snapshot_hash":
        update(job, "evidence_snapshot.json", lambda p: p.update(sha256="bad"))
    elif bad == "evidence_hash":
        update(job, "report.json", lambda p: p.update(evidence_sha256="bad"))
    elif bad == "schema":
        update(job, "proposals.json", lambda p: p["attempts"][0]["generation_input"].update(
            format={"type": "object"},
        ))
    elif bad == "policy":
        update(job, "proposals.json", lambda p: p["attempts"][0]["generation_input"].update(
            messages=[],
        ))
    elif bad == "audit":
        update(job, "state.json", lambda p: p["tool_calls"][0].update(output={}))
    elif bad == "state_candidate":
        update(job, "state.json", lambda p: p["pending_reviews"][0].update(claim="Changed"))
    elif bad in {"teacher", "profile"}:
        key = "teacher_reviews" if bad == "teacher" else "profile_updates"
        update(job, "state.json", lambda p: p[key].append({"unexpected": True}))
    elif bad == "request_count":
        update(job, "report.json", lambda p: p.update(model_request_count_observed=2))
    elif bad == "cleanup":
        update(job, "report.json", lambda p: p.update(cleanup_error={"type": "RuntimeError"}))
    elif bad == "termination":
        update(job, "report.json", lambda p: p.update(termination={"reason": "cancelled"}))
    elif bad == "missing_report":
        (job.run_dir / "report.json").unlink()
    elif bad == "missing_sidecar":
        (job.run_dir / "proposals.json").unlink()
    elif bad == "result_failure":
        update(job, "result.json", lambda p: p.update(status="fail"))
    job.start()
    view = finish(job, process, 2 if bad == "candidate_nonzero" else 0)
    assert view["status"] == "error"
    assert view["candidate"] is None
    assert view["error"]
    assert job.state_path.exists()  # Partial candidates remain in the audit, never in the UI offer.


def test_invalid_model_proposal_stays_error_without_seeded_fallback(tmp_path, process, write_case):
    job = portal_qwen.QwenJob(tmp_path)
    invalid = candidate()
    del invalid["candidate"]["claim"]
    assert write_case(job, invalid) == 2
    job.start()
    view = finish(job, process, 2)
    assert view["status"] == "error"
    assert view["candidate"] is None
    assert view["report"]["proposal_status"] == "invalid_proposal"
    assert view["request_count"] == 1


def test_progress_handles_partial_json_and_never_offers_unfinished_candidate(tmp_path, process):
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    assert process.waiting.wait(2)
    path = job.run_dir / "report.progress.json"
    atomic_json(path, {"active_stage": "initial", "model_requests": [{"status": "running"}]})
    assert job.snapshot()["stage"] == "generation"
    assert job.snapshot()["request_count"] == 1
    path.write_text('{"active_stage":', encoding="utf-8")
    assert job.snapshot()["status"] == "running"
    assert job.snapshot()["stage"] == "generation"
    atomic_json(path, {"active_stage": [], "events": [None], "model_requests": None})
    assert job.snapshot()["candidate"] is None
    job.close()


def test_terminal_candidate_freezes_before_legitimate_human_review(tmp_path, process, write_case):
    job = portal_qwen.QwenJob(tmp_path)
    write_case(job)
    job.start()
    completed = finish(job, process, 0)
    service = EducationToolService(
        load_synthetic_dataset(DEFAULT_DATA_DIR), JsonStateStore(job.state_path),
    )
    service.record_teacher_review(
        review_id=completed["candidate"]["review_id"], reviewer_id="SIMULATED",
        decision="approve", reason="Fictional review after the generation finished.",
    )
    assert job.snapshot() == completed
    completed["candidate"]["claim"] = "Mutated caller copy"
    assert job.snapshot()["candidate"]["claim"] != "Mutated caller copy"


def test_terminal_error_never_becomes_candidate_after_late_files(tmp_path, process, write_case):
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    failed = finish(job, process, 2)
    assert failed["status"] == "error"
    write_case(job)
    job.start()
    assert job.snapshot() == failed
    assert len(process.launches) == 1


def test_watchdog_stops_owned_worker_and_withholds_saved_candidate(tmp_path, process, write_case):
    job = portal_qwen.QwenJob(tmp_path)
    write_case(job)
    process.outer_timeout = True
    process.ignore_terminate = True
    job.start()
    job._thread.join(timeout=3)
    view = job.snapshot()
    assert view["status"] == "error"
    assert "240-second" in view["error"]
    assert view["candidate"] is None
    assert process.terminated == process.killed == 1
    assert process.waits == [240, 2, 2]


def test_close_before_start_and_repeated_close_never_launch(tmp_path, process):
    job = portal_qwen.QwenJob(tmp_path)
    job.close()
    closed = job.snapshot()
    job.start()
    job.close()
    assert job.snapshot() == closed
    assert closed["status"] == "error" and closed["stage"] == "stopped"
    assert process.launches == []


def test_close_running_worker_is_idempotent_and_uses_bounded_wait(tmp_path, process):
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    assert process.waiting.wait(2)
    job.close()
    job.close()
    assert job.snapshot()["stage"] == "stopped"
    assert process.terminated == 1
    assert 2 in process.waits
    assert not job._thread.is_alive()


def test_process_start_error_is_reported_without_creating_state(tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("Mocked process start failure")

    monkeypatch.setattr(portal_qwen.subprocess, "Popen", fail)
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    job._thread.join(timeout=3)
    view = job.snapshot()
    assert view["status"] == "error"
    assert "Mocked process start failure" in view["error"]
    assert not job.state_path.exists()


def test_watchdog_keeps_job_busy_until_delayed_termination_finishes(
    tmp_path, process, monkeypatch,
):
    entered, release = threading.Event(), threading.Event()

    def delayed_terminate():
        entered.set()
        assert release.wait(2), "Test did not release delayed termination"
        process.finish(-15)

    monkeypatch.setattr(process, "terminate", delayed_terminate)
    process.outer_timeout = True
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    assert entered.wait(2)
    stopping = job.snapshot()
    assert stopping["status"] == "running"
    assert stopping["stage"] == "stopping"
    assert stopping["worker_active"] is True
    assert stopping["candidate"] is None
    job.start()
    assert len(process.launches) == 1
    release.set()
    job._thread.join(timeout=3)
    assert job.snapshot()["status"] == "error"
    assert job.snapshot()["worker_active"] is False


def test_unconfirmed_termination_retains_active_worker_flag(tmp_path, process, monkeypatch):
    process.outer_timeout = True
    process.ignore_terminate = True
    monkeypatch.setattr(process, "kill", lambda: None)
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    job._thread.join(timeout=3)
    failed = job.snapshot()
    assert failed["status"] == "error"
    assert failed["worker_active"] is True
    assert failed["candidate"] is None
    process.finish(-9)
    assert job.snapshot()["status"] == "error"
    assert job.snapshot()["worker_active"] is False
    job.close()


def test_unexpected_wait_error_stops_owned_worker_before_reporting_failure(
    tmp_path, process, monkeypatch,
):
    original = process.wait

    def fail_wait(timeout):
        if timeout == 240:
            raise OSError("Mocked wait error")
        return original(timeout)

    monkeypatch.setattr(process, "wait", fail_wait)
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    job._thread.join(timeout=3)
    assert process.terminated == 1
    assert job.snapshot()["status"] == "error"
    assert job.snapshot()["worker_active"] is False


def test_error_view_reads_observed_request_and_evidence_without_any_progress_poll(
    tmp_path, process, write_case,
):
    job = portal_qwen.QwenJob(tmp_path)
    write_case(job)
    update(job, "report.json", lambda p: p.update(cleanup_error={"type": "RuntimeError"}))
    job.start()
    view = finish(job, process, 2)
    assert view["status"] == "error"
    assert view["candidate"] is None
    assert view["request_count"] == 1
    assert len(view["evidence"]) == 8


def test_thread_start_failure_can_be_closed_without_launching_process(
    tmp_path, process, monkeypatch,
):
    def fail_start(_thread):
        raise RuntimeError("Mocked thread start failure")

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    job = portal_qwen.QwenJob(tmp_path)
    job.start()
    assert job.snapshot()["status"] == "error"
    assert job.snapshot()["worker_active"] is False
    job.close()
    job.close()
    assert process.launches == []
