# Retake detection: how to decide what to cut

This is the only part of the cut that needs judgement. Everything else is mechanical and lives in
`build_timeline.py`. Your output is `spans.json`: a list of things to remove, quoted from the
transcript.

## What you are given

With a TypeSafe key, `retakes.py propose` has already decided the clear cases and written
`spans.json`. You read `review.md` (the uncertain items) and fix entries in `spans.json`. The rules
below are what you judge them by.

Without a key, you decide everything from `transcript.txt`: one line per phrase,
`[start-end] words`, with `(+1.4s)` marking a pause before a phrase. `candidates.md` lists the
places code flagged as possible restarts. Never read `words.raw.json`: it is the same words at
about 12x the size. Fillers, false starts and "wait, sorry" are in the transcript on purpose. They
are the evidence.

Whisper (the free engine) tidies speech: it drops some fillers and sometimes a false start. Scribe
and CrisperWhisper keep them all. On a Whisper transcript, a repeated opening a second apart is
often all that is left of a false start. Read the timings as well as the words.

## What you do not decide

**Pauses.** `build_timeline.py` tightens every silence over the pause target, measured from the
audio. Never write a span for silence.

**Timestamps.** Never type one. Quote the words; the script finds their exact edges.

## spans.json

The shape and field rules: `shapes.md`.

## What to cut

### `false_start`
A sentence stops mid-thought and restarts with the same opening words, usually within 2 seconds.

> "So the thing about, um, **the thing about** money is..."

Cut the abandoned attempt and keep the finished one.

### `retake`
A whole line said twice, seconds to about 30 seconds apart. **The last take wins**: people retry
until they get it right. Exceptions:
- The last attempt is itself broken or unfinished. Keep the best complete one.
- The user supplied a script and both takes are complete: keep the one closer to it.

Words that often come just before a retake: "wait", "sorry", "again", "let me do that again",
"one more time", or a hard stop followed by a long pause.

**A pause of about a second or more between two runs at the same idea means the first run was
abandoned**, even when it is a clean sentence on its own. Keep the run the speaker carried on from.
Never keep the start of one run and the end of another unless the join reads as one sentence.

### `filler`
"um", "uh", "you know", "I mean", "like". Cut whole words only. Do not strip every one: a "so" or
"like" that carries rhythm stays. Cut the ones that sound like hesitation.

### `meta`
Talking to themself, not to the viewer: "wait", "shoot", "let me start again", "was that okay?".
Always cut.

### `audio_event`
Scribe tags coughs, sniffs and lip smacks as tokens like `[coughs]`. Cut them.

### `redundant` (optional second pass)
Complete, clean content that does not earn its place. See `editorial-rules.md`. Only run this pass
when the user wants the video shorter. Every `redundant` cut is highlighted in cut-check.html.

## Procedure

1. Read the whole transcript. Note gaps over 1 second: retakes cluster around them.
2. Find repeats: near-identical phrases within about 30 seconds.
3. For each cluster, pick the keeper (last take wins, then the exceptions).
4. Mark false starts, then meta, then fillers.
5. For every cut ask: is this a worse take of something said better elsewhere? If there is no
   better take, it is not a cut. Repetition for emphasis, delivered cleanly both times, stays.
6. Write `spans.json`, then `build_timeline.py --dry-run` and read the cut list.
7. Read `paper-edit.md` straight through, as the viewer will hear it. Fix anything that reads
   wrong at a `<<n>>` join.

## Mistakes to check yourself against

- **Cut the good take.** The retry was itself flubbed and you kept it because it was last.
- **Cut deliberate repetition.** Said twice for rhythm, both clean: keep both.
- **Cut an improvised line** because it was not in the script. A script breaks ties between two
  takes of the same line. It is never a reason to cut a line.
- **Over-cut fillers** into machine-gun delivery with no breath.
- **A number mismatch.** "fifty million" and "50 million" are the same words.
