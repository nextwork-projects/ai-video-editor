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

- Teardown graphics miss most titles on slow-drift videos. Measured on two public ones (a
  colourised-stills documentary, 16 titles; generated stills, 4 titles): recall 0.00 and 0.25,
  precision 0.00 and 0.05, with 19-22 false finds each. Causes, largest first: look.py marks the
  documentary's titles as captions (no transcript, titles 1.3-1.7 s), so the caption band hides
  them; `drift_dets` needs lettering held still for +-1 s, longer than those titles; thin
  lettering with no ground over a busy picture (3 of 4 generated-stills titles) never forms a
  still-edge box; tracks from the moving-footage test pick up photo borders on a black ground
  while the photo colourises (most of the false finds).

- Modal: the hedge (a second copy of a piece still running at 2x the median) ran live only on a
  stand-in function; no sample-take render has hit a slow container since it shipped. The estimate
  counts the whole upload even when Modal already holds the footage (a re-render uploads in 3-4 s).

Carried over (still untested live):
- Links: OneDrive personal share links go through the `api.onedrive.com/v1.0/shares` download
  path, untested live (no public OneDrive sample). Test with a real share; if Microsoft has
  closed it, say "download it in the browser" instead.
- Measured cost per video on a real run (needs a TypeSafe key on the test machine).
- Export opened in DaVinci Resolve (free) to confirm FCPXML positions.

## Needs a decision from the maintainer

- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped).
