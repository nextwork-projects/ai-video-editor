# Contracts between the skills

Three skills hand files to each other. These shapes are the only coupling. Change one here first.

```
creator-teardown  ->  creator-teardowns/<handle>/style.json
cut               ->  edits/<name>/cut.mp4 + edits/<name>/words.json
style-edit        <-  style.json + cut.mp4 + words.json (+ optional images)
                  ->  edits/<name>/visuals.json -> images/capture-*.png + images.json
                  ->  edits/<name>/plan.json -> stills/ -> render.mp4
```

All paths are relative to the folder Claude Code was started in (the user's project folder).

## Tool home

Everything the skills install lives in one folder per user, outside the plugin (plugin updates wipe the plugin folder):

```
~/.ai-video-editor/
  venv/            Python venv: faster-whisper, numpy, pillow
  remotion/        copy of plugins/ai-editor/remotion + node_modules
  models/          faster-whisper model cache (HF_HOME)
```

The ElevenLabs key stays where creator-teardown already keeps it: `~/.config/creator-teardown/.env`
(`ELEVENLABS_API_KEY=...`), written by `fetch.py setkey`. Both plugins read it there.

Python scripts run with `~/.ai-video-editor/venv/bin/python` (`Scripts\python.exe` on Windows).
Stdlib-only scripts may run with any `python3`.

## Transcription

One engine choice, same output for both plugins: a list of words.

```json
[{"text": "so", "start": 0.12, "end": 0.31, "type": "word"},
 {"text": "um", "start": 0.40, "end": 0.62, "type": "word"},
 {"text": " ", "start": 0.62, "end": 1.40, "type": "spacing"}]
```

- Default engine: **faster-whisper** (free, local), `word_timestamps=True`, `initial_prompt` seeded with
  fillers ("Umm, uh, so, like, you know, I mean...") so it keeps more of them.
- If an ElevenLabs key exists: **Scribe v2** (verbatim). `--engine whisper|scribe` overrides.
- Seconds are floats in the source media's timeline.

## style.json (creator-teardown -> style-edit)

Existing keys (card events, from `editplan.py style`) stay. The visual pass adds `cuts`, `zoom`, `captions`, `pace`:

```json
{
  "handle": "creator",
  "videos": 5,
  "aspect": "9:16",
  "pace": {
    "wpm": 182,
    "max_pause_s": 0.25,
    "cuts_per_10s": 3.1,
    "median_shot_s": 2.4
  },
  "zoom": {
    "per_min": 9.5,
    "kind": "punch",
    "scale": 1.18,
    "duration_s": 0.0,
    "on": "sentence_start"
  },
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
  },
  "events": {"...": "existing card categories from editplan.py"}
}
```

- `pace`, `cuts`, `zoom` numbers come from scripts (repeatable). `zoom.kind`: `punch` (instant scale step on a
  cut) or `push` (smooth scale over `duration_s`). `zoom.on`: `sentence_start` | `emphasis` | `every_cut`.
- `captions` is filled by Claude from the frame sheets. `font_match` must be a Google Font (free to ship).
  `case`: `lower` | `upper` | `sentence`. `animation`: `pop` | `none` | `slide` | `word_highlight`.
- `max_pause_s`: the longest silence the creator leaves between phrases. The cut uses it as its pause target.

## Cut output (cut -> style-edit)

```
edits/<name>/
  words.raw.json    transcript of the source (Transcription shape)
  decisions.json    kept spans in source seconds: [{"start": 1.2, "end": 5.8}, ...]
  cut-check.html    the transcript with removed words struck through (the user approves this)
  cut.mp4           the rendered cut, source resolution, H.264 + AAC
  words.json        words re-timed onto cut.mp4's timeline (same shape as Transcription)
```

## visuals.json (Claude -> capture.mjs + plan.py)

Written by Claude from words.json. One beat per visual, anchored to a word as words.json spells it.

```json
[{"word": "notion", "nth": 1, "kind": "capture", "url": "https://www.notion.com",
  "clip": [0, 80, 900, 420], "width": 1000, "note": "why this beat"},
 {"word": "faster", "nth": 1, "kind": "anim", "type": "counter",
  "props": {"from": 0, "to": 10, "suffix": "x", "label": "faster"}, "hold_s": 2.5}]
```

- `capture`: `url`, optional `clip` `[x, y, w, h]` in page px or `selector` (CSS), `width` / `height`
  (viewport px, default 1000 x 700), `wait_ms` (default 2500). `capture.mjs` writes
  `images/capture-<i>-<word>.png` and replaces its earlier entries in `images.json`.
- `anim`: `type` one of `counter` (`to`, `from`, `prefix`, `suffix`, `label`, `decimals`), `steps`
  (`items`), `versus` (`a`, `b`, `a_label`, `b_label`), `logo` (`src`, `label`), `keyword` (`text`, `sub`).
  plan.py reads these straight from visuals.json.
- Both: `nth`, `box`, `hold_s`, `entrance`, as in images.json.

## plan.json (style-edit -> Remotion)

```json
{
  "video": "cut.mp4",
  "width": 1080, "height": 1920, "fps": 30, "durationInFrames": 1800,
  "captions": {"style": {"...": "style.json captions block"},
               "chunks": [{"text": "this is how", "start": 0.1, "end": 0.9,
                           "words": [{"text": "this", "start": 0.1, "end": 0.3}]}]},
  "zooms": [{"start": 3.2, "end": 7.9, "scale": 1.18, "kind": "punch", "ease_s": 0}],
  "cards": [{"src": "images/a.png", "start": 12.4, "end": 15.0, "trigger_word": "notion",
             "entrance": "pop", "box": [10, 12, 80, 40]},
            {"anim": {"type": "counter", "props": {"to": 10, "suffix": "x"}}, "start": 18.0, "end": 20.5,
             "trigger_word": "faster", "entrance": "pop", "box": [12, 4, 76, 22]}]
}
```

A card has `src` (image or Lottie) or `anim` (a visuals.json anim), never both.

Times in seconds on cut.mp4's timeline. `box` is `[x, y, w, h]` in percent of the frame. Caption `size_pct` is measured on the frame's long side, so it reads the same in 9:16 and 16:9.
