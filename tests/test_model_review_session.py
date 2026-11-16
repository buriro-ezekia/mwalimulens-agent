"""Bounded operator sessions and read-only continuity checks; no live inference."""

from __future__ import annotations

import hashlib
import json
import socket
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from test_portal_qwen import write_case as write_case

from mwalimulens import model_review_session as session
from mwalimulens import portal_qwen
from mwalimulens.domain import load_synthetic_dataset
from mwalimulens.mcp_server.server import DEFAULT_DATA_DIR
from mwalimulens.mcp_server.service import EducationToolService
from mwalimulens.mcp_server.state import JsonStateStore
from mwalimulens.teacher_portal import REVIEWER


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Session tests must never start a subprocess or contact a model")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(portal_qwen.subprocess, "Popen", forbidden)


@pytest.fixture
def provenance():
    return {
        "ready": True, "model_requests": 0,
        "source": {"head": "a" * 40, "dirty": False,
                   "fixture_sha256": {"evidence.json": "b" * 64}},
        "provider": {"model": portal_qwen.MODEL, "digest": "sha256:" + "c" * 64,
                     "version": "test-only", "base_url": portal_qwen.BASE_URL},
        "errors": [],
    }


def all_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


@pytest.fixture
def recorded_session(tmp_path, monkeypatch, write_case, provenance):
    """Run the real structured/MCP contract with only the model response mocked."""
    original = session.QwenJob
    jobs = []

    def build(output=None):
        job = original(tmp_path)
        starts = []

        def start():
            starts.append(True)
            assert len(starts) == 1
            for name in ("stdout.txt", "stderr.txt"):
                (job.run_dir / name).write_text("Mocked worker; no live inference.\n")
            job._exit_code = write_case(job, output)
            job._set_terminal(job._completed(job._exit_code))

        monkeypatch.setattr(job, "start", start)
        monkeypatch.setattr(session, "QwenJob", lambda _root: job)
        result = session.run_once(tmp_path, deepcopy(provenance))
        monkeypatch.setattr(session, "QwenJob", original)
        jobs.append((job, starts, result))
        return job, result

    return build


def test_failed_preflight_creates_no_job_or_files(tmp_path, monkeypatch):
    def forbidden(*_args):
        pytest.fail("A failed preflight must not allocate a model attempt")

    monkeypatch.setattr(session, "QwenJob", forbidden)
    with pytest.raises(ValueError, match="Preflight"):
        session.run_once(tmp_path, {"ready": False})
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("outcome", ["abstained", "error"])
def test_terminal_non_candidates_are_saved_without_retry_or_human_action(
    tmp_path, monkeypatch, provenance, outcome,
):
    run_dir = tmp_path / "qwen-terminal"
    run_dir.mkdir()
    starts, closes = [], []
    view = {"status": outcome, "worker_active": False, "request_count": 1,
            "error": "Test transport failure" if outcome == "error" else None}
    job = SimpleNamespace(run_dir=run_dir, start=lambda: starts.append(True),
                          close=lambda: closes.append(True), snapshot=lambda: view)
    monkeypatch.setattr(session, "QwenJob", lambda _root: job)
    result = session.run_once(tmp_path, provenance)
    assert starts == closes == [True]
    assert result["outcome"] == outcome
    assert result["teacher_review_status"] == "not_available"
    assert result["sequence_complete"] is False
    assert {p.name for p in run_dir.iterdir()} == {
        "session_provenance.json", "session_result.json",
    }
    assert not (run_dir / "state.json").exists()
    saved = json.loads((run_dir / "session_result.json").read_text())
    assert saved["outcome"] == outcome and saved["model_requests"] == 1


