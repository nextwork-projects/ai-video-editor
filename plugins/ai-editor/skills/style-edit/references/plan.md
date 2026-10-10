# Plan detail

Moved out of SKILL.md step 4. Read the section the step points at.

## Contents
- Prepared while the cut was reviewed
- No creator: the default style
- What plan.py does
- Behind the speaker (the cutout)
- Sound cues
- Music
- What the checks FAIL and WARN

## Prepared while the cut was reviewed

Called by start for a whole edit, the cut skill starts the `visual-prep` agent as the cut page opens.
It does steps 1-3 and `face.py` on the first cut and copies its `decisions.json` to
`prep-decisions.json`. Every visual it writes names a word and which time it is said (`nth`), never a
second. It plans, renders and uploads nothing; its one bill is the step 3 Jev call (a fraction of a
cent).

Wait for its JSON if it is still running. Cut approved unchanged: go to step 4. Cut changed after notes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts/retakes.py" remap edits/<name>
python3 "${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts/retakes.py" captions edits/<name>
python3 "$S/route.py" beats edits/<name>
python3 "$VPY" "$S/face.py" edits/<name>
```

`remap` re-points each beat in visuals.json and images.json to the new cut and prints the ones it
dropped because their word was cut. Add a beat (step 3) for a line the re-cut brought back that names
something real, then run `capture.mjs` again (it keeps files already fetched). Captures and logos do
not change with the cut. Then step 4.

## No creator: the default style

No creator named is the recommended answer, so it has a style of its own: `DEFAULT_STYLE` in
`lib/ai_editor/profile.py`, which `profile.py style edits/<name>` writes when the profile has no
creators and plan.py uses when style.json is missing or empty. It follows PRINCIPLES.md (smooth,
overlay-first) and takes each number from the median of the measured styles the editor was built
against:

| part | default | measured (3 styles) |
|---|---|---|
| zooms | push to 1.18, eased 0.8 s each way (sine.inOut, PRINCIPLES "Smooth before varied"), on sentence starts, 9.5 a minute | punch in all three; 1.18 / 1.18 / 1.2; 6 / 9.5 / 10 a minute |
| long sentences | a zoom change on the word nearest the middle of any stretch over 5 s (`zoom.max_hold_s`) | (the render check WARNs at 6 s with nothing moving) |
| motion | `smooth` personality, median shot 2.4 s | 2.4 / 2.4 / 3.98 s |
| captions | 3 words, 5.5% type, y 66%, lower case, weight 800, white, no stroke (plan.py adds one where the footage needs it) | 1 / 3 / 3 words; 4.7 / 5.5 / 6.5%; y 62 / 66 / 75% |

A slow push (0.8 s) was tried first: on a talking head the render check read the speaker's own
movement during the push as a surge. The profile's caption and sound answers lay over the default
as over a creator's style. Cards still come from visuals.json (step 3).

## What plan.py does

- **Anti-generic** first: stock captures and icon-only cards are skipped, emoji stripped, the AI
  default look (purple-blue, glass with neon, Inter) replaced. Read every warning.
- **Look** (motion.md): the profile's brand kit > the creator's measured palette and fonts >
  `editorial`. **Motion personality** from the creator's median shot (punchy, snappy, smooth, calm).
- **Caption contrast:** each caption page is measured on the cut behind it. Where the creator's
  look would read under 4.7:1 (`CONTRAST_TARGET`: the render check's 4.5:1 WARN line plus 0.2, since
  the plan's estimate runs a little above what the render check reads), that page gets a soft
  shadow, then a thin stroke, then a backing, whichever is first to reach 4.7:1 (printed per
  caption). After a render, `check.py render` lists the pages it read under 4.7:1 in `check.json`;
  the next plan.py run gives each one the next step and keeps it in `contrast.json`.
- **Layout per card:** overlay first: every card floats over the footage in the free space round
  the head; a beat asking for `"layout": "scene"` gets a full-frame cut-away with a designed
  transition; logos, arrow callouts and caption pages stay boxes. There are no type cards. A beat's
  `layout` overrides, except that an explaining card on vertical is never a box. `--layout overlay`
  never opens the panel.
- **Timing:** each card lands 0.1 s before its word, landing as the render check measures it (an
  overlay starts `OVERLAY_LEAD_S` earlier, the time it takes to carry half its ink; both read it); every part, bar, item and capture mark lands on
  its own word (`word` / `at_word`); a caption_page gets the words said while it is up.
- **Captions:** `words_per_caption` at a time, never held 0.3 s past the last word, the stressed
  word of a line marked (the renderer draws it in the emphasis colour and one weight heavier, never
  bigger); each page one line at one size; the creator's effect, sizes and colours passed through.
- **Pacing:** `card_gap_s` (SKILL.md step 3); inside a longer stretch with no card a zoom change at
  least every 5 s, and a warning naming anything said there that could be shown.
- **Zooms:** about `zoom.per_min` a minute, alternating in and out so the frame never creeps.
- **Shape:** the cut's shape unless `--aspect` says otherwise (a wide cut made vertical is
  centre-cropped; a vertical cut made wide sits over a blurred copy). For a second shape or layout,
  `--out edits/<name>/plan-16x9.json`, then pass `--plan plan-16x9.json` to every later command.

## Behind the speaker (the cutout)

When the profile says `"behind": true` (or `plan.py ... --behind on`), shots, stickers, social
posts and logo clusters get `"layer": "behind"`: they draw over the footage and under a cutout of
the speaker, and a card above the head grows down behind the hair while its marked words stay
clear of the head. Overlay layout only. Then cut the speaker out where those cards are up:

```bash
python3 "$VPY" "$S/matte.py" edits/<name> [--plan plan.json] [--modal]
```

It writes `edits/<name>/cutout/<size>-<key>/` (RGBA PNGs named by their frame of the cut, about
0.5 MB a frame; the key changes with cut.mp4) and the plan's `cutouts`, then prints, per card, how much of its key region the speaker covers and that the face
is solid. On a `WARNING`, shrink or move that card. Laptop CPU: about 0.2-0.5 s a frame (free).
`--modal` runs each range on its own Modal CPU container (8 cores). The estimate is Modal's listed
rates times the laptop's 0.26 s a frame: about $0.00003 a frame, $0.06 per minute of behind-card time;
the run then prints the cost from the containers' own run time. `--estimate` prints
the frames to cut, the time and the cost, and stops: say them before running it. A frame already
cut is never cut again, and plan.py keeps every cutout whose frames are all there, so a re-plan that
moves nothing needs no matte run and one that moves a card cuts only the frames it adds. `check.py
plan` FAILs a behind card with no cutout and prints the matte.py command to run.

## Sound cues

`plan.py` adds a few cues: a whoosh when a card slides in, a pop when a sticker, part or logo
pops in, a soft hit for a scene's tag, a punch on a zoom; cards that scale or fade in land silent.
Never two within 0.25 s, never the same cue twice running, about one per 5 s, each started early by
its attack. `scripts/sfx.py` synthesises the kit from a fixed seed into `edits/<name>/.sfx/`
(nothing to licence), set about 4 dB under the speech. No sound: the profile's `sound.sfx: false`,
`"sfx": false` in style.json, or `plan.py ... --no-sfx`. A copied creator's measured `sound` (cues a
minute, kinds) sets the budget and the cues (visuals.md "From the teardown").

## Music

Unless the profile says `sound.music: false`, ask once in the question box: **Generated for this
cut (Recommended)** / **Your own track** (a file) / **A YouTube link** (or any link yt-dlp reads) /
**None**. For a link, ask for an optional start and end, then who holds the rights: "It's my own
track" / "YouTube Audio Library or Creative Commons (I'll credit it)" / "Licensed (Epidemic, Artlist
etc.)" / "Not sure". Then:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/product-video/scripts/product.py" music edits/<name> --url '<link>' \
  [--start S --end S] --rights own|cc|licensed|unsure [--credit '...']
```

