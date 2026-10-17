---
name: style-edit
description: Turns an approved cut into the finished video in a creator's measured style. Takes cut.mp4 from the cut skill plus a style.json (from start or creator-teardown), plans captions and zooms to match the creator, adds visuals timed to the spoken word (the user's own images, real screenshots, posts and logos of what is named, the line marked on the real page; no type cards, stock icons or emoji), shows the stills on the review page for approval, then renders 9:16 or 16:9 with Remotion on the laptop, Modal, GitHub Actions or the user's AWS Lambda, and can export the edit to Final Cut, Premiere, Resolve or CapCut. Use when a cut already exists and the user says "style it", "now add the style", "add captions and zooms", "add my images to the video", "render the edit", "change the captions", "export to Final Cut" or "send it to Premiere". Not for a raw take or a first request to edit a video like a creator (that is start), not for cutting mistakes out (cut), and not for measuring a creator (creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, Node 20+ and the Remotion renderer the setup skill installs; internet for captures. Optional Modal, gh or AWS account for cloud renders. Runs from the full ai-editor plugin folder (uses its lib/ and remotion/).
---

# Style edit

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video follows (where, asking, looking real, motion, story, privacy, cost).

Every question goes in the question box: the AskUserQuestion tool (2-4 options, recommended first). Only in an agent without it, ask numbered questions in text. `Attached images: <paths>` in an answer: Read each first.

An approved cut and a creator's style in (a `skill=` job runs that skill: start step 3).
The finished video out: captions, zooms, real captures and motion scenes timed to the words, in the
creator's look and the user's brand. The user approves the stills on the review page (step 5) and picks the render (step 6).

Paths are relative to the library (PRINCIPLES.md). Run the scripts with `python3` on Mac
and Linux, `py` on Windows. `S="${CLAUDE_SKILL_DIR}/scripts"`,
`VPY="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py"`; `python3 "$VPY"` is the venv Python.

```
edits/<name>/cut.mp4 + cut.transcript.json + words.json       (cut)
edits/<name>/style.json                                       (start: the profile's creators blended)
  or creator-teardowns/<handle>/style.json                    (one creator, from creator-teardown)
~/.ai-video-editor/profile.json                               (start: brand kit, names, assets, avoid, sound)
captions.json -> beats.json -> visuals.json -> images/ + images.json -> plan.json -> stills/sheet.png -> render.mp4
```

References, read only when a step says: `references/visuals.md` (each format in detail),
`references/plan.md` (plan.py, cutout, sound, music, checks), `references/motion.md` (templates,
transitions, marks), `references/render.md` (targets, live preview, export), `references/review.md`
(the review page), `references/ai-tells.md` (the banned AI looks). `references/contracts.md` is for people: never read it.

## 0. Read the taste and profile

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show --edit edits/<name>
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" show
```

Follow every taste rule; the scripts read the settings themselves. When the user reacts to a result
("too slow", "captions too small"), save it with the taste skill before redoing the edit.

## 1. Check the inputs

- **No cut.mp4?** Run the cut skill first, never style a raw take. **`prep-decisions.json`?** The
  `visual-prep` agent did steps 1-3 and the sheet: `references/plan.md` "Prepared while the cut was reviewed".
- **No style.json?** `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" style edits/<name>`.
  With no creators in the profile (or no profile) it writes the default style: a smooth zoom move
  at least every 5 s, 3-word captions (`references/plan.md` "No creator"). If it stops with
  `no creator style.json found`, run creator-teardown quick mode for the profile's creators, then
  again. plan.py also plans with the default style when style.json is missing, and says so.
- **The user's images:** everything in the profile's `assets_dir` that fits a line, plus anything
  they hand over, goes in `edits/<name>/images/` and `images.json`:
  `[{"src": "images/dashboard.png", "word": "dashboard", "nth": 1}]` (optional `layout`, `hold_s`,
  `entrance`; transparent PNG and Lottie `.json` work).
