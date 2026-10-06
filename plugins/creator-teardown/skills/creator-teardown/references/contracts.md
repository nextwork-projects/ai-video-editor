# style.json contract

The file this skill hands to the ai-editor plugin's style-edit skill. Copied from
ai-editor's `skills/style-edit/references/contracts.md`; change both together (CI checks they match).

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
