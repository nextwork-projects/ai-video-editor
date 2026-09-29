# Analysis framework

Passes 1 and 2 run over every transcribed video. Pass 3 runs when the ask covers
the creator's look or editing.

**Run `scripts/metrics.py <handle>` first.** It computes every objective number
in Pass 2 off the word timings and writes `metrics.json`: WPM overall and per
third, time to first word, sentence length, pause rate and longest pause,
filler rate, you/I/we counts, repeated n-grams. Read those numbers, do not
re-derive them by eye. What the script cannot do is label a beat or judge a
register; that is the analyst's job.

The transcript JSON carries word-level timings, so every number below is
measured, not estimated:

```python
import json
d = json.load(open("creator-teardowns/<handle>/transcripts/<id>.json"))
words = [w for w in d["words"] if w["type"] == "word"]   # skip "spacing"
words[0]["start"], words[0]["end"]                        # seconds, float
d["audio_duration_secs"]
```

---

## Pass 1: Beat map + timings

Split the transcript into **beats**. A beat is one job the script is doing, not
one sentence. Label each with the timestamp of its first word.

Beat labels are discovered per creator, not imposed. Common ones:

`cold open` · `hook` · `open loop` · `credential` · `context` ·
`item N` · `mechanism / the why` · `example` · `objection` ·
`reframe` · `CTA`

For each video produce this table:

| Beat | Start | Dur | Words | WPM | Text |
|---|---|---|---|---|---|
| hook | 0:00 | 3.1s | 14 | 271 | "Here are three strategies you can use to..." |
| open loop | 0:03 | 4.8s | 21 | 262 | "The third one is so overlooked that..." |
| item 1 | 0:08 | 9.2s | 38 | 248 | ... |

Then the numbers that make the format buildable:

- **Time to hook**: when does the first content word land? Under 1.0s or not.
- **Hook length**: seconds and words. This is the number people get wrong.
- **Beat count** and **seconds per item**, with the spread (are items even, or
  does the last one get double the time?).
- **Overall WPM**, and WPM *per beat*. Most good short-form accelerates into the
  list and slows for the close. If it does, that is a directable note.
- **Where the CTA starts**, as a percentage of total runtime.
- **Does the last item get the most time?** Almost always yes in the winners.

### Across the set

One summary table, all videos, one row each: duration, views, ×median, time to
hook, beat count, sec/item, WPM, close type.

Then say what is **constant across every video**: that is the format. Anything
that varies is the creator improvising and should not become a rule.

### The control check

Compare each move against the median-performing videos:

- Appears in winners **and** median videos → the creator's habit. Not the lever.
- Appears **only** in winners → candidate lever. Say so, and say how many
  videos support it. Two out of six is a hypothesis, not a rule.

---

## Pass 2: Voice / vocab profile

Measured off the same transcripts.

**Sentence shape**
- Median sentence length in words, and the range.
- Longest sentence and shortest. Short-form voices usually run 6–14 words with
  one deliberate long sentence for contrast.
- Fragment rate. Do they speak in full sentences or clipped ones?

**Person and stance**
- Count of `you` / `your` vs `I` / `my` vs `we`. Ratio, not raw count.
- Imperative density: bare-verb commands per 100 words ("write down", "stop",
  "open your laptop").
- Do they ever name themselves or claim a credential?

**Recurring phrases**
- Repeated 3–5 word n-grams across the set. These are the creator's tics and
  the most copyable part of a voice.
- Item connectors: "first / second / finally" vs "and then" vs bare asyndeton.
- Their sticky-line pattern: where the quotable line sits in each item, and
  what shape it takes.

**Voice audit.** If the user has a voice guide (a style doc, a voice skill, a list
of words they won't say), load it and audit against it. Otherwise start from
`hype_hits` in `metrics.json` and ask the user which moves they would never say.
Flag every instance with the line it appears in.

Report these as **counts with examples**. They are not failures of the creator,
they are the conversion work a new skill has to do. A creator can be at 2M
views *because of* moves the user will not use. Say that plainly.

**Register call.** One paragraph: how would this sound out of the user's mouth,
and what specifically has to change. This paragraph is the bridge to
`skill-handoff.md`.

---

## Pass 3: Visual events (any teardown of a look or an edit)

Mandatory when the ask covers the creator's style, editing or visuals, not only the
script. Frames at 2 fps find the events. Every boundary is then timed at the source
frame rate, because pops and slides are shorter than 0.5 s.

- **Event log.** One row per image, card, logo, drawn mark and text block: in, settled,
  out and gone to the frame, what it shows and where it came from (real UI, screen
  recording, logo, photo, AI image, custom graphic).
- **Trigger.** The spoken word that names it, that word's start from the transcript,
  and the lag (in minus word start). The lag is what makes the edit replicable.
- **Entrance and exit.** Cut, pop (start scale, overshoot, frames to settle), fade,
  slide (direction), typewriter. Counted in frames at 30 fps, never guessed at 2 fps.
- **Placement.** Resting box as % of frame, layer (over face, beside, behind a head
  cutout, full frame), corners, border and shadow, motion inside the card.
- **Rhythm.** Events per minute, median time on screen, gap between cards, share that
  land on a hard cut, and what the face framing does while a card is up.
- **Audio.** Music bed (gap loudness against speech) and whether a sound marks entrances.
- **Tool.** `python3 scripts/strip.py <handle> <id> <t>` (in this skill's folder; needs numpy
  and pillow) downloads the video on first use and cuts a frame-labelled 30 fps strip around t; `--measure x0,y0,x1,y1` prints how a card box
  changes per frame. Read the strip itself: the measure numbers also pick up head and
  hand movement. Take every boundary from strips, never from `ffmpeg fps=2` frames, which
  ran 0.233 s behind the mp4 timeline on TikTok downloads.
- Write `events.json` next to `teardown.md`, in the shape in `edit-plan.md`, so a skill
  reads the numbers, not prose. `scripts/editplan.py style` turns it into the creator's rules.
