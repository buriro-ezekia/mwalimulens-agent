# MwalimuLens product development and validation roadmap

**Updated:** 26 October 2026  
**Development branch:** `product-development`  
**Original validated submission:** `6215b9efb79ffd022a835dabba386c5ccb8226e4`

## Product goal

MwalimuLens helps educators interpret longitudinal learning evidence while reserving consequential decisions for a human teacher. The application should be usable in schools with constrained connectivity and modest computing resources, without assuming one score defines a learner.

## Current functionality

The teacher-facing [Learner Progress Review](teacher-workspace.md) provides an assessment trend, chronological evidence, supporting and contradictory observations, uncertainty, an explicit review question and a browser-based human decision workflow. Approve, revise and reject decisions require confirmation and are persisted with the local audit record.

The application supports a seeded fictional practice case and a separate deterministic workflow that makes real calls to the custom Education MCP and read-only Filesystem MCP. The deterministic workflow is not live Qwen inference. The separate Qwen2.5 3B evidence remains available as an independently validated model path.

The [model repeatability harness](model-reliability.md) records isolated attempts, timeouts, errors, tool traces and duration metrics. The [offline demonstration checks](offline-demo.md) cover local dependencies, MCP execution and manual network-disconnection rehearsal. A [teacher feedback protocol](teacher-feedback.md) supports exploratory usability assessment using synthetic data.

## Verified results and outstanding checks

The latest locally reported development baseline is **367 pytest tests passed** and **Ruff: All checks passed**. Those results preceded the current naming-only cleanup and must be rechecked after it.

- The browser workflow, evaluation harness and preflight modules are implemented.
- Live repeated-Qwen reliability results on the target laptop remain outstanding; do not invent pass rates.
- A manual disconnected-network rehearsal remains outstanding.
- Teacher usability feedback and classroom impact have **not** been established.
- Identity is simulated rather than authenticated; no real learner data, public write endpoint or multi-user school deployment is approved.

## Priorities and acceptance requirements

### P0 — Complete and verify teacher decision support

Provide a coherent teacher experience from retrieved evidence through review and audit. Display uncertainty and contradictory evidence prominently; keep technical details available on demand. Verify approve, revise and reject outcomes, duplicate rejection, cancellation, HTML safety and profile-note consequences.

**Gate:** full pytest and Ruff pass; local browser review passes in seeded and real-MCP modes; no model-visible teacher-review tool.

### P0 — Repeat local model evaluation

Evaluate the Qwen model with multiple isolated attempts and openly retain success, failure and timeout evidence. The initial harness repeats one fictional learner task. Extend it to distinct scenarios and appropriate-abstention criteria before claiming broader reliability.

**Gate:** an auditable run-level report, grounded metrics and explicit hardware and timing information.

### P0 — Confirm offline operation

Rehearse the teacher interface and genuine MCP calls with connectivity deliberately disabled. Check local dependencies, files, CPU responsiveness and readability. Do not confuse a recorded fallback with a live model run.

**Gate:** completed manual rehearsal with observed results documented.

### P1 — Classroom usability and suitability

Conduct permission-based exploratory teacher walkthroughs using fictional data. Document confusion, missing context, useful evidence displays and the clarity of review decisions. Report the sample honestly; do not infer learning outcomes from a small usability exercise.

### P1 — Production security and governance

Before considering real learner data, design verified identity, role-based authorisation, consent, data minimisation, secure persistence, audit retention, offline synchronisation and privacy controls. The current prototype is not production-ready.

## Product change-control

Develop on `product-development`, keep the original submission history identifiable by its exact SHA, and avoid mixing experimental evaluations into promoted historical evidence.

After each change:

```powershell
git switch product-development
git pull --ff-only origin product-development
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git diff --check
git status --short
```

Treat a change as ready only when code, validation, documentation and a realistic teacher-facing walkthrough agree. Preserve all historical failures as genuine evidence rather than overwriting them.
