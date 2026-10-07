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

(empty: the next item comes from Next)

## Next

Cut:
- Whisper can fold a whole spoken repeat into one stretched label: on the sample, "and to break down
  competitor ads and" (117.7-119.4 s) sits inside "content" (117.07-119.01 s), so no span can quote it and
  only verify sees it ("SURVIVED"). Fitting the label (build_timeline) does not recover the words. Test: a
  label fitted over more audio than its word holds is listed for a re-transcription of that stretch.
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
