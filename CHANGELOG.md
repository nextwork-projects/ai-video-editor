# Changelog

What changed for every user, newest first.

## Unreleased

- `check.py render` now checks motion on every frame of the whole picture, not only on each card. It
  FAILs a one-frame flash (frame 0 too) and one or two black frames while the footage has picture, and
  WARNs a one-frame jump that no cut, zoom or card change explains. Each names the time and the fix. A
  fault the footage itself has is skipped. Test: `quality.py demo` (a clean clip passes; a white flash,
  black frames and a jump are caught).

- The Modal hedge tested on a real render. 45 s of the sample take (1,352 frames, 9 pieces, 3
  containers) with piece 0 held in its container (`AI_EDITOR_MODAL_SLOW_PIECE=0:600`, test only, off by
  default): a second copy started, finished first, and the held one was cancelled. 197 s against 189 s
  with nothing held; $0.032 on the bill against $0.037. `check.py render` 0 FAIL. The render's saved
  start-up read 124 s, because the second copy's container boots late on purpose. Start-up now counts
  only first copies. Test: `modal_render.py demo`.
- The Modal estimate counted the whole footage upload when Modal already held it (a re-render uploads
  in 3-4 s). It now asks Modal by each file's hash and counts only what is missing, without sending
  anything (about 1 s; every byte when Modal is not set up or does not answer). Test: `edit.py demo`.

## ai-editor 2.1.0, creator-teardown 2.4.0 (2026-10-08)

- Setup times are now measured, not guessed. Six clean GitHub runs of the e2e job (2026-10-08) took
  25-36 s to install from zero on Linux, 33-49 s on a Mac, 66-75 s on Windows (packages 11-33 s,
  renderer with Chrome 8-33 s), with the tiny test model. README and the setup skill quote these.
  `tests/fresh_install.py` ends with a table of each step's time, also in the job summary on CI.
  Test: `fresh_install.py demo` (in demos.sh).

- A beginner who left the names question blank got no logos or captures: `route.py beats` marked only the
  profile's `names`. It now also marks any word written with a capital inside a sentence and says which ones
  are not in the profile. The sample take's beats list Jev, Claude, Haiku, Opus and Fable. Test: `route.py demo`.

- Output a new user could not read. face.py and `check.py render` no longer print OpenCV's "Targets are not
  supported by the new graph engine" WARN (its log is set to errors where the detector is made).
  `check.py render` no longer prints seven ffmpeg "Broken pipe" lines after its summary (a frame reader that
  stops early stops ffmpeg first). The flow scene tweened a veil it never draws on a scene's ground: 15 "GSAP
  target undefined not found" lines on the sample's stills, now 0. Setup keeps npm's "added 369 packages" and
  "Has browser at ..." back unless the step fails, and a model download names the file, not its pinned URL.
  `transcribe.py` prints one line for its re-heard words, `profile.py style` says "the default style (smooth
  zooms about every 6 s, 3-word captions)", and the sound kit prints one line, "4-5 dB under your voice".
  Tests: `face.py demo`, `check.py demo`, `setup.py demo`, `models.py`, `test_media.py`, `sfx.py demo` (now in
  demos.sh), smoke.py (stills fail on any GSAP target warning).

- `verify_cut.py` SURVIVED lines gave no time, so a doubled "and, and" went on into captions. Each line now
  prints its cut time, its source time and the spans.json entry to add (`after` set). Test: `verify_cut.py
  demo` (in demos.sh).

- Intake wording disagreed with itself. One id list everywhere: `audience` and `names` per video (the
  audience answer also saves `goal`), the style questions in three calls that start, setup step 8 and
  intake.md share. With no creator the caption option reads "clean, 3 words at a time". `profile.py set`
  given a bare `key value` among `key=value` pairs names the argument that is wrong. Test: `profile.py demo`.

- Render estimates. The laptop benchmark times Chrome's start-up apart from the frames (it was folded into
  the per-frame speed); on the 44.9 s sample cut the estimate was within 25% of the render in 3 of 4 tries.
  The GitHub Actions and Lambda lines say "Not set up yet" the way Modal's does. README and cloud.md carry
  one set of numbers, each named by what was rendered: the 44.9 s cut on Modal 2.7 min on 3 machines, about
  $0.03; the uncut 3.4-minute take $0.18-0.19 on the bill; $0.06 for 60 s and $0.54 for 10 min (estimates).
  Test: `edit.py demo`.

- Stale docs. motion.md and contracts.md: a hard-cut scene starts `CARD_LEAD_S` before its word.
  teardown-page.md: slow-drifting footage goes to `drift_dets`, with what it misses. plan.md: how the matte
  `--modal` cost is worked out. render-watcher covers Modal. contracts.md: `flow` is a full-frame scene on
  vertical and a box on wide, as plan.py does it.

- Link routing. A Drive link carries its share how-to only for a failed download, and its edit folder is
  named after the file. Podcast analytics redirects (podtrac, chartable, podsights, op3 and others) are
  stripped to the host's own file. An Instagram reel yt-dlp cannot open comes back with a note saying so.
  Test: `links.py demo`.

- style-edit shapes.md opens with a whole two-beat visuals.json, so the file's shape (one JSON array of
  beats) is shown before the per-pick table.

- A vertical capture too small to read became a sticker of the page's own headline, which the speaker never
  said, with its tight lines touching. plan.py now cuts a capture to a sticker only around words marked on
  the page (`find` or `highlight`). With none marked, or marked words set tighter than the captions' line
  height (1.14), it drops the card and says why and what to add (a sticker beat with a `find`, which
  capture.mjs re-sets with open lines). The message for a cut says plan.py did it. Test: `check.py demo`
  (the sample's two unmarked captures drop; the marked headline set 150 px apart on 212 px lines drops; an
  open line becomes a sticker).

