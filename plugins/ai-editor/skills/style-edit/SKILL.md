---
name: style-edit
description: Edits the user's cut video in a creator's measured style. Takes cut.mp4 and words.json from the cut skill plus a creator's style.json from creator-teardown, plans the captions and zooms to match that creator, adds its own visuals timed to the spoken word (the user's own images, real screenshots, posts and logos of what is named, the line marked on the real page; no type cards, stock icons or emoji), shows stills for approval, then renders the finished video with Remotion on the laptop, on Modal (cloud), on GitHub Actions (free, in a private repo) or on the user's own AWS Lambda. Output is 9:16 or 16:9. Use when the user says "edit this in the style of @creator", "make it look like <creator>'s videos", "add captions and zooms", "style my video", "add my images to the video", "render the edit", or has a cut and a style.json and wants the finished video. Runs after cut. Not for cutting mistakes out (that is cut) and not for measuring a creator (that is creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, Node 20+ and the Remotion renderer the setup skill installs; internet for captures. Optional Modal, gh or AWS account for cloud renders. Runs from the full ai-editor plugin folder (uses its lib/ and remotion/).
---

# Style edit

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows (asking, looking real, motion, story and framing, privacy, cost).

A cut video and a creator's style in. The finished edit out: captions, zooms, real captures and
motion scenes timed to the words, in that creator's look and the user's brand.

Paths are relative to the folder Claude Code was started in. File shapes:
`references/contracts.md`; templates, look, transitions and marks: `references/motion.md`; what to
put on screen: `references/visuals.md`. Run the scripts with `python3` on Mac and Linux, `py` on Windows.
`S="${CLAUDE_SKILL_DIR}/scripts"`.

```
edits/<name>/cut.mp4 + captions.json        (from the cut skill)
edits/<name>/style.json                     (start skill: the profile's creators blended)
  or creator-teardowns/<handle>/style.json  (one creator, from creator-teardown)
~/.ai-video-editor/profile.json             (start skill: brand kit, names, assets, avoid, sound)
edits/<name>/beats.json -> visuals.json -> images/ + images.json -> plan.json -> stills/ -> render.mp4
```

