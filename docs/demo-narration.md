# Final demo narration — target 2:40

Use this with the [time-coded storyboard](demo-guide.md). Read only the blockquotes aloud.
The section headings, timing notes and `[pause]` cues are for the recorder.

The script contains **296 spoken words**: contractions and hyphenated words count as one;
`MCP` counts as one written word, spoken as the letters “M C P”. Numbers are written as spoken.
Headings and bracketed cues are excluded. At 115–125 words per minute, the speech takes about
2:22–2:34; allow roughly ten seconds for pauses and screen movements. Aim for **2:40**, and
rehearse to a finish between **2:30 and 2:45**. A timed read-through is the final timing check.

Prefer the creator's **own human voice**. Speak as if showing a colleague something you've built:
calm, interested and unhurried. Keep your normal accent; the wording uses natural UK English.
Let the shorter sentences land. Give “only a candidate” and the two zero counts a little emphasis,
without giving every sentence the same rise and fall. The pauses are breaths, not dramatic stops.

Have the command visible before capture starts. Press Enter as the first sentence begins:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.demo_run
```

Do not read the command, evidence identifiers or raw JSON aloud. Point to the matching evidence
and exact tool names on the freshly generated page. The final video is one continuous live take.

## 0:00–0:25 — introduce the purpose and run the command

> I built MwalimuLens to help teachers see how a learner's evidence changes over time. I'm running
> the fast demo now, with synthetic learner data. A deterministic model drives this recording
> workflow, and the MCP calls are real. [pause] Here's what it found.

## 0:25–0:55 — follow the evidence, including the contradiction

> These fraction assessments rise from sixty-one to eighty-seven per cent across four terms.
> They're ordered by when things happened in the classroom. But look at this classroom note:
> the learner struggled to justify a method independently during an open-ended problem.
> [pause] That's counter-evidence, and it stays beside the improving scores. Later practical work
> adds support, without settling the question.

## 0:55–1:22 — explain the real MCP activity

> The activity panel shows the custom Education MCP retrieving the competency evidence. The
> borrowed Filesystem MCP then reads a teaching reference, with read-only access. That reference
> isn't evidence about this learner. Finally, the Education MCP flags a pattern for review.
> These are the audited calls from the command we just ran.

## 1:22–1:43 — show the candidate and its uncertainty

> The candidate says fraction performance improved, while independent explanation remained mixed.
> It's only a candidate for teacher review. The uncertainty is kept explicit, with a question for
> the teacher: does the improvement hold when the learner explains an unfamiliar fraction problem?

## 1:43–2:03 — stop at the human boundary

> Now the agent stops. The teacher must approve, edit or reject the candidate. [pause] Here, it
> remains pending teacher review: zero teacher decisions and zero profile updates. The model can't
> call the human review action. That boundary's enforced in code.

## 2:03–2:25 — distinguish the separate real model evidence

> This separate PASS comes from the real Qwen two point five, three billion parameter model run
> already committed in the repository. Today's deterministic demo isn't that open-weights run.
> Eleven current evaluations pass, and two historical model failures are still preserved.

## 2:25–2:40 — acknowledge the limitation and close

> MwalimuLens brings the evidence together. The teacher decides what it means. [pause] For now,
> this small, synthetic evaluation doesn't establish how well it works in real classrooms.

## Delivery and rehearsal notes

- Speak “PASS” as “pass”, and the model name as written in the narration. Leave the exact
  `qwen2.5:3b` spelling visible on screen.
- Point to EV-008 while describing the open-ended problem. The assessment sequence is 61%, 78%,
  84%, 87%; the later practical task is 81%. The script does not claim every score rises.
- During the tool paragraph, point to `get_competency_evidence`, `read_text_file`, then
  `flag_pattern_for_review`. The spoken explanation is deliberately less technical than the labels.
- On “remains pending teacher review”, show `pending_teacher_review` and both zero counts.
  Leave the candidate untouched. The video shows the boundary, not a teacher decision.
- The Qwen paragraph refers to [committed open-weights evidence](../evidence/open_weights_run.json).
  It describes an earlier real model run; it does not announce a Qwen run during this recording.
- Rehearse aloud while making the actual screen movements. If a paragraph finishes early, hold
  the relevant evidence for a breath. If a run stalls or the finish drifts beyond 2:45, stop and
  rehearse again before recording a fresh continuous take. Do not rush the counter-evidence or gate.

If a human recording is unavailable, TTS is an **optional fallback**. Use a conversational UK
English voice at roughly 120 words per minute, with the contractions and short pauses intact.
Preview the project name, acronym and Qwen pronunciation; avoid an announcer style or identical
pauses after every sentence. Check the full take by ear and stopwatch. Keep generated audio and
video outside the repository; do not commit media binaries.
