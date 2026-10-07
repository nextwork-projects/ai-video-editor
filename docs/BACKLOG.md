# Backlog

Ranked by value to a first-time user. One item at a time; each lands with a test that fails before
and passes after. Done items move to CHANGELOG.md.

Sources:
- 2026-10-07 (first pass): a new-user run with an empty `AI_EDITOR_HOME`, no API keys, the sample
  take through start, cut and style-edit to a laptop render and `check.py render`, plus one creator
  profile (teardown, `--top 3`), one 20-minute public talk (clips, candidates only) and one public
  website (product-video, brief to animatic).
- 2026-10-07 (second pass): the sample take through start (no creator), cut and style-edit with an
  isolated `AI_EDITOR_HOME` and no keys, judged from the stills sheet and a 1 fps strip of the
  render; a read of every SKILL.md, agent and script for wrong turns, platform gaps and privacy.
  Times on the test laptop: transcribe 54 s (205 s take, Whisper small), cut render 22 s, verify
  31 s, captures 7.5 s, face 3.4 s, plan 3.8 s, stills 28 s, laptop render 2.9 min (estimate said
  3.8), `check.py render` 58 s. Paid spend: none.

## Now

1. **Explaining cards on vertical render small and off-centre.** On the sample, the `flow` card
   (28.8-37.8 s) sits in a 21%-tall top band with its content pushed right: `check.py render` FAILs
   it at 37.25 s (+5.6% off centre) while `check.py plan` passed 0 FAIL, and the FAIL's fix points
   the model at `Anims.tsx`. Its `tasks` chips ("small task", "harder") are unreadable at phone size.
   The `logo_cluster` (9.1-11.6 s) is a full-frame box with two logos about 6% of the width at the
   frame edges; the TypeSafe logo is a 256 px Google favicon. The Claude `logo` (22.9-24.1 s) is a
   small mark over the plant, still up on "jev is good". SKILL.md step 3 says explaining cards on
   vertical are full-frame scenes or in the split panel; plan.py placed all four as `box`.
   Test: `check.py plan` on the sample plan FAILs a vertical `flow` or `logo_cluster` whose ink is
   under 60% of the frame width or off centre, and plan.py gives the flow a scene or split layout.

2. **`profile.py style edits/<name>` crashes on a new video.** start step 3 runs it before cut
   creates `edits/<name>/`, and it dies with a `FileNotFoundError` traceback
   (`profile.py:278`). Every first video through start hits it.
   Test: `profile.py style <temp>/edits/new` with no folder exits 0 and writes `style.json`.

3. **Whisper word timings send the cut into a false loop.** On the sample, Whisper times "if" at
   0.7 s and "I" at 3.0 s. `build_timeline.py` reports `CLIPPED by a pause cut: if` at every `--pad`
   (0.12, 0.3), and the paper edit shows the "I" at 179 s as kept after `alt_hook` cut it. Verify
   then says the opposite: "if" SURVIVED, "i" MISSING. cut SKILL.md tells the model to raise
   `--pad` on CLIPPED, so it rebuilds for nothing. The same transcript also hides the alternate
   hooks: `alt_hooks()` found none at 179-199 s (no `hooks.json`, nothing in `candidates.md`),
   because Whisper put the "I" of "I built" into the previous phrase.
   Test: a `test_build_timeline.py` case with one stretched word (start + 3 s) gives no CLIPPED and
   a paper edit that matches the kept words; `test_retakes.py` on the sample's Whisper words finds
   one alternate-hook run from 179 s.

## Next

Output quality (sample render, times in the cut):
- Caption pages mix sizes inside one page and wrap to two lines: "that a lot" and "using right now"
  (4-8 s), "down competitor ads" (16 s), "one-for-one substitute to" (20.5 s), "before a task"
  (28.4 s), "then comment router" (42 s). The stressed-word mark changes the size mid-page.
  Test: no caption page over one line at 3 words; stressed word changes colour or weight, not size.
- The first card is the site's headline as a sticker ("The First (Public) System One Model; ...",
  0.8-3.8 s): lines touch (leading under 1.0) and the kicker above it is unreadable. It is the
  page's marketing line, not what is said, so it reads as a type card. Test: sticker leading 1.1 or
  more, text under 28 px x-height dropped, `find` required for a sticker on the hook.
