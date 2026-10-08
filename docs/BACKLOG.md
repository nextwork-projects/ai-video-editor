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

- An RSS feed link downloads the wrong thing. `route` sends a podcast feed (442 episodes) straight
  to clips with no episode chosen; `fetch` then runs yt-dlp with `--no-playlist`, which does not stop
  a feed: `yt-dlp --no-playlist --simulate` on it was still walking episodes after 5 minutes. The
  item's name is the feed host and the start of its path, cut at 40 characters. clips/SKILL.md never mentions podcasts,
  Apple Podcasts or RSS, though the README lists them. Done: a feed becomes an `ask` with its newest
  3 episode titles as options, fetch downloads only the chosen enclosure, the name is the episode
  title, clips/SKILL.md says what a podcast link does.

- Someone else's short video recommends editing it as your own. A public agency's TikTok (136 s) and
  YouTube Short (39 s), pasted without "my", route to `ask` with **Edit it as my video** first, which
  start makes "(Recommended)". start/SKILL.md:49 says "a creator's video is for the teardown, not to
  re-edit". The item has no question text, so the model writes its own. Done: without `--own`,
  "Copy this creator's style" is first; each `ask` item carries the question wording.

- "Finish setup" after the one-command install finds nothing to finish. After `bootstrap`, `setup.py
  todo` prints "Nothing saved for later." while three keys, the style questions and Modal are all
  missing (doctor shows them as `--`). `setup.py later bogus` is accepted, exit 0, and saved.
  setup/SKILL.md:22 says "fill the times from doctor once it has run", but doctor prints no times.
  Done: `todo` lists every missing optional step (keys, style, modal, matte), `later` rejects unknown
  steps with the list, doctor prints the step times the plan quotes (or the SKILL gives them).

- A browser capture with no `find` becomes a sticker of the page's headline. plan.py printed "'Jev'
  images/capture-1-jev.png: browser text would read at 22 px x-height; cut to the evidence as a
  sticker, 39 px" and the stills show the site's own four-line headline, which the speaker never said,
  with lines set so tight their letters touch (stills 4-6). shapes.md bans the headline only on the
  hook. The message does not say whether plan changed it or the model should. Done: an automatic
  sticker needs a said phrase on the page, else the card drops with a warning naming why; sticker
  leading matches the caption's; the message says what plan did.

- A one-frame zoom snap on a fresh install. `check.py render`: "WARN 28.05s the punch zoom at 28.05
  s snaps in one frame -> render with the current StyleEdit.tsx". The renderer is the current one, so
  the fix is meaningless; frames at 28.0 and 28.1 s show the jump, next to the flow scene that
  starts at 28.2 s. Also "WARN 8.14s 'Claude' logo's outline turns back at speed 4 time(s)" on the
  default style. Done: the sample's default render has no zoom or jitter WARN, and every WARN's
  fix is an action the model can take.

- No named things are found when the names question is left blank. The sample take names Claude,
  Jev, Haiku and Opus; `route.py beats` gave `"names": []` on all 13 sentences because it only
  marks the profile's `names`, and that question is free text with no default. A beginner on the
  sample take gets no logos or captures unless the model invents them. Done: route.py also marks
  product names it can resolve to a logo or domain, or the sample take comes with its names; the
  sample's beats list the four.

- Output a new user cannot read. face.py and `check.py render` print OpenCV's "[ WARN:0@0.140] global
  net_impl_backend.cpp:345 setPreferableTarget Targets are not supported by the new graph engine";
  `edit.py stills` prints 15 and the render 35 "GSAP target undefined not found" lines; bootstrap
  prints raw download URLs with commit hashes, npm's "added 369 packages in 3s" and "Has browser at
  /private/..."; `transcribe.py` prints "re-heard 'one' 132.34-133.70s" lines; `profile.py style`
  prints "the default style (DEFAULT_STYLE)"; plan prints "cues sit 5-4 dB under it". Done: library
  noise filtered, one plain line per step, the GSAP warnings fixed at their source.

- `verify_cut.py` SURVIVED gives no time: "... less than five cents [and] and to break down ...".
  cut/SKILL.md step 5 tells the model to map the cut time to source time with decisions.json, but no
  time is printed, and the doubled "and, and" went on into captions and the render. Done: each
  SURVIVED line prints its cut time and source time and the span to add.

- Intake wording disagrees with itself. start/SKILL.md:70 says "`goal` and `names` belong to this
  video"; profile.py `VIDEO_QUESTIONS` is `audience`, `names`; intake.md has a `set goal` example
  but no `goal` question. intake.md puts the style ids `platform` and `creators` under "Call 1: the
  video", and setup step 8 groups the same questions differently. With no creator, the recommended
  caption answer is "like the creator". `profile.py set` given one `key value` pair followed by
  `key=value` pairs prints only the usage line, not which argument was wrong. Done: one id list and
  one grouping across start, setup, intake.md and profile.py; caption default reads right with no
  creator; set names the bad argument.

- Render estimates and README numbers are out of date. `edit.py estimate` said laptop 75 s ("speed
  from the last benchmark" on a fresh home); the render took 45 s. README "What it costs" quotes
  "the 46.8-second sample, laptop 63 s, Modal 2.0 min"; today's cut is 43.9 s and Modal is quoted
  at 3.5 min. README says Modal is about $0.06 for 60 s and $0.54 for 10 min; setup/references/
  cloud.md says $0.05 and $0.48. Both call the cost "the 3.4-minute sample take" though style-edit
  renders the 44 s cut. The Lambda and GitHub lines do not say "not set up yet" the way Modal does.
  Done: one set of measured numbers, named by what was rendered, in README and cloud.md; the laptop
  estimate within 25% on the sample.

- Stale after today's changes. style-edit/references/motion.md:139 and contracts.md:266 say every
  scene starts `SCENE_LEAD_S` before its word; a hard-cut scene now starts `CARD_LEAD_S` before it.
  creator-teardown references/teardown-page.md:46 says slow-drifting footage "gives no detections";
  `drift_dets` now finds some (see the teardown item above). style-edit/references/plan.md:77 calls
  matte `--modal` cost "not yet measured". agents/render-watcher.md covers local, Lambda and GitHub
  renders, not Modal. contracts.md says a `flow` is "an overlay box by default", but plan made the
  sample's flow a 9.3 s full-frame white scene (28.2-37.5 s) with the speaker gone. Done: each line
  matches the code; flow's default is decided and written once.

- Smaller link-routing gaps. A working Drive share still carries "In Drive, Share > General access >
  'Anyone with the link', then paste the link again", which start says to read out. Drive names are
  unreadable ("drive-1l-5rk28jr"). A Spotify episode resolves to a podcast-analytics redirect URL
  rather than the host's file. An Instagram reel whose probe fails comes back as an `ask` with no
  duration and no note. Done: the Drive note only after a failed fetch; names from the file or
  episode title; the redirect stripped where the feed allows; a failed probe says so.

- style-edit shapes.md never shows that visuals.json is a JSON array of beats; only contracts.md has
  it, and SKILL.md says "never read it to run the skill". Done: shapes.md opens with a two-beat
  example of the whole file.

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

- Cutout model licence: RVM is GPL-3.0 (downloaded at first use, never shipped). intake.md lists
  **Yes** first for "Let graphics sit behind you?", so a user who accepts every recommended answer
  downloads it (16.5 s, third pass).
