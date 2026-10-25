# Nairobi offline demonstration rehearsal

**Purpose:** prepare a robust, honest presentation on the CPU-only Windows laptop.
This checklist is not proof that a full offline rehearsal has already passed.

## Before travel (while connected)

Verify the local environment and required dependencies:

```powershell
.\.venv\Scripts\python.exe --version
node --version
npm --version
ollama list
Test-Path 'node_modules\@modelcontextprotocol\server-filesystem\dist\index.js'
```

The required Qwen model should be `qwen2.5:3b`. Download or install any missing
software **before** the offline rehearsal. Never put credentials or real learner data
in the demonstration repository.

## Automated local preflight

Run the following with the local environment prepared:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.nairobi_preflight --run-mcp --check-model
```

The preflight checks installed Python/Node components, synthetic fixtures, the borrowed
Filesystem MCP, a real fast MCP task and whether the local Ollama model is available.
It writes a JSON report under `runtime/nairobi_preflight/`. A result of
`automated_pass` means only the **automated** checks passed; it does not prove that
Wi-Fi was disconnected or that a real Qwen inference completed. A failure is retained
and reported rather than silently bypassed.

## Offline test (disconnect Wi-Fi)

1. Disconnect the laptop from Wi-Fi and any other internet connection.
2. Start the local Ollama service if it is not already running.
3. In PowerShell, launch the teacher workspace:

   ```powershell
   .\.venv\Scripts\python.exe -m mwalimulens.teacher_portal
   ```

4. Confirm the default seeded fictional case loads and remains usable without internet.
5. Select **Run MCP evidence analysis**. This executes real local Education and borrowed
   Filesystem MCP calls with a deterministic model. Check the audit trail for
   `get_competency_evidence`, `read_text_file` and `flag_pattern_for_review`.
6. Confirm the candidate is awaiting teacher review and that no profile note exists.
7. Choose **Revise**, enter a rationale and revised wording, inspect the confirmation
   page and confirm. Verify one simulated teacher decision and one synthetic profile note.
8. Start a fresh case and choose **Reject**. Confirm that no profile note is created.
9. Repeat the full workflow in a narrow browser window, checking that evidence and
   action buttons remain readable. Keep the technical audit collapsed until needed.
10. Separately run a real Qwen task, if the laptop can complete it within the rehearsal
    time, and report its actual execution time and outcome. Never call the deterministic
    browser run a live Qwen inference.

## Fallback and stage delivery

Keep the original verified 2:39 YouTube demo as historical submission evidence. Prepare
an additional local, clearly labelled video of the Nairobi version only **after** the
new workflow has passed manual checks. Playback is a fallback, not a live run.

For the stage, use the following narrative sequence: the classroom problem, longitudinal
learner evidence, contradictory observation EV-008, genuine MCP tool activity, provisional
candidate, teacher's revised decision, audited consequence, then limitations and next steps.

If the real model is slow or unavailable, demonstrate the fast genuine MCP workflow and
show the separately recorded Qwen results with their exact provenance. Do not hide
failed model attempts or claim real-school validation.

## Rehearsal record

| Gate | Observed result | Date |
|---|---|---|
| Seeded local browser without internet | Pending | |
| Real Education and borrowed MCP calls offline | Pending | |
| Human revise/reject decisions and audit | Pending | |
| Local Qwen task (if run), measured duration | Pending | |
| Mobile/narrow-screen legibility | Pending | |
| Recorded fallback verified | Pending | |

The Nairobi demonstration is ready only after the observed results are recorded.
No real learner records or unauthenticated production write endpoints are permitted.
