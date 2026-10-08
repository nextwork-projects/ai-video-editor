# Motion: templates, look, personalities, marks

The renderer (`remotion/src`) draws every built card from a template. Claude never writes code for a
card: it fills a template's JSON props (about 200 tokens) in visuals.json. Every template is one GSAP
timeline that the Remotion frame seeks (`@remotion/gsap` `useGsapTimeline`), so previews, stills and
renders show the same frame.

Files: `motion.ts` (eases, personalities, the bridge), `look.tsx` (look presets, fonts, texture),
`Templates.tsx` (the templates), `Captions.tsx` (captions and `caption_page`), `Capture.tsx` (capture
cards and marks), `Anims.tsx` (the card host and the old type names), `StyleEdit.tsx` (the edit).

## Rules every template follows

- Text is shown exactly as given. Every number, value and label comes from props. A template never
  invents a figure, a tick label or a date.
- Lines DRAW along their length (DrawSVG). Boxes, pills and dims FADE AND SCALE. A highlight sweeps.
- Every entrance has anticipation: the `antic` ease winds back ~8% before the move, overshoots ~4%
  and settles (`antic.soft` for smooth and calm). Labels, rules, underlines and dots lag the primary
  element by a stagger (follow-through).
- Nothing moves linearly. Things land with an overshoot (`back.out`, springs) or a settle (`settle`,
  `expo.out`). Secondary pieces (rule, label, sub line) follow the primary one by 0.05-0.2 s.
- The camera is never still: every card pushes in slowly and drifts; layers marked `data-depth` move
  against it for parallax.
- Type fits by measurement (`@remotion/layout-utils`), never by a characters-times-em guess.
- `*word*` inside a text prop sets that word in the look's serif italic in the accent colour.

## Overlay formats (the default)

The speaker stays on screen; pictures float over the frame around the head, never over it
(`Overlays.tsx`). Each format draws its own neutral chrome: a white card or the real app's surface,
a soft three-layer shadow, depth. Text on any card is a label of a few words.

Every format runs one GSAP timeline labelled with the beat's words (`motion.ts` `wordTl`, from the
GSAP skills): defaults in the constructor, a label `in` for the card's own word and one per spoken
word in its props (`haiku`, `faster`), every tween placed off a label with the position parameter,
`fromTo` for anything seeked, transform aliases and `autoAlpha`. On it, the choreography the
HyperFrames talking-head-recut set (`cardLife`):

| beat | move |
|---|---|
| entrance | drops in 0.1 s + 0.07 s x k before its word (motion.ts CARD_LEAD_S, OVERLAY_LEAD_S), so it carries half its ink 0.1 s before the word: falls ~70 px (1080 frame), tipped back 16 degrees, blurred 10 px, scale 0.94 to 1 on `expo.out` over 0.62 s x k |
| hit | on each hit word (a mark landing, an app reply, a command's output): a punch to 1.025 in 0.1 s, then `elastic.out(1, 0.5)` back |
| under it | the camera's slow push (1 + `push`) and drift for the card's whole life |
| exit | upward ~50 px, scale 0.97, blurring, on the personality's `.in` ease over 0.7 x `out` (faster than the entrance) |

The card's word sits at `props.word_at`: plan.py passes it on every box card (seconds from the card's
start to its word, so a logo tile or a card cut short by the one before still lands on its word). Without
it, 0.1 + 0.3 x k s after the card lands (plan.py's `CARD_LEAD_S` + `OVERLAY_LEAD_S`).

### The creator's measured motion

When the copied creator's teardown measured her graphics (style.json `graphics.entrances[]`, `exits[]`,
`secondary_motion`) and the blend took `entrances`, plan.py deals one of her entrances and exits to each
box card in her shares, and her moves replace the drop-in and the lift above (visuals.md "From the teardown"):

