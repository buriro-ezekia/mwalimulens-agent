"""Checks reject incomplete takes without changing the demo or its evidence."""

from __future__ import annotations

import copy
import json
import subprocess
from types import SimpleNamespace

import pytest

from mwalimulens import recording_checks as checks


@pytest.fixture
def report():
    candidate = {
        "status": "pending_teacher_review", "learner_id": "L001",
        "competency_code": "MATH-FRACTIONS", "claim": "Improved across terms.",
        "uncertainty": "Independent explanation remains mixed.",
        "suggested_teacher_question": "Does this hold in unfamiliar tasks?",
        "supporting_evidence_ids": ["EV-004", "EV-007", "EV-009", "EV-011"],
        "counter_evidence_ids": ["EV-008"],
    }
    calls = [
        {"tool_name": "get_competency_evidence", "status": "success", "error": None},
        {"tool_name": "read_text_file", "status": "success", "source": "borrowed_mcp",
         "toolset_id": "borrowed-official-filesystem-mcp", "error": None},
        {"tool_name": "flag_pattern_for_review", "status": "success", "error": None,
         "output": copy.deepcopy(candidate)},
    ]
    return {
        "status": "pass", "mode": "fast_deterministic_demo", "error": None,
        "learner": {"learner_id": "L001", "synthetic": True},
        "competency_code": "MATH-FRACTIONS", "candidate": candidate,
        "pending_review_count": 1, "teacher_review_count": 0, "profile_update_count": 0,
        "checks": {name: True for name in (
            "education_evidence_retrieved", "borrowed_reference_read", "candidate_created",
            "human_gate_untouched", "model_tool_surface_safe", "real_qwen_evidence_passed",
            "challenge_evidence_passed", "evaluation_evidence_passed", "final_output_present",
        )},
        "visible_tools": [
            "get_learner_timeline", "get_competency_evidence", "flag_pattern_for_review",
            "read_text_file", "read_multiple_files", "list_directory", "search_files",
            "get_file_info", "list_allowed_directories",
        ],
        "tool_calls": calls,
        "evidence": [
            {"evidence_id": evidence_id, "role": "supporting"}
            for evidence_id in ["EV-004", "EV-007", "EV-009", "EV-011"]
        ] + [{"evidence_id": "EV-008", "role": "counter", "observation": "Needed help."}],
        "real_qwen_validation": {"status": "pass", "model": "qwen2.5:3b"},
        "challenge_validation": {"status": "pass", "model": "qwen2.5:3b"},
        "evaluation_validation": {"status": "pass", "summary": {
            "current_pass": 11, "current_fail": 0, "current_regression_cases": 11,
            "historical_fail_preserved": 2, "historical_failure_cases": 2, "total_cases": 13,
        }},
        "final_output": "Candidate prepared for human teacher review.",
    }


def test_report_check_is_read_only(report):
    original = copy.deepcopy(report)
    checks.validate_demo_report(report)
    assert original == report


@pytest.mark.parametrize(("key", "value"), [
    ("status", "fail"), ("error", {"message": "failed"}),
    ("mode", "real_qwen_run"), ("learner", {"learner_id": "L001", "synthetic": False}),
    ("competency_code", "OTHER"), ("candidate", None), ("pending_review_count", 0),
    ("teacher_review_count", 1), ("profile_update_count", 1), ("teacher_review_count", False),
    ("checks", {}), ("checks", {"human_gate_untouched": True}), ("evidence", []),
    ("visible_tools", []), ("tool_calls", []), ("final_output", " "),
    ("real_qwen_validation", {"status": "pass", "model": "scripted"}),
    ("challenge_validation", {"status": "fail"}),
    ("evaluation_validation", {"status": "pass", "summary": {}}),
])
def test_report_rejects_pass_label_over_incomplete_or_unsafe_facts(report, key, value):
    report[key] = value
    with pytest.raises(checks.RecordingCheckError):
        checks.validate_demo_report(report)


@pytest.mark.parametrize(("key", "value"), [
    ("status", "approved"), ("learner_id", "L002"), ("competency_code", "OTHER"),
    ("supporting_evidence_ids", ["EV-004"]), ("counter_evidence_ids", []),
    ("counter_evidence_ids", [{"fake": "EV-008"}]), ("uncertainty", ""),
    ("suggested_teacher_question", None),
])
def test_report_rejects_changed_candidate(report, key, value):
    report["candidate"][key] = value
    with pytest.raises(checks.RecordingCheckError):
        checks.validate_demo_report(report)


@pytest.mark.parametrize("problem", ["failure", "source", "order", "human", "candidate", "check"])
def test_report_requires_actual_ordered_successful_mcp_audit(report, problem):
    if problem == "failure":
        report["tool_calls"][0]["status"] = "error"
    elif problem == "source":
        report["tool_calls"][1].pop("source")
    elif problem == "order":
        report["tool_calls"].reverse()
    elif problem == "human":
        report["visible_tools"].append("record_teacher_review")
    elif problem == "candidate":
        report["tool_calls"][2]["output"]["status"] = "approved"
    else:
        report["checks"]["candidate_created"] = "true"
    with pytest.raises(checks.RecordingCheckError):
        checks.validate_demo_report(report)


