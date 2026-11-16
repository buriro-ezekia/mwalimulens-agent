# Historical challenge evidence

This directory preserves the original challenge reports and local model failure
records for inspection and reproduction. Their passing statuses refer to specific
runs and checks; they do not establish current model reliability or consistent
educational judgement. See the [model reliability guide](../docs/model-reliability.md)
for the subsequent multi-scenario investigation and its limitations.

Keep new investigation and reproduction reports in `runtime/` or another separate
output directory. Do not replace the preserved reports or failure records in this
directory. The sections below describe the original evidence and the checks used
to qualify reports for promotion.

## Open-weights run

`open_weights_run.json` records a real local Qwen/Ollama run. Automated software
tests do not generate this evidence.

The original workflow ran `mwalimulens.agent.open_weights_run`, checked the runtime
report and used `mwalimulens.agent.promote_open_weights_evidence` to promote an
eligible result. Promotion requires `"status": "pass"` and every required
open-weights evidence check to pass. These checks qualify the recorded run; they
do not establish reliability across other tasks.

The report stores the prompt, initial and final outputs, and tool metadata for
audit. It does not store hidden chain-of-thought.

## Preserved model failures

The `failures/` directory preserves real local Qwen failures involving workflow
completion and semantic abstention, together with their recorded follow-up
actions. Proposed corrections are not evidence of a successful later result.
These records remain part of the challenge evaluation evidence.

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

The original workflow used `mwalimulens.evals` to generate the runtime report and
`mwalimulens.promote_evals` to validate it for promotion.

The committed `evals_run.json` contains 13 cases: 11 regression cases marked `PASS`
and two preserved historical model failures marked `FAIL`. Its overall status is
`pass` because it meets the promotion conditions above. These original challenge
results are separate from the later multi-scenario model evaluations.

## One-command challenge run

The clean-checkout bootstrap writes `runtime/challenge_run.json` and separate
component reports.

The original workflow used `mwalimulens.promote_challenge_run` to promote a complete
passing consolidated report. Promotion requires the Ollama preflight, real
open-weights task, borrowed-MCP smoke test, evaluation suite and human-review
boundary checks all to pass.

The committed `challenge_run.json` records a completed real workflow using
`qwen2.5:3b`. The Ollama preflight, open-weights task, borrowed-MCP smoke test,
evaluation suite and human-review boundary checks all passed in that recorded run.

## Reproducing the checks

Follow the [reproduction guide](../docs/reproducible-run.md) for prerequisites and
the original challenge sequence. Reproduction may execute a local model; it is
separate from reading these committed reports.

The promotion modules above default to destinations in `evidence/`. When
validating a newly generated report, supply `--destination` with a path outside
this directory. Review the new report separately and retain any failed attempts;
reproduction does not replace the original evidence.
