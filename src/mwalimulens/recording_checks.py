"""Read-only prerequisite and result checks for the local recording helper.

These checks verify the take's inputs and machine-readable facts. They cannot
certify what a viewer sees or hears; a human must still watch the final take.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

NARRATION_SECONDS = 156.48
NARRATION_TOLERANCE = 0.75
RECORDING_MIN_SECONDS = 157.0
RECORDING_MAX_SECONDS = 165.0
_FILESYSTEM_PACKAGE = "@modelcontextprotocol/server-filesystem"
_SUPPORT_IDS = {"EV-004", "EV-007", "EV-009", "EV-011"}
_COUNTER_IDS = {"EV-008"}
_SAFE_TOOLS = {
    "get_learner_timeline", "get_competency_evidence", "flag_pattern_for_review",
    "read_text_file", "read_multiple_files", "list_directory", "search_files",
    "get_file_info", "list_allowed_directories",
}
_REQUIRED_CHECKS = {
    "education_evidence_retrieved", "borrowed_reference_read", "candidate_created",
    "human_gate_untouched", "model_tool_surface_safe", "real_qwen_evidence_passed",
    "challenge_evidence_passed", "evaluation_evidence_passed", "final_output_present",
}


class RecordingCheckError(RuntimeError):
    """A prerequisite or recorded-result check failed without changing evidence."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecordingCheckError(message)


def _run(args: list[str], *, cwd: Path | None = None, timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RecordingCheckError(f"Could not complete {Path(args[0]).name} check.") from exc
    _require(result.returncode == 0, f"{Path(args[0]).name} check failed; inspect it locally.")
    return result.stdout.strip()


def verify_revision(root: Path, expected_commit: str, allow_branch: bool = False) -> str:
    """Require a clean tracked checkout at the explicitly reviewed full commit.

    Normal takes require main and the locally fetched origin/main reference.
    The caller must fetch before this offline check. A maintainer can explicitly
    permit a review branch, but must still supply its reviewed exact commit.
    Untracked files, including historical evidence, are never removed or rejected.
    """
    _require(
        bool(re.fullmatch(r"[0-9a-fA-F]{40}", expected_commit)),
        "Supply the reviewed full 40-character commit SHA with --expected-commit.",
    )
    root = root.resolve()
    top = _run(["git", "rev-parse", "--show-toplevel"], cwd=root)
    _require(Path(top).resolve() == root, "Run the recorder from the repository root.")
    head = _run(["git", "rev-parse", "HEAD"], cwd=root)
    _require(head == expected_commit.lower(), "HEAD does not match the reviewed expected commit.")
    branch = _run(["git", "branch", "--show-current"], cwd=root)
    if not allow_branch:
        _require(branch == "main", "Final recording requires the main branch.")
        origin = _run(["git", "rev-parse", "refs/remotes/origin/main"], cwd=root)
        _require(head == origin, "main must match fetched origin/main before recording.")
    dirty = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root)
    _require(not dirty, "Tracked files have changes; review and commit them before recording.")
    return head


def _read_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordingCheckError(f"Cannot read valid JSON from {path.name}.") from exc
    _require(isinstance(data, dict), f"{path.name} must contain a JSON object.")
    return data


def verify_dependencies(root: Path) -> dict[str, str]:
    """Check the prepared Windows environment; never install or fetch anything."""
    root = root.resolve()
    python = root / ".venv" / "Scripts" / "python.exe"
    _require(python.is_file(), "Missing .venv/Scripts/python.exe; complete the README setup.")
    node, npm = shutil.which("node"), shutil.which("npm")
    _require(bool(node and npm), "Node.js and npm must already be installed and on PATH.")
    _run([str(node), "--version"])
    # Import the same application and clients as the demo, using its interpreter.
    # Also reject an editable install pointing at a different repository checkout.
    import_check = (
        "import pathlib,sys,pydantic,pydantic_ai,mcp,fastmcp,mwalimulens.demo_run; "
        "p=pathlib.Path(mwalimulens.demo_run.__file__).resolve(); "
        "sys.exit(0 if p.is_relative_to(pathlib.Path(sys.argv[1]).resolve()/'src') else 1)"
    )
    _run([str(python), "-c", import_check, str(root)], cwd=root, timeout=30)
    package_dir = root / "node_modules" / "@modelcontextprotocol" / "server-filesystem"
    _require((package_dir / "dist" / "index.js").is_file(),
             "Missing local Filesystem MCP entry point; complete npm ci before recording.")
    manifest = _read_object(root / "package.json")
    lock = _read_object(root / "package-lock.json")
    installed = _read_object(package_dir / "package.json")
    dependencies = manifest.get("dependencies")
    packages = lock.get("packages")
    _require(isinstance(dependencies, dict) and isinstance(packages, dict),
             "The borrowed Filesystem MCP dependency lock is incomplete.")
    expected = dependencies.get(_FILESYSTEM_PACKAGE)
    locked = packages.get(f"node_modules/{_FILESYSTEM_PACKAGE}")
    _require(isinstance(locked, dict) and isinstance(expected, str),
             "The borrowed Filesystem MCP dependency is missing from its lock.")
    _require(
        bool(re.fullmatch(r"\d+\.\d+\.\d+", expected))
        and installed.get("version") == locked.get("version") == expected,
        "Installed Filesystem MCP must match the exact package.json and lockfile version.",
    )
    return {"python": str(python), "node": str(node), "npm": str(npm)}