| prop | shape | played by |
|---|---|---|
| `enter` | `{"kind": "cut\|slide\|scale\|fade\|mask", "ease": "back.out(3.5)", "dur": 0.325, "dir": "top", "dist": 6.2, "fade"?: true, "scale"?: 0.8}` | `fitIn`: hidden until it starts, ends on the word (`L("in")`); `cut` (or `dur` 0) shows it on the word |
| `exit` | the same, `dir` the side it leaves to | `fitOut`: ends as the card's time runs out; a `cut` hides it on its last frame |
| `ambient` | `still` / `push` / `drift` / `video` | `camera`: still = no move, push = scale only, drift = move only, video = both (the default) |

`dist` is % of the frame's short side (plan.py converts her `distance_pct`, which is % of the frame along
the move). The ease is her fitted GSAP name, played as is, so her overshoot lives in it (`back.out(3.5)`).
`cardLife` (shot, browser, sticker, chat, terminal, video_card), `toasts` and `side_by_side` take `enter` and
`exit`; the `flow` diagram builds itself part by part and takes `exit` only. plan.py deals none to
`logo_cluster` (a measured slide carried its logos across the face); the renderer would play one if given;
every template takes `ambient`. ai_tells.py still WARNs `bounce-ease` on a measured `back.out`: it is hers,
so leave it.

