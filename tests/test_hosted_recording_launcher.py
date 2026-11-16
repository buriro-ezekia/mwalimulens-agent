"""Preflight and mocked capture regressions, not Windows/OBS video acceptance."""

import importlib.util
import json
import threading
import wave
from contextlib import contextmanager, nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "record-hosted-review.py"
spec = importlib.util.spec_from_file_location("hosted_recording", SCRIPT)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1:8081",
        "http://localhost:8081",
        "http://example.org:8081",
        "http://127.0.0.1:8081@evil.org",
        "http://127.0.0.1:8081/?token=x",
        "http://127.0.0.1:8081/#x",
        "http://127.0.0.1:8081/other",
        "http://127.0.0.1",
    ],
)
def test_only_explicit_loopback_root(url):
    with pytest.raises(ValueError):
        launcher.local_url(url)


def test_loopback_url():
    assert launcher.local_url("http://127.0.0.1:8081/") == "http://127.0.0.1:8081"


def page_fixture(label="Authored demonstration", ident="demo-one", counts=None):
    code = SimpleNamespace(inner_text=lambda: ident)
    identity = SimpleNamespace(
        inner_text=lambda: label,
        locator=lambda _: SimpleNamespace(first=code),
    )
    metrics = SimpleNamespace(all_text_contents=lambda: counts or ["1", "0", "0"])
    return SimpleNamespace(
        locator=lambda selector: identity if selector == ".case-identity" else metrics
    )


def test_exact_identity_and_counts():
    assert launcher.assert_case(page_fixture(), ["1", "0", "0"]) == "demo-one"
    with pytest.raises(RuntimeError):
        launcher.assert_case(page_fixture(), ["0", "1", "1"])
    with pytest.raises(RuntimeError):
        launcher.assert_case(page_fixture(), ["1", "0", "0"], "demo-other")


@pytest.mark.parametrize(
    "label,ident",
    [
        ("Qwen result", "qwen-one"),
        ("Authored demonstration", "qwen-one"),
    ],
)
def test_refuses_non_authored_case(label, ident):
    with pytest.raises(RuntimeError):
        launcher.assert_case(page_fixture(label, ident), ["1", "0", "0"])


def test_windows_only_before_browser_or_obs(monkeypatch):
    monkeypatch.setattr("sys.argv", [str(SCRIPT)])
    if launcher.os.name == "nt":
        return
    with pytest.raises(RuntimeError, match="Windows laptop"):
        launcher.main()


class FakeObs:
    """OBS-shaped responses including an unmuted input in an unrelated scene."""

    def __init__(self):
        self.original = {
            "Desktop Audio": False,
            "Microphone": False,
            "Old scene mic": False,
            "Already muted": True,
            "Disabled mic": False,
        }
        self.muted = dict(self.original)
        self.calls = []
        self.active = False
        self.fail_stop = False
        self.fail_mute = None
        self.closed = False
        self.captures = [
            dict(sourceName="Chrome", inputKind="window_capture", sceneItemEnabled=True),
            dict(sourceName="Microphone", inputKind="wasapi_input_capture", sceneItemEnabled=True),
            dict(
                sourceName="Already muted", inputKind="wasapi_input_capture", sceneItemEnabled=True
            ),
            dict(
                sourceName="Disabled mic", inputKind="wasapi_input_capture", sceneItemEnabled=False
            ),
        ]

    def _request(self, method, **data):
        self.calls.append((method, data))
        if method == "GetSpecialInputs":
            return dict(desktop1="Desktop Audio", desktop2=None, mic1="Microphone")
        if method == "GetInputMute":
            return {"inputMuted": self.muted[data["inputName"]]}
        if method == "SetInputMute":
            name = data["inputName"]
            self.muted[name] = data["inputMuted"]
            if self.fail_mute == (name, data["inputMuted"]):
                raise RuntimeError("Simulated lost response after mute changed")
            return {}
        if method == "GetCurrentProgramScene":
            return {"currentProgramSceneName": launcher.SCENE}
        if method == "GetRecordStatus":
            return {"outputActive": self.active}
        if method == "GetStreamStatus":
            return {"outputActive": False}
        if method == "GetSceneItemList":
            return {"sceneItems": self.captures}
        if method == "StartRecord":
            assert self.muted["Desktop Audio"] is True
            assert self.muted["Microphone"] is True
            self.active = True
            return {}
        if method == "StopRecord":
            if self.fail_stop:
                raise RuntimeError("Simulated OBS stop failure")
            self.active = False
            return {"outputPath": "take.mkv"}
        if method in {
            "CreateInput",
            "RemoveInput",
            "TriggerMediaInputAction",
            "SetInputSettings",
            "SetInputAudioTracks",
            "SetInputAudioMonitorType",
        }:
            return {}
        raise AssertionError(f"Unexpected OBS request: {method}")

    def close(self):
        self.closed = True


