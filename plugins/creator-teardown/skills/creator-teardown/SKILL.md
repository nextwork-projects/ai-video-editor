---
name: creator-teardown
description: Reverse-engineers a short-form creator's video format from their real numbers. Pulls a TikTok or YouTube Shorts profile (or pasted links, Instagram reels too) with view, like and save counts, transcribes the top videos word for word, measures pace, pauses and fillers, maps each video into timed beats, and writes a teardown.md someone can film from, a teardown.html page of their graphics, motion and sound, and the style.json the ai-editor plugin edits from (on its own it can write an edit plan as a table and .srt). Use when the user wants to analyse, break down or study a creator ("analyse @handle", "tear down @handle", "teardown of @handle", "break down this creator", "what makes this creator's videos work"), pastes TikTok, YouTube or Instagram links and asks what the pattern is, or asks to set up creator-teardown. Not for editing the user's own video like a creator when ai-editor is installed (its start skill), not for researching a topic, and not for cutting raw footage.
license: MIT
compatibility: Python 3.9+, ffmpeg, yt-dlp and internet access. Optional ElevenLabs key for verbatim transcripts and Gemini key for the look pass. Mac, Windows or Linux.
---

# Creator Teardown

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

Give it a creator. Get back a teardown of their format and a page of what they do on
screen, every claim tied to a view count and every timing measured.

## Output

`creator-teardowns/<handle>/`: `teardown.md` (the analysis), `teardown.html` (the page the user looks
at), `look.md` (what Claude reads), `style.json` (every measured number, for editing in this style),
plus the per-video files listed in `${CLAUDE_SKILL_DIR}/references/outputs.md`. An edit plan goes to
`edit-plans/<name>/`.

## First: doctor

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" doctor
```

Run it before the first teardown in a session. On Windows, use `py` wherever these
commands say `python3`.

`Ready.` means go. If it prints `Not ready`, or the user asks to install or set up
the skill, follow `${CLAUDE_SKILL_DIR}/references/setup.md`. The ElevenLabs and
Gemini keys are optional. Never ask for either in the chat: the user saves them with
`setkey` (`setkey --gemini`) in their own terminal.

`$VPY` below is `python3 "${CLAUDE_SKILL_DIR}/scripts/run.py"` (`py` on Windows), which runs a script with
the tool venv's Python wherever `AI_EDITOR_HOME` puts it.

## Pipeline

### Quick mode (called by ai-editor's start, setup or style-edit)

When another skill needs only the style.json, run exactly: Step 1 `list`, Step 2's two commands with
`--top 5` (5 plus 2 control videos), Step 3b's three, then Step 3c's four (a `gemini.py` that exits 2
with no key is skipped), then stop. The Step 0 parts question only if the caller has not asked it. Skip
`metrics.py`, the Step 3 written passes and Steps 4-6 (Step 3's "always run" is the visual pass, included).
About 15 minutes per creator on a laptop, measured: download and transcription about a minute a video,
`look.py` about 40 s a video, `graphics.py` about 20 s, `sound.py` 2 s, the page 15 s. Say so first.

### Step 0: Ask, once

Skip what the message already answers. One question box call:

1. **Which creators?** The handle or links they named (Recommended) / I'll paste more handles or
   links. Several is normal: people like one creator's captions and another's pace.
2. With more than one: **which part from whom?** Captions, pace (cuts, zooms, motion), visuals
   (graphics, face framing, cards), or **Not sure yet (Recommended)**: ask again after Step 3b, with
   each creator's `look.md` to compare.

### Step 1: Get the videos

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" list <handle> --platform tiktok --limit 40   # or youtube
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" list <name> --urls picks.txt   # pasted links, one a line
```
Prints a ranked table (views, x median) and writes `videos.json`; `*` marks 3x the median.

**Instagram:** profiles are login-walled, single reel links are not. Ask the user to paste
the reel links (10 or more, their best and some average ones), write them one per line to
`picks.txt`, and run `list <name> --urls picks.txt`. Instagram hides views from yt-dlp, so
the ranking and the control group use likes; say so in the teardown.

### Step 2: Download and transcribe the winners and a control group

```bash
$VPY "${CLAUDE_SKILL_DIR}/scripts/visual.py" download <handle>
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" transcribe <handle>
```

