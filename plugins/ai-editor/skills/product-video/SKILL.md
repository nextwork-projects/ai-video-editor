---
name: product-video
description: Makes a product launch, feature demo or ad video from a website URL. Asks a short brief (what to show, for whom, the end action), crawls the home page and up to 20 inner pages headlessly, ranks the site's use cases in its own words, records real click-throughs of each (clicks, typing, ⌘K, scrolling, desktop and phone size) with a real cursor, and cuts them from a shot library (cursor POV, keycaps, tilted plane, macro rack focus, isometric stack, push-through, split, orbit, whip, grid, type) in a measured style (Linear default, Apple, Stripe, Arc, Raycast). Scores its own music and UI sounds (synthesised, nothing to licence), cuts on the beat, -14 LUFS. 16:9, 9:16 filled by the product, 1:1. Use when the user pastes a website and says "make a launch video for <url>", "product video", "demo video of my site", "turn my landing page into a video", "make an ad from my website", "feature video for <url>". Not for talking-head footage (cut, style-edit) or measuring a creator (creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, Node 20+ and the Remotion renderer the setup skill installs (its Chrome Headless Shell does the crawling). Internet for the crawl. Runs from the full ai-editor plugin folder (uses style-edit's scripts, lib/ and remotion/).
---

# Product video

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video follows (story first, smooth before varied, nothing leaves the frame, privacy, no presses that write).

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

A URL in. A product video out, made only of the site's real UI, real recorded click-throughs of it, its own
colours and type, and its own words, scored and mixed for this cut. `S="${CLAUDE_SKILL_DIR}/scripts"`,
`PY=~/.ai-video-editor/venv/bin/python` (Windows: `%USERPROFILE%\.ai-video-editor\venv\Scripts\python.exe`).
Work in `product/<name>/` under the folder Claude Code was started in.

```
URL -> brief (questions) -> crawl.mjs -> site.json + pages/ (features, pricing, docs, changelog, customers...)
    -> pages.md -> use-cases.md (ranked, quoted, sourced) -> the user picks 2-5, ordered as a journey
    -> storyboard.md (the story first: hook, reveal, each use case as cause then effect, payoff, end)
    -> flows.json (chained) -> record.mjs --states (+ --mobile) -> flows/*.states.json (3x stills of every UI state)
    -> story.json beats -> plan (one camera, every frame checked, score + mix) -> animatic -> critic -> user approves
    -> render (60 fps) -> check (framing, fill, names, smoothness meter)
```

Read `references/story.md` before writing storyboard.md or story.json, `references/style.md` before judging
the animatic sheet, `references/sound.md` before changing the sound and `references/brief.md` for
music rights and logging in.

## 0. Setup