- The default render WARNed a one-frame zoom snap and a jittering logo, with fixes the model could not act
  on ("render with the current StyleEdit.tsx"). plan.py moves a zoom change out of a card's entrance so the
  punch finishes before the card starts, or, for a full-frame scene, to the scene's middle where it is
  hidden; two zooms closer than a punch's 0.16 s travel join into one. `quality.py` skips zoom moves under a
  scene, reads one just before a scene only up to its start, and now catches a zoom that drops out and
  straight back in one frame. Its jitter check needs 2+ frames of movement each side of a turn, so a thin
  logo edge flickering through a fade no longer counts. The logo sting lost its ring, which popped in on one
  frame. Zoom, jitter and cover WARNs now name a style.json, visuals.json or plan.json change. The sample's
  default render: 0 FAIL, only the loudness WARN. Tests: `plan.py demo` (the 28.05 s punch before a scene),
  `quality.py demo` (the out-and-back snap; the logo's one-frame flicker).

- Someone else's short video recommended editing it as your own. A public TikTok or YouTube Short pasted
  without `--own` now asks with **Copy this creator's style** first; **Edit it as my video** is second.
  Every `ask` item from `links.py route` carries its `question`, which start/SKILL.md says word for word.
  Test: `links.py demo` (a 136 s TikTok and a 39 s Short put `creator` first; every ask has a question).

- "Finish setup" after the one-command install found nothing to finish. `setup.py todo` now lists every
  optional step not done yet (the three keys, the style questions, Modal, the matte), from the same checks
  doctor reads, whether or not it was saved for later. `setup.py later <step>` refuses an unknown step with
  exit 2 and the list of steps. setup/SKILL.md no longer asks for times doctor does not print. Test:
  `setup.py demo`.

- Audio-only podcast clips held still: only the captions moved, and `check.py render` WARNed "nothing moves"
  for the whole clip. The renderer now draws the cover itself (plan `cover`, from `clip.json`): a slow push
  on the sharp cover to 1.12x and the blurred ground easing back from 1.06x and drifting down, both on one
  `sine.inOut` over the clip in log space, plus a 1.02x `punch` on each sentence start (motion.ts
  `punchAt`). No zooms on those clips. The cover is 640 px at y 320 so the push stays inside the 9:16 safe
  frame. `quality.py` counts the cover as moving where its edge travels 0.5 px/s or more, and measures the
  push on the render (WARN when under half the plan). Tests: `tests/smoke.py` renders a 16 s audio clip and
  fails on a "nothing moves" WARN (it did before this change); `plan.py`, `quality.py`, `clips.py` demos.
  Live on a public feed episode, a 25 s clip: render 35 s, check render 0 FAIL 0 WARN, push planned 0.113,
  measured 0.113 log-scale.

- An audio-only podcast stopped at clips: a feed or Spotify episode downloads `source.mp3`, and
  `clips.py` looked only for `source.mp4/mov/mkv/webm`. One `source()` lookup now finds video or audio
  (mp3, m4a, aac, wav, ogg, flac, opus) for candidates, page and trim; `link` keeps an audio file's
  extension. `links.py` reads each episode's artwork from the feed (the episode's itunes:image, else the
  show's) into the episode options, and `fetch --direct --cover <image>` (or a Spotify link) saves it as
  `cover.jpg` next to the audio. `trim` makes each audio clip a 1080x1920 video: the cover blurred and
  dimmed to 30% fills the frame, the sharp cover sits above the captions (no artwork: the file's
  embedded art, else black); `clip.json` says `audio_only` and `profile.py style` keeps captions on for
  it. The picks page plays audio previews. Tests: `clips.py demo`, `links.py demo`, `profile.py demo`,
  and `tests/smoke.py` renders a synthetic audio clip through the real renderer with `check.py render`
  0 FAIL. Live on a public 4-minute news feed episode: episode list 0.2 s, download with cover 1.5 s,
  Whisper 32 s, candidates 0.4 s, picks page 1.5 s, trim 5 s, render 14 s, check render 0 FAIL.

- A podcast feed link (RSS or Atom, 442 episodes) went straight to clips with no episode picked, and
  yt-dlp `--no-playlist` was still walking the feed after 5 minutes. `links.py route` now reads the feed
  itself (stdlib, 15 s timeout, 32 MB cap; an Apple Podcasts show page through the iTunes lookup API)
  and returns an `ask` with the newest 10 episodes (title, date, length, audio url), the newest 3 as
  options, newest first. `fetch --direct` downloads only the picked file, no yt-dlp; a feed passed to
  `fetch` says to pick an episode. Every yt-dlp call on a link that can be a playlist (`probe`, `fetch`,
  product-video's music step) adds `--playlist-items 1` and a hard timeout (60 s to read, 30 min to
  download) that ends in a sentence saying what to paste instead. clips/SKILL.md says what a podcast
  link does. Measured on one public feed: episode list in 0.65 s, download started 1.7 s later.

- `check.py render` FAILed a behind card the cutout already covers ("drawn over the face ... up to 41%
  of the head", fix: face.py, plan again, which loops). It looked the matte up by its 4-a-second
  sample number instead of the plan's frame, so no matte was found, and ffmpeg's fps filter handed
  it the render 0.1 s off the footage it compared with (mid zoom-out at 3.5 s). It now samples exact
  frames and reads the matte the render drew at that frame; a behind card counts as on the face only
  where it shows on the speaker's solid matte. A behind card with no matte there says to run matte.py.
  On the sample take: 3 face FAILs -> none. Test: `check.py demo`.
- A re-plan dropped the cutouts, and matte.py re-cut a whole range when a card moved (195 frames,
  49.5 s, for 30 new ones). Matte frames are now named by their frame of the cut, in one folder per
  cut and output size, and only frames not cut yet are cut; plan.py keeps every cutout whose frames
  are all there. On the sample take, a re-plan with the same ranges needs no matte run, and one that
  moves a card cuts 30 frames in 10 s; the cutout folder is 179 MB, was 278 MB. matte.py `--estimate`
  prints the frames, time and cost and stops. style-edit step 4 runs matte after music's re-plan and
  says to run it after any later plan. `check.py plan` and plan.py print the real edit path (was a
  literal `edits/<name>`). Plans made before this need plan.py and matte.py again before a render.
  Tests: `matte.py demo`, `check.py demo`.

- A caption correction into several words ("use." heard, the cut says "are using.") was one token,
  which plan.py's word cleaning glued into "areusing" on stills and the render, and `check.py render`
  flagged as a LOOK. `retakes.py caption_words` and `retakes.py fix` on captions.json now write one
  token per word, the original word's time shared by letter count. Clip edits run the same captions
  step. Test: `test_retakes.py` (one heard word corrected into two gives two non-overlapping tokens).
- A scene cut in hard (`cut`) started SCENE_LEAD_S (0.3 s x k) before its word, a lead sized for a
  transition that grows, so the picture changed up to 0.4 s early. It now starts where a box card
  does, CARD_LEAD_S before its word; match, iris and the other growing transitions keep the lead.
  `quality.py` counts a cut scene as landed on its first frame. Tests: `plan.py demo`, `quality.py demo`.
- Teardowns made before `"transitions"` was written left the key out, so a creator who only cuts
  still got match / iris. `profile.fill_transitions` (run by plan.py on load) now derives them from the
  style's measured `pace.cut_kinds`, the same rule as visual.py; a style with no cut kinds keeps the
  default and plan.py says re-running the teardown gets the creator's transitions. Test: `profile.py demo`.

- The code kind guess called white one- and two-line titles over photos "photo" or "UI recording".
  `text_fill` is now the share of the box all its OCR lines cover (it was the biggest line), and one
  to three lines covering half the box or more is a text card before the moving test (the picture
  between the letters can move). On the hand-labelled titles of two public slow-drift videos: 6/16
  -> 16/16 and 2/4 -> 4/4 text card (the documentary with look.py's caption marks cleared; with
  them, 2/16 both ways, see Next). Test: `graphics.py demo` (a two-line title over a moving photo).
- `laid_on` dropped titles that arrive and leave on cuts. A drift track is now also kept when it
  starts or ends on a cut (from visual.json or a frame-wide jump) with one to three OCR lines
  inside, or when a hard cut inside its run changes the picture between its letters but not the
  letters. Test: `graphics.py demo` (generated stills, a title held across a cut with no OCR, a
  title from one cut to the next with OCR). Measured: documentary precision / recall 0.00 / 0.00
  before and after; generated stills 0.00 / 0.00 -> 0.05 / 0.25 (the title that lands on a cut is
  found). What still misses them is in Next.

- Modal renders took 5.2 min on the 3.4-minute sample take where the estimate said 2.9 min. Measured
  causes: the upload sent the bundle as ~3,700 small files, one request each (44 s, 40 s even when
  nothing had changed); one container in each render ran its piece 2-10x slower than the rest (213 s
  against a 107 s average; another time 368 s against 16-61 s); the pieces downloaded one after
  another after the last finished (39 s). Containers started 4-18 s after submit, not 225 s: that
  figure had the download and join counted as start-up.
- Fixes: the code goes up as one tar with fixed file times, so Modal skips it by hash when unchanged
  (upload 44 s -> 22 s new, 3-4 s repeat). Each container takes three pieces from a shared queue, and
  once the queue is empty a piece still running at twice the median gets a second copy on another
  container; the first to finish counts. Pieces download as they finish. Containers: as many as keep
  the 23 s billed boot under 20% of each one's bill (17 for the sample take).
- The estimate now adds upload, start, the work over the containers times a straggle factor, and the
  tail (last download and the join), each measured on the last render and saved to `modal.json`;
  before the first render, the sample take's (`edit.py` `MODAL_MEASURED`). Sample take after: 184 s
  (estimate 3.1 min) and 257 s on a laptop at load average 131 (122 s of the join under that load),
  $0.18-0.19 on the bill as before. Tests: `edit.py demo` (container count, pieces, the estimate
  from given speeds), `modal_render.py demo` (the tar is identical across file times, the measured
  speeds, a stuck piece replaced and cancelled).

- Modal render tested live on the 3.4-minute sample take (6,167 frames). It failed on every container:
  render.mjs asked for one tab per core Node reports, and Remotion caps at `nproc` (4 on a Modal
  container). render.mjs now takes Remotion's own ceiling. Test: `modal_render.py demo <bundle> <plan>
  <out>` with a fake `nproc` of 4.
- A failed Modal render left the job's folder on the Volume: a container still running wrote it back
  after the delete. The delete now waits until the app has stopped. Test: the same demo.
- Modal billed each container 60 s idle after its piece. `scaledown_window=2` cuts that.
- The printed Modal cost was 28% under the bill ($0.131 against $0.181). Chrome uses about 4.6 of the
  4 cores requested and each container is billed about 23 s past its piece; the cost now counts both.
  First-render guesses moved to the measured 0.29 s a frame and 70 s of start-up. Test: `edit.py demo`.
- Captions with no font named rendered in system-ui: SF Pro on a Mac, another font on Modal, GitHub
  Actions and Lambda, so the render did not match the approved stills. They now load Inter, as does any
  font Google Fonts does not have. Test: `tests/check_plugins.py`.
- Measured: image build about 2 min once (NodeSource's signed apt source works), render 6.5 min,
  $0.18 on the bill, `check.py render` 0 FAIL, the Volume empty afterwards.

- Teardown graphics found nothing over footage that only drifts (slow pushes on stills, dissolves
  between them). New in overlay mode: `drift_dets` keeps hard edges that hold exactly still for
  +-1 s while the picture's other edges move, and drops a box whose surround holds still too (the
  fixed point of a push). A drift track is grown on its own lettering (`grow_drift`), snapped to the
  OCR lines it holds (`to_text`), and kept only when its box changes at its entrance or exit while
  the rest of the frame does not (`laid_on`). Samples in a dissolve or on a cut find nothing.
  Faces that turn up all over the frame (portraits in a documentary) no longer count as a speaker,
  so such a video gets overlay mode. Test: `graphics.py demo` (a title over a slow push, a hard cut
  with nothing on it).
- look.py marked held titles as captions when there was no transcript: OCR misreads of a held line
  restarted its run, so the 4 s limit never fired, and the caption band then hid the titles from
  graphics.py. A line now carries on a nearly identical one from the sample before. Test:
  `look.py demo`.
- Re-scored on one public documentary (colourised stills, slow pushes, dissolves, 8 hand-labelled
  one- and two-line titles; 90 s): precision 0.00 / recall 0.00 before, 1.00 / 1.00 after. OCR read a
  line inside every title; 3 of 8 were marked captions before (and set the caption band), 0 after.
  The code kind guess still calls most of these titles "photo".

## ai-editor 2.0.0, creator-teardown 2.3.0 (2026-10-07)

- Teardown graphics in overlay mode (moving footage, no steady speaker) had no entrance or exit.
  `overlay_motion` tracks the graphic's settled picture through the source frames (where it is found
  gives a slide, its size a scale, how much of it shows a cut or fade) and fits the curve with the same
  `fit_ease` as plate mode. A fit under 1.5 frames now reads as a cut in both modes. Test:
  `graphics.py demo` (card slides up 0.3 s power3.out, tile cuts in and fades out over moving footage).
- The code-only kind guess called a one-line word mark in a near-square box a logo. A box whose biggest
  OCR line covers half of it or more (`text_fill`) is a text card. Test: `graphics.py demo`.
- Checked on one public non-talking-head explainer (8 hand-labelled graphics): overlay mode precision
  0.00, recall 0.00 before and after; the miss is detection on near-still footage (now in Next).

- The Modal render image installs Node from NodeSource's signed apt source; check_plugins now rejects any downloaded script piped into a shell, root or not.

- The Debian and Ubuntu Node fix line ran NodeSource's setup script as root. It now adds NodeSource's
  signing key and apt source by hand, then installs `nodejs`. `tests/check_plugins.py` fails any file that
  pipes a downloaded script into `sudo` and a shell. Test: `setup.py demo`.
- A Flatpak Chrome, Chromium or Edge left login.mjs saying "no Chrome found". It runs only inside its
  sandbox, so it is still not launched, but login.mjs and doctor now name it and give the fix (a snap,
  distro or Google Chrome install). Doctor has an optional `chrome` row from the new `login.mjs browser`.
  Test: `node tests/test_record.mjs` (chrome lookup), `setup.py demo`.
- clips told Windows users to copy the source video, often several GB. `clips.py link` makes
  `source.mp4` a hard link on the same drive (no admin needed), else a symlink, else a copy, and the
  skill uses it on every OS. Test: `clips.py demo`.
- The renderer copy in `~/.ai-video-editor/remotion/src` kept components deleted from the plugin:
  edit.py copied over it with `dirs_exist_ok`. `mirror()` now removes files and folders gone from the
  plugin's `remotion/src`, inside that folder only. Test: `edit.py demo`.
- product-video's brief asked 11 questions over three calls. It now asks the four that change what gets
  built, then one question confirming the defaults for the rest (style, length, login, music, sound,
  voice), with "Change some" asking only the ones named.
- cut's step 0 told Claude to ask "cut first or everything" even after "edit my video like @creator",
  a request that routes to start, which decides that itself. The line now says so.
  `tests/check_plugins.py` fails a skill that quotes another skill's trigger without naming that skill.
- cut, clips, product-video and improve ran `python3` scripts with no line saying `py` on Windows; each
  now has the line the other skills use. `tests/check_plugins.py` fails a skill that runs a
  `python3 "<script>"` command without one.
- A suggestion sent as a public GitHub issue kept the names, domains and creator handles from the user's
  profile, and any bare domain (`acme.io`): `taste.py scrub` only caught full URLs, emails, @handles,
  paths and media files. Every `names` entry (name and domain) and every creator handle in profile.json
  now becomes `<name>`, and any other bare domain `<domain>`. File names like `plan.json` stay. Test:
  `taste.py demo`.
- `setup.py setkey gemini` sent whatever token-shaped text was on the clipboard to Google to test it.
  `keys.verify` now refuses a Gemini key that does not start with `AIza` before any request, and says a
  Gemini key was expected. TypeSafe and ElevenLabs have no documented fixed prefix, so they are not
  checked. Test: `keys.py`.
- Blending creators dropped the pace creator's scene transitions: `profile.py` PARTS["pace"] did not list
  `transitions`, so the blend fell back to style-edit's default. It now comes with pace, as in
  creator-teardown's editplan. Test: `profile.py demo`.
- A creator measured with no drop shadow lost the contrast treatment on bright footage: Captions.tsx read
  `shadow: false` as "a scene is up" and dropped the treatment with the shadow. Scenes now set their own
  `flat` flag; `shadow: false` only drops the default shadow. Before: the no-shadow bright-desk render read
  1.24:1 and `check.py render` FAILed; after, it passes. Test: `tests/smoke.py` (the `noshadow` contrast case).
- A creator who only cuts got match in / iris out on every scene. Scene.tsx has a `cut` transition (no
  transition either side), creator-teardown writes `"transitions": []` when the cuts it measured are all
  hard, and plan.py turns that into `cut` in and out (no list still gives match / iris). The
  `same-transition` tell no longer fires on all-cut scenes, which is its own fix. Test: `plan.py demo`,
  `visual.py demo`, `ai_tells.py demo`, `node tests/test_record.mjs` (cutPhase).
- ai-tells.md named a real person for a caption preset; it now says "the uppercase yellow-keyword stroked
  caption preset" and keeps the source link.
- product-video loaded the home page twice: once for the brief (`--pages 0`) and again in the full crawl.
  The full crawl now starts in the background before the brief; crawl.mjs writes site.json as soon as the
  home page is shot (`pages_pending`) and again with the inner pages, `product.py copy` waits for the
  first and `product.py pages` for the second. On linear.app: 55 s + 56 s of crawl before, 54 s after
  (the inner pages finished inside the home page's time). Test: `product.py demo` (wait_site).

- creator-teardown did not measure how a caption's words change as they are said (`highlight None` on a
  grey-to-dark karaoke). look.py now reads every source frame inside the caption box of up to 8 captions a
  video, times each word from the transcript, and names the style from what a word looks like before it is
  said: `reveal`, `karaoke`, `highlight`, `pill`, `none`, with how far the change lands from the word. It
  writes `captions.effect` in style-edit's names (karaoke + `inactive_opacity`, reveal, word_highlight for a
  box behind the word; a said word that only changes colour keeps the entrance and its `highlight_color`)
  and `captions.shadow`. A moving yellow word used to become `word_highlight`, which style-edit draws as a
  box. A highlight colour that never follows the words is now `emphasis_color`: on a real talking-head
  creator (5 videos, frames checked) the old style.json would have turned every said word yellow; the
  frames show whole captions with one static yellow keyword. Test: `look.py demo` (five fixture clips, one
  per style, the timing within 0.1 s).
- App icons were labelled "text card". A small, near-square graphic of 8 colours or fewer with a line of
  text at most (none running out of it) is now a logo in the code's guess, and the Gemini kinds pass gets
  each crop's size and shape on screen. A real red title banner stays a text card. Test: `graphics.py demo`,
  `gemini.py demo`.
- On creators with no steady speaker or plate (vlogs, walks, b-roll) the graphics detector called the
  moving footage a graphic and missed the real ones. graphics.py now switches to an overlay mode there: what
  holds still while the footage moves, rectangular and not flat, with text or a hard edge. Hand-labelled
  fixture (3 graphics, a still sky and a moving ball over a panning 3-shot clip): precision / recall 0.00 /
  0.00 before, 1.00 / 1.00 after. Test: `graphics.py demo`.
- The AI-tell scan raised a font BAN ("Inter") from Gemini's closest-font guess on one look. Gemini now
  rates its confidence; a font tell stays a BAN only when 3+ videos agree (75%) and most rate it high,
  otherwise it is a WARN worded as a guess with the vote count, and look.md marks the font as a guess. Test:
  `report.py demo`, `gemini.py demo`, `look.py demo`.
- The teardown wrote no top-level `transitions` or `layout`, so style-edit used its defaults. visual.py
  writes `transitions` from the creator's transition cuts (whip, match, mask, dissolve as push, match,
  wipe, fade; absent when they only cut) and graphics.py writes `layout` `{"mode": "split", "seam"}` when
  the graphics own the top panel over a speaker below it. `editplan.py blend` carries them with pace and
  layout. Colour already reaches style-edit through `graphics.palette`. Test: `visual.py demo`,
  `graphics.py demo`, `editplan.py demo`.
- ai-editor ran its independent work one item at a time. Measured on a 14-core Mac, before -> after, same
  inputs: style-edit `capture.mjs` (6 page captures, 3 logos, a repo card, a YouTube thumbnail) 28.5 s -> 8.9 s;
  product-video `crawl.mjs` on a public site (home page and 17 inner pages) 150.5 s -> 48.1 s; `record.mjs
  --states` (4 flows) 27.7 s -> 9.0 s. The pages share one headless Chrome, four tabs at a time
  (`AI_EDITOR_TABS`, 1 turns it off); logos and free sources fetch at once; the crawl reads inner pages while
  it shoots the home page. Same files out (same pages, line counts and state sizes). Screencasts stay one at a
  time (a busy machine drops their real-time frames). No agents here: one Chrome is cheaper than one agent per
  page. Test: `tests/test_record.mjs` (pool order and cap).
- clips edits the chosen clips at once: one `clip-editor` agent (sonnet; Bash, Read, Write, Edit) per clip, all
  launched in one message, each taking its clip through the cut and style-edit to the stills sheet and returning
  a short JSON; then one `stills-critic` per sheet, also in one message. Without subagents the skill runs the
  same steps one clip at a time. On three 23-27 s clips of the sample take (no TypeSafe key, Whisper): 924 s in
  one session -> 112 s (the three agents took 83, 86 and 112 s); input tokens 1.70 M -> 2.00 M (+17%), and the
  main session gets three JSON lines instead of three transcripts and paper edits (peak context 99 K in one
  session, 85-89 K per agent). Test: `evals/clips-fan-out` (three clip-editor launches in one message).
- Hook variants (cut, `references/retake-detection.md`): the variants build, render and verify as parallel shell
  jobs in one call, not agents (the commands are fixed). Two hooks on the sample take: 125 s -> 87 s
  (Whisper's verify is CPU-bound, so two at once is not twice as fast).
- `edit.py` rewrote every renderer file on each stills or render run, so parallel runs could bundle a file
  another run had just emptied. It now copies only changed files, through a temp name. Test: `edit.py demo`.
- A SKILL.md that names an agent must ship it with `model` and `tools` set, and every agent needs `tools`
  (`tests/check_plugins.py`). The unused `teardown-worker` agent is gone (creator-teardown ships its own).
  PRINCIPLES.md "Speed": independent work runs at once, scripts first, agents return short JSON.

- creator-teardown ran every video one after another. Transcription, downloads, the Gemini look calls and the
  visual, look and graphics measures now run several videos at once (a quarter of the cores, 1-4; `CT_JOBS=1`
  turns it off), and SKILL.md starts `gemini.py look --no-merge` beside `transcribe`. Measured on a 14-core
  Mac, `--top 3` (5 videos), every script step: a TikTok creator 425 s -> 119 s, a YouTube Shorts creator
  364 s -> 167 s. Test: `parallel.py demo` (via `fetch.py demo`).
- creator-teardown ships a `video-analyst` agent (haiku): one per video, launched together, each returns a JSON
  beat map (labels, second marks, words, WPM, hook, close, graphics) from the files the scripts wrote. The main
  session merges summaries instead of reading every transcript; without an Agent tool it reads
  `transcripts/<id>.timed.txt` (new: a line a sentence or pause with its start). Test: `fetch.py demo`.
- "Winners" lines compared one video against two and said "every winner on that side". A side with under 2
  videos is now "not enough" and prints no line. Test: `report.py demo`.
- The graphics kinds prompt assumed a talking head, so on a vlog or challenge video Gemini called crops of the
  camera shot (people, ceilings, trees) "b-roll": a measured run reported 16 graphics where there was 1 logo.
  Crops of the main shot are now "part of the set" and b-roll must be an inserted clip; the same run keeps
  only the logo. Test: `gemini.py demo`.
- The AI-tell scan flagged a BAN "flat saturated ground" from the camera footage (a red store wall) when
  graphics were on screen 1% of the time. Palette tells now need graphics on 5% of the runtime. Test:
  `report.py demo`.
- look.md printed `Captions settle in None s.` and Python dicts for cut and sound kinds. It prints
  `hard 56%, jump 7%` and leaves out unmeasured numbers. Test: `look.py demo`.
- YouTube transcripts said `0s - 0 wpm` (a YouTube listing carries no durations) and the cost line said
  `~0s audio`. The header takes the transcript's own length. Test: `fetch.py demo`.
- A download that failed (YouTube 403, TikTok "unexpected response") was printed and skipped, so the teardown
  silently measured 4 videos of 5. Each download now retries once and a failure ends with the ids and the
  `--ids` retry line, exit 1. Both failures from the measured runs recovered on the retry.
- A private TikTok account (or one TikTok hides from yt-dlp) and a misspelt handle both said "update yt-dlp".
  The hint now names the cause: private, missing account, rate limit, Instagram login wall. Test: `fetch.py demo`.
- Gemini: a 429 after the retries said only `Gemini HTTP 429`, and a network drop was a traceback. Both now say
  what to do (wait a minute and rerun, cached videos are skipped; check the connection).
- Blending creators: `camera` stayed with the heaviest creator even when `--pace` named another, `hook` and
  `sound` belonged to no part, and kind percentages averaged only where both had the key (cut kinds summed to
  114%). `camera` goes with pace, `hook` with visuals, `--sound` is a part, and a missing kind counts as 0%.
  Test: `editplan.py demo`.

- Skills ran the venv as `~/.ai-video-editor/venv/bin/python` (ignoring `AI_EDITOR_HOME`) or
  `%USERPROFILE%\...\python.exe` (which Git Bash does not expand). Every skill now runs scripts with
  `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py" <script>` (`py` on Windows; creator-teardown ships the
  same `run.py` in its scripts), which finds the venv under `AI_EDITOR_HOME` and falls back to the running Python
  with a note before setup. creator-teardown's own venv fix line prints the real folder, quoted. Test:
  `check_plugins.py` FAILs a SKILL.md, reference or agent that hardcodes `~/.ai-video-editor/venv` or
  `%USERPROFILE%`, and the two `run.py` copies differing; `run.py demo`.
- style-edit's where-to-render question marked no option recommended, against PRINCIPLES.md "Asking". Both now
  say it is the one exception (only the user knows their time and money).
- "No Chrome Headless Shell" (style-edit table, `capture.mjs`) said run `edit.py stills`, which needs a plan
  that does not exist at step 3. Both now point at `setup.py remotion`, which installs it.
- `route.py` crashed with a traceback on a rejected key or a TypeSafe outage. Picks are left null with the
  error printed, as with no key, and a highlight falls back to the printed blocks. Test: `route.py demo` (a 401
  leaves every pick null and no highlight).
- creator-teardown quick mode said "about a minute per creator". It now lists exactly what it runs (Step 1
  `list`, Step 2 with `--top 5`, Step 3b, Step 3c; no `metrics.py` or written passes, which settles the clash
  with Step 3's "always run") and the measured time (now about 3 minutes, see the parallel entry above).
- `agents/template-filler.md` read `${CLAUDE_PLUGIN_ROOT}/...`, which may reach an agent unexpanded. The caller
  (style-edit step 3) now passes the full path of `shapes.md`. Test: `check_plugins.py` FAILs an agent that uses
  `${CLAUDE_...}`.
- A rejected TypeSafe key (401/403) exited 4 like "no key", so the cut told the user a key would help. It now
  exits 5 with "TypeSafe rejected the saved key ... save a new one"; an outage stays 4. Test: `test_retakes.py`
  (401 exits 5, 503 exits 4, both write candidates.md).
- `candidates.md` flagged "like" in "models like Claude" as a filler and "a lot of tokens and" before "a lot of
  money and time" as a retake. "like" is a filler candidate only when set off (a pause or comma, after
  "and"/"so"/"was", or opening a clause); a repeat whose first run finished its item and ends in "and"/"or" is a
  list. On the sample: both gone, every other candidate unchanged. Test: `test_retakes.py` (the sample's words).
- A network error during Scribe transcription ended in a traceback. It now prints "ElevenLabs unreachable ...
  or use --engine whisper" and exits 3. Test: `test_media.py` (a URLError exits 3 with the message).
- Whisper could fold a spoken repeat into one stretched label, so no span could quote it and only verify saw it.
  `transcribe.py` now lists every label holding far more voiced audio than its word (`build_timeline.unheard`:
  more than twice a speech-rate length and that length plus 0.5 s), transcribes that stretch again on its own and splices in the
  words when it hears more than one; when it hears none (or on CrisperWhisper), the word keeps `unheard_s` and
  transcript.txt shows `[N.Ns of speech not transcribed]` after it (`retake-detection.md` says what to do). On
  the sample: "AI" over 51.18-52.66 s came back as the hidden restart "I'm up. Jeff is just new a -". Test:
  `test_build_timeline.py` (the sample's "content" over 117.7-119.4 s is listed and re-heard; a long label over
  silence is not; nothing re-heard is marked; one word back is a drawn-out word).
- `login.mjs` found Chrome only at fixed paths, and `check()` then spawned nothing with no message. It now also
  looks on PATH (snap and distro Chromium, a portable install), at Chromium and Edge on a Mac, and at Edge on
  Windows, and says what is missing. Test: `tests/test_record.mjs` (PATH on Linux, snap, Edge and PATH on Windows).
- Linux fix lines were apt-only. setup and creator-teardown now print the dnf (Fedora) or pacman (Arch) line
  when that is the package manager on the computer. Test: `setup.py demo`, `fetch.py demo`.
- The cut render's concat list broke on a `'` in the temp path (a user name like O'Brien). It is quoted the way
  ffmpeg reads it. Test: `test_media.py` (a render through a temp folder named `it's tmp`).
- System yt-dlp preferred over the pinned venv copy: already fixed (`links.ytdlp`, `fetch.ytdlp` take the venv's
  first).
- `setup.py doctor` said FIX "installed before version pins" on a working install with no `env.json` and sent
  the user to `repair`, a full reinstall. When what is installed matches the lock (every unconditional pin
  present, every installed pinned package at a pinned version; remotion at its pin), doctor records it in
  `env.json` instead; real drift is still a FIX. Test: `setup.py demo` (a lock-exact install is recorded and
  shows no drift; a wrong yt-dlp or a missing one is not recorded).
- Captions went back to white about 0.3 s before a leaving scene's paper was gone (the ink ended halfway
  through the exit). The ink now holds until the scene's ground is gone from under the captions, per exit
  (iris, match, push, wipe, block, fade; `remotion/src/ground.ts`); a scene held under the next keeps it to its
  end. quality.py skips inked pages up to the scene's end. Test: `tests/test_record.mjs` (halfway through an
  iris out the ground still covers a caption at 75%; nearly closed it does not).

