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
  profile.json     the start skill's answers, asked once (profile.py; AI_EDITOR_HOME overrides the folder)
```

The ElevenLabs key stays where creator-teardown already keeps it: `~/.config/creator-teardown/.env`
(`ELEVENLABS_API_KEY=...`), written by `fetch.py setkey`. Both plugins read it there. With
`AI_EDITOR_HOME` set, both read and save keys in `$AI_EDITOR_HOME/.env` instead and never open the
shared file.

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
- `captions` numbers come from look.py (OCR and colour clustering); `font_match` comes from gemini.py and must be a Google Font (free to ship). `size_pct` is the font size in % of the frame's long side.
- Newer fields (`captions.lines/x_pct/stroke_color/box_color/entrance/ease_s/source`, `face`, `graphics`, `motion`, `look`, `blend`): see creator-teardown `references/look-pass.md`.
  `case`: `lower` | `upper` | `sentence`. `animation`: `pop` | `none` | `slide` | `word_highlight`.
- `max_pause_s`: the longest silence the creator leaves between phrases. The cut uses it as its pause target.
- `sfx` (optional, default true): `false` turns off the sound cues plan.py adds.
- Teardown fields (all measured by code; only `graphics.entrances[].kind` names and `graphics.kinds` labels can come from a model, the numbers never do). Full detail: creator-teardown `references/teardown-page.md`.
  - `pace.cut_kinds`: % of cuts per kind, `hard` | `jump` | `zoom-punch` | `whip` | `match` | `mask` | `dissolve`. `zoom.ease`: the GSAP ease fitted to the zoom (`none` for a punch).
  - `camera`: `{"pan_per_min", "push_per_min", "shake_pct"}`.
  - `graphics.kinds`: % of graphic screen time per kind (`real screenshot`, `UI recording`, `logo`, `text card`, `photo`, `meme`, `chart`, `b-roll`); `graphics.kinds_source`: `model` or `code`.
  - `graphics.layout`: `{"zones_pct": {"top", "middle", "bottom", "full"}, "median_box": [x, y, w, h] (% of frame), "area_pct", "covers_face_pct", "grid": 16 x 9 (portrait) seconds-of-cover 0-100, "heatmap": "graphics/heatmap.png"}`.
  - `graphics.entrances[]` / `graphics.exits[]`, most used first: `{"kind": "cut" | "slide" | "scale" | "fade" | "mask", "ease": GSAP name ("power1.out" ... "power4.out", "expo.out", "sine.inOut", "power2.inOut", "power3.inOut", "back.out(s)", "none"; exits use the ".in" names), "duration_s", "overshoot" (0.06 = 6% past the rest), "fade": bool, "from"/"to": "left" | "right" | "top" | "bottom" (slides), "distance_pct", "scale_from"/"scale_to" (scales), "share_pct", "n"}`. The motion engine can play `ease` over `duration_s` as is.
  - `graphics.secondary_motion`: % of graphics that are `still`, `drift`, `push` or `video` while up. `graphics.blur_behind_pct`: % shown over blurred footage. `graphics.crop_palette`: colours of the graphics themselves.
  - `sound`: `{"sfx_per_min", "kinds": {"whoosh" | "pop" | "click" | "riser" | "impact" | "ding" | "other": %}, "on_cut_pct", "on_graphic_pct", "in_voice_pct", "music": {"present_pct", "level_db" (under the voice)}}`.
  - `hook`: medians for `winner` and `control` of `first_cut_s`, `first_graphic_s`, `first_text_s`, `first_caption_s`, `first_word_s`, `face_pct`; `title_on_screen_pct`.
  - `winners`: `{"n_winners", "n_control", "differs": [sentences with both medians and n]}`. `ai_tells`: `{"ran", "found": [ai_tells.py findings], "bans", "warns"}`.
  - `blend.take`: the parts the user chose to copy (`captions`, `pace`, `graphics`, `entrances`, `layout`, `sound`); a part left out is absent and style-edit uses its own default.

## Cut output (cut -> style-edit)

```
edits/<name>/
  words.raw.json    transcript of the source (Transcription shape)
  decisions.json    kept spans in source seconds: [{"start": 1.2, "end": 5.8}, ...]
  cut-check.html    the transcript with removed words struck through (the user approves this)
  cut.mp4           the rendered cut, source resolution, H.264 + AAC
  words.json        words re-timed onto cut.mp4's timeline (same shape as Transcription)
  cut.transcript.json  verify_cut.py's transcript of cut.mp4 (same shape)
  fixes.json        {"cloud": "Claude"}: every retakes.py fix, applied again by retakes.py captions
  captions.json     retakes.py captions: cut.transcript.json's words and times, the cut's spelling (style-edit step 2)
  captions.txt      the same as text, to proofread
  contrast.json     {"pages": {"12.22": "stroke"}, "read": [...]}: caption pages a render check read too low (plan.py)
