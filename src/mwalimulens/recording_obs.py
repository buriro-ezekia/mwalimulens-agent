"""Small, bounded OBS WebSocket adapter for the owner-prepared recording scene.

Requests follow obs-websocket's v5 protocol. The optional SDK is imported only
when a real connection is requested; unit tests inject a request client.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SDK_LOCK = threading.RLock()
_SDK_LOGGERS = (
    "obsws_python.baseclient.ObsClient",
    "obsws_python.reqs.ReqClient",
)


class ObsError(RuntimeError):
    """Actionable error that never includes raw SDK responses or credentials."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ObsSnapshot:
    fingerprint: str
    record_directory: Path


@contextmanager
def _quiet_sdk():
    # obsws-python logs its password at INFO when connecting, and raw server
    # comments on failed requests. Suppress precisely these SDK loggers, then
    # restore their state; application logging is unaffected.
    with _SDK_LOCK:
        loggers = [logging.getLogger(name) for name in _SDK_LOGGERS]
        previous = [logger.disabled for logger in loggers]
        try:
            for logger in loggers:
                logger.disabled = True
            yield
        finally:
            for logger, disabled in zip(loggers, previous, strict=True):
                logger.disabled = disabled


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ObsError(message)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _scene_configuration(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep configured scene properties, excluding decoded media dimensions."""
    configuration = []
    for item in items:
        entry = dict(item)
        transform = item.get("sceneItemTransform")
        if isinstance(transform, dict):
            # OBS derives these four values from the currently decoded source.
            # MP3 cover art can disappear on STOP/ENDED and return on PLAY.
            # Position, scale, crop, bounds and every identity/order flag remain
            # checked. The display's complete transform is checked separately.
            entry["sceneItemTransform"] = {
                key: value
                for key, value in transform.items()
                if key not in {"sourceWidth", "sourceHeight", "width", "height"}
            }
        configuration.append(entry)
    return configuration


class ObsController:
    """Validate configuration without replacing scenes or changing OBS settings."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4455,
        password: str = "",
        timeout: float = 3.0,
        *,
        client: Any = None,
    ) -> None:
        _require(host == "127.0.0.1", "OBS must use the local address 127.0.0.1.")
        _require(type(port) is int and 1 <= port <= 65535, "OBS port must be 1–65535.")
        _require(_number(timeout) and 0 < timeout <= 3, "OBS timeout must be at most 3 seconds.")
        self._client = client
        self._timeout = timeout
        self._request_deadline: float | None = None
        self._connection_uncertain = False
        self._configuration: dict[str, Any] | None = None
        self._snapshot: ObsSnapshot | None = None
        self._owns_recording = False
        if client is None:
            try:
                import obsws_python
            except ImportError:
                raise ObsError(
                    "Install recording dependencies with pip install -e '.[record]'."
                ) from None
            try:
                with _quiet_sdk():
                    self._client = obsws_python.ReqClient(
                        host=host, port=port, password=password, timeout=timeout, subs=0
                    )
                # Authentication is complete. Do not retain a password in the
                # SDK object's printable representation.
                self._client.base_client.password = ""
            except Exception:
                raise ObsError(
                    "Cannot connect to local OBS. Check WebSocket enablement, port and password."
                ) from None

    def _request(
        self, request: str, *, deadline: float | None = None, **data: Any
    ) -> dict[str, Any]:
        _require(self._client is not None, "The OBS connection is closed.")
        _require(
            not self._connection_uncertain,
            "OBS connection state is uncertain after a transport failure. "
            "Stop recording in OBS manually and reconnect before retrying.",
        )
        if self._request_deadline is not None:
            deadline = min(deadline, self._request_deadline) if deadline else self._request_deadline
        remaining = self._timeout if deadline is None else deadline - time.monotonic()
        _require(remaining > 0, "OBS operation deadline expired.")
        socket = getattr(getattr(self._client, "base_client", None), "ws", None)
        try:
            with _quiet_sdk():
                if deadline is not None and socket is not None:
                    socket.settimeout(min(self._timeout, remaining))
                try:
                    response = self._client.send(request, data or None, raw=True)
                finally:
                    if deadline is not None and socket is not None:
                        socket.settimeout(self._timeout)
        except BaseException as error:
            code = getattr(error, "code", None)
            if type(code) is not int:
                # The SDK does not correlate received request IDs. A delayed
                # reply after a timeout/interruption could be consumed by the
                # next request and falsely confirm recording cleanup. Refuse
                # all further requests on this connection, including StopRecord.
                self._connection_uncertain = True
                if not isinstance(error, Exception):
                    raise
                raise ObsError(
                    f"OBS {request} failed or timed out; connection state is uncertain. "
                    "Stop recording in OBS manually and reconnect before retrying."
                ) from None
            # OBS reports InvalidResourceState when these optional outputs are
            # unavailable (for example, Replay Buffer is disabled in Settings).
            # That is a known inactive output, not a connection failure.
            if (
                request in {"GetVirtualCamStatus", "GetReplayBufferStatus"}
                and getattr(error, "req_name", None) == request
                and code == 604
            ):
                return {"outputActive": False}
            raise ObsError(
                f"OBS {request} failed or timed out. Check the OBS window and local connection.",
                code=code,
            ) from None
        if response is None:
            return {}
        _require(isinstance(response, dict), f"OBS {request} returned an invalid response.")
        return response

    def _input_settings(self, name: str, kind: str) -> dict[str, Any]:
        actual = self._request("GetInputSettings", inputName=name)
        _require(actual.get("inputKind") == kind, f"Configure the expected source type for {name}.")
        defaults = self._request("GetInputDefaultSettings", inputKind=kind)
        base = defaults.get("defaultInputSettings")
        overrides = actual.get("inputSettings")
        _require(
            isinstance(base, dict) and isinstance(overrides, dict), "OBS settings are missing."
        )
        return {**base, **overrides}

    def _profile(self, category: str, name: str) -> str | None:
        result = self._request(
            "GetProfileParameter", parameterCategory=category, parameterName=name
        )
        return result.get("parameterValue") or result.get("defaultParameterValue")

    def _recording_settings(self) -> dict[str, Any]:
        mode = self._profile("Output", "Mode")
        _require(mode in {"Simple", "Advanced"}, "Use OBS Simple or Advanced recording output.")
        category = "SimpleOutput" if mode == "Simple" else "AdvOut"
        if mode == "Advanced":
            _require(
                self._profile(category, "RecType") == "Standard",
                "Use Standard recording in OBS Advanced output, not custom FFmpeg output.",
            )
            _require(
                self._profile(category, "RecRescale") in {None, "false", "0"}
                and self._profile(category, "RecRescaleFilter") in {None, "0"},
                "Disable recording rescaling in OBS Advanced output.",
            )
        format_name = self._profile(category, "RecFormat2")
        _require(
            format_name in {"mkv", "hybrid_mp4"},
            "Choose MKV (recommended) or Hybrid MP4 as the OBS recording format.",
        )
        raw_tracks = self._profile(category, "RecTracks")
        try:
            tracks = int(raw_tracks or "")
        except ValueError:
            raise ObsError(
                "Cannot verify OBS recording audio tracks; select recording track 1."
            ) from None
        _require(tracks == 1, "Enable only audio track 1 in the OBS recording output.")
        if mode == "Simple":
            _require(
                self._profile(category, "RecQuality") in {"HQ", "Small"},
                "Choose High Quality or Indistinguishable recording quality in OBS Simple output.",
            )
        _require(
            self._profile("Output", "OverwriteIfExists") in {None, "false", "0"},
            "Turn off overwrite-if-existing in OBS recording output.",
        )
        return {"mode": mode, "format": format_name, "tracks": tracks}

    def _audio(self, name: str) -> dict[str, Any]:
        mute = self._request("GetInputMute", inputName=name)
        volume = self._request("GetInputVolume", inputName=name)
        tracks = self._request("GetInputAudioTracks", inputName=name)
        monitor = self._request("GetInputAudioMonitorType", inputName=name)
        sync = self._request("GetInputAudioSyncOffset", inputName=name)
        _require(mute.get("inputMuted") is False, f"Unmute {name} in OBS.")
        multiplier = volume.get("inputVolumeMul")
        _require(
            _number(multiplier) and 0.1 <= multiplier <= 2,
            f"Set an audible, unclipped mixer level for {name} (between -20 and +6 dB).",
        )
        _require(
            tracks.get("inputAudioTracks", {}).get("1") is True,
            f"Enable recording audio track 1 for {name}.",
        )
        _require(
            monitor.get("monitorType") == "OBS_MONITORING_TYPE_NONE",
            f"Set Audio Monitoring to Monitor Off for {name} to prevent duplicate audio.",
        )
        _require(
            sync.get("inputAudioSyncOffset") == 0, f"Set the audio sync offset to 0 for {name}."
        )
        return {**mute, **volume, **tracks, **monitor, **sync}

    def _state(self) -> tuple[dict[str, Any], Path]:
        config = self._configuration
        _require(config is not None, "Run OBS preflight before using the recording scene.")
        scene = config["scene_name"]
        display = config["display_name"]
        narration = config["narration_name"]
        mic = config["microphone_name"]
        video = self._request("GetVideoSettings")
        _require(
            all(
                video.get(key) == value
                for key, value in {
                    "baseWidth": 1920,
                    "baseHeight": 1080,
                    "outputWidth": 1920,
                    "outputHeight": 1080,
                }.items()
            ),
            "Set both OBS canvas and output resolution to 1920×1080.",
        )
        numerator, denominator = video.get("fpsNumerator"), video.get("fpsDenominator")
        _require(
            _number(numerator)
            and _number(denominator)
            and denominator > 0
            and numerator / denominator == 30,
            "Set OBS video frame rate to exactly 30 FPS.",
        )
        _require(
            self._request("GetCurrentProgramScene").get("currentProgramSceneName") == scene,
            f"Select the dedicated OBS scene {scene}.",
        )
        _require(
            self._request("GetStudioModeEnabled").get("studioModeEnabled") is False,
            "Turn off OBS Studio Mode for this continuous take.",
        )
        for request in ("GetStreamStatus", "GetVirtualCamStatus", "GetReplayBufferStatus"):
            _require(
                self._request(request).get("outputActive") is False,
                "Stop streaming, Virtual Camera and Replay Buffer before the recording.",
            )
        items = self._request("GetSceneItemList", sceneName=scene).get("sceneItems")
        _require(isinstance(items, list), "OBS did not return the recording scene sources.")
        enabled = [item for item in items if item.get("sceneItemEnabled") is True]
        expected = {display: "monitor_capture", narration: "ffmpeg_source"}
        if mic:
            expected[mic] = "wasapi_input_capture"
        _require(
            len(enabled) == len(expected)
            and {item.get("sourceName") for item in enabled} == set(expected)
            and all(not item.get("isGroup") for item in enabled),
            "Enable only the named Display Capture, narration and optional microphone sources.",
        )
        settings = {name: self._input_settings(name, kind) for name, kind in expected.items()}
        for name in (scene, *expected):
            filters = self._request("GetSourceFilterList", sourceName=name).get("filters")
            _require(
                isinstance(filters, list) and not any(f.get("filterEnabled") for f in filters),
                "Disable source and scene filters in the dedicated recording scene.",
            )
        item = next(item for item in enabled if item["sourceName"] == display)
        narration_item = next(item for item in enabled if item["sourceName"] == narration)
        _require(
            type(item.get("sceneItemIndex")) is int
            and type(narration_item.get("sceneItemIndex")) is int
            and item["sceneItemIndex"] > narration_item["sceneItemIndex"],
            "Place Display Capture above narration in OBS Sources to cover any MP3 artwork.",
        )
        transform = self._request(
            "GetSceneItemTransform", sceneName=scene, sceneItemId=item["sceneItemId"]
        ).get("sceneItemTransform", {})
        self._check_full_frame(transform)
        media = settings[narration]
        actual_path = media.get("local_file")
        _require(
            media.get("is_local_file") is True
            and isinstance(actual_path, str)
            and Path(actual_path).resolve() == config["narration_path"],
            "Select the supplied local narration file in the OBS Media Source.",
        )
        _require(
            media.get("looping") is False
            and media.get("restart_on_activate") is False
            and media.get("speed_percent") == 100
            and media.get("close_when_inactive", False) is False,
            "Narration must use speed 100%, with Loop, Restart and Close when inactive disabled.",
        )
        _require(
            self._request("GetSourceActive", sourceName=narration).get("videoActive") is True,
            "The narration source must be active in the selected OBS scene.",
        )
        audio = {name: self._audio(name) for name in (narration, mic) if name}
        special = self._request("GetSpecialInputs")
        muted = {}
        for name in set(special.values()) - {None, "", mic}:
            muted[name] = self._request("GetInputMute", inputName=name).get("inputMuted")
            _require(
                muted[name] is True, "Mute all global Desktop Audio and unused Mic/Aux inputs."
            )
        output = self._request("GetRecordDirectory").get("recordDirectory")
        _require(isinstance(output, str) and bool(output), "Set an OBS recording directory.")
        directory = Path(output).resolve()
        _require(
            Path(output).is_absolute()
            and directory.is_dir()
            and not directory.is_relative_to(config["repository"]),
            "Choose an existing OBS recording directory outside the repository.",
        )
        return {
            "video": video,
            "items": _scene_configuration(items),
            "transform": transform,
            "settings": settings,
            "audio": audio,
            "special": special,
            "muted": muted,
            "output": str(directory),
            "recording": self._recording_settings(),
        }, directory

    @staticmethod
    def _check_full_frame(transform: dict[str, Any]) -> None:
        _require(
            all(
                _number(transform.get(key))
                for key in (
                    "width",
                    "height",
                    "positionX",
                    "positionY",
                    "scaleX",
                    "scaleY",
                    "rotation",
                )
            ),
            "OBS did not provide the Display Capture transform.",
        )
        alignment = transform.get("alignment")
        _require(type(alignment) is int, "OBS display alignment is missing.")
        left = transform["positionX"] - transform["width"] * (
            0 if alignment & 1 else 1 if alignment & 2 else 0.5
        )
        top = transform["positionY"] - transform["height"] * (
            0 if alignment & 4 else 1 if alignment & 8 else 0.5
        )
        _require(
            abs(transform["width"] - 1920) < 0.5
            and abs(transform["height"] - 1080) < 0.5
            and abs(left) < 0.5
            and abs(top) < 0.5
            and transform["rotation"] == 0
            and transform["scaleX"] > 0
            and transform["scaleY"] > 0
            and transform.get("boundsType") == "OBS_BOUNDS_NONE"
            and all(
                transform.get(key) == 0
                for key in ("cropLeft", "cropRight", "cropTop", "cropBottom")
            ),
            "Fit Display Capture to the complete canvas, with no crop, rotation, flip or bounds.",
        )

    def preflight(
        self,
        *,
        repository: Path,
        narration_path: Path,
        scene_name: str = "MwalimuLens Final",
        display_name: str = "MwalimuLens Display",
        narration_name: str = "MwalimuLens Narration",
        microphone_name: str | None = None,
        expected_duration_ms: float = 156480,
    ) -> ObsSnapshot:
        self._snapshot = None
        _require(not self._owns_recording, "Cannot run preflight while this take is recording.")
        _require(
            self.record_status().get("outputActive") is False,
            "OBS is already recording. Stop it yourself before starting a new take.",
        )
        _require(narration_path.is_file(), "The supplied narration file does not exist.")
        names = [scene_name, display_name, narration_name]
        if microphone_name:
            names.append(microphone_name)
        _require(all(names) and len(set(names)) == len(names), "Use distinct OBS source names.")
        self._configuration = {
            "repository": repository.resolve(),
            "narration_path": narration_path.resolve(),
            "scene_name": scene_name,
            "display_name": display_name,
            "narration_name": narration_name,
            "microphone_name": microphone_name,
        }
        state, directory = self._state()
        media = self.media_status()
        duration = media.get("mediaDuration")
        _require(
            _number(duration) and abs(duration - expected_duration_ms) <= 750,
            "Load the 2:36.48 narration in OBS; media duration is unavailable or does not match.",
        )
        _require(
            media.get("mediaState")
            in {
                "OBS_MEDIA_STATE_PLAYING",
                "OBS_MEDIA_STATE_PAUSED",
                "OBS_MEDIA_STATE_STOPPED",
                "OBS_MEDIA_STATE_ENDED",
            },
            "The OBS narration source is not ready; load it and pause before retrying.",
        )
        self._snapshot = ObsSnapshot(self._fingerprint(state), directory)
        return self._snapshot

    @staticmethod
    def _fingerprint(state: dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()

    def assert_unchanged(self, snapshot: ObsSnapshot, budget_seconds: float = 1.0) -> None:
        _require(
            _number(budget_seconds) and 0 < budget_seconds <= 3,
            "OBS scene-check budget must be between 0 and 3 seconds.",
        )
        previous = self._request_deadline
        self._request_deadline = time.monotonic() + budget_seconds
        try:
            state, directory = self._state()
            _require(
                time.monotonic() <= self._request_deadline,
                "OBS scene check exceeded its time budget.",
            )
            _require(
                self._fingerprint(state) == snapshot.fingerprint
                and directory == snapshot.record_directory,
                "The prepared OBS scene, audio or recording configuration changed during the take.",
            )
        finally:
            self._request_deadline = previous

    def _narration_action(self, action: str) -> None:
        _require(self._snapshot is not None, "Run OBS preflight before controlling narration.")
        self._request(
            "TriggerMediaInputAction",
            inputName=self._configuration["narration_name"],
            mediaAction=f"OBS_WEBSOCKET_MEDIA_INPUT_ACTION_{action}",
        )

    def prepare_narration(self) -> None:
        """Hold narration before recording without changing any source settings."""
        self._narration_action("STOP")

    def restart_narration(self) -> None:
        _require(self._owns_recording, "Start this recording before restarting narration.")
        record = self.record_status()
        _require(
            record.get("outputActive") is True and record.get("outputPaused") is False,
            "OBS has not confirmed an active recording; narration was not started.",
        )
        self._narration_action("RESTART")
        # OBS acknowledges media actions before decoding starts. Wait briefly
        # for real playback, retaining the shared take timeline in the caller.
        deadline = time.monotonic() + 1.25
        while True:
            _require(time.monotonic() < deadline, "OBS narration startup timed out.")
            media = self._request(
                "GetMediaInputStatus",
                deadline=deadline,
                inputName=self._configuration["narration_name"],
            )
            state = media.get("mediaState")
            if state == "OBS_MEDIA_STATE_PLAYING":
                cursor = media.get("mediaCursor")
                _require(
                    _number(cursor) and 0 <= cursor <= 1500,
                    "OBS narration did not restart at its beginning.",
                )
                return
            _require(
                state
                in {
                    "OBS_MEDIA_STATE_OPENING",
                    "OBS_MEDIA_STATE_BUFFERING",
                    "OBS_MEDIA_STATE_STOPPED",
                    "OBS_MEDIA_STATE_NONE",
                },
                "OBS narration failed to start playing.",
            )
            remaining = deadline - time.monotonic()
            _require(remaining > 0, "OBS narration startup timed out.")
            time.sleep(min(0.05, remaining))

    def media_status(self) -> dict[str, Any]:
        _require(self._configuration is not None, "Run OBS preflight to select narration.")
        return self._request("GetMediaInputStatus", inputName=self._configuration["narration_name"])

    def record_status(self) -> dict[str, Any]:
        return self._request("GetRecordStatus")

    def _wait_recording(self, active: bool, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        while True:
            _require(
                time.monotonic() < deadline, "OBS did not confirm the recording state in time."
            )
            status = self._request("GetRecordStatus", deadline=deadline)
            if status.get("outputActive") is active:
                _require(
                    not active or status.get("outputPaused") is False,
                    "OBS recording is paused; this take is invalid.",
                )
                return
            remaining = deadline - time.monotonic()
            _require(remaining > 0, "OBS did not confirm the recording state in time.")
            time.sleep(min(0.05, remaining))

    def start_record(self) -> None:
        _require(self._snapshot is not None, "Run OBS preflight before recording.")
        self.assert_unchanged(self._snapshot)
        _require(
            self.record_status().get("outputActive") is False,
            "OBS is already recording; this helper will not take over another recording.",
        )
        # A timeout can happen after OBS accepted StartRecord. Retain ownership
        # intent so the caller can attempt StopRecord in its failure cleanup.
        self._owns_recording = True
        try:
            self._request("StartRecord")
        except ObsError as error:
            if error.code is not None:
                # A protocol rejection is unambiguous, including another owner
                # starting a recording between our idle check and this request.
                self._owns_recording = False
            raise
        self._wait_recording(True, 1.5)

    @property
    def owns_recording(self) -> bool:
        """Whether this helper must attempt to stop an acknowledged or uncertain start."""
        return self._owns_recording

    def stop_record(self) -> Path:
        _require(self._owns_recording, "This helper has not started an OBS recording.")
        response = self._request("StopRecord")
        self._wait_recording(False, 5.0)
        self._owns_recording = False
        output = response.get("outputPath")
        _require(isinstance(output, str) and bool(output), "OBS did not return a recording path.")
        path = Path(output).resolve()
        _require(
            Path(output).is_absolute()
            and self._snapshot is not None
            and path.is_relative_to(self._snapshot.record_directory)
            and not path.is_relative_to(self._configuration["repository"]),
            "OBS returned an unexpected recording location. Check its output directory.",
        )
        return path

    def close(self) -> None:
        """Disconnect only; the caller must stop its own take in a finally block."""
        if self._client is not None:
            try:
                with _quiet_sdk():
                    self._client.disconnect()
            except Exception:
                raise ObsError("OBS disconnect failed. Check the OBS window.") from None
            finally:
                self._client = None