def test_mute_scopes_active_scene_and_global_audio_and_deduplicates():
    obs = FakeObs()
    snapshot = {}
    launcher.mute_recording_audio(obs._request, obs.captures, snapshot)
    assert snapshot == {
        "Already muted": True,
        "Desktop Audio": False,
        "Microphone": False,
    }
    assert obs.muted["Old scene mic"] is False
    assert obs.muted["Disabled mic"] is False
    changes = [data["inputName"] for name, data in obs.calls if name == "SetInputMute"]
    assert sorted(changes) == ["Desktop Audio", "Microphone"]
    assert launcher.restore_recording_audio(obs._request, snapshot) == []
    assert obs.muted == obs.original


def test_no_audio_inputs_requires_no_mute_changes():
    calls = []

    def request(method, **data):
        calls.append(method)
        assert method == "GetSpecialInputs"
        return dict(desktop1=None, mic1=None)

    snapshot = {}
    launcher.mute_recording_audio(request, [], snapshot)
    assert snapshot == {}
    assert calls == ["GetSpecialInputs"]


def test_invalid_mute_response_fails_before_any_mutation():
    obs = FakeObs()

    def request(method, **data):
        if method == "GetInputMute" and data["inputName"] == "Microphone":
            return {"inputMuted": "false"}
        return obs._request(method, **data)

    snapshot = {}
    with pytest.raises(RuntimeError, match="valid mute state"):
        launcher.mute_recording_audio(request, obs.captures, snapshot)
    assert snapshot == {}
    assert obs.muted == obs.original
    assert not any(method == "SetInputMute" for method, _ in obs.calls)


def test_partial_mute_failure_retains_snapshot_for_restoration():
    obs = FakeObs()
    obs.fail_mute = ("Microphone", True)
    snapshot = {}
    with pytest.raises(RuntimeError, match="lost response"):
        launcher.mute_recording_audio(obs._request, obs.captures, snapshot)
    assert launcher.restore_recording_audio(obs._request, snapshot) == []
    assert obs.muted == obs.original


def test_restoration_failure_reports_input_and_still_restores_others():
    obs = FakeObs()
    snapshot = {}
    launcher.mute_recording_audio(obs._request, obs.captures, snapshot)
    obs.fail_mute = ("Desktop Audio", False)
    assert launcher.restore_recording_audio(obs._request, snapshot) == ["Desktop Audio"]
    assert obs.muted["Microphone"] is False


