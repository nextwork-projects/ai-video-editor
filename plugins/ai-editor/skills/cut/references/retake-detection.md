# Retake detection: how to decide what to cut

This is the only part of the cut that needs judgement. Everything else is mechanical and lives in
`build_timeline.py`. Your output is `spans.json`: a list of things to remove, quoted from the
transcript.

## What you are given

`words.raw.json`: every word with `start` and `end` in seconds. Fillers, false starts and
"wait, sorry" are in it on purpose. They are the evidence.

Whisper (the free engine) tidies speech: it drops some fillers and sometimes a false start. Scribe
keeps them all. On a Whisper transcript, a repeated opening a second apart is often all that is
left of a false start. Read the timings as well as the words.

## What you do not decide

**Pauses.** `build_timeline.py` tightens every silence over the pause target, measured from the
audio. Never write a span for silence.

**Timestamps.** Never type one. Quote the words; the script finds their exact edges.

## spans.json

```json
[
  {"text": "so the thing about, um,", "kind": "false_start", "note": "restarts at 5.8s"},
  {"text": "wait, sorry", "kind": "meta"},
  {"text": "the second thing is that you", "kind": "retake", "occurrence": 1,
   "confidence": "medium", "note": "keeper is the take at 70.4s"}
]
```

| field | rule |
|---|---|
| `text` | Words copied from the transcript. Punctuation and case do not matter. |
| `kind` | `retake`, `false_start`, `filler`, `meta`, `audio_event`, `redundant` |
| `occurrence` / `after` | Required when the phrase appears more than once. `occurrence` is 1-based. `after` takes the first match starting after that many seconds. |
| `confidence` | `high` (default), `medium`, `low`. `low` cuts are highlighted for the user. |
| `note` | Why, in a few words. For a retake, where the keeper is. |

Two spans must not overlap. Merge them into one.

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
