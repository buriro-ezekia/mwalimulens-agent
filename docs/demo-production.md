# Windows demo production guide

For the final male narration asset and automated OBS take, use
[final recording automation](final-recording-automation.md). The guide below covers the
alternative human-voiced manual recording; its timing and microphone settings differ.

Use this to prepare a **single continuous 2:30–2:45 take**, targeting 2:40 and strictly under
3:00. The project owner records locally with their own voice. No recording or upload is performed
by this package, and no audio/video files belong in this repository.

Start here for setup; use the [storyboard](demo-guide.md#time-coded-storyboard) for the screen
sequence, [narration and voice rehearsal](demo-narration.md) for speech, and the
[operator cue sheet](demo-operator-cues.md) beside the screen during the take. Finish with the
[checklist](demo-checklist.md) and [YouTube upload package](youtube-package.md).

## 1. Prepare the reviewed revision

Open PowerShell in the repository root. While PR #24 is draft, use its
`codex/issue-23-recording-package` branch at the latest reviewed commit. After it is merged, use
the corresponding `main` revision. Check before recording; do not switch away from unfinished
local work or discard it:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
```

Note the branch and commit on your private cue sheet. If the environment needs preparing, run
this off camera (Python 3.11+ and Node.js 20+ with npm are required):

```powershell
python scripts/run_demo.py --no-open
.\.venv\Scripts\python.exe --version
```

Now rehearse the actual recording command, including its automatic browser launch:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.demo_run
```

Require `DEMO RUN: PASS`, three successful MCP calls, `pending_teacher_review`, one pending
candidate, zero teacher decisions and zero profile updates. Check that the freshly generated
browser page opens on the display you will capture. Close old demo tabs before the real take.
This is a deterministic model driving real MCP tools. It reads the committed Qwen proof; it
does not run Qwen. Do not start the slow challenge/open-weights workflow for this recording.

## 2. Set the recording frame and sound

These are production settings for this demo, usable with any recorder that can capture both
the terminal and browser continuously:

| Setting | Use for this take |
|---|---|
| Frame | Landscape, 1920 × 1080, 30 fps. Prefer a 1080p display or capture region; inspect the output if scaling a larger display. |
| Capture | One display/region containing both terminal and browser; one scene throughout. |
| Voice | Microphone enabled; select the intended device explicitly. |
| Other audio | Disable desktop/system audio and unused inputs. No music or notification sounds. |
| Text | Start at about 110% browser zoom. Enlarge terminal text until command and summary are legible in the saved video. |
| Pointer | Visible, normal size. Point once, then park it in a blank margin; no circling or click effects. |
| Workspace | Disable notifications for the take; close unrelated tabs/windows. Put the default browser on the captured display. |
| Notes | Printed sheet or a second, uncaptured display; never inside the captured region. |
| Output folder | Choose a local folder outside the repository, such as `Videos\MwalimuLens`, and check free space. |

Check space in File Explorer's **This PC** before rehearsal. Allow room for several takes and
both the original and upload copy; check the test file's size rather than assuming a fixed bitrate.
The final screen-legibility check decides the zoom, not the suggested percentage. Keep the full
counter-observation, exact tool names and all three human-gate counts readable.

If the long repository path crowds the command, use a short prompt in this recording terminal
only, then clear the setup logs. This does not change your PowerShell profile or working directory:

```powershell
function prompt { 'MwalimuLens> ' }
Clear-Host
```

Paste the exact live command at the prompt, but **do not press Enter yet**.

## 3. OBS Studio example

Other recorders are fine if they preserve the same frame, microphone and continuous capture.
OBS users can follow this minimal setup; menu wording may vary slightly by version.

1. Create one scene named `MwalimuLens`. In **Sources → + → Display Capture**, choose the
   recording display and enable **Show Cursor**. Fit the source to the canvas without clipping
   the terminal or browser. Keep the same scene for the entire take. OBS supports full-display
   capture and a cursor toggle. [OBS Display Capture](https://obsproject.com/kb/display-capture-sources)
2. In **Settings → Video**, set **Base (Canvas) Resolution** and **Output (Scaled) Resolution**
   to `1920x1080`, and **Common FPS Values** to `30`. Use a matching capture display where
   possible; check text after scaling. In **Settings → Hotkeys**, assign separate **Start
   Recording** and **Stop Recording** shortcuts that do not conflict with the terminal/browser.
   Test both with those apps focused. [OBS settings overview](https://obsproject.com/eu/wiki/obs-studio-overview)
3. In **Settings → Audio**, choose your microphone under **Mic/Auxiliary Audio**. Disable
   **Desktop Audio** and unused audio devices. Speak and check the Audio Mixer for activity;
   lower input volume if loud words clip. OBS can capture desktop audio and microphone by
   default, so check both deliberately. [OBS quick start](https://obsproject.com/kb/quick-start-guide)
4. Use just one microphone capture route. If you selected it globally in Settings, do not also
   add the same microphone as an **Audio Input Capture** source; that can produce an echo.
   [OBS audio sources](https://obsproject.com/kb/audio-sources)
5. In **Settings → Output**, choose **Simple** output mode. Set **Recording Path** to the folder
   outside the repository, choose **High Quality, Medium File Size**, an available **H.264**
   encoder (hardware if available, otherwise x264), and **AAC** audio if the choice is shown.
   Select **MKV** as the recording format. OBS recommends MKV for resilience if recording is
   interrupted. [OBS recording output guide](https://obsproject.com/kb/standard-recording-output-guide)
6. Test a short microphone-and-screen clip. Move OBS to an uncaptured display or minimise it
   before starting via the tested hotkey. The captured opening must be the terminal, without
   the recorder preview appearing inside its own capture. Do not use pause, scene transitions,
   an intro, an outro or a second scene.

After the successful take, use **File → Remux Recordings**: select the MKV, choose the MP4 output
beside it, then click **Remux**. This changes the container without cutting, speeding up or
re-recording the take. Keep the original locally and verify the MP4 from start to finish before
upload. [OBS remux instructions](https://obsproject.com/kb/standard-recording-output-guide#remuxing)

## 4. Rehearse before the final take

Complete all three checks in the [voice rehearsal guide](demo-narration.md#delivery-and-rehearsal-notes):

- **Microphone playback:** record a short test locally, then listen. Use your normal accent and
  conversational volume; check clarity, background noise, echo, clipping and the two zero counts.
- **Screen legibility:** play back a test at normal viewing size. Read the counter-observation,
  three tool names, pending status, zero counts and Qwen evidence path without zooming the player.
- **Full stopwatch rehearsal:** speak the complete script while running the command and moving
  through every section. Time from capture start to capture stop, including the final hold.

Address one judge; do not perform an announcer voice. Breathe between ideas, vary the pace a
little, and let the counter-evidence and zero counts land. If a sentence feels awkward, rewrite
it and re-time the script. If the rehearsal exceeds 2:45, shorten wording or navigation rather
than speaking faster. Preserve every required proof point. Do not remove the limitation or gate.

**Keep PR #24 as draft until the owner has completed both the browser visual playback check and
the full timed spoken rehearsal.** A passing test suite is not a substitute for either check.

## 5. Record the take

Use the [operator cue sheet](demo-operator-cues.md). Times are landmarks, not a requirement to
hit each second perfectly. Small shifts are fine if the complete take stays at 2:30–2:45.

1. **0:00 — start:** terminal visible, command ready but unexecuted, microphone on. Start
   recording with the tested hotkey. Let the recording begin before pressing Enter.
2. **About 0:02 — run:** press Enter on the exact command and begin the introduction. Narrate
   while the real MCP work runs; do not type another command or show installation logs.
3. **When PASS appears — hold:** leave the live terminal summary visible for about two seconds.
   If the browser takes focus automatically, switch back briefly to show PASS, then return to
   the newly generated page. Aim to be at the browser by about 0:25.
4. **About 0:25 — Evidence:** use the Evidence link. Follow the assessment trend, then hold
   EV-008's full counter-observation for at least four seconds. Keep supporting rows visible.
5. **About 0:55 — MCP activity:** show all three audited SUCCESS calls. Then use **Candidate**
   around 1:22 and **Human gate** around 1:43. Hold the actual status and uncertainty, followed
   by the one/zero/zero counts. Do not take any teacher review action.
6. **About 2:03 — Separate validation:** show the earlier real Qwen PASS with its committed
   evidence path. Leave the preserved historical-failure count visible. Move to **Limitation**
   around 2:25.
7. **About 2:38 — finish:** complete the last spoken sentence on the limitation. Stop moving
   the pointer and leave a quiet **two-second visual hold**.
8. **About 2:40 — stop:** use the tested stop hotkey while the limitation stays visible. Check
   the saved file's duration; the recording includes the opening and closing holds.

If a call fails, the page does not open, or startup is so slow that the take cannot fit calmly,
stop and resolve it off camera. Close stale pages and make a new whole take. A minor pause is
normal; never rescue a broken/overlong take with cuts, speed-ups, inserted screenshots or
transitions. Do not rerun Qwen, alter evidence or resolve the candidate for visual effect.

## 6. Prepare the upload copy

Watch the final MP4 all the way through and complete the [recording checklist](demo-checklist.md).
It must be strictly under 3:00, with no added title sequence or credits. Use the filename,
description and upload verification in [the YouTube package](youtube-package.md). All local
tests, takes and remuxed copies stay outside the repository. Keep the video requirement
**Ready to record** until the real public link and duration have been verified.
