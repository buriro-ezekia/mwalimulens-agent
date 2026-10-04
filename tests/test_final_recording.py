"""Exercise the timed coordinator with no OBS, media generation or real-time waits."""

import subprocess
import time
from pathlib import Path

import pytest

from mwalimulens import final_recording
from mwalimulens.final_recording import (
    RecordingError,
    _demo_environment,
    _narration_progress,
    _recording_active,
    _terminate_owned_process,
    _verify_fresh_output,
    capture_take,
    run_preflight_demo,
)


class Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Obs:
    def __init__(self, clock, *, start_error=False, stop_error=False, bad_audio=False):
        self.clock = clock
        self.active = False
        self.start_error = start_error
        self.stop_error = stop_error
        self.bad_audio = bad_audio
        self.started = None
        self.stopped = None
        self.cleanup = False
        self.owns_recording = False

    def assert_unchanged(self, snapshot, budget_seconds=None):
        assert snapshot == "scene"

    def start_record(self):
        self.active = True
        self.owns_recording = True
        self.started = self.clock.now
        if self.start_error:
            raise RecordingError("Lost start acknowledgement")

    def restart_narration(self):
        pass

    def prepare_narration(self):
        self.cleanup = True

    def record_status(self):
        return {
            "outputActive": self.active,
            "outputPaused": False,
            "outputDuration": self.clock.now * 1000,
        }

    def media_status(self):
        if self.bad_audio and self.clock.now > 5:
            return {"mediaState": "OBS_MEDIA_STATE_PAUSED", "mediaCursor": 5000}
        return {
            "mediaState": (
                "OBS_MEDIA_STATE_ENDED" if self.clock.now >= 156.48 else "OBS_MEDIA_STATE_PLAYING"
            ),
            "mediaCursor": self.clock.now * 1000,
        }

    def stop_record(self):
        if self.stop_error:
            raise RecordingError("Lost OBS connection")
        self.active = False
        self.owns_recording = False
        self.stopped = self.clock.now
        return Path("take.mkv")


class Browser:
    url = "http://127.0.0.1:1234/test/live/"

    def __init__(self, clock, *, open_error=False, hidden=False):
        self.clock = clock
        self.open_error = open_error
        self.hidden = hidden
        self.opened = None
        self.ready = False

    def begin_stage(self):
        self.ready = False

    def set_clock(self, start):
        assert start == 0

    def publish(self, path):
        assert path.name == "mwalimulens_demo.html"

    def open(self):
        if self.open_error:
            raise RecordingError("Browser failed")
        self.opened = self.clock.now

    def check_health(self, *, require_active):
        assert require_active
        if self.hidden:
            raise RecordingError("Browser hidden")


class Live:
    def __init__(self, clock, browser, *, code=0, finish=15):
        self.clock, self.browser = clock, browser
        self.code, self.finish = code, finish
        self.returncode = None
        self.terminated = False
        self.launched = clock.now

    def poll(self):
        if self.clock.now >= self.finish:
            self.returncode = self.code
            self.browser.ready = self.code == 0
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -1

    def wait(self, timeout):
        return self.returncode


def take(tmp_path, *, obs_options=None, browser_options=None, live_options=None, validator=None):
    clock = Clock()
    obs = Obs(clock, **(obs_options or {}))
    browser = Browser(clock, **(browser_options or {}))
    live = None

    def factory(url):
        nonlocal live
        assert url == browser.url
        live = Live(clock, browser, **(live_options or {}))
        return live

    def run():
        return capture_take(
            obs=obs,
            browser=browser,
            snapshot="scene",
            root=tmp_path,
            live_factory=factory,
            validate_live=validator or (lambda: None),
            monotonic=clock.time,
            sleep=clock.sleep,
        )

    return run, obs, browser, lambda: live


def test_continuous_take_aligns_real_command_hold_and_stop(tmp_path):
    run, obs, browser, live = take(tmp_path)
    assert run() == Path("take.mkv")
    assert 2 <= live().launched < 2.3
    assert 22 <= browser.opened < 22.3
    assert obs.stopped == pytest.approx(159)
    assert obs.cleanup


@pytest.mark.parametrize(
    "options, message",
    [
        ({"live_options": {"code": 2}}, "live MCP command failed"),
        ({"live_options": {"finish": 40}}, "timing budget"),
        ({"browser_options": {"open_error": True}}, "Browser failed"),
        ({"browser_options": {"hidden": True}}, "Browser hidden"),
        ({"obs_options": {"bad_audio": True}}, "Narration is not playing"),
        ({"obs_options": {"start_error": True}}, "Lost start acknowledgement"),
    ],
)
def test_failure_stops_only_owned_take(tmp_path, options, message):
    run, obs, _browser, live = take(tmp_path, **options)
    with pytest.raises(RecordingError, match=message):
        run()
    assert not obs.active
    assert obs.stopped < 159
    assert obs.cleanup is not bool(options.get("obs_options", {}).get("start_error"))
    if live() and live().finish > obs.stopped:
        assert live().terminated


def test_stale_report_cannot_become_a_take(tmp_path):
    def stale():
        raise RecordingError("Stale report")

    run, obs, _browser, _live = take(tmp_path, validator=stale)
    with pytest.raises(RecordingError, match="Stale report"):
        run()
    assert obs.stopped < 159


def test_existing_recording_is_never_stopped(tmp_path):
    run, obs, _browser, _live = take(tmp_path)
    obs.active = True
    with pytest.raises(RecordingError, match="already recording"):
        run()
    assert obs.active
    assert obs.stopped is None


