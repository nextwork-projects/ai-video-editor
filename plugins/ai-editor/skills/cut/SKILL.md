---
name: cut
description: Cuts raw talking-head footage into a clean jump cut. Takes one take (mp4 or mov, any aspect, 4K phone footage is fine), transcribes it word by word, removes retakes, false starts, fillers and dead pauses, and renders cut.mp4 at the source resolution plus words.json timed to the cut. The user approves the cut on a page with the whole transcript and every removed word struck through. Use when the user says "cut my video", "just cut it", "remove my mistakes", "cut out the retakes", "remove the pauses", "clean up this take", "jump cut this", "tighten this clip", or asks only for the cut of a raw take; start calls it for a full edit. Runs before style-edit. Not for a general request to edit a video or to make it look like a creator (that is start), not for adding captions, zooms or cards (style-edit), and not for analysing someone else's videos (creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg and the venv the setup skill installs (faster-whisper). Recommended TypeSafe key (Jev decides the cut for a fraction of a cent; without it Claude decides). Optional ElevenLabs key or CrisperWhisper. Mac, Windows or Linux. Runs from the full ai-editor plugin folder (uses its lib/).
---

# Cut

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows (asking, looking real, motion, story and framing, privacy, cost).

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

One raw take in. A clean jump cut out, with nothing on a timeline for the user to touch.

```
edits/<name>/
  words.raw.json    transcript of the source (never read it: use transcript.txt)
  transcript.txt    the same words, one line per phrase with times
  spans.json        what to remove, quoted (retakes.py proposes it, you review)
  review.md         the items Jev was unsure of
  jev-usage.jsonl   what each Jev request cost
  decisions.json    kept spans in source seconds
  report.json       every cut with its reason
  paper-edit.md     the cut as text, for your read-through
  cut-check.html    the page the user approves
  cut.mp4           the render
  words.json        words re-timed onto cut.mp4
```

`<name>` is a short slug of the file name (`IMG_1234.MOV` -> `img-1234`). Paths are relative to the
folder Claude Code was started in. Never modify, move or copy the source file. Pass its path.

Python: `PY=~/.ai-video-editor/venv/bin/python` (Windows: `%USERPROFILE%\.ai-video-editor\venv\Scripts\python.exe`).
If it is missing, run the `setup` skill first. `S="${CLAUDE_SKILL_DIR}/scripts"`.

## No video yet?

The user's own talking-head video is the main path: ask for its path first. If they have none,
offer the sample take (a raw vertical take with retakes, false starts and pauses left in)
and download it into their folder:

```bash
curl -L -o sample-take.mp4 https://github.com/nextwork-projects/ai-video-editor/releases/download/sample-video/sample-take.mp4
```

`curl` ships with Mac, Linux and Windows 10 and later.

## 0. Ask: the cut first, or everything at once

Before anything else, ask the user one question in the question box, even if they said "edit my
video like @creator":

> Do you want just the cut first, or the cut and the styled edit in one go?
> - **Just the cut first.** I take out the retakes, false starts and pauses, and you approve that
>   before I add captions, zooms or visuals. If the cut changes, the visuals don't have to be
>   rebuilt, so it uses fewer tokens.
> - **Everything at once.** I cut it, then carry straight on into the style without waiting for you
>   to approve the cut. You still see the cut page and the stills sheet before anything renders.

List "just the cut first" first, marked (Recommended). Skip the question only when the user already
answered it ("just cut it", "cut and style it in one go") or when start or clips called this skill
(they have already decided).

- **Just the cut first:** run steps 1-6 and stop. Do not start style-edit until the user approves
  the cut **and** asks for the style ("style it", "now edit it like @creator").
- **Everything at once:** run steps 1-5, open the cut page (step 6), then go straight on to
  style-edit without waiting. If the user changes the cut afterwards, rebuild the cut and re-run
  style-edit from its plan step.

