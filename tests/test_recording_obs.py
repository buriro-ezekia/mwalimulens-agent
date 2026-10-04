"""Deterministic OBS protocol tests; these never connect to OBS or record media."""

from __future__ import annotations

import copy
import logging
import sys
from types import SimpleNamespace

import pytest

from mwalimulens.recording_obs import ObsController, ObsError


class FakeObs:
    def __init__(self, narration, output):
        self.calls = []
        self.closed = False
        self.fail = None
        self.output = output
        self.responses = {
            "GetRecordStatus": {"outputActive": False, "outputPaused": False},
            "GetStreamStatus": {"outputActive": False},
            "GetVirtualCamStatus": {"outputActive": False},
            "GetReplayBufferStatus": {"outputActive": False},
            "GetVideoSettings": {
                "baseWidth": 1920,
                "baseHeight": 1080,
                "outputWidth": 1920,
                "outputHeight": 1080,
                "fpsNumerator": 30,
                "fpsDenominator": 1,
            },
            "GetCurrentProgramScene": {"currentProgramSceneName": "MwalimuLens Final"},
            "GetStudioModeEnabled": {"studioModeEnabled": False},
            "GetSceneItemList": {
                "sceneItems": [
                    {
                        "sourceName": "MwalimuLens Display",
                        "sceneItemId": 1,
                        "sceneItemIndex": 1,
                        "sceneItemEnabled": True,
                        "isGroup": False,
                    },
                    {
                        "sourceName": "MwalimuLens Narration",
                        "sceneItemId": 2,
                        "sceneItemIndex": 0,
                        "sceneItemEnabled": True,
                        "isGroup": False,
                    },
                ]
            },
            "GetSceneItemTransform": {
                "sceneItemTransform": {
                    "width": 1920,
                    "height": 1080,
                    "positionX": 0,
                    "positionY": 0,
                    "scaleX": 1,
                    "scaleY": 1,
                    "rotation": 0,
                    "alignment": 5,
                    "boundsType": "OBS_BOUNDS_NONE",
                    "cropLeft": 0,
                    "cropRight": 0,
                    "cropTop": 0,
                    "cropBottom": 0,
                }
            },
            "GetSourceActive": {"videoActive": True},
            "GetSourceFilterList": {"filters": []},
            "GetSpecialInputs": {"desktop1": "Desktop Audio", "mic1": "Mic/Aux", "desktop2": None},
            "GetRecordDirectory": {"recordDirectory": str(output)},
            "GetMediaInputStatus": {
                "mediaState": "OBS_MEDIA_STATE_PAUSED",
                "mediaDuration": 156480,
                "mediaCursor": 0,
            },
            "GetInputVolume": {"inputVolumeMul": 1, "inputVolumeDb": 0},
            "GetInputAudioTracks": {"inputAudioTracks": {"1": True, "2": False}},
            "GetInputAudioMonitorType": {"monitorType": "OBS_MONITORING_TYPE_NONE"},
            "GetInputAudioSyncOffset": {"inputAudioSyncOffset": 0},
        }
        self.input_settings = {
            "MwalimuLens Display": {"inputKind": "monitor_capture", "inputSettings": {}},
            "MwalimuLens Narration": {
                "inputKind": "ffmpeg_source",
                "inputSettings": {
                    "local_file": str(narration),
                    "restart_on_activate": False,
                },
            },
        }
        self.defaults = {
            "ffmpeg_source": {
                "is_local_file": True,
                "looping": False,
                "restart_on_activate": True,
                "speed_percent": 100,
            },
            "monitor_capture": {},
        }
        self.mutes = {"MwalimuLens Narration": False, "Desktop Audio": True, "Mic/Aux": True}
        self.profile = {
            ("Output", "Mode"): "Simple",
            ("Output", "OverwriteIfExists"): "false",
            ("SimpleOutput", "RecFormat2"): "mkv",
            ("SimpleOutput", "RecTracks"): "1",
            ("SimpleOutput", "RecQuality"): "HQ",
        }

    def send(self, request, data=None, *, raw):
        assert raw is True
        self.calls.append((request, data))
        if self.fail == request:
            raise RuntimeError("private password and raw server comment")
        data = data or {}
        if request == "GetInputSettings":
            return copy.deepcopy(self.input_settings[data["inputName"]])
        if request == "GetInputDefaultSettings":
            return {"defaultInputSettings": copy.deepcopy(self.defaults[data["inputKind"]])}
        if request == "GetInputMute":
            return {"inputMuted": self.mutes[data["inputName"]]}
        if request == "GetProfileParameter":
            return {
                "parameterValue": self.profile.get(
                    (data["parameterCategory"], data["parameterName"])
                ),
                "defaultParameterValue": None,
            }
        if request == "StartRecord":
            self.responses["GetRecordStatus"]["outputActive"] = True
            return None
        if request == "StopRecord":
            self.responses["GetRecordStatus"]["outputActive"] = False
            return {"outputPath": str(self.output / "take.mkv")}
        if request == "TriggerMediaInputAction":
            self.responses["GetMediaInputStatus"]["mediaState"] = (
                "OBS_MEDIA_STATE_STOPPED"
                if data["mediaAction"].endswith("STOP")
                else "OBS_MEDIA_STATE_PLAYING"
            )
            return None
        return copy.deepcopy(self.responses[request])

    def disconnect(self):
        self.closed = True


