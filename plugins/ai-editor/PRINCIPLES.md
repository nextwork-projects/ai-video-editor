# Principles

The rules every skill in this plugin follows, for every user and video. Each names where it is
enforced. What enforces each rule and the test that proves it: the repo's
`docs/feedback-matrix.md`.

## Asking

- Every question goes in the question box (AskUserQuestion), recommended option first, free text
  always allowed. Pages show evidence; they never collect answers. (every SKILL.md;
  where to render has none)
- Ask what the video must cover before building it: a short brief first. (start, product-video)
- Taste is asked once at setup and saved; each video asks only what belongs to that video.
  (setup, `lib/ai_editor/profile.py`)
- Any step can be skipped and finished later. (setup, `setup.py later`)
- Say the plan and why before doing it: what each step is, why it helps, what it costs, what
  skipping means. (setup)

## Looking real, never AI-made

- Real things carry each beat: the user's own assets, real captures of what is named, real logos,
  real posts, the real UI. A number is shown inside the page that published it, never as a big
  number on a plain ground. (`style-edit/references/visuals.md`)
- No text slides, no invented stats, no invented copy: on-screen words come from the speaker or the
  site. (plan.py, product.py grounding)
- No invented palette. Card chrome is neutral; colour comes from the real content, the user's brand
  kit or the copied creator's measured colours. (`look.tsx`, `profile.py`)
- The researched AI tells are banned: see `skills/style-edit/references/ai-tells.md`; enforced by
  `ai_tells.py` in plan and render checks. The user's own brand can override a ban.

## Motion

- Smooth before varied: one easing language per film, moves that overlap so nothing stops dead,
  zooms in log space about the target, motion carried across cuts, 60 fps where the renderer
  allows, motion blur only on fast moves. Measured, not judged by eye: `quality.py` zoom checks,
  `product-video/scripts/meter.py` against reference films.
- Draw, don't record, when a recording would stutter: capture UI states sharply and animate
  between them. (product-video `journey.py`)
- Every element lands on its spoken word; the timeline is labelled with the words.
  (`motion.ts` wordTl)

## Story and framing

- Story first, shots second: each beat has a job (hook, reveal, action, result, payoff, end) and
  the shot is chosen for the job, never for variety. Each shot starts where the last ended.
  (`product-video/references/story.md`)
- Order use cases as a journey a viewer would take: discover and learn first, make something of
  their own later, end on what they own or can do. (story.md)
- Nothing important leaves the frame: focus, words and cursor stay inside the safe frame on every
  frame, checked from the plan and again on the render. (product.py check, check.py)
- A vertical frame is filled by real product or the speaker, measured by detected content, never
  by "not the background colour". (product.py check)
- Never cover the speaker's face; cards may tuck behind the head only when the cutout is on.
  (plan.py, check.py)
- Default length is short: about 40 s for a product film with five use cases, scaled to the
  count, but never shortened past the smoothness bar: smooth beats short. (product.py,
  `journey.py` SPEED_BAR)

## Safety and privacy

- A logged-in capture uses its own browser profile, never the user's main one; the user logs in
  by hand; nothing leaves the computer. (`login.mjs`)
- Personal data is blurred by default, including the logged-in account's own name and handle.
  (`record.mjs`)
- Never press anything that creates, deletes, pays, publishes or invites unless the user said yes
  in the question box for that video. (`record.mjs` deny list)
- Every music and sound file has a recorded licence; links ask who holds the rights.
  (`product-video/audio/LICENSES.md`, `MUSIC-LICENSE.md`)
- Nothing personal ships in this repo: no names, handles or personal file names.
  (`tests/check_plugins.py`)

## Cost

- Code measures; cheap models judge; Claude decides only what is left. Claude never reads raw
  transcripts or frame-by-frame images when a script can summarise them. (cut `retakes.py`,
  creator-teardown `look.py`, `sheet.py`)

## Speed

- Independent work runs at once: in the script first (Chrome tabs), an agent per item only where
  it needs judgement, returning a short JSON. (`capture.mjs`, clips)

## Learning

- Every correction becomes a rule for the next video, counted, with regressions shown.
  (`lib/ai_editor/taste.py`)
- After every correction the question box asks "this video, your style, or would it help
  everyone?". "Everyone" goes to
  `~/.ai-video-editor/suggestions.jsonl` (scrubbed) and, on a yes, a GitHub issue (`taste.py suggest`,
  `issue`). The `improve` skill turns those into a rule here, the check that enforces it and a test.
