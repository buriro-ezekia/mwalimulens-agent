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
- The final [recording package](demo-guide.md) supplies a natural spoken script, a 2:40
  command-first storyboard, short captions and a [recording checklist](demo-checklist.md).
- The recording page identifies deterministic orchestration and separate committed Qwen
  validation, and exposes the actual pending status beside the human review counts.

## Remaining submission blocker

The repository cannot prove the **under-three-minute demo video** until a real recording exists.

The fast demo has now passed locally with the real custom and borrowed MCP boundaries: evidence
retrieval PASS, borrowed reference read PASS, candidate creation PASS, human gate untouched, and
separate committed real Qwen validation PASS. The challenge matrix is therefore **Ready to record**.

It must not become **Present** until the final under-three-minute public video URL is available
and signed-out playback is verified. The README and challenge matrix contain explicit pending
URL placeholders; no public video is claimed by the recording package.

## Known limitations

These are documented rather than hidden:

- synthetic learner data only;
- small challenge-focused evaluation set;
- real Qwen validation comes from a committed local run rather than the fast recording demo;
- no claim of educational validity across real schools or curricula; and
- no autonomous learner classification or pathway assignment.

## Final pre-submission checks after video recording

1. Follow the [final recording checklist](demo-checklist.md): one continuous take, live command,
   visible evidence and gate, natural voice, ideally 2:30–2:45 and strictly under 3:00.
2. Verify public playback without signing in, then add the real URL and duration to the README
   and challenge evidence map and mark the video **Present**.
3. Keep full Qwen reproducibility checks separate and off camera. The existing committed PASS
   reports remain the open-weights proof; do not overwrite or promote them from the fast demo.
4. Run the full deterministic test suite and Ruff after any code or contract changes.
5. Review the diff and `git status`; exclude generated media and preserve historical failures.
6. Confirm the submission references the final `main` commit and public video URL.