```

## profile.json (start -> every skill)

`~/.ai-video-editor/profile.json`, written by `python3 plugins/ai-editor/lib/ai_editor/profile.py set <key> <json>`.
Only answered keys are stored; `profile.py missing` lists the rest and `load()` fills the defaults.

```json
{"platform": "tiktok", "aspect": "9:16",
 "creators": [{"handle": "somecreator", "take": ["captions", "pace", "visuals"]}],
 "audience": "developers who use Claude", "goal": "follow + comment for the guide",
 "brand": {"colors": ["#F2EEE6", "#E5482C"], "font": "Archivo", "logo": "/path/logo.svg"},
 "assets_dir": "/path/to/my/screenshots",
 "names": [{"name": "Claude", "domain": "claude.com"}],
 "avoid": {"emoji": true, "stock": true, "icons": true, "colors": ["#7B61FF"], "notes": ""},
 "captions": {"on": true, "style": "creator"},
 "sound": {"sfx": true, "music": false}}
```

- `platform`: `tiktok` | `reels` | `shorts` | `youtube`; `aspect` follows it (`9:16`, or `16:9` for youtube).
- `brand`: `{"use_creator": true}` or colours, font and logo. `captions.style`: `creator` | `bold` | `karaoke` | `minimal`.
- `goal` and `names` belong to one video and are re-confirmed on later videos.
- Look order in plan.py: the profile's brand kit, then the creators' measured style.json, then the `editorial` preset.

## style.json (blended) (start -> style-edit)

`python3 profile.py style edits/<name>` writes `edits/<name>/style.json` with the shape above, taken
part by part from the profile's creators. `blend` records which creator each part came from.

```json
{"handle": "creatorA+creatorB", "blend": {"captions": "creatorA", "pace": "creatorB", "visuals": "creatorA"},
 "aspect": "9:16", "captions": {}, "pace": {}, "zoom": {}, "cuts": {}, "motion": {}, "look": {}}
```

- `captions` <- `captions`; `pace` <- `pace`, `zoom`, `cuts`, `motion`; `visuals` <- `graphics`, `look`, `layout`, `cats`, `events`.
- A creator-teardown blend (`editplan.py blend --take`) records `blend.take` (`captions`, `pace`, `graphics`,
  `entrances`, `layout`, `sound`); plan.py and route.py read a measured field only when its part is in it
  (no `take`: every part present counts). visuals.md "From the teardown" lists each field and what it drives.
- A part no creator claims comes from the first creator. The profile's `captions` answer then overrides
  the caption style (`on: false` sets `captions.present` false), and `sound.sfx: false` sets `sfx: false`.

## beats.json (route.py -> template-filler -> visuals.json)

`python3 route.py beats edits/<name>` splits captions.json into sentences (times kept in code) and writes
`edits/<name>/beats.json`. Claude (or the template-filler agent) turns the picks into visuals.json entries.

```json
[{"i": 1, "text": "It is 40 times faster than Claude.", "start": 2.4, "end": 4.1,
  "names": ["Claude"], "pick": "capture:sticker", "p": 0.7}]
