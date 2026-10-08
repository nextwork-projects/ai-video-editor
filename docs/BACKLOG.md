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
- 2026-10-07 (third pass): a fresh `AI_EDITOR_HOME`, `setup.py bootstrap` then doctor; the sample
  take through start (no creator, every recommended answer, so `behind` on), cut and style-edit to
  stills, a laptop render and `check.py render`, following each SKILL.md literally with no keys;
  `links.py classify` and `route` on one public example of each README link type (a public agency's
  and a public open-source project's links; Instagram, Dropbox and iCloud as made-up shapes, no
  public sample found); a read of every SKILL.md and agent against today's changes. Times on the test
  laptop (uv and npm caches warm, so venv and npm are faster than a new user's): bootstrap 75 s
  (packages 8 s, models 53 s, renderer 13 s), 1.49 GB; doctor 0.7 s; sample download 7.6 s; matte
  model 16.5 s; transcribe 51.5 s; build dry run 0.5 s; cut render 13.9 s; verify 8.1 s; captures
  6.2 s; face 1.3 s; plan 1.9 s; matte 29 s (run twice); stills 16 s; estimate 6.2 s (said laptop
  75 s); laptop render 45 s; `check.py render` 22 s. Paid spend: none.

## Now

(empty: the next item comes from Next)

## Next

- Laptop render estimate on a fresh home's first benchmark. The benchmark now times Chrome's start-up
  apart; 3 of 4 back-to-back estimate/render pairs on the 44.9 s sample cut were within 25%, the fourth 57%
  under (load average 20-37 from other work on the test machine). The cold first benchmark the item was
  about (75 s quoted, 45 s rendered) was not reproduced: caches were warm. Done: on an idle machine and a
  new AI_EDITOR_HOME with an empty renderer cache, the first estimate within 25% of the render. The Modal
  $0.03 for the sample cut is Modal's rates times container time, not yet checked on the bill.

- Teardown graphics miss most titles on slow-drift videos. Measured on two public ones (a
  colourised-stills documentary, 16 titles; generated stills, 4 titles): recall 0.00 and 0.25,
  precision 0.00 and 0.05, with 19-22 false finds each. Causes, largest first: look.py marks the
  documentary's titles as captions (no transcript, titles 1.3-1.7 s), so the caption band hides
  them; `drift_dets` needs lettering held still for +-1 s, longer than those titles; thin
  lettering with no ground over a busy picture (3 of 4 generated-stills titles) never forms a
  still-edge box; tracks from the moving-footage test pick up photo borders on a black ground
  while the photo colourises (most of the false finds).

Carried over (still untested live):
- Links: OneDrive personal share links go through the `api.onedrive.com/v1.0/shares` download
  path, untested live (no public OneDrive sample). Test with a real share; if Microsoft has
  closed it, say "download it in the browser" instead.
- Measured cost per video on a real run (needs a TypeSafe key on the test machine).
- Export opened in DaVinci Resolve (free) to confirm FCPXML positions.

## Needs a decision from the maintainer

- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped). intake.md lists
  **Yes** first for "Let graphics sit behind you?", so a user who accepts every recommended answer
  downloads it (16.5 s, third pass).