@pytest.fixture
def prepared(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    narration = tmp_path / "narration.mp3"
    narration.write_bytes(b"not actual media; metadata is mocked")
    output = tmp_path / "recordings"
    output.mkdir()
    client = FakeObs(narration, output)
    controller = ObsController(client=client)
    return controller, client, {"repository": repository, "narration_path": narration}


def test_preflight_is_read_only_and_preserves_owner_scene(prepared):
    controller, client, kwargs = prepared
    snapshot = controller.preflight(**kwargs)
    assert snapshot.record_directory == client.output
    assert len(snapshot.fingerprint) == 64
    assert all(request.startswith("Get") for request, _ in client.calls)
    controller.assert_unchanged(snapshot)


def test_continuous_recording_and_narration_commands(prepared):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    controller.prepare_narration()
    controller.start_record()
    assert controller.owns_recording is True
    assert controller.record_status()["outputActive"] is True
    controller.restart_narration()
    assert controller.media_status()["mediaState"] == "OBS_MEDIA_STATE_PLAYING"
    assert controller.stop_record() == client.output / "take.mkv"
    assert controller.owns_recording is False
    controller.close()
    assert client.closed
    mutations = [(request, data) for request, data in client.calls if not request.startswith("Get")]
    assert mutations == [
        (
            "TriggerMediaInputAction",
            {
                "inputName": "MwalimuLens Narration",
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP",
            },
        ),
        ("StartRecord", None),
        (
            "TriggerMediaInputAction",
            {
                "inputName": "MwalimuLens Narration",
                "mediaAction": "OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
            },
        ),
        ("StopRecord", None),
    ]


@pytest.mark.parametrize(
    ("rpc", "key", "value", "message"),
    [
        ("GetRecordStatus", "outputActive", True, "already recording"),
        ("GetVideoSettings", "outputWidth", 1280, "1920"),
        ("GetVideoSettings", "fpsNumerator", 60, "30 FPS"),
        ("GetCurrentProgramScene", "currentProgramSceneName", "Private desktop", "dedicated"),
        ("GetStudioModeEnabled", "studioModeEnabled", True, "Studio Mode"),
        ("GetStreamStatus", "outputActive", True, "Stop streaming"),
        ("GetVirtualCamStatus", "outputActive", True, "Stop streaming"),
        ("GetReplayBufferStatus", "outputActive", True, "Stop streaming"),
        ("GetInputVolume", "inputVolumeMul", 0, "audible"),
        ("GetInputAudioTracks", "inputAudioTracks", {"1": False}, "track 1"),
        (
            "GetInputAudioMonitorType",
            "monitorType",
            "OBS_MONITORING_TYPE_MONITOR_ONLY",
            "Monitor Off",
        ),
        ("GetInputAudioSyncOffset", "inputAudioSyncOffset", 3000, "sync offset"),
        ("GetMediaInputStatus", "mediaDuration", None, "duration"),
        ("GetMediaInputStatus", "mediaDuration", 170000, "duration"),
        ("GetMediaInputStatus", "mediaState", "OBS_MEDIA_STATE_ERROR", "not ready"),
        ("GetSourceFilterList", "filters", [{"filterEnabled": True}], "filters"),
    ],
)
def test_invalid_obs_configuration_fails_without_mutation(prepared, rpc, key, value, message):
    controller, client, kwargs = prepared
    client.responses[rpc][key] = value
    with pytest.raises(ObsError, match=message):
        controller.preflight(**kwargs)
    assert not any(request == "StartRecord" for request, _ in client.calls)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("looping", True),
        ("restart_on_activate", True),
        ("speed_percent", 150),
        ("is_local_file", False),
        ("local_file", "https://example.com/audio.mp3"),
        ("close_when_inactive", True),
    ],
)
def test_media_must_be_exact_local_narration_at_original_speed(prepared, key, value):
    controller, client, kwargs = prepared
    client.input_settings["MwalimuLens Narration"]["inputSettings"][key] = value
    with pytest.raises(ObsError):
        controller.preflight(**kwargs)