## 0. Read the user's taste and profile

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" show
```

Follow every taste rule; the scripts already read the settings. When the user reacts to the result
("too slow", "captions too small"), save it with the taste skill before redoing the edit. No
profile yet and the user wants more than a quick edit: run the `start` skill's intake first.

## 1. Check the inputs

- **No style.json?** With a profile: `profile.py style edits/<name>`. Without: ask which creator and
  run creator-teardown in quick mode first. No creator at all is fine: the editorial defaults.
- **No cut.mp4 or captions?** Run the cut skill first.
- **The user's images:** everything in the profile's `assets_dir` that fits a line, plus anything
  they hand over, goes in `edits/<name>/images/` and `images.json`:
  `[{"src": "images/dashboard.png", "word": "dashboard", "nth": 1}]` (optional `layout`, `hold_s`,
  `entrance`; transparent PNG and Lottie `.json` work).

## 2. Captions text

Copy `edits/<name>/cut.transcript.json` (the verify step's transcript of the finished cut) to
`captions.json` and proofread it. Fix only `text`, never times: names the transcriber misheard
(use the profile's `names`), fillers heard as words (delete them). Use captions.json from here on.

## 3. Visuals

**Read `references/visuals.md` first.** The anti-generic rules and the order of what goes on screen
are there; plan.py enforces them.

1. **Propose:** `python3 "$S/route.py" beats edits/<name>` splits the transcript into sentences,
   marks the profile's named things, and with a TypeSafe key Jev picks one route per sentence
   (`none`, `capture:shot|browser|sticker`, `post`, `logo`, `logo_cluster`, `chat`, `terminal`,
   `toasts`, `side_by_side`, `video_card`) into beats.json. Without a key the picks are null: decide them yourself from the same file. Most
   sentences get nothing.
2. **Real things first:** a named product or doc becomes a `capture` (with `marks` found by text),
   a quoted post a `post`, an app an `app`, a video a `youtube`, a repo a `github`, a brand in
   passing a `logo`.
3. **Fill the overlays:** for the overlay picks, write only the props (visuals.md "Template-filler
   contract"). Hand it to the `template-filler` agent (haiku) when available, else write them. Only
   words and numbers the speaker said. There are no type cards.
4. **Fetch:** `node "$S/capture.mjs" edits/<name>` screenshots, fetches logos, posts, app, YouTube
   and GitHub images into `images/`, hides cookie banners, measures marks. Look at every capture.

Pacing: about one card every 4-6 s, never two at once, and leave the speaker alone between runs of
scenes. On vertical every explaining card is a full-frame scene (or sits in the split panel),
never a small box over the face.

## 4. Plan

Find the speaker's head first, so no box covers the face and scenes open from it:

```bash
~/.ai-video-editor/venv/bin/python "$S/face.py" edits/<name>   # Windows: Scripts\python.exe
python3 "$S/plan.py" edits/<name>/style.json edits/<name>/captions.json  [--aspect 9:16|16:9] [--layout overlay|split]
```

Writes `edits/<name>/plan.json`, the cut's shape unless `--aspect` says otherwise (a wide cut made
vertical is centre-cropped; a vertical cut made wide sits over a blurred copy). For a second shape
or layout, `--out edits/<name>/plan-16x9.json` and pass `--plan plan-16x9.json` below.

What the plan does:
- **Anti-generic** first: stock captures and icon-only cards are skipped, emoji stripped, the AI
  default look (purple-blue, glass with neon, Inter) replaced. Read every warning.
- **Look** (motion.md): the profile's brand kit > the creator's measured palette and fonts >
  `editorial`. **Motion personality** from the creator's median shot (punchy, snappy, smooth, calm).
- **Layout per card:** overlay first: every card floats over the footage in the free space round
  the head; a beat asking for `"layout": "scene"` gets a full-frame cut-away with a designed
  transition; logos, arrow callouts and caption pages stay boxes. There are no type cards. A beat's `layout` overrides, except that an
  explaining card on vertical is never a box. `--layout overlay` never opens the panel.
- **Timing:** each card lands 0.1 s before its word; every part, bar, item and capture mark lands on
  its own word (`word` / `at_word`); a caption_page gets the words said while it is up.
- **Captions:** `words_per_caption` at a time, never held 0.3 s past the last word, the stressed
  word of a line marked; the creator's effect, sizes and colours passed through.
- **Zooms:** about `zoom.per_min` a minute, alternating in and out so the frame never creeps.

### Behind the speaker

When the profile says `"behind": true` (or `plan.py ... --behind on`), shots, stickers, social
posts and logo clusters get `"layer": "behind"`: they draw over the footage and under a cutout of
the speaker, and a card above the head grows down behind the hair while its marked words stay
clear of the head. Overlay layout only. Then cut the speaker out where those cards are up:

```bash
~/.ai-video-editor/venv/bin/python "$S/matte.py" edits/<name> [--plan plan.json] [--modal]
```

It writes `edits/<name>/cutout/<range>/` (RGBA PNGs, about 0.5 MB a frame) and the plan's `cutouts`, then prints, per card,
how much of its key region the speaker covers and that the face is solid. On a WARNING, shrink or
move that card. Laptop CPU: about 0.2-0.5 s a frame (free). `--modal` runs each range on
its own Modal CPU container (8 cores; about $0.00003 a frame at Modal's rates, about $0.06 per minute of behind-card time, not yet measured). Skip this step when the profile says no.
`check.py plan` FAILs a behind card with no cutout. Re-run matte.py after every plan.py run; ranges
already cut are reused.

### Sound

`plan.py` adds a few cues: a whoosh when a card slides in, a pop when a sticker, part or logo
pops in, a soft hit for a scene's tag, a punch on a zoom; cards that scale or fade in land silent.
Never two within 0.25 s, never the same cue twice running, about one per 5 s, each started early by
its attack. `scripts/sfx.py` synthesises the kit from a
fixed seed into `edits/<name>/.sfx/` (nothing to licence), set about 4 dB under the speech. No sound:
the profile's `sound.sfx: false`, `"sfx": false` in style.json, or `plan.py ... --no-sfx`. A copied
creator's measured `sound` (cues a minute, kinds) sets the budget and the cues (references/visuals.md
"From the teardown").

**Music.** Unless the profile says `sound.music: false`, ask once in the question box: **Generated for
this cut (Recommended)** / **Your own track** (a file) / **A YouTube link** (or any link yt-dlp reads) /
**None**. For a link, ask for an optional start and end, then who holds the rights: "It's my own track" /
"YouTube Audio Library or Creative Commons (I'll credit it)" / "Licensed (Epidemic, Artlist etc.)" /
"Not sure". Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/product-video/scripts/product.py" music edits/<name> --url '<link>' \
  [--start S --end S] --rights own|cc|licensed|unsure [--credit '...']
```

