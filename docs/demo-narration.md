# Final demo narration — target 2:40

Use this with the [time-coded storyboard](demo-guide.md), [production notes](demo-production.md)
and [operator cues](demo-operator-cues.md). Read only the blockquotes aloud. Headings, timing
notes and `[pause]` cues are for the recorder.

The script has **279 displayed words / 292 spoken-word equivalents**. The spoken count expands
each `MCP` to “M C P”, `two-point-five` to “two point five”, `three-B` to “three B”, and the score
numbers to “sixty one” and “eighty seven”. Contractions and other hyphenated words count as one;
headings and bracketed cues are excluded. At about 120 words per minute, speech takes **2:26**,
leaving about fourteen seconds for the opening interval, breaths, screen movements and holds,
including the final two-second hold. Use 115–125 words per minute as a comfortable range, then
check the actual timing aloud. Aim for **2:40**, with a finished take between **2:30 and 2:45**.

Prefer the creator's **own human voice**. Imagine showing the project to one judge sitting beside
you. Explain what you're looking at; there's no need to perform. Keep your normal accent and
breathing. Let the pace vary slightly, with a little emphasis on “only a candidate” and the two
zero counts. Avoid over-enunciating technical names or giving every sentence the same rhythm.
The pauses are ordinary breaths.

Have the command visible before capture starts. **Start screen capture first**, then press Enter
as the opening sentence begins:

```powershell
.\.venv\Scripts\python.exe -m mwalimulens.demo_run
```

Do not read the command, evidence identifiers or raw JSON aloud. Point to the matching evidence
and exact tool names on the freshly generated page. The final video is one continuous live take.

## 0:00–0:25 — introduce the purpose and run the command

> I built MwalimuLens to help teachers see how a learner's evidence changes over time. I'm running
> the demo now, using synthetic learner data. For this recording, a deterministic model drives the
> demo, but the MCP calls you're seeing are real. [pause] Let's look at what came back.

## 0:25–0:55 — follow the evidence, including the contradiction

> These fraction assessments go from sixty-one to eighty-seven per cent across four terms.
> That's encouraging. But here's the counter-evidence: the learner struggled to justify their
> method independently in an open-ended problem. [pause] The higher scores don't erase that note.
> Later practical work adds support, but there's still a question to explore.

## 0:55–1:22 — explain the real MCP activity

> Here are the calls from the command we just ran. Our custom Education MCP fetched the competency
> evidence. The borrowed Filesystem MCP read a teaching reference, using read-only access.
> That file isn't learner evidence. Then the Education MCP flagged the pattern for review.
> Each call is recorded in the audit.

## 1:22–1:43 — show the candidate and its uncertainty

> The candidate says fraction performance improved, while independent explanation is still mixed.
> It's only a candidate. We can see what we're unsure about, and the question for the teacher:
> does that improvement carry over to explaining an unfamiliar fraction problem?

## 1:43–2:03 — stop at the human boundary

> Now the agent stops. The teacher must approve, edit or reject the candidate. [pause]
> It's still pending teacher review, with zero teacher decisions and zero profile updates.
> The model can't call the teacher's review action.

## 2:03–2:25 — distinguish the separate real model evidence

> This separate pass comes from a real Qwen two-point-five, three-B run that's already committed
> in the repository. Today's deterministic demo isn't that open-weights run. Eleven current
> evaluations pass, and we've kept the two historical model failures.

## 2:25–2:40 — acknowledge the limitation and close

> The evidence is visible. The teacher decides. [pause] It's still a small, synthetic evaluation.
> We haven't established how well it works in real classrooms.

Finish the last sentence by about **2:38**. Hold the closing screen silently for two seconds,
then stop capture at about **2:40**.

## Delivery and rehearsal notes

- Say “pass” as a word, “M C P” as letters, and “Qwen two-point-five, three-B” naturally, without
  stretching each syllable. Leave the exact `qwen2.5:3b` spelling visible on screen.
- Point to EV-008 while describing the open-ended problem. The assessment sequence is 61%, 78%,
  84%, 87%; the later practical task is 81%. The script does not claim every score rises.
- During the tool paragraph, point to `get_competency_evidence`, `read_text_file`, then
  `flag_pattern_for_review`. The spoken explanation is deliberately less technical than the labels.
- On “still pending teacher review”, show `pending_teacher_review` and both zero counts.
  Say the status as normal words; don't say “underscore”. Leave the candidate untouched.
- The Qwen paragraph refers to [committed open-weights evidence](../evidence/open_weights_run.json).
  It describes an earlier real model run; it does not announce a Qwen run during this recording.
- Do one complete **stopwatch rehearsal** with the actual command and screen movements. Keep the
  spoken explanation connected to what's visible. If a paragraph finishes early, hold its evidence
  for a breath; reserve the final two seconds for the silent closing screen.
- Play back a **microphone sample**: check clarity, volume and whether it sounds like your ordinary
  voice. Check **screen legibility** at the size judges will watch, especially EV-008, the three tool
  names, the pending status and both zero counts.
- If the take runs beyond **2:45**, shorten awkward wording or reduce unnecessary navigation, then
  rehearse again. Don't simply speak faster. Keep all the evidence and boundary points. If a live
  run stalls, stop and record a fresh continuous take once the problem is resolved.

TTS is an **optional fallback** if a human recording isn't possible. Choose a conversational UK
English voice around 120 words per minute, retaining the contractions and normal breaths.
Listen to the project name, “M C P” and “Qwen two-point-five, three-B” before using it. Avoid an
announcer style or identical pauses after every sentence, and check the whole take by ear and
stopwatch. Keep generated audio and video outside the repository; do not commit media binaries.