def test_input_defaults_are_checked_not_assumed_safe(prepared):
    controller, client, kwargs = prepared
    del client.input_settings["MwalimuLens Narration"]["inputSettings"]["restart_on_activate"]
    with pytest.raises(ObsError, match="Restart"):
        controller.preflight(**kwargs)


@pytest.mark.parametrize("source", ["Desktop Audio", "Mic/Aux", "MwalimuLens Narration"])
def test_mixer_mute_boundaries(prepared, source):
    controller, client, kwargs = prepared
    client.mutes[source] = not client.mutes[source]
    with pytest.raises(ObsError):
        controller.preflight(**kwargs)


def test_output_cannot_be_written_inside_repository(prepared):
    controller, client, kwargs = prepared
    client.responses["GetRecordDirectory"]["recordDirectory"] = str(kwargs["repository"])
    with pytest.raises(ObsError, match="outside the repository"):
        controller.preflight(**kwargs)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("cropLeft", 1),
        ("rotation", 5),
        ("scaleX", -1),
        ("width", 1280),
        ("positionX", 100),
        ("boundsType", "OBS_BOUNDS_STRETCH"),
    ],
)
def test_capture_must_cover_full_canvas(prepared, key, value):
    controller, client, kwargs = prepared
    client.responses["GetSceneItemTransform"]["sceneItemTransform"][key] = value
    with pytest.raises(ObsError, match="complete canvas"):
        controller.preflight(**kwargs)


def test_center_aligned_full_canvas_capture_is_accepted(prepared):
    controller, client, kwargs = prepared
    transform = client.responses["GetSceneItemTransform"]["sceneItemTransform"]
    transform.update(alignment=0, positionX=960, positionY=540)
    controller.preflight(**kwargs)


def test_extra_visible_source_or_group_is_rejected(prepared):
    controller, client, kwargs = prepared
    items = client.responses["GetSceneItemList"]["sceneItems"]
    items.append({"sourceName": "Private Camera", "sceneItemEnabled": True, "sceneItemId": 3})
    with pytest.raises(ObsError, match="Enable only"):
        controller.preflight(**kwargs)
    items.pop()
    items[0]["isGroup"] = True
    with pytest.raises(ObsError, match="Enable only"):
        controller.preflight(**kwargs)


def test_named_microphone_is_the_only_optional_audio_source(prepared):
    controller, client, kwargs = prepared
    client.responses["GetSceneItemList"]["sceneItems"].append(
        {
            "sourceName": "Mic/Aux",
            "sceneItemEnabled": True,
            "sceneItemId": 3,
        }
    )
    client.input_settings["Mic/Aux"] = {"inputKind": "wasapi_input_capture", "inputSettings": {}}
    client.defaults["wasapi_input_capture"] = {}
    client.mutes["Mic/Aux"] = False
    controller.preflight(**kwargs, microphone_name="Mic/Aux")


@pytest.mark.parametrize(
    ("category", "name", "value", "message"),
    [
        ("SimpleOutput", "RecTracks", "2", "track 1"),
        ("SimpleOutput", "RecTracks", "3", "only audio track 1"),
        ("SimpleOutput", "RecTracks", "bad", "tracks"),
        ("SimpleOutput", "RecFormat2", "mp4", "MKV"),
        ("SimpleOutput", "RecQuality", "Stream", "High Quality"),
        ("Output", "OverwriteIfExists", "true", "overwrite"),
    ],
)
def test_recording_profile_requires_audible_recoverable_file(
    prepared, category, name, value, message
):
    controller, client, kwargs = prepared
    client.profile[(category, name)] = value
    with pytest.raises(ObsError, match=message):
        controller.preflight(**kwargs)


