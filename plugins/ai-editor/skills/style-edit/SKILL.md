---
name: style-edit
description: Turns an approved cut into the finished video in a creator's measured style. Takes cut.mp4 from the cut skill plus a style.json (from start or creator-teardown), plans captions and zooms to match the creator, adds visuals timed to the spoken word (the user's own images, real screenshots, posts and logos of what is named, the line marked on the real page; no type cards, stock icons or emoji), shows one stills sheet for approval, then renders 9:16 or 16:9 with Remotion on the laptop, Modal, GitHub Actions or the user's AWS Lambda, and can export the edit to Final Cut, Premiere, Resolve or CapCut. Use when a cut already exists and the user says "style it", "now add the style", "add captions and zooms", "add my images to the video", "render the edit", "change the captions", "export to Final Cut" or "send it to Premiere". Not for a raw take or a first request to edit a video like a creator (that is start), not for cutting mistakes out (cut), and not for measuring a creator (creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, Node 20+ and the Remotion renderer the setup skill installs; internet for captures. Optional Modal, gh or AWS account for cloud renders. Runs from the full ai-editor plugin folder (uses its lib/ and remotion/).
---

# Style edit

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows (asking, looking real, motion, story and framing, privacy, cost).

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

An approved cut and a creator's style in. The finished video out: captions, zooms, real captures and
motion scenes timed to the words, in that creator's look and the user's brand. The user approves
the stills sheet (step 5) and picks where to render (step 6).

Paths are relative to the folder Claude Code was started in. Run the scripts with `python3` on Mac
and Linux, `py` on Windows. `S="${CLAUDE_SKILL_DIR}/scripts"`,
`VPY="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py"`; `python3 "$VPY"` is the venv Python.

```
edits/<name>/cut.mp4 + cut.transcript.json + words.json       (the cut skill)
edits/<name>/style.json                                       (start: the profile's creators blended)
  or creator-teardowns/<handle>/style.json                    (one creator, from creator-teardown)
~/.ai-video-editor/profile.json                               (start: brand kit, names, assets, avoid, sound)
captions.json -> beats.json -> visuals.json -> images/ + images.json -> plan.json -> stills/sheet.png -> render.mp4
```

