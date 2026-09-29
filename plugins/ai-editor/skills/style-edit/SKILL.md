---
name: style-edit
description: Edits the user's cut video in a creator's measured style. Takes cut.mp4 and words.json from the cut skill plus a creator's style.json from creator-teardown (and any images the user wants shown), plans the captions, zooms and image cards to match that creator, shows four stills for approval, then renders the finished video with Remotion on the laptop or on the user's own AWS Lambda. Output is 9:16 or 16:9. Use when the user says "edit this in the style of @creator", "make it look like <creator>'s videos", "add captions and zooms", "style my video", "add my images to the video", "render the edit", or has a cut and a style.json and wants the finished video. Runs after cut. Not for cutting mistakes out (that is cut) and not for measuring a creator (that is creator-teardown).
---

# Style edit

A cut video and a creator's style in. The finished edit out: captions, zooms and image cards
timed to the words, in that creator's look.

All paths are relative to the folder Claude Code was started in. File shapes are in the repo's
`docs/CONTRACTS.md`. Run the scripts with `python3` on Mac and Linux, `py` on Windows.

```
edits/<name>/cut.mp4 + words.json      (from the cut skill)
creator-teardowns/<handle>/style.json  (from creator-teardown)
edits/<name>/images.json + images/     (optional, the user's images)
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

## 2. Plan

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" creator-teardowns/<handle>/style.json edits/<name>/words.json \
  [--images edits/<name>/images.json] [--aspect 9:16|16:9]
```

Writes `edits/<name>/plan.json`. The output matches the cut's shape unless `--aspect` says
otherwise. A wide cut made vertical is centre-cropped. A vertical cut made wide sits over a
blurred copy of itself. For both shapes, write a second plan with `--out edits/<name>/plan-16x9.json`
and pass `--plan plan-16x9.json` to every command below (its files get the same `-16x9` suffix).

What the plan does:
- Captions: `words_per_caption` words at a time, a new line at every pause and comma. The word being
  said turns the highlight colour.
- Zooms: about `zoom.per_min` a minute on sentence starts, stressed words or cuts (`zoom.on`),
  alternating in and out so the frame never keeps creeping tighter.
- Cards: land 0.1 s before their word, stay for the creator's hold time. A warning names any word
  that is never said.

## 3. Stills, then wait

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" stills edits/<name>
```

The first run installs the renderer (a few minutes, once). Writes `stills/1-opening.png`,
`2-caption.png`, `3-zoom.png` and `4-card.png` (no card still without cards). Look at every still
yourself before showing them. Fix before showing if a caption covers the face, a zoom cuts off the
head, or text is too small to read on a phone. Change `captions.y_pct` or `size_pct` in style.json,
or a card's `box` in images.json, then plan again.

Show the user the four stills. **Do not render until they approve.** Their notes go back into
style.json or images.json, then plan and stills again.

## 4. Laptop or Lambda

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

## 5. Render

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" render edits/<name>            # laptop
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" render edits/<name> --lambda   # AWS Lambda
```

Both write `edits/<name>/render.mp4` and print how long it took. Lambda also prints what the render
really cost. The first Lambda render sets up the function and a storage bucket in their account;
later renders reuse them. Region comes from `REMOTION_AWS_REGION` or `AWS_REGION`, else us-east-1.

## 6. Open it

Open the result for the user (`open` on Mac, `start ""` on Windows, `xdg-open` on Linux) and give
the full path. Ask for notes. Caption, zoom and card notes need a new plan and stills, then a render.
Notes about what was cut go back to the cut skill.

## Files

- `scripts/plan.py`: style.json + words.json (+ images.json) to plan.json. `plan.py demo` self-checks.
- `scripts/edit.py`: stills, estimate and render. `edit.py demo` self-checks.
- `../../remotion/`: the Remotion project, copied to `~/.ai-video-editor/remotion` (installed once,
  its source refreshed on every run). It reads `edits/<name>/.render/`, which holds a copy of the cut
  sized for the output and the card images.