def test_one_generation_is_pending_until_teacher_revises_and_reopens(
    recorded_session, tmp_path, monkeypatch,
):
    job, result = recorded_session()
    assert result["outcome"] == "candidate"
    assert result["sequence_complete"] is False
    assert result["teacher_review_status"] == "pending"
    provenance = json.loads((job.run_dir / "session_provenance.json").read_text())
    assert provenance["teacher_identity"] == "simulated-teacher-not-authenticated"
    assert provenance["model_tool_selection_evaluated"] is False
    assert provenance["request_limit"] == 1
    before = all_bytes(tmp_path)
    pending = session.verify_session(tmp_path, job.run_dir.name)
    assert pending["sequence_complete"] is False
    assert (pending["pending"], pending["teacher_decisions"],
            pending["synthetic_profile_notes"]) == (1, 0, 0)
    assert all_bytes(tmp_path) == before

    reason = "EV-008 leaves independent explanation uncertain; retain that limitation."
    final = "Recorded scores rose; independent explanation needs an unfamiliar task."
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR),
                                   JsonStateStore(job.state_path))
    service.record_teacher_review(job.snapshot()["candidate"]["review_id"], REVIEWER,
                                  "edit", reason, final)
    before = all_bytes(tmp_path)

    def no_preflight():
        pytest.fail("Saved verification must not query provider metadata")

    monkeypatch.setattr(session, "preflight", no_preflight)
    for _ in range(2):
        verified = session.verify_session(tmp_path, job.run_dir.name)
        assert verified["case_id"] == job.run_dir.name
        assert verified["sequence_complete"] is True
        assert verified["reopening_verified"] is True
        assert verified["semantic_quality_verified"] is False
        assert "not authenticated teacher" in verified["note"]
        assert verified["model_requests"] == 1
        assert (verified["pending"], verified["teacher_decisions"],
                verified["synthetic_profile_notes"]) == (0, 1, 1)
        assert verified["teacher_reason"] == reason
        assert verified["final_wording"] == final
        assert session.main(["--output-dir", str(tmp_path),
                             "--verify", job.run_dir.name]) == 0
    assert all_bytes(tmp_path) == before


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_other_human_decisions_do_not_claim_the_revision_sequence(
    recorded_session, tmp_path, decision,
):
    job, _ = recorded_session()
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR),
                                   JsonStateStore(job.state_path))
    service.record_teacher_review(job.snapshot()["candidate"]["review_id"], REVIEWER,
                                  decision, "Keep this decision separate from a revision.")
    verified = session.verify_session(tmp_path, job.run_dir.name)
    assert verified["sequence_complete"] is False
    assert session.main(["--output-dir", str(tmp_path), "--verify", job.run_dir.name]) == 2


@pytest.mark.parametrize("target", ["session_provenance.json", *session.ARTIFACTS])
def test_changed_provenance_or_generation_fails_closed(recorded_session, tmp_path, target):
    job, _ = recorded_session()
    path = job.run_dir / target
    path.write_bytes(path.read_bytes() + b"\n")
    before = all_bytes(tmp_path)
    with pytest.raises(ValueError, match="changed"):
        session.verify_session(tmp_path, job.run_dir.name)
    assert all_bytes(tmp_path) == before


@pytest.mark.parametrize("target", ["session_provenance.json", "session_result.json",
                                    *session.ARTIFACTS])
def test_missing_provenance_or_generation_fails_closed(recorded_session, tmp_path, target):
    job, _ = recorded_session()
    (job.run_dir / target).unlink()
    before = all_bytes(tmp_path)
    assert session.main(["--output-dir", str(tmp_path), "--verify", job.run_dir.name]) == 2
    assert all_bytes(tmp_path) == before


def test_generation_ready_cli_does_not_claim_a_completed_teacher_sequence(
    tmp_path, monkeypatch, provenance, capsys,
):
    attempts = []
    monkeypatch.setattr(session, "preflight", lambda: provenance)

    def run(root, supplied):
        attempts.append((root, supplied))
        return {"case_id": "qwen-generation-only", "outcome": "candidate",
                "sequence_complete": False, "teacher_review_status": "pending"}

    monkeypatch.setattr(session, "run_once", run)
    assert session.main(["--output-dir", str(tmp_path), "--run", "--no-open"]) == 0
    assert len(attempts) == 1
    assert json.loads(capsys.readouterr().out)["sequence_complete"] is False