def test_scene_change_during_take_is_detected(prepared):
    controller, client, kwargs = prepared
    snapshot = controller.preflight(**kwargs)
    client.input_settings["MwalimuLens Display"]["inputSettings"]["monitor_id"] = "different"
    with pytest.raises(ObsError, match="configuration changed"):
        controller.assert_unchanged(snapshot)
    with pytest.raises(ObsError, match="configuration changed"):
        controller.start_record()
    assert not any(request == "StartRecord" for request, _ in client.calls)


def test_preexisting_recording_never_stopped(prepared):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    client.responses["GetRecordStatus"]["outputActive"] = True
    with pytest.raises(ObsError, match="already recording"):
        controller.start_record()
    with pytest.raises(ObsError, match="has not started"):
        controller.stop_record()
    assert not any(request == "StopRecord" for request, _ in client.calls)


def test_uncertain_start_needs_manual_stop_without_leaking_server_error(prepared):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    client.fail = "StartRecord"
    with pytest.raises(ObsError, match="StartRecord failed") as error:
        controller.start_record()
    assert "private password" not in str(error.value)
    assert controller.owns_recording
    client.fail = None
    with pytest.raises(ObsError, match="Stop recording in OBS manually"):
        controller.stop_record()
    assert not any(request == "StopRecord" for request, _ in client.calls)


def test_no_narration_before_recording_is_confirmed(prepared):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    with pytest.raises(ObsError, match="Start this recording"):
        controller.restart_narration()
    controller.start_record()
    client.responses["GetRecordStatus"]["outputActive"] = False
    with pytest.raises(ObsError, match="not confirmed"):
        controller.restart_narration()
    assert not any(request == "TriggerMediaInputAction" for request, _ in client.calls)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"host": "remote.example.com"},
        {"host": "localhost"},
        {"port": 0},
        {"port": 65536},
        {"timeout": 4},
        {"timeout": 0},
        {"timeout": float("nan")},
    ],
)
def test_connection_is_local_and_bounded(kwargs):
    with pytest.raises(ObsError):
        ObsController(client=object(), **kwargs)


def test_sdk_password_log_is_suppressed_and_not_retained(monkeypatch, caplog):
    received = {}
    base_client = SimpleNamespace(password="owner-secret")

    def connect(**kwargs):
        received.update(kwargs)
        logging.getLogger("obsws_python.baseclient.ObsClient").info(kwargs["password"])
        return SimpleNamespace(base_client=base_client)

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(ReqClient=connect))
    with caplog.at_level(logging.INFO):
        ObsController(password="owner-secret")
    assert "owner-secret" not in caplog.text
    assert base_client.password == ""
    assert received["host"] == "127.0.0.1"
    assert received["timeout"] == 3
    assert received["subs"] == 0
    assert not logging.getLogger("obsws_python.baseclient.ObsClient").disabled


def test_connection_failure_is_safe_and_restores_logging(monkeypatch, caplog):
    def connect(**kwargs):
        logging.getLogger("obsws_python.baseclient.ObsClient").error(kwargs["password"])
        raise RuntimeError(kwargs["password"])

    monkeypatch.setitem(sys.modules, "obsws_python", SimpleNamespace(ReqClient=connect))
    with pytest.raises(ObsError, match="Cannot connect") as error:
        ObsController(password="owner-secret")
    assert "owner-secret" not in str(error.value) + caplog.text
    assert not logging.getLogger("obsws_python.baseclient.ObsClient").disabled


@pytest.mark.parametrize("rpc", ["GetReplayBufferStatus", "GetVirtualCamStatus"])
def test_disabled_optional_output_is_inactive_but_timeout_is_not(prepared, rpc, monkeypatch):
    controller, client, kwargs = prepared
    original = client.send

    def send(request, data=None, *, raw):
        if request == rpc:
            error = RuntimeError("unavailable output")
            error.req_name = rpc
            error.code = 604
            raise error
        return original(request, data, raw=raw)

    monkeypatch.setattr(client, "send", send)
    controller.preflight(**kwargs)
    monkeypatch.setattr(client, "send", original)
    client.fail = rpc
    with pytest.raises(ObsError, match="failed or timed out"):
        controller.preflight(**kwargs)


