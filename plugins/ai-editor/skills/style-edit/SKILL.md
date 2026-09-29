---
name: style-edit
description: Edits the user's cut video in a creator's measured style. Takes cut.mp4 and words.json from the cut skill plus a creator's style.json from creator-teardown, plans the captions and zooms to match that creator, adds its own visuals timed to the spoken word (real screenshots of what is named, built animations for numbers, steps and comparisons, plus any images the user gives), shows stills for approval, then renders the finished video with Remotion on the laptop or on the user's own AWS Lambda. Output is 9:16 or 16:9. Use when the user says "edit this in the style of @creator", "make it look like <creator>'s videos", "add captions and zooms", "style my video", "add my images to the video", "render the edit", or has a cut and a style.json and wants the finished video. Runs after cut. Not for cutting mistakes out (that is cut) and not for measuring a creator (that is creator-teardown).
---

# Style edit

A cut video and a creator's style in. The finished edit out: captions, zooms and image cards
timed to the words, in that creator's look.

All paths are relative to the folder Claude Code was started in. File shapes are in the repo's
`docs/CONTRACTS.md`. Run the scripts with `python3` on Mac and Linux, `py` on Windows.

```
edits/<name>/cut.mp4 + words.json      (from the cut skill)
creator-teardowns/<handle>/style.json  (from creator-teardown)
edits/<name>/visuals.json              (Claude writes it: screenshots + animations)
edits/<name>/images.json + images/     (the user's images, plus the screenshots)
   -> plan.json -> stills/ -> render.mp4
```

## 1. Check the inputs

- **No style.json?** Ask which creator. Run creator-teardown in quick mode on them first.
- **No cut.mp4 or words.json?** Run the cut skill on their raw take first.
- **Images?** Ask if they want any image on screen, and on which word. Put each file in
  `edits/<name>/images/` and write `edits/<name>/images.json`:

```json
[{"src": "images/dashboard.png", "word": "dashboard"}]
```

Optional per image: `"nth": 2` (the second time the word is said), `"box": [x, y, w, h]` in
percent of the frame, `"entrance"` (`pop`, `slide`, `fade`, `scale`), `"hold_s"`.
Transparent PNG and Lottie `.json` files both work.

## 2. Captions text