```

- `i`: sentence index. `start`, `end`: seconds on cut.mp4. `names`: the profile's `names` said in the sentence.
- `pick`: `none` | `capture:shot|browser|sticker` | `post` | `logo` | `logo_cluster` | `chat` | `terminal` | `toasts` | `side_by_side` | `video_card`,
  or `null` with no TypeSafe key (Claude routes). `p`: the pick's probability, or `null`.

## visuals.json (Claude -> capture.mjs + plan.py)

Written by Claude from captions.json. One beat per visual, anchored to a word as captions.json spells it.

```json
[{"word": "notion", "nth": 1, "kind": "capture", "url": "https://www.notion.com",
  "clip": [0, 80, 900, 420], "width": 1000, "note": "why this beat"},
 {"word": "faster", "nth": 1, "kind": "capture", "url": "https://example.com/benchmarks", "format": "sticker",
  "marks": [{"kind": "highlight", "find": "10x faster", "at_word": "faster"}], "hold_s": 2.5}]
```

- `capture`: `url`, optional `clip` `[x, y, w, h]` in page px or `selector` (CSS), `width` / `height`
  (viewport px, default 1000 x 700), `wait_ms` (default 2500), `highlight` (an exact sentence on the
  page; whitespace and case ignored). `capture.mjs` writes `images/capture-<i>-<word>.png` and replaces
  its earlier entries in `images.json`, each with `size` `[w, h]` (image px) and, for a highlight,
  `"highlight": {"rects": [[x, y, w, h], ...]}`: one box per line of the sentence, in fractions of the
  image. With a highlight the shot runs from the clip's top down past the sentence (at most 3200 page px).
- `anim`: `type` an overlay format (visuals.md), `logo` (`src`, `label`), or a template in motion.md.
  Type cards (`counter`, `steps`, `versus`, `keyword`, `slam`, `title`, charts) were removed; plan.py
  skips them with a warning. plan.py reads these straight from visuals.json.
  The diagram, `flow` (Diagrams.tsx; an overlay box by default, a full-frame scene with `"layout": "scene"`):
  `nodes` (1-6 Parts, a chain; 4+ wrap to two rows), optional `split` (2-4 branch Parts off the last
  node), `tasks` (`[{"text", "word", "heavy"?}]`: chips that pop left of the source on their word),
  `accent` (`#hex`: ring, hot wire and chosen name; the destination's brand colour), `tag` (`{"text", "word"}`).
  A Part may stack names with `lines: [{"text", "word"}]`, each lighting on its word. motion.md "The diagram".
  A part (node, branch, line, tag) takes `icon` (a Lucide name), `logo` (a brand, optional
  `domain`) or `src` (an image in `images/`), `label` (a string, or `[{"text", "word"}]` that swaps
  on each word), `word` (lands on that word; `nth` for a later time) and `off_word` (dims again).
  plan.py writes `src` from `icon` / `logo` (`images/icon-<name>.svg`, `images/logo-<brand>.svg|png`)
  and `at` / `off_at` in seconds after the card lands, from the first time the word is said once
  the card is up. `capture.mjs` fetches every `icon` and `logo` named anywhere in anim props.
- `logo`: `brand` (a Simple Icons slug, default the word), optional `domain` for the site-icon
  fallback. `capture.mjs` writes `images/logo-<brand>.svg|png`; plan.py turns it into a small logo
  card in its own lane above the captions.
- `post`, `app`, `youtube`, `github`: free sources, no keys, fetched by `capture.mjs` (not `anim` beats).
  - `post`: `url` (an X status link), optional `text` / `highlight` (must appear in the post). Writes
    `images/post-<id>.json` and `images/avatar-<id>.jpg`; a `social_post` card reads them.
    `images/post-<id>.json`: `{"platform": "x", "name", "handle", "text", "likes", "replies", "time", "url", "avatar", "highlight"}`.
  - `app`: `url` or `app_id` (App Store), optional `brand`, `screenshot` (index, default 0). Writes the icon as
    `images/logo-<brand>.png`, `images/app-<id>.json` and the first screenshot as a card image.
    `images/app-<id>.json`: `{"name", "seller", "rating", "ratings", "price", "url"}`.
  - `youtube`: `url` or `id`; the video's thumbnail as a card image.
  - `github`: `url` or `repo` (`owner/name`); the repo's social card as a card image.
