"""Persisted authored demonstrations, with inference and network access forbidden."""

from __future__ import annotations

import json
import socket
import subprocess

import pytest

from mwalimulens import portal_demo, portal_qwen
from mwalimulens.agent.execution import atomic_json
from mwalimulens.teacher_portal import REVIEWER


@pytest.fixture(autouse=True)
def no_inference_or_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Authored demonstrations must not start a model, MCP client or network request")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(portal_qwen.QwenJob, "__init__", forbidden)


def contents(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def update(record, name, change):
    path = record.run_dir / name
    value = json.loads(path.read_text())
    change(value)
    atomic_json(path, value)


@pytest.mark.parametrize("scenario,pending", [("candidate", 1), ("error", 0)])
def test_create_and_reopen_authored_case_without_writes_or_generation(tmp_path, scenario, pending):
    record = portal_demo.create_demonstration(tmp_path, scenario)
    assert record.run_dir.name.startswith("demo-") and record.verified
    assert len(record.evidence) == 8
    assert len(record.state.pending_reviews()) == pending
    assert record.state.teacher_reviews() == record.state.profile_updates() == ()
    assert {path.name for path in record.run_dir.iterdir()} == {"state.json", "portal_demo.json"}
    manifest = json.loads((record.run_dir / "portal_demo.json").read_text())
    assert manifest["source"] == "authored_fixture_no_inference"
    assert manifest["case_id"] == record.run_dir.name
    assert manifest["model_request_count"] == manifest["mcp_client_calls"] == 0
    before = contents(tmp_path)
    for _ in range(2):
        reopened = portal_demo.open_demonstration(tmp_path, record.run_dir.name)
        assert reopened.verified and reopened.scenario == scenario
        assert reopened.candidate == record.candidate
        assert reopened.error == record.error
    assert contents(tmp_path) == before


@pytest.mark.parametrize("decision,notes", [("approve", 1), ("edit", 1), ("reject", 0)])
def test_saved_demonstration_retains_only_its_audited_human_decision(tmp_path, decision, notes):
    record = portal_demo.create_demonstration(tmp_path, "candidate")
    record.service.record_teacher_review(
        record.candidate["review_id"], REVIEWER, decision,
        "EV-008 leaves independent explanation uncertain.",
        "Scores rose; independent explanation needs checking." if decision == "edit" else None,
    )
    before = contents(tmp_path)
    reopened = portal_demo.open_demonstration(tmp_path, record.run_dir.name)
    assert reopened.verified, reopened.error
    assert len(reopened.state.pending_reviews()) == 0
    assert len(reopened.state.teacher_reviews()) == 1
    assert len(reopened.state.profile_updates()) == notes
    assert contents(tmp_path) == before


@pytest.mark.parametrize("name,change", [
    ("portal_demo.json", lambda d: d.update(source="qwen")),
    ("portal_demo.json", lambda d: d.update(case_id="demo-another-case")),
    ("portal_demo.json", lambda d: d.update(model_request_count=1)),
    ("portal_demo.json", lambda d: d.update(mcp_client_calls=1)),
    ("portal_demo.json", lambda d: d.update(scenario="error")),
    ("portal_demo.json", lambda d:
     d["initial_state"]["pending_reviews"][0].update(claim="Altered")),
    ("portal_demo.json", lambda d:
     d["initial_state"]["tool_calls"][0]["output"].update(evidence=[])),
    ("state.json", lambda d: d.update(profile_updates=[{"claim": "Unapproved note"}])),
    ("state.json", lambda d: d["tool_calls"][0].update(tool_name="altered_action")),
])
def test_inconsistent_demonstration_opens_unverified_without_candidate(tmp_path, name, change):
    record = portal_demo.create_demonstration(tmp_path, "candidate")
    update(record, name, change)
    before = contents(tmp_path)
    reopened = portal_demo.open_demonstration(tmp_path, record.run_dir.name)
    assert not reopened.verified and reopened.candidate is None
    assert reopened.evidence == [] and "could not be verified" in reopened.error
    assert contents(tmp_path) == before


def test_inconsistent_human_note_is_not_reopened_as_a_valid_case(tmp_path):
    record = portal_demo.create_demonstration(tmp_path, "candidate")
    record.service.record_teacher_review(record.candidate["review_id"], REVIEWER, "approve",
                                         "Retain uncertainty for follow-up assessment.")
    update(record, "state.json", lambda d: d["profile_updates"][0].update(claim="Altered"))
    assert not portal_demo.open_demonstration(tmp_path, record.run_dir.name).verified


def test_later_human_decision_cannot_hide_changes_to_initial_audit(tmp_path):
    record = portal_demo.create_demonstration(tmp_path, "candidate")
    record.service.record_teacher_review(record.candidate["review_id"], REVIEWER, "approve",
                                         "Retain uncertainty for follow-up assessment.")
    update(record, "state.json", lambda d: d["tool_calls"][0].update(output={"altered": True}))
    reopened = portal_demo.open_demonstration(tmp_path, record.run_dir.name)
    assert not reopened.verified and reopened.candidate is None


def test_copying_another_cases_records_does_not_change_the_selected_identity(tmp_path):
    one = portal_demo.create_demonstration(tmp_path, "candidate")
    two = portal_demo.create_demonstration(tmp_path, "error")
    for name in ("portal_demo.json", "state.json"):
        (two.run_dir / name).write_bytes((one.run_dir / name).read_bytes())
    reopened = portal_demo.open_demonstration(tmp_path, two.run_dir.name)
    assert not reopened.verified and reopened.run_dir == two.run_dir


@pytest.mark.parametrize("name", ["portal_demo.json", "state.json"])
def test_missing_malformed_or_linked_records_are_unreviewable(tmp_path, name):
    record = portal_demo.create_demonstration(tmp_path, "candidate")
    path = record.run_dir / name
    original = path.read_bytes()
    path.unlink()
    assert not portal_demo.open_demonstration(tmp_path, record.run_dir.name).verified
    path.write_text("{incomplete")
    assert not portal_demo.open_demonstration(tmp_path, record.run_dir.name).verified
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_bytes(original)
    path.symlink_to(outside)
    assert not portal_demo.open_demonstration(tmp_path, record.run_dir.name).verified


@pytest.mark.parametrize("run_id", ["../demo-outside", "demo-test/../other", "qwen-actual", ""])
def test_demonstration_id_cannot_select_other_paths(tmp_path, run_id):
    with pytest.raises(ValueError):
        portal_demo.open_demonstration(tmp_path, run_id)


def test_demonstrations_and_qwen_attempts_have_separate_catalogues(tmp_path):
    demo = portal_demo.create_demonstration(tmp_path, "candidate")
    qwen = tmp_path / "qwen-existing"
    qwen.mkdir()
    atomic_json(qwen / "portal_job.json", {"status": "abstained"})
    ids = [row["run_id"] for row in portal_demo.saved_demonstrations(tmp_path)]
    assert ids == [demo.run_dir.name]
    assert [row["run_id"] for row in portal_qwen.saved_reviews(tmp_path)] == [qwen.name]
    with pytest.raises(ValueError):
        portal_qwen.QwenJob.open_saved(tmp_path, demo.run_dir.name)
    with pytest.raises(ValueError):
        portal_demo.open_demonstration(tmp_path, qwen.name)


def test_each_new_demonstration_preserves_previous_case_state(tmp_path):
    one = portal_demo.create_demonstration(tmp_path, "candidate")
    before = contents(one.run_dir)
    two = portal_demo.create_demonstration(tmp_path, "error")
    assert one.run_dir != two.run_dir
    assert contents(one.run_dir) == before


def test_malformed_manifest_remains_listed_as_unknown(tmp_path):
    record = portal_demo.create_demonstration(tmp_path, "error")
    (record.run_dir / "portal_demo.json").write_text("{incomplete")
    rows = portal_demo.saved_demonstrations(tmp_path)
    assert rows == [{"run_id": record.run_dir.name, "scenario": "unknown", "created_at": "—"}]


def test_demonstration_rejects_fixture_changes_and_nonfictional_learners(tmp_path, monkeypatch):
    from dataclasses import replace

    record = portal_demo.create_demonstration(tmp_path, "candidate")
    original = portal_demo._evidence_payload
    monkeypatch.setattr(portal_demo, "_evidence_payload", lambda row: {
        **original(row), "observation": "Changed fixture",
    })
    assert not portal_demo.open_demonstration(tmp_path, record.run_dir.name).verified
    dataset = portal_demo._dataset()
    learner = replace(dataset.learners[0], synthetic=False)
    monkeypatch.setattr(portal_demo, "load_synthetic_dataset", lambda _path:
                        replace(dataset, learners=(learner, *dataset.learners[1:])))
    with pytest.raises(ValueError, match="exclusively fictional"):
        portal_demo.create_demonstration(tmp_path, "candidate")


def test_saved_demonstration_rejects_directory_redirection(tmp_path, monkeypatch):
    from pathlib import Path

    one = portal_demo.create_demonstration(tmp_path, "candidate")
    two = portal_demo.create_demonstration(tmp_path, "error")
    original = Path.resolve
    monkeypatch.setattr(Path, "resolve", lambda self, *args, **kwargs:
                        two.run_dir if self == one.run_dir else original(self, *args, **kwargs))
    with pytest.raises(ValueError):
        portal_demo.open_demonstration(tmp_path, one.run_dir.name)