def test_stop_failure_demands_manual_stop_and_never_returns_success(tmp_path, capsys):
    run, obs, _browser, _live = take(tmp_path, obs_options={"stop_error": True})
    with pytest.raises(RecordingError, match="Lost OBS connection"):
        run()
    assert obs.active
    assert "Stop recording in OBS now" in capsys.readouterr().err


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "1000", None, True])
def test_nonfinite_record_and_media_times_are_rejected(value):
    with pytest.raises(RecordingError):
        _recording_active({"outputActive": True, "outputDuration": value}, 1)
    with pytest.raises(RecordingError):
        _narration_progress({"mediaState": "OBS_MEDIA_STATE_PLAYING", "mediaCursor": value}, 1)


def test_media_ending_early_is_not_success():
    with pytest.raises(RecordingError, match="too early"):
        _narration_progress({"mediaState": "OBS_MEDIA_STATE_ENDED"}, 25)


def test_secret_never_inherited_by_live_mcp_process(monkeypatch):
    monkeypatch.setenv("OBS_WEBSOCKET_PASSWORD", "private")
    monkeypatch.setenv("MWALIMULENS_RECORDING_URL", "stale")
    env = _demo_environment()
    assert "OBS_WEBSOCKET_PASSWORD" not in env
    assert "MWALIMULENS_RECORDING_URL" not in env
    assert _demo_environment("current")["MWALIMULENS_RECORDING_URL"] == "current"


def test_old_matching_video_cannot_be_claimed_as_current(tmp_path):
    import os

    output = tmp_path / "prior.mkv"
    output.write_bytes(b"test fixture, not a real video")
    old = time.time() - 60
    os.utime(output, (old, old))
    with pytest.raises(RecordingError, match="stale"):
        _verify_fresh_output(output, time.time_ns())


def test_fresh_nonempty_output_is_required(tmp_path):
    output = tmp_path / "new.mkv"
    start = time.time_ns()
    output.touch()
    with pytest.raises(RecordingError, match="empty"):
        _verify_fresh_output(output, start)
    output.write_bytes(b"test fixture, not a real video")
    _verify_fresh_output(output, start)


def test_accepted_audio_start_delay_can_finish_after_nominal_end(tmp_path, monkeypatch):
    run, obs, browser, _live = take(tmp_path)
    original_start = obs.start_record

    def delayed_start():
        original_start()
        obs.clock.sleep(0.5)

    def delayed_audio():
        obs.clock.sleep(0.5)

    def media():
        cursor = obs.clock.now - 1.0
        return {
            "mediaState": (
                "OBS_MEDIA_STATE_ENDED" if cursor >= 156.9 else "OBS_MEDIA_STATE_PLAYING"
            ),
            "mediaCursor": cursor * 1000,
        }

    monkeypatch.setattr(obs, "start_record", delayed_start)
    monkeypatch.setattr(obs, "restart_narration", delayed_audio)
    monkeypatch.setattr(obs, "media_status", media)
    assert run() == Path("take.mkv")
    assert obs.stopped == pytest.approx(159)
    assert browser.opened >= 22


def test_unresolved_delayed_start_requires_manual_stop(tmp_path, monkeypatch, capsys):
    run, obs, _browser, _live = take(tmp_path, obs_options={"stop_error": True})

    def delayed_start():
        obs.owns_recording = True
        # OBS accepted StartRecord but may still activate after this idle state.
        obs.active = False
        raise RecordingError("Start not confirmed")

    monkeypatch.setattr(obs, "start_record", delayed_start)
    with pytest.raises(RecordingError, match="Start not confirmed"):
        run()
    assert "Stop recording in OBS now" in capsys.readouterr().err
    assert not obs.cleanup


def test_rejected_start_does_not_stop_another_owners_recording(tmp_path, monkeypatch):
    run, obs, _browser, _live = take(tmp_path)

    def rejected_start():
        obs.active = True
        obs.owns_recording = False
        raise RecordingError("Another recording won the race")

    monkeypatch.setattr(obs, "start_record", rejected_start)
    with pytest.raises(RecordingError, match="won the race"):
        run()
    assert obs.active and obs.stopped is None
    assert not obs.cleanup


def test_preflight_timeout_cleans_up_owned_child(monkeypatch, tmp_path):
    class TimedOut:
        def wait(self, timeout):
            raise subprocess.TimeoutExpired("demo", timeout)

    process = TimedOut()
    cleaned = []
    monkeypatch.setattr(final_recording.subprocess, "Popen", lambda *a, **k: process)
    monkeypatch.setattr(final_recording, "_terminate_owned_process", cleaned.append)
    with pytest.raises(RecordingError, match="timed out"):
        run_preflight_demo(tmp_path)
    assert cleaned == [process]


def test_windows_cleanup_targets_only_owned_pid_and_descendants(monkeypatch):
    class Child:
        pid = 12345

        def poll(self):
            return None

        def wait(self, timeout):
            return 0

    calls = []
    monkeypatch.setattr(final_recording.sys, "platform", "win32")
    monkeypatch.setattr(final_recording.subprocess, "Popen", Child)
    monkeypatch.setattr(final_recording.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    _terminate_owned_process(Child())
    args, kwargs = calls[0]
    assert args[0][1:] == ["/PID", "12345", "/T", "/F"]
    assert kwargs["timeout"] == 5 and kwargs["check"] is True


def test_final_take_cannot_bypass_main_requirement(monkeypatch, capsys):
    monkeypatch.setattr(final_recording.sys, "platform", "win32")
    monkeypatch.setattr(final_recording, "verify_dependencies", lambda root: {})
    result = final_recording.main([
        "--allow-review-branch", "--expected-commit", "a" * 40, "--narration", "owner.mp3",
    ])
    assert result == 2
    assert "Review branches support --preflight-only" in capsys.readouterr().err
