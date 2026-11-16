"""Preflight and mocked capture regressions, not Windows/OBS video acceptance."""

import importlib.util
import wave
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

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

    def set_default_timeout(self, *args):
        pass

    def route(self, *args):
        pass

    def goto(self, *args):
        pass

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

        return SimpleNamespace(click=click, check=lambda: None)

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
    monkeypatch.setattr(launcher, "make_audio", lambda root: [clip] * 6)
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
