# Backlog

Ranked by value to a first-time user. One item at a time; each lands with a test that fails before
and passes after. Done items move to CHANGELOG.md.

Source of the 2026-10-07 items: a new-user run with an empty `AI_EDITOR_HOME`, no API keys, the
sample take through start, cut and style-edit to a laptop render and `check.py render`, plus one
creator profile (teardown, `--top 3`), one 20-minute public talk (clips, candidates only) and one
public website (product-video, brief to animatic).

## Now

(empty: the next items move up from Next.)

## Next

- Alternate hooks recorded after the call to action: the sample take ends with two more takes of the
  opening line (186-199 s). `retake-detection.md` says "the last take wins", which would move the
  hook to the end; there is no rule for it and `candidates.md` flags it as a plain retake.
- README troubleshooting gives `python3 plugins/ai-editor/...` paths, which exist only for Way 1
  (the cloned folder), not for a Way 2 plugin install.
- The sample take is quiet (-24.6 LUFS), so every first render WARNs on loudness with no fix offered.
- doctor's key lines say "Run in a terminal: ... setkey", while setup SKILL.md saves keys from the
  clipboard. One instruction.
- Links: OneDrive personal share links go through the `api.onedrive.com/v1.0/shares` download
  path, untested live (no public OneDrive sample). Test with a real share; if Microsoft has
  closed it, say "download it in the browser" instead.
- Measured cost per video on a real run (needs a TypeSafe key on the test machine).
- Modal render tested live (needs a Modal login on the test machine).
- Export opened in DaVinci Resolve (free) to confirm FCPXML positions.

## Needs a decision from the maintainer

- Merge `upgrade` into `main` (a pull request with before/after screenshots).
- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped).
