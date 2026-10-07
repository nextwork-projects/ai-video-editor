# Changelog

What changed for every user, newest first.

## Unreleased

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