References, read only when a step says: `references/visuals.md` (each format in detail),
`references/plan.md` (plan.py, cutout, sound, music, checks), `references/motion.md` (templates,
transitions, marks), `references/render.md` (targets, live preview, export), `references/review.md`
(the review page), `references/ai-tells.md` (the banned AI looks). `references/contracts.md` (every file's shape) is for people: never read it.

## 0. Read the taste and profile

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show --edit edits/<name>
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" show
```

Follow every taste rule; the scripts read the settings themselves. When the user reacts to a result
("too slow", "captions too small"), save it with the taste skill before redoing the edit.

## 1. Check the inputs

- **No cut.mp4?** Run the cut skill first. Never style a raw take. **`prep-decisions.json`?** The
  `visual-prep` agent did steps 1-3: `references/plan.md` "Prepared while the cut was reviewed".
- **No style.json?** `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" style edits/<name>`.
  With no creators in the profile (or no profile) it writes the default style: a smooth zoom move
  at least every 5 s, 3-word captions (`references/plan.md` "No creator"). If it stops with
  `no creator style.json found`, run creator-teardown quick mode for the profile's creators, then
  again. plan.py also plans with the default style when style.json is missing, and says so.
- **The user's images:** everything in the profile's `assets_dir` that fits a line, plus anything
  they hand over, goes in `edits/<name>/images/` and `images.json`:
  `[{"src": "images/dashboard.png", "word": "dashboard", "nth": 1}]` (optional `layout`, `hold_s`,
  `entrance`; transparent PNG and Lottie `.json` work).

## 2. Captions text

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts/retakes.py" captions edits/<name>
```

Writes `captions.json` and `captions.txt`: the words heard in the finished cut (the verify step's
`cut.transcript.json`), timed to it, with every word that pass heard differently ("Jeff" for "Jev")
spelled as the approved cut text has it, names spelled as the profile's `names`, and every earlier
`retakes.py fix` applied. It prints each word it changed. Never read either JSON: proofread
`captions.txt`, the file captions are built from. A word still wrong is one command, which fixes
captions.json in place, timings untouched, and is kept in `fixes.json` for every later captions run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts/retakes.py" fix edits/<name> cloud=Claude jiv=Jev
```

Use captions.json from here on.

## 3. Visuals

**Read `references/shapes.md` first**: the visuals.json shape for every pick, the order of what goes
on screen and the rules plan.py enforces.

1. **Propose:** `python3 "$S/route.py" beats edits/<name>` splits captions.json into sentences,
   marks the profile's named things, and with a TypeSafe key Jev picks one route per sentence
   (`none`, `capture:shot|browser|sticker`, `post`, `logo`, `logo_cluster`, `chat`, `terminal`,
   `toasts`, `side_by_side`, `video_card`) into beats.json. No key: null picks, decide them yourself.
2. **Real things first:** write `visuals.json` (`references/shapes.md`): a named product
   or doc becomes a `capture` (with `marks` found by text), a quoted post a `post`, an app an `app`,
   a video a `youtube`, a repo a `github`, a brand in passing a `logo`.
3. **Fill the overlays:** for the overlay picks, write only the props (`references/shapes.md`). Hand it to the `template-filler` agent (haiku) with the full path of `references/shapes.md` when available, else write them. Only
   words and numbers the speaker said. There are no type cards.
4. **Fetch:** `node "$S/capture.mjs" edits/<name>` screenshots, fetches logos, posts, app, YouTube
   and GitHub images into `images/`, hides cookie banners, measures marks. Do not open the images:
   the step 5 stills sheet shows every capture.

Pacing, one rule: a card where a sentence names something real (a product, site, post, person, or a
figure on the page that published it), never two at once; otherwise the speaker carries it. No stretch
without a card over `card_gap_s` (10 s, or twice a copied creator's measured gap); where a longer one names
nothing, never make a visual up: plan.py adds zoom changes (`references/plan.md` "Pacing"). Vertical
captures must read on a phone: give each a `find` (plan.py drops a small one with none).

## 4. Plan

Find the speaker's head first, so no box covers the face, then plan with the style.json from step 1:

```bash
python3 "$VPY" "$S/face.py" edits/<name>
python3 "$S/plan.py" edits/<name>/style.json edits/<name>/captions.json [--aspect 9:16|16:9] [--layout overlay|split]
```

Writes `edits/<name>/plan.json`. Read every warning it prints. What it does (look, contrast, layout,
timing, captions, zooms, a second shape with `--out`): `references/plan.md`.

1. **Music:** unless the profile says `sound.music: false`, ask the music question and lay the bed
   (`references/plan.md` "Music"), then run plan.py again. Sound cues need nothing: plan.py adds them.
2. **Behind the speaker:** if the profile says `"behind": true`, run `matte.py` after the last plan.py run and
   again after any later one (it cuts only new frames); say its `--estimate` first (`references/plan.md`).
3. **Check the plan:**

```bash
python3 "$S/check.py" plan edits/<name> [--plan plan.json] [--style edits/<name>/style.json]
```

Fix every FAIL and plan again. What it FAILs: `references/plan.md`.

## 5. Stills sheet, then wait

```bash
python3 "$S/edit.py" stills edits/<name>
```

The first run installs the renderer (a few minutes, once; say so first). Writes one still per beat and
`stills/sheet.png`, one numbered stills sheet labelled with beat, time and card kind (about 1,600
tokens). Review the sheet; open a single still only to zoom in on a problem it shows.
Fix before showing: a box on the face, a zoom cutting the head, a capture showing the wrong part,
text too small for a phone, anything that looks like a default AI edit (icon tiles, emoji, dark
glass with neon). The `stills-critic` agent can check a sheet.

Show the user the sheet and ask in the question box: **Approve (Recommended)** / **Change something**
/ **Open the live preview** (drag, trim and swap cards in a local page). **Do not render until they
approve.** Notes go into the taste skill, visuals.json or images.json, then plan and stills again.

On **Open the live preview**:

```bash
python3 "$S/preview.py" edits/<name> [--plan plan.json]
```

It waits until they press **Render** in the page (`references/render.md` "The live preview"). Then
read `preview-done.json`, save corrections that are a preference with the taste skill, apply the
overrides with `python3 "$S/preview.py" apply edits/<name> [--plan plan.json]`, and go to step 6.

## 6. Where to render

```bash
python3 "$S/edit.py" estimate edits/<name>
```

Prints `Laptop:`, `Modal:` and two `Other:` lines (GitHub Actions, Lambda) with this video's time and
cost. Ask **one question** for every video, exactly three options in this order, each carrying the
printed numbers, none marked recommended (the one exception: only the user knows their time and money).

1. **Laptop**: its time, free.
2. **Modal**: its time and cost (Modal's Starter plan includes $30 of free credit a month). If the
   line says `Not set up yet`, say so in the description.
3. **Other: GitHub Actions or AWS Lambda**: both `Other:` lines in the description. On this pick, ask
   a second question with the two. GitHub Actions: free, needs `gh` logged in, the footage goes into
   a **private** repo in their account; ask before creating the repo. Lambda: their own AWS account.
   No `cloud_cleanup` in the profile: ask once "Delete the uploaded footage from <GitHub|AWS> after
   rendering?" (Yes (Recommended) / No, keep it there), then `profile.py set cloud_cleanup=true|false`.

Modal picked but not set up: the setup skill's Modal step first. Lambda picked and
`aws sts get-caller-identity` fails: the setup skill's Lambda section first.

## 7. Render and check

```bash
python3 "$S/edit.py" render edits/<name>            # laptop
python3 "$S/edit.py" render edits/<name> --modal    # Modal
python3 "$S/edit.py" render edits/<name> --lambda   # AWS Lambda
python3 "$S/edit.py" render edits/<name> --draft    # laptop, 2/3 size, quick look: render-draft.mp4
```

All but `--draft` write `edits/<name>/render.mp4`. GitHub Actions (`--github`, then `github-push`
and `github-fetch`) and every target's detail: `references/render.md`. Then, before the user sees it:

```bash
python3 "$VPY" "$S/check.py" render edits/<name> [--plan plan.json] [--style edits/<name>/style.json]
```

FAILs go back to the plan or the cut; at most two fix rounds, then show the render with what is
still listed. A caption contrast FAIL: plan again, then render (plan.py reads the check and steps
those pages up). The full list: `references/plan.md`.

A `loudness ... LUFS` WARN is the take's own level, not a fault in the edit. Ask once in the question box:

> Your video plays at <N> LUFS; the apps play speech at about -14, so it will sound <quieter|louder>
> than the videos around it. Change the volume?
> - **Leave my audio as it is (Recommended).** Nothing is touched.
> - **Make it one level louder/quieter.** One gain on the whole track to -14 LUFS, never past a -1 dB
>   peak. No compression, no noise removal: the voice sounds the same, only louder or quieter.

Only on the second answer: `python3 "$S/quality.py" normalize edits/<name>/render.mp4`. It writes
`render-normalized.mp4` beside it; hand over that file.

## 8. Hand over

Hand over on the review page (`references/review.md`), then `serve` and `wait` in the background:
`python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py" edits/<name> round --stage edit --video edits/<name>/render.mp4`
(no page yet: `start`, same flags). Card, caption, zoom notes: plan, stills, render, `round`; cut notes: the cut skill.

## 9. Export to another editor

Only when the user asks to finish it by hand ("open it in Final Cut", "send it to Premiere"):

```bash
python3 "$S/export_nle.py" edits/<name> --to fcpxml|premiere|resolve|capcut|edl|srt|all
```

Writes `edits/<name>/export/`. Moving cards render with alpha first (about 0.7 s a card frame; say
so). Tell the user which file to open and how: `references/render.md` "Export to another editor". 16:9: also offer YouTube chapters (`references/render.md` "YouTube chapters").

## If a script stops

| message | do |
|---|---|
| `no cut.mp4 in ...` (plan.py, face.py) or `cut.mp4 missing` (edit.py) | run the cut skill first |
| `no creator style.json found for the profile's creators` | creator-teardown quick mode, then `profile.py style` again |
| `note: ... style.json not found; planning with the default style` | fine with no creator; `profile.py style edits/<name>` keeps it with the edit |
| `no cut.transcript.json` (retakes.py captions) | run the cut skill's verify step |
| `the split layout is vertical only` | plan again with `--layout overlay` |
| `check.py plan found a FAIL` (edit.py stills) | fix the FAIL in the plan, plan again |
| `... missing (run matte.py)` | run matte.py, then stills or render again |
| `... missing (run sfx.py build, then plan.py)` | do exactly that |
| `no Chrome Headless Shell` (capture.mjs) | `python3 "${CLAUDE_PLUGIN_ROOT}/skills/setup/scripts/setup.py" remotion`, then capture again |
| capture.mjs `failed <kind> '<word>'` | drop that visual or give it another URL; the rest were saved |
| `Modal is not set up on this computer` | the setup skill's Modal step |
| `the GitHub CLI (gh) is missing` / `... is public` | setup's GitHub CLI section / a private repo only |
| `the laptop render failed` | `references/render.md` "If a render stops" |
| `the Modal render failed` / `the render failed. Open <url>` | say so, offer the laptop render |

## Files

- `scripts/`: `route.py` beats, `capture.mjs` captures, `plan.py` plan, `face.py` head, `matte.py`
  cutout, `sfx.py` sound, `check.py` + `quality.py` checks, `sheet.py` stills sheet, `edit.py` stills,
  estimate and render, `preview.py` live preview, `export_nle.py` export, `chapters.py` chapters. Each has a `demo` self-check.
- `${CLAUDE_PLUGIN_ROOT}/agents/template-filler.md` (haiku), `stills-critic.md` (sonnet): the helpers.
- `${CLAUDE_PLUGIN_ROOT}/remotion/`: the renderer, copied to `~/.ai-video-editor/remotion` and refreshed
  on every run. `tests/golden.py` at the repo root: golden frames; `--update` after an intended look change.
