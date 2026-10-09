---
name: cut
description: Cuts raw talking-head footage into a clean jump cut. Takes one take (mp4 or mov, any aspect, 4K phone footage is fine), transcribes it word by word, removes retakes, false starts, fillers and dead pauses, and renders cut.mp4 at the source resolution plus words.json timed to the cut. The user approves the cut on a page with the whole transcript and every removed word struck through. Use when the user says "cut my video", "just cut it", "remove my mistakes", "cut out the retakes", "remove the pauses", "clean up this take", "jump cut this", "tighten this clip", or asks only for the cut of a raw take; start calls it for a full edit. Runs before style-edit. Not for a general request to edit a video or to make it look like a creator (that is start), not for adding captions, zooms or cards (style-edit), and not for analysing someone else's videos (creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg and the venv the setup skill installs (faster-whisper). Recommended TypeSafe key (Jev decides the cut for a fraction of a cent; without it Claude decides). Optional ElevenLabs key or CrisperWhisper. Mac, Windows or Linux. Runs from the full ai-editor plugin folder (uses its lib/).
---

# Cut

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

```
edits/<name>/  transcript.txt (read this, never words.raw.json), spans.json (what to remove, quoted),
  review.md (what Jev was unsure of), paper-edit.md (the cut as text), cut-check.html (the approval
  page), cut.mp4 + words.json (the render and its words).
```

`<name>` is a slug of the file name (`IMG_1234.MOV` -> `img-1234`), relative to the folder Claude Code
started in. Never modify, move or copy the source file: pass its path.

`$PY` is `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py"`, the tool venv. On Windows, use `py`
wherever these commands say `python3`.
No venv yet: run the `setup` skill first. `S="${CLAUDE_SKILL_DIR}/scripts"`.

## No video yet?

Ask for the path of their own take first. If they have none, offer the sample take (a raw vertical
take with retakes, false starts and pauses left in) and download it into their folder:

```bash
curl -L -o sample-take.mp4 https://github.com/nextwork-projects/ai-video-editor/releases/download/sample-video/sample-take.mp4
```

## 0. Ask: the cut first, or everything at once

Before anything else, ask one question in the question box (start decides this for a whole edit):

> Do you want just the cut first, or the cut and the styled edit in one go?
> - **Just the cut first (Recommended).** You approve the cut before I add captions, zooms or
>   visuals, so a changed cut never rebuilds the visuals (fewer tokens).
> - **Everything at once.** I cut, then style without waiting. You still see the cut page and the
>   stills sheet before anything renders.

Skip it only when the user already answered ("just cut it", "cut and style it in one go") or start or
clips called this skill. **Just the cut first:** steps 1-6, then stop until the user approves the cut
**and** asks for the style. **Everything at once:** steps 1-5, open the cut page, go straight on to
style-edit; a later cut change re-runs style-edit from its plan step.

