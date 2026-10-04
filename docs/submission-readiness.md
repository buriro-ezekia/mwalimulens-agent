# Submission readiness audit

**Repository audit date:** 4 October 2026

This note records the final repository-side review after the demo video was recorded and published.

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
- The [Windows production guide](demo-production.md) covers capture, sound, rehearsal and the
  complete take; [operator cues](demo-operator-cues.md) keep on-the-day actions short.
- The [YouTube package](youtube-package.md) supplied the upload copy and verification workflow.
- The final continuous demo was recorded at 1920×1080/30 fps, measured at **2:39.03**, remuxed to
  MP4, uploaded with captions, and verified at 1080p.
- Public demo: [https://youtu.be/Zh9V_Ptc4ME](https://youtu.be/Zh9V_Ptc4ME).

## Final owner checks completed

The owner completed the final visual and playback review on 4 October 2026. The published take is
one continuous **2:39.03** recording and preserves the intended evidence sequence: the live command,
counter-evidence, three audited MCP calls, the pending teacher-review state, **1 pending / 0 teacher
decisions / 0 profile updates**, separate committed Qwen2.5 3B validation and the explicit
real-classroom limitation. Captions were added to the published video, and 1080p playback was
verified.

## Demo video requirement completed

The under-three-minute demo requirement is now **Present**.

- Public video: [https://youtu.be/Zh9V_Ptc4ME](https://youtu.be/Zh9V_Ptc4ME)
- Verified local master duration: **2:39.03**
- Resolution/frame rate: **1920×1080 at 30 fps**
- Video/audio: **H.264 + AAC**
- Published captions: **Present**
- 1080p playback verified: **4 October 2026**

The deterministic recording remains distinct from the committed real Qwen evidence. No promoted
model/evaluation evidence, historical failures or human-review semantics were changed.

## Known limitations

These are documented rather than hidden:

- synthetic learner data only;
- small challenge-focused evaluation set;
- real Qwen validation comes from a committed local run rather than the fast recording demo;
- no claim of educational validity across real schools or curricula; and
- no autonomous learner classification or pathway assignment.

## Final pre-submission checks

1. Keep full Qwen reproducibility evidence separate from the deterministic recording; the existing
   committed PASS reports remain the open-weights proof.
2. Run the full deterministic test suite and Ruff after this submission-state update.
3. Review the final diff and `git status`; exclude generated media and preserve historical failures.
4. Confirm the submission references the final `main` commit and
   [public video](https://youtu.be/Zh9V_Ptc4ME).
