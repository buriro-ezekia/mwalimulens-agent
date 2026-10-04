# Automated final recording on Windows

Run `scripts/record-final-demo.ps1` to coordinate one genuine live OBS capture. It starts the
supplied narration, executes the real fast MCP command, guides the generated browser page and
stops around **2:39**. It never uploads, edits footage or updates submission status.

The final narration is the owner-supplied **“MwalimuLens final male 2m35 narration”** asset.
Its verified duration is **156.48 seconds (2:36.48)** despite the asset's short name. This
automation uses that asset and the timetable below, not the earlier human-read script's timing.
The [manual production guide](demo-production.md) remains an alternative for a human-voiced take.

## Prepare once, off camera

1. Use Windows, Python 3.11+, Node.js 20+ and the existing repository environment. Prepare the
   fast demo and install the small optional OBS client into `.venv`:

   ```powershell
   python scripts/run_demo.py --no-open
   .\.venv\Scripts\python.exe -m pip install -e ".[record]"
   ```

   The optional dependency is `obsws-python>=1.8,<2`; the ordinary demo does not need it.
   [OBS client library](https://github.com/aatikturk/obsws-python)
2. Install/open [OBS Studio](https://obsproject.com/download). Use OBS with its version 5
   WebSocket server (included in OBS 28+). Under **Tools → WebSocket Server Settings**, enable
   the server, retain authentication and use port **4455**. The launcher connects only to
   `127.0.0.1`; do not expose the port to other machines. It prompts privately for the password.
   Never put the password in a script, command argument, commit or screenshot. An existing
   process-only `OBS_WEBSOCKET_PASSWORD` environment variable is also accepted, and is stripped
   from the live MCP subprocess environment. [OBS WebSocket](https://github.com/obsproject/obs-websocket)
3. Install a Windows build of FFmpeg from the options linked on the
   [official FFmpeg download page](https://ffmpeg.org/download.html), and make `ffprobe.exe`
   available on PATH. Alternatively pass `-Ffprobe 'C:\path\to\ffprobe.exe'`. The launcher only
   reads metadata; it never converts or generates media. Check availability with:

   ```powershell
   ffprobe -version
   ```

   Duration, audio/video streams, dimensions and frame rate are checked using
   [ffprobe's JSON output](https://ffmpeg.org/ffprobe.html).
4. Download the final male narration from the project conversation/attachment where it was
   supplied, or copy your existing downloaded MP3. Save it **outside this repository**, for
   example in your Windows `Videos\MwalimuLens` folder. Supply that actual path; there is no
   public narration download URL in this repository. If the asset is missing, obtain that
   exact asset from the project owner before proceeding. Do not substitute new TTS, retime it,
   commit it, or claim that a matching duration alone proves its spoken content.
5. Listen to the MP3 once. Confirm it is the intended final narration and that its content
   matches the live workflow, counter-evidence, teacher gate and separate Qwen explanation.
   The launcher requires an MP3 audio stream and duration within 0.75 seconds of 156.48.

## Prepare the dedicated OBS scene

The launcher validates a scene you prepare; it does not overwrite your OBS profile, other
scenes or recording settings. Use these exact names:

| Item | Required setup |
|---|---|
| Scene | `MwalimuLens Final`, selected as the current scene; Studio Mode off. |
| Display source | `MwalimuLens Display`, **Display Capture**, showing the monitor used for both terminal and browser. Cursor enabled. Place it above the narration in the source stack. |
| Framing | Fit Display Capture to the whole canvas: position at the top-left, no crop, rotation, flip or bounding box. Use Transform → Fit to Screen, then inspect Edit Transform. |
| Narration source | `MwalimuLens Narration`, **Media Source**, Local File set to the supplied MP3. Enabled in the scene; beneath the display so embedded cover art cannot cover the live page. |
| Media controls | Loop off; Restart playback when source becomes active off; Close file when inactive off; speed 100%. Play briefly, then pause so OBS has loaded its duration. |
| Video | Settings → Video: canvas and output both **1920 × 1080**, **30 fps**. |
| Output | Prefer Simple output, **High Quality, Medium File Size**, H.264 video, AAC audio, **MKV**. Hybrid MP4 is also accepted. Recording **track 1 only**; no rescaling or overwrite-existing. |
| Recording folder | Existing local folder outside this repository, with at least **2 GiB** free. |
| Audio | Narration unmuted at a normal audible level; Advanced Audio Properties: Track 1 enabled, Monitor Off, sync offset 0. |
| Other sources/audio | No other enabled scene sources or source/scene filters. Disable or mute global Desktop Audio and Mic/Aux. No music. Stop streaming, Replay Buffer and Virtual Camera. |

If you explicitly need a live microphone, add one named Audio Input Capture source and pass
its name with `-Microphone 'MwalimuLens Microphone'`. It must also use track 1, Monitor Off and
zero sync offset. Otherwise the microphone stays muted. Avoid recording the narration twice
through desktop audio or microphone monitoring. OBS media and input settings are checked through
the [version 5 protocol](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md).

Use a 1080p monitor where possible. Start browser zoom near 110%, enlarge terminal text, disable
notifications and close unrelated windows. Put OBS and notes on an uncaptured display or minimise
them. The owner must inspect OBS preview to confirm the chosen monitor and readable framing;
software cannot establish those visual facts from OBS settings alone.

## Check the revision and launch

Final recording requires a clean tracked checkout on `main`, matching fetched `origin/main` and
the **full reviewed commit SHA** supplied by the owner. The launcher never fetches, switches,
commits or discards files. After this change is merged, update main off camera and note the SHA:

```powershell
git fetch origin main
git switch main
git pull --ff-only origin main
git rev-parse HEAD
```

Resolve your own local changes before switching; untracked historical evidence is left alone.
Replace the example path and `REVIEWED_40_CHARACTER_MAIN_SHA` below with the actual values:

```powershell
.\scripts\record-final-demo.ps1 `
  -NarrationPath 'C:\Users\YOUR_NAME\Videos\MwalimuLens\MwalimuLens_final_male_2m35.mp3' `
  -ExpectedCommit 'REVIEWED_40_CHARACTER_MAIN_SHA'
```

For nonstandard installations add `-ObsExe 'C:\path\to\obs64.exe'`, `-ObsPort 4455` or
`-Ffprobe 'C:\path\to\ffprobe.exe'`. Open OBS yourself first. The launcher checks installed OBS,
the local connection, scene, audio routing, media duration, free space and prepared dependencies.

It runs the real fast demo once **off camera**, requires PASS, and opens its rehearsal page.
The local browser service serves only the generated demo HTML at an unguessable loopback URL.
After inspecting the page and OBS preview, return to the captured terminal. Type **RECORD** when
ready; there is a five-second countdown. This is the only start confirmation inside the launcher.
Anything else cancels without recording. Close stale demo tabs before starting.

## What happens during the take

| Recording time | Automatic action |
|---|---|
| 0:00 | Start OBS, confirm recording, restart narration from the beginning. |
| About 0:02 | Print and execute `.\.venv\Scripts\python.exe -m mwalimulens.demo_run` in the captured terminal. These are real custom Education and borrowed read-only Filesystem MCP calls. |
| About 0:20–0:24 | Hold the actual `DEMO RUN: PASS` summary for at least two seconds. Open the fresh live page at about 0:22, or two seconds after completion if slightly later. |
| 0:31 | Scroll to Evidence: synthetic learner and fraction assessment trend. |
| 0:43 | Centre EV-008's counter-observation about independent explanation. |
| 0:58 | MCP activity: `get_competency_evidence`, `read_text_file`, `flag_pattern_for_review`. |
| 1:23 | Candidate: actual `pending_teacher_review`, claim, uncertainty and teacher question. |
| 1:43 | Human gate: **1 pending / 0 decisions / 0 updates**. No review action is offered or taken. |
| 1:59 | Separate committed real Qwen2.5 3B PASS and preserved historical evaluation failures. |
| 2:21 | Real-classroom validation limitation. |
| 2:36.48 | Narration finishes naturally. |
| About 2:39 | Stop OBS, confirm finalisation, inspect the saved file and print its path/duration. |

The page is the HTML generated by the captured MCP run, with a small navigation script added
in memory. No screenshots, replacement footage, cuts, speed changes, transitions or second scene
are used. The preflight page is invalidated before the live run and cannot satisfy live checks.
The browser must stay visible and focused from the Evidence section onward. Do not click other
windows or scroll during the take. Its local heartbeat confirms the scheduled section remains
in view; it does not prove that the correct monitor was captured.

## Failure handling and remaining owner actions

Any failed prerequisite prevents recording. A failed/slow live command, missing browser, hidden
page, narration drift, scene/audio change, paused recording or failed stop invalidates the take.
The helper attempts to stop only its own recording and child process tree. Partial files remain
in the chosen video folder for inspection; they are never presented as valid or uploaded.
If OBS becomes unreachable or a start/stop cannot be confirmed, an explicit **stop recording
in OBS now** message appears. Stop it manually; do not reuse that partial take. After a transport
timeout, the connection is discarded to avoid trusting delayed responses. Resolve the cause and
restart the launcher for a new whole capture.

A successful automated check requires a **fresh** nonempty MKV/MP4, one H.264 1080p30 video
stream, one AAC audio stream, and measured duration between **157 and 165 seconds**, always
strictly under 180 seconds. Those are machine checks, not a claim of a finished submission.
Watch the whole result to verify sound, legibility, terminal PASS, every required evidence point
and the ending. Keep the narration and all recordings outside the repository. For MKV, use OBS
File → Remux Recordings to create an MP4 without cutting/re-encoding the take, then check it again.

Upload yourself using the [YouTube package](youtube-package.md). Only after the real public URL,
HD processing, duration and signed-out playback are verified should the three submission
documents change from **Ready to record** to **Present**. All promoted evidence and historical
failures remain unchanged. The deterministic capture never becomes the Qwen model evidence.

## Non-recording checks

Run this safe dry run without narration, OBS connection or recording. It exercises the real
off-camera MCP preflight and prints the timed plan; it does **not** validate media or OBS hardware:

```powershell
.\scripts\record-final-demo.ps1 -DryRun
```

Add `-PreflightOnly` to the full launch command to validate the prepared narration, OBS and
browser without recording. On an unmerged review branch, this mode alone also accepts
`-AllowReviewBranch` with its exact reviewed commit SHA. Final takes must use `main`.

Before owner testing, review the complete diff, then run the full suite, Ruff and the dry run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\scripts\record-final-demo.ps1 -DryRun
```

Tests use simulated clocks/OBS responses for failure cases; they do not generate media or serve
as live recording evidence. A real OBS/narration/browser take still requires the owner's local
setup and playback check. Do not label either simulation or dry-run output as a final video.