No renderer yet (`~/.ai-video-editor/remotion` missing): run the `setup` skill's Remotion step first.
It installs the Chrome Headless Shell the crawl and the recordings drive. Read the user's taste:
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show`.

## 1. The brief, in the question box, before crawling deeply

Load the home page first (`node "$S/crawl.mjs" <url> product/<name> --pages 0`, about 40 s), then
`python3 "$S/product.py" copy product/<name>`: its `tagline:` and `nav:` lines and the headings under them
are the options, in the site's own words. Never read `site.json` (about 20 KB). Then three AskUserQuestion calls (at most four questions each), the
recommended option first and marked "(Recommended)", "Other" always open for their own words.

**Call 1, the video's job:**

1. **What it does, in one line**: the `tagline:` line of `product.py copy` / Other.
2. **The 2-3 things the video must show** (multi-select): the jobs in `product.py copy`'s headings
   and `nav:` line, each in the site's words.
3. **Who will watch**: new users (Recommended) / existing users / investors / developers.
4. **The one action at the end**: visit the URL (Recommended) / sign up / try a feature.

**Call 2, the shape:**

5. **A page or flow that must be in it**: none (Recommended) / Other (a URL).
6. **Style**: Linear (Recommended: tilted plane, slow drift, blur-dissolves, small low-left words) /
   Apple / Stripe / Arc / Raycast (`references/style.md`, one line each).
7. **Length and shape**: 30 s 16:9 (Recommended) / 30 s 9:16 / both / 15 s. (`--fps 60` on request:
   smoother camera moves, twice the render time.)
8. **Show the logged-in product?** Yes, log in now (Recommended when the use cases live behind a login) /
   Public pages only / Later.

**Call 3, the sound:**

9. **Music**: generated here for this cut (Recommended: synthesised, nothing to licence) / ElevenLabs
   Music (only with their key) / their own track (a file) / a link (YouTube, SoundCloud, Bandcamp) /
   none. A link or a file: ask who holds the rights, then `product.py music` (`references/brief.md` "Music").
10. **Sound effects**: subtle UI sounds (Recommended: clicks and key ticks where the UI acts, a swell into
    the logo) / none.
11. **Voice**: none, on-screen words only (Recommended) / their own recording / text to speech (only with
    an ElevenLabs key).

Write the answers to `product/<name>/brief.json` (shape: `references/shapes.md`). `plan` refuses without it. Example brief for nextwork.ai: must_show = the Create button (prompt your
own project), search other people's projects, roadmaps, step-by-step guides, the portfolio in Your Library.

**Logging in** (on "Yes"): follow `references/brief.md` "Logging in": say where the login is kept
first, then `node "$S/login.mjs" login <url>` opens a separate Chrome window they log in to by hand.
Recording stays read-only (no create, delete, pay, publish or invite without a yes in the question
box) and blurs personal data; show the user the `flows/<id>-blurred.png` sheets before rendering.

## 2. Crawl the site

```bash
node "$S/crawl.mjs" <url> product/<name> [--include <brief urls>] [--pages 20] [--app <url> --cookies cookies.json]
```

About 2-3 minutes. The home page as before (2x tiles, element crops, brand from computed styles, logo,
font files, the page's own videos), then up to 20 inner pages found from the site's own nav and
sitemap.xml, ranked features > pricing > customers > templates > docs > changelog > blog, a few of each,
the brief's URLs first. Each page: its headings and lines, its controls (tabs, buttons, inputs), its
videos and GIFs, a screenshot. Look at `images/tile-0.jpg`: a blank tile means the site blocked the
headless browser; say so and offer another URL.

## 3. Use cases

```bash
python3 "$S/product.py" pages product/<name>
```

Writes `pages.md`: every page compact (never raw HTML), the brief on top; with a TypeSafe key Jev also
ranks the headings that read as jobs (about $0.0001). Read it and write `use-cases.md`: who it is for and
3-4 jobs ranked, each with the site's own words quoted, the source URL, and the flow that would show it.
Brief items first, marked **[brief]**. Ask in the question box which 2-3 to feature (recommended first).

## 4. Storyboard, then record the states

Write `storyboard.md` first (`references/story.md` "Story first"): the beats in story order, each with its
job, its words (the site's, at most ~5), the capture it uses and how it hands off to the next. Order the use
cases as the user's journey, so each one leaves the screen where the next begins.

Then `flows.json`, one flow per use case in that order, **chained**: each flow's `url` is the page the last
one ended on. Steps as in `record.mjs`'s header (`text=<the site's words>` or a CSS selector).

```bash
node "$S/record.mjs" product/<name> flows.json --states            # every UI state as a 3x still
node "$S/record.mjs" product/<name> flows.json --states --mobile   # the phone layout, for 9:16
```

Each flow writes `flows/<id>.states.json` and `flows/states/*.jpg`: the start, each step's after-state, the
focused field and the typed text with the caret measured per character, a tall still for each scroll. It
waits for each view to finish loading (pictures, skeletons) before taking it. Look at the states, not every
file: a loading page, a click that opened the wrong thing, a modal you did not want. Fix the flow and capture again
(`--only <id>`). Without `--states` it records screencasts (`flows/*.mp4`) for the shot film below.
`{"write": "..."}` types into whatever has focus (a search a button or shortcut opened); a link that opens
a new tab is followed in the same one; with a dialog open, a `text=` target is looked for in the dialog
first; a flow may carry `"mobile": {"steps": [...]}` where the phone layout's controls differ. Each take
also records the page's headline, so the opening never crops it.

