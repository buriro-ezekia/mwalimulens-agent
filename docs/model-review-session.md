# One-attempt model review session

Use this path to record one genuine local Qwen interpretation, hand a valid
candidate to the human reviewer and verify the same saved case after revision.
It uses only the fictional fractions case, `L001` / `MATH-FRACTIONS`. The
authored `demo-*` examples remain separate.

The application retrieves evidence through the Education MCP, supplies that
snapshot to Qwen and submits a validated candidate through MCP. The model
generates the interpretation; retrieval and submission are controlled by the
application. This path does not demonstrate model-selected tools.

## Prepare without generation

Use a clean, committed `product-development` checkout containing
[`model_review_session.py`](../src/mwalimulens/model_review_session.py), with the
existing virtual environment, Ollama running locally and `qwen2.5:3b` already
installed. Stop another portal instance before using the same output folder.
The command neither downloads a model nor spends hosted compute credits.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_review_session --output-dir 'D:\ML-runtime\portal'
```

With no action flag, this is a metadata-only preflight. It checks the Git HEAD,
clean working tree, fixture hashes, Ollama version and installed model digest.
It makes **zero generation requests** and creates no Qwen attempt. Continue
only when it reports `"ready": true` and exits 0. If the service is unavailable,
the model is missing or the checkout has local changes, resolve that condition
before running. Do not discard local work to make the check pass.

## Run once

The following command authorises exactly one new local attempt:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_review_session --run --output-dir 'D:\ML-runtime\portal'
```

The session reuses the existing `QwenJob`: **one model request**, a **210-second
internal deadline** and a **240-second worker watchdog**, with no prewarm or
proposal repair. It records the source and provider metadata before starting.
Each attempt gets a fresh `qwen-*` case ID; previous cases are preserved.

Read the terminal result and record its exact `case_id`. If a valid candidate
returns, the command opens that saved case in the existing teacher portal.
No second model request is made by opening it, and the portal starts without
the action for launching another Qwen review.

To save the outcome without opening the interface, add `--no-open`:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_review_session --run --no-open --output-dir 'D:\ML-runtime\portal'
```

These are alternative run commands. **Do not execute both for the same planned
attempt.** A zero exit code after candidate generation means a candidate is
available for human review; it does not mean the teacher-review sequence is
complete or that the interpretation is educationally correct.

If Qwen abstains, fails or times out, preserve the outcome and stop. The command
does not retry, substitute an authored finding or create a teacher decision.
A valid abstention may still fail the fixed expected-candidate scenario; keep
that grade and assess the explanation separately. Do not change the prompt,
evidence or expected outcome merely to force a candidate.

## Human revision and explicit confirmation

Only proceed when the actual model output is a valid candidate. Read the claim,
all cited records, counter-evidence and uncertainty. Check the task types and
conditions before interpreting score differences, and inspect EV-008 alongside
the later explanation evidence. Decide whether the wording is justified.

If revision is warranted, the human reviewer selects **Revise**, enters their
own reason and replacement wording, then selects **Review decision**. The
preview does not save a review. Only **Confirm simulated decision** records it
and creates one synthetic profile note. The original model proposal remains
in the generation records.

Do not invent a revision to satisfy a demonstration target. Approve or Reject
remain legitimate human choices; they do not complete this particular
revision-sequence check. No script in this session supplies a teacher decision.

## Reopen and verify the same case

After recording a revision, stop the portal with **Ctrl+C** and reopen the exact
saved ID, replacing the placeholder below:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.teacher_portal --output-dir 'D:\ML-runtime\portal' --open-qwen qwen-YOUR-CASE-ID
```

Check the case identity, retained reason, final wording and counts **0 awaiting /
1 decision / 1 synthetic profile note**. Reopening requires no inference. Do not
submit another decision.

Run the read-only session verifier in a separate PowerShell window:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_review_session --output-dir 'D:\ML-runtime\portal' --verify qwen-YOUR-CASE-ID
```

Verification contacts no provider and writes no files. It checks the session
identity, unchanged generation hashes and the portal's saved-result validation.
It reports `sequence_complete: true` only for the single-request candidate with
one consistent simulated human revision and one note. The result includes the
saved reason and final wording. A pending candidate or another human decision
does not pass this revision-sequence check.

## Evidence and limits

Keep the **complete case directory**. `session_provenance.json` records the
preflight metadata and execution limits. `session_result.json` records the
terminal outcome and hashes of the original generation artefacts. The saved
Qwen bundle retains the evidence snapshot, raw proposal, reports and tool audit;
later human changes belong in `state.json`, which is deliberately outside the
immutable generation-hash set.

These are local consistency checks, not signed provenance or authenticated
teacher identity. Reviewer identity remains
`simulated-teacher-not-authenticated`. Software tests and a completed revision
record do not establish independent educator moderation, general model
reliability or classroom effectiveness. The verifier retains
`semantic_quality_verified: false`.

A workspace without access to the local Ollama service cannot produce the live
candidate. Preparing or testing this wrapper is not evidence that generation
or human confirmation occurred. Record a genuine outcome only after the
one-attempt command runs on the device hosting the model.

See the [portal Qwen contract](portal-qwen-integration.md),
[structured-review contract](structured-review-contract.md) and
[manual semantic rubric](semantic-review-rubric.md) for the underlying validation
and interpretation limits.
