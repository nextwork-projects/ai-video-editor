# Plan detail

Moved out of SKILL.md step 4. Read the section the step points at.

## Contents
- What plan.py does
- Behind the speaker (the cutout)
- Sound cues
- Music
- What the checks FAIL and WARN

## What plan.py does

- **Anti-generic** first: stock captures and icon-only cards are skipped, emoji stripped, the AI
  default look (purple-blue, glass with neon, Inter) replaced. Read every warning.
- **Look** (motion.md): the profile's brand kit > the creator's measured palette and fonts >
  `editorial`. **Motion personality** from the creator's median shot (punchy, snappy, smooth, calm).
- **Caption contrast:** each caption page is measured on the cut behind it. Where the creator's
  look would read under 3:1, that page gets a soft shadow, then a thin stroke, then a backing,
  whichever is first to reach 3:1 (printed per caption).
- **Layout per card:** overlay first: every card floats over the footage in the free space round
  the head; a beat asking for `"layout": "scene"` gets a full-frame cut-away with a designed
  transition; logos, arrow callouts and caption pages stay boxes. There are no type cards. A beat's
  `layout` overrides, except that an explaining card on vertical is never a box. `--layout overlay`
  never opens the panel.
- **Timing:** each card lands 0.1 s before its word; every part, bar, item and capture mark lands on
  its own word (`word` / `at_word`); a caption_page gets the words said while it is up.
- **Captions:** `words_per_caption` at a time, never held 0.3 s past the last word, the stressed
  word of a line marked; the creator's effect, sizes and colours passed through.
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
~/.ai-video-editor/venv/bin/python "$S/matte.py" edits/<name> [--plan plan.json] [--modal]
```

It writes `edits/<name>/cutout/<range>/` (RGBA PNGs, about 0.5 MB a frame) and the plan's
`cutouts`, then prints, per card, how much of its key region the speaker covers and that the face
is solid. On a `WARNING`, shrink or move that card. Laptop CPU: about 0.2-0.5 s a frame (free).
`--modal` runs each range on its own Modal CPU container (8 cores; about $0.00003 a frame at
Modal's rates, about $0.06 per minute of behind-card time, not yet measured). Say the time or cost
before running it. `check.py plan` FAILs a behind card with no cutout. Re-run matte.py after every
plan.py run; ranges already cut are reused.

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
~/.ai-video-editor/venv/bin/python "$S/sfx.py" music edits/<name> [--track audio/track.wav] [--mood linear] [--under-db 18]
```

`.sfx/music.wav`: the track, or a bed generated for this cut's length (product-video sound.py,
nothing to licence), set `--under-db` under the speech in the gaps (default: the copied creator's
measured `sound.music.level_db`, else 18), ducked 9 dB more under every word, faded out over the
last 2 s. plan.py picks it up as plan.json `"music"`; run plan.py after it.

## What the checks FAIL and WARN

`check.py plan` (instant; `edit.py stills` runs it first and stops on a FAIL): FAILs a box under
the app's UI or on the head, an off-centre vertical card, captions outside the safe band or held
too long, text-card text under 34 px, a behind card with no cutout. WARNs long stretches with
nothing moving.

`check.py render` (runs `quality.py` too; results in `check.json`): FAILs a render older than its
plan or inputs (never show one), a card on the face, a card off centre, a silence inside the speech,
a tiny kept span, frozen frames, a first-frame flash, a card landing over 0.15 s late, text into a
card's edge, contrast under 3:1, a caption touching the frame's side, true peak over 0 dBTP, SFX
louder than the voice. WARNs: early landings, one-frame pops, jitter, long static stretches, rhythm
outside 0.5-2x the creator's, contrast under 4.5:1, loudness outside -23 to -9 LUFS, and the AI
default look (a dark panel with one neon colour, a blue-purple gradient, emoji, more than 3 stock
icons in a card or more stock icons than real images).