| type | shows | props |
|---|---|---|
| `shot` (an image card's default `format`) | a real capture drops in, the camera pushes into the first mark's region as it lands, the card punches on the marked word; `label` / `logo_src` put the source row (the site's real logo and name, 36 px) on a white card above it | `src`, `size`, `marks`, `highlight`, `label?`, `logo_src?`, `zoom?` (1.45, clamped so the mark stays whole) |
| `browser` | the page in a browser window with its URL, scrolling to the mark; a cursor travels there and clicks with a ripple as the mark lands, then rests and drifts along the line | `src`, `size`, `url`, `marks`, `cursor?` (true) |
| `sticker` | the one sentence that is the evidence (capture.mjs cuts it and sets it on white at a phone-readable size; most of its padding is trimmed) on a white card under the source row, dropped in, the highlighter sweeping line by line on the word as the card punches | `src`, `size`, `crop?` `[x, y, w, h]` image px (a hand crop of a full capture), `rotate?` (0), `marks` (image px, `rects` one per line), `label?`, `logo_src?` |
| `chat` | an app's thread from its real parts: the user bubble pops, the app shows typing dots then types its reply; the window punches on each reply | `app`, `logo`, `model?`, `messages: [{from: user\|app, text, at?}]` |
| `terminal` | a real terminal window: commands type at 30 chars/s with a caret, output lands | `title?`, `lines: [{text, kind: cmd\|out, at?}]` |
| `toasts` | real notifications drop in from above, blurred, each just before its word, and stack, pushing the older ones down | `items: [{app, src, title, body?, at?}]` |
| `logo_cluster` | real logos drop in blurred round the head just before their word, land on `back.out(1.7)`, punch on the word, bob, leave upward; bare with a soft shadow and a faint light halo (dark logos read on dark footage) | `logos: [{src, at?}]`, `head` `[x, y, w, h]` % (plan.py fills it), `band?` `[x0, x1]` % and `size?` % (vertical), `seed?` |
| `side_by_side` | two real screenshots drop in 0.14 s apart, each tilted 1.2 degrees toward the other, the pair centred; each punches on its own marks | `a: {src, size, label?, marks?}`, `b: {...}` |
| `video_card` | a short real clip in a rounded card, dropping in | `src` (video in `images/`), `size?`, `start_s?`, `rate?`, `label?` |
| `social_post` | the real post, the quoted phrase in the highlighter | as below |

Shared primitives (`motion.ts`): `wordTl`, `dropIn`, `punch`, `exitUp`, `fitIn`, `fitOut`, `cardLife`; in `Overlays.tsx`
the source row, the cursor (arrow + click ripple, `cursorTo`), zoom into a region (Capture's `zoom`).

Image cards take `"format": "shot" | "browser" | "sticker" | "plain"` and `"props"` (the format's
extra props) in plan.json; plan.py copies both from the capture beat.

## Layout

Overlay first. plan.py (`place_overlays`) gives each overlay card the free region around the head
(face.json) its picture fills best: above the head (top 10% down to just over the hair) for wide
pictures, beside it for tall ones; left or right of the head on 16:9. A card leads its word by
`OVERLAY_LEAD_S` (0.3 s) x the personality's duration multiplier, so the entrance has landed on the
word. `logo_cluster` takes `[0, 0, 100, 100]` and the head box, plus on vertical `band` [17, 83] and
`size` 20 (% of the width). A beat's own `box` wins. On vertical a `flow` is a scene and an `icon_burst`
sits in the split panel whatever the beat says: in a box they render small and off centre.

### Behind the speaker

With the profile's `behind` on, `shot`, `sticker`, `social_post` and `logo_cluster` cards get
`"layer": "behind"` (plan.py `tuck_behind`). Draw order in the overlay layout: footage, behind
cards, the speaker's cutout, every other card, scenes, captions.

- A behind card above the head grows down behind the hair, at most `BEHIND_TUCK` (0.4) of the head's
  height, as far as its **key region** stays clear of the head box (+2%). Key region: the marks'
  union, grown by a shot's push-in zoom; with no marks, the picture less its bottom fifth. plan.py
  writes it as `"key"` `[x, y, w, h]` %; matte.py measures it against the real cutout.
- The cutout (`plan.cutouts`: `[{src, from, to}]`, frames of the cut) is drawn only from 0.5 s
  before a behind card to 0.5 s after it, on the footage's own zoom and move, so it stays
  registered. Everywhere else the raw camera shows: no matte edge can show where no card is.
- RGBA PNGs drawn with `<Img>`, not a video: ProRes 4444 came back about 3 levels darker in the
  shadows than the footage through Remotion (the speaker visibly changed as the cutout switched on), a
  .mov of PNGs lost its alpha, VP9 alpha seeks poorly. The PNGs match the footage exactly.
- matte.py per frame: RVM mobilenetv3 at `downsample_ratio` 0.25 (0.4 let the wall through at the
  hairline), alpha median over t-2..t+2 on still edge pixels (no flicker, no lag), then the wall
  unmixed out of soft edge pixels where the wall is flat and the solid hair colour filled in where
  it is textured (slats, plants), alpha firmed on dark hair and kept soft on skin.
- The face must be solid in the matte (matte.py checks the middle of the head box is over 97%
  alpha), or the card would show through it.

Full-frame **scenes** only when a beat asks (`"layout": "scene"`) for a picture template (`flow`,
`icon_burst`, `social_post`). There are no type scenes. The rest of this section describes them.

A scene card in plan.json:

```json
{"anim": {"type": "flow", "props": {"nodes": [{"logo": "github"}, {"logo": "vercel"}]}}, "layout": "scene",
 "start": 12.4, "end": 15.9, "transition_in": "match", "transition_out": "iris", "focus": [50, 31],
 "box": [0, 0, 100, 100], "entrance": "pop", "trigger_word": "2026"}
```

- `layout`: `"scene"` (full frame) or `"box"` (default: the card's `box` over the footage, as before).
- `box` on a scene: `[0, 0, 100, 100]` means "use the scene box": `[6, 13, 88, 52]` vertical (clear of the
  app's top bar, captions under it), `[6, 9, 88, 70]` wide. check.py skips its safe-zone, centre and
  head checks for this shape. Any other box is used as given.
- `focus`: `[x, y]` % of the frame where `match` and `iris` open from and close to. plan.py passes the
  head centre from face.json at the card's start, so the cut grows out of the speaker's face.
- Timing: plan.py starts a scene `CARD_LEAD_S` (0.1 s) plus `SCENE_LEAD_S` (0.3 s) x the
  personality's duration multiplier before its word, so the match or iris is half done on the word. A
  hard-cut scene (`transition_in` `cut`) is whole on its first frame: it starts `CARD_LEAD_S` before its word.
- Captions over a scene draw in the scene's own ink and accent, with no stroke or shadow (white on
  paper would vanish). When every word being said is already in the scene's type, the captions hide:
  the scene is the caption.
- `ground`: `ground`, `ink` or `accent`: which of the look's colours the scene sits on (ink and accent
  swap the text colours to stay readable). Unset, scenes take ground, ink, accent in turn, so two
  scenes in a row never look identical.
- A capture card (`src`, `size`, `marks`, `highlight`) can be a scene too: the page fills the scene box.
- After its entrance a scene keeps moving: a slow push (4.5%) and pan over its whole life, on top of
  the template's own camera. Nothing decorative is added: `look.decor` defaults to `none`.
- In the split layout a scene covers the panel and the speaker window alike; the panel does not open for it.

## Transitions

`transition_in` / `transition_out` on a scene card (default in: `match`; out: `iris`, or the same as in
for `push`, `block` and `cut`). Each takes about 0.62 s x the personality's duration multiplier. plan.py cycles
style.json `transitions`; an empty list (the creator only cuts) gives `cut` in and out.

| name | what happens | ease |
|---|---|---|
| `match` | a dot of the scene's ground grows from `focus` until it is the whole frame (a scale match cut); the content settles from 1.12 x as it grows. Two scenes back to back: the second grows over the first. | expo.inOut |
| `iris` | a circle opens from `focus` (out: closes back onto the face) | power3.inOut |
| `push` | the scene pushes the footage off the frame sideways, motion-blurred along x only (out: pushes it back) | power4.inOut |
| `block` | an accent block then an ink block sweep across; the scene switches under the second (transitions-cover) | power3.inOut |
| `wipe` | a hard edge crosses from the right | power3.inOut |
| `fade` | a dissolve | sine.inOut |
| `cut` | none: the scene is whole on its first frame and gone after its last | |

Box cards that swap in the same lane keep the cover wipe.

Inside every scene the template's camera pushes and drifts, layers marked `data-depth` move against it,
and only with `look.decor: "blocks"` (off by default) two flat colour blocks (an accent bar, a large disc) sit on their own
layer drifting the other way: parallax depth in flat 2D.

## Template catalogue

`type` goes in a visuals.json `anim` beat exactly as today (`"kind": "anim", "type": ..., "props": ...`).
Any `at` below is seconds after the card lands; plan.py fills it from a `word` (see "What plan.py must
pass"). `src` is a file in `images/`.

| type | shows | props | example |
|---|---|---|---|
| `flow` | the diagram (`Diagrams.tsx`, below): real logos on white node cards, wires that draw, a packet that runs a wire and lands on the word | `nodes: [Part]` (1-6), `split?: [Part]` (2-4), `tasks?: [{text, word, heavy?}]`, `accent?`, `tag?: {text, at}` | `{"nodes": [{"logo": "github", "label": "push", "word": "push"}, {"logo": "vercel", "label": "live", "word": "live"}]}` |
| `logo_sting` | the real logo lands, a light sweep crosses it inside its own silhouette | `src`, `label?` | `{"src": "images/logo-notion.svg", "label": "Notion"}` |
| `social_post` | a real X post, Reddit post or YouTube comment rises in, words fade up, the quoted phrase gets a marker, likes bump. `name` and `text` are required and must be copied from the real post (the X syndication endpoint gives text and counts); the render stops with an error without them, never a placeholder | `platform` (x/reddit/youtube), `name`, `handle?`, `avatar?`, `text`, `highlight?`, `likes?`, `replies?`, `reposts?`, `time?`, `subreddit?`, `logo_src?`, `excerpt?` (true: when the whole text would set under 5% of the frame width, only the sentence holding `highlight`, with ellipses) | `{"platform": "x", "name": "...", "handle": "...", "text": "<copied verbatim>", "highlight": "<the phrase said>", "likes": "1.2K"}` |
| `arrow_callout` | a label pill pops, a hand-drawn arrow draws from it to a point | `label`, `point: [fx, fy]` (fractions of the card box), `side?` (auto/left/right) | `{"label": "this setting", "point": [0.72, 0.3]}` |
| `icon_burst` | the subject springs in and throws flat confetti on seeded Physics2D arcs | `src?` or `text?`, `count?` (18), `seed?`, `at?` | `{"src": "images/logo-python.svg", "count": 22}` |
| `caption_page` | word-timed karaoke page (built on `@remotion/captions` `createTikTokStyleCaptions`) | `words: [{text, start, end, emph?}]` (seconds after the card lands), `combine_ms?` (1200), `style?` (a captions block) | plan.py fills `words` |

Real logos (any `src` not named `icon-*`) are drawn bare at full size: no tile, no shadow, no ring.
Only icons and letters sit in a white tile.

### The diagram (`flow`)

Built from the HyperFrames router (stage 9, prompt 2). Every node is a white card with its real logo
and label: a readable surface over any footage, on a soft dark veil (no panel; no veil on a
full-frame scene). Labels are measured with `@remotion/layout-utils` and never set under 40 px on a
1080 frame: pictures and gaps shrink first. The board fills the band above the head (plan.py's box).

- **Chain** (`nodes`, 1-6): sequential steps left to right; 4 or more wrap to two rows as a snake.
  Each node with a `word` pops as the packet that runs the link into it lands on that word.
- **Branches** (`split`, 2-4): the options off the last chain node, stacked on the right, sliding in
  once the source is up. A branch with a `word` is chosen on it: the packet (a white dot riding a hot
  wire in the accent) leaves the source, which pulses, and lands on the word; the branch's ring pops,
  the card punches, its name takes the accent, the other branches dim to 45%. Before the next beat
  the board resets: hot wire and ring fade, every branch back to full.
- **Tasks** (`tasks`): a chip left of the source pops on its word (`heavy: true`: a dark chip with
  rising bars slams in, for "harder"); it is swallowed by the node it feeds just before the packet
  leaves. Each chip feeds the first landing after it.
- **Stacked names**: a Part's `lines: [{text, word}]` stacks several names on one card ("Opus" /
  "Fable"), each lighting on its own word.
- `accent`: the ring, hot wire and chosen name; use the destination's real brand colour (Claude's
  `#D97757`). Unset: the look's accent, or its highlighter when that accent is near black. A name keeps
  the ink when the accent is too light to read on white.

A Part is `{src?, label?, lines?, at?, off_at?}` (plan.py turns `icon`/`logo` into `src` and
`word`/`off_word` into `at`/`off_at`). A label can swap on words: `[{"text": "task"}, {"text": "small task", "at": 1.2}]`.

```json
{"word": "which", "kind": "anim", "type": "flow", "hold_s": 7.2, "props": {"accent": "#D97757",
 "nodes": [{"src": "images/logo-typesafe.png", "label": "Jev", "word": "which"}],
 "split": [{"src": "images/logo-claude.svg", "label": "Haiku", "word": "Haiku"},
           {"src": "images/logo-claude.svg", "lines": [{"text": "Opus", "word": "Opus"}, {"text": "Fable", "word": "Fable"}]}],
 "tasks": [{"text": "small task", "word": "small"}, {"text": "harder", "word": "harder", "heavy": true}]}}
```

### Removed: type cards

`slam`, `title`, `phrase_mark`, `counter` (and its digit wheel), `bar_chart`, `line_chart`, `versus`,
`checklist`, `lower_third`, `pile` and the old `keyword`, `steps`, `race` were removed (2026-10-06):
words on a ground read as AI-made. plan.py skips a beat that names one and says which overlay format
shows the real source instead. Of the old names, `logo` (-> `logo_sting`) and `flow` still work.

## Motion design rules

The vendored LottieFiles skill (`../../motion-design/`, MIT) is the reference for timing and review;
`reference/quality-checklist.md` there is the checklist for judging stills and clips. How its rules
show up here:

| rule (motion-design) | in our templates |
|---|---|
| three layers: primary, secondary (30-50%, offset 50-100 ms), ambient (10-20%) | primary: the card's entrance and the mark landing on its word; secondary: the highlighter sweeping line by line, rings and arrows drawing, a label following the card; ambient: `camera()` push and drift, the sticker's slow lean, the browser cursor resting on its line |
| entrance decelerates, exit accelerates; exit 65-75% of the entrance | entrances on `.out` / spring eases, exits on `m.exit` (`.in`) over `m.out` (0.26-0.6 s) |
| 1/3 rule (distance): no unbroken move over a third of the container | captures travel to a mark in steps sized to the window; overlays enter over a few % of the frame, not from the edge (side_by_side's slide from the edges is the exception) |
| 1/3 rule (density): at most a third of elements moving at once | one card up at a time (plan.py), its parts staggered on their own words |
| stagger total under 500 ms | `m.stagger` 0.04-0.12 s; parts are timed to words, not to a stagger, when they are said |

Their four personalities against ours (names unchanged in the API; a mapping, not a retune):

| ours | theirs | their numbers (standard duration, ease, overshoot) |
|---|---|---|
| `punchy` | Energetic | 180 ms, ease-out-expo, 15-30% |
| `snappy` | Playful | 250 ms, ease-out-back, 10-20% |
| `smooth` (default) | Corporate | 300 ms, (0.2, 0, 0, 1), 0-3% |
| `calm` | Premium | 500 ms, (0.4, 0, 0.2, 1), 0% |

Our durations run longer than theirs (a card on video is read, not clicked), so `m.k` stays as it is.
The stage 7 bake-off (`remotion/src/lab/`) compares this and five other sources side by side.

## The look

plan.json `"look"`: a preset name plus any overrides. Filled from the user's brand kit, then the copied
creator's measured palette and fonts. Unset keys come from the preset.

```json
"look": {"preset": "editorial", "accent": "#E5482C", "font": "IBM Plex Sans", "font_display": "Newsreader",
         "font_serif": "Instrument Serif", "texture": "grain"}
```

| key | meaning |
|---|---|
| `preset` | `neutral` (default), `editorial`, `editorial-dark`, `poster-red`, `poster-green`, `poster-blue`, `mono`, `glass` |
| `mark`, `ring` | highlighter colour; ring/box/underline stroke (drawn over a dark outline) |
| `ground` | the card surface and the colour everything sits on |
| `ink`, `muted` | text and line art; secondary text |
| `accent`, `accent_ink` | the ONE accent (marks, the winning bar, the live node) and text on it |
| `line` | hairlines, tracks, dividers |
| `surface` | `card` (a flat card of `ground` under each overlay card), `none`, `glass` |
| `radius` | corner radius, % of the card's short side |
| `shadow` | `soft`, `hard` (offset flat shadow, print style), `none` |
| `font`, `font_display`, `font_serif` | Google Fonts for labels, headlines/numbers, the italic accent word (`""` = none) |
| `weight`, `weight_display`, `tracking` (em), `case` (`as_is`/`lower`/`upper`) | type settings |
| `texture`, `texture_amount` | `grain` (film grain, re-seeded every 2 frames), `paper` (fibre), `print` (grain + halftone dots), `none`; 0-1. Overlay blend, so it reads on light and dark grounds; the poster presets default to 1 (visible at phone size), editorial to 0.55 |
| `decor` | `blocks` (scenes get flat colour blocks on a parallax layer) or `none` |

Default is `neutral`: no house palette. White cards (or the real app's own surface), near-black ink
`#0D0D0D`, a soft shadow, no texture, no coloured grounds, no accent bars, IBM Plex Sans for UI labels and
Newsreader (a serif) for any heading, never a grotesk heading. Colour comes from
the real content. `mark` (the highlighter, default marker yellow `#FFE14D`) comes from the brand kit's
accent, else the copied creator's measured saturated accent; `ring` (rings, boxes, underlines) is white
over a dark outline so it reads on any capture. The `editorial`, `editorial-dark` and `mono`
presets are opt-in (a style.json look naming the preset); the flat-ground `poster-*` presets only come
from the user's own brand kit. Real logos and real images carry
the visuals; type does the work. The old dark glass panel with the mint `#7CF2B0` accent is the
`glass` preset and appears only when a style names it. No preset uses gradients, purple-blue, neon on
near-black, emoji, Inter or icon tiles on glass.

In the split layout every card draws straight on `layout.ground` (no surface) and the grain covers the
whole ground.

## Zooms

The footage's zooms (plan.json `zooms`, StyleEdit.tsx `zoomAt`) move like a camera, never a step:

- Scale moves in log space (`scale ** p`), so zooming in and back out read at the same speed.
- Each zoom grows from `origin`, the top centre of the head while it is up (plan.py, from face.json), so the face
  holds its place and the hair never rises into a card above the head; without face.json, 50% across, 30% down.
- A `punch` keeps its speed but eases: 0.16 s on `power2.out` in, and the same back out at its end.
- A `push` is a camera move: at least 0.8 s each way, on the creator's fitted `zoom.ease` when the blend
  took `pace`, else `sine.inOut`. Never linear.
- Transforms are not rounded (sub-pixel).

check.py render (quality.py `zoom_moves`) measures every zoom on the render, frame to frame in the face band
(ORB + a similarity fit), and WARNs a snap (one frame carries over 60% of the change) or jerk (the speed
reverses or surges a second time mid-move).

## Personalities

plan.json `"motion"`: `"snappy" | "smooth" | "punchy" | "calm"` or `{"personality": "..."}`. Unset, the
renderer uses `smooth`. plan.py should pick from the copied creator's pace so motion follows them:

| personality | when (style.json `pace.median_shot_s`) | duration x | enter / text | pop | stagger |
|---|---|---|---|---|---|
| `punchy` | under 1.4 s | 0.7 | power4.out / expo.out | spring.bouncy, impact shake | 0.04 s |
| `snappy` | 1.4-2.4 s | 0.8 | expo.out / power4.out | back.out(1.7) | 0.055 s |
| `smooth` | 2.4-4 s | 1.0 | power3.out / settle | spring.snappy | 0.08 s |
| `calm` | 4 s and over | 1.35 | power2.out / settle | spring.soft | 0.12 s |

Named eases (registered once in motion.ts): `ink` (CustomEase, a pen stroke: fast off the mark, long
soft landing), `settle` (glides in and keeps the last 7% of travel for the closing frames), `impact`
(CustomWiggle, a shake that dies away), `spring.snappy`, `spring.bouncy`, `spring.soft` (damped
springs normalised to end on 1), plus GSAP's `expo.out`, `power3.out`, `power4.out`, `back.out(1.7)`,
`sine.inOut`.

## Capture marks

A capture card (an image from capture.mjs) takes `marks`, each registered in the capture's own pixel
space inside the layer that scrolls and pushes, so a mark rides the page. The card travels to each mark
just before it lands (centred at 45% of the window).

```json
"marks": [{"kind": "box", "rect": [40, 60, 760, 140], "at_word": "overview"},
          {"kind": "ring", "rect": [60, 700, 300, 70], "at_s": 2.0},
          {"kind": "bracket", "rect": [40, 900, 600, 220], "label": "the rule", "side": "right", "at_word": "rule"}]
```

| kind | draws | motion |
|---|---|---|
| `box` | a rounded rectangle round the rect | fades and scales in (1.14 -> 1) |
| `ring` | an ellipse round the rect | draws along its length |
| `underline` | a pen line under the rect | draws |
| `bracket` | a bracket on one `side`, with a leader to a pill when it has a `label` | bracket draws, leader draws, pill pops |
| `pill` | a labelled pill at the rect's left edge, vertically centred (`label` required) | fades and scales |
| `dim` | four plates dim everything except the rect (a spotlight) | fades |
| `highlight` | clean marker yellow multiplied over the text, one band per line box (`rects`, trimmed to the line pitch) | sweeps line by line, left to right |

`rect` is `[x, y, w, h]` in image px (the PNG's own pixels). Test every mark: does it add something
the capture does not already show? A pill repeating visible text, or a box round something already
boxed, fails.

## What plan.py must pass

1. `ANIMS` holds every template name: `flow`, `logo_sting`, `social_post`, `arrow_callout`,
   `icon_burst`, `caption_page`, the overlay formats, and the old `logo`. Type cards are not in it.
2. `scene_parts` walks the props of EVERY anim card, not only `SCENES`, so `word` -> `at`,
   `off_word` -> `off_at`, `icon`/`logo` -> `src` work in every template (flow nodes, icon_burst,
   chat messages, social_post `avatar`/`logo_src` given as `logo`).
3. `caption_page` with no `words`: fill `props.words` from words.json, the words said while the card
   is up, `start`/`end` relative to the card's start.
4. Capture marks: a visuals.json `capture` beat may carry `marks`; capture.mjs copies them into its
   images.json entry; plan.py copies them onto the card and turns each `at_word` (+ optional `nth`)
   into `at` (seconds after the card lands, same rule as scene words), keeping `at_s` as `at`
   when given directly. Marks with neither land at 0.8 s.
5. Top-level `"look"`: style.json `look` laid over the user's taste.json `look` (brand kit wins for
   colours and fonts the user set), passed through unchanged. Absent: the editorial default.
6. Top-level `"motion"`: style.json `motion` (or `motion.personality`) if set, else from
   `pace.median_shot_s` with the table above.
7. Layout: overlay first (plan.py `place_overlays`, `OVERLAY_LEAD_S`). Scenes only for a beat with
   `"layout": "scene"`; plan.py then sets `box: [0, 0, 100, 100]`, `focus` and the
   transitions as above.
8. Captions: style.json `captions` may add `effect` (`pop`, `slide`, `word_highlight`, `karaoke`,
   `reveal`, `lift`, `none`; `animation` stays as the old name), `active_scale`, `active_lift` (% of
   the font size), `emphasis_color` (the stressed word's colour; it also draws one weight heavier, never bigger:
   `emphasis_scale` is not read), `inactive_opacity`, `max_lines` (1: a page is one line at one size;
   `check.py render` FAILs a page drawn on more), `width_pct` (86). `caption_page` defaults to karaoke with the said word filling in the highlight colour at 1.12 x and unsaid words at 35% opacity. plan.py passes them through and may mark a chunk word `"emph": true` (the
   stressed word of a line).
9. `props.word_at` on every box card; `props.enter` / `exit` / `ambient`, `pans`, a zoom's `ease` and
   `targets` from the creator's measured fields when the blend took them (visuals.md "From the teardown").
10. Vertical overlay boxes: `TOP_CARD_MAX_H["9:16"]` (22%) keeps cards off the head. Social posts
   read best in a box at least 30% tall, or as an excerpt (`social_post` `excerpt`).

## Craft lessons from the quality reference

Reference: Ben Marriott, "The Best Motion Design & Animation of 2026 (So Far...)". It is studio work
(illustration, 3D, cel), so the transferable parts are craft, not style. Frames studied: the
calligraphy title build, the poster sequence (lemon on flat green, fruit-market posters), the
"AN ALL-TIMER" title over a sky, the horse poster grid.

- Palette: two or three flat colours per frame. Red ground, black type, one gold accent. Deep green
  ground, one yellow object. No gradients carrying the design; colour blocks do. The `poster-*`
  presets follow this, but a flat saturated ground behind a card reads as AI-made over a talking
  head: plan.py refuses them unless the user's brand kit names one (visuals.md "The AI title card").
- Texture: grain, paper and print halftone sit on top of flat colour so it never reads as vector
  default. Every preset except `mono` has grain on.
- Composition: type is big and confident, cropped by the frame if it has to be; layouts are
  asymmetric with a lot of empty ground; one subject per frame.
- Build order: a title builds stroke by stroke and glyph by glyph in a clear sequence, each piece
  landing with weight, the next starting before the last settles (overlap, not queue).
- Motion: anticipation before a move, overshoot and settle on arrival, follow-through on secondary
  pieces, holds where the frame is allowed to breathe, a camera that keeps drifting through the hold.
- Transitions: match cuts by scale (an object grows to fill the frame and becomes the next ground),
  wipes by a shape in the scene, not a generic crossfade.
- Depth: two or three layers moving at different rates (parallax) even in flat 2D.

What the templates do with it: grain/paper/print texture, masked line reveals
with overlapping staggers, overshoot (`back.out`, springs) and settle (`settle`) eases, secondary
pieces that follow, parallax `data-depth` layers against the camera drift, a wipe between swapped cards.