- **The user's b-roll libraries:** from the page, the job's `EDIT/broll.json` (`"auto": true` = Claude decides: use the
  libraries this video fits; `false`: only those listed; no file: none). Asked in chat with no page job, the profile's
  `broll` (`python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/broll.py" list`): pick the one that fits from the transcript
  (the user named one: that one; none fits: skip; two fit equally: ask in the question box). `EDIT/instructions.md`
  (Additional instructions for Claude) can say which folder goes where: follow it. `broll.py sheet <name>` prints numbered contact sheets: look at
  every sheet, copy the clips that show what a line says into `images/` (paths in its `index.json`) and use
  each as a `video_card` on that line. Never a clip that does not match the words.
- **What the user added on the page** (`assets.json`, review.py `wait`'s `assets:` line): first, before any search,
  each on its `say` words, as `agents/visual-prep.md` step 2 says. One not in images.json or visuals.json yet is new.

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

**Read `references/shapes.md` and `references/motion-design.md` first**: each pick's shape and plan.py's
rules, then the default look and motion (built animations over captures, big in the band, one capture a page).

1. **Propose:** `python3 "$S/route.py" beats edits/<name>` splits captions.json into sentences,
   marks the named things (profile, logo-pack) into beats.json. Pick one route per sentence yourself
   (`none`, `capture:shot|browser|sticker`, `post`, `logo`, `logo_cluster`, `chat`, `terminal`,
   `toasts`, `side_by_side`, `video_card`).
2. **Real things first:** write `visuals.json` (`references/shapes.md`): a named product
   or doc becomes a `capture` (with `marks` found by text), a quoted post a `post`, an app an `app`,
   a video a `youtube`, a repo a `github`, a brand in passing a `logo`, an expert's words a clip (`references/visuals.md` "Sourced proof").
3. **Fill the overlays:** for the overlay picks, write only the props (`references/shapes.md`). Hand it to the `template-filler` agent (haiku) with the full path of `references/shapes.md` when available, else write them. Only
   words and numbers the speaker said. There are no type cards.
4. **Fetch:** `node "$S/capture.mjs" edits/<name>` fetches captures, logos, posts into `images/`, marks measured.
5. **Motion:** moving-template beats become bespoke clips (motion skill); a failed clip keeps its card.

Pacing: a copied creator's rate wins. route.py prints her cards a minute, kinds and place in the frame,
and marks that many sentences `want` (named ones first). Give each a card of her kind with a `box` at her
place, clear of the head: the user's own photo, else a capture of the real thing the line is about (page,
profile, post), else their own clip as a `video_card`. Never a made-up or stock picture: a `want` with
nothing real stays empty. Never ask what to show: pick the real capture (their own product's too). No creator: a card only where a line names something real. Never two at once; no
stretch without a card over `card_gap_s` (plan.py adds zooms there, `references/plan.md` "Pacing").
Vertical captures need a `find` to read on a phone. Card edit: `shapes.md`.

## 4. Plan

Find the speaker's head first, so no box covers the face, then plan with step 1's style.json:

```bash
python3 "$VPY" "$S/face.py" edits/<name>
python3 "$S/plan.py" edits/<name>/style.json edits/<name>/captions.json [--aspect 9:16|16:9] [--layout overlay|split|letterbox]
```

Writes `edits/<name>/plan.json`. Read every warning. It ends with the **style check** (`style_check.py`):
each `style:` line is a way the plan differs from the creator. Fix each (style.json, visuals.json,
images.json) and plan again before the stills; what the user changed is already the target.

1. **Music** follows the style unless the user set it (`references/plan.md` "Music"; plan.py lays the creator's bed itself), then plan.py again. Sound cues need nothing: plan.py adds them.
2. **Behind the speaker:** if the profile says `"behind": true`, run `matte.py` after the last plan.py run and
   again after any later one (it cuts only new frames); say its `--estimate` first (`references/plan.md`).
3. **Check the plan:**

```bash
python3 "$S/check.py" plan edits/<name> [--plan plan.json] [--style edits/<name>/style.json]
```

Fix every FAIL and plan again. What it FAILs: `references/plan.md`.

## 5. Stills, checked by you, then straight to the render

The user approved the cut: that approve means make the edit. Never put the stills on the review page and never wait
for a second approve (Max, 2026-10-15: users did not like the frames step).

```bash
python3 "$S/edit.py" stills edits/<name>
```

The first run installs the renderer (a few minutes, once; say so first). Writes one still per beat,
`stills/sheet.png` (labelled with beat, time and card kind). Review the sheet yourself; open a single still only to
zoom in. Fix before rendering: a box on the face, a zoom cutting the head, the wrong part of a capture, text too small
for a phone, a default AI look. `stills-critic` can check it. Then go on to step 6 and render; the user's notes come on
the rendered edit. Moving cards by hand only when the user asks: `references/render.md` "The live preview".

## 6. Where to render

```bash
python3 "$S/edit.py" estimate edits/<name>
```

Prints `Laptop:`, `Modal:` and two `Other:` lines (GitHub Actions, Lambda) with this video's time and
cost, then `Recommended:`: Modal once it is connected, the video is over a minute and Modal is quicker; the
laptop otherwise. `render` in the profile, or `Recommended: Laptop`: render there with no question, one line
with the time ("Rendering on your laptop, about 14 s. Say 'render on Modal' to change"). Not set and
`Recommended: Modal`: ask once, three options in this order with the printed numbers, Modal marked
(Recommended), then `profile.py set render='"laptop|modal|github|lambda"'`.

1. **Laptop**: its time, free.
2. **Modal**: its time and cost ($30 free credit a month). Not connected: label it **Connect Modal**; on that
   pick run `setup.py modal-connect` in the background (the setup skill's Modal step), then render on Modal.
3. **Other: GitHub Actions or AWS Lambda**: both `Other:` lines in the description. On this pick, ask
   a second question with the two. GitHub Actions: free, needs `gh` logged in, the footage goes into
   a **private** repo in their account; ask before creating the repo. Lambda: their own AWS account.
   No `cloud_cleanup` in the profile: ask once "Delete the uploaded footage from <GitHub|AWS> after
   rendering?" (Yes (Recommended) / No, keep it there), then `profile.py set cloud_cleanup=true|false`.

Modal picked but not connected: `setup.py modal-connect` first (above). Lambda picked and
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

A `loudness ... LUFS` or take's own `true peak` WARN is the take's level, not a fault in the edit. `loudness`
in the profile: do that, no question. Not set: ask once, then `profile.py set loudness='"leave|normalize"'`:

> Your video is quieter than most reels. Make it as loud as Instagram and TikTok expect? (louder: "...louder than most reels. Bring it down to what they expect?") Details: <N> LUFS; the apps play speech at about -14.
> - **Leave my audio as it is (Recommended).** Nothing is touched.
> - **Make it as loud as the apps expect** (or **Bring it down**). One volume change, never past a -1 dB peak.

Numbers only on the Details line. Check output (FAIL, WARN, "2 frames short") never reaches the user.

Only on the second answer: `python3 "$S/quality.py" normalize edits/<name>/render.mp4`. It writes
`render-normalized.mp4` beside it; hand over that file.

## 8. Hand over

Hand over on the review page (`references/review.md`), `serve` and `wait` in the background:
`python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py" edits/<name> round --stage edit --video edits/<name>/render.mp4`
(no page: `start`, same flags). On `APPROVE`: motion skill `save`. Card and visual changes later: overlays skill (a motion clip: motion skill `note`); caption, zoom: plan, stills, render, `round`; cut: cut skill.

## 9. Export to another editor

Only when the user asks to finish it by hand ("open it in Final Cut", "send it to Premiere"):

```bash
python3 "$S/export_nle.py" edits/<name> --to fcpxml|premiere|resolve|capcut|edl|srt|all
```

Writes `edits/<name>/export/`. Moving cards render with alpha first (about 0.7 s a card frame; say so).
Which file to open, YouTube chapters for 16:9: `references/render.md` "Export to another editor".

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

- `scripts/`: one script per step above, each with a `demo` self-check.
- `${CLAUDE_PLUGIN_ROOT}/agents/template-filler.md` (haiku), `stills-critic.md` (sonnet): the helpers.
- `${CLAUDE_PLUGIN_ROOT}/remotion/`: the renderer, copied to `~/.ai-video-editor/remotion` on every run.
