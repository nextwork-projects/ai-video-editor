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

1. **Skills fan out to subagents where work is independent** (faster, smaller main context): per-video teardown analysis, per-flow product captures/recordings, per-capture style-edit captures, per-candidate clip scoring, per-hook variant renders. Each worker is a plugin agent (haiku where the job is mechanical) returning a short JSON summary. Test: an eval or a dry run that shows the skill launching the workers in one message, and wall time measured before/after on the sample.

(empty: the next item comes from Next)

## Next

Skill wording:
- cut step 0 says ask "even if they said 'edit my video like @creator'", which routes to start.
- cut and clips use `python3` with no "`py` on Windows" line.
- product-video brief: 11 questions over three calls; ask call 1, default the rest in one confirm.
- `edit.py:43` copies the renderer with `dirs_exist_ok`, so deleted components stay in the user's copy.

Privacy and safety:
- `taste.py scrub` does not remove `profile.names` or bare domains before a public issue.
- `setkey` from the clipboard sends any token-shaped text to the vendor; check the prefix first.

Windows and Linux:
- The apt Node fix line pipes NodeSource's remote script to `sudo bash` (Debian and Ubuntu ship a Node
  older than 20). Flatpak Chromium is not found (no plain binary).
- clips on Windows copies a multi-GB source instead of linking.

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
