---
name: creator-teardown
description: Reverse-engineer a short-form creator's video format from their real numbers, then plan your own video in their style. Pulls a TikTok or YouTube Shorts profile with view, like and save counts, transcribes the top videos word for word with timings, measures pace, pauses and fillers, maps each video into timed beats, and writes a teardown.md someone can film from. From the creator's measured edit it also writes an edit plan for the user's own video, every card timed to its word, as a table and an .srt to import into an editor. Use when the user names a creator or account and wants to analyse, break down or study their videos ("analyse @handle", "teardown of @handle", "what makes this creator's videos work"), pastes TikTok or YouTube links and asks what the pattern is, hands over their own video and says "edit this like @handle", or asks to install or set up creator-teardown. Not for researching a topic, and not for cutting raw footage.
---

# Creator Teardown

Give it a creator. Get back a teardown of their format, with every claim tied to a
view count and every timing measured off the transcript. Optionally, a plan for
editing the user's own video the way that creator edits.

## Output

Everything lands under the folder Claude Code was started in:

```
creator-teardowns/<handle>/
  videos.json                 stats for every video pulled
  transcripts/<id>.json       verbatim, word-level timings
  transcripts/<id>.txt        flat text + role/views/duration/wpm header
  metrics.json                measured pace, pauses, fillers per video
  video/<id>.mp4              the picked videos (visual pass)
  video/<id>.visual.json      cut times, shot lengths, zoom events per video
  sheets/<id>-NN.jpg          contact sheets: 2 frames a second, timestamps burned on
  style.json                  pace, zoom and captions, for editing in this style
  teardown.md                 THE ANALYSIS
  events.json                 card events, when the card pass ran
edit-plans/<name>/
  plan.md, plan.srt           the user's video, planned in the creator's style
```

## First: doctor

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" doctor
```

Run it before the first teardown in a session. On Windows, use `py` wherever these
commands say `python3`.

`Ready.` means go. If it prints `Not ready`, or the user asks to install or set up
the skill, follow `${CLAUDE_SKILL_DIR}/references/setup.md`. The ElevenLabs key is
optional. Never ask for it in the chat: the user saves it with `setkey` in their
own terminal.

`VPY` below is the tool venv's Python: `~/.ai-video-editor/venv/bin/python`
(`%USERPROFILE%\.ai-video-editor\venv\Scripts\python.exe` on Windows).

## Pipeline

### Step 1: Get the videos

**Whole profile (TikTok or YouTube Shorts, free):**
```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" list <handle> --platform tiktok --limit 40
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" list <handle> --platform youtube --limit 40
```
Prints a ranked table (views, ×median, duration) and writes `videos.json`.
`*` marks videos at 3× or more of that creator's own median.

**Hand-picked links** (the user pastes the videos they like):
```bash
# one URL per line
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" list <name> --urls picks.txt
```

**Instagram:** yt-dlp cannot pull Instagram. It is login-walled even with browser
cookies. Check whether the creator posts the same videos to TikTok or YouTube and
use that account.

### Step 2: Download and transcribe the winners and a control group

```bash
$VPY "${CLAUDE_SKILL_DIR}/scripts/visual.py" download <handle>
python3 "${CLAUDE_SKILL_DIR}/scripts/fetch.py" transcribe <handle>
```

The default takes the 8 most-viewed videos plus the 2 closest to the median: 10
videos. For a fast run, pass `--top 5` to both commands. `--ids <id>,<id>` picks
exact videos. The median ones are the control: a move that appears in the 500K
video *and* the 3K video is that creator's habit, not the reason the 500K one
worked. Keep at least 2.

**Whisper is the default and free.** It runs on this computer off the downloaded
video. **Scribe is better for the voice profile when a key exists**: it keeps every
filler, false start and repetition, which Whisper partly drops. With a key saved,
`transcribe` uses Scribe automatically ($0.22 per hour of audio; tell the user the
estimate before more than 10 videos). `--engine whisper|scribe` overrides. When the
teardown's voice profile leans on filler counts and Whisper made the transcripts,
say so in the teardown.

### Step 3: Measure, then analyse

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/metrics.py" <handle>
```

Writes `metrics.json`: WPM overall and per third, time to first word, sentence length,
pause rate, longest pause, filler rate, you/I/we counts, repeated phrases. All computed
off the word timestamps, never estimated.

Then load `${CLAUDE_SKILL_DIR}/references/analysis-framework.md` and run its passes:

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

Do not skip the timings. "Hook, then list, then close" is not a format. "Hook lands by
0:03 and runs 14 words, items are 8–11s each, close is one sentence" is a format
someone can film.

### Step 3b: The visual pass

```bash
$VPY "${CLAUDE_SKILL_DIR}/scripts/visual.py" measure <handle>
```

Per video it finds every cut (frame differencing, so locked-off jump cuts count),
shot lengths, and zoom events (a punch is an instant scale step, a push is a slow
one). It writes `video/<id>.visual.json`, contact sheets in `sheets/`, and merges
`pace` and `zoom` into `style.json`. Run it after `transcribe`, so `pace.wpm` and
`pace.max_pause_s` have transcripts to read. Those numbers come from the script.
Never edit them by hand.

Then fill the `captions` block yourself. Read 2 or 3 sheets per video, from
different videos: the first sheet (the hook) and one from the middle. Each tile
is one frame, its time burned top left. To check a colour or font closely, pull
one full frame: `ffmpeg -ss <t> -i video/<id>.mp4 -frames:v 1 frame.png`, then read it.

Write into `style.json`, keeping every other key:

```json
"captions": {
  "present": true,
  "words_per_caption": 3,
  "y_pct": 62,
  "size_pct": 6.5,
  "case": "lower",
  "font_match": "Montserrat",
  "weight": 800,
  "color": "#FFFFFF",
  "highlight_color": "#FFE14D",
  "stroke": true,
  "box": false,
  "animation": "pop"
}
```

- `present`: false if the creator burns in no captions. Then the rest can be null.
- `words_per_caption`: the usual number of words on screen at once.
- `y_pct`: the caption's vertical centre, as % of frame height from the top.
- `size_pct`: cap height of the text as % of frame height.
- `case`: `lower`, `upper` or `sentence`.
- `font_match`: the closest **Google Font** (free to ship). Name a real one, such as
  Montserrat, Poppins, Inter, Roboto, Anton, Bebas Neue or TikTok Sans. Never a paid font.
- `weight`: 400 to 900.
- `color`, `highlight_color`: hex. `highlight_color` is the colour of the word being
  spoken, or null if no word is highlighted.
- `stroke`: an outline or heavy shadow around the letters. `box`: a filled box behind them.
- `animation`: `pop` (each caption scales in), `word_highlight` (the spoken word
  changes colour), `slide` or `none`. Compare consecutive tiles to tell them apart.

Judge only what the sheets show. If two videos disagree, take what most of them do
and say so in the teardown.

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
from the visual pass. It plans cards against the user's words; it does not render.

## Hard rules

- **Real numbers or nothing.** Every claim about what works cites the view count next
  to it. Never say a video "went viral" without the number.
- **Verbatim transcripts only.** Never summarise a video that was not transcribed.
- **Structure is copied, voice is not.** Every teardown states what to reject.
- **Median control group.** At least two mid-performers transcribed, or the analysis
  cannot separate the format from the creator's habits.
- **Never invent a transcript line**, or a stat or quote for a card. If transcription
  failed, retry with `--ids`, then say it failed.
- **Never ask for the ElevenLabs key in the chat.**
- **Measured numbers only in style.json.** `pace` and `zoom` come from `visual.py`;
  `captions` comes from what the sheets show.