It writes `audio/track.wav` and `audio/MUSIC-LICENSE.md`; the download never leaves the edit folder. On
"Not sure", warn that platforms may mute or claim the video and offer the generated option. Then lay the
bed under the voice (a file of their own: copy it into the edit folder and pass it as `--track`):

```bash
~/.ai-video-editor/venv/bin/python "$S/sfx.py" music edits/<name> [--track audio/track.wav] [--mood linear] [--under-db 18]
```

`.sfx/music.wav`: the track, or a bed generated for this cut's length (product-video sound.py, nothing
to licence), set `--under-db` under the speech in the gaps (default: the copied creator's measured
`sound.music.level_db`, else 18), ducked 9 dB more under every word, faded out over the last 2 s.
plan.py picks it up as plan.json `"music"`; run plan.py after it.

### Check the plan

```bash
python3 "$S/check.py" plan edits/<name> [--plan plan-split.json] [--style edits/<name>/style.json]
```

Instant. FAILs a box under the app's UI or on the head, an off-centre vertical card, captions outside
the safe band or held too long, text-card text under 34 px. WARNs long stretches with nothing
moving. Fix every FAIL and plan again. `edit.py stills` runs it first and stops on a FAIL.

## 5. Stills, then wait

```bash
python3 "$S/edit.py" stills edits/<name>
```

The first run installs the renderer (a few minutes, once). Writes one still per beat (opening,
caption, zoom, then each card with early, late and swap frames) and `stills/sheet.png`, one numbered
contact sheet labelled with beat, time and card kind (about 1,600 tokens). Review the sheet; open a
single still only to zoom in. Fix before showing: a box on the face, a zoom cutting the head, a
capture showing the wrong part, text too small for a phone, anything that looks like a default AI
edit (icon tiles, emoji, dark glass with neon). The `stills-critic` agent can check a sheet.

Show the user the sheet. **Do not render until they approve.** Their notes go into the taste
skill, visuals.json or images.json, then plan and stills again.

## 5b. Preview

After the stills are approved, offer the live preview before the render question:

```bash
python3 "$S/preview.py" edits/<name> [--plan plan.json]
```

Opens a local page (no account, works offline) that plays the real edit: the same composition and
props as the render. The user can drag a card in time or trim it, drag it on the frame (it snaps to
the free regions round the head, never onto the face), swap its picture for another in `images/`,
delete it, fix a misheard caption word (empty it to remove it), and nudge a sound cue's level.
Every change is a small diff in `edits/<name>/overrides.json` and a line in `corrections.jsonl`
(what, from, to). The script waits until they press **Render**, which writes
`edits/<name>/preview-done.json` with a summary and stops it.

Then: read preview-done.json, save its corrections with the taste skill where they are a
preference rather than a one-off fix, run `plan.py` again with the same arguments (it applies
overrides.json) or `python3 "$S/preview.py" apply edits/<name> [--plan plan.json]` to apply the
overrides to the existing plan without re-planning, and go to step 6. `preview.py demo` self-checks.

## 6. Laptop, Modal or other

```bash
python3 "$S/edit.py" estimate edits/<name>
```

Prints `Laptop:`, `Modal:` and two `Other:` lines (GitHub Actions, Lambda) with this video's time
and cost. Ask **one question** for every video, in the question box (the AskUserQuestion tool;
numbered text only in an agent without it). Exactly three options in this order, none marked
recommended, each label or description carrying the printed numbers:

