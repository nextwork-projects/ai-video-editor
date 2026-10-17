---
name: broll-reel
description: Copies a reference reel onto the user's own b-roll. Reads the reel's cut times, its on-screen words (place, size, colour) and its sound, picks one clip from the user's b-roll folders (Google Drive or local, broll.py) for every shot, rebuilds the reel at 9:16 with the same words over the new clips and the reel's audio, renders it and opens it in the editor so the user changes anything with notes. No talking head, no script. Use when a home page job says `mode=broll-reel`, or the user says "copy this reel with my b-roll", "make this reel with my clips", "same text, my b-roll", "redo this reel with my footage". Not for editing the user's own talking take (that is start, cut and style-edit) and not for measuring a creator's style (that is creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, the venv (numpy, pillow, OCR: ocrmac on a Mac, rapidocr elsewhere), Node and the renderer the setup skill installs. Runs from the full ai-editor plugin folder (uses lib/, style-edit's renderer and creator-teardown's measuring scripts).
---

# B-roll reel

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows (asking, looking real, motion, story and framing, privacy, cost).

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

Run the scripts with `python3` on Mac and Linux, `py` on Windows.
`PY="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py"` (`python3 "$PY" <script>` runs the editor's venv Python; `py "$PY"` on Windows),
`R="${CLAUDE_SKILL_DIR}/scripts/reel.py"`, `L="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor"`, `EDIT` the job's `edit=` folder,
`REEL` the job's clip (the reel the page downloaded into the library).

```
reel -> reel.py read (cuts, words, sound, a frame per shot) -> Claude fixes the words from the frames
     -> broll.py sheet per library -> Claude picks a clip per shot -> picks.json
     -> reel.py build (base.mp4 + plan.json) -> edit.py render -> the editor (review.py, stage edit) -> notes -> again
```

The page already opened the editor on the reel (round 0, stage `edit`): serve it and say its URL first
(`start/references/home.md`), then report each step there with `review.py EDIT status "<step>"`.

## 1. Read the reel

`python3 "$PY" "$R" read EDIT REEL`. It writes `EDIT/reel.json` (the shots and the reel's captions), `EDIT/reel/audio.m4a`,
`EDIT/reel/shots.jpg` (one frame per shot, numbered left to right) and `EDIT/reel/shot-NN.jpg` (each shot full size),
and `EDIT/reel/ocr.json` (every word the OCR read, footage included).

## 2. Fix the words (always)

OCR gets the captions and their timing; it misreads letters and can merge a line from the footage into a caption.
Open every `shot-NN.jpg` and make `reel.json` `texts` say exactly what the reel says on screen:

- the reel's own words, letter for letter (`AI`, not `Al`), with its line breaks; drop any text that is part of the
  footage (a screen, a sign, a keyboard); add a caption the filter missed (look in `ocr.json`)
- `color` the text's fill and `box_color` the solid box behind it (`null` when the words sit on the picture with no box)
- `start` / `end` when the caption is up for more of the shot than the OCR caught

`EDIT/instructions.md` (Additional instructions for Claude), when there is one, comes next and beats the reel: new
words, a caption added or removed, a different end line. Without it the words stay the reel's.

## 3. Pick the b-roll

`EDIT/broll.json` lists the folders (`"auto": true`: Claude decides, use the ones that fit; `false`: only those).
For each folder `python3 "$L/broll.py" sheet <name>`, then look at every sheet it prints (clip paths in its `index.json`).
For every reel shot pick one clip that shows what that shot shows or what its caption says, following the instructions.
Prefer clips at least as long as the shot (a shorter one loops), never the same clip twice in a row, and the reel's own
footage never. Write `EDIT/picks.json`: `{"shots": [{"clip": "<path from index.json>", "from": <s into the clip>}]}`,
one per shot in order.

## 4. Build, render, hand over

```bash
python3 "$PY" "$R" build EDIT
python3 "${CLAUDE_PLUGIN_ROOT}/skills/style-edit/scripts/edit.py" render EDIT
python3 "$L/review.py" EDIT start --video EDIT/render.mp4 --stage edit --plan EDIT/plan.json
```

Look at three stills of `render.mp4` (one per caption change) before saying it is ready: every caption readable over
its clip and inside the reels safe zone, no clip with someone else's words burned in.

## 5. Notes

Run `review.py EDIT wait` in the background, as for any edit (`style-edit/references/review.md`). A note about a shot
changes its pick in `picks.json`; a note about words changes `reel.json` `texts` (a note on a caption names it).
Then build, render and `review.py EDIT round --video EDIT/render.mp4 --stage edit --plan EDIT/plan.json`.