## 0b. Read the user's taste

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show --edit edits/<name>
```

Follow every rule in it; the scripts already read its settings. When the user reacts to the result
("too slow", "captions too small"), save it with the taste skill before redoing the edit.

## 1. Transcribe

```bash
$PY "$S/transcribe.py" <source> edits/<name>/words.raw.json
```

Say the time first (below). Picks the engine itself: ElevenLabs Scribe when a key is saved, else CrisperWhisper when the
setup skill installed it, else the free local Whisper model. `--engine whisper|crisper|scribe`
overrides. Whisper takes 1-4 minutes for a 3-minute take on a laptop, CrisperWhisper about the
length of the take. Whisper tidies speech (drops some ums and false starts); Scribe and
CrisperWhisper keep them, and the cut uses them. If the user has neither, say once that setup can
add either. CrisperWhisper's weights are licensed for non-commercial use only: say so if they ask
for it.

Whisper `small` sometimes merges a false start into the next run, or garbles a line. When the take
is full of retakes, `AI_EDITOR_WHISPER_MODEL=medium` hears them better (a 1.5 GB download, about
twice as slow). Either way, step 5 catches what the transcript missed.

**Never read `words.raw.json`.** It is about 12x bigger than the same words as text. Everything
below reads `transcript.txt` or the files `retakes.py` writes.

## 2. Decide what to cut

```bash
python3 "$S/retakes.py" propose edits/<name>
```

Code finds every place that might be a cut (a line said again, a sentence left unfinished, "wait,
sorry", fillers) and TypeSafe's Jev model judges them all in one request, for a fraction of a cent.
It writes `spans.json`, `review.md` and `transcript.txt`, and prints what Jev cost.

- **Exit 0.** Read `review.md` only: the few items Jev was unsure of, each with the words and what
  was done. Fix any you disagree with in `spans.json` (`references/retake-detection.md` has the
  format and the rules), then go to step 3. Do not re-decide the items Jev was sure of; the
  read-through in step 3 catches a wrong one.
- **Exit 4: no TypeSafe key** (or Jev unreachable). Fall back to deciding yourself: read
  `transcript.txt` and `candidates.md` (the places code flagged), follow
  `references/retake-detection.md`, and write `spans.json`. Tell the user once that a
  TypeSafe key makes this much cheaper (the `setup` skill walks them through it).

`propose` will not overwrite an existing `spans.json`; `--force` replaces it and keeps the old one
as `spans.prev.json`. Last take wins either way. Never type a timestamp and never write a span for
a pause.

Only if the user wants it shorter, also read `references/editorial-rules.md` and add `redundant`
cuts. Jev does not make those: they are content calls.

A misheard word (a name the transcriber spelled wrong) is one command, never a rewrite of the JSON:

```bash
python3 "$S/retakes.py" fix edits/<name> cloud=Claude jiv=Jev
```

It fixes `words.raw.json` and `words.json` in place, whole words only, timings untouched.

## 3. Build

```bash
python3 "$S/build_timeline.py" <source> edits/<name> --dry-run
python3 "$S/build_timeline.py" <source> edits/<name>
```

Every pause longer than `--max-pause` (default 0.15 s) is shortened to 0.10 s. Breaths count as
pauses: a gap between words is cut when the audio in it stays well under speech level. `--dry-run` prints the cut list and the resulting length.
Fix any `ERROR` it prints (a quote that does not match, or a phrase that appears twice without
`occurrence`), then run it for real.

Music under the voice is handled: it prints "music bed" and trims only the gaps between
transcript words, never inside one. If it stops with "cannot derive a silence threshold", speech
and background are under 10 dB apart. Measure with
`ffmpeg -i <source> -af volumedetect -vn -f null -` and pass `--noise <dB>` about 10 dB above the
mean volume.

Then read `edits/<name>/paper-edit.md` straight through. It is what the viewer will hear, with
`<<n>>` at each join. Critique it yourself before rendering:
- A flub, restart or "wait" still in the text: add a span.
- A join that reads wrong, or two halves of different takes stitched into a sentence nobody said:
  move the span.
- A good line gone that no better take replaces: remove that span.
- A `CLIPPED` line at the top means a pause cut ate a word. Rebuild with a larger `--pad`.

Loop until it reads clean. It costs nothing; a render costs minutes.

## 4. Render

```bash
python3 "$S/render.py" <source> edits/<name>
```

Plain ffmpeg. Source resolution, H.264 CRF 18, AAC 192k, frame-accurate, short audio fades at
every join. A 3-minute 4K take renders in a few minutes. Run it in the background for long takes.

## 5. Verify

```bash
$PY "$S/verify_cut.py" edits/<name> --engine <same engine as step 1>
```

Re-transcribes cut.mp4 and diffs it against the words the cut meant to keep.
- **MISSING**: a kept word is not in the render. Raise `--pad` (or narrow the span that ate it),
  rebuild, re-render.
- **SURVIVED**: printed as phrases in context. A repeat or stumble there is real: map its cut time
  back to source time with `decisions.json`, quote the raw tokens at that time in a new span. Clean
  speech there only means the raw transcript misheard that line.
- Notes about fillers or other small differences are transcriber variance, not errors.

One fix cycle, then show the user whatever is left.

## 6. The user approves

Every time a cut is rendered, the first one and every re-cut, rebuild the page so it includes the
video. The script opens it in the browser itself:

```bash
python3 "$S/preview_cut.py" edits/<name>
```

Never skip this, and never tell the user to open the page themselves. If the browser does not open
(a remote machine), give them the full path to `cut-check.html`.

Tell the user in two lines: how many seconds came out, and what the page shows (struck-through
words are cut, highlighted ones are judgement calls). Then **wait**.

- "keep <line>": delete or narrow that entry in `spans.json`.
- "cut <line>": add an entry.
- Pauses feel rushed or slow: rebuild with a different `--max-pause`.

After any change: build, render, verify, reopen the page. Only when the user approves is the cut
done. `cut.mp4` and `words.json` are what style-edit takes next.

On "just the cut first", stop here after approval: say the cut is done and that they can ask for
the style when they're ready. Never start style-edit on your own.

## If a script stops

| message | do |
|---|---|
| `no such file` / `ffmpeg could not read audio` (transcribe) | ask for the right path; never copy or convert the source |
| `faster-whisper missing` / `CrisperWhisper missing` | run with `$PY`, or the setup skill's step 3 |
| `no ElevenLabs key` (exit 2) / `HTTP 4xx` (exit 3) | drop `--engine scribe`, or re-save the key with the setup skill |
| `spans.json exists. Pass --force` | only on a fresh decision: `propose --force` (keeps spans.prev.json) |
| build `ERROR` on a quote | fix that span's quote or add `occurrence`, `--dry-run` again |
| `cannot derive a silence threshold` / `marked no silence` | measure with volumedetect and pass `--noise` (step 3) |
| render `ERROR ... (kept in <tmp>)` | say the message; re-run render once; the temp folder has the segments |

## Rules

1. Every cut quotes the transcript. No quote, no cut.
2. A script, if the user has one, breaks ties between two takes of the same line. Nothing is cut
   for being off-script.
3. Never stream-copy (`-c copy`) across cuts. It snaps to keyframes and lands up to 2 s off.
4. Never hand over a render that has not been verified and approved.

## Self-check

```bash
python3 "$S/test_build_timeline.py"
python3 "$S/test_retakes.py"
python3 "$S/test_media.py"      # needs ffmpeg: render frame counts, music bed
```
