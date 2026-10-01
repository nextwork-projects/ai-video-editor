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
- `sfx` (optional, default true): `false` turns off the sound cues plan.py adds.

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

Written by Claude from captions.json. One beat per visual, anchored to a word as captions.json spells it.

```json
[{"word": "notion", "nth": 1, "kind": "capture", "url": "https://www.notion.com",
  "clip": [0, 80, 900, 420], "width": 1000, "note": "why this beat"},
 {"word": "faster", "nth": 1, "kind": "anim", "type": "counter",
  "props": {"from": 0, "to": 10, "suffix": "x", "label": "faster"}, "hold_s": 2.5}]
```

- `capture`: `url`, optional `clip` `[x, y, w, h]` in page px or `selector` (CSS), `width` / `height`
  (viewport px, default 1000 x 700), `wait_ms` (default 2500), `highlight` (an exact sentence on the
  page; whitespace and case ignored). `capture.mjs` writes `images/capture-<i>-<word>.png` and replaces
  its earlier entries in `images.json`, each with `size` `[w, h]` (image px) and, for a highlight,
  `"highlight": {"rects": [[x, y, w, h], ...]}`: one box per line of the sentence, in fractions of the
  image. With a highlight the shot runs from the clip's top down past the sentence (at most 3200 page px).
- `anim`: `type` one of `counter` (`to`, `from`, `prefix`, `suffix`, `label`, `decimals`), `steps`
  (`items`), `versus` (`a`, `b`, `a_label`, `b_label`), `logo` (`src`, `label`), `keyword` (`text`, `sub`).
  plan.py reads these straight from visuals.json.
  Scenes (pictures that move, on a dark glass panel):
  `flow` (`nodes`, optional `split` of 2-3 nodes off the last one, `tag`),
  `race` (`rows` of `value`, optional `from`, `label`; `prefix`, `suffix`, `tag`),
  `pile` (`icon`, `count`, `source`, `stacks` of 1-3, `word` for when items start flying, `tag`).
  A part (node, row, stack, source, tag) takes `icon` (a Lucide name), `logo` (a brand, optional
  `domain`) or `src` (an image in `images/`), `label` (a string, or `[{"text", "word"}]` that swaps
  on each word), `word` (lands on that word; `nth` for a later time) and `off_word` (dims again).
  plan.py writes `src` from `icon` / `logo` (`images/icon-<name>.svg`, `images/logo-<brand>.svg|png`)
  and `at` / `off_at` in seconds after the card lands, from the first time the word is said once
  the card is up. `capture.mjs` fetches every `icon` and `logo` named anywhere in anim props.
- `logo`: `brand` (a Simple Icons slug, default the word), optional `domain` for the site-icon
  fallback. `capture.mjs` writes `images/logo-<brand>.svg|png`; plan.py turns it into a small logo
  card in its own lane above the captions.
- All: `nth`, `box`, `hold_s`, `entrance`, as in images.json.

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

A card has `src` (image or Lottie) or `anim` (a visuals.json anim), never both. Optional per card:
`lane` (`"logo"` for the logo tiles' lane), `size` and `highlight` (from images.json, for an image).

`layout` is present only for the split layout (`plan.py --layout split`, vertical only):

```json
"layout": {"mode": "split", "ground": "#F4F4F2", "seam": 50, "art": [6, 14, 80, 34],
           "speaker": {"scale": 1, "x": 0, "y": 29.2, "origin": [45.8, 45.9]}, "caption_full_y": 68}
```

`seam`: where the top panel ends, % of the height. `art`: the box every card fills (clear of the app's
UI and the seam). `speaker`: the cut drawn at `scale`, pulled left `x` and up `y` (% of the frame) inside
the window under the seam; `origin` is the head's centre on the video (zooms grow from it). The panel
opens while cards are up (runs of cards closer than 1.2 s share one opening) and the speaker has the
whole frame otherwise. `captions.style.y_pct` is the split position (just under the seam);
`caption_full_y` is where captions sit while the speaker has the whole frame.

`sfx` (optional): sound cues, `[{"t": 6.99, "src": ".sfx/whoosh-in.wav", "event": 7.18}]`. `t` is when the
file starts; `event` is the visual event its hit lands on (`t` = `event` minus the cue's attack). `src`
is relative to the edit folder: `edits/<name>/.sfx/`, written by `sfx.py build` with `kit.json`
(`speech_db`, `cut_mtime`, and per cue `attack_s` and `db`, its loudest 50 ms in dBFS). Each cue plays at
volume 1; its level is baked into the file. Empty when style.json has `"sfx": false` or `plan.py --no-sfx`.

Times in seconds on cut.mp4's timeline. `box` is `[x, y, w, h]` in percent of the frame. Caption `size_pct` is measured on the frame's long side, so it reads the same in 9:16 and 16:9.

## github-render (edit.py render --github -> GitHub Actions)

```
edits/<name>/
  github-render/              a git repo, pushed to the user's PRIVATE GitHub repo. No footage.
    .github/workflows/render.yml   workflow_dispatch, three jobs:
                                   plan: chunk_ranges() over plan.json -> outputs chunks
                                     [{"i": "00", "from": 0, "to": 3599}, ...] (about 120 s of
                                     video each, 1-20 chunks) and fps
                                   render (matrix, one job per chunk): npm ci, remotion browser
                                     ensure, gh release download media (cat the .part-* files when
                                     present), unzip into public/, node render.mjs chunk public
                                     plan.json out/chunk-NN.mkv FROM TO, upload-artifact "chunk-NN" (1 day)
                                   join: download chunk-*, cut each chunk's PCM audio to exactly its
                                     frames, ffmpeg concat the video (-c copy) + the audio (AAC once)
                                     -> out/render.mp4, upload-artifact "render" (7 days), delete
                                     the chunk artifacts
    src/ package.json render.mjs tsconfig.json   the renderer, copied from the plugin
    package-lock.json         from ~/.ai-video-editor/remotion when present (npm ci), else npm install
    plan.json                 the plan (any plan-XYZ.json is written here as plan.json)
    .gitignore README.md
  github-render-media.zip     .render/ zipped (cut at output size, images/, .sfx/): the release
                              asset of the "media" release in that repo. Over 1.9 GB it is written as
                              github-render-media.zip.part-00, -01, ... instead (one asset each)
  github.json                 {"repo", "started"}: the run github-fetch waits for
  render-github.mp4           written by edit.py github-fetch
```

`node render.mjs chunk <publicDir> <plan.json> <out.mkv> <from> <to>` renders frames from..to
(inclusive) as h264 with PCM audio, so pieces join without an AAC gap.

A plan named plan-XYZ.json uses `github-render-XYZ/`, `github-render-XYZ-media.zip`, `render-github-XYZ.mp4`.

## taste (the user -> every skill)

`~/.ai-video-editor/taste.md` (rules in words) and `~/.ai-video-editor/taste.json` (settings), written
by the taste skill. taste.json has the same shape as style.json plus `cut.max_pause`; `plan.py`
lays it over style.json (taste wins) and `build_timeline.py` reads `cut.max_pause`.