def _local_file(path: Path) -> Path:
    raw = str(path)
    _require(
        not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", raw)
        and not raw.startswith(("\\\\", "//")),
        "Media must be a local file, not a URL or network share.",
    )
    resolved = Path(path).resolve()
    _require(resolved.is_file(), "The local media file does not exist.")
    return resolved


def _outside_repository(path: Path, root: Path) -> Path:
    resolved = _local_file(path)
    _require(not resolved.is_relative_to(root.resolve()),
             "Keep narration and video files outside the repository.")
    return resolved


def probe_media(path: Path, ffprobe: str) -> dict[str, Any]:
    """Inspect a local file with a bounded, shell-free ffprobe invocation."""
    resolved = _local_file(path)
    output = _run([
        str(ffprobe), "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate:"
        "stream_disposition=attached_pic",
        "-of", "json", str(resolved),
    ])
    try:
        data = json.loads(output)
    except ValueError as exc:
        raise RecordingCheckError("ffprobe returned invalid JSON.") from exc
    _require(isinstance(data, dict), "ffprobe must return a metadata object.")
    return data


def _duration(metadata: dict[str, Any]) -> float:
    _require(isinstance(metadata, dict) and isinstance(metadata.get("format"), dict),
             "Media metadata has no format duration.")
    value = metadata["format"].get("duration")
    _require(not isinstance(value, bool), "Media duration must be a finite number.")
    try:
        duration = float(value)
    except (TypeError, ValueError) as exc:
        raise RecordingCheckError("Media duration must be a finite number.") from exc
    _require(math.isfinite(duration) and duration > 0,
             "Media duration must be a positive finite number.")
    return duration


