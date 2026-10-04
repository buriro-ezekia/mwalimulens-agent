"""Windows recording coordinator; never manufactures footage or uploads a take."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mwalimulens.recording_checks import (
    RecordingCheckError,
    check_narration,
    probe_media,
    validate_demo_report,
    verify_dependencies,
    verify_recording,
    verify_revision,
)

ROOT = Path(__file__).resolve().parents[2]
LIVE_COMMAND = r".\.venv\Scripts\python.exe -m mwalimulens.demo_run"
NARRATION_SECONDS = 156.48
STOP_SECONDS = 159.0
LIVE_DEADLINE = 27.0
TIMELINE = (
    (0, "Recording + narration"),
    (2, "Execute the real fast MCP command"),
    (20, "Hold terminal PASS; browser follows after at least two seconds"),
    (31, "Evidence"),
    (43, "Counter-evidence: EV-008"),
    (58, "MCP activity: three audited calls"),
    (83, "Candidate and uncertainty"),
    (103, "Human gate: 1 pending / 0 decisions / 0 updates"),
    (119, "Separate real Qwen validation"),
    (141, "Limitation"),
    (156.48, "Narration ends; quiet hold"),
    (159, "Stop recording and measure the saved file"),
)


class RecordingError(RuntimeError):
    """An invalid or incomplete take, never a successful submission."""


def _report(root: Path) -> dict[str, Any]:
    try:
        report = json.loads((root / "runtime/demo_run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RecordingError("The current demo report is missing or unreadable.") from exc
    validate_demo_report(report)
    return report


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _demo_environment(url: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    # OBS credentials are not needed by the model, MCP servers or demo subprocess.
    env.pop("OBS_WEBSOCKET_PASSWORD", None)
    env.pop("MWALIMULENS_RECORDING_URL", None)
    if url is not None:
        env["MWALIMULENS_RECORDING_URL"] = url
    return env


def run_preflight_demo(root: Path) -> dict[str, Any]:
    process = subprocess.Popen(
        [str(root / ".venv/Scripts/python.exe"), "-m", "mwalimulens.demo_run", "--no-open"],
        cwd=root,
        env=_demo_environment(),
    )
    try:
        code = process.wait(timeout=60)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        _terminate_owned_process(process)
        raise RecordingError("Off-camera MCP preflight was interrupted or timed out.") from None
    if code:
        raise RecordingError("Off-camera fast MCP preflight failed. No recording was started.")
    return _report(root)


def _terminate_owned_process(process: Any) -> None:
    """Stop only our running child and its MCP descendants, never a name-wide process kill."""
    if process.poll() is not None:
        return
    if sys.platform == "win32" and isinstance(process, subprocess.Popen):
        killer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
        try:
            subprocess.run(
                [str(killer), "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=True,
            )
            process.wait(timeout=3)
            return
        except (OSError, subprocess.SubprocessError):
            print(
                "MCP process-tree cleanup failed; inspect local child processes.", file=sys.stderr
            )
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def _verify_fresh_output(path: Path, started_ns: int) -> None:
    try:
        stat = path.stat()
    except OSError as exc:
        raise RecordingError("OBS output is missing after recording stopped.") from exc
    if stat.st_size <= 0 or stat.st_mtime_ns < started_ns - 1_000_000_000:
        raise RecordingError("OBS returned an empty or stale recording; this take is invalid.")


def _recording_active(status: dict[str, Any], elapsed: float) -> None:
    if not status.get("outputActive") or status.get("outputPaused"):
        raise RecordingError("OBS recording stopped or paused during the take.")
    duration = status.get("outputDuration")
    if (
        type(duration) not in (float, int)
        or not math.isfinite(duration)
        or abs(duration / 1000 - elapsed) > 2
    ):
        raise RecordingError("OBS recording time drifted; this is not a verified continuous take.")


def _narration_progress(status: dict[str, Any], elapsed: float) -> bool:
    state = status.get("mediaState")
    if state == "OBS_MEDIA_STATE_ENDED":
        if elapsed < NARRATION_SECONDS - 1:
            raise RecordingError("Narration ended too early.")
        return True
    if state != "OBS_MEDIA_STATE_PLAYING":
        raise RecordingError("Narration is not playing; the take is invalid.")
    cursor = status.get("mediaCursor")
    if (
        type(cursor) not in (int, float)
        or not math.isfinite(cursor)
        or abs(cursor / 1000 - elapsed) > 2
    ):
        raise RecordingError("Narration stalled, restarted or drifted from the live take.")
    # Accepted startup latency and MP3 duration tolerance can extend playback
    # beyond 156.48s. Keep checking cursor drift; require ENDED after the 159s stop.
    return False


def capture_take(
    *,
    obs: Any,
    browser: Any,
    snapshot: Any,
    root: Path,
    live_factory: Callable[[str], Any],
    validate_live: Callable[[], None],
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Record one owned take; injectable clocks/adapters let tests exercise failure cleanup."""
    live = None
    start_attempted = False
    narration_attempted = False
    stopped = False
    browser_open = False
    demo_finished: float | None = None
    next_check = 0.0
    next_scene_check = 5.0
    cue_index = 0
    browser.begin_stage()  # A preflight tab can never acknowledge the live take.
    initial = obs.record_status()
    if initial.get("outputActive"):
        raise RecordingError("OBS is already recording. The launcher will not stop another take.")
    obs.assert_unchanged(snapshot)
    try:
        start_attempted = True  # Even a lost StartRecord response needs cleanup.
        obs.start_record()
        status = obs.record_status()
        duration_ms = status.get("outputDuration")
        if (
            type(duration_ms) not in (int, float)
            or not math.isfinite(duration_ms)
            or not 0 <= duration_ms <= 1500
        ):
            raise RecordingError("OBS recording start could not be aligned to the timeline.")
        initial_duration = duration_ms / 1000
        start = monotonic() - initial_duration
        _recording_active(status, initial_duration)
        narration_attempted = True
        obs.restart_narration()
        if monotonic() - start > 1.5:
            raise RecordingError("OBS start was too slow to align narration with the live command.")
        browser.set_clock(start)
        while True:
            elapsed = monotonic() - start
            if elapsed >= STOP_SECONDS:
                break
            while cue_index < len(TIMELINE) and elapsed >= TIMELINE[cue_index][0]:
                print(f"[{elapsed:06.2f}s] {TIMELINE[cue_index][1]}", flush=True)
                cue_index += 1
            if live is None and elapsed >= 2:
                if elapsed > 3:
                    raise RecordingError("The live command missed its start window.")
                print(f"\nLIVE COMMAND\n{LIVE_COMMAND}\n", flush=True)
                live = live_factory(browser.url)
            if live is not None and demo_finished is None and live.poll() is not None:
                if live.returncode != 0:
                    raise RecordingError("The live MCP command failed. This take is invalid.")
                validate_live()
                if not browser.ready:
                    raise RecordingError("The live demo did not notify the recording browser.")
                demo_finished = elapsed
            if demo_finished is None and elapsed >= LIVE_DEADLINE:
                raise RecordingError("Live MCP run exceeded its timing budget; stop and retry.")
            if demo_finished is not None and not browser_open:
                if elapsed >= max(22.0, demo_finished + 2.0):
                    browser.publish(root / "runtime/mwalimulens_demo.html")
                    browser.open()
                    browser_open = True
            if elapsed >= 31:
                if not browser_open:
                    raise RecordingError(
                        "The live browser was not opened for the evidence section."
                    )
                browser.check_health(require_active=True)
            if elapsed >= next_check:
                _recording_active(obs.record_status(), monotonic() - start)
                _narration_progress(obs.media_status(), monotonic() - start)
                next_check = elapsed + 1
            if elapsed >= next_scene_check:
                obs.assert_unchanged(snapshot, budget_seconds=1)
                next_scene_check = elapsed + 5
            sleep(min(0.2, max(0, STOP_SECONDS - (monotonic() - start))))

        if demo_finished is None or not browser_open:
            raise RecordingError("The take did not complete the live workflow.")
        # Stop at the deadline before running slower final validation requests.
        output = Path(obs.stop_record())
        stopped = True
        if obs.record_status().get("outputActive"):
            raise RecordingError("OBS did not confirm recording stop. Stop it manually now.")
        browser.check_health(require_active=True)
        if not _narration_progress(obs.media_status(), monotonic() - start):
            raise RecordingError("Narration has not finished; this take is invalid.")
        obs.assert_unchanged(snapshot)
        return output
    finally:
        if start_attempted and not stopped and obs.owns_recording:
            try:
                # An idle poll cannot disprove a delayed StartRecord. Require a
                # confirmed stop, or explicitly ask the owner to check OBS.
                partial = obs.stop_record()
                print(f"INVALID/PARTIAL TAKE retained at: {partial}", flush=True)
            except Exception:
                print(
                    "CRITICAL: OBS stop could not be confirmed. Stop recording in OBS now. "
                    "No valid video is claimed.",
                    file=sys.stderr,
                    flush=True,
                )
        if live is not None:
            try:
                _terminate_owned_process(live)
            except (OSError, subprocess.SubprocessError):
                print("MCP child cleanup failed; inspect local processes.", file=sys.stderr)
        if narration_attempted:
            try:
                obs.prepare_narration()
            except Exception:
                print("Narration cleanup could not be confirmed; check OBS.", file=sys.stderr)


