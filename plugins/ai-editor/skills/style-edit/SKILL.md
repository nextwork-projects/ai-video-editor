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

## 0. Read the user's taste

```bash
python3 "${CLAUDE_SKILL_DIR}/../taste/scripts/taste.py" show
```

Follow every rule in it; the scripts already read its settings. When the user reacts to the result
("too slow", "captions too small"), save it with the taste skill before redoing the edit.

## 1. Check the inputs

- **No style.json?** Ask which creator. Run creator-teardown in quick mode on them first.
- **No cut.mp4 or words.json?** Run the cut skill on their raw take first.
- **Layout?** Ask overlay or split (vertical only). **Overlay** (default): the speaker fills the
  frame and visuals float in the space above their head, so they stay small. **Split**: while a
  visual is up it owns the top half of the frame on a plain ground and the speaker sits in a
  rounded window underneath, framed so the whole head shows; with no visual up the speaker has the
  whole frame again, and the window slides between the two. Split gives visuals about twice the
  room. Pass `--layout split` to plan.py (or set `"layout": {"mode": "split", "ground": "#F4F4F2"}`
  in style.json; `ground` is the panel colour, `seam` where it ends, default 50% of the height).
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
  `"highlight": "the exact sentence"` (copied from the page, as it reads there) makes the card open
  on the clip, travel down the page to that sentence and sweep a highlighter over it. Use it on
  docs and articles, where one sentence is the evidence. Give the card `hold_s` of 3 s or more so the
  sweep finishes. capture.mjs stops with an error if the sentence is not on the page.
- **logo** every time a brand or product is named (`"brand": "claude"`, plus `"domain": "example.com"`
  for brands Simple Icons lacks). A small logo tile pops above the caption for 1.2 s (split: the logo
  gets the panel to itself for 1.5 s, and is skipped while a bigger visual is up). Logos run in
  their own lane, so one can land while a bigger card is up. Mark a named brand with a logo even
  when it also gets a capture; skip generic words ("email", "AI").
- **anim** for an EXPLAINING beat, one idea per card. Only words and numbers the speaker said. Never
  invent a figure. **Prefer a scene** (`flow`, `race`, `pile`): logos and icons that move, each part
  landing on its own word. A text card (`counter`, `steps`, `versus`, `keyword`) is the last resort:
  at most one or two per video, for a line with nothing to picture (a call to action).

Scenes. A part is `{"icon": "mail"}` (any name on lucide.dev/icons), `{"logo": "claude"}` (plus
`"domain"` for brands Simple Icons lacks) or `{"src": "images/x.png"}`, with an optional 1-2 word
`label` and a `"word"` to land on (as captions.json spells it, the first time it is said once the
card is up; `"nth"` for a later time). `"off_word"` dims a part again. A label can swap on words:
`[{"text": "task"}, {"text": "small task", "word": "small"}]`. Set `hold_s` so the card is still up
on its last word (plan.py warns when it is not).

| scene | shows | props |
|---|---|---|
| `flow` | a process or a decision: nodes joined by arrows that draw in, each lighting on its word; the last node can split to 2-3 | `nodes`, optional `split`, `tag` |
| `race` | "X times faster/cheaper": bars led by logos grow to the values said, the winner counts up | `rows` (`value`, optional `from`, `label`), `prefix`, `suffix` |
| `pile` | volume: `count` icons fly from a `source` into 1-3 `stacks` | `icon`, `count`, `source`, `stacks`, `word` (when they start) |

Every scene takes `tag: {"text": "< 5¢", "word": "cents"}`, a small badge for the one number said.

```json
{"word": "Before", "nth": 1, "kind": "anim", "type": "flow", "hold_s": 10,
 "props": {"nodes": [{"icon": "list-todo", "label": "task", "word": "task"},
                     {"logo": "typesafe", "domain": "typesafe.ai", "label": "jev", "word": "Jev"}],
           "split": [{"logo": "claude", "label": "haiku", "word": "Haiku", "off_word": "harder,"},
                     {"logo": "claude", "label": "opus", "word": "Opus"}]}}
```

