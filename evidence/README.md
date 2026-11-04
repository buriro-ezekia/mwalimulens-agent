# Historical challenge evidence

This directory preserves the original challenge reports and local model failure
records for inspection and reproduction. Their passing statuses refer to specific
runs and checks; they do not establish current model reliability or consistent
educational judgement. See the [model reliability guide](../docs/model-reliability.md)
for the subsequent multi-scenario investigation and its limitations.

Keep new investigation reports separate from these historical files. The commands
below document the original reporting and promotion workflows.

## Open-weights run

`open_weights_run.json` records a real local Qwen/Ollama run. Tests do not generate it.

Workflow:

1. Run the real local Qwen/Ollama task:
   `python -m mwalimulens.agent.open_weights_run`
2. Confirm the runtime report shows `"status": "pass"`.
3. Promote an eligible report:
   `python -m mwalimulens.agent.promote_open_weights_evidence`
4. Review the promoted JSON before committing it.

Promotion is blocked unless every required open-weights evidence check passes.

The report stores the prompt, initial and final outputs, and tool metadata for
audit. It does not store hidden chain-of-thought.

## Genuine failures

The `failures/` directory preserves real local Qwen failures involving workflow
completion, the MCP lifecycle and candidate meaning. These records remain part of
the challenge evaluation evidence and document the next attempted correction.

## Borrowed MCP run

The committed `borrowed_mcp_run.json` records a real smoke test of the official
Filesystem MCP. That run passed the read-only allowlist, write-tool exclusion,
sandbox, installed-version, legacy-handshake and borrowed-call audit checks.

## Evaluation run

The challenge evaluation runner writes `runtime/evals_run.json`.

The report combines regression cases with preserved historical model failures.
Historical `FAIL` rows are intentional and do not count as regression failures
when determining the report's overall status.

Promotion to `evidence/evals_run.json` is blocked unless:

- at least 8 evaluation cases exist;
- all regression cases classified as current in the report pass; and
- at least one genuine historical model failure remains preserved.

Run:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.evals
.\.venv\Scripts\python.exe -m mwalimulens.promote_evals
```

The committed `evals_run.json` contains 13 cases: 11 regression cases marked `PASS`
and two preserved historical model failures marked `FAIL`. Its overall status is
`pass` because it meets the promotion conditions above. These original challenge
results are separate from the later multi-scenario model evaluations.

## One-command challenge run

The clean-checkout bootstrap writes `runtime/challenge_run.json` and separate
component reports.

Promote only a complete passing consolidated report:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.promote_challenge_run
```

Promotion to `evidence/challenge_run.json` is blocked unless the Ollama preflight, real
open-weights task, borrowed-MCP smoke, evaluation suite and human-review boundary all pass.

The committed `challenge_run.json` records a completed real workflow using
`qwen2.5:3b`. The Ollama preflight, open-weights task, borrowed-MCP smoke test,
evaluation suite and human-review boundary checks all passed in that recorded run.