## 5. Story and plan

Write `story.json` as `beats` from the storyboard (shape: `references/shapes.md`; rules: `references/story.md`): hook, action and result per use
case, payoff, end. Each beat's `steps` are its flow's step numbers.

```bash
$PY "$S/product.py" plan product/<name> --story story.json --style linear --aspect 16:9 [--music generated|eleven|none|audio/<track>] [--sfx subtle|none] [--vo audio/vo.wav]
```

Length: about 8 s a use case (40 s for five), the hook, payoff and logo included, unless the user asked
for a length (`--length`, or `"length"` in the story). The plan paces the result, hook, payoff and travel
moments down to fit, never below reading time, and keeps the story, the steps and every per-frame check.
It stops shortening where the camera would get busier than the reference films (`journey.py` SPEED_BAR,
from the planned camera): smooth beats short, so a site with long pages can run a few seconds over.

A story of beats plans the rendered film (`journey.py`): the pages on one canvas left to right, one camera
on one easing, a drawn cursor, every change revealed in place, 60 fps. The plan checks every frame from the
camera path (the held focus in the safe frame and clear of the words, the cursor whole or hidden, every
line of text whole or out of frame, no capture past its own resolution), re-plans the camera when a frame fails, and exits 1 on what is left. A sparse
page is framed tighter on its detected content (`references/story.md` "Framing guarantee"). The score follows
the beats (a section per beat, the chord changing at each), effects land on the clicks, keys and new pages; -14 LUFS, -1 dBTP. A story of `shots` plans the
older shot film (screencasts and the shot library, each shot naming its `job`).

## 6. The animatic, the critic, approval

```bash
$PY "$S/product.py" animatic product/<name> --plan plan-linear-16x9.json
```

Writes `animatic-<tag>/sheet.png`, the animatic sheet: the start, middle and end of every beat, captioned with its job, time
and words, in seconds. Run the `storyboard-critic` agent on the sheet; apply its fixes to the story (order,
steps, words, a capture) and plan again; two rounds at most. Then show the sheet and ask in the question
box: **Approve** (Recommended) / **Change the order** / **Swap a shot** / **Redo a capture**. Do not render
before Approve. On Approve, stamp it: `$PY "$S/product.py" approve product/<name> --plan plan-linear-16x9.json`.
`render` refuses a plan with no stamp, or one whose plan or story changed after it (`scripts/gates.py`).

`stills` still makes the denser per-shot sheet for the shot film.

## 7. Render

Only after step 6's Approve. "Just render it" on a plan with no stamp still goes through step 6 first:
make the animatic and ask Approve.

```bash
$PY "$S/product.py" render product/<name> --plan plan-linear-16x9.json [--draft | --modal | --lambda]
```

A 30 s video renders in about a minute on a laptop. The same renderer and render paths as style-edit
(`edit.py`): laptop by default; `--modal` or
`--lambda` once the setup skill has set those up. Writes `render-<tag>.mp4`.

## 8. Check

```bash
$PY "$S/product.py" check product/<name> --plan plan-linear-16x9.json
```

The camera: every zoom changes size in log space (the same scale factor every frame), takes 0.9-1.4 s,
eases in and out (sine.inOut; expo.inOut for arc), and zooms about the target. `plan` and `check` print
WARN for a zoom faster than 7x a second at its peak, a speed that jumps between frames, or a continued
camera that changes speed at the join.

