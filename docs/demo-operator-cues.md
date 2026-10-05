# Operator cue sheet — target 2:40

Keep outside capture. Approximate landmarks; do not rush to catch a second.
Full setup: [production guide](demo-production.md). Spoken words: [narration](demo-narration.md).
This cue sheet is for the manual human-voiced workflow. For the validated prerecorded narration
workflow, use [final recording automation](final-recording-automation.md) and keep the microphone muted.

```text
BEFORE       Mic on · command ready · notes off screen
0:00         START RECORDING
~0:02        Press Enter · begin introduction
On PASS      Hold terminal result for 2 seconds
~0:25        Browser → Evidence
             Point to assessment trend: 61 → 78 → 84 → 87
~0:40        Hold counter-evidence: independent explanation
             Keep full EV-008 note visible for 4 seconds
~0:55        MCP activity → show 3 SUCCESS calls
~1:22        Candidate → pending_teacher_review + uncertainty
~1:43        Human gate → 1 pending / 0 decisions / 0 updates
~2:03        Separate validation → real Qwen PASS + source path
             Keep historical failures visible
~2:25        Limitation
~2:38        Finish sentence · pointer still
             2-second quiet hold
~2:40        STOP RECORDING
```

Live command — press Enter only after recording has started:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.demo_run
```

Failed run or projected finish beyond 2:45: stop, fix/rehearse off camera, start a fresh whole
take. No teacher actions, cuts, pauses in capture, speed-ups, transitions or inserted screenshots.
