# Changelog

What changed for every user, newest first.

## Unreleased

- Captions never fail contrast (backlog item 1): plan.py measures the cut behind every caption page
  (at the caption box, through the zooms and pans, 4 samples a second) and, where the creator's look
  would read under 3:1, adds the first step that reaches it: a denser soft shadow, then a 0.1 em stroke
  in the darkest colour of her palette that stands 4.5:1 off the fill (else near-black), then a 0.45
  backing. Per chunk, in plan.json `treat` / `treat_color`; a dark background keeps her plain look,
  and a style with its own stroke or box is left alone. Fixed in check.py render on the way: on a
  bright desk the caption finder took the desk for white text (now its colour tolerance shrinks when
  the footage is close to the fill), and the ring round the glyphs used a square kernel that reached
  past a stroke on every curve (now round). plan.py demo checks the steps on flat colours and on
  bright and dark clips; smoke renders white unstroked captions on a bright desk and check.py
  render passes
- Cut bugs (backlog item 2). render.py "span N: X frames, wanted X+1": build_timeline sized the last
  span from the file's duration, which is the audio's when it outlasts the video (a phone's often
  does), so it asked for frames that do not exist; now the frame count is the video stream's own
  (ffprobe -count_packets). And render.py trimmed on exact frame times, so a container timestamp
  rounded a hair either side of the boundary (a 1/600 s timescale at 29.97 fps) kept or dropped
  that frame, and a video stream starting a frame or two in lost frames from span 0; now it trims
  half a frame early on both edges from the video stream's own start, and the audio follows the
  same offset. Music under the voice: build_timeline used to stop ("only 18 dB apart") and the
  fix it suggested, a fixed `--noise`, found no silence or cut into quiet words. Now a speech-to-
  background gap of 10-20 dB is a music bed: the threshold is the quietest 10% of the take plus a
  third of the way to speech, and only the gaps between transcript words are trimmed, never inside
  a word. `cut/scripts/test_media.py` (in CI): 4000 random span / frame rate / timescale / start
  offset combinations, real renders at 29.97, 25 and 60 fps with audio past the video and a late
  video start, and a synthetic music bed where no word loses a frame
- Evals load the plugin: every ai-editor eval case lists `plugins: ["../..",
  "../../../creator-teardown"]`, so `claude plugin eval` loads creator-teardown beside ai-editor
  and the dependency resolves (before, every ai-editor case ran without the plugin and scored 0).
  Run both suites from the repo root with `tests/run_evals.sh`; an optional CI job runs it when
  the repo has an `ANTHROPIC_API_KEY` secret. Headless eval runs have no AskUserQuestion tool, so
  the `tool_used: AskUserQuestion` graders are now `asks-and-waits` llm graders that pass on a
  question with choices, recommended first, that stops the turn. Eval runs have no shell, so
  each case runs as a dry run (`append_system_prompt`). Fixed on the way: `start` now routes a
  plain website to product-video even after "edit my video" (it asked what the link was), and
  product-video makes the animatic and asks Approve before a "just render it" on an unstamped
  plan. Graders for edit-like-creator and paste-tiktok-profile follow the `start` front door,
  and tear-down-handle names two creators, the case where the skill has a question to ask
- Drop in any link (backlog item 1): `start` routes every pasted link, @handle or file path before
  anything else, with no question about what it is. `lib/ai_editor/links.py` classifies offline
  (own footage to cut + style-edit, a creator to tear down, a long video or podcast to clips, a
  website or app store page to product-video, music to the rights question), reads a single
  video's length with yt-dlp (8 min and over goes to clips), groups several videos from one
  creator into one teardown, and orders the work (questions, creators, own footage, long videos,
  websites, music). One question in the question box only when a short video could be the
  user's own or a creator's. `links.py fetch` downloads the user's footage (yt-dlp, Google
  Drive, Dropbox dl=1, OneDrive, plain HTTP) into the edit folder with a plain sentence for a
  private link, a folder link, a web page instead of a file, or a file over 4 GB; iCloud links
  are explained (they open a page, not the file). Cookies only after a yes in the question box
  (exit 3). `links.py demo` checks 62 URL shapes; evals paste-website-link and
  paste-tiktok-profile
- Fresh install, reproducible (backlog item 1): Python packages install from one hashed lock for
  every OS (`plugins/ai-editor/requirements/requirements.lock`, `uv pip compile --universal`,
  Python 3.10+); the renderer installs with `npm ci` from its package-lock.json; the whisper
  (tiny, small), face and matting models are pinned by URL and sha256 in `lib/ai_editor/models.py`
  and checked on download. `setup.py bootstrap` installs everything and is safe to re-run (a second
  run downloads and changes nothing); `setup.py repair` puts the exact pinned set back. What got
  installed is recorded in `~/.ai-video-editor/env.json`; doctor prints FIX on drift from it and
  checks minimum Python 3.10, ffmpeg 4.4 and Node 20 with the exact fix command. CI installs from
  zero with the bootstrap on Mac, Windows (through `py`) and Linux, re-runs it, drifts a package and
  repairs it (tests/fresh_install.py), then runs smoke. setup.py demo covers the drift check
- Fixed: the transcribers (cut and creator-teardown) and clips ignored AI_EDITOR_HOME, so an
  install there downloaded the 500 MB model again into ~/.ai-video-editor
- Fixed: on Linux and Windows rapidocr pulled in opencv-python next to opencv-python-headless, two
  packages writing the same cv2 folder; the lock leaves opencv-python out
- Fixed: the face model came from opencv_zoo's moving main branch; whisper re-resolved the Hub's
  latest revision on every transcript; the renderer re-installed only when package.json changed,
  never when the lock did
- improve skill: collects suggestions, taste regressions, preview corrections and feedback issues, grouped, for fixes with a test each; docs/feedback-matrix.md maps every rule to its check and test
- taste: after a correction, ask this video / my style / would help everyone; everyone writes a scrubbed suggestion and can open a GitHub issue (taste.py suggest, issue)
- journey.py demo: a cursor cut by the frame edge fails and is hidden; empty ground counts as no product
- golden.py: the default look must carry no banned AI tell, planned (demo) and rendered (full run)
- check.py: a number on a built card that the speaker never says is a FAIL (check.py demo)
- record.mjs: create is on the deny list; tests/test_record.mjs proves the deny list and the blur (incl. the logged-in name) on a synthetic page
- product.py: story order checked (hook first, end last, result after action, payoff before end; make-before-discover warns); default length in gates.target_length (gates.py demo)
- product.py: music needs --rights, --file records a file's licence, plan refuses an own track with no recorded rights (gates.py demo)
- product.py: plan refuses without brief.json; render refuses a plan not stamped by product.py approve, or changed since (gates.py demo)
- check_plugins: every own SKILL.md must say AskUserQuestion; the key links in setup and the asking evals cannot be dropped