def _streams(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    streams = metadata.get("streams")
    _require(isinstance(streams, list) and bool(streams)
             and all(isinstance(stream, dict) for stream in streams),
             "Media metadata has no valid streams.")
    return streams


def check_narration(path: Path, metadata: dict[str, Any], root: Path) -> float:
    """Check the supplied narration's duration and format without rewriting it."""
    resolved = _outside_repository(path, root)
    _require(resolved.suffix.lower() == ".mp3", "Narration must be the supplied MP3 file.")
    duration = _duration(metadata)
    _require(abs(duration - NARRATION_SECONDS) <= NARRATION_TOLERANCE,
             "Narration must be approximately 156.48 seconds; do not retime or replace it.")
    streams = _streams(metadata)
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    _require(len(audio) == 1 and audio[0].get("codec_name") == "mp3",
             "Narration must contain one MP3 audio stream.")
    _require(all(
        stream.get("codec_type") == "audio" or (
            stream.get("codec_type") == "video"
            and isinstance(stream.get("disposition"), dict)
            and stream["disposition"].get("attached_pic") == 1
        ) for stream in streams
    ), "Narration may contain cover art, but no moving video or other streams.")
    return duration


def verify_recording(path: Path, metadata: dict[str, Any], root: Path) -> float:
    """Check final MP4/MKV dimensions, frame rate, duration and audio presence."""
    resolved = _outside_repository(path, root)
    _require(resolved.suffix.lower() in {".mp4", ".mkv"},
             "The final recording must be an MP4 or MKV file.")
    duration = _duration(metadata)
    _require(duration < 180, "The recording must be strictly under three minutes.")
    _require(RECORDING_MIN_SECONDS <= duration <= RECORDING_MAX_SECONDS,
             "The continuous recording must be approximately 2:37–2:45.")
    streams = _streams(metadata)
    video = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    _require(len(video) == 1, "The recording must contain one video stream.")
    _require(video[0].get("width") == 1920 and video[0].get("height") == 1080,
             "The recording must be 1920 by 1080 pixels.")
    try:
        frame_rate = Fraction(str(video[0].get("avg_frame_rate")))
    except (ValueError, ZeroDivisionError) as exc:
        raise RecordingCheckError("The video frame rate is missing or invalid.") from exc
    _require(frame_rate == 30, "The recording must have a 30 fps video stream.")
    _require(video[0].get("codec_name") == "h264", "The video codec must be H.264.")
    _require(len(audio) == 1 and audio[0].get("codec_name") == "aac",
             "The recording must contain one AAC audio stream.")
    return duration


def validate_demo_report(report: dict[str, Any]) -> None:
    """Refuse a take unless its fresh demo report retains every recording boundary.

    This is consistency checking, not proof of provenance: the caller separately
    requires a new successful live demo process and fresh, unchanged report files.
    """
    _require(isinstance(report, dict), "Demo report must be a JSON object.")
    _require(report.get("status") == "pass" and report.get("error") is None,
             "The live demo did not pass cleanly.")
    _require(report.get("mode") == "fast_deterministic_demo",
             "The recording must identify the deterministic live MCP demo.")
    checks = report.get("checks")
    _require(isinstance(checks, dict) and _REQUIRED_CHECKS.issubset(checks)
             and all(value is True for value in checks.values()),
             "All live demo checks must explicitly pass.")
    learner = report.get("learner")
    _require(isinstance(learner, dict) and learner.get("synthetic") is True
             and learner.get("learner_id") == "L001"
             and report.get("competency_code") == "MATH-FRACTIONS",
             "The demo must use the expected synthetic learner and competency.")
    for name, expected in (
        ("pending_review_count", 1), ("teacher_review_count", 0), ("profile_update_count", 0),
    ):
        _require(type(report.get(name)) is int and report[name] == expected,
                 "The demo needs one pending candidate, zero decisions and zero profile updates.")
    candidate = report.get("candidate")
    _require(isinstance(candidate, dict), "The live demo has no candidate.")
    _require(candidate.get("status") == "pending_teacher_review"
             and candidate.get("learner_id") == "L001"
             and candidate.get("competency_code") == "MATH-FRACTIONS",
             "The candidate must remain pending teacher review for the expected scope.")
    for name in ("claim", "uncertainty", "suggested_teacher_question"):
        _require(isinstance(candidate.get(name), str) and bool(candidate[name].strip()),
                 f"The candidate must retain its {name}.")
    for name, expected in (
        ("supporting_evidence_ids", _SUPPORT_IDS), ("counter_evidence_ids", _COUNTER_IDS),
    ):
        ids = candidate.get(name)
        _require(isinstance(ids, list) and all(isinstance(item, str) for item in ids)
                 and set(ids) == expected and len(ids) == len(expected),
                 "The recorded candidate must retain its support and EV-008 counter-evidence.")
    evidence = report.get("evidence")
    _require(isinstance(evidence, list) and all(isinstance(row, dict) for row in evidence),
             "The report must show supporting evidence and counter-evidence.")
    for evidence_id in _SUPPORT_IDS | _COUNTER_IDS:
        rows = [row for row in evidence if row.get("evidence_id") == evidence_id]
        role = "supporting" if evidence_id in _SUPPORT_IDS else "counter"
        _require(len(rows) == 1 and rows[0].get("role") == role,
                 "Visible evidence must match the candidate's supporting and counter-evidence.")
        if role == "counter":
            _require(isinstance(rows[0].get("observation"), str)
                     and bool(rows[0]["observation"].strip()),
                     "The EV-008 counter-evidence observation must remain visible.")
    visible = report.get("visible_tools")
    _require(isinstance(visible, list) and all(isinstance(name, str) for name in visible)
             and set(visible) == _SAFE_TOOLS,
             "The model tool surface must retain only the existing read-only and candidate tools.")
    calls = report.get("tool_calls")
    _require(isinstance(calls, list) and len(calls) == 3
             and all(isinstance(call, dict) for call in calls),
             "The live demo must contain its three real MCP calls.")
    expected_tools = ["get_competency_evidence", "read_text_file", "flag_pattern_for_review"]
    for call, name in zip(calls, expected_tools, strict=True):
        _require(call.get("tool_name") == name and call.get("status") == "success"
                 and call.get("error") is None,
                 "The three expected live MCP calls must succeed in order.")
        if name == "read_text_file":
            _require(call.get("source") == "borrowed_mcp"
                     and call.get("toolset_id") == "borrowed-official-filesystem-mcp",
                     "read_text_file must come from the borrowed read-only Filesystem MCP.")
        else:
            _require(call.get("source") in (None, "education_mcp"),
                     "Education tools must come from the custom Education MCP.")
    _require(calls[2].get("output") == candidate,
             "The audited candidate must match the visible pending candidate.")
    qwen = report.get("real_qwen_validation")
    challenge = report.get("challenge_validation")
    _require(isinstance(qwen, dict) and qwen.get("status") == "pass"
             and qwen.get("model") == "qwen2.5:3b",
             "Separate committed real Qwen2.5 3B PASS evidence must remain visible.")
    _require(isinstance(challenge, dict) and challenge.get("status") == "pass",
             "Separate committed challenge PASS evidence must remain visible.")
    evaluation = report.get("evaluation_validation")
    _require(isinstance(evaluation, dict) and evaluation.get("status") == "pass"
             and isinstance(evaluation.get("summary"), dict),
             "The evaluation summary must remain visible.")
    expected_summary = {
        "current_pass": 11, "current_fail": 0, "current_regression_cases": 11,
        "historical_fail_preserved": 2, "historical_failure_cases": 2, "total_cases": 13,
    }
    _require(all(type(evaluation["summary"].get(key)) is int
                 and evaluation["summary"][key] == value
                 for key, value in expected_summary.items()),
             "Keep eleven current evaluation passes and both historical failures visible.")
    _require(isinstance(report.get("final_output"), str) and bool(report["final_output"].strip()),
             "The live demo must finish with its candidate review summary.")
