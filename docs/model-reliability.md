# Local real-model repeatability evaluation

This is **post-selection experimental evaluation**. It does not replace the original
committed Qwen evidence, the challenge evaluation suite or historical failure reports.

## Purpose

The original submission contains a successful local Qwen2.5 3B workflow and preserved
failures. A single success is insufficient to establish repeatability. This harness runs
the **same fictional L001 / MATH-FRACTIONS task** multiple times using the actual local
Qwen model and the custom Education MCP. It reports all outcomes, including failures.

This first benchmark does **not** cover multiple learners, curricula, languages or schools.
Those remain separate research and validation tasks.

## Run on Windows

From the `product-development` branch, after starting Ollama and confirming
`qwen2.5:3b` is installed:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --dry-run
.\.venv\Scripts\python.exe -m mwalimulens.model_reliability --runs 3 --timeout 600
```

The harness performs an Ollama preflight against the **local** endpoint before running.
Each attempt uses a separate Python process and fresh JSON state. A timeout or failed
model/tool action is retained as a failed attempt. The original one-turn bounded
completion-recovery policy still applies within each run; this is disclosed in the report.

The output is saved under:

```text
runtime/model_reliability/campaign-*/
    summary.json
    attempt-001/report.json
    attempt-001/state.json
    attempt-001/stdout.txt
    attempt-001/stderr.txt
    ...
```

No files in `evidence/` are overwritten or promoted. Runtime files are outside Git.
The command exits non-zero when preflight is blocked or any attempt fails, but still
writes the summary and preserves all completed attempts.

## Measures

The summary records attempt count, pass/fail counts and rate, candidate count, audited
tool failures, bounded recovery attempts, **observed** teacher-gate violations and the
p50/p95 elapsed time. Attempts without a complete report are counted as **unknown** for
human-gate and tool-audit outcomes, not silently treated as safe successes. It lists
every attempt, including errors and timeouts. This is a small descriptive reliability
check, not a statistically powered estimate.

Do not publish a pass rate before running the actual model. The isolated unit tests
use mock subprocess results; they do **not** demonstrate live Qwen reliability.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_model_reliability.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

For a stronger study, extend the evaluation contract to additional fictional learner
scenarios with scenario-specific expected outcomes, including appropriate abstention.
The current `open_weights_run` validator is tied to L001 / MATH-FRACTIONS, so simply
changing the prompt would not produce a valid multi-scenario evaluation.
