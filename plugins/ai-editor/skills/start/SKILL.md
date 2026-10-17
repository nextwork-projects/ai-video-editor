---
name: start
description: The front door of cooked. Takes the user's video and a few multiple-choice answers (platform, creators to copy and what to take from each, audience, brand kit, own photos, names, what to avoid, captions, sound), saves them once to a profile, then runs the whole edit in order (setup if a tool is missing, creator-teardown for a new creator, cut, style-edit) so the user only drops a video, answers, approves the cut and approves the stills. Use when the user says "edit my video", "edit this like @creator", "make my video look like @creator", "make this look like <creator>'s videos", "I want my videos edited", "start", "new video", drops a video file or pastes any link (video, Drive or Dropbox share, creator profile, website, podcast) with no other instruction, or asks how to use the editor. Not for one step named on its own (only cutting is cut, only analysing a creator is creator-teardown, a correction is taste, styling an existing cut is style-edit).
license: MIT
compatibility: Python 3.9+, standard library only for the intake. The steps it runs need what the setup skill installs. Runs from the full ai-editor plugin folder (uses its lib/).
---

# Start

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video follows (where, asking, looking real, motion, story, privacy, cost).

Every question goes in the question box: the AskUserQuestion tool (2-4 options, recommended first). Only in an agent without it, ask numbered questions in text. `Attached images: <paths>` in an answer: Read each first.

The user's whole job: drop a video, answer a few questions, approve the cut, approve the stills, both on
the review page. Everything else is this skill's job.

`P="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py"`. Run it with `python3` (`py` on Windows).

**First run** (the session-start line says so, or `setup.py doctor --quiet` prints a line): the
setup skill's step 0 first (window, then installs in the background), then carry on here.

## 0. Links first

If the message has any link, @handle or file path, route it before anything else. Never ask what a
link is; the classifier knows.

```bash
L="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/links.py"
python3 "$L" route "<the user's whole message>" [--own]
```

`--own` only when the user says the video link is theirs ("my video", "I posted this"). It prints a list, already in the order to handle it: questions, creators, own footage, long
videos, websites, music. Each item has a `kind`:

| kind | do |
|---|---|
| `ask` | One question box for all `ask` items together (at most four): each item's `question` word for word, its `options` labels in order, the first marked "(Recommended)". The answer becomes the kind. |
| `creator` | creator-teardown quick mode on `handle` and `platform` (no platform: ask, TikTok first). With `urls`, write them to `picks.txt` and use `list <handle> --urls picks.txt`. Save it as the profile creator. |
| `own` | `python3 "$L" fetch "<url>" edits/<name>` (`name` is in the item). It prints the file path; that is the video for step 1. |
| `long` | the clips skill, with this link as its source. |
| `product` | the product-video skill with this URL. A plain website (not a video site, file or share link) is always `product`, even after "edit my video": go straight to its brief, with no "did you mean your own footage" line. |
| `music` | the music question with rights (style-edit, or product-video's `music` step). |
| `unsupported` | say its `note` to the user, word for word, and go on with the rest. |

An item with a `note` (Instagram profiles, Spotify, app stores, OneDrive): say the note once.
fetch exit 3 means the site wants a login: ask in the question box "Use your browser's login for
this one download?" (No, I'll download it myself (Recommended) / Yes, Chrome / Yes, another
browser), and only on a yes re-run with `--cookies-from-browser <browser>`. Exit 1: say its message.
Only download what the user may edit; a creator's video is for the teardown, not to re-edit.

## 1. The video

"Open the home page" (`nextwork-editor`, `/ai-editor:start`), "listen for jobs", "take job <id>", "carry on <edit>": `references/home.md`. No video,
link or creator (a bare "edit my video"): ask **Open the home page (Recommended)** / **I'll give
the path** / **Use the sample take** (cut's "No video yet?"). Edit folder: `IMG_1234.MOV` -> `edits/img-1234`.

## 2. Intake: ask nothing the profile or style answers

```bash
python3 "$P" missing --style     # answered at setup, or by the style picked in the window
```

A `JOB video` (the window picked the style), "just edit it", or no id printed: run `python3 "$P" defaults`
and ask nothing. It keeps every saved answer and fills the rest with the first option (audience "people
curious about the topic", goal follow, names found in what they say). Post no status about defaults: the
review page shows an audience only when the user gave one (`review.py <edit> status "For <their audience>"`).
Otherwise read `references/intake.md` and ask the printed ids in one question box. Profile: `python3 "$P" show`.

## 3. Route

Do each step in order, skipping what is already done. Read each skill's SKILL.md before its step.

1. **setup**, if any step fails because a tool is missing (`setup.py doctor` says `FIX`).
2. **creator-teardown** in quick mode (its SKILL.md "Quick mode") for every profile creator without
   `creator-teardowns/<handle>/style.json`. Say the time first (about a minute per creator). Run
   several creators in parallel when the platform allows.
3. **Blend the style**: `python3 "$P" style edits/<name>` writes `edits/<name>/style.json` from the
   parts the user ticked for each creator, with the caption and sound answers laid over (no creator:
   the default style). It prints the copied style's skill (`skill: edit-like-<h> -> <path>`): read
   it and follow its learned rules through the cut and the edit. `no creator style.json found`:
   run step 2 again.
4. **cut** on the raw take, from its step 0b (start has already decided: cut, wait for the cut page
   approval, then style). The user approves the cut page. This is approval 1 of 2.
5. **style-edit** with `edits/<name>/style.json`. Renders on the cut's approve; the edit is approval 2. It reads the
   profile itself: the brand kit sets the look, `names` get real logos and captures, `assets_dir`
   images go on screen first, `avoid` is enforced by plan.py. Letterbox (wide take, title on top):
   cut `--max-pause 0.5`, `--layout letterbox`.
   `skill=<skill>` on the job: step 5 is that skill, not style-edit (`references/home.md`, Skill style).

Between steps say one line about what is next. Never ask the user to do a step the skill can do.

## 4. After

The render is handed over on the review page (style-edit step 8). Corrections go to the taste skill; a change of brand, creators or platform goes back into the profile with
`python3 "$P" set ...`.
