# Backlog

Ranked by value to a first-time user. One item at a time; each lands with a test that fails before
and passes after. Done items move to CHANGELOG.md.

## Now

1. **Skill quality pass.** Every SKILL.md read against PRINCIPLES.md: one decision path, under 250
   lines, references for detail, trigger phrases that fire (claude plugin eval, 3 runs each), no
   step that makes Claude read raw data a script can summarise.

## Next

- Links: creator-teardown lists YouTube creators by @handle only, so a `/channel/UC...` link
  needs the user to read the @name off the channel. Resolve it with yt-dlp (`channel_url` ->
  `uploader_id`) in `links.py route`.
- Links: OneDrive personal share links go through the `api.onedrive.com/v1.0/shares` download
  path, untested live (no public OneDrive sample). Test with a real share; if Microsoft has
  closed it, say "download it in the browser" instead.
- Links: Spotify episodes are DRM for most shows; `links.py` says to paste the Apple Podcasts,
  YouTube or RSS link. Find the RSS feed from the Spotify show name automatically (the Apple
  Podcasts search API is free).

- The matting image on Modal (`matte.py` run_modal) installs numpy, opencv and onnxruntime
  unpinned. Take the versions from requirements.lock.
- creator-teardown on its own (without ai-editor) still prints an unpinned `pip install` fix line
  and suggests `brew upgrade yt-dlp` past 90 days. Point it at the ai-editor bootstrap when present.
- yt-dlp is now pinned, so TikTok and Instagram breakages need a lock refresh: regenerate
  requirements.lock monthly (the command is at the top of the file) and when the weekly CI
  TikTok step goes red.
- Python 3.15: the lock resolves for 3.10+, but faster-whisper's ctranslate2 and onnxruntime ship
  wheels late. Add a CI job on the newest Python to see a gap before users do.

6. Measured cost per video on a real run (needs a TypeSafe key on the test machine).
7. Modal render tested live (needs a Modal login on the test machine).
8. Export opened in DaVinci Resolve (free) to confirm FCPXML positions.
9. Product films: sparse dark sites (fill), desktop captures at 3x, the generated score richer.
10. README rewritten for a beginner around `start`, with the cost table and what each skill does.
11. Smoke test stable under load (one timeout seen in edit.py stills).

## Needs a decision from the maintainer

- Merge `upgrade` into `main` (a pull request with before/after screenshots).
- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped).