FAIL: a render older than its plan or story, words not on the site or over 7 words, emoji, an AI tell
the site's brand does not own (purple-blue, neon on black, a flat saturated ground, heading + subline
+ rule), clipping audio, a shot where the product fills under 75% of a 9:16 frame (60% of 16:9; type and
the end card exempt; plain ground of the site's colour does not count). WARN: over 2.5 s with nothing moving, words under 4.5:1 contrast on the
ground, loudness outside -23 to -9 LUFS (the mix is mastered to -14), a centred block (expected on the end card). Fix FAILs, then
render again; at most two rounds. For the rendered film `check` also runs the framing on every frame, the
focus found by template match where the plan put it, the product filling the frame by detected content
(edges, not colour), OCR for the logged-in name, and the smoothness meter (`meter.py`: judder, dead stops,
jerk, carry across cuts) against the Linear bar in `references/style.md`. Also make a 2 fps strip and look at it:
`ffmpeg -i render-<tag>.mp4 -vf "fps=2,scale=300:-1,tile=12x5" -frames:v 1 strip-<tag>.png`.

## 9. Share copy, hand over

```bash
python3 "$S/product.py" share product/<name>
```

`share.txt`: the caption (checked: only the site's sentences and its domain), the URL, and alt text
that says what is shown. Open the render (`open` / `start ""` / `xdg-open`), give the full paths of
the video, sheet and share.txt, and ask for notes. Notes about taste go to the taste skill.

A logged-in run: say where the login is kept (`node "$S/login.mjs" where <domain>` prints the folder)
and that it stays logged in on this computer until removed. Once the video is approved, ask in the
question box "Log out of <domain> on this computer?" (Yes, delete the saved login (Recommended) / Keep
it for the next video); on yes, `node "$S/login.mjs" logout <domain>`.

## If a script stops

| message | do |
|---|---|
| `no brief: ask the brief ...` / `brief.json has no ...` | ask those in the question box (step 1), write brief.json |
| `plan-<tag> is not approved` / `changed after it was approved` / `no animatic-<tag>/sheet.png` | step 6: animatic, show it, ask Approve, `approve` |
| `story names '...', which is not in site.json elements` / `click target ... not in site.json` | `product.py copy` lists the elements; use one of them |
| `not the site's words: ...` | replace those words with the site's own (`pages.md`) |
| `--rights is required` | ask who holds the rights (`references/brief.md` "Music") |
| `LOGIN: the site wants a login` (music) | ask before retrying with `--cookies-from-browser <browser>`, or offer the generated score |
| `No ElevenLabs key` | offer on-screen words or their own recording |
| `Modal is not set up on this computer` | the setup skill's Modal step, or render on the laptop |
| a blank `images/tile-0.jpg` after the crawl | the site blocked the headless browser: say so, ask for another URL |

## Files

- `scripts/crawl.mjs`: the crawl, home page and inner pages. Reuses `style-edit/scripts/capture.mjs` (Chrome binary, cookie banners).
- `scripts/record.mjs`: UI states as 3x stills (`--states`) or screencasts, desktop and `--mobile`; logged in via a profile, read-only deny-list, auto-blur (the logged-in account's own name and handle read from the session into `flows/whoami.json`, avatars, profile names, emails).
- `scripts/journey.py`: the rendered film's plan (canvas, camera, cursor per frame), the framing guarantee, the render checks. `journey.py demo` self-checks.
- `scripts/meter.py`: the smoothness meter. `meter.py demo` self-checks.
- `scripts/login.mjs`: login (a visible window on a dedicated profile), check, logout, where.
- `scripts/product.py`: pages, record, copy, plan, animatic, stills, approve, render, check, meter, share, tts. `product.py demo` self-checks.
- `scripts/gates.py`: what `plan` and `render` refuse without (brief, approval, music rights, story order). `gates.py demo` self-checks.
- `scripts/sound.py`: the score, the effects, the mix and the master. `sound.py demo` self-checks.
- `audio/LICENSES.md`: every sound's licence and evidence (all synthesised; what was evaluated and why not).
- `references/story.md`: story.json, the shot library, flows, the words rules, purposes, 9:16.
- `references/style.md`: what Apple, Linear, Stripe, Arc and Raycast films do, measured; how the styles borrow it; what to look for.
- `references/sound.md`: their sound, measured; what sound.py does with it.
- `references/brief.md`: music rights and logging in, for the brief.
- `references/brag.md`: what this takes from latent-spaces/brag (MIT) and what it does differently.
- `../../remotion/src/product/`: `ProductVideo.tsx` (the composition, page/lift/media/flow shots), `Journey.tsx` (the rendered film), `Shots.tsx` (the shot library), `kit.tsx` (styles, geometry, words, the logo).
- `../../agents/storyboard-critic.md`: reviews the animatic against the checklist.
