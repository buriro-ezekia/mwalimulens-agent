# MwalimuLens engineering guide

MwalimuLens is an evidence-grounded educational AI product that retrieves
fictional learner records, proposes qualified patterns and leaves every
approval, revision and rejection decision to a human teacher.

## Scope and source of truth

- Develop on `product-development`; do not modify `main`, the
  `submission-final-2026-10-05` snapshot or any original evidence under
  `evidence/`.
- Study `src/mwalimulens/agent/open_weights_run.py`,
  `src/mwalimulens/multi_scenario_eval.py`,
  `src/mwalimulens/agent/grounding.py`,
  `src/mwalimulens/agent/orchestrator.py`,
  `src/mwalimulens/mcp_server/service.py` and their tests before altering
  model/tool orchestration.
- Only fictional data in `data/synthetic/` is permitted in development
  and tests. Do not add real learners or personal data.
- The available tool set must never expose `record_teacher_review` to
  the model. Pending candidates cannot modify a learner profile.
- Distinguish model reasoning reliability from application-enforced safety:
  a gate may block a wrong action without making the model's reasoning right.

## Current reliability investigation

- The multi-scenario suite has four fictional cases:
  `longitudinal-pattern`, `conflicting-evidence`,
  `single-assessment`, `missing-competency`.
- A completed live run reported **2/4**, with individual case durations
  187.95s, 311.06s, 134.88s and 23.93s respectively. Prior campaigns
  varied from 1/4 to 3/4. Historical failures must remain visible.
- The model has at times falsely claimed that terms were missing, omitted
  tool arguments or counter-evidence, or attempted candidate actions with
  insufficient history.
- Before further prompt tuning, inspect the latest local reports in
  `runtime/multi_scenario/suite-1jy77zd1/`; they are **local runtime files**,
  not committed GitHub files. Use the no-rerun `--diagnose` CLI or read
  `result.json` and `report.json` for each case.
- Reproduce failures with focused tests and verify tool schema, state
  transitions, validator semantics and recovery policies. Do not weaken
  checks, rewrite expected outcomes or inject gold answers into prompts.

## Verification gates

Use the repository virtual environment from PowerShell:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m mwalimulens.multi_scenario_eval --diagnose "runtime/multi_scenario/suite-1jy77zd1"
```

- Review imports and run Ruff **before** invoking the expensive local model.
- The last user-confirmed baseline was **422 tests passed**; new tests
  should increase the count. Do not assume CI success on new commits.
- Keep tests self-contained; CI does not run live Ollama.
- A successful live evaluation must report the exact per-scenario checks,
  candidate IDs, tools, errors, first-pass versus corrected outcomes and
  observed human-gate violations. Never claim reliability from unit tests.
- Do not launch repeated CPU-intensive Qwen runs without the user's
  permission and a concrete test plan. The model runs at roughly
  8 output tokens/s on CPU; the live suite may take several minutes.
- Make small changes, explain the defect they fix, verify with
  `ruff` and `pytest`, and preserve auditability of failures.