Text cards:

| type | props |
|---|---|
| `counter` | `to`, optional `from`, `prefix`, `suffix`, `label`, `decimals` (counts up to what was said) |
| `steps` | `items`: 2-4 short lines, landing one by one |
| `versus` | `a`, `b`, optional `a_label`, `b_label` |
| `logo` | `src` (an image in `images/`), `label` |
| `keyword` | `text`, optional `sub` |

All kinds take `nth` (always set it), `box`, `hold_s`, `entrance`. About one card every 4-6 s,
never two cards at once, none in the first second unless it is the hook's subject. Leave `hold_s` out to
use the creator's measured hold.

```bash
node "${CLAUDE_SKILL_DIR}/scripts/capture.mjs" edits/<name>
```

Fetches every logo into `images/logo-<brand>.svg|png` (Simple Icons, CC0, then the site's own icon)
and every scene icon into `images/icon-<name>.svg` (Lucide, ISC),
and screenshots every capture beat into `images/capture-*.png` and lists them in `images.json` (your
own images there are kept). It uses the browser the renderer installs, so run `edit.py stills` once
first on a fresh machine. Look at every capture: if a cookie banner or the wrong part of the page
shows, change `clip`, `selector` or `wait_ms` and run it again.

Nothing lands where the app draws its own buttons. On vertical video, `plan.py` keeps every card and
the captions out of the top 14% (the top bar), the right 14% (the like and share rail) and the
bottom 22% (the username and description), and caps a card at the top at 22% tall so it stays off
the head. In split, every visual fills the top panel between the top 14% and the seam instead.

## 4. Plan

Find the speaker's head first, so no card or logo covers the face:

```bash
~/.ai-video-editor/venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/face.py" edits/<name>   # Windows: Scripts\python.exe
```

It writes `edits/<name>/face.json`. `plan.py` reads it: a card at the top shrinks into the space
above the head, a logo moves below the chin or beside the head, and a card that cannot fit is
dropped with a warning. Covering the face is never the fallback. In split it frames the speaker's
window instead: the hair sits just under the seam, the head centred, scaled up if it is small.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/plan.py" creator-teardowns/<handle>/style.json edits/<name>/captions.json  [--aspect 9:16|16:9] [--layout overlay|split]
```

Writes `edits/<name>/plan.json`. The output matches the cut's shape unless `--aspect` says
otherwise. A wide cut made vertical is centre-cropped. A vertical cut made wide sits over a
blurred copy of itself. For both shapes, write a second plan with `--out edits/<name>/plan-16x9.json`
and pass `--plan plan-16x9.json` to every command below (its files get the same `-16x9` suffix).
To compare layouts the same way, write `--layout split --out edits/<name>/plan-split.json`.

What the plan does:
- Captions: `words_per_caption` words at a time, never held more than 0.3 s past the last word, a new line at every pause and comma. The word being
  said turns the highlight colour.
- Zooms: about `zoom.per_min` a minute on sentence starts, stressed words or cuts (`zoom.on`),
  alternating in and out so the frame never keeps creeping tighter.
- Cards: images, screenshots and the anims in `visuals.json` (read automatically). Each lands 0.1 s
  before its word and stays for the creator's hold time, cut short when the next one lands. A warning
  names any word that is never said.
- Motion: every card moves the whole time it is up. Screenshots push in slowly (a tall page, or
  one with a `highlight`, travels down inside its card); scene parts spring in on their words and
  float; a card that lands right after the last one slides it out as it slides in. In split, the
  panel stays open across gaps under 1.2 s, so a run of visuals swaps inside one panel.

### Sound

`plan.py` adds sound cues on its own: a whoosh when a card lands, a whoosh when a card leaves
while a sentence is still going, a pop when a scene part or logo lands, a soft hit for a counter
or a scene's tag, and a punch on a zoom. Never two within 0.25 s, at most one per 1.5 s on average.
Each cue starts early by its attack, so its hit is heard on the frame the thing lands.

The first plan builds the kit into `edits/<name>/.sfx/` with `scripts/sfx.py`: every cue is
synthesised by ffmpeg from a fixed seed (nothing to licence), then set about 4 dB under this
cut's speech (the pop 6, the zoom 5), measured on the loudest 50 ms. The level lives in the file,
so change it there, not in the renderer. A new cut.mp4 rebuilds the kit on the next plan.
`sfx.py build edits/<name>` rebuilds it by hand.

No sound: `"sfx": false` in style.json, or `plan.py ... --no-sfx`.

### Check the plan

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/check.py" plan edits/<name> [--plan plan-split.json] [--style creator-teardowns/<handle>/style.json]
```

Instant. It FAILs a card under the app's UI, a vertical card whose centre is more than 1.5% off
the middle, a card on the head while it is up (zooms and the split window included), captions
outside the safe band, a caption up longer than 1.2 s a word or held more than 0.3 s past its last
word, and text-card text under 34 px. It WARNs a stretch with no card, zoom or cut longer than
2.5 x the creator's median shot (6 s without `--style`) and text cards that outnumber picture
cards. Every line has the time and the fix. Fix every FAIL, plan again, check again, before the
stills. `edit.py stills` runs it first and stops on a FAIL (`--no-check` to look anyway).

## 5. Stills, then wait

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/edit.py" stills edits/<name>
```

The first run installs the renderer (a few minutes, once). Writes `stills/1-opening.png`,
`2-caption.png`, `3-zoom.png`, then one still per card (`4-card.png`, `5-card.png`, ...), and for
each card `N-card-early.png` and `N-card-late.png` so its motion can be judged, and `N-swap.png`
mid-move where a card slides in over the one before it. Look at
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

### Check the render

```bash
~/.ai-video-editor/venv/bin/python "${CLAUDE_SKILL_DIR}/scripts/check.py" render edits/<name> [--plan plan-split.json]
```

Before the user sees the render. Four samples a second: it FAILs a card whose drawn pixels land on
the face (YuNet, as face.py), a vertical card whose drawn content sits more than 2% of the width
off centre at mid-life, a silence over 0.3 s inside the speech (cut.mp4, the cut skill's derived
threshold) and a kept span under 0.2 s between two splices. It WARNs a card that holds still for
more than 1.5 s. It lists (LOOK) caption words that differ from what cut.transcript.json heard.
FAILs go back to the plan (re-plan, re-render) or the cut (re-cut). At most two fix rounds; then
show the user the render with what is still listed. Overlay cards sit on a dark panel, so their
centre is the panel's, not the art inside it. Results land in `edits/<name>/check.json`.

## 8. Open it

Open the result for the user (`open` on Mac, `start ""` on Windows, `xdg-open` on Linux) and give
the full path. Ask for notes. Caption, zoom, card and visual notes need a new plan and stills, then a render.
Notes about what was cut go back to the cut skill.

## Files

- `scripts/plan.py`: style.json + captions.json (+ images.json, visuals.json, face.json) to plan.json. `plan.py demo` self-checks.
- `scripts/sfx.py`: the sound cues, synthesised and level-matched to the cut into `.sfx/`. `sfx.py demo` self-checks.
- `scripts/capture.mjs`: visuals.json to screenshots, logos and icons in `images/`. No dependencies.
- `scripts/face.py`: the speaker's head per 0.5 s into face.json (OpenCV YuNet). `face.py demo` self-checks.
- `scripts/check.py`: the automatic check of a plan (stdlib) and a render (venv). `check.py demo` self-checks.
- `scripts/edit.py`: stills, estimate and render. `edit.py demo` self-checks.
- `../../remotion/`: the Remotion project, copied to `~/.ai-video-editor/remotion` (installed once,
  its source refreshed on every run). `src/Anims.tsx` holds the anim templates. It reads `edits/<name>/.render/`, which holds a copy of the cut
  sized for the output and the card images.