def test_report_keeps_counter_observation_and_historical_failures(report):
    report["evidence"][-1]["observation"] = None
    with pytest.raises(checks.RecordingCheckError, match="observation"):
        checks.validate_demo_report(report)
    report["evidence"][-1]["observation"] = "Needed help."
    report["evaluation_validation"]["summary"]["historical_fail_preserved"] = 0
    with pytest.raises(checks.RecordingCheckError, match="historical failures"):
        checks.validate_demo_report(report)


@pytest.fixture
def media(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    narration = tmp_path / "narration.mp3"
    video = tmp_path / "take.mp4"
    narration.touch()
    video.touch()
    audio_meta = {"format": {"duration": "156.48"}, "streams": [
        {"codec_type": "audio", "codec_name": "mp3"},
    ]}
    video_meta = {"format": {"duration": "160.0"}, "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1920,
         "height": 1080, "avg_frame_rate": "30/1"},
        {"codec_type": "audio", "codec_name": "aac"},
    ]}
    return repo, narration, video, audio_meta, video_meta


def test_valid_narration_and_recording_metadata(media):
    root, narration, video, audio_meta, video_meta = media
    assert checks.check_narration(narration, audio_meta, root) == 156.48
    assert checks.verify_recording(video, video_meta, root) == 160
    mkv = video.with_suffix(".mkv")
    mkv.touch()
    assert checks.verify_recording(mkv, video_meta, root) == 160


def test_narration_allows_cover_art_but_no_moving_video(media):
    root, narration, _, metadata, _ = media
    cover = {"codec_type": "video", "codec_name": "mjpeg", "disposition": {"attached_pic": 1}}
    metadata["streams"].append(cover)
    checks.check_narration(narration, metadata, root)
    cover["disposition"]["attached_pic"] = 0
    with pytest.raises(checks.RecordingCheckError, match="moving video"):
        checks.check_narration(narration, metadata, root)


@pytest.mark.parametrize("duration", ["nan", "inf", "-inf", None, True, "bad", "0", "-1"])
def test_duration_rejects_nonfinite_and_invalid_values(media, duration):
    root, narration, video, audio_meta, video_meta = media
    for meta in (audio_meta, video_meta):
        meta["format"]["duration"] = duration
    with pytest.raises(checks.RecordingCheckError):
        checks.check_narration(narration, audio_meta, root)
    with pytest.raises(checks.RecordingCheckError):
        checks.verify_recording(video, video_meta, root)


@pytest.mark.parametrize("duration", [156, 165.01, 179.9, 180, 181, 1000])
def test_recording_rejects_wrong_length_including_three_minutes(media, duration):
    root, _, video, _, metadata = media
    metadata["format"]["duration"] = str(duration)
    with pytest.raises(checks.RecordingCheckError):
        checks.verify_recording(video, metadata, root)


@pytest.mark.parametrize(("field", "value"), [
    ("width", 1280), ("height", 720), ("avg_frame_rate", "30000/1001"),
    ("avg_frame_rate", "0/0"), ("avg_frame_rate", "inf"), ("codec_name", "hevc"),
])
def test_recording_rejects_wrong_video_format(media, field, value):
    root, _, video, _, metadata = media
    metadata["streams"][0][field] = value
    with pytest.raises(checks.RecordingCheckError):
        checks.verify_recording(video, metadata, root)


def test_recording_requires_audio_and_narration_requires_original_duration(media):
    root, narration, video, audio_meta, video_meta = media
    video_meta["streams"].pop()
    with pytest.raises(checks.RecordingCheckError, match="audio"):
        checks.verify_recording(video, video_meta, root)
    audio_meta["format"]["duration"] = "150"
    with pytest.raises(checks.RecordingCheckError, match="156.48"):
        checks.check_narration(narration, audio_meta, root)


def test_media_must_stay_outside_repo_and_must_exist(media):
    root, _, _, audio_meta, video_meta = media
    narration = root / "narration.mp3"
    video = root / "take.mp4"
    narration.touch()
    video.touch()
    with pytest.raises(checks.RecordingCheckError, match="outside"):
        checks.check_narration(narration, audio_meta, root)
    with pytest.raises(checks.RecordingCheckError, match="outside"):
        checks.verify_recording(video, video_meta, root)
    with pytest.raises(checks.RecordingCheckError, match="does not exist"):
        checks.probe_media(root / "missing.mp4", "ffprobe")


def test_probe_is_bounded_and_shell_free(media, monkeypatch):
    _, narration, _, audio_meta, _ = media
    observed = []

    def run(args, **kwargs):
        observed.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(audio_meta))

    monkeypatch.setattr(checks.subprocess, "run", run)
    assert checks.probe_media(narration, "ffprobe") == audio_meta
    args, kwargs = observed[0]
    assert args[-1] == str(narration.resolve())
    assert "attached_pic" in args[4]
    assert kwargs["timeout"] == 10
    assert not kwargs.get("shell", False)