def test_rejected_start_does_not_claim_someone_elses_recording(prepared, monkeypatch):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    original = client.send

    def send(request, data=None, *, raw):
        if request == "StartRecord":
            error = RuntimeError("output already running")
            error.code = 500
            raise error
        return original(request, data, raw=raw)

    monkeypatch.setattr(client, "send", send)
    with pytest.raises(ObsError):
        controller.start_record()
    assert not controller.owns_recording
    assert controller.record_status()["outputActive"] is False
    with pytest.raises(ObsError, match="has not started"):
        controller.stop_record()


def test_restart_waits_for_asynchronous_playback(prepared, monkeypatch):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    controller.start_record()
    original = client.send
    pending = ["OBS_MEDIA_STATE_STOPPED", "OBS_MEDIA_STATE_OPENING", "OBS_MEDIA_STATE_PLAYING"]

    def send(request, data=None, *, raw):
        result = original(request, data, raw=raw)
        if request == "GetMediaInputStatus":
            result["mediaState"] = pending.pop(0)
        return result

    monkeypatch.setattr(client, "send", send)
    controller.restart_narration()
    assert not pending


def test_restart_wait_is_bounded_even_when_media_never_opens(prepared, monkeypatch):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    controller.start_record()
    original = client.send
    clock = [0.0]

    def send(request, data=None, *, raw):
        result = original(request, data, raw=raw)
        if request == "GetMediaInputStatus":
            result["mediaState"] = "OBS_MEDIA_STATE_OPENING"
        return result

    monkeypatch.setattr(client, "send", send)
    monkeypatch.setattr("mwalimulens.recording_obs.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "mwalimulens.recording_obs.time.sleep", lambda delay: clock.__setitem__(0, clock[0] + delay)
    )
    with pytest.raises(ObsError, match="startup timed out"):
        controller.restart_narration()
    assert clock[0] <= 1.25


def test_restart_refuses_paused_recording(prepared):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    controller.start_record()
    client.responses["GetRecordStatus"]["outputPaused"] = True
    with pytest.raises(ObsError, match="not confirmed"):
        controller.restart_narration()


def test_narration_artwork_cannot_cover_the_display(prepared):
    controller, client, kwargs = prepared
    client.responses["GetSceneItemList"]["sceneItems"][1]["sceneItemIndex"] = 2
    with pytest.raises(ObsError, match="above narration"):
        controller.preflight(**kwargs)