class FakePage:
    """Model the required browser transitions without real network or OBS."""

    def __init__(self):
        self.counts = ["1", "0", "0"]
        self.preview = False
        self.confirmed = False
        self.reopened = False
        self.fail_preview = False
        self.clicks = []
        self.navigations = []
        self.fail_navigation = False
        self.url = "about:blank"

    def set_default_timeout(self, *args):
        pass

    def set_default_navigation_timeout(self, *args):
        pass

    def route(self, *args):
        pass

    def goto(self, url, **kwargs):
        self.navigations.append((url, kwargs))
        if self.fail_navigation:
            raise TimeoutError("Simulated page timeout")
        self.url = url
        return SimpleNamespace(status=200)

    def bring_to_front(self):
        pass

    def wait_for_timeout(self, *args):
        pass

    def locator(self, selector):
        if selector == ".case-identity":
            return page_fixture().locator(selector)
        if selector == ".metric strong":
            return SimpleNamespace(all_text_contents=lambda: self.counts)
        return SimpleNamespace(fill=lambda text: None, scroll_into_view_if_needed=lambda: None)

    def get_by_role(self, role, name=None, **kwargs):
        if role == "row":
            return SimpleNamespace(filter=lambda **kwargs: self)

        def click():
            self.clicks.append(name)
            if name == "Review decision":
                if self.fail_preview:
                    raise RuntimeError("Simulated browser failure")
                self.preview = True
            elif name == "Confirm simulated decision":
                assert self.preview is True
                self.confirmed = True
                self.counts = ["0", "1", "1"]
            elif name == "Open demonstration":
                assert self.confirmed is True
                self.reopened = True

        return SimpleNamespace(
            click=click, check=lambda: None, wait_for=lambda **kwargs: None, is_enabled=lambda: True
        )

    def get_by_text(self, *args, **kwargs):
        assert self.preview is True
        assert self.confirmed is False
        return SimpleNamespace(wait_for=lambda: None)

    def inner_text(self, selector):
        assert self.reopened is True
        return launcher.REASON + "\n" + launcher.WORDING


@pytest.fixture
def fake_capture(monkeypatch, tmp_path):
    page = FakePage()
    obs = FakeObs()
    clip = tmp_path / "voice.wav"
    with wave.open(str(clip), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8)
    browser = SimpleNamespace(
        new_context=lambda **kwargs: SimpleNamespace(new_page=lambda: page),
        close=lambda: None,
    )
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kwargs: browser))
    monkeypatch.setitem(
        __import__("sys").modules,
        "playwright.sync_api",
        SimpleNamespace(sync_playwright=lambda: nullcontext(playwright)),
    )
    monkeypatch.setattr(launcher, "os", SimpleNamespace(name="nt", startfile=lambda path: None))
    monkeypatch.setattr(launcher, "make_audio", lambda root, **kwargs: [clip] * 6)
    monkeypatch.setattr(launcher, "check_portal", lambda base: None)
    monkeypatch.setattr(launcher, "ObsController", lambda **kwargs: obs)
    monkeypatch.setattr(launcher.getpass, "getpass", lambda prompt: "test-only")
    monkeypatch.setattr("builtins.input", lambda prompt: "RECORD")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--record"])
    return page, obs


def test_main_records_with_active_audio_and_restores_it(fake_capture):
    page, obs = fake_capture
    launcher.main()
    assert page.reopened is True
    assert page.counts == ["0", "1", "1"]
    assert obs.active is False
    assert obs.closed is True
    assert obs.muted == obs.original
    methods = [method for method, _ in obs.calls]
    assert methods.count("StartRecord") == 1
    assert methods.count("StopRecord") == 1
    assert methods.index("StopRecord") < len(methods) - 1


def test_main_cancel_does_not_change_audio_or_confirm(fake_capture, monkeypatch):
    page, obs = fake_capture
    monkeypatch.setattr("builtins.input", lambda prompt: "CANCEL")
    launcher.main()
    assert page.confirmed is False
    assert obs.muted == obs.original
    assert not any(method in {"StartRecord", "SetInputMute"} for method, _ in obs.calls)


def test_main_browser_failure_stops_take_and_restores_audio(fake_capture):
    page, obs = fake_capture
    page.fail_preview = True
    with pytest.raises(RuntimeError, match="browser failure"):
        launcher.main()
    assert page.confirmed is False
    assert obs.active is False
    assert obs.muted == obs.original


def test_main_partial_mute_failure_never_starts_take(fake_capture):
    page, obs = fake_capture
    obs.fail_mute = ("Microphone", True)
    with pytest.raises(RuntimeError, match="lost response"):
        launcher.main()
    assert page.confirmed is False
    assert obs.muted == obs.original
    assert not any(method == "StartRecord" for method, _ in obs.calls)