- Caption pages wrapped to two lines and mixed sizes inside one page (the sample's "down competitor ads",
  "for one substitute"): the stressed word was drawn 1.15x bigger and a page could wrap to two lines. Now a
  page is one line at one size (`max_lines` defaults to 1, fitted at the stressed weight with room for the
  active word's pop, never wrapped); the stressed word draws in the emphasis colour and one weight heavier,
  never bigger (`emphasis_scale` is no longer read). `check.py render` counts the lines of every page and
  FAILs one over `max_lines`. On the sample: 6 of 58 pages on two lines before, 0 of 57 after. Test:
  `quality.py demo` (a page on one line reads 1, wrapped reads 2); `caption_lines` on the old sample
  render finds the 6 pages.
- The opening card was the site's headline as a sticker with its lines touching and a kicker too small to
  read. capture.mjs re-sets a sticker sentence at leading 1.2 or more and drops the page's emoji; plan.py
  leaves a line under 28 px x-height out of a sticker cut from a shot; `check.py plan` FAILs a sticker that
  still shows one, and a capture on the hook (first 3 s) with no `find` mark. plan.py now keeps each mark's
  `find` in the plan for that check. Test: `tests/test_record.mjs` (a 0.85 line-height headline with an
  emoji: leading 1.20, no emoji), `check.py demo` (the sample page's 58 px kicker over its 212 px headline is
  left out of the crop; a hook capture without `find` FAILs, with it passes, also after planning).
- Two pacing rules contradicted each other in style-edit ("a card every 4-6 s", "most sentences get
  nothing") and the sample had 11.5 s (10.6-22.1 s) with no card. One rule now: a card where a sentence names
  something real, never two at once; no stretch without a card over `card_gap_s` (10 s, or twice a copied
  creator's measured gap, `120 / graphics.per_min`). In a longer stretch that names nothing, plan.py adds a
  zoom change at least every 5 s instead of a made-up visual, and prints what was named there from
  beats.json; `check.py plan` WARNs a longer stretch that names something or holds still over 5 s. On the
  sample the "decisions" and "40 to 200 times faster" lines now show the TypeSafe pages that say them:
  longest stretch with no card 11.5 s before, 8.4 s after; 5.3 cards a minute before, 6.6 after. Test:
  `plan.py demo` (a sparse creator's zooms get a change every 5 s inside a quiet stretch, untouched outside;
  `card_gaps`, `card_gap_s`), `check.py demo` (a named thing in a long gap WARNs, a moving frame with nothing
  named passes, a still one WARNs).
- `check.py render` WARNed caption contrast (4.36:1 at 20.77 s) that "plan again" never fixed: plan.py aimed
  at 3.3:1 (the FAIL line) while the render WARNs under 4.5:1. plan.py now aims at 4.7:1. On the sample the
  worst caption reads 11.7:1, no WARN. Test: `plan.py demo` (mid-grey footage at 4.48:1 gets a treatment).

- Explaining cards on vertical rendered small and off centre (backlog Now 1). plan.py placed a `flow` as a
  box in the 21%-tall band above the head (its cards pushed right, `check.py render` FAILed it at +5.6% while
  `check.py plan` passed), and a `logo_cluster`'s logos at about 6% of the width at the frame edges. Now on
  vertical a `flow` is always a full-frame scene (an `icon_burst` sits in the split panel), as style-edit
  step 3 says; the diagram centres its cards and, in a portrait box, stacks the task chips over the source
  instead of a lane to its left and lets the cards grow to 340 px (from 240). A vertical `logo_cluster` gets `band` [17, 83] and `size` 20: logos 20% of
  the width, spread over a band centred on the frame, above the head. A `logo` card leaves when its sentence
  ends. `check.py plan` estimates where a vertical flow or logo_cluster draws (the renderer's layout) and FAILs
  one under 60% of the width or off centre; `check.py render` FAILs the same, and both point the fix at the plan.
  While a scene is landing or leaving, captions keep their own colour (the scene's ink only once its
  transition is half done), and quality.py does not read inked scene captions as white ones. Logos: Simple
  Icons, then the site's own SVG or apple-touch icon, before the 256 px favicon service (the sample's
  TypeSafe logo is now its 400 px PNG). Test: `check.py demo` (the sample's flow in the band FAILs with a
  plan fix; as a scene it passes; a cluster without its band FAILs, with it passes), `plan.py demo` (layouts,
  the band, a logo off at its sentence end), `tests/test_record.mjs` (logo source order).
- `profile.py style edits/<name>` crashed with `FileNotFoundError` on every first video, because start runs it
  before cut makes the folder (backlog Now 2). It now creates the folder. Test: `profile.py demo` (a missing
  `edits/new` exits 0 and holds `style.json`).
- Whisper's stretched word labels sent the cut into a false loop (backlog Now 3). A label far longer than the
  word can be said in (over twice a speech-rate length; an "if" at 0.7 s, an "I" at 3 s) is fitted to where
  the audio has energy in or just after it, so a pause cut no longer "clips" a word the render plays.
  `build_timeline.py` prints the fitted labels and keeps them in `report.json`; `paper-edit.md`, `words.json`
  and `verify_cut.py` all judge the fitted words, so they agree. Alternate hooks match on the word sequence:
  a take whose first word Whisper hung on the phrase before it ("more tips I | built a model router") is
  found, and no other candidate reaches into it. Test: `test_build_timeline.py` (a 3 s label ahead of its
  audio: a false CLIPPED before fitting, none after, the paper edit plays the kept words) and
  `test_retakes.py` (the sample's Whisper words, `testdata/sample-whisper.json`: the late hook run is found
  from 179 s with the stray "I" attached).

- `login.mjs logout ..` deleted the whole editor folder, and `logout /` every saved login (backlog Now 1).
  `domainOf` fell back to the raw text. Now a site must be a plain hostname (or an http(s) URL whose host is
  one), and the profile folder must sit directly inside `<home>/browser/`; anything else (`..`, `/`, empty,
  `.`, `a/b`, a drive letter, `%2e%2e`) exits 2 and deletes nothing. `where`, `check` and `login` use the
  same check. Audit of every other delete in the repo (`rmSync`, `rmtree`, `unlink`, `os.remove`): each
  works on a temp folder or a fixed name inside the edit folder; none takes a path from the user. Test:
  `tests/test_record.mjs` (in a temp `AI_EDITOR_HOME`, 12 bad names exit non-zero and the home and both
  profiles survive; `logout https://www.example.com/settings` removes only `browser/example.com`).
- An ordinary download error asked for the browser login (backlog Now 2). `links.py`'s `LOGIN` matched
  the bare "age" in "webpage", "image" and "storage". It now matches whole words and real gate messages
  (sign in, login, private, members-only, age-restricted, confirm your age). Test: `links.py demo`
  ("Unable to download webpage: HTTP Error 404" is not a login; "age-restricted" and "Log in for access" are).
- The product-video music step ran a bare `yt-dlp` with `--cookies-from-browser chrome` behind
  `--yt-cookies`. It now runs the venv's pinned yt-dlp (`links.ytdlp()`, which also prefers the venv over a
  copy on PATH now), never passes cookies by default, and stops with `LOGIN:` when the site wants a login,
  so the skill asks in the question box before `--cookies-from-browser <browser>`. Test: `product.py demo`
  (the default command has no cookies flag; the named browser goes through only when given).
- Keys from the working folder (backlog Privacy). `keys.py` and creator-teardown's `transcribe.py` read a
  `.env` in whatever folder Claude Code started in, so another project's key could be billed. Now only the
  environment variable and the key file (`$AI_EDITOR_HOME/.env`, else the shared one). Test: `keys.py` and
  `fetch.py demo` (a `.env` with a key in the working folder is not read).
- Key files are created readable by the user only (0600) instead of written and then chmodded: `keys.py`
  (`write_private`), `setup.py awskey` (aws.env) and creator-teardown `fetch.py setkey`. Test: `keys.py`,
  `setup.py demo`, `fetch.py demo` (umask 0 and chmod disabled: a new file is still 0600).
- GitHub renders no longer run `gh auth setup-git`, which rewrote the user's global git credential helper.
  The render repo gets its own `credential.helper` (`git config --local`, cleared, then `!gh auth
  git-credential`). Test: `edit.py demo` (no `setup-git` in `github_push`; every credential command is
  `--local`).
- Cloud renders delete the uploaded footage after the download. GitHub: `github-fetch` deletes the `media`
  release (and tag) and the run's artifacts; the video artifact is kept 1 day, not 7. Lambda: `render.mjs
  lambda --cleanup` deletes the deployed site (the footage) and the render's objects from S3. style-edit
  asks once "Delete the uploaded footage from <GitHub|AWS> after rendering?" (Yes recommended) and keeps
  the answer as `cloud_cleanup` in the profile; with no, the run says where the footage is. Modal already
  deleted its volume folder. Test: `edit.py demo` (a mocked `gh` deletes the release and both artifacts,
  never the repo) and `tests/test_record.mjs` (a mocked Lambda client gets `deleteRender` and `deleteSite`,
  called only after `downloadMedia`).
- Saved logins are shown: `setup.py doctor` lists each logged-in browser profile with when it was last used
  and how to delete it ("log me out of <site>"), and setup asks whether to delete them. product-video says
  where the login is kept at the end of a logged-in run and offers `logout` once the video is approved.
  Test: `setup.py demo` (two profiles listed with their age, a folder with no profile left out).
- Linux captures kept Chrome's sandbox off on every site. `capture.mjs` and `record.mjs` now launch with the
  sandbox and turn it off only when a probe launch fails with a sandbox or namespace error (blocked user
  namespaces, running as root), and say so. Test: `tests/test_record.mjs` (`noSandbox`: on for a working
  sandbox and for an unrelated crash, off only for a sandbox error on Linux, never off on Mac or Windows).
  The Remotion renderer, which opens only the local bundle, is unchanged.
- The live preview took requests from any page. `preview.py` now binds 127.0.0.1 only (checked) and puts a
  random token in the URL; the page gets it as an HttpOnly, SameSite=Strict cookie, and every request
  without it (page, script, state, media, changes, Render) gets 403. Test: `preview.py demo` (a real
  server: no token is 403 on every path and writes nothing; the token then reads and writes).

- Alternate hooks recorded after the call to action stay out of the main cut (backlog Next). A take that
  ends with more takes of the opening line had "last take wins" moving the hook to the end. `retakes.py
  propose` now finds them (more than 40 s after the opening, at the end of the recording, each under 30
  words), cuts each from the main cut as `alt_hook` (never judged as a retake), keeps the hook at the start
  (its last good take there, as before) and lists them in `hooks.json`; `candidates.md` lists them without
  a key. After the cut is approved the cut skill asks once whether to render one version per hook:
  `retakes.py hook edits/<name> <n>` writes `edits/<name>-hook<n>/` (same body, the opening cut, that
  alternate kept) with `lead.json`, which `build_timeline.py` plays first. Test: `test_retakes.py`
  (opening, body, call to action, then two more takes of the opening: the hook stays first, both late
  takes are one `alt_hook` span, the main cut ends on the call to action, and the hook-2 variant opens on
  the body with alternate 2 kept and the others cut; `lead_first` moves and splits frame ranges).
- Key paths with `AI_EDITOR_HOME` set (backlog Next): README troubleshooting no longer gives
  `plugins/ai-editor/...` paths that exist only in a cloned folder; it says what to ask Claude, with the
  path for Way 1 marked as such, and a "Where are my keys?" row. `style-edit/references/contracts.md`,
  the `gemini.py` docstring and the cut `transcribe.py` docstring say `$AI_EDITOR_HOME/.env` when it is
  set; the transcribe "no ElevenLabs key" error names the file it actually read.
- Opt-in loudness fix (backlog Next): the sample take plays at -24.7 LUFS and every first render WARNed
  with no fix. When `check.py render` WARNs on loudness, style-edit asks once, default "leave my audio as it
  is"; on yes, `quality.py normalize <render>` writes `<render>-normalized.mp4` with one gain to -14 LUFS,
  never past a -1 dBTP peak, no compression, limiter or denoise, the original left as it is. Test:
  `quality.py demo` (`gain_db`, and a -30 dB tone normalized to -14 +-0.5 LUFS).
- doctor's key lines say `Say "add my <name> key": setup saves it from your clipboard`, the same one
  instruction as setup step 5, instead of "Run in a terminal: ... setkey" (backlog Next). Test:
  `setup.py demo` (`key_line`).

- Fewer bytes before the first step (backlog Next, cost). Each skill's required reads (SKILL.md plus every
  file it says to "Read ... first") now fit a budget that `tests/check_plugins.py` enforces: start 12 KB,
  cut 15 KB, style-edit 25 KB, product-video 30 KB. Before and after: start 15.6 to 12.0 KB (the intake
  tables moved to `start/references/intake.md`, read only when `profile.py missing` prints an id), cut 17.7
  to 15.0 KB, style-edit 39.5 to 23.1 KB, product-video 21.9 to 22.0 KB. The shapes Claude writes live in
  one short file per skill: `style-edit/references/shapes.md` (images.json, visuals.json for every pick,
  the rules plan.py enforces; 4.1 KB, read first instead of the 20.5 KB `visuals.md`, and step 3 points
  there instead of the 23.1 KB `contracts.md`, now marked for people), `cut/references/shapes.md`
  (spans.json, out of `retake-detection.md`), `product-video/references/shapes.md` (brief.json,
  story.json beats). The `template-filler` agent reads shapes.md too. Test: the new check fails on the
  old files (start 15,565, cut 17,651, style-edit 39,524 bytes) and passes on the new.
- product-video's brief names `product.py copy` (backlog Next): step 1 runs it after the home-page crawl,
  and it now prints a `tagline:` line (the site's description, else its h1) and a `nav:` line before the
  headings, so the options come from it and Claude never reads `site.json` (about 20 KB). crawl.mjs says
  `logo text "Acme"` for a wordmark logo instead of `logo undefined`. Tests: `product.py demo`
  (`brief_lines`), `tests/test_record.mjs` (`logoNote`).
- Captions join Whisper's hyphen tokens: "one", "-for", "-one" is one word, "one-for-one", in one caption
  (it showed as "one -for -one"). plan.py joins any token starting with "-" to the word before it before
  chunking. Test: `plan.py demo`.
- The stills sheet runs in time order with no gaps in its numbers: each tile is "N  what it shows  time
  kind" (card N is `plan.cards[N-1]`). It showed "1-opening 0.50s" before "2-caption 0.23s" and skipped 3
  when there was no zoom. Test: `sheet.py demo`.
- `check.py render` with an empty style file (the no-creator default) says it is the default style instead
  of "no --style". Test: `check.py demo`.
- clips fetches a link with `links.py fetch` (the venv's yt-dlp; setup does not put yt-dlp on the PATH)
  capped at 1080p (`--max-height 1080`): step 1 ran bare yt-dlp at up to 2160p, several GB for a
  20-minute talk cut to 1080x1920. Every yt-dlp fallback format now carries the height cap. Test:
  `links.py demo`.
- clips shortlist "names:" lists real names: the profile's names and capitalised words that do not start
  a sentence (a sentence that ends on a pause with no full stop counts), are not single letters and are not
  also said in lower case. It listed "And", "So", "What", "T". Test: `clips.py demo`.
- Teardown measures print one line, not their JSON. `graphics.py measure` (246 lines of JSON on the audit
  run), `visual.py measure` (40) and `sound.py measure` (29) each print one summary line ending in the
  style.json path and the block's name; `--json` prints the full block. `graphics.py merge` does the same,
  and `gemini.py kinds` prints its kinds on one line. Test: each script's `demo` asserts the summary is one
  line with no JSON.
- Teardown look.md reads right without a Gemini key. The font line says "not named (no look pass ...)"
  instead of the "[from the look pass]" placeholder. Graphics numbers come from one source: graphics.py's
  per-card measure (new `graphics.share_pct_measured`, the hold over runtime report.py shows per video)
  when it has run, else look.py's frame estimate labelled as such (the audit's "on screen 55%" next to
  "winners 2, control 0" came from the two sources). look.md names each AI tell with its level and where it
  fired. `report.py build` rewrites look.md from the final style.json (it stopped before graphics, sound and
  the tells). The palette tells read `graphics.palette`, the palette look.md prints and ai-editor copies,
  not `crop_palette` (the colours inside captured pages): a black and brown palette no longer gets
  "purple-blue" or "cream-paper-ground". Tests: `look.py demo`, `report.py demo`.
- Teardown says what `--top N` downloads: SKILL.md says N plus 2 control videos (`--top 5` is 7, the
  default 10), and `visual.py download` and `fetch.py transcribe` print the count first ("5 most-viewed +
  2 control (closest to the median) = 7 videos"). Test: `fetch.py demo`.
- `profile.py set` takes several answers in one call: `set platform=youtube sound.music=false
  'names=["X"]'` writes them all and prints one line (an intake took 12 calls, each printing the full
  path). The old `set key value` form still works, and a value may hold `=`. start's `intake.md` shows it.
  Test: `profile.py demo` sets four pairs, one a URL with `=` (the old code stored `"sound.music=false"`
  under the key `platform=youtube`).
- doctor checks free disk: under 3 GB it FIXes with the reason (setup installs about 1.5 GB, the cutout
  writes about 0.5 MB a frame, about 0.9 GB a minute at 30 fps) and what to delete, and ends "Not ready".
  Test: `setup.py demo` feeds `disk_row` 5 GB (ok) and 2.9 GB (FIX with the reason).
- Isolated runs never touch real keys: with `AI_EDITOR_HOME` set, both plugins read and save keys in
  `$AI_EDITOR_HOME/.env` first and never open `~/.config/creator-teardown/.env` (`keys.py`, and
  creator-teardown's `transcribe.py` key lookup that `fetch.py` and `gemini.py` share). Test: the
  `keys.py` self-check finds a key in a temp `AI_EDITOR_HOME`, saves there, and finds none once that file
  is gone.
- README: the laptop render is no longer "the slowest option". On the 46.8 s sample `edit.py estimate`
  gave laptop 63 s, Modal 2.0 min and GitHub Actions 7.7 min, and the laptop render took 42 s.
- Product film: no blank frame, no headline cut by the edge, a wrong step number explained (backlog Now 1).
  The framing check now reads every frame of the plan for content (`journey.blank_frames`: the same edge
  cells as the fill guard, over every page the frame touches, moves and state changes included; under 4% is
  blank) and fails any held line of text cut by the frame edge where no edge fade covers it (a headline cut by
  the top or bottom edge deeper than the fade's 12% of the short side used to pass as "every frame holds").
  The planner fixes both: a held framing is re-framed as before, and a move that crosses a blank frame lifts
  higher (a "lift" on the key it moves to, raised each replan round) until the frame keeps product in view;
  what is still blank or cut FAILs `product.py plan` with its times. A beat's `steps` (or `after`) past its
  flow's steps exits with one line naming the beat, the flow and each valid step (`0 click 'text=Search'; 1
  write 'github'`) instead of an `IndexError`; `story.md` says the numbers skip waits and auto scrolls. Tests:
  `journey.py demo` (a bottom-cut headline fails and replan clears it; a move down 1800 px of page whitespace
  fails with blank frames and passes once lifted; `"steps": [5]` gives the one-line message). Four real
  stories (two sites, both aspects) plan with no new failure.
- Captures on vertical read on a phone (backlog Now 2). plan.py measures a capture card's evidence text (the
  lines under its marks or highlight, else its headline) from its DOM line boxes at the size the card draws it
  (`capture_xh`: line box x 0.42, at the browser window's, shot's or sticker's own fit). On 9:16 a shot or
  browser capture under 28 px x-height becomes a sticker cropped to that evidence, the crop taking the band's
  shape at the largest size that holds it (never past 1:1), every line whole. `check.py plan` FAILs a capture
  card still under 28 px on vertical (the plan used to pass with 0 FAIL). Test: `check.py demo` with the
  audit's two browser captures planned as boxes about a fifth of the frame tall: 22 and 16 px, both FAIL;
  after `readable_captures` 39 and 53 px, no FAIL. With no head found, a capture on vertical takes the
  overlay band (4-96% wide, from 10% down) instead of the 72%-wide default box. `tests/smoke.py`'s page
  capture is now a sticker on its first sentence: example.com's body text as a shot read at 4 px.
- Tests clean up: `tests/smoke.py` and `tests/golden.py` delete their temp folder on success (they kept
  every one outside CI: 1.6 GB of `ave-smoke-*` and 467 MB of `ave-golden-*` on one machine) and keep it
  only on failure, printing its path. The Linux golden stills take the card timing change.
- The no-creator path renders a lively edit (backlog Now 1). "No creator" is the recommended answer, so it
  has a style of its own: `profile.py style edits/<name>` writes `DEFAULT_STYLE` when the profile has no
  creators (it used to exit `no creator style.json found`), and `plan.py` plans with it when style.json is
  missing or empty, with a one-line note instead of a `FileNotFoundError`. The default follows PRINCIPLES
  (smooth, overlay-first) and takes each number from the median of three measured styles: punch zooms to
  1.18 that the renderer eases (never a one-frame snap), 9.5 a minute on sentence starts, the smooth
  personality, 3-word lower-case captions at 5.5%, no stroke unless the footage needs one (style-edit
  `references/plan.md` "No creator"). New `zoom.max_hold_s` (5 s in the default): a long sentence still
  gets a zoom change on the word nearest its middle. A zoom change never lands during a card's entrance
  (`plan.clear_entrances`), and cards are placed off the head as drawn under the zooms, inside the same
  14% side margins `check.py plan` holds (logos could land under the right rail or behind a zoomed head).
  A slow push was tried first: the render check read the speaker's own movement during a 0.8 s push as a
  surge. The outline-jitter check skips frames where a cut or zoom moves everything. Tests:
  `profile.py demo` (no creators writes the default; now in `tests/demos.sh`), `plan.py demo` (a missing
  style plans with a note, the default puts a zoom change at least every 5 s on a 47 s cut where `{}`
  planned none, a logo beside a zoomed head clears it). Sample take, no creator, end to end: 7 zooms and
  4 cards, `check.py render` 0 FAIL and no "nothing moves" (was 0 zooms and "nothing moves for 32.4 s").
- plan.py's output passes check.py render (backlog Now 2). Contrast: plan.py aims at `CONTRAST_TARGET`
  3.3:1, the FAIL line plus 10%, and quality.py takes its FAIL line (`CONTRAST_MIN`, 3.0) from plan.py, so
  the two cannot drift. "Plan again" now changes something: `check.py render` lists the caption pages it
  read under 3.3:1 (`caption_contrast.low_at`), and the next plan.py run gives each one the next step
  (shadow, stroke, backing), kept in `contrast.json` and read once per check. Card timing: plan.py,
  the renderer and the render check share one lead model: an overlay starts `CARD_LEAD_S` + `OVERLAY_LEAD_S`
  x k before its word (0.1 + 0.07 s, the time the drop-in takes to carry half its ink), and motion.ts
  starts the drop-in there from the same two numbers (it was 0.3 s x k, so captures landed 0.19-0.28 s
  early). `plan.py demo` fails if motion.ts drifts from plan.py. Tests: `plan.py demo` (a grey the shadow
  lifts only to 3.15:1 now gets a stroke, every pick reaches 3.3:1, a low page steps up once per check).
  Sample take: captures land 0.12 and 0.13 s before their words, no "before its word" WARN. Golden
  stills (darwin) updated: the terminal card starts 0.23 s later, so its typing is one letter behind at
  the still. Linux goldens need the CI `golden-out` artifact.
- Misheard names are not cut errors (backlog Now 3). `verify_cut.py` matches the second pass to the cut's
  words by time (`textnorm.pair_by_time`): a kept word heard differently at the same time is listed
  under HEARD DIFFERENTLY ("jev -> jeff x4, claude -> cloud"), never MISSING, so there is no `--pad`
  rebuild for it. New `retakes.py captions edits/<name>` builds captions.json (and captions.txt to
  proofread) from the second pass's words and times, with each word it heard differently spelled as the
  approved cut text has it, the profile's `names` spellings, and every `retakes.py fix` applied (fix now
  keeps its pairs in `fixes.json`). style-edit step 2 runs it instead of copying cut.transcript.json and
  proofreads captions.txt, the file captions are built from. `check.py render` no longer LOOKs at a
  caption that matches the cut text. Tests: `test_retakes.py` (captions take "Jev" and "Claude" with no
  fix call; a fix applies to a later captions run; a misheard name is HEARD DIFFERENTLY, a word with
  nothing heard at its time is still MISSING). Sample take: verify prints 0 MISSING (was 6), and
  captions.json holds "Jev" x4 and "Claude" with no fix.

- No half-cut text at the frame edge (backlog Now 1). `record.mjs --states` records each state's
  text line boxes from the DOM (Range.getClientRects per text node, one box per line inside one
  block, overflow-clipped and hidden text left out) and its pictures' boxes; OCR reads text inside
  pictures, and whole states recorded before this. Each held framing keeps every line wholly in
  frame or out: the focus grows to the lines it holds part of, then the camera shifts or widens within
  the key's limits and the resolution floor, never onto emptier ground (`journey.text_guard`); a
  line it cannot clear, off the focus, fades out at that edge (`journey.edge_fades`, drawn by
  Journey.tsx); a cut line on the focus FAILs the plan. `product.py check` reads the render with OCR at
  2 fps: a word running into the frame edge is a WARN, on the focus a FAIL. Style-edit captures:
  `capture.mjs` grows a shot's clip so no line crosses its edge (`snapClip`) and lists the PNG's
  line boxes; a sticker's crop keeps every line whole (`plan.py whole_lines`) and `check.py` FAILs a
  crop that cuts one. Tests: `journey.py demo` (a framing that cuts a line fails, the guard re-frames
  it, an unclearable line gets an edge fade, the OCR edge rule), `check.py demo` (a sticker trim that
  cuts two lines fails, the planned crop passes), `tests/test_record.mjs` (snapClip; the DOM line
  boxes on a page with two columns, an overflow clip and hidden text). linear.app 16:9 and nextwork
  9:16 re-rendered as v7: cut-text WARNs 6 to 0 and 6 to 1 (a filter chip the page scrolls under its
  own edge), 0 FAIL, meter inside the Linear bar (judder 0, stops 0.4 and 0.23 per 10 s, jerk p95
  1888 and 1436). Where a paragraph sat beside the focus, the framing is now wider, so the type is
  smaller.

- Product films, v6 (backlog item 9). Sparse dark sites: the plan estimates how much of each framing
  is product (edge cells of the states on screen, the measure `check` uses) and re-frames any under
  50% tighter onto the busy part, its focus kept whole and above the words (`journey.fill_guard`); a
  flow whose first action is far down its page starts there instead of the camera falling thousands
  of px down it. linear.app, re-crawled and run end to end with the beats flow, passes the fill check
  (0 FAIL; the old shot film filled 12-44%). Resolution: states were already 3x on desktop and phone;
  every layer now records its picture's own px per page px and the per-frame framing FAILs any frame
  that shows a state past it (`journey.py demo` covers it); after the plan each state is cut to what
  the camera shows of it (`journey.crop_layers`, Journey.tsx draws the crop). The score follows the
  cut: a section per story beat (pads on the hook, the groove on actions and results, the fullest on
  the payoff), the chord changing where a beat starts, voice-led pads, a bass line that steps into
  each change, brushed ticks under 3.5 kHz, pads breathing with the sub, a riser into the payoff and
  the tonic ringing over a low tonic and a bell on the logo; typing ticks 6 dB louder (`sound.py demo`
  checks the hook has no pulse, the groove arrives with the first action, the tone sits in Linear's
  trailer's bands, and voice leading). The fade to the logo no longer repeats a frame: the ground
  fades in on a straight ramp and the canvas out on sine.in, so no ease-out tail rounds to a held
  frame (meter: judder 0).

- Pinned everywhere. The matting image on Modal (`matte.py --modal`) installed numpy, opencv and
  onnxruntime unpinned; it now installs requirements.lock's lines for them and what they pull in,
  hash-checked (`--no-deps --require-hashes`), built by the new `lib/ai_editor/lock.py`
  (`matte.py demo` records the image spec and fails on an unpinned package or a version off the
  lock). `modal_render.py` installs no Python packages (npm ci from package-lock.json), so it was
  already pinned. creator-teardown on its own printed `pip install faster-whisper numpy ...
  yt-dlp` and, past 90 days, `brew upgrade yt-dlp`: its doctor now points at ai-editor's
  `setup.py bootstrap` / `repair` when that plugin is installed, and otherwise at its own
  `requirements.lock`, ai-editor's exact pins for what it uses (yt-dlp, faster-whisper, numpy,
  pillow, opencv, the OCR engines) with hashes. `tests/check_plugins.py` fails when that copy
  drifts (`python3 plugins/ai-editor/lib/ai_editor/lock.py teardown` rewrites it); `fetch.py demo`
  fails on any unpinned, brew, pipx or winget install line. fetch.py now uses the venv's pinned
  yt-dlp before one on PATH.
- Weekly CI (`.github/workflows/weekly.yml`, Mondays). `yt-dlp`: lists one TikTok and one YouTube
  video with the pinned yt-dlp and with the lock re-resolved to the newest yt-dlp; a list the pin
  fails and the newest passes opens (or comments on) a "Refresh requirements.lock" issue and fails
  the run. `python-new`: the lock and every demo on the newest released Python, allowed to fail,
  reported in the run summary. The demo list moved into `tests/demos.sh` (check.yml and weekly.yml
  both run it; it gained `lock.py demo` and `matte.py demo`). RELEASING.md "Refreshing the lock":
  the monthly refresh and what to run after it.
- Links. A YouTube `/channel/UC...` (or `/c/`, `/user/`) link now routes to the creator's @handle:
  `links.py route` asks yt-dlp for the channel page alone (`--dump-single-json --flat-playlist
  --playlist-items 0`, under a second) and drops the "read the @name off the channel" note. A
  Spotify episode or show link routes to clips with the same episode's audio from the show's own
  RSS feed: the episode and show names from Spotify's embed page (its oEmbed carries only the
  episode title, and for a show the latest episode's), the feed from the free iTunes Search API
  (exact show-name match), the episode by title; `fetch` does the same. Offline, the old note
  stays. `links.py demo` covers both with canned responses; `links.py live` checks the YouTube
  channel and a long-running public podcast (weekly CI runs it).
- Renders under load (backlog item 10). Once, under heavy load, an `edit.py stills` frame timed
  out in delayRender while fetching cut.mp4 (Remotion's 30 s default). render.mjs now gives every
  delayRender 120 s (stills, renders, chunks, the benchmark), retries a still once on a timeout,
  and renders with half the cores' tabs when the 1-minute load average is over 70% of the cores.
  `tests/smoke.py --load N` runs the smoke test beside N busy loops; it passes at `--load 112` on a
  14-core Mac (load average 130).

- Start in the repo (backlog item 10). Opening a clone or the zip download in Claude Code and
  trusting the folder now loads ai-editor and creator-teardown from that folder: a committed
  `.claude/settings.json` registers the repo as the `nextwork` marketplace by local path (`./`) and
  enables both plugins (checked headless in an empty `CLAUDE_CONFIG_DIR`, git clone and zip alike).
  A root `CLAUDE.md` sends "edit my video" to `start`, and when the plugin did not load, asks to
  install it with the two `claude plugin` commands; it tells contributors to skip all this.
  `AGENTS.md` and `GEMINI.md` open with the same instruction for Codex, Cursor and Gemini. What users
  make in the folder (`edits/`, `clips/`, `product/`, `creator-teardowns/`, root videos) is
  gitignored. README rewritten for someone who has never used a terminal: three ways in with the
  commands per computer, what happens next, what to say and paste for each skill, the cost table
  with estimates marked, troubleshooting from the scripts' own messages, contributing. New eval
  `repo-no-plugin` (offers to install, then hands to `start`); `tests/check_plugins.py` fails when the
  settings entries, the three start paths in README, the AGENTS.md first lines, the GEMINI.md copy or
  the eval's copy of CLAUDE.md drift.
- Skill quality pass. Every first-party SKILL.md is under 250 lines (style-edit 305 -> 230, setup
  283 -> 193, product-video 263 -> 244, creator-teardown 251 -> 242), detail moved one level down
  with a pointer saying when to read it: `style-edit/references/plan.md` (what plan.py does, the
  cutout, sound, music, the check lists) and the live preview into `render.md`;
  `setup/references/keys.md` and `cloud.md` (Modal, GitHub CLI); `product-video/references/brief.md`
  (music rights, logging in); `creator-teardown/references/blend.md` and `outputs.md`. Each skill
  has an "If a script stops" table built from its scripts' own messages. Triggers no longer collide:
  "edit this like @creator" is start's alone (creator-teardown and style-edit dropped it), style-edit
  fires only once a cut exists, cut no longer quotes "edit my video", setup dropped "get started".
  creator-teardown defines the quick mode start and setup call. The question boxes keep to four
  questions a call (start's intake, product-video's brief now three calls), recommended first, and
  setup asks before it starts. style-edit proofreads captions from `paper-edit.md` instead of the
  caption JSON; `retakes.py fix` now fixes `captions.json` and `cut.transcript.json` too
  (`test_retakes.py`). `tests/check_plugins.py` fails a first-party SKILL.md over 250 lines and a
  quoted trigger phrase claimed by two skills' descriptions
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
