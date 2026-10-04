# YouTube upload package

Use this copy after recording and checking the real continuous take. Follow the
[production guide](demo-production.md), [storyboard](demo-guide.md) and
[recording checklist](demo-checklist.md). Target **2:30–2:45**; the complete uploaded video
must be **strictly under 3:00**. Keep the recording outside the repository.

## Title options

1. MwalimuLens Demo | Learner Evidence, Teacher Judgement
2. MwalimuLens | Education — The Long View | Live MCP Demo
3. MwalimuLens | African Agentic AI Design Challenge Demo

## First-line preview summary

MwalimuLens follows learner evidence across terms and leaves the final judgement with the teacher.

## Ready-to-paste description

The opening line below is the preview summary. Check that the final recording matches the
description before publishing.

```text
MwalimuLens follows learner evidence across terms and leaves the final judgement with the teacher.

Built for Education — The Long View in the African Agentic AI Design Challenge, this prototype uses synthetic learner records to explore longitudinal patterns in fraction work. It shows improving assessment results alongside counter-evidence: difficulty explaining the method independently.

This continuous demo uses a deterministic local model to drive real MCP calls: get_competency_evidence and flag_pattern_for_review from the custom Education MCP, plus read_text_file from the borrowed read-only Filesystem MCP.

The pattern is only a candidate. It remains pending_teacher_review, with zero teacher decisions and zero profile updates. A teacher must approve, edit or reject it; the model cannot make that decision.

The real local Qwen2.5 3B PASS is separate, already committed validation in evidence/open_weights_run.json. It is not the deterministic run shown here. Historical model failures remain available in the repository.

Limitation: MwalimuLens has not been validated in real classrooms.

Repository: https://github.com/buriro-ezekia/mwalimulens-agent
```

## File and upload settings

Suggested filename: `MwalimuLens_African_Agentic_AI_Design_Challenge_Demo.mp4`

Use **1920 × 1080, 30 fps, MP4 with H.264 video and AAC-LC audio**. Preserve the recorded
frame rate when exporting. These container and codec choices follow
[YouTube's recommended upload settings](https://support.google.com/youtube/answer/1722171?hl=en).
Keep the microphone clear; omit music and unnecessary system audio. Export or remux the
whole take without cuts, speed changes, inserted screenshots or transitions.

In YouTube Studio, choose **Create → Upload videos → Select files** and select the final MP4.
Choose a title and paste the description. Complete the required audience and other upload
fields accurately. Wait for upload and HD processing to finish;
YouTube can publish after SD processing, while HD may still be processing. See
[YouTube's upload guidance](https://support.google.com/youtube/answer/57407?co=GENIE.Platform%3DDesktop&hl=en).

### Visibility

Choose **Public** for the final submission. Only use **Unlisted** if the official challenge
rules or an organiser expressly confirm that it is accepted; this package does not establish
that permission. Retain that confirmation with the submission notes if applicable.

YouTube Public videos can be viewed by anyone; Unlisted videos can be viewed and reshared by
anyone with the link without a Google account. Private access and a future scheduled release
are unsuitable for the final judge link. See
[YouTube's visibility settings](https://support.google.com/youtube/answer/157177?co=GENIE.Platform%3DDesktop&hl=en).
Whichever permitted setting is used, verify the actual final URL without signing in or
requesting access before updating the repository.

## Verify the final upload

- [ ] Upload is complete and the intended final take is published.
- [ ] The complete video is strictly **under 3:00**, ideally **2:30–2:45**. Check the uploaded
  player duration as well as the local file; include every opening and closing hold.
- [ ] HD processing is complete and **1080p** is available in the player quality menu.
- [ ] Open the exact final video URL in a signed-out/private browser. Watch from start to
  finish at normal speed; no login, access request or unavailable-video message appears.
- [ ] Sound is clear and natural. The command, tool names, counter-evidence, pending status,
  zero counts and separate Qwen evidence are readable at normal playback size.
- [ ] The live run and human gate match the description. No teacher review action occurred.
- [ ] Copy the actual watch/share URL, not a Studio editing URL, and reopen the copied link.

```text
Final YouTube URL: ______________________
Verified duration: ______________________
```

Leave both fields blank until verified. Do not invent a URL or substitute the target duration
for the measured duration. No audio/video binaries belong in a commit.

## Post-upload repository update

Do this only after every upload check passes and a real, publicly accessible final video URL
exists. Until then, the demo requirement remains **Ready to record**.

1. In [README.md](../README.md), replace the `Public demo video URL: pending` placeholder with
   a Markdown link to the actual video and its verified duration. Update the adjacent readiness
   sentence and the **Under-three-minute video** evidence row to **Present**, with the same
   link and duration.
2. In [docs/challenge-requirements.md](challenge-requirements.md), replace its pending URL
   placeholder with the same real link and verified duration. Update the **Demo under 3 minutes**
   evidence row from **Ready to record** to **Present**. Replace the pending instructions with
   a factual note that signed-out playback was checked, including the check date.
3. In [docs/submission-readiness.md](submission-readiness.md), update the audit date and change
   the video blocker/readiness wording to reflect verified completion. Add the identical URL,
   measured duration and playback-check date. Replace the pending owner-check statement with
   the actual visual-check date and spoken-rehearsal duration once those checks are complete.
   Preserve the project's known limitations; do not claim a PR status change that has not happened.
4. Leave promoted model/evaluation evidence, historical failures, source code and review-gate
   semantics unchanged. This final submission-state update changes only those three text files.
5. Run both checks from the repository root and resolve any failures before committing:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   .\.venv\Scripts\python.exe -m ruff check .
   ```

6. Review the changes, confirm that all three files use the same verified link and duration,
   and check that neither pending URL placeholder remains in the updated submission files:

   ```powershell
   git status --short
   git diff --check
   git diff -- README.md docs/challenge-requirements.md docs/submission-readiness.md
   rg -n 'Public demo video URL: pending' README.md docs/challenge-requirements.md docs/submission-readiness.md
   ```

   No `rg` matches is the expected result (exit code 1). Review any unrelated working-tree
   changes separately; do not include generated media or evidence changes.
7. Stage only the three submission text files, then inspect the staged diff before committing:

   ```powershell
   git add -- README.md docs/challenge-requirements.md docs/submission-readiness.md
   git diff --cached --name-only
   git diff --cached --check
   git diff --cached
   git commit -m "docs: add verified public demo video"
   ```

   Before the commit, the staged file list must contain only those three files. If other work
   was already staged, resolve that separately first. These steps do not push, merge or change
   PR #24's draft status. Keep it draft until the owner has completed the browser visual
   playback check and the full timed spoken rehearsal.