Captions come from `edits/<name>/cut.transcript.json`: the cut skill's verify step transcribed the
finished cut itself, so its words and times match what plays. (`words.json` is the raw take's
transcript moved onto the cut, and carries the raw take's mishearings.) If it is missing, run the
cut skill's verify step first.

Copy it to `edits/<name>/captions.json` and proofread it. Fix only `text`, never `start`/`end`:
- Names and products the transcriber misheard ("cloud" for Claude). Use the script, the video's
  topic and how the speaker says it elsewhere.
- A filler heard as a word ("uh" written as "and"): delete that entry.
Use captions.json in place of words.json from here on.

## 3. Visuals

Add visuals on your own, even when the user gave no images. Read `edits/<name>/captions.json` and write
`edits/<name>/visuals.json`. Every beat anchors to a word as it appears in captions.json (the
transcript may misspell a name: anchor on its spelling, not the real one).

```json
[{"word": "notion", "nth": 1, "kind": "capture", "url": "https://www.notion.com", "clip": [0, 80, 900, 420],
  "note": "the product he names"},
 {"word": "faster", "nth": 1, "kind": "anim", "type": "counter",
  "props": {"from": 0, "to": 10, "suffix": "x", "label": "faster"}}]
```

- **capture** for a NAMED thing: a product, website, doc, post. The real page, cropped to the part
  that is the evidence. `"clip": [x, y, w, h]` in page px, or `"selector": "css"`. `"width"` sets the
  viewport (default 1000): a narrow one (400-550) reflows docs so their text reads on a phone.
- **anim** for an EXPLAINING beat, one idea per card. Only words and numbers the speaker said. Never
  invent a figure.

| type | props |
|---|---|
| `counter` | `to`, optional `from`, `prefix`, `suffix`, `label`, `decimals` (counts up to what was said) |
| `steps` | `items`: 2-4 short lines, landing one by one |
| `versus` | `a`, `b`, optional `a_label`, `b_label` |
| `logo` | `src` (an image in `images/`), `label` |
| `keyword` | `text`, optional `sub` |

Both kinds take `nth` (always set it), `box`, `hold_s`, `entrance`. About one visual every 4-6 s,
never two at once, none in the first second unless it is the hook's subject. Leave `hold_s` out to
use the creator's measured hold.

```bash
node "${CLAUDE_SKILL_DIR}/scripts/capture.mjs" edits/<name>
```

Screenshots every capture beat into `images/capture-*.png` and lists them in `images.json` (your
own images there are kept). It uses the browser the renderer installs, so run `edit.py stills` once
first on a fresh machine. Look at every capture: if a cookie banner or the wrong part of the page
shows, change `clip`, `selector` or `wait_ms` and run it again.

## 4. Plan

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" creator-teardowns/<handle>/style.json edits/<name>/captions.json \
  --images edits/<name>/images.json [--aspect 9:16|16:9]
```

Writes `edits/<name>/plan.json`. The output matches the cut's shape unless `--aspect` says
otherwise. A wide cut made vertical is centre-cropped. A vertical cut made wide sits over a
blurred copy of itself. For both shapes, write a second plan with `--out edits/<name>/plan-16x9.json`
and pass `--plan plan-16x9.json` to every command below (its files get the same `-16x9` suffix).

What the plan does:
- Captions: `words_per_caption` words at a time, never held more than 0.3 s past the last word, a new line at every pause and comma. The word being
  said turns the highlight colour.
- Zooms: about `zoom.per_min` a minute on sentence starts, stressed words or cuts (`zoom.on`),
  alternating in and out so the frame never keeps creeping tighter.
- Cards: images, screenshots and the anims in `visuals.json` (read automatically). Each lands 0.1 s
  before its word and stays for the creator's hold time, cut short when the next one lands. A warning
  names any word that is never said.

## 5. Stills, then wait

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" stills edits/<name>
```

The first run installs the renderer (a few minutes, once). Writes `stills/1-opening.png`,
`2-caption.png`, `3-zoom.png`, then one still per card (`4-card.png`, `5-card.png`, ...). Look at
every still yourself before showing them. Fix before showing if a caption or card covers the face, a
zoom cuts off the head, a screenshot shows the wrong part of the page, or text is too small to read
on a phone. Change `captions.y_pct` or `size_pct` in style.json, or a beat's `box` or `clip` in
visuals.json, then capture and plan again.

Show the user the four stills. **Do not render until they approve.** Their notes go back into
style.json or images.json, then plan and stills again.

## 6. Laptop or Lambda

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" estimate edits/<name>
```

Renders two seconds to time this computer, then prints both options:

```
Laptop: about 2.3 min (measured 6.7 s for 60 frames, 1200 frames in all).
Lambda: about 70 s on 8 Lambdas in us-east-1, about $0.010. A guess until a real render is measured.
```

Give the user both lines and ask which one. Laptop is the default: free, and nothing to set up.
Lambda runs on their own AWS account and costs money. Only offer it when their AWS credentials
work (`aws sts get-caller-identity`); if not, the setup skill's Lambda section sets them up.

## 7. Render

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" render edits/<name>            # laptop
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" render edits/<name> --lambda   # AWS Lambda
```

Both write `edits/<name>/render.mp4` and print how long it took. Lambda also prints what the render
really cost. The first Lambda render sets up the function and a storage bucket in their account;
later renders reuse them. Region comes from `REMOTION_AWS_REGION` or `AWS_REGION`, else us-east-1.

## 8. Open it

Open the result for the user (`open` on Mac, `start ""` on Windows, `xdg-open` on Linux) and give
the full path. Ask for notes. Caption, zoom, card and visual notes need a new plan and stills, then a render.
Notes about what was cut go back to the cut skill.

## Files

- `scripts/plan.py`: style.json + words.json (+ images.json) to plan.json. `plan.py demo` self-checks.
- `scripts/capture.mjs`: visuals.json capture beats to screenshots + images.json. No dependencies.
- `scripts/edit.py`: stills, estimate and render. `edit.py demo` self-checks.
- `../../remotion/`: the Remotion project, copied to `~/.ai-video-editor/remotion` (installed once,
  its source refreshed on every run). `src/Anims.tsx` holds the anim templates. It reads `edits/<name>/.render/`, which holds a copy of the cut
  sized for the output and the card images.