def test_main_stop_failure_keeps_audio_muted_and_reports_recovery(fake_capture, capsys):
    page, obs = fake_capture
    obs.fail_stop = True
    with pytest.raises(RuntimeError, match="stop failure"):
        launcher.main()
    assert page.reopened is True
    assert obs.active is True
    assert obs.muted["Desktop Audio"] is True
    assert obs.muted["Microphone"] is True
    assert "Audio remains muted" in capsys.readouterr().out


def inventory_fixture():
    return {
        "edition": "Core",
        "version": "7",
        "voices": [
            dict(name="Microsoft George", gender="Male", culture="en-GB", enabled=True),
            dict(name="Microsoft David Desktop", gender="Male", culture="en-US", enabled=True),
            dict(name="Microsoft Hazel", gender="Female", culture="en-GB", enabled=True),
        ],
    }


def write_voice_clips(root, name):
    (root / "selected-voice.txt").write_text(name, encoding="utf-8-sig")
    for i in range(len(launcher.SPEECH)):
        with wave.open(str(root / f"{i}.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\1\0" * 16)


def test_audio_generation_selects_exact_voice_with_no_hint_fallback(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(launcher, "voice_inventory", lambda *args: inventory_fixture())

    def run(args, **kwargs):
        calls.append((args, kwargs))
        script = Path(args[3]).read_text()
        assert "$voice.SelectVoice($VoiceName)" in script
        assert "SelectVoiceByHints" not in script
        assert "$_.Enabled" in script
        assert "finally { $voice.Dispose() }" in script
        write_voice_clips(tmp_path, args[-1])

    monkeypatch.setattr(launcher.subprocess, "run", run)
    result = launcher.make_audio(tmp_path)
    assert calls[0][0][-1] == "Microsoft George"
    assert calls[0][1]["check"] is True
    assert calls[0][1]["timeout"] == 180
    assert len(result) == len(launcher.SPEECH)


def test_voice_name_is_passed_as_data_not_powershell_source(monkeypatch, tmp_path):
    name = 'A voice; $(not-a-command) "with quotes"'
    calls = []
    inventory = inventory_fixture()
    inventory["voices"][0]["name"] = name
    monkeypatch.setattr(launcher, "voice_inventory", lambda *args: inventory)

    def run(args, **kwargs):
        calls.append(args)
        write_voice_clips(tmp_path, name)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    launcher.make_audio(tmp_path, voice_name=name)
    assert calls[0][-1] == name
    assert name not in (tmp_path / "voice.ps1").read_text()


def test_disabled_george_is_not_chosen_over_usable_david():
    inventory = inventory_fixture()
    inventory["voices"][0]["enabled"] = False
    assert launcher.voice_candidates(inventory, "auto") == ["Microsoft David Desktop"]
    with pytest.raises(RuntimeError, match="not enabled"):
        launcher.voice_candidates(inventory, "Microsoft George")


def test_automatic_selection_never_substitutes_female_or_non_english_voice():
    inventory = inventory_fixture()
    inventory["voices"] = [
        inventory["voices"][2],
        dict(name="French", gender="Male", culture="fr-FR", enabled=True),
    ]
    with pytest.raises(RuntimeError, match="No enabled English male"):
        launcher.voice_candidates(inventory, "auto")


def test_same_custom_powershell_is_used_for_inventory_and_generation(monkeypatch, tmp_path):
    calls = []
    host = r"C:\Program Files\PowerShell\7\pwsh.exe"

    def run(args, **kwargs):
        calls.append(args)
        if Path(args[3]).name == "voice-inventory.ps1":
            return SimpleNamespace(stdout=json.dumps(inventory_fixture()))
        write_voice_clips(tmp_path, args[-1])

    monkeypatch.setattr(launcher.subprocess, "run", run)
    launcher.make_audio(tmp_path, powershell=host)
    assert [args[0] for args in calls] == [host, host]


def test_auto_falls_back_after_synthesis_failure_without_mixing_clips(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "voice_inventory", lambda *args: inventory_fixture())
    attempts = []

    def run(args, **kwargs):
        name = args[-1]
        attempts.append(name)
        if name == "Microsoft George":
            (tmp_path / "0.wav").write_bytes(b"incomplete")
            raise launcher.subprocess.CalledProcessError(1, args)
        assert not (tmp_path / "0.wav").exists()
        write_voice_clips(tmp_path, name)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    clips = launcher.make_audio(tmp_path)
    assert attempts == ["Microsoft George", "Microsoft David Desktop"]
    assert len(clips) == 6


def test_explicit_voice_does_not_fall_back_after_synthesis_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "voice_inventory", lambda *args: inventory_fixture())
    attempts = []

    def run(args, **kwargs):
        attempts.append(args[-1])
        raise launcher.subprocess.CalledProcessError(1, args, stderr="Voice engine unavailable")

    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="Voice engine unavailable"):
        launcher.make_audio(tmp_path, voice_name="Microsoft George")
    assert attempts == ["Microsoft George"]