1. **Laptop**: its time, free.
2. **Modal**: its time and cost (Modal's Starter plan includes $30 of free credit a month). If the
   line says `Not set up yet`, say so in the description.
3. **Other: GitHub Actions or AWS Lambda**: both `Other:` lines in the description. On this pick,
   ask a second question with the two. GitHub Actions: free, needs `gh` logged in, the footage goes
   into a **private** repo in their account; ask before creating the repo. Lambda: their own AWS
   account; if `aws sts get-caller-identity` fails, the setup skill's Lambda section first.

Modal picked but not set up: run the setup skill's step 5b (Modal) first, then render.

## 7. Render

```bash
python3 "$S/edit.py" render edits/<name>            # laptop
python3 "$S/edit.py" render edits/<name> --modal    # Modal
python3 "$S/edit.py" render edits/<name> --lambda   # AWS Lambda
python3 "$S/edit.py" render edits/<name> --draft    # laptop, 2/3 size, quick look: render-draft.mp4
```

All but `--draft` write `edits/<name>/render.mp4`. A Modal render prints its wall time and cost
when it finishes. GitHub Actions, Lambda, Modal and draft details: `references/render.md`.

### Check the render

```bash
~/.ai-video-editor/venv/bin/python "$S/check.py" render edits/<name> [--plan plan-split.json] [--style edits/<name>/style.json]
```

Before the user sees it. Runs `scripts/quality.py` too. FAILs: a render older than its plan or
inputs (never show one), a card on the face, a card off centre, a silence inside the speech, a tiny
kept span, frozen frames, a first-frame flash, a card landing over 0.15 s late, text into a card's
edge, contrast under 3:1, a caption touching the frame's side, true peak over 0 dBTP, SFX louder
than the voice. WARNs: early landings, one-frame pops, jitter, long static stretches, rhythm
outside 0.5-2x the creator's, contrast under 4.5:1, loudness outside -23 to -9 LUFS, and the AI
default look (a dark panel with one neon colour, a blue-purple gradient, emoji, more than 3 stock
icons in a card or more stock icons than real images). FAILs go back to the plan or the cut; at
most two fix rounds, then show the render with what is still listed. Results: `check.json`.

## 8. Open it

Open the result (`open` on Mac, `start ""` on Windows, `xdg-open` on Linux) and give the full path.
Ask for notes. Caption, zoom, card and visual notes need a new plan and stills, then a render. Notes
about what was cut go back to the cut skill.

## 9. Export to another editor

When the user wants to finish the edit by hand ("open it in Final Cut", "send it to Premiere",
"I want to tweak it in Resolve / CapCut"):

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/export_nle.py" edits/<name> --to fcpxml|premiere|resolve|capcut|edl|srt|all
```

Into `edits/<name>/export/`: the jump cut as trims of the raw take (so every cut can be re-opened),
captions (titles + `.srt`), each card on its own track at its time and place, sound cues on their
own audio track, a marker per beat. Moving cards are rendered with alpha first (about 0.7 s per card
frame on a laptop); `--no-render` skips them. If the raw take moved, pass `--source <file>`. Tell
the user which file to open and how, from `references/render.md` "Export to another editor".

## Files

- `references/visuals.md`: anti-generic rules, what goes on screen in what order, layouts, every
  beat kind, free sources, safe areas.
- `references/motion.md`: templates and props, the look, personalities, transitions, capture marks.
- `references/render.md`: the GitHub Actions and Lambda render steps.
- `references/contracts.md`: the shape of every file the skills hand each other.
- `scripts/route.py`: sentences and Jev route picks into beats.json; `highlight` picks a capture's
  evidence line. `route.py demo` self-checks.
- `scripts/capture.mjs`: visuals.json to screenshots, marks, logos, posts, app, YouTube and GitHub
  images in `images/`. No dependencies.
- `scripts/plan.py`: style + captions (+ images, visuals, face, profile) to plan.json. `plan.py demo`.
- `scripts/sfx.py`: the sound kit, synthesised and level-matched into `.sfx/`. `sfx.py demo`.
- `scripts/face.py`: the speaker's head per 0.5 s into face.json (OpenCV YuNet). `face.py demo`.
- `scripts/matte.py`: the speaker cut out (Robust Video Matting + stabilise + edge unmix) for behind
  cards, RGBA PNG frames into cutout/. `matte.py demo`.
- `scripts/check.py`, `scripts/quality.py`: the plan and render checks. `check.py demo`.
- `scripts/sheet.py`: the numbered stills contact sheet.
- `scripts/edit.py`: stills, estimate and render. `edit.py demo`.
- `scripts/export_nle.py`: the edit as FCPXML, FCP7 XML, EDL, SRT or CapCut steps. `export_nle.py demo`.
- `scripts/preview.py`: the live preview page (`../../preview/`) and overrides.json. `preview.py demo`.
- `../../agents/template-filler.md`: the haiku agent that fills template props from beats.json.
- `../../lib/ai_editor/profile.py`: the profile, the creator blend, the look order.
- `../../remotion/`: the renderer, copied to `~/.ai-video-editor/remotion` and refreshed on every run.
- `../../../../tests/golden.py`: golden frames; `--update` after an intended look change.
