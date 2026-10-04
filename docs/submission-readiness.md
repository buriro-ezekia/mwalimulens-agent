# Submission readiness audit

**Repository audit date:** 4 October 2026

This note records the final repository-side review before the demo video is recorded.

## Strong, inspectable requirements

The repository already contains evidence for:

- a four-tool custom Education MCP;
- a model-visible allowlist that excludes the human review action;
- an action tool that persists a pending candidate;
- audited tool inputs, outputs/errors and timestamps;
- an explicit approve/edit/reject teacher gate;
- a real local Qwen2.5 3B task;
- an official borrowed Filesystem MCP with a read-only sandbox;
- a reproducible one-command challenge run;
- a 13-case evaluation suite;
- genuine historical model failures with documented next attempts;
- Apache-2.0 licensing; and
- synthetic data only.

## Improvements made during this audit

- The default Ollama model is aligned with the validated `qwen2.5:3b` path.
- Borrowed-MCP installation instructions use `npm ci` consistently with the committed lockfile.
- A fast judge-facing browser demo uses the real MCP boundaries without rerunning slow Qwen
  inference.
- The README has been rewritten in UK English and separates the fast demo from the real
  open-weights evidence.
- Stale "planned" and "in this slice" status language has been removed where implementation is
  complete.
- Console entry points are available after installation for both the challenge run and demo.

## Remaining submission blocker

The repository cannot prove the **under-three-minute demo video** until a real recording exists.

The demo workflow is implemented and documented in `docs/demo-guide.md`, but the fast demo still
needs one local validation run on this branch. The challenge matrix therefore remains
**Pending demo validation** until that succeeds, and must not become **Present** until the final
video URL is available.

## Known limitations

These are documented rather than hidden:

- synthetic learner data only;
- small challenge-focused evaluation set;
- real Qwen validation comes from a committed local run rather than the fast recording demo;
- no claim of educational validity across real schools or curricula; and
- no autonomous learner classification or pathway assignment.

## Final pre-submission checks after video recording

1. Confirm the final video is public and under the challenge time limit.
2. Add the video URL to the README and challenge evidence map.
3. Run `python scripts/run_challenge.py` one final time from `main`.
4. Run the deterministic test suite and Ruff.
5. Confirm `git status` contains no unintended files.
6. Confirm the submission references the final `main` commit.
