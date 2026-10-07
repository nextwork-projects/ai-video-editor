# Backlog

Ranked by value to a first-time user. One item at a time; each lands with a test that fails before
and passes after. Done items move to CHANGELOG.md.

Source of the 2026-10-07 items: a new-user run with an empty `AI_EDITOR_HOME`, no API keys, the
sample take through start, cut and style-edit to a laptop render and `check.py render`, plus one
creator profile (teardown, `--top 3`), one 20-minute public talk (clips, candidates only) and one
public website (product-video, brief to animatic).

## Now

1. **Product film: blank frames and a half-cut headline pass the plan's framing check.** On a public
   site with a 4-beat story, `product.py plan` printed "framing: every frame holds", but the
   animatic shows the hook's end and the action's start as blank white (the camera crossing page
   whitespace), and the second line of the stat headline cut by the bottom edge at the action's end
   and through the result beat. A story `steps` index past the flow's real steps is a raw
   `IndexError` from `journey.py` line 317; the index counts the auto scroll-into-view step and drops
   `wait`, which `story.md` does not say.
   Fix: the framing check FAILs a frame with no detected content and a text line crossing the frame
   edge outside an edge fade; `plan` validates `steps` and lists the valid indices with what each is.
   Test: the same site and story -> plan exits 1 naming the blank frames and the cut line, or
   re-plans the camera; a story with `"steps": [5]` exits with a one-line message, no traceback.

2. **Captures on vertical are small boxes nobody can read on a phone.** Two `format: "browser"`
   captures on the 9:16 sample planned as `layout: box` at about 20% of the frame height above the
   head; the site text inside is a few pixels high. style-edit says "On vertical every explaining
   card is a full-frame scene (or sits in the split panel), never a small box", and
   `check.py plan` passed with 0 FAIL, 0 WARN.
   Fix: on 9:16 a capture is a scene or split card by default; check.py FAILs a capture whose
   largest text line renders under a phone-readable height.
   Test: the sample plan with one browser capture -> its layout is `scene` or `split`, or
   `check.py plan` FAILs on the box.

## Next

- Cost: the talking-head path makes Claude read about 120 KB (about 30,000 tokens) before the
  first render, half of it in style-edit: `contracts.md` 22.7 KB (for a 2 KB visuals.json shape),
  `visuals.md` 20.5 KB, `SKILL.md` 13.2 KB, `plan.md` 6.4 KB. `motion.md` (31.4 KB) and
  `ai-tells.md` (20.4 KB) are named as "read when a step says". Split the shapes Claude writes
  (visuals.json, spans.json, story.json) into one short file and cut style-edit's required reads
  under 25 KB.
- Captions keep Whisper's hyphen tokens: the sample shows "one -for -one" as a caption chunk
  (`plan.json`). Join hyphenated tokens when building chunks. Test: words `one`, `-for`, `-one` ->
  one caption "one-for-one".
- Alternate hooks recorded after the call to action: the sample take ends with two more takes of the
  opening line (186-199 s). `retake-detection.md` says "the last take wins", which would move the
  hook to the end; there is no rule for it and `candidates.md` flags it as a plain retake.
- The stills sheet labels are out of order: "1-opening 0.50s" then "2-caption 0.23s", and tile 3 is
  missing.
- `check.py render --style <file>` prints "note: no --style" when the style file is `{}`.
- clips step 1 runs bare `yt-dlp`, which setup installs only inside the venv (links.py already
  falls back to `venv/bin/python -m yt_dlp`), and asks for up to 2160p: a 20-minute talk at 4K is
  several GB for a 1080x1920 clip. Use `links.py fetch` or the venv's yt-dlp, capped at 1080p.
- clips `shortlist.md` "names:" lists sentence starts ("And", "So", "What", "Extraordinary", "T").
- Teardown `look.md` without a Gemini key: "font [from the look pass]" stays as a placeholder;
  "Graphics: on screen 55% of the runtime" contradicts "graphics on screen: winners 2, control 0";
  "AI tells: 3 BAN" names none (they are only in `style.json` and `report.json`, 8.7 KB), and the
  two names found ("cream-paper-ground", "purple-blue") are on a black and brown palette.
- Teardown `--top 3` downloads and transcribes 5 videos (3 plus 2 control). Say so in SKILL.md and
  in the command's first line.
- Teardown script output goes straight into Claude's context: `graphics.py measure` prints 246 lines
  of JSON, `visual.py measure` 40, `sound.py measure` 29. Print one summary line and the file path.
- product-video step 1 builds the brief from "the h2s and nav items" but never names
  `product.py copy` (4.7 KB, already compact), so Claude reads `site.json` (20.8 KB). crawl.mjs
  prints "logo undefined".
- `profile.py set` takes one answer per call and prints the full profile path each time (12 calls
  for one intake). Accept several `key=value` pairs in one call, print one line.
- No free-disk check: setup needs about 1.5 GB and the cutout writes about 0.5 MB a frame. The test
  machine had 3.5 GB free. doctor should FIX under 3 GB.
- The key file ignores `AI_EDITOR_HOME` (`keys.py` uses `~/.config/creator-teardown/.env`), so an
  isolated test run still finds and spends real keys. Read `$AI_EDITOR_HOME/.env` first.
- README calls the laptop render "the slowest option"; on the 46.8 s sample `edit.py estimate` gave
  laptop 63 s, Modal 2.0 min, GitHub Actions 7.7 min, and the laptop took 42 s.
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
