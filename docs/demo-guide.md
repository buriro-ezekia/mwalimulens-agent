# Final demo recording guide — target 2:40

Record one continuous screen capture, including the command that runs the real MCP workflow.
Aim for **2:30–2:45**, including the terminal, browser transitions and closing hold. The final
file must be **under 3:00**. Setup happens before capture; there are no cuts or sped-up sections.

Use the [spoken script](demo-narration.md), [short captions and cues](demo-cues.md), and
[recording checklist](demo-checklist.md) together. Prefer the creator's own voice.

## What this recording proves

The fast demo uses a **deterministic local model** to drive real calls through the custom
Education MCP and the borrowed read-only Filesystem MCP. The browser page is generated from
that run's report and audited state. It is a read-only presentation, not a teacher review form.

The real **Qwen2.5 3B PASS** is separate, already committed evidence in
[`evidence/open_weights_run.json`](../evidence/open_weights_run.json). The consolidated real
challenge run is in [`evidence/challenge_run.json`](../evidence/challenge_run.json).
Neither is rerun by the fast demo. Do not describe the live deterministic run as Qwen inference.

## Prepare off camera

1. Use the reviewed recording-package revision. Once merged, use the updated `main` branch.
   Resolve local work before switching branches; keep historical evidence intact.
2. Bootstrap once if needed (Python 3.11+ and Node.js 20+ with npm):

   ```powershell
   python scripts/run_demo.py --no-open
   ```

3. Rehearse the actual command below, including browser launch, with a stopwatch. Require
   `DEMO RUN: PASS`, three successful audited calls, one pending candidate, zero teacher
   decisions and zero profile updates. The fresh run replaces only the demo runtime state;
   it does not approve a candidate or promote model evidence.
4. Set terminal and browser text large enough to read in the exported video. Start with a
   1920 × 1080 capture and browser zoom around 110%; adjust after the playback check. Use a
   short terminal prompt if the working-directory path wraps the command. Close stale demo
   tabs and unrelated windows, silence notifications, and test the microphone.
5. Practise the page's Evidence, MCP activity, Candidate, Human gate, Separate validation and Limitation
   navigation links. Scroll gently within a section when necessary. Keep the script beside the
   screen, outside the capture. No prepared screenshot stands in for the live page.

Ollama is not needed for this fast take. Do not run `scripts/run_challenge.py` or the open-weights
runner during capture. Any separate reproducibility work belongs outside the recording.

## Start the capture

Start recording with the terminal visible **before** executing this exact command. It may be
typed at the prompt in advance; press Enter on camera as the first narration begins:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.demo_run
```

The command writes `runtime/demo_run.json`, `runtime/demo_state.json` and
`runtime/mwalimulens_demo.html`, then opens the generated page after a passing run. Keep the
terminal summary visible for about two seconds; if the browser takes focus first, briefly
switch back to show `DEMO RUN: PASS`, then return to the new page.

## Time-coded storyboard

Times include all movement and pauses. Follow the matching script sections; exact tool names
are shown on screen rather than spelled out aloud.

| Time | Surface and action | Evidence to hold visibly | Narration beat |
|---|---|---|---|
| 0:00–0:25 | **Terminal first.** Start capture, press Enter at about 0:02. Narrate while the real MCP run finishes. Show the terminal PASS summary for two seconds, then the browser hero by 0:25. | Exact command; deterministic mode; live run PASS; synthetic-data badge. | Why MwalimuLens exists; synthetic data; deterministic fast demonstration with real MCP calls. |
| 0:25–0:55 | **Browser → Evidence** (`#evidence`). Point down the assessment rows, then hold the counter-observation for at least four seconds. | 61%, 78%, 84%, 87% assessments across 2025-T1 to 2026-T1. EV-008 in 2025-T3 says the learner struggled to justify the method independently during an open-ended problem. EV-011 is a later 81% practical task, marked supporting. | The longitudinal pattern and why the contradictory observation matters. |
| 0:55–1:22 | **Browser → MCP activity** (`#activity`). Move the pointer once per call; hold the three rows together. | `get_competency_evidence` — Education MCP; `read_text_file` — borrowed read-only Filesystem MCP; `flag_pattern_for_review` — Education MCP. All show SUCCESS from this run. | Evidence retrieval, reference read, pending-candidate action. Reference guidance is not learner evidence. |
| 1:22–1:43 | **Browser → Candidate** (`#candidate`). Hold the claim, status, uncertainty and teacher question. | “Fraction performance improved across terms, while independent explanation remained mixed.” Actual status `pending_teacher_review`. | Only a candidate; uncertainty and a useful question for the teacher. |
| 1:43–2:03 | **Browser → Human gate** (`#gate`). Keep the three counts together for the whole beat. | Pending candidates **1**; teacher decisions **0**; profile updates **0**. Human review action is not model-visible. | Teacher must approve, edit or reject. The live demo stops before any teacher decision. |
| 2:03–2:25 | **Browser → Separate validation** (`#validation`). Keep the separate-evidence heading and source paths visible. | Committed `evidence/open_weights_run.json`: real Qwen2.5 3B PASS; `evidence/challenge_run.json`: PASS; 11 current evaluation passes and 2 preserved historical failures. | Earlier real model proof, explicitly separate from today's deterministic run. Do not open or read raw JSON during the take. |
| 2:25–2:40 | **Browser → Limitation** (`#limitation`). Finish the last sentence, leave a short quiet hold, stop capture. | Synthetic prototype and limits of validation. | Close with the honest limitation in the script. |

## Timing and recovery

The script is paced for about 115–125 spoken words per minute. The first 25 seconds include
execution time: narration continues while the command runs. Rehearse on the recording machine;
startup time and browser focus vary. The word count is a planning estimate, not a measured take.

If the browser is not ready by 0:25, or a call fails, stop, resolve the cause off camera and
restart the whole take. Do not fill the gap with a previous page or splice in a successful run.
If the full rehearsal exceeds 2:45, remove dead navigation time and rehearse again; do not rush
the evidence or the human gate. A stumble is a reason for a fresh continuous take, not a cut.

No approving, editing or rejecting for visual effect. No changes to evidence files, historical
failures or review permissions. No generated audio/video binaries belong in the repository.

## Publication hand-off

The repository's video requirement stays **Ready to record**. After recording, use the
[final checklist](demo-checklist.md) to verify the exported duration and public playback.
Only then replace the public-video placeholders in the README and challenge evidence map and
mark the video requirement **Present**.
