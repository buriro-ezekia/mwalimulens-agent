# MwalimuLens demo guide — target 2:30

The recording should be one continuous screen capture. The fast demo uses the real custom and
borrowed MCP boundaries with a deterministic local model so the workflow is visible without the
multi-minute Qwen inference delay.

The separately committed Qwen2.5 3B run remains the open-weights evidence.

## Before recording

Prepare and validate the environment once before starting the screen capture:

```powershell
git switch main
git pull --ff-only origin main
python scripts/run_demo.py --no-open
```

This bootstrap step installs/reuses the local environment and validates the fast demo without
opening the browser.

## Start the actual recording

Begin the unedited screen capture with the terminal visible, then run the real fast MCP workflow:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.demo_run
```

This command performs the live MCP calls and opens `runtime/mwalimulens_demo.html`. Capture the
terminal PASS summary briefly before moving to the browser page.

The terminal should finish with:

```text
Education evidence retrieval: PASS
Borrowed reference read: PASS
Candidate pending review: PASS
Human gate untouched: PASS
Real Qwen validation: PASS
DEMO RUN: PASS
```

## Recording plan

### 0:00–0:20 — problem and principle

Show the top of the page.

Say:

> MwalimuLens looks across learner evidence over time rather than treating one score as a permanent
> label. The agent identifies a pattern, but the teacher decides what it means.

Point out that the learner data is synthetic.

### 0:20–0:55 — longitudinal evidence

Move to the evidence table.

Show the improving fraction scores and the counter-observation. Mention that both are kept visible,
rather than allowing the higher scores to erase contradictory classroom evidence.

### 0:55–1:25 — visible MCP actions

Move to the MCP activity panel.

Show:

1. `get_competency_evidence` from the custom Education MCP;
2. `read_text_file` from the official borrowed Filesystem MCP; and
3. `flag_pattern_for_review` from the custom Education MCP.

Explain that the borrowed server is read-only and that the reference file is not learner evidence.

### 1:25–1:55 — candidate and uncertainty

Move to the pending candidate.

Read the short claim and point out the explicit uncertainty and teacher question. Avoid reading
every evidence row.

### 1:55–2:15 — human gate

Show:

- one pending candidate;
- zero teacher decisions; and
- zero profile updates.

Say that `record_teacher_review` is deliberately not model-visible.

### 2:15–2:35 — reliability and open-weights proof

Show the validation cards.

Mention:

- the separate real Qwen2.5 3B run passed;
- the one-command challenge run passed;
- 11 current evaluation cases pass; and
- 2 historical model failures remain preserved.

### 2:35–2:50 — limitation and close

Show the limitation card.

Say:

> This is a synthetic challenge prototype, not a production learner-classification system. The
> purpose is to make evidence, uncertainty and teacher responsibility inspectable.

End on the MwalimuLens principle at the top of the page if time permits.

## What not to do in the video

- Do not rerun the slower Qwen inference during the recording.
- Do not imply that the deterministic demo is the open-weights validation.
- Do not approve or edit the candidate just to create movement on screen.
- Do not hide the counter-evidence or the historical failures.
- Do not spend time reading installation logs.

The strongest demo is short because the evidence and boundaries are already visible.
