"""Record the authored hosted workflow on Windows; never invoke a model.

Requires playwright and the repository's [record] extra. OBS and the private
SSH tunnel must already be running. The owner selects the capture window and
explicitly starts the take after preflight. Existing cases are never reset.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
import tempfile
import uuid
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from mwalimulens.recording_obs import ObsController

SCENE = "MwalimuLens Hosted Review"
DEFAULT_VOICE = "auto"
REASON = (
    "Recorded assessment scores rise from 61% to 87% across four terms "
    "(EV-001, EV-004, EV-007, EV-009), but task comparability is not established. "
    "EV-008 records difficulty explaining independently, while the later EV-011 "
    "records a successful explanation in a practical task. Independent reasoning "
    "across unfamiliar tasks remains uncertain."
)
WORDING = (
    "Recorded fractions assessment scores increased across four terms. "
    "Explanations vary across the available observations, so independent "
    "understanding remains uncertain. Ask the learner to explain their method "
    "for an unfamiliar fractions problem without prompts."
)
SPEECH = [
    "MwalimuLens helps teachers review learner evidence across terms while keeping "
    "uncertainty visible. This is the AWS hosted application, accessed through a "
    "private SSH tunnel. The learner is fictional, the candidate is authored, "
    "and reviewer identity is simulated. No model inference runs in this sequence.",
    "Recorded assessment scores rise from 61 to 87 per cent. These tasks are not "
    "established as directly comparable. One observation records difficulty "
    "explaining independently. A later practical task records a successful "
    "explanation. Both observations matter. Neither establishes lasting mastery.",
    "I am revising the finding to distinguish recorded scores from independent "
    "understanding. The revision retains uncertainty and proposes an unfamiliar "
    "explanation task without prompts. This preview has not saved a decision.",
    "Explicit confirmation records one simulated teacher decision and creates "
    "one synthetic profile note. The model cannot approve its own candidate.",
    "Reopening the same saved case retains the reason, revised wording and single "
    "profile note. Reopening does not create another decision.",
    "This supplements the earlier MCP demonstration by showing the completed "
    "review workflow. A valid model generated proposal completing this sequence, "
    "and a qualified teacher's assessment, remain to be verified.",
]


def local_url(value: str) -> str:
    p = urlsplit(value)
    if (
        p.scheme != "http"
        or p.hostname != "127.0.0.1"
        or not p.port
        or p.netloc != f"127.0.0.1:{p.port}"
        or p.path not in ("", "/")
        or p.query
        or p.fragment
    ):
        raise ValueError("Use only http://127.0.0.1:PORT with no other URL components.")
    return value.rstrip("/")


class NoPortalRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def check_portal(base: str) -> None:
    """Bounded catalogue GET, with no proxy/redirect or case creation."""
    base = local_url(base)
    try:
        opener = build_opener(ProxyHandler({}), NoPortalRedirect())
        with opener.open(base + "/demos", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError(f"Workspace catalogue returned HTTP {response.status}.")
            limit = 4 * 1024 * 1024
            data = response.read(limit + 1)
            if len(data) > limit:
                raise RuntimeError("Workspace catalogue exceeded the expected page size.")
            text = data.decode("utf-8", errors="replace")
            markers = (
                "<title>MwalimuLens | Demonstration cases</title>",
                "<h1>Demonstration cases</h1>",
                "New candidate demonstration",
            )
            if not all(marker in text for marker in markers):
                raise RuntimeError(
                    f"{base} did not return the MwalimuLens demonstration catalogue."
                )
    except HTTPError as exc:
        status = exc.code
        exc.close()
        hint = (
            f"Check the remote workspace --browser-port {urlsplit(base).port} setting."
            if status == 403
            else "Check the remote workspace and server.log."
        )
        raise RuntimeError(f"Workspace catalogue returned HTTP {status}. {hint}") from None
    except (URLError, OSError) as exc:
        raise RuntimeError(
            f"Cannot reach {base}/demos within the connection deadline. "
            "Reconnect the private SSH tunnel and check the remote workspace is running. "
            "No speech, browser case or recording has started."
        ) from exc


def open_catalogue(page, base: str) -> None:
    """Wait for the actual catalogue, without waiting for a full load event."""
    try:
        response = page.goto(base + "/demos", wait_until="domcontentloaded", timeout=30000)
        if response is None or response.status != 200 or page.url != base + "/demos":
            raise RuntimeError("Unexpected catalogue response or redirect.")
        page.get_by_role("heading", name="Demonstration cases", exact=True).wait_for(
            state="visible",
            timeout=30000,
        )
        button = page.get_by_role("button", name="New candidate demonstration", exact=True)
        button.wait_for(state="visible", timeout=30000)
        if not button.is_enabled():
            raise RuntimeError("The workspace is busy; finish the existing operation first.")
    except Exception as exc:
        raise RuntimeError(
            f"Browser could not open {base}/demos. Check the SSH tunnel and workspace. "
            f"No new case was created. {str(exc).splitlines()[0]}"
        ) from None


def voice_inventory(root: Path, powershell: str) -> dict:
    """Enumerate Enabled in the same executable used for synthesis."""
    script = root / "voice-inventory.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
        "Add-Type -AssemblyName System.Speech\n"
        "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "try {\n"
        " $voices = @($synth.GetInstalledVoices() | ForEach-Object {\n"
        "  @{name=$_.VoiceInfo.Name; gender=$_.VoiceInfo.Gender.ToString(); "
        "culture=$_.VoiceInfo.Culture.Name; enabled=$_.Enabled}\n"
        " })\n"
        " @{edition=$PSVersionTable.PSEdition; version=$PSVersionTable.PSVersion.ToString(); "
        "is64bit=[Environment]::Is64BitProcess; voices=$voices} | "
        "ConvertTo-Json -Depth 4 -Compress\n"
        "} finally { $synth.Dispose() }\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-File", str(script)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        inventory = json.loads(result.stdout.lstrip("\ufeff"))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise RuntimeError(f"Could not enumerate voices with {powershell}: {detail}") from None
    if not isinstance(inventory, dict) or not isinstance(inventory.get("voices"), list):
        raise RuntimeError("The speech host returned an invalid voice inventory.")
    for voice in inventory["voices"]:
        if (
            not isinstance(voice, dict)
            or type(voice.get("enabled")) is not bool
            or any(not isinstance(voice.get(key), str) for key in ("name", "gender", "culture"))
        ):
            raise RuntimeError("The speech host returned invalid voice information.")
    return inventory


def voice_candidates(inventory: dict, requested: str) -> list[str]:
    voices = inventory["voices"]
    enabled = [v for v in voices if v.get("enabled") is True and isinstance(v.get("name"), str)]
    if requested.casefold() != "auto":
        exact = [v["name"] for v in enabled if v["name"].casefold() == requested.casefold()]
        if exact:
            return exact[:1]
        available = ", ".join(v["name"] for v in enabled) or "none"
        raise RuntimeError(
            f"{requested!r} is not enabled in this speech host. "
            f"Enabled voices: {available}. Use --voice auto for an English male voice."
        )
    male = [
        v
        for v in enabled
        if v.get("gender", "").casefold() == "male"
        and (
            v.get("culture", "").casefold() == "en"
            or v.get("culture", "").casefold().startswith("en-")
        )
    ]
    preferred = ["Microsoft George", "Microsoft David Desktop", "Microsoft David", "Microsoft Mark"]
    male.sort(
        key=lambda v: (
            v.get("culture", "").casefold() != "en-gb",
            preferred.index(v["name"]) if v["name"] in preferred else len(preferred),
            v["name"].casefold(),
        )
    )
    names = list(dict.fromkeys(v["name"] for v in male))
    if not names:
        raise RuntimeError(
            "No enabled English male voice is available in this speech host. "
            "Use --list-voices to inspect Enabled and --powershell for another host."
        )
    return names


def make_audio(
    root: Path, voice_name: str = DEFAULT_VOICE, powershell: str = "powershell.exe"
) -> list[Path]:
    """Choose a usable male voice before browser/OBS actions; never install voices."""
    inventory = voice_inventory(root, powershell)
    candidates = voice_candidates(inventory, voice_name)
    print("Speech host:", powershell, inventory.get("edition"), inventory.get("version"))
    manifest = root / "speech.json"
    manifest.write_text(json.dumps(SPEECH), encoding="utf-8")
    script = root / "voice.ps1"
    script.write_text(
        "param($Manifest, $Folder, $VoiceName)\n"
        "$ErrorActionPreference='Stop'\n"
        "Add-Type -AssemblyName System.Speech\n"
        "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
        "try {\n"
        " $installed = @($voice.GetInstalledVoices() | Where-Object { "
        "$_.Enabled -and $_.VoiceInfo.Name -eq $VoiceName })\n"
        " if ($installed.Count -eq 0) { "
        "throw ('Voice is not installed or enabled: ' + $VoiceName) }\n"
        " $voice.SelectVoice($VoiceName)\n"
        " $voice.Voice.Name | Set-Content -LiteralPath "
        "(Join-Path $Folder 'selected-voice.txt') -Encoding UTF8\n"
        " $voice.Rate=-1\n"
        " $items=Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json\n"
        " for($i=0; $i -lt $items.Count; $i++) {\n"
        "  $voice.SetOutputToWaveFile((Join-Path $Folder ($i.ToString()+'.wav')))\n"
        "  $voice.Speak($items[$i]); $voice.SetOutputToNull()\n"
        " }\n"
        "} finally { $voice.Dispose() }\n",
        encoding="utf-8",
    )
    clips = [root / f"{i}.wav" for i in range(len(SPEECH))]
    selected = root / "selected-voice.txt"
    for candidate in candidates:
        for path in [*clips, selected]:
            path.unlink(missing_ok=True)
        try:
            subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-File",
                    str(script),
                    str(manifest),
                    str(root),
                    candidate,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
            actual = selected.read_text(encoding="utf-8-sig").strip()
            if actual.casefold() != candidate.casefold():
                raise ValueError("Speech host selected a different voice.")
            for clip in clips:
                with wave.open(str(clip)) as audio:
                    if audio.getnframes() <= 0 or audio.getframerate() <= 0:
                        raise ValueError("Speech host produced an empty audio clip.")
            print("Selected narration voice:", actual)
            return clips
        except (subprocess.CalledProcessError, OSError, EOFError, wave.Error, ValueError) as exc:
            print(f"Voice {candidate!r} could not synthesise the narration.")
            if voice_name.casefold() != "auto":
                detail = getattr(exc, "stderr", None) or str(exc)
                raise RuntimeError(f"Speech generation failed for {candidate}: {detail}") from None
    raise RuntimeError(
        "None of the enabled English male voices could produce valid audio. "
        "No browser case or recording was started. Run --list-voices for diagnostics."
    )


def assert_case(page, counts: list[str], case_id: str | None = None) -> str:
    identity = page.locator(".case-identity")
    if "Authored demonstration" not in identity.inner_text():
        raise RuntimeError("Expected an explicitly authored demonstration.")
    actual = identity.locator("code").first.inner_text()
    if not actual.startswith("demo-") or (case_id and actual != case_id):
        raise RuntimeError("Case identity changed unexpectedly.")
    if page.locator(".metric strong").all_text_contents() != counts:
        raise RuntimeError("Unexpected review counts; preserve the case and stop.")
    return actual


def mute_recording_audio(request, captures, original: dict[str, bool]) -> None:
    """Mute this scene's Windows audio and global channels, retaining exact states.

    GetInputList covers other scenes as well. Their inactive microphones must
    neither prevent a take nor have their configuration changed for this scene.
    Read every relevant mute state before the first mutation so a failed read
    leaves the original configuration intact.
    """
    names = {
        item["sourceName"]
        for item in captures
        if item["sceneItemEnabled"] and "wasapi" in item.get("inputKind", "")
    }
    special = request("GetSpecialInputs")
    names.update(
        name
        for key in ("desktop1", "desktop2", "mic1", "mic2", "mic3", "mic4")
        if isinstance(name := special.get(key), str) and name
    )
    snapshot = {}
    for name in sorted(names):
        muted = request("GetInputMute", inputName=name).get("inputMuted")
        if type(muted) is not bool:
            raise RuntimeError(f"OBS did not report a valid mute state for {name!r}.")
        snapshot[name] = muted
    original.update(snapshot)
    for name, muted in snapshot.items():
        if not muted:
            request("SetInputMute", inputName=name, inputMuted=True)
            if request("GetInputMute", inputName=name).get("inputMuted") is not True:
                raise RuntimeError(f"OBS did not mute {name!r}; recording has not started.")


def restore_recording_audio(request, original: dict[str, bool]) -> list[str]:
    """Restore only inputs this launcher needed to mute; try every restoration."""
    failed = []
    for name, muted in original.items():
        if not muted:
            try:
                request("SetInputMute", inputName=name, inputMuted=False)
                if request("GetInputMute", inputName=name).get("inputMuted") is not False:
                    raise RuntimeError("Mute restoration was not confirmed.")
            except Exception:
                failed.append(name)
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8081")
    parser.add_argument(
        "--voice",
        default=DEFAULT_VOICE,
        help="auto selects an enabled English male voice; or give an exact voice name",
    )
    parser.add_argument(
        "--powershell", default="powershell.exe", help="Speech host executable path"
    )
    parser.add_argument("--list-voices", action="store_true", help="List this host's Enabled flags")
    parser.add_argument(
        "--record", action="store_true", help="Enable capture and simulated confirmation"
    )
    args = parser.parse_args()
    base = local_url(args.url)
    if os.name != "nt":
        raise RuntimeError("Run this launcher on the Windows laptop, not on EC2.")
    with tempfile.TemporaryDirectory(prefix="mwalimulens-voice-") as temp:
        if args.list_voices:
            print(json.dumps(voice_inventory(Path(temp), args.powershell), indent=2))
            return
        print("Checking the private teacher workspace:", base)
        check_portal(base)
        audio = make_audio(Path(temp), voice_name=args.voice, powershell=args.powershell)
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                channel="chrome",
                headless=False,
                args=["--start-maximized", "--no-proxy-server"],
            )
            context = browser.new_context(no_viewport=True)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.set_default_navigation_timeout(30000)
            page.route(
                "**/*",
                lambda route: (
                    route.continue_() if route.request.url.startswith(base + "/") else route.abort()
                ),
            )
            open_catalogue(page, base)
            print("Chrome is open. Existing case records have not been changed.")
            if not args.record:
                print("Preflight only: no recording, case creation or confirmation.")
                input("Inspect the browser. Press Enter to close this automated window: ")
                browser.close()
                return
            page.get_by_role("button", name="New candidate demonstration", exact=True).click()
            case_id = assert_case(page, ["1", "0", "0"])
            obs = ObsController(password=getpass.getpass("Local OBS WebSocket password: "))
            request = obs._request
            source = "Hosted narration " + uuid.uuid4().hex
            source_created = False
            recording = False
            audio_before: dict[str, bool] = {}
            try:
                if request("GetCurrentProgramScene")["currentProgramSceneName"] != SCENE:
                    raise RuntimeError(f"Select the OBS scene {SCENE!r}.")
                if request("GetRecordStatus")["outputActive"]:
                    raise RuntimeError("OBS is already recording. Stop that take manually first.")
                if request("GetStreamStatus")["outputActive"]:
                    raise RuntimeError(
                        "Stop streaming before recording this private demonstration."
                    )
                captures = request("GetSceneItemList", sceneName=SCENE)["sceneItems"]
                visible = [
                    item
                    for item in captures
                    if item["sceneItemEnabled"] and "wasapi" not in item.get("inputKind", "")
                ]
                if len(visible) != 1 or visible[0].get("inputKind") != "window_capture":
                    raise RuntimeError("Use one visible Window Capture source in this new scene.")
                print(
                    f"Fresh authored case: {case_id}. It will be revised and explicitly confirmed."
                )
                print(
                    "In OBS, select THIS automated Chrome window under Window Capture Properties."
                )
                print("Check readable framing; recording folder must be outside the repository.")
                print("Active microphone/desktop inputs will be muted for this take and restored.")
                print("Listen to the generated voice test before proceeding:", audio[0])
                os.startfile(str(audio[0]))
                if input("After playback ends and framing is correct, type RECORD: ") != "RECORD":
                    return
                if request("GetCurrentProgramScene")["currentProgramSceneName"] != SCENE:
                    raise RuntimeError("OBS scene changed during preparation. Start again.")
                if request("GetRecordStatus")["outputActive"]:
                    raise RuntimeError("Another recording started during preparation. Stop here.")
                captures = request("GetSceneItemList", sceneName=SCENE)["sceneItems"]
                mute_recording_audio(request, captures, audio_before)
                request(
                    "CreateInput",
                    sceneName=SCENE,
                    inputName=source,
                    inputKind="ffmpeg_source",
                    sceneItemEnabled=True,
                    inputSettings={
                        "is_local_file": True,
                        "local_file": str(audio[0]),
                        "looping": False,
                        "restart_on_activate": False,
                    },
                )
                source_created = True
                request(
                    "TriggerMediaInputAction",
                    inputName=source,
                    mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_STOP",
                )
                request(
                    "SetInputAudioTracks",
                    inputName=source,
                    inputAudioTracks={str(i): i == 1 for i in range(1, 7)},
                )
                request(
                    "SetInputAudioMonitorType",
                    inputName=source,
                    monitorType="OBS_MONITORING_TYPE_NONE",
                )
                page.bring_to_front()
                recording = True  # A timeout may occur after OBS accepts StartRecord.
                request("StartRecord")
                for index, clip in enumerate(audio):
                    if index == 1:
                        page.locator("#evidence-EV-008").scroll_into_view_if_needed()
                    elif index == 2:
                        page.get_by_role("radio", name="Revise").check()
                        page.locator("#reason").fill(REASON)
                        page.locator("#edited").fill(WORDING)
                        page.get_by_role("button", name="Review decision").click()
                        page.get_by_text("Not saved yet", exact=True).wait_for()
                    elif index == 3:
                        page.get_by_role("button", name="Confirm simulated decision").click()
                        assert_case(page, ["0", "1", "1"], case_id)
                        page.locator("#decision").scroll_into_view_if_needed()
                    elif index == 4:
                        page.get_by_role("link", name="Demonstration cases", exact=True).click()
                        page.get_by_role("row").filter(has_text=case_id).get_by_role(
                            "button", name="Open demonstration"
                        ).click()
                        assert_case(page, ["0", "1", "1"], case_id)
                        if REASON not in page.inner_text("body") or WORDING not in page.inner_text(
                            "body"
                        ):
                            raise RuntimeError("Saved decision text did not survive reopening.")
                    elif index == 5:
                        page.locator("#decision").scroll_into_view_if_needed()
                    request(
                        "SetInputSettings",
                        inputName=source,
                        overlay=True,
                        inputSettings={"local_file": str(clip)},
                    )
                    request(
                        "TriggerMediaInputAction",
                        inputName=source,
                        mediaAction="OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART",
                    )
                    with wave.open(str(clip)) as wav:
                        duration = wav.getnframes() / wav.getframerate()
                    if index == 1:
                        page.wait_for_timeout(duration * 500)
                        page.locator("#evidence-EV-011").scroll_into_view_if_needed()
                        page.wait_for_timeout((duration / 2 + 2) * 1000)
                    else:
                        page.wait_for_timeout((duration + 2) * 1000)
                output = request("StopRecord")["outputPath"]
                recording = False
                print("Saved:", output)
                print("Reopened case verified:", case_id, "counts 0/1/1.")
                print("Watch the entire video: capture, sound and timing require visual review.")
            finally:
                if recording:
                    try:
                        request("StopRecord")
                        recording = False
                    except Exception:
                        print(
                            "Check OBS and stop recording manually. Do not delete the saved case."
                        )
                if source_created:
                    try:
                        request("RemoveInput", inputName=source)
                    except Exception:
                        print(
                            "Remove the temporary Hosted narration source in this scene manually."
                        )
                if not recording:
                    failed = restore_recording_audio(request, audio_before)
                    if failed:
                        print("Restore these originally unmuted inputs in OBS:", ", ".join(failed))
                elif any(not muted for muted in audio_before.values()):
                    print(
                        "Audio remains muted because stopping the recording was not confirmed. "
                        "Stop OBS manually, then restore the originally unmuted inputs: "
                        + ", ".join(name for name, muted in audio_before.items() if not muted)
                    )
                obs.close()
                browser.close()


def cli() -> None:
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Recording launcher stopped: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        if not type(exc).__module__.startswith("playwright."):
            raise
        print(
            "Browser automation stopped: " + str(exc).splitlines()[0] + ". "
            "A submitted action may have been saved; inspect the current case before "
            "starting another take. Actions have not been retried.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    cli()