def _obs_executable(value: str | None) -> Path:
    if value:
        candidate = Path(value).expanduser().resolve()
    else:
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidate = program_files / "obs-studio/bin/64bit/obs64.exe"
    if not candidate.is_file() or candidate.name.lower() != "obs64.exe":
        raise RecordingCheckError("OBS Studio was not found; install it or supply --obs-exe.")
    return candidate


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--narration", type=Path, help="Owner's final 156.48-second MP3, outside repo"
    )
    parser.add_argument("--expected-commit", help="Full reviewed main SHA; required except dry-run")
    parser.add_argument("--allow-review-branch", action="store_true")
    parser.add_argument("--obs-exe")
    parser.add_argument("--obs-port", type=int, default=4455)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--microphone", help="Explicit OBS microphone input to keep audible")
    parser.add_argument(
        "--dry-run", action="store_true", help="Real MCP preflight + plan; no OBS/media"
    )
    parser.add_argument(
        "--preflight-only", action="store_true", help="Check prepared OBS; no recording"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    obs = None
    browser = None
    try:
        if sys.platform != "win32":
            raise RecordingCheckError("This recording launcher requires Windows.")
        verify_dependencies(ROOT)
        if args.dry_run:
            print(
                "DRY RUN: real off-camera MCP preflight; no OBS, browser or media recording.",
                flush=True,
            )
            run_preflight_demo(ROOT)
            for seconds, cue in TIMELINE:
                print(f"{seconds:6.2f}s  {cue}")
            print(
                "DRY RUN COMPLETE. Narration, OBS, browser capture and video duration are "
                "NOT validated. No recording was created."
            )
            return 0
        if not args.expected_commit or args.narration is None:
            raise RecordingCheckError(
                "Supply --expected-commit and --narration (see recording guide)."
            )
        if args.allow_review_branch and not args.preflight_only:
            raise RecordingCheckError("Review branches support --preflight-only, not final takes.")
        verify_revision(ROOT, args.expected_commit, args.allow_review_branch)
        _obs_executable(args.obs_exe)
        ffprobe = shutil.which(args.ffprobe)
        if not ffprobe:
            raise RecordingCheckError(
                "ffprobe is missing; install FFmpeg or supply --ffprobe PATH."
            )
        narration = args.narration.expanduser().resolve()
        narration_seconds = check_narration(narration, probe_media(narration, ffprobe), ROOT)
        print(
            f"Narration checked: {narration_seconds:.2f} seconds. No asset is copied to the repo."
        )

        from mwalimulens.recording_browser import RecordingBrowser
        from mwalimulens.recording_obs import ObsController

        browser = RecordingBrowser(ROOT / "runtime")
        browser.begin_stage()
        run_preflight_demo(ROOT)
        browser.publish(ROOT / "runtime/mwalimulens_demo.html")
        browser.open()
        browser.wait_loaded(timeout=15)
        password = os.environ.get("OBS_WEBSOCKET_PASSWORD")
        if password is None:
            password = getpass.getpass("OBS WebSocket password (hidden, never saved): ")
        obs = ObsController(port=args.obs_port, password=password)
        del password
        snapshot = obs.preflight(
            repository=ROOT,
            narration_path=narration,
            microphone_name=args.microphone,
        )
        print(f"OBS output folder: {snapshot.record_directory}")
        free = shutil.disk_usage(snapshot.record_directory).free
        if free < 2 * 1024**3:
            raise RecordingCheckError("Allow at least 2 GiB free in the recording output folder.")
        if args.preflight_only:
            print(
                "PREFLIGHT COMPLETE; no recording started. Visually check browser and OBS framing."
            )
            return 0
        obs.prepare_narration()

        print(
            "\nCheck OBS preview shows the correct display, whole terminal and browser at 1080p.\n"
            "Use the final male narration; mute your microphone unless explicitly requested.\n"
            "Put OBS/notes outside capture, return to this terminal, and leave it in front.\n"
            "The take is live and unedited. A failed take is retained but never marked valid."
        )
        if (
            input("Type RECORD to start the countdown, or anything else to cancel: ").strip()
            != "RECORD"
        ):
            print("Cancelled. No recording started.")
            return 0
        for seconds in (5, 4, 3, 2, 1):
            print(f"Recording in {seconds}...", flush=True)
            time.sleep(1)

        before = _digest(ROOT / "runtime/demo_run.json")

        def validate_live() -> None:
            if _digest(ROOT / "runtime/demo_run.json") == before:
                raise RecordingError("The live demo report is stale.")
            _report(ROOT)

        def launch_live(url: str) -> subprocess.Popen:
            return subprocess.Popen(
                [str(ROOT / ".venv/Scripts/python.exe"), "-m", "mwalimulens.demo_run"],
                cwd=ROOT,
                env=_demo_environment(url),
            )

        started_ns = time.time_ns()
        output = capture_take(
            obs=obs,
            browser=browser,
            snapshot=snapshot,
            root=ROOT,
            live_factory=launch_live,
            validate_live=validate_live,
        )
        print(f"Saved take (validation pending): {output}", flush=True)
        _verify_fresh_output(output, started_ns)
        duration = verify_recording(output, probe_media(output, ffprobe), ROOT)
        print(f"\nAUTOMATED CHECKS PASSED\nRecording: {output}\nMeasured duration: {duration:.2f}s")
        print(
            "Under 3:00. Watch the WHOLE take to check framing, sound and visible evidence. "
            "No upload was performed; repository video status remains Ready to record."
        )
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        # SDK errors must not leak credentials; adapters expose sanitised diagnostics.
        message = (
            str(exc)
            if isinstance(exc, (RecordingError, RecordingCheckError))
            else type(exc).__name__
        )
        if type(exc).__name__ in {"ObsError", "RecordingBrowserError"}:
            message = str(exc)
        print(f"RECORDING FAILED: {message}. No valid final video is claimed.", file=sys.stderr)
        return 2
    finally:
        if obs is not None:
            try:
                obs.close()
            except Exception:
                print("OBS disconnect cleanup failed; inspect OBS locally.", file=sys.stderr)
        if browser is not None:
            try:
                browser.close()
            except Exception:
                print("Browser service cleanup failed; close this launcher.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