`--top N` downloads and transcribes N plus 2 control videos (the 2 closest to the
median; `--control` changes the 2). The default `--top 8` is 10 videos; `--top 5`, the
fast run, is 7; pass it to both commands. Both print the count first. `--ids <id>,<id>`
picks exact videos. The median ones are the control: a move that appears in the 500K
video *and* the 3K video is that creator's habit, not the reason the 500K one
worked. Keep at least 2.

Say the time first (download plus transcription, about a minute a video on a laptop). Whisper
(free, local) is the default; with an ElevenLabs key `transcribe` uses Scribe, which keeps every
filler ($0.22 an hour of audio; give the estimate before 10+ videos).
If filler counts lean on Whisper transcripts, say so in the teardown.

### Step 3: Measure, then analyse

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/metrics.py" <handle>
```

Writes `metrics.json` (WPM per third, pauses, fillers, sentence length, you/I/we,
repeated phrases), all off the word timestamps.

Then load `${CLAUDE_SKILL_DIR}/references/analysis-framework.md` and run its passes. Read
`transcripts/<id>.txt` (flat text with a stats header), never `transcripts/<id>.json` or `metrics.json`
whole:

1. **Beat map + timings.** Every video split into labelled beats with second-marks
   and word counts.
2. **Voice/vocab profile.** Sentence length, person, commands, recurring phrases, and
   the moves the user would not say.
3. **Visual pass.** Always run it. It is what lets the user edit their own video in
   this creator's style. See Step 3b.
4. **Card events**, only when the ask covers the creator's cards and graphics, or an
   edit plan is coming. Writes `events.json` in the shape in
   `${CLAUDE_SKILL_DIR}/references/edit-plan.md`. `scripts/strip.py` needs ffmpeg,
   `numpy` and `pillow`.

Do not skip the timings: "hook lands by 0:03 and runs 14 words, items are 8-11 s each"
is a format someone can film; "hook, then list, then close" is not.

### Step 3b: The visual pass (measured, no images for you to read)

```bash
$VPY "${CLAUDE_SKILL_DIR}/scripts/visual.py" measure <handle>
$VPY "${CLAUDE_SKILL_DIR}/scripts/look.py" measure <handle>
$VPY "${CLAUDE_SKILL_DIR}/scripts/gemini.py" look <handle>
```

Run them after `transcribe` (`look.py` matches OCR text to the spoken words).

1. `visual.py`: cuts and their kinds, shot lengths, zooms, pans and shake.
2. `look.py`: OCR 3 frames a second and YuNet faces: the captions (place, size, words,
   case, colours, weight, entrance), face framing, graphics share, palette, motion
   personality. About 40 s a video.
3. `gemini.py look`: Gemini Flash-Lite watches the 5 most-viewed videos (about 5,600
   tokens each) and names font, graphics style, transitions, what is not generic. Never
   a number.

**Then read `look.md` (under 48 lines). Do not open frames or sheets.** Every
field is in `${CLAUDE_SKILL_DIR}/references/look-pass.md`. Numbers in `style.json`
come from code; never edit them by hand. Where `look.md` and the model's words
disagree (say `motion: punchy` measured, `smooth` named), the measured one wins
and the teardown says both.

**No Gemini key** (`gemini.py look` exits 2): offer the free key once
(`references/setup.md` step 4). If the user skips it, run the fallback: one Agent
call with `model: "haiku"` that reads `sheets/<id>.jpg` for each video (one 3 x 3
sheet each, made by `visual.py`) and writes `video/<id>.look-ai.json` per
`gemini.py prompt`. Exact brief in `references/look-pass.md`. Then
`$VPY "${CLAUDE_SKILL_DIR}/scripts/gemini.py" merge <handle>`.

**No OCR engine** (doctor says optional): `captions` stays unmeasured and look.md
says so. Install it (`doctor` prints the line) rather than reading sheets yourself.

### Step 3c: The deep pass and the page

```bash
$VPY "${CLAUDE_SKILL_DIR}/scripts/graphics.py" measure <handle>
$VPY "${CLAUDE_SKILL_DIR}/scripts/gemini.py" kinds <handle>
$VPY "${CLAUDE_SKILL_DIR}/scripts/sound.py" measure <handle>
$VPY "${CLAUDE_SKILL_DIR}/scripts/report.py" build <handle>
```

Each measure prints one summary line and the file it wrote (`--json` prints the full block; not
needed: look.md has the numbers). Run them after Step 3b (graphics.py masks the speaker with look.py's faces). They add every
graphic (cropped, its kind, where it sits, how it enters and exits as a fitted GSAP ease),
cut kinds and camera moves (visual.py), sound effects and music, the first 3 seconds of each
video, winners against the control group, and an AI-tell scan of the creator's own look.
Fields, methods, ceilings and cost: `${CLAUDE_SKILL_DIR}/references/teardown-page.md`.
No Gemini key: `gemini.py kinds` exits 2; the kinds stay the code's guess, or run the haiku
fallback in that reference.

Then open `creator-teardowns/<handle>/teardown.html` for the user (`open` on a Mac, `start` on
Windows, `xdg-open` on Linux) and offer to publish it as an artifact. Do not read the page or
its images yourself: look.md has the numbers. Tell the user in two or three lines what the
winners do differently (the `Winners:` lines in look.md, with n) and any BAN-level AI tell
in their look.

Then ask in the question box (the page only shows the evidence; it has nothing to tick), one
multi-select question: "Which parts of @<handle> should your edit copy?" Options: captions,
pace, graphic kinds, entrance motion, layout, sound (at most 4 options a question: split into two
questions if needed), each option's description one measured line from look.md (e.g. "slides in
0.25 s with overshoot"). If any BAN tell sits
in a part they pick, say which before they confirm. Save the answer:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/editplan.py" blend <handle>-mine --from <handle> \
    --take captions,pace,graphics,entrances,layout,sound    # only the parts picked
```