- Optional on any beat, copied onto its card: `layout`, `transition_in`, `transition_out`, `focus`, `marks`
  (see plan.json below).
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
            {"anim": {"type": "chat", "props": {"app": "Jev", "messages": [{"from": "user", "text": "small task"}]}}, "start": 18.0, "end": 20.5,
             "trigger_word": "faster", "entrance": "pop", "box": [12, 4, 76, 22]}]
}
```

A caption chunk may carry `treat` (`"shadow"` | `"stroke"` | `"backing"`) and `treat_color`: plan.py measured the
cut behind that page (at the caption box, through the zooms) and the creator's look would read under 3:1 there,
so it adds the first step that reaches 3:1. Each step keeps the one before. The colour is the darkest of the
creator's palette that stands 4.5:1 off the fill, else near-black (near-white for dark text). A style with its
own stroke or box gets none.

A card has `src` (image or Lottie) or `anim` (a visuals.json anim), never both. Optional per card:
`lane` (`"logo"` for the logo tiles' lane), `size` and `highlight` (from images.json, for an image), and:

- `layout`: `"scene"` (full frame) | `"split"` (the split layout's top panel) | `"box"` (the card's `box` over the footage).
  plan.py sets it on every card; a visuals.json beat's own `layout` wins, except that an explaining card on vertical is never a box.
- `transition_in`, `transition_out`: `match` | `iris` | `push` | `block` (scene only; defaults `match` in, `iris` out,
  or cycled from style.json `transitions`). Each takes about 0.62 s x the personality's k.
- `focus`: `[x, y]` % of the frame a scene opens from and closes to (default the head centre from face.json).
- `marks`: `[{"kind": "box|ring|underline|bracket|pill|dim|highlight", "rect": [x, y, w, h], "at": 0.8}]` on a
  capture card. `rect` is in the capture's own pixels, `at` is seconds after the card lands (from `at_word`,
  `at_s`, else 0.8), plus `label` and `side` for `bracket` and `pill`. See references/motion.md "Capture marks".
  A mark found by text also carries `rects`, one box per line in capture px; a `highlight` draws one band
  per line from them. A sticker capture's images.json entry carries `xh`: the font's x-height in PNG px.
- `layer`: `"behind"`: drawn over the footage and under the speaker's cutout (references/motion.md "Behind
  the speaker"), with `key` `[x, y, w, h]` %: the region plan.py kept clear of the head. The plan then
  carries `"cutouts": [{"src": "cutout/behind-1080x1920-1-130", "from": 1, "to": 130}]` (matte.py: a folder of
  RGBA PNGs, 000000.png is frame `from`; frames of the cut, inclusive), and check.py plan FAILs a behind card no cutout covers.
- A scene starts SCENE_LEAD_S x k earlier than its word (k: punchy 0.7, snappy 0.8, smooth 1.0, calm 1.35);
  quality.py counts it landed when its transition is half done.
- In the props the renderer reads (`anim.props`, or an image card's own `props`), plan.py writes for every box card:
  `word_at`: seconds from the card's start to its own word (motion.ts `landAt` lands the entrance there).
  From the creator's style.json, only when the blend took the part (visuals.md "From the teardown"):
  `enter` / `exit`: one measured entrance / exit, `{"kind": "cut|slide|scale|fade|mask", "ease": "<GSAP name>",
  "dur": s, "dir"?: "left|right|top|bottom", "dist"?: % of the frame's short side, "fade"?: true, "scale"?: n}`
  (motion.ts `Fit`); `ambient`: `"still" | "push" | "drift" | "video"`. The card's `entrance` then names the
  kind (`cut` is allowed: a hard cut, no "appears whole" warning in quality.py).

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

`pans` (optional, from the creator's `camera.pan_per_min`): `[{"start", "end", "from", "to"}]`, the footage
drifting sideways from `from` to `to` % of the width on `sine.inOut` (scaled up just enough to hide its edge).
A zoom may carry `ease` (the creator's fitted `zoom.ease`, pushes only) and `origin` `[x, y]` % of the frame
(the top centre of the head over the zoom, from face.json; the point it grows from). How zooms move: motion.md "Zooms". `targets` (optional, from the creator's
`hook`): `{"first_graphic_s", "control_first_graphic_s"}`; check.py plan WARNs when the first card lands over
0.5 s after `first_graphic_s`.

`music` (optional): `{"src": ".sfx/music.wav"}`, the bed `sfx.py music` wrote (levelled and ducked under the
speech, played at volume 1). plan.py adds it when the file exists and the profile does not say `sound.music: false`.

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
