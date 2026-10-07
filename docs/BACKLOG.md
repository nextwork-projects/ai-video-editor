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

- Overlay mode finds nothing when the footage under the graphics barely moves. A public motion-graphics
  explainer (slow-drifting generated stills, cuts every 6 s, 8 hand-labelled one-line titles) scored
  precision 0.00, recall 0.00: `overlay_dets` needs 40% of the frame changing within 0.4 s, and its one
  find was part of the footage. look.py's OCR also returned no line inside 6 of the 8 title boxes, so
  the text tests had nothing to read.

- Teardowns made before `"transitions": []` was written leave the key out for a creator who only cuts,
  so their scenes still get match / iris; re-run visual.py on them. A `cut` scene still starts
  SCENE_LEAD_S (0.3 s x k) before its word, a lead sized for a transition that grows.

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
