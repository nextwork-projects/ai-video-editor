# Feedback matrix

Every rule in `plugins/ai-editor/PRINCIPLES.md` that came from a correction: where it is written, the code
that enforces it, and the test that proves the code still does. A rule with no enforcement and no test is
not done. The `improve` skill adds a row for every fix it makes.

Paths: `A` = `plugins/ai-editor/skills`, `E` = `plugins/ai-editor/evals`. CI runs every test below
(`.github/workflows/check.yml`).

| Rule | Written in | Enforced by | Tested by |
|---|---|---|---|
| Every question goes in the question box | PRINCIPLES "Asking"; every SKILL.md | `tests/check_plugins.py`: every own SKILL.md must say AskUserQuestion | evals with an `asks-and-waits` grader (llm: a question with choices that stops the turn; headless eval runs have no AskUserQuestion): `E/setup-plan-first`, `E/start-asks`, `E/launch-video-url`, `E/captions-too-small`, `creator-teardown/evals/tear-down-handle`; check_plugins fails if those graders go |
| Setup says its plan, why, cost and skip before acting | PRINCIPLES "Asking"; `A/setup/SKILL.md` step 0 | the skill text (agent behaviour, no script runs before it) | `E/setup-plan-first/graders/plan-first.md` (llm) |
| Skipped steps are remembered and resumable | PRINCIPLES "Asking"; setup step 0 | `setup.py later <step>` writes `~/.ai-video-editor/later.json`; `setup.py todo` lists it; doctor reminds | `setup.py demo` (later, dedupe, still_later) |
| Direct links to each key's page | `A/setup/SKILL.md` "Keys" | `tests/check_plugins.py` KEY_URLS | check_plugins |
| A brief before a product film | PRINCIPLES "Asking"; product-video step 1 | `gates.need_brief`: `product.py plan` refuses without brief.json (must_show, audience, action) | `gates.py demo`; `E/launch-video-url/graders/brief-first.md` (llm) |
| Animatic approved before render | product-video step 6; `references/story.md` | `product.py approve` stamps plan + story hashes after the sheet exists; `product.py render` refuses with no stamp or a changed plan or story (`gates.need_approval`) | `gates.py demo` (no sheet, no stamp, changed story); `E/render-unapproved` (llm) |
| No text slides | PRINCIPLES "Looking real"; `A/style-edit/references/visuals.md` | `plan.py` skips TYPE_ONLY cards with what to show instead; `ai_tells.py` text-only-cards | `plan.py demo` (type_only), `ai_tells.py demo` |
| No AI tells, invented palette or generic fonts | PRINCIPLES; `A/style-edit/references/ai-tells.md` | `ai_tells.py` in plan and render checks (BAN = FAIL); `product.py check` per shot | `ai_tells.py demo`; `tests/golden.py demo` (the default look plans with no BAN, and a purple-blue ground does fail); `tests/golden.py` (no BAN on the rendered stills) |
| Stats shown in their source, no invented numbers or copy | PRINCIPLES "Looking real" | product-video: `is_site_phrase` (on-screen words are the site's). style-edit: `check.py unsaid_numbers`, a number on a built card that nobody says is a FAIL | `product.py demo` ("ship 10x faster" rejected); `check.py demo` ("3x" unsaid fails, "42%" said as "forty two" passes, a real post exempt) |
| Nothing off-screen; cursor wholly in frame | PRINCIPLES "Story and framing" | `journey.framing` + `replan` on every planned frame; `gate_cursor` hides a cursor the frame would cut; `journey.check_render`; style-edit `check.py` safe zones | `journey.py demo` (cut-off focus fails then replans; edge cursor fails then is hidden); `check.py demo` |
| A vertical frame filled by product | PRINCIPLES "Story and framing" | `journey.content_fill` in `check_render`; `product.coverage` for the shot film | `journey.py demo` (flat ground = 0, UI detail > 0.9) |
| Smooth motion | PRINCIPLES "Motion" | `quality.py` zoom snap/jerk; `product.smoothness`; `journey.SPEED_BAR` stops a shorter cut that is busier; `meter.py` judder/jerk/stops | `quality.py demo`, `product.py demo` (a 0.2 s zoom warns, 1 s passes), `journey.py demo` (no snap in the camera), `meter.py demo` |
| Never cover the speaker's face | PRINCIPLES "Story and framing" | `plan.avoid_heads`, `check.py` "covers the head" FAIL, behind cards need a cutout | `check.py demo`, `plan.py demo` |
| Personal data blurred, incl. the logged-in account name | PRINCIPLES "Safety"; product-video "While recording" | `record.mjs` BLUR (emails, listed words incl. whoami's name, avatars, email fields) | `tests/test_record.mjs` on a synthetic page in Chrome Headless Shell (CI e2e, `--require-chrome`) |
| No create, delete, pay, publish or invite without a yes | PRINCIPLES "Safety" | `record.mjs` DENY (now includes create), overridden only by `"allow": true` on a step | `tests/test_record.mjs` (18 refused labels, 6 allowed) |
| Music licence recorded; who holds the rights | PRINCIPLES "Safety"; product-video step 1.8 | `product.py music` requires `--rights`; `--file` records a file's; `plan --music audio/F` refuses with no recorded rights (`gates.need_licence`) | `gates.py demo` |
| No private names in the repo | PRINCIPLES "Safety" | `tests/check_plugins.py` hashed name list, IMG_#### file names | check_plugins |
| Default length | PRINCIPLES "Story and framing"; `references/story.md` | `gates.target_length`: 8 s an action (40 s for five) unless asked; `build_journey` paces to it but never past SPEED_BAR | `gates.py demo` |
| Story order | `references/story.md` "The arc" | `gates.story_order` in `check_story`: hook first, end last, result after an action, payoff last before the end (FAIL); making before discovering (WARN) | `gates.py demo`; `product.py demo` (a story opening on 'end' fails) |
| A cut is graded on paper before it renders, and the grader loses write access when users revert it | PRINCIPLES "Cost"; `A/cut/references/judge.md` | `judge_cut.py` (drops unquoted findings, applies by quote, freezes restores, W6 adds suggest-only, suggest-only below 0.60 precision); `read_cut.py` readers and verifiers for takes over 5 min | `judge_cut.py demo`, `read_cut.py demo` |
| Independent work runs at once | PRINCIPLES "Speed"; clips step 5 | `capture.mjs` `pool`: captures, logos and sources, `crawl.mjs` inner pages, `record.mjs --states` flows, four tabs at a time (`AI_EDITOR_TABS`); clips launches one `clip-editor` agent per clip in one message; cut (called by start) starts the `visual-prep` agent as the cut page opens, its visuals keyed to words so `retakes.py remap` re-points them after a re-cut; `edit.py copy_changed` keeps parallel stills from rewriting the shared renderer; `tests/check_plugins.py`: every agent a SKILL.md names exists with model and tools | `tests/test_record.mjs` (pool order and cap), `edit.py demo` (copy_changed), `test_retakes.py` (remap), check_plugins |
| Corrections improve the product | PRINCIPLES "Learning"; taste step 2 and 6 | `taste.py suggest` (scrubbed suggestions.jsonl), `taste.py issue --yes` (gh, only after a yes); `improve` skill + `improve.py collect/log` | `taste.py demo` (scrub, issue preview), `improve.py demo` (grouping, changelog); `E/captions-too-small/graders/asks-who-it-helps.md`, `E/improve-from-feedback` |

## Not enforceable by code

- **Asking, and asking well** (the question box, the setup plan, the brief, the "help everyone" question):
  these are what the agent says before any script runs. Covered by evals (llm and tool_used graders) and
  by check_plugins keeping those evals and the AskUserQuestion line in every SKILL.md.
- **The user said yes** before an approval, a create or a GitHub issue: code can require the stamp
  (`approve`, `"allow": true`, `issue --yes`) but not see the answer in the question box. Covered by the
  skill text and `E/render-unapproved`.
- **Discover before make** in the story order is a judgement of what each use case is; the code warns on
  the words it can see (search, browse before create, build), and the `storyboard-critic` agent judges it.
- **Story beats are the right story** (a hook that hooks, a payoff that pays off): the
  `storyboard-critic` agent and the user's Approve.