def _fake_clock(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("mwalimulens.recording_obs.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "mwalimulens.recording_obs.time.sleep", lambda delay: clock.__setitem__(0, clock[0] + delay)
    )
    return clock


def test_start_and_stop_wait_for_output_state_after_ack(prepared, monkeypatch):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    clock = _fake_clock(monkeypatch)
    original = client.send
    pending = []

    def send(request, data=None, *, raw):
        result = original(request, data, raw=raw)
        if request == "StartRecord":
            pending.extend([False, False, True])
        elif request == "StopRecord":
            pending.extend([True, True, False])
        elif request == "GetRecordStatus" and pending:
            result["outputActive"] = pending.pop(0)
        return result

    monkeypatch.setattr(client, "send", send)
    controller.start_record()
    assert not pending and controller.owns_recording
    controller.stop_record()
    assert not pending and not controller.owns_recording
    assert clock[0] == pytest.approx(0.2)


@pytest.mark.parametrize(("phase", "limit"), [("StartRecord", 1.5), ("StopRecord", 5.0)])
def test_output_state_wait_is_bounded_and_retains_cleanup_ownership(
    prepared, monkeypatch, phase, limit
):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    if phase == "StopRecord":
        controller.start_record()
    clock = _fake_clock(monkeypatch)
    original = client.send
    waiting = False

    def send(request, data=None, *, raw):
        nonlocal waiting
        result = original(request, data, raw=raw)
        if request == phase:
            waiting = True
        elif request == "GetRecordStatus" and waiting:
            result["outputActive"] = phase == "StopRecord"
        return result

    monkeypatch.setattr(client, "send", send)
    with pytest.raises(ObsError, match="recording state in time"):
        if phase == "StartRecord":
            controller.start_record()
        else:
            controller.stop_record()
    assert clock[0] <= limit
    assert controller.owns_recording


def test_scene_check_has_one_budget_for_all_requests_and_restores_it(prepared, monkeypatch):
    controller, client, kwargs = prepared
    snapshot = controller.preflight(**kwargs)
    clock = _fake_clock(monkeypatch)
    original = client.send
    calls = []
    socket_timeouts = []
    client.base_client = SimpleNamespace(ws=SimpleNamespace(settimeout=socket_timeouts.append))

    def send(request, data=None, *, raw):
        calls.append(request)
        clock[0] += 0.2
        return original(request, data, raw=raw)

    monkeypatch.setattr(client, "send", send)
    with pytest.raises(ObsError, match="deadline expired"):
        controller.assert_unchanged(snapshot, budget_seconds=1)
    assert len(calls) <= 5
    assert all(0 < value <= 1 for value in socket_timeouts[::2])
    assert all(value == 3 for value in socket_timeouts[1::2])
    assert controller._request_deadline is None
    monkeypatch.setattr(client, "send", original)
    controller.assert_unchanged(snapshot)


@pytest.mark.parametrize("failure", [TimeoutError("private transport detail"), KeyboardInterrupt()])
def test_uncertain_connection_never_consumes_a_queued_stale_reply(prepared, monkeypatch, failure):
    controller, client, kwargs = prepared
    controller.preflight(**kwargs)
    original = client.send
    queued = [{"outputActive": False, "outputPaused": False}]
    failed = False
    calls = []

    def send(request, data=None, *, raw):
        nonlocal failed
        calls.append(request)
        if request == "StartRecord" and not failed:
            failed = True
            raise failure
        if failed:
            return queued.pop(0)
        return original(request, data, raw=raw)

    monkeypatch.setattr(client, "send", send)
    with pytest.raises(KeyboardInterrupt if isinstance(failure, KeyboardInterrupt) else ObsError):
        controller.start_record()
    assert controller.owns_recording
    sent = len(calls)
    with pytest.raises(ObsError, match="reconnect before retrying"):
        controller.record_status()
    with pytest.raises(ObsError, match="Stop recording in OBS manually"):
        controller.stop_record()
    assert len(calls) == sent
    assert queued == [{"outputActive": False, "outputPaused": False}]
    controller.close()
    assert client.closed


def test_media_lifecycle_dimensions_do_not_invalidate_scene_configuration(prepared):
    controller, client, kwargs = prepared
    item = client.responses["GetSceneItemList"]["sceneItems"][1]
    item["sceneItemTransform"] = {
        "sourceWidth": 512,
        "sourceHeight": 512,
        "width": 512,
        "height": 512,
        "positionX": 0,
        "positionY": 0,
        "scaleX": 1,
        "scaleY": 1,
        "cropLeft": 0,
        "cropRight": 0,
        "cropTop": 0,
        "cropBottom": 0,
    }
    snapshot = controller.preflight(**kwargs)
    controller.prepare_narration()
    item["sceneItemTransform"].update(sourceWidth=0, sourceHeight=0, width=0, height=0)
    controller.assert_unchanged(snapshot)
    controller.start_record()
    controller.restart_narration()
    item["sceneItemTransform"].update(sourceWidth=512, sourceHeight=512, width=512, height=512)
    controller.assert_unchanged(snapshot)
    client.responses["GetMediaInputStatus"]["mediaState"] = "OBS_MEDIA_STATE_ENDED"
    item["sceneItemTransform"].update(sourceWidth=0, sourceHeight=0, width=0, height=0)
    controller.assert_unchanged(snapshot)
    controller.stop_record()


@pytest.mark.parametrize("change", ["display_crop", "display_order", "source_identity", "enabled"])
def test_normalized_scene_still_rejects_configuration_changes(prepared, change):
    controller, client, kwargs = prepared
    snapshot = controller.preflight(**kwargs)
    display = client.responses["GetSceneItemList"]["sceneItems"][0]
    if change == "display_crop":
        client.responses["GetSceneItemTransform"]["sceneItemTransform"]["cropLeft"] = 8
    elif change == "display_order":
        display["sceneItemIndex"] = 2
    elif change == "source_identity":
        display["sourceUuid"] = "replacement-display"
    else:
        display["sceneItemEnabled"] = False
    with pytest.raises(ObsError):
        controller.assert_unchanged(snapshot)
