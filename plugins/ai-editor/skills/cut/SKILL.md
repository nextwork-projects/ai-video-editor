---
name: cut
description: Cuts raw talking-head footage into a clean jump cut. Takes one take (mp4 or mov, any aspect, 4K phone footage is fine), transcribes it word by word, removes retakes, false starts, fillers and dead pauses, and renders cut.mp4 at the source resolution plus words.json timed to the cut. The user approves the cut on a page with the whole transcript and every removed word struck through. Use when the user says "cut my video", "remove my mistakes", "cut out the retakes", "remove the pauses", "clean up this take", "jump cut this", "tighten this clip", or hands over raw footage with flubbed lines and gaps. Runs before style-edit. Not for adding captions, zooms or cards (that is style-edit), and not for analysing someone else's videos (that is creator-teardown).
---

# Cut

One raw take in. A clean jump cut out, with nothing on a timeline for the user to touch.

```
edits/<name>/
  words.raw.json    transcript of the source
  spans.json        what to remove, quoted (you write this)
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

## 0. Read the user's taste

```bash
python3 "${CLAUDE_SKILL_DIR}/../taste/scripts/taste.py" show
```

Follow every rule in it; the scripts already read its settings. When the user reacts to the result
("too slow", "captions too small"), save it with the taste skill before redoing the edit.

## 1. Transcribe

```bash
$PY "$S/transcribe.py" <source> edits/<name>/words.raw.json
```

Uses ElevenLabs Scribe when a key is saved (`~/.config/creator-teardown/.env`), else the free local
Whisper model. `--engine whisper|scribe` overrides. Whisper takes 1-4 minutes for a 3-minute take on a
laptop. Tell the user Scribe catches more fillers and false starts, once, if they have no key.

Whisper `small` sometimes merges a false start into the next run, or garbles a line. When the take
is full of retakes, `AI_EDITOR_WHISPER_MODEL=medium` hears them better (a 1.5 GB download, about
twice as slow). Either way, step 5 catches what the transcript missed.

## 2. Decide what to cut (your job)

Read `references/retake-detection.md` and follow it. Read the whole transcript, then write
`edits/<name>/spans.json`: the words to remove, quoted, with a kind and a note. Last take wins.
Never type a timestamp and never write a span for a pause.

Only if the user wants it shorter, also read `references/editorial-rules.md` and add `redundant`
cuts.

## 3. Build

```bash
python3 "$S/build_timeline.py" <source> edits/<name> --dry-run
python3 "$S/build_timeline.py" <source> edits/<name>
```

Every pause longer than `--max-pause` (default 0.15 s) is shortened to 0.10 s. Breaths count as
pauses: a gap between words is cut when the audio in it stays well under speech level. `--dry-run` prints the cut list and the resulting length.
Fix any `ERROR` it prints (a quote that does not match, or a phrase that appears twice without
`occurrence`), then run it for real.

If it stops with "cannot derive a silence threshold", the room is noisy. Measure with
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

Rebuild the page so it includes the video, then open it:

```bash
python3 "$S/preview_cut.py" edits/<name>
open edits/<name>/cut-check.html        # Windows: start "" <path>   Linux: xdg-open <path>
```

Tell the user in two lines: how many seconds came out, and what the page shows (struck-through
words are cut, highlighted ones are judgement calls). Then **wait**.

- "keep <line>": delete or narrow that entry in `spans.json`.
- "cut <line>": add an entry.
- Pauses feel rushed or slow: rebuild with a different `--max-pause`.

After any change: build, render, verify, reopen the page. Only when the user approves is the cut
done. `cut.mp4` and `words.json` are what style-edit takes next.

## Rules

1. Every cut quotes the transcript. No quote, no cut.
2. A script, if the user has one, breaks ties between two takes of the same line. Nothing is cut
   for being off-script.
3. Never stream-copy (`-c copy`) across cuts. It snaps to keyframes and lands up to 2 s off.
4. Never hand over a render that has not been verified and approved.

## Self-check

```bash
python3 "$S/test_build_timeline.py"
```