style-edit reads `creator-teardowns/<handle>-mine/style.json`; a part left out uses its
default.

### Step 3d: Several creators (when the user named more than one)

Follow `${CLAUDE_SKILL_DIR}/references/blend.md`: Steps 1 to 3b per creator, `look.md` side by side,
then `editplan.py blend`.

### Step 4: Write the teardown

Fill `${CLAUDE_SKILL_DIR}/references/teardown-template.md` into
`creator-teardowns/<handle>/teardown.md`. Every video gets a stats line, verbatim
transcript, beat table with timings, patterns to keep and patterns to reject.

### Step 5 (optional): Turn it into a skill

Ask whether the format is worth keeping. If yes, follow
`${CLAUDE_SKILL_DIR}/references/skill-handoff.md`.

### Step 6 (optional): Plan the user's video in the creator's style

When the user hands over their own video, follow
`${CLAUDE_SKILL_DIR}/references/edit-plan.md`. It needs the creator's `events.json`
from the visual pass; it does not render.

## If a script stops

| message | do |
|---|---|
| doctor `Not ready: ...` | follow `references/setup.md` for each line it lists |
| `yt-dlp returned nothing` / `parsed 0 videos` | read the hint it prints: update yt-dlp (doctor shows how), or ask for single video links and use `--urls` |
| Instagram profile fails | ask for 10+ reel links (Step 1 "Instagram") |
| `... Fix the key, then rerun` (transcribe) | the ElevenLabs key is wrong: the user re-saves it with `setkey` in their own terminal, or drop it and use Whisper |
| `gemini.py` exits 2 (no key) | Step 3b "No Gemini key" |
| `Gemini rejected the key` / `none of ... is available to this key` | the user makes a new key at the link it prints; meanwhile the haiku fallback |
| `no videos in ... Run download first` | run `visual.py download <handle>` |
| `yt-dlp not found` | run `fetch.py doctor` and fix what it lists |
| some videos fail to transcribe | retry with `--ids`, then say which failed; never fill the gap |

## Hard rules

- **Real numbers or nothing.** Every claim about what works cites the view count next
  to it. Never say a video "went viral" without the number.
- **Verbatim transcripts only.** Never summarise a video that was not transcribed.
- **Structure is copied, voice is not.** Every teardown states what to reject.
- **Median control group.** At least two mid-performers transcribed, or the analysis
  cannot separate the format from the creator's habits.
- **Never invent a transcript line**, or a stat or quote for a card. If transcription
  failed, retry with `--ids`, then say it failed.
- **Never ask for the ElevenLabs or Gemini key in the chat.**
- **Measured numbers only in style.json.** `pace` and `zoom` come from `visual.py`;
  `captions`, `face`, `graphics` and `motion` from `look.py`; only words (`look`,
  `font_match`) from the model.
- **Read look.md, not frames.** Open a frame only to settle a question look.md
  cannot answer, and say which one. The user gets teardown.html; Claude gets look.md.
- **Winners against control: say n.** Never call a difference proven; "every winner"
  only means no overlap in this sample.