@pytest.mark.parametrize("failure", ["timeout", "malformed", "process"])
def test_probe_fails_cleanly_on_errors(media, monkeypatch, failure):
    _, narration, _, _, _ = media

    def run(args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return SimpleNamespace(returncode=1 if failure == "process" else 0, stdout="not JSON")

    monkeypatch.setattr(checks.subprocess, "run", run)
    with pytest.raises(checks.RecordingCheckError):
        checks.probe_media(narration, "ffprobe")


def _git(monkeypatch, root, *, head="a" * 40, branch="main", origin="a" * 40, dirty=""):
    responses = {
        ("rev-parse", "--show-toplevel"): str(root), ("rev-parse", "HEAD"): head,
        ("branch", "--show-current"): branch,
        ("rev-parse", "refs/remotes/origin/main"): origin,
        ("status", "--porcelain", "--untracked-files=no"): dirty,
    }
    commands = []

    def run(args, **kwargs):
        assert kwargs["timeout"] == 10
        assert kwargs["cwd"] == root
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout=responses[tuple(args[1:])])

    monkeypatch.setattr(checks.subprocess, "run", run)
    return commands


def test_revision_requires_explicit_reviewed_commit_and_clean_main(tmp_path, monkeypatch):
    commands = _git(monkeypatch, tmp_path)
    assert checks.verify_revision(tmp_path, "a" * 40) == "a" * 40
    assert commands[-1][-1] == "--untracked-files=no"
    # Existing untracked history is intentionally outside this check's scope.
    assert not any("clean" in command for command in commands)


@pytest.mark.parametrize("state", [
    {"head": "b" * 40}, {"branch": "review"}, {"branch": ""},
    {"origin": "b" * 40}, {"dirty": " M README.md"},
])
def test_revision_rejects_unreviewed_checkout(tmp_path, monkeypatch, state):
    _git(monkeypatch, tmp_path, **state)
    with pytest.raises(checks.RecordingCheckError):
        checks.verify_revision(tmp_path, "a" * 40)


def test_review_branch_override_still_requires_exact_reviewed_commit(tmp_path, monkeypatch):
    commands = _git(monkeypatch, tmp_path, branch="issue-25", origin="b" * 40)
    assert checks.verify_revision(tmp_path, "a" * 40, allow_branch=True) == "a" * 40
    assert ["git", "rev-parse", "refs/remotes/origin/main"] not in commands
    with pytest.raises(checks.RecordingCheckError, match="expected commit"):
        checks.verify_revision(tmp_path, "c" * 40, allow_branch=True)


@pytest.mark.parametrize("sha", ["", "HEAD", "origin/main", "abc123", "z" * 40])
def test_revision_never_selects_its_own_reviewed_sha(tmp_path, sha):
    with pytest.raises(checks.RecordingCheckError, match="40-character"):
        checks.verify_revision(tmp_path, sha)


def _dependencies(root):
    python = root / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    package = root / "node_modules" / "@modelcontextprotocol" / "server-filesystem"
    (package / "dist").mkdir(parents=True)
    (package / "dist" / "index.js").touch()
    (root / "package.json").write_text(json.dumps({
        "dependencies": {"@modelcontextprotocol/server-filesystem": "2026.8.31"},
    }))
    (root / "package-lock.json").write_text(json.dumps({"packages": {
        "node_modules/@modelcontextprotocol/server-filesystem": {"version": "2026.8.31"},
    }}))
    (package / "package.json").write_text('{"version":"2026.8.31"}')
    return package


def test_dependencies_validate_local_locked_server_without_installs(tmp_path, monkeypatch):
    _dependencies(tmp_path)
    commands = []
    monkeypatch.setattr(checks.shutil, "which", lambda name: f"C:/tools/{name}.exe")

    def run(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(returncode=0, stdout="ok")

    monkeypatch.setattr(checks.subprocess, "run", run)
    result = checks.verify_dependencies(tmp_path)
    assert result["python"].endswith("python.exe")
    assert len(commands) == 2
    assert commands[1][1] == "-c"
    assert "install" not in " ".join(" ".join(command) for command in commands)


@pytest.mark.parametrize("problem", ["python", "node", "entrypoint", "version", "json"])
def test_missing_or_mismatched_dependencies_fail_without_repair(tmp_path, monkeypatch, problem):
    package = _dependencies(tmp_path)
    monkeypatch.setattr(checks.shutil, "which", lambda name: None if problem == "node" else name)
    monkeypatch.setattr(checks.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stdout="ok"))
    if problem == "python":
        (tmp_path / ".venv" / "Scripts" / "python.exe").unlink()
    elif problem == "entrypoint":
        (package / "dist" / "index.js").unlink()
    elif problem == "version":
        (package / "package.json").write_text('{"version":"1.0.0"}')
    elif problem == "json":
        (tmp_path / "package-lock.json").write_text("bad")
    with pytest.raises(checks.RecordingCheckError):
        checks.verify_dependencies(tmp_path)