- 11.6-22.9 s and 37.8-45.8 s have no card; the most showable lines (sorting emails, competitor ads,
  11.4-18.2 s) get nothing. SKILL.md says "about one card every 4-6 s" and "most sentences get
  nothing" in the same step. Pick one rule and have `check.py plan` WARN on a gap over 10 s.
- `check.py plan` passes plans that `check.py render` FAILs (off-centre flow). Move the centring
  measure into the plan check from the template's layout.
- Logo source: prefer the site's apple-touch-icon or og image over the Google favicon service.
- Caption contrast WARN at 20.77 s (4.36:1) after plan.py's contrast pass.

Cut:
- `candidates.md` flags "like" in "models like Claude" as a filler and "a lot of tokens and" vs "a lot
  of money and time" as a retake. Test: neither is a candidate on the sample.
- A rejected TypeSafe key (401) returns exit 4 like "no key", so the model reads the full transcript
  and tells the user a key would help (`retakes.py:631-634`). Give it its own exit and message.
- `transcribe.py run_scribe` catches only HTTPError; a network error is a traceback.

Skill wording:
- `PY`/`VPY` in cut, style-edit, clips, product-video and creator-teardown are hardcoded to
  `~/.ai-video-editor/venv` (ignores `AI_EDITOR_HOME`) and to `%USERPROFILE%\...` on Windows, which
  Git Bash does not expand. Add `setup.py python` that prints the right interpreter; use it everywhere.
- style-edit step 6 says "none marked recommended", against PRINCIPLES.md and every other question.
  Say it is the one exception, or recommend Laptop.
- "No Chrome Headless Shell" advice (style-edit table, `capture.mjs:658`) says run `edit.py stills`,
  which needs a plan that does not exist yet at step 3. Point at `setup.py remotion`.
- `route.py:110` does not catch `JevError`; a bad key or TypeSafe outage is a traceback with no row
  in the table. Fall back to null picks like cut does.
- creator-teardown quick mode says "about a minute per creator"; `look.py` alone is about 40 s a
  video on 7 videos. State the real time, and list the exact commands quick mode runs (it conflicts
  with "always run" in step 3).
- cut step 0 says ask "even if they said 'edit my video like @creator'", which routes to start.
- `agents/template-filler.md` uses `${CLAUDE_PLUGIN_ROOT}`, which may not expand in an agent prompt.
- cut and clips use `python3` with no "`py` on Windows" line.
- product-video brief: 11 questions over three calls; ask call 1, default the rest in one confirm.
- `edit.py:43` copies the renderer with `dirs_exist_ok`, so deleted components stay in the user's copy.

Privacy and safety:
- `taste.py scrub` does not remove `profile.names` or bare domains before a public issue.
- `setkey` from the clipboard sends any token-shaped text to the vendor; check the prefix first.

Windows and Linux:
- `login.mjs:22-27` finds Chrome only at fixed paths: no PATH lookup, no Edge on Windows, no snap or
  flatpak Chromium. `check()` then spawns null with no message.
- setup and creator-teardown Linux fixes are apt-only; the Node line pipes a remote script to
  `sudo bash`.
- `render.py:111` concat list breaks on a `'` in the temp path.
- clips on Windows copies a multi-GB source instead of linking.

Setup:
- `setup.py doctor` says FIX "installed before version pins" for a working install with no
  `env.json` and sends the user to `repair` (a full reinstall). Write `env.json` from what is
  installed when it already matches the lock.

Carried over (still untested live):
- Links: OneDrive personal share links go through the `api.onedrive.com/v1.0/shares` download
  path, untested live (no public OneDrive sample). Test with a real share; if Microsoft has
  closed it, say "download it in the browser" instead.
- Measured cost per video on a real run (needs a TypeSafe key on the test machine).
- Modal render tested live (needs a Modal login; doctor still says "installed, not logged in").
- Export opened in DaVinci Resolve (free) to confirm FCPXML positions.

## Needs a decision from the maintainer

- Merge `upgrade` into `main`: the pull request with before/after screenshots is being opened.
- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped).