## 0b. Read the user's taste

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show --edit edits/<name>
```

Follow every rule in it. Save a reaction to a result ("too slow") with the taste skill before redoing.

## 1. Transcribe

```bash
$PY "$S/transcribe.py" <source> edits/<name>/words.raw.json
```

Say the time first: Whisper takes 1-4 minutes for a 3-minute take on a laptop, CrisperWhisper about
the length of the take. It picks ElevenLabs Scribe when a key is saved, else CrisperWhisper if setup
installed it, else the free local Whisper (`--engine whisper|crisper|scribe` overrides). Whisper drops
some ums and false starts; Scribe and CrisperWhisper keep them for the cut. With neither, say once that
setup can add one (CrisperWhisper's weights are non-commercial only). A take full of retakes:
`AI_EDITOR_WHISPER_MODEL=medium` hears them better (1.5 GB, twice as slow). Step 5 catches the rest.

**Never read `words.raw.json`**: `transcript.txt` has its words at 1/12 the size.

## 2. Decide what to cut

```bash
python3 "$S/retakes.py" propose edits/<name>
```

Code finds every possible cut (a line said again, an unfinished sentence, "wait, sorry", fillers) and
TypeSafe's Jev judges them in one request (a fraction of a cent) into `spans.json` and `review.md`.

- **Exit 0.** Read `review.md` only: the few items Jev was unsure of. Fix any you disagree with in `spans.json` (shape: `references/shapes.md`; rules:
  `references/retake-detection.md`), then go to step 3. Do not re-decide the items Jev was sure of; the
  read-through in step 3 catches a wrong one.
- **Exit 4: no TypeSafe key** (or Jev unreachable); **exit 5: the key was rejected.** Decide yourself:
  read `transcript.txt` and `candidates.md` (the places code flagged), follow
  `references/retake-detection.md`, and write `spans.json` (`references/shapes.md`). Tell the user once
  that a TypeSafe key (exit 5: a new one) makes this much cheaper, via the `setup` skill.

Last take wins, except alternate hooks. Never type a timestamp and never write a span for
a pause.

Only if the user wants it shorter, also read `references/editorial-rules.md` and add `redundant`
cuts. Jev does not make those: they are content calls.

A misheard name is one command, never a JSON rewrite: `python3 "$S/retakes.py" fix edits/<name>
cloud=Claude jiv=Jev` (whole words, timings untouched, kept in `fixes.json` for the captions).

## 3. Build

```bash
python3 "$S/build_timeline.py" <source> edits/<name> --dry-run
python3 "$S/build_timeline.py" <source> edits/<name>
```

Every pause (breaths included) over `--max-pause` (0.15 s) becomes 0.10 s; under music only gaps
between words are trimmed. Fix any `ERROR` the dry run prints, then run it for real.

Then the `cut-judge` agent scores `paper-edit.md` (what plays, `<<n>>` at each join) on a rubric
and fixes `spans.json`: a flub, restart or "wait" left in (add a span), a bad join or two takes
stitched into a sentence nobody said (move it), a good line lost that no better take replaces
(remove it). Launch, readers for takes over 5 min, and the approval score: `references/judge.md`.
- A `CLIPPED` line at the top means a pause cut ate a word. Rebuild with a larger `--pad`.
- Joins inside speech move to a quiet frame. Any `still in speech`: listen to it in step 5.

Build again if spans changed: paper is free, a render is not.

## 4. Render

```bash
python3 "$S/render.py" <source> edits/<name>
```

A 3-minute 4K take takes a few minutes: run long takes in the background.

## 5. Verify

```bash
$PY "$S/verify_cut.py" edits/<name> --engine <same engine as step 1>
```

Re-transcribes cut.mp4 and diffs it against the words the cut meant to keep.
- **MISSING**: a kept word is not in the render. Raise `--pad` (or narrow the span), rebuild, re-render.
- **SURVIVED**: each line prints its cut and source time and the span to add. A real repeat or
  stumble: add that span to `spans.json`. Clean speech there is a mishearing.
- **HEARD DIFFERENTLY** ("jev -> jeff") and filler notes are transcriber variance: no rebuild.
- **DOUBLED**: words said twice in a row. Natural ("very, very"): keep. A stumble: add its span.

One fix cycle, then show the user whatever is left.

## 6. The user approves

After every render (the first and every re-cut) run `python3 "$S/preview_cut.py" edits/<name>`. It
opens the page in the browser itself; never skip it or tell the user to open it (no browser, as on a
remote machine: give the full path to `cut-check.html`). Tell the user in two lines how many seconds
came out and what the page shows (struck-through words are cut, highlighted ones are judgement
calls). Then **wait**. "keep <line>": delete or narrow that span. "cut <line>": add one. Pauses
rushed or slow: rebuild with another `--max-pause`. After any change: build, render, verify, reopen.

After approval: hook check, then hook variants if `hooks.json` exists (`references/retake-detection.md`).

Only the user's approval finishes the cut; `cut.mp4` and `words.json` go to style-edit. On "just the
cut first", say they can ask for the style. Never start style-edit on your own. Called by start: as
the page opens, start the `visual-prep` agent in the background.

## If a script stops

| message | do |
|---|---|
| `no such file` / `ffmpeg could not read audio` | ask for the right path; never copy or convert the source |
| `faster-whisper missing` / `CrisperWhisper missing` | run with `$PY`, or the setup skill's step 3 |
| `no ElevenLabs key` (exit 2) / `HTTP 4xx`, `unreachable` (3) | drop `--engine scribe`, or re-save the key with the setup skill |
| `spans.json exists. Pass --force` | only on a fresh decision: `propose --force` (keeps spans.prev.json) |
| build `ERROR` on a quote | fix that span's quote or add `occurrence`, `--dry-run` again |
| `cannot derive a silence threshold` / `marked no silence` | speech and background are under 10 dB apart: `ffmpeg -i <source> -af volumedetect -vn -f null -`, pass `--noise` about 10 dB above the mean |
| render `ERROR ... (kept in <tmp>)` | say it; re-run render once |

## Rules

1. Every cut quotes the transcript. No quote, no cut.
2. A script, if the user has one, breaks ties between takes. Nothing is cut for being off-script.
3. Never stream-copy (`-c copy`) across cuts: it lands up to 2 s off.
4. Never hand over a render that has not been verified and approved.

## Self-check

`python3 "$S/test_build_timeline.py"`, `test_retakes.py`, `test_media.py` (needs ffmpeg).
