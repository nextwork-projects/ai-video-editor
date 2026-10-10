# Changes

Each request as a change to one beat, with the command. `S` is style-edit's `scripts/` folder, as in
SKILL.md. Templates, props and marks in full: style-edit `references/motion.md`; beat shapes:
style-edit `references/shapes.md`.

## Contents
- Requests
- A diagram
- Animate a screenshot
- Motion
- Checks that fail on a changed beat

## Requests

Boxes are `[x, y, w, h]` in % of the frame. On 9:16 everything stays inside x 6-86 and y 14-78 (the
app's buttons, header and caption area); a vertical card is centred (`x = 50 - w / 2`). On 16:9:
x 3-97, y 5-90. The caption band sits at the style's `captions.y_pct` (66% by default).

| request | change |
|---|---|
| move a card | `plan.py beat ... card:N 'box=[x,y,w,h]'`. Pick a free region from the stills: above the head, beside it, or the dark band of a screen. |
| a card covers the caption | move it above the band: `y + h` at least 4 under `captions.y_pct` (a logo tile is 11 tall). |
| a card covers the face | `box` beside or above the head (face.json, from `face.py`). plan.py also shrinks or drops a card that would sit on the head; read its warning. |
| bigger / smaller | a bigger or smaller `box` around the same centre. A capture's text must read on a phone: give it a `find` mark instead of a bigger box when the page is busy. |
| the wrong card or the wrong picture | a logo: `brand=` and `domain=`. A capture: a new `url`, `clip` or `selector`, or new `marks` with `find` (the page's exact words). Then `capture.mjs`. |
| show the real page instead | turn the beat into a capture: `kind=capture url=https://... format=shot` (or `browser`, `sticker`) with a mark: `'marks=[{"kind":"highlight","find":"exact page text","at_word":"word"}]'`. Remove keys the old kind used (`brand=null`). Then `capture.mjs`. |
| swap the logo | `brand=` and `domain=`; the old file stays in `images/` and is no longer used. |
| fewer cards | `--drop` on the cards the user picked. Never drop a card they did not name. |
| it lands late / early | the beat's `word` and `nth` (as captions.json spells the word); a part lands on its own `word` (`at_word` on a mark). |
| it leaves too soon | `hold_s` so the card is still up on its last word. |
| it moves too much / too little | see "Motion". |
| a new animation here | a new beat on the word said at that moment: the real thing the sentence names (shapes.md order). A mechanism with no screen: a diagram. |

A capture beat is in visuals.json and images.json (capture.mjs copies it). `plan.py beat` changes
both. A user's own image is in images.json only.

After the change: `plan.py` again (SKILL.md step 3). It is deterministic, so only the changed beats
move, plus anything the pacing rules attach to them: an added card can remove a zoom change that
filled the gap, a dropped one can add one. `edit.py patch` renders those spans too.

## A diagram

How something works ("it takes the reference video and builds the style"), drawn as a `flow`:
white node cards, each with a real picture and a label of the speaker's words, wires that draw, a
packet that runs a wire and lands on each node's word. On 9:16 a flow is a full-frame scene with a
transition from the speaker's face.

```json
{"word": "reference", "nth": 1, "kind": "anim", "type": "flow", "hold_s": 1.9,
 "props": {"nodes": [{"logo": "youtube", "label": "reference video", "word": "reference"},
                     {"logo": "github", "label": "created the style", "word": "created"}]}}
```

- Every node is a real logo (`{"logo": "brand"}`, plus `"domain"` when Simple Icons may lack it) or a
  file in `images/` (`"src": "images/capture-....png"`, a capture or the user's own image). Never an
  icon alone, never emoji, never a node with a label and no picture.
- Labels are a few of the speaker's own words. No number, name or step the speaker did not say.
- One node per thing named, in the order they are said; 2-4 nodes read on a phone, 6 at most.
  Options off the last node go in `split`; inputs that feed a node in `tasks`.
- Each node's `word` is said while the diagram is up; `hold_s` reaches past the last one by about 0.4 s.
- The diagram must not run into the next card. A logo within 0.5 s of a scene is dropped (plan.py
  warns): shorten `hold_s` until the scene ends 0.5 s before it.
- `accent`: the destination's real brand colour, or leave it unset.

Run `capture.mjs` (it fetches every `logo` inside the props), then plan.

## Animate a screenshot

A still the user hands over moves like a capture: in images.json give it `"format": "shot"` and
marks in its own pixels, and the camera pushes into the first mark as its word is said:

```json
{"src": "images/dashboard.png", "size": [1600, 1000], "word": "dashboard", "nth": 1, "format": "shot",
 "marks": [{"kind": "ring", "rect": [620, 140, 300, 90], "at_word": "revenue"}], "props": {"zoom": 1.45}}
```

`browser` scrolls a tall page to the mark with a cursor; `sticker` cuts the sentence and highlights
it. Each mark adds something the picture does not already show.

## Motion

- One card: its `entrance` (`pop`, `slide`, `fade`, `scale`). `fade` and `scale` are the calmest.
- The whole edit ("everything is too bouncy", "make the motion smoother"): the personality is
  style-level (`motion` in style.json: `calm`, `smooth`, `snappy`, `punchy`). Change it with the taste
  skill, plan again; `edit.py patch` then says the change is not local and asks for a full render.
- A copied creator's measured `enter` / `exit` on a card are hers: leave them unless the user names
  that card.

## Checks that fail on a changed beat

| check | fix |
|---|---|
| `check.py plan`: box under the app's UI | move the box inside the safe zone above |
| `check.py plan`: box on the head | move it beside or above the head, or smaller |
| `check.py plan`: off-centre vertical card | `x = 50 - w / 2` |
| `check.py plan`: vertical `flow` under 60% of the width | fewer nodes or shorter labels |
| `check.py render`: card on the face | as above, then patch again |
| `check.py render`: card lands late | the beat's `word` / `nth`; a scene needs its lead, so start one word earlier |
| `check.py render`: text into a card's edge | a bigger box or a shorter label |
| `check.py render`: AI-default look | the beat uses an icon, emoji or a type card: a real logo or capture instead |
| `check.py render`: render older than its plan | patch or render again; never hand over an old render |
