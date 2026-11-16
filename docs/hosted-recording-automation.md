# Hosted review recording launcher

This new launcher records the authored teacher-review sequence through the
existing private SSH tunnel. It selects a usable installed Windows English male
voice, rather than the previous narration asset or a paid speech service. It makes no model
request. Keep the original submitted video and its recording launcher unchanged.

Status: URL, case-identity, counts and scoped audio mute/restoration checks are
automated. Windows speech, Chrome capture, OBS audio and actual exported footage
require owner acceptance.
This is a prepared launcher, not evidence that a video has been captured.

## Prepare on the Windows laptop

Keep the SSH tunnel open at http://127.0.0.1:8081. Close other teacher-workspace
tabs during capture because this prototype has one current case per server.
The launcher first makes a five-second, no-proxy, no-redirect GET of `/demos` and
checks the catalogue markers. Failure stops before speech, Chrome, case creation
or OBS. HTTP 403 points to the remote browser-port setting; a connection timeout
or refusal points to the SSH tunnel or remote workspace. An unrelated application
on the local port is rejected. The probe does not create or change a saved case.

An observed browser timeout waited for the full load event. The browser now uses
DOMContentLoaded with a 30-second navigation deadline and then checks the exact
catalogue heading and enabled candidate button. The isolated browser bypasses
proxies. The portal catalogue has inline CSS and no external script/image
dependencies; that timeout alone does not establish a resource-loading cause.
Submitted form actions are never automatically retried after an uncertain error.

To check the existing tunnel from Windows without starting a recording:

```powershell
curl.exe --noproxy '*' --connect-timeout 5 --max-time 10 -f -sS -o NUL -w 'HTTP %{http_code}\n' http://127.0.0.1:8081/demos
```

Expect HTTP 200. If it times out, restart the existing SSH tunnel and keep its
window open. Use ServerAliveInterval=15 and ServerAliveCountMax=3 to detect stale
SSH connections. See [private hosting](application-hosting.md) for the tunnel
and saved-case recovery commands; do not provision another instance or reset cases.

Install the optional recording and browser dependencies in the existing venv:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[record]" "playwright>=1.49,<2"
```

Installed Google Chrome is used; no Playwright browser download is needed.
The earlier operator voice list showed names without Enabled flags. George
appeared in that list but was unavailable in the launcher's speech process.
The launcher now enumerates names and Enabled in the exact executable it uses
for synthesis. Default `--voice auto` prefers an enabled UK English male voice,
then available English male voices such as Microsoft David Desktop. If a
candidate cannot produce a complete set of valid WAV clips, auto tries the next
enabled English male voice. It reports the actual selected name and validates
every clip before opening Chrome or creating a case. No female voice is
automatically substituted, and a named `--voice` remains strict.

Use the PowerShell executable from the current session to avoid host/runtime
differences between an interactive voice list and synthesis:

```powershell
$hostedSpeechHost = (Get-Process -Id $PID).Path
.\.venv\Scripts\python.exe scripts/record-hosted-review.py --record --voice auto --powershell $hostedSpeechHost
```

For a diagnostic list from that same process type, including Enabled flags:

```powershell
.\.venv\Scripts\python.exe scripts/record-hosted-review.py --list-voices --powershell $hostedSpeechHost
```

Listing does not synthesise speech, open Chrome, create a case or start OBS.
The launcher does not install voices, alter the registry, change system defaults
or use Runway. This is a free male-voice fallback, not an exact James voice match.

For another installed voice, pass its exact name, for example:

```powershell
.\.venv\Scripts\python.exe scripts/record-hosted-review.py --record --voice 'Microsoft David Desktop'
```

Each screen stage still waits for the measured duration of its own WAV clip.
Changing the voice therefore changes the recording duration without forcing
the narration into the timing of the previous take. Listen to the sample before
typing RECORD.

In OBS select **MwalimuLens Hosted Review**. Use one visible Window Capture source.
There is no need to mute inputs manually. After the RECORD prompt, the launcher
temporarily mutes enabled Windows audio inputs in this scene and the global
desktop/microphone channels, then restores their original states when the take
stops. Inactive microphones in other scenes are not inspected or changed. Already
muted inputs stay muted. The earlier version inspected every Windows audio input
across all scenes and could refuse a take unnecessarily; this version fixes that
overbroad check.
In Settings choose 1920 x 1080 at 30 fps, a recording folder outside the repository,
MKV and audio track 1. Under Tools > WebSocket Server Settings, enable the local
server on port 4455 and retain authentication. Enter its password only at the
launcher's private prompt. Do not paste it into chat or a command.

First run without capture:

```powershell
.\.venv\Scripts\python.exe scripts/record-hosted-review.py
```

This generates temporary narration and opens a separate automated Chrome window
at the catalogue. It does not create a case, record or confirm a decision.
Press Enter at its prompt to close that window.

Then run the take:

```powershell
.\.venv\Scripts\python.exe scripts/record-hosted-review.py --record
```

It creates a new authored candidate and prints its case ID. It never resets the
already-reviewed demonstration. Select this **new automated Chrome window** in
OBS Window Capture Properties and fit it to the canvas. The old window selection
may not follow the new browser. Inspect the preview yourself: the launcher cannot
prove that the selected source captures the correct window or readable text.

The first narration segment opens in the default audio player. Listen, then
close that player after playback ends. Type **RECORD** at the prompt only when
the voice and frame are acceptable. The launcher starts OBS, narrates the evidence,
fills Revise, shows the unsaved preview, confirms the simulated decision and
reopens the exact same case. Counts must change from 1/0/0 to 0/1/1; saved wording
and reason must match. These automated clicks are operator-driven demonstration
actions, not model autonomy or a qualified teacher's assessment.

The launcher uses a temporary OBS narration source and removes it afterwards.
It prints the recording path on completion. Speech duration depends on the
installed voice; the original 2:35 storyboard is not a measured duration here.
If a failure occurs after confirmation, retain the decided case and partial
recording. Do not edit state to reset it. Check OBS manually if its connection
fails, and stop any remaining recording before another attempt. If the launcher
cannot confirm that recording stopped, it leaves the affected audio muted and
prints the originally unmuted input names. Restore those only after stopping
the recording. A disconnected or forcibly terminated process cannot guarantee
automatic restoration; follow any displayed recovery instructions.

Watch the whole recording for correct window, readable disclosures, voice,
matching screen actions and retained single note. Use File > Remux Recordings
for MP4, then verify the MP4. No automatic upload or submission replacement is
performed. Keep the earlier submitted link authoritative unless an update is
requested and the replacement is separately accepted.
