# Backlog

Ranked by value to a first-time user. One item at a time; each lands with a test that fails before
and passes after. Done items move to CHANGELOG.md.

## Now

1. **Fresh install, reproducible.** Run setup from zero with `AI_EDITOR_HOME=<empty dir>` on Mac,
   and the full bootstrap on Windows and Linux in CI. Pin every version (Python packages in a lock
   file per OS, Node lockfile already pinned, minimum ffmpeg/Node versions checked by doctor).
   One command restores the exact environment. Test: CI job that installs from zero and runs smoke.
2. **Drop in any link.** `start` routes a pasted link to the right skill without questions about
   what it is: a video file or video URL (YouTube, TikTok, Instagram reel, Drive/Dropbox share) to
   cut + style-edit; a creator profile or several video links to creator-teardown; a website to
   product-video; a long video or podcast to clips. A small classifier with a test table of real
   URL shapes.
3. **Captions never fail contrast.** When the copied creator's caption style (e.g. white, no
   stroke) drops under 3:1 on the real footage, add a stroke or soft shadow automatically. Test:
   check.py render passes on a bright background.
4. **Cut bugs.** `render.py` "span 0: N frames, wanted N+1" with custom pause settings; the silence
   threshold clipping words over a music bed. Tests on synthetic audio.
5. **Skill quality pass.** Every SKILL.md read against PRINCIPLES.md: one decision path, under 250
   lines, references for detail, trigger phrases that fire (claude plugin eval, 3 runs each), no
   step that makes Claude read raw data a script can summarise.

## Next

- Evals load the plugin: `claude plugin eval` cannot resolve the creator-teardown dependency for ai-editor (and rejects --plugin-dir), so every ai-editor eval runs without the plugin. Make the dependency resolvable in eval runs (tagged release or a self-contained eval marketplace), then confirm AskUserQuestion graders work headless.

6. Measured cost per video on a real run (needs a TypeSafe key on the test machine).
7. Modal render tested live (needs a Modal login on the test machine).
8. Export opened in DaVinci Resolve (free) to confirm FCPXML positions.
9. Product films: sparse dark sites (fill), desktop captures at 3x, the generated score richer.
10. README rewritten for a beginner around `start`, with the cost table and what each skill does.
11. Smoke test stable under load (one timeout seen in edit.py stills).

## Needs a decision from the maintainer

- Merge `upgrade` into `main` (a pull request with before/after screenshots).
- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped).