def test_default_cli_is_preflight_only(monkeypatch, provenance, capsys):
    monkeypatch.setattr(session, "preflight", lambda: provenance)
    monkeypatch.setattr(session, "run_once", lambda *_args: pytest.fail("Not authorised"))
    assert session.main([]) == 0
    assert json.loads(capsys.readouterr().out)["model_requests"] == 0


@pytest.mark.parametrize("dirty,models,ready", [
    (False, [{"name": portal_qwen.MODEL, "digest": "test-digest"}], True),
    (True, [{"name": portal_qwen.MODEL, "digest": "test-digest"}], False),
    (False, [{"name": "other-model", "digest": "other-digest"}], False),
    (False, [{"name": portal_qwen.MODEL}], False),
    (False, ["malformed-entry"], False),
])
def test_preflight_checks_only_provider_metadata_and_records_source(
    tmp_path, monkeypatch, dirty, models, ready,
):
    fixture = tmp_path / "evidence.json"
    fixture.write_text('{"fictional": true}\n')
    monkeypatch.setattr(session, "DEFAULT_DATA_DIR", tmp_path)
    commands, requests = [], []

    def git(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=("M README.md" if dirty else "")
                               if command[1] == "status" else "a" * 40)

    monkeypatch.setattr(session.subprocess, "run", git)

    def respond(request):
        requests.append((request.method, request.url.path))
        payload = ({"version": "test-version"} if request.url.path == "/api/version"
                   else {"models": models})
        return httpx.Response(200, json=payload)

    client_type = httpx.Client
    monkeypatch.setattr(session.httpx, "Client", lambda **kwargs: client_type(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    result = session.preflight()
    assert result["ready"] is ready
    assert result["source"]["head"] == "a" * 40
    assert result["source"]["fixture_sha256"] == {
        fixture.name: hashlib.sha256(fixture.read_bytes()).hexdigest(),
    }
    assert result["source"]["dirty"] is dirty
    if ready:
        assert result["provider"]["digest"] == "test-digest"
    else:
        assert result["errors"]
    assert requests == [("GET", "/api/version"), ("GET", "/api/tags")]
    assert result["model_requests"] == 0
    assert all(command[0] == "git" for command in commands)


@pytest.mark.parametrize("target", ["session_provenance.json", "session_result.json"])
@pytest.mark.parametrize("payload", [[], None])
def test_non_object_session_records_are_reported_as_unverified(
    recorded_session, tmp_path, target, payload,
):
    job, _ = recorded_session()
    (job.run_dir / target).write_text(json.dumps(payload))
    before = all_bytes(tmp_path)
    assert session.main(["--output-dir", str(tmp_path), "--verify", job.run_dir.name]) == 2
    assert all_bytes(tmp_path) == before


def test_inconsistent_teacher_note_cannot_complete_the_sequence(recorded_session, tmp_path):
    job, _ = recorded_session()
    service = EducationToolService(load_synthetic_dataset(DEFAULT_DATA_DIR),
                                   JsonStateStore(job.state_path))
    service.record_teacher_review(job.snapshot()["candidate"]["review_id"], REVIEWER,
                                  "edit", "Retain the uncertainty in EV-008.",
                                  "Recorded scores rose; explanation remains uncertain.")
    state = json.loads(job.state_path.read_text())
    state["profile_updates"][0]["claim"] = "Unaudited replacement wording."
    job.state_path.write_text(json.dumps(state))
    before = all_bytes(tmp_path)
    with pytest.raises(ValueError, match="no verified"):
        session.verify_session(tmp_path, job.run_dir.name)
    assert all_bytes(tmp_path) == before