@pytest.mark.parametrize(
    "data",
    [
        {"voices": ["bad"]},
        {"voices": [dict(name="David", gender="Male", culture="en-US", enabled="false")]},
    ],
)
def test_invalid_inventory_is_not_used(monkeypatch, tmp_path, data):
    monkeypatch.setattr(
        launcher.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(data))
    )
    with pytest.raises(RuntimeError, match="invalid voice"):
        launcher.voice_inventory(tmp_path, "powershell.exe")


def test_empty_audio_is_not_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "voice_inventory", lambda *args: inventory_fixture())

    def run(args, **kwargs):
        write_voice_clips(tmp_path, args[-1])
        with wave.open(str(tmp_path / "5.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="empty audio"):
        launcher.make_audio(tmp_path, voice_name="Microsoft George")


def test_list_voices_does_not_synthesise_or_start_obs(fake_capture, monkeypatch, capsys):
    page, obs = fake_capture
    monkeypatch.setattr(launcher, "voice_inventory", lambda *args: inventory_fixture())
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--list-voices", "--powershell", "pwsh.exe"])
    monkeypatch.setattr(launcher, "make_audio", lambda *args, **kwargs: pytest.fail("No synthesis"))
    launcher.main()
    assert '"enabled": true' in capsys.readouterr().out
    assert obs.calls == []
    assert page.confirmed is False


def test_cli_voice_reaches_synthesizer(fake_capture, monkeypatch):
    selected = []
    original = launcher.make_audio

    def audio(root, **kwargs):
        selected.append(kwargs["voice_name"])
        return original(root, **kwargs)

    monkeypatch.setattr(launcher, "make_audio", audio)
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--record", "--voice", "Microsoft Mark"])
    launcher.main()
    assert selected == ["Microsoft Mark"]


def test_voice_generation_failure_stops_before_browser_or_case_creation(fake_capture, monkeypatch):
    page, obs = fake_capture

    def audio(*args, **kwargs):
        raise launcher.subprocess.CalledProcessError(1, "powershell.exe")

    monkeypatch.setattr(launcher, "make_audio", audio)
    with pytest.raises(launcher.subprocess.CalledProcessError):
        launcher.main()
    assert obs.calls == []
    assert page.confirmed is False


@contextmanager
def catalogue_server(status=200, body=None, headers=()):
    payload = (
        body
        if body is not None
        else (
            b"<title>MwalimuLens | Demonstration cases</title>"
            b"<h1>Demonstration cases</h1><button>New candidate demonstration</button>"
        )
    )
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_catalogue_probe_bypasses_proxy_and_makes_only_get(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("no_proxy", "")
    with catalogue_server() as (base, requests):
        launcher.check_portal(base)
        assert requests == ["/demos"]


@pytest.mark.parametrize("status", [403, 500])
def test_http_failure_reports_specific_status(status):
    with catalogue_server(status=status) as (base, requests):
        with pytest.raises(RuntimeError, match=f"HTTP {status}") as error:
            launcher.check_portal(base)
        if status == 403:
            assert "--browser-port" in str(error.value)
        assert requests == ["/demos"]


def test_probe_does_not_follow_redirects():
    with catalogue_server(status=302, headers=(("Location", "/elsewhere"),)) as (base, requests):
        with pytest.raises(RuntimeError, match="HTTP 302"):
            launcher.check_portal(base)
        assert requests == ["/demos"]


def test_probe_refuses_unrelated_application():
    with catalogue_server(body=b"<h1>Another app</h1>") as (base, requests):
        with pytest.raises(RuntimeError, match="did not return the MwalimuLens"):
            launcher.check_portal(base)
        assert requests == ["/demos"]


def test_probe_timeout_has_tunnel_recovery_message(monkeypatch):
    def open_url(*args, **kwargs):
        assert kwargs["timeout"] == 5
        raise URLError("timed out")

    monkeypatch.setattr(launcher, "build_opener", lambda *args: SimpleNamespace(open=open_url))
    with pytest.raises(RuntimeError, match="Reconnect the private SSH tunnel"):
        launcher.check_portal("http://127.0.0.1:8081")


def test_real_catalogue_probe_does_not_change_saved_state(tmp_path):
    from mwalimulens import teacher_portal

    case = teacher_portal.demonstration_case(tmp_path, scenario="candidate")
    portal = teacher_portal.TeacherPortal(tmp_path, case)
    server = ThreadingHTTPServer(("127.0.0.1", 0), teacher_portal.make_handler(portal))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    thread.start()
    try:
        launcher.check_portal(f"http://127.0.0.1:{server.server_port}")
        after = {
            p.relative_to(tmp_path): p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()
        }
        assert after == before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_browser_uses_dom_readiness_and_does_not_create_case_on_navigation_failure():
    page = FakePage()
    launcher.open_catalogue(page, "http://127.0.0.1:8081")
    assert page.navigations == [
        (
            "http://127.0.0.1:8081/demos",
            {
                "wait_until": "domcontentloaded",
                "timeout": 30000,
            },
        )
    ]
    assert page.clicks == []
    page.fail_navigation = True
    with pytest.raises(RuntimeError, match="No new case was created"):
        launcher.open_catalogue(page, "http://127.0.0.1:8081")
    assert page.clicks == []
    assert len(page.navigations) == 2  # Exactly one GET per explicit invocation.


def test_unreachable_portal_stops_before_speech_browser_or_obs(fake_capture, monkeypatch):
    page, obs = fake_capture

    def fail(base):
        raise RuntimeError("Tunnel is disconnected")

    monkeypatch.setattr(launcher, "check_portal", fail)
    monkeypatch.setattr(
        launcher, "make_audio", lambda *a, **k: pytest.fail("Speech must not start")
    )
    with pytest.raises(RuntimeError, match="Tunnel is disconnected"):
        launcher.main()
    assert page.clicks == []
    assert page.navigations == []
    assert obs.calls == []


def test_browser_navigation_failure_does_not_submit_or_record(fake_capture):
    page, obs = fake_capture
    page.fail_navigation = True
    with pytest.raises(RuntimeError, match="No new case was created"):
        launcher.main()
    assert page.clicks == []
    assert obs.calls == []


def test_playwright_error_is_actionable_and_not_retried(fake_capture, monkeypatch, capsys):
    class BrowserFailure(Exception):
        pass

    BrowserFailure.__module__ = "playwright._impl._errors"

    def fail():
        raise BrowserFailure("Navigation failed after a submitted action")

    monkeypatch.setattr(launcher, "main", fail)
    with pytest.raises(SystemExit) as error:
        launcher.cli()
    assert error.value.code == 1
    assert "Actions have not been retried" in capsys.readouterr().err
