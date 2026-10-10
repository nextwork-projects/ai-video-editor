---
name: overlays
description: Works on the visuals of an edit that is already rendered, one beat at a time, without running the whole edit again. Moves, resizes, swaps, drops or adds a card, logo, real page capture or animated diagram at the moment the user names, re-plans, makes stills of just those moments, checks them (safe zone, face, motion, AI looks), patch-renders only the frames that changed and hands over on the review page. Use when the user says "add an animation here", "make a diagram of how this works", "this card is wrong", "the card covers my face", "move the card", "make the card bigger", "swap the logo", "show the real page instead", "fewer cards", "animate this screenshot", "make the motion smoother", or leaves a review note about a card. Not for the cut (cut), not for caption size, font or colour defaults (taste and style-edit), not for the first full style pass on a new cut (style-edit), and not for measuring a creator (creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, Node 20+ and the Remotion renderer the setup skill installs; internet for new captures. Runs from the full ai-editor plugin folder (uses style-edit's scripts, lib/ and remotion/).
---

# Overlays

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: real things carry each beat, no AI looks, smooth
before varied, every element lands on its spoken word, never cover the face, the safe zone.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

An edit folder that style-edit already rendered in. The same edit out, with only the named beats
changed: re-planned, checked, and re-rendered where they changed. Everything else stays exactly as
the user approved it. This skill writes no renderer code: it changes visuals.json and images.json,
and style-edit's scripts and Remotion templates do the rest.

Run the scripts with `python3` on Mac and Linux, `py` on Windows. Paths are relative to the folder
Claude Code was started in. `S="${CLAUDE_PLUGIN_ROOT}/skills/style-edit/scripts"`,
`VPY="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py"`; `python3 "$VPY"` is the venv Python.

```
edits/<name>/plan.json + render.mp4 (+ render.plan.json, the plan it was made from)
visuals.json / images.json  ->  plan.py  ->  stills-at/sheet.png  ->  edit.py patch  ->  check.py render  ->  review page
```

`references/changes.md` has every kind of change with its exact command, the diagram recipe and
what to do when a check fails. Read the section a step names.

## 0. Read the taste and the edit

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show --edit edits/<name>
python3 "$S/plan.py" cards edits/<name>
```

`cards` prints one line per card: `card:N`, its time, kind, word, box, layer, and the visuals.json or
images.json beat it came from. `card:N` is the review page's `[card N ...]`; the stills sheet's
"card N" is `card:N-1`. Never read plan.json itself.

- **No render.mp4 or no plan.json?** This is a first pass: use style-edit.
- **The note is about the cut** (a word cut off, a pause): the cut skill. **About caption size, font
  or colour for every video:** the taste skill, then style-edit.
- **The note is a preference for every video** ("logos always smaller", "no full-screen
  diagrams"): do the fix here, and save the rule with the taste skill too.

## 1. Find the beat

Match the user's words to cards: a time ("at 0:15"), a word ("the Duolingo one"), a review note
(`[card 1 logo 'Duolingo']`). One clear match: go on. Two or more, or none: ask in the question box,
one option per candidate card (its time, kind and word), recommended the nearest one.

Change only the beats the user named. Never re-pick, move or restyle another card on the way.
"Fewer cards" with no names: list the cards that carry the least (a logo in passing, the second
appearance of the same picture) and ask which go, the weakest one recommended.

## 2. Make the change

One command per beat. A beat is found by `card:N`, a time (`0:15`, `15.4s`, the card up then or
starting within 1.5 s) or a word (`Duolingo`, `Duolingo@2` for the second time it is said):

```bash
python3 "$S/plan.py" beat edits/<name> card:1 'box=[40,17,20,11]'      # move or resize (x, y, w, h in % of the frame)
python3 "$S/plan.py" beat edits/<name> 0:20 brand=Notion domain=notion.so   # swap the logo
python3 "$S/plan.py" beat edits/<name> YouTube@1 --drop                # fewer cards
python3 "$S/plan.py" beat edits/<name> --add edits/<name>/visuals.fill-1.json   # new beats, in spoken order
```

Values are JSON (or plain text); `props.label=x` sets inside a beat; `key=null` removes a key. A
capture beat lives in both visuals.json and images.json: `beat` changes both. What each request
becomes (move, bigger, off the face, off the caption, real page, animate a screenshot, smoother,
lands late): `references/changes.md` "Requests".

**New visuals** (an animation, a diagram, a real page): pick the format from what is said, in
style-edit's order (`${CLAUDE_PLUGIN_ROOT}/skills/style-edit/references/shapes.md`): the user's own
asset, the real thing captured, UI rebuilt from real parts, real logos. A diagram is a `flow` of real
logos or capture files that lights each part on its spoken word (`references/changes.md` "A
diagram"); never a text panel, a type card or stock icons. With several new beats, fan out: one
`template-filler` agent per beat, all in ONE message, each given the edit folder, its sentence, its
pick, the word it lands on, the full path of style-edit's `references/shapes.md`, and its own output
file `edits/<name>/visuals.fill-<n>.json`. Then one `beat --add` with every file. One new beat:
write it yourself.

## 3. Fetch, then plan again

```bash
node "$S/capture.mjs" edits/<name>          # only when a beat needs a new capture, logo or post; keeps files already fetched
python3 "$S/plan.py" edits/<name>/style.json edits/<name>/captions.json [--aspect ...] [--layout ...]
```

Plan with the same flags as the edit's last plan (the same `--out` for a second shape, then
`--plan plan-16x9.json` on every later command). plan.py is deterministic: the beats you did not
touch come out the same. It keeps the rendered plan as `render.plan.json` before it overwrites
plan.json. Read every warning about your beat. With the profile's `behind` on and a behind card
moved or added, run `python3 "$VPY" "$S/matte.py" edits/<name>` (it cuts only new frames; say its
`--estimate` first when it is more than a few seconds of cards).

```bash
python3 "$S/check.py" plan edits/<name>
```

Fix every FAIL on your beats and plan again.

## 4. Stills of just those moments

```bash
python3 "$S/edit.py" stills edits/<name> --at 15.4 --at 12.9-15.3
```

A time is one still; a range is five (entrance, landing, middle, late, exit), the frames a moving
card is judged on. Give each changed card its range (from `plan.py cards`), and a moment just
before and after it. Writes `stills-at/` and `stills-at/sheet.png`, each tile labelled with its time
and the card up. Review the sheet; hand it to the `stills-critic` agent too and compare its blind
`reads_as` with what the beat should show. Fix before going on: a card on the face, under the
caption or the app's buttons, text too small for a phone, the wrong part of a page, an AI look.

- **A fix** (move, resize, swap, drop): go on to step 5.
- **New visuals** (an animation, a diagram, a new page): show the sheet and ask in the question box:
  **Render it (Recommended)** / **Change something**. Do not render before the answer.

## 5. Patch-render

```bash
python3 "$S/edit.py" patch edits/<name>
```

It compares plan.json with `render.plan.json`, re-renders only the spans that changed (each grown
0.5 s for exits and sound tails) on the laptop, and splices them into render.mp4, sound cut by the
sample. It prints the spans and the frame count. It renders in full instead when most of the video
changed, and stops when the change is not local (size, look, motion personality, caption style):
then ask where to render as style-edit step 6 does, and render as its step 7. `--range 13-15.5`
re-renders a span by hand (an older render with no `render.plan.json`).

## 6. Check the render

```bash
python3 "$VPY" "$S/check.py" render edits/<name>
```

FAILs at your moments go back to step 2 or 3; at most two fix rounds, then hand over with what is
still listed. A FAIL far from your beats was there before: say so, do not chase it here. What each
FAIL means: style-edit `references/plan.md` "What the checks FAIL and WARN".

## 7. Hand over on the review page

```bash
R="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py"
python3 "$R" edits/<name> resolve <note> fixed --reply "moved the Duolingo logo above the caption" --new-t 15.4
python3 "$R" edits/<name> round --stage edit --video edits/<name>/render.mp4 --plan edits/<name>/plan.json
```

No page yet: `start` with the same flags. Then `serve` and `wait` in the background
(style-edit `references/review.md`). Tell the user in one line what changed and where. New notes
about cards come back here; notes about the cut go to the cut skill.

## If a script stops

| message | do |
|---|---|
| `no beat matches ...` | `plan.py cards` and pick the card by `card:N` |
| `no render.plan.json ...` (edit.py patch) | `--range A-B` around the changed cards, or render in full |
| `the change is not local (<key> changed)` | render in full: style-edit steps 6 and 7 |
| `the plan is WxH, N frames; render.mp4 is ...` | the cut or the shape changed: render in full |
| `warning: '<word>' ... never said` | the beat's `word`/`nth` must be spelled as captions.json has it |
| capture.mjs `failed <kind> '<word>'` | another URL, or a logo instead |
| `check.py plan found a FAIL` (stills) | fix the FAIL on your beat, plan again |
| `... missing (run matte.py)` | run matte.py, then stills or patch again |

## Files

- `references/changes.md`: each request as a beat change, the diagram recipe, failing checks.
- style-edit's `scripts/`: `plan.py cards|beat` (find and change one beat), `edit.py stills --at`
  (stills of moments), `edit.py patch` (re-render what changed), `capture.mjs`, `matte.py`, `check.py`.
- `${CLAUDE_PLUGIN_ROOT}/agents/template-filler.md` (haiku, one per new beat), `stills-critic.md` (sonnet),
  `render-watcher.md` (a full render that runs long).
