# The deep pass: graphics, cuts, sound, hook, winners, AI tells, the page

Five scripts after the look pass. Code measures every number; Gemini Flash-Lite names the
kind of each graphic from its crop; Claude reads images only in the no-key fallback.

| Script | Writes | How |
|---|---|---|
| `visual.py measure` | `pace.cut_kinds`, `zoom.ease`, `camera` | each cut classified from the frames round it; pans and shake by phase correlation on the top third; a push's scale frame by frame, fitted to an ease |
| `graphics.py measure` | `video/<id>.graphics.json`, `graphics/<id>_<n>.jpg`, `graphics/heatmap.png`, `graphics.*` | a clean plate per framing, the changed regions that are not the speaker, tracked; entrances and exits fitted at the source frame rate |
| `gemini.py kinds` | `kind`, `what` per graphic, `graphics.kinds` | Flash-Lite on the crops, 12 a call |
| `sound.py measure` | `video/<id>.sound.json`, `sound` | spectral-flux onsets outside the voice, five spectral features, music in the gaps |
| `report.py build` | `hook`, `winners`, `ai_tells`, `report.json`, `teardown.html` | reads all of the above |

## Graphics

**Found.** Frames at 5 a second, 180 px wide. Every segment between cuts and pushes is
matched to the longest one by its corners (ORB, RANSAC similarity), so a punch-in or a
nudged tripod lines up. Each segment's median votes per pixel; the value most segments
agree on (within 24 levels) is the plate. Where no value holds 60% of the segments, the
two top clusters compete and the one closer to the sure pixels around it wins (so white
pages that are up half the time do not become the wall). A graphic is a region that
differs from the plate, is not the speaker (face box widened, full width below the
shoulders), is not the caption band, fills 35% of its box, and holds 0.6 s with edges that
move on a line. Dropped: mostly skin (hands), nothing drawn in it, the set nudged a few
pixels, the set reframed (template match over five zooms above 0.65), a thin strip with no
OCR text. When the footage around the speaker is half as sharp as the plate, the creator
blurs behind graphics: the sharp region is the graphic (`blur_behind`).

**Moves.** Round each entrance, every source frame is compared with the plate in two strips
through the box (one per axis), so a card that starts off-frame still measures by its
leading edge. The biggest change wins: `slide` (from, distance), `scale` (from what size),
`mask` (one side grows), `fade` (the picture is all there but weaker against the plate),
else `cut`. A grid search fits start, duration and ease family to the progress curve:
`power1-4.out`, `expo.out`, `sine.inOut`, `power2/3.inOut`, `back.out(0.8 .. 3.5)`, `none`.
Exits: the same fit on the reversed clip, `.in` names. While up: `video` (the picture inside
changes), `push` (the box grows), `drift` (the box moves), `still`.

**Kinds.** Code guesses first (moving: b-roll or a UI recording; 4+ OCR lines: a screenshot;
text on a flat ground: a text card). `gemini.py kinds` replaces the guess and drops crops it
calls `part of the set`. Without a key: one Agent call, `model: "haiku"`, reads the crops in
`graphics/` and writes `kind` and `what` into each `video/<id>.graphics.json`, then
`graphics.py merge <handle>`.

**Ceilings.** A graphic that arrives on a hard cut to a new shot has no plate to differ from.
A graphic beside the speaker's lap is masked with the body. Whooshes under speech are not
told from an "s" and are missed. On a real creator about 1 in 5 crops was the set before
the kinds pass (19 of 95); the pass caught them.

## Cuts and camera

`zoom-punch` (the next shot is the last one scaled), `whip` (frames round the cut under 40%
of the shots' sharpness), `dissolve` / `mask` (most of the change spread over 2+ frames;
mask when pixels are either old or new), `jump` (a third of the frame unchanged across the
cut), `match` (new picture, same layout of edges), else `hard`. Pans: the top third drifts
2% of the width a second for 1 s, one direction, strong phase peak. Shake: frame-to-frame
jitter round the drift over 0.4% of the width.

## Sound

Mono 22 kHz, 1024-point STFT. Onsets: log spectral flux 8 median deviations over its 4 s
neighbourhood. The voice is the transcript's words (plus 0.08 s, gaps under 0.25 s filled);
inside it only a low hit (40% of the linear flux under 120 Hz) counts. Kind from the next
0.8 s (cut where the voice comes back): click (under 0.06 s, bright), pop (under 0.18 s),
impact (centroid under 500 Hz), ding (tonal, bright, 0.3 s), whoosh (noise, 0.15-1.3 s,
swells), riser (over 1 s, climbs). Music: a gap 10-40 dB under the voice whose median
spectrum peaks 20 dB over its floor and holds (log-spectrum correlation 0.1 s apart over
0.5). Two such gaps, or half, and the video has a bed; `span_s` says where. It reads gaps
only: the page says to listen to one.

## Hook and winners

Hook: the first 3 s of each video. Face share, OCR text that is not a caption (the title),
first cut, first words on screen, first graphic and its kind, first caption, first word, the
opening line verbatim. Winners are 2x the creator's median views or more (likes for
Instagram links); control is 0.5-2x. A field differs when the medians are 25% apart (0.5 s
for times); "every winner" when no winner overlaps a control video. No p-values; n is
printed next to every number.

## AI tells

`report.py` loads ai-editor's `ai_tells.py` (this repo, `AI_EDITOR_STYLE_SCRIPTS`, or an
installed plugin) and runs `check_look` on the creator's measured font and the graphics'
own colours, `check_plan` on their caption style, and `check_still` on every text card crop.
Real screenshots are skipped: a capture is the real page. Without ai-editor installed the
page says so.

## The page

`creator-teardowns/<handle>/teardown.html`, one file, images embedded (1-2 MB for 7 videos):
the numbers that matter, a strip of 8 frames per video (winners first), every graphic grouped
by kind with what it shows and how it moved, the layout heatmap, each entrance as its fitted
curve, caption samples, cuts and camera, sound, the first 3 s table, winners against control
as dot plots, the AI tells with the offending crops, and the list of parts Claude then asks about in the question box. Open it with `open` (Mac), `start` (Windows), `xdg-open`
(Linux), or publish it as an artifact. Claude reads `look.md`, not the page.

## Cost per teardown (7 videos, about 9 minutes of video, measured on a real creator)

| Pass | Where | Tokens | $ (paid tier) |
|---|---|---|---|
| look (`gemini.py look`) | Gemini, 5-7 videos at 1 fps | about 40,000 | $0.010-0.012 |
| kinds (`gemini.py kinds`) | Gemini, 75-95 crops | 21,000-27,000 (about 280 a crop) | $0.006-0.008 |
| everything else | this computer | 0 | $0 |
| Claude | reads look.md (about 45 lines) | about 600 | |

Free tier: $0. Time on an M-series Mac: graphics about 20 s a video, sound 2 s, the page 15 s.