It writes `audio/track.wav` and `audio/MUSIC-LICENSE.md`; the download never leaves the edit folder.
On "Not sure", warn that platforms may mute or claim the video and offer the generated option. Then
lay the bed under the voice (a file of their own: copy it into the edit folder and pass it as
`--track`):

```bash
python3 "$VPY" "$S/sfx.py" music edits/<name> [--track audio/track.wav] [--mood linear] [--under-db 18]
```

`.sfx/music.wav`: the track, or a bed generated for this cut's length (product-video sound.py,
nothing to licence), set `--under-db` under the speech in the gaps (default: the copied creator's
measured `sound.music.level_db`, else 18), ducked 9 dB more under every word, faded out over the
last 2 s. plan.py picks it up as plan.json `"music"`; run plan.py after it.

## What the checks FAIL and WARN

`check.py plan` (instant; `edit.py stills` runs it first and stops on a FAIL): FAILs a box under
the app's UI or on the head, an off-centre vertical card, captions outside the safe band or held
too long, text-card text under 34 px, a behind card with no cutout, and a vertical `flow` or
`logo_cluster` that would draw under 60% of the width or off centre (the renderer's layout, estimated
from the plan, so the render check never FAILs what this passed), a sticker showing text under 28 px
x-height beside its evidence, and a capture on the hook (first 3 s) with no `find` mark. WARNs long
stretches with nothing moving, and a stretch with no card over `card_gap_s` that names something
(beats.json) or holds still over 5 s (SKILL.md step 3 "Pacing").

`check.py render` (runs `quality.py` too; results in `check.json`): FAILs a render older than its
plan or inputs (never show one), a card on the face, a card off centre (a `flow` or `logo_cluster`
also under 60% of the width; the fix is in the plan), a silence inside the speech,
a tiny kept span, frozen frames, a first-frame flash, a caption page drawn on more lines than
`max_lines` (1: one line at one size), a card landing over 0.15 s late, text into a
card's edge, contrast under 3:1, a caption touching the frame's side, true peak over 0 dBTP, SFX
louder than the voice. WARNs: early landings, one-frame pops, jitter, long static stretches, rhythm
outside 0.5-2x the creator's, contrast under 4.5:1, loudness outside -23 to -9 LUFS, and the AI
default look (a dark panel with one neon colour, a blue-purple gradient, emoji, more than 3 stock
icons in a card or more stock icons than real images).
