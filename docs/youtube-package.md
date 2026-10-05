# YouTube upload package

Use this copy after recording and checking the real continuous take. Follow the
[production guide](demo-production.md), [storyboard](demo-guide.md) and
[recording checklist](demo-checklist.md). Target **2:30–2:45**; the complete uploaded video
must be **strictly under 3:00**. Keep the recording outside the repository.

Current published submission: [https://youtu.be/Zh9V_Ptc4ME](https://youtu.be/Zh9V_Ptc4ME),
verified duration **2:39.03**, 1080p, with captions. The instructions below are retained for any
future replacement upload.

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
Current YouTube URL: https://youtu.be/Zh9V_Ptc4ME
Verified duration: 2:39.03
Replacement YouTube URL: ______________________
Replacement verified duration: ________________
```

Leave replacement fields blank until a replacement is verified. Do not invent a URL or substitute
the target duration for the measured duration. No audio/video binaries belong in a commit.

## Post-upload repository update

The current submission already completed this step. Use the process below only for a verified
replacement video.

1. Update the existing public-demo link and verified duration consistently in [README.md](../README.md),
   [docs/challenge-requirements.md](challenge-requirements.md) and
   [docs/submission-readiness.md](submission-readiness.md).
2. Record the replacement playback-check date and retain the current known limitations.
3. Leave promoted model/evaluation evidence, historical failures, source code and review-gate
   semantics unchanged.
4. Run the deterministic suite and Ruff before committing:

   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   .\.venv\Scripts\python.exe -m ruff check .
   ```

5. Review the diff and working tree. Keep media files outside the repository and commit only the
   intended text updates. Do not replace the currently published demo until the replacement has
   passed duration, HD, captions and signed-out playback checks.
