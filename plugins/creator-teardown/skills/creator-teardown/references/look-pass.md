# The look pass: fields, sources, fallback

Graphics kinds, entrances, layout, cuts, camera, sound, hook, winners and the page:
`teardown-page.md`.

Three scripts write the look. Code writes every number; a model writes only words.

| Script | Writes | How |
|---|---|---|
| `visual.py measure` | `pace`, `zoom`, `sheets/<id>.jpg` | frame differencing for cuts (catches locked-off jump cuts), a scale search for zoom punches and pushes |
| `look.py measure` | `captions` (numbers), `face`, `graphics`, `motion`, `look.md` | OCR + transcript match, OpenCV k-means in the caption boxes, YuNet faces, frame diffs at the source frame rate |
| `gemini.py look` / `merge` | `look`, `captions.font_match` | Gemini Flash-Lite on the video, or the fallback sheet pass, into one fixed schema |

## style.json, new fields

Old keys keep their meaning, so style-edit reads an old or new file the same way.

```json
"captions": {
  "present": true, "words_per_caption": 1, "lines": 1, "case": "lower",
  "y_pct": 72.4, "x_pct": 49.6, "size_pct": 4.5,
  "color": "#FFFFFF", "stroke": false, "stroke_color": null,
  "box": false, "box_color": null, "highlight_color": null,
  "weight": 600, "font_match": "TikTok Sans",
  "entrance": "pop", "ease_s": 0.133, "animation": "pop",
  "source": {"numbers": "ocr", "font": "gemini-3.1-flash-lite"}
},
"face": {"present_pct": 89, "x_pct": 51.9, "y_pct": 45.0, "height_pct": 15.3, "framing": "medium"},
"graphics": {"share_pct": 75, "per_min": 5.0, "hold_s": 5.67, "ease_in_s": 0.43,
             "palette": [{"hex": "#000000", "pct": 14}]},
"motion": {"cuts_per_min": 12.6, "ease_in_s": 0.43, "hold_s": 5.67, "caption_ease_s": 0.133,
           "zoom_punch_per_min": 6.0, "personality": "smooth"},
"look": {"source": "gemini-3.1-flash-lite", "videos": 5, "font_class": "grotesk",
         "closest_google_font": "TikTok Sans", "weight_class": "semibold", "caption_case": "lower",
         "caption_animation": "pop", "graphics_style": ["real screenshots"],
         "motion_personality": "smooth", "transitions": ["jump cut"],
         "broll_types": ["screen recording"], "not_generic": ["..."]},
"blend": {"weights": {"alice": 0.5, "bob": 0.5}, "owners": {"captions": "alice", "pace": "weighted", "visuals": "bob"}}
```

- `size_pct`: the font size (em) as % of the frame's long side, the unit the renderer
  uses. Measured from the x-height (cap height for all-caps), the band most of the
  ink sits in, divided by 0.53 (0.70). It does not move with ascenders or the OCR
  engine. The OCR box height is the fallback when the colours cannot be read.
- `y_pct`, `x_pct`: the caption block's centre, % of height / width.
- `color`, `stroke_color`, `box_color`, `highlight_color`: k-means (6 colours) over
  the caption boxes of up to 60 samples a video. Fill and stroke sit inside the OCR
  box and not a line-height away; the stroke wraps the fill and contrasts with it
  (the anti-aliased edge never counts); a box colour fills the padding only; a
  highlight is a saturated text colour that comes and goes and is not a blend.
- `weight`: glyph stem (2 x area / perimeter of the fill's contours) over the em:
  0.09 = 400, 0.15 = 700, 0.20 = 900.
- `entrance`: `pop`, `slide` or `none`, from the fill mask frame by frame at the
  source rate around 8 caption changes a video. `ease_s`: frames to settle.
- `animation`: `word_highlight` when the highlight moves word to word inside the
  same caption, else the entrance. Same values as before.
- `face.framing`: face height of frame >= 22% `close`, >= 12% `medium`, else `wide`.
- `graphics.share_pct`: samples showing screen text that is not a caption and not set
  dressing (text on screen more than half the video), or no face in a video that
  mostly shows one. `per_min`: runs of those samples a minute. `hold_s`: median run.
- `motion.personality`: `smooth` if graphics take 0.3 s or more to land; `punchy`
  with 5+ zoom punches and 10+ cuts a minute; `snappy` with 15+ cuts a minute;
  `calm` under 8 cuts a minute with holds of 3 s or more.

Measured on a real creator (7 videos, checked against the frames): white fill
on all 7, no stroke, one word, lower case, centre 64-81% down (median 75%), em 4.7%
of the height (3.1% in one video, where the frames show smaller text), weight 600,
punchy. The old Claude-read style.json had `stroke: true`, `weight: 700`,
`y_pct: 68`; the frames show a soft shadow, no outline.

## Fallback: no Gemini key

One Agent call, `model: "haiku"`, so the images never enter the main conversation:

> For each video id in `<ids>`, read `creator-teardowns/<handle>/sheets/<id>.jpg`
> (9 frames of one video, time top left). Fill the JSON schema printed by
> `<VPY> <skill>/scripts/gemini.py prompt`, judging only what the frames show. Write it
> to `creator-teardowns/<handle>/video/<id>.look-ai.json` with `"_source": "sheet"`.
> Reply with one line per video: id, font_class, closest_google_font.

Then `gemini.py merge <handle>`. One sheet is 720 x 1281 px, about 1,200 image tokens,
read by the small model.

## Token cost per teardown (7 videos)

| | Images the main model reads | Tokens in the main model |
|---|---|---|
| Before: 2-3 of 62 sheets a video (1200 x 1704, about 1,550 tokens each) + a full frame or two | 14-23 | 22,000-35,000 |
| After, Gemini key | 0 (look.md, 26 lines) | about 350 |
| After, no key | 0 (haiku reads 7 sheets of 720 x 1281, about 8,600 tokens there) | about 350 + the haiku reply |

Gemini side: about 5,600 input tokens a 60 s video at 1 fps and low resolution (measured:
39,565 for 7 videos), $0.0014 a video at $0.25 per 1M on the paid tier, $0 on the free tier.
