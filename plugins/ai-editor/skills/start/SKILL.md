---
name: start
description: The front door of the AI video editor. Takes the user's video and a few multiple-choice answers (platform, creators to copy and what to take from each, audience, brand kit, own photos, names, what to avoid, captions, sound), saves them once to a profile, then runs the whole edit in order (setup if a tool is missing, creator-teardown for a new creator, cut, style-edit) so the user only drops a video, answers, approves the cut and approves the stills sheet. Use when the user says "edit my video", "edit this like @creator", "make my video look like @creator", "make this look like <creator>'s videos", "I want my videos edited", "start", "new video", drops a video file or pastes any link (video, Drive or Dropbox share, creator profile, website, podcast) with no other instruction, or asks how to use the editor. Not for one step named on its own (only cutting is cut, only analysing a creator is creator-teardown, a correction is taste, styling an existing cut is style-edit).
license: MIT
compatibility: Python 3.9+, standard library only for the intake. The steps it runs need what the setup skill installs. Runs from the full ai-editor plugin folder (uses its lib/).
---

# Start

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Read `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` first: the rules every video in this plugin follows (asking, looking real, motion, story and framing, privacy, cost).

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

The user's whole job: drop a video, answer a few questions, approve the cut, approve the stills sheet.
Everything else is this skill's job.

`P="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py"`. Run it with `python3` on Mac and Linux, `py` on Windows.

## 0. Links first

If the message has any link, @handle or file path, route it before anything else. Never ask what a
link is; the classifier knows.

```bash
L="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/links.py"
python3 "$L" route "<the user's whole message>" [--own]
```

Pass `--own` only when the user says the video link is theirs ("my video", "my TikTok", "I posted
this"). It prints a list, already in the order to handle it: questions, creators, own footage, long
videos, websites, music. Each item has a `kind`:

| kind | do |
|---|---|
| `ask` | One question in the question box for all `ask` items together (at most four), the `options` labels in the order given, the first marked "(Recommended)". The answer becomes the kind. |
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
Only download what the user has the right to edit; a creator's video is for the teardown, not to
re-edit.

## 1. The video

If the user has not given a video path (or a link step 0 fetched), ask for it in the question box:
**I'll give the path (Recommended)** / **Use the sample take** (the cut skill's "No video yet?").
Name the edit folder after the file (`IMG_1234.MOV` -> `edits/img-1234`).

## 2. Intake: only what is missing

```bash
python3 "$P" missing --video     # audience, names: asked for every video
python3 "$P" missing --style     # normally answered at setup; ask here only if setup was skipped
```

Prints the question ids with no saved answer. The style questions (platform, creators, liked
videos, brand, own photos, avoid, captions, sound, behind) are asked once at the end of setup. Ask
only the printed ids, at most four questions per call, grouped as below. Every question has a first
option that a beginner can accept as is: list it first and mark it "(Recommended)". Free-text
answers ("Other") are always allowed.

**Call 1: the video**

| id | question | options |
|---|---|---|
| `platform` | Where will this be posted? | TikTok, Reels or Shorts (vertical 9:16) / YouTube (wide 16:9) |
| `creators` | Which creators' videos do you want yours to look like? Give 1-3 handles or links. | the creator they named in their message / I'll paste handles / no one: a clean editorial look |
| `creators` (take) | What should we take from each? (multi-select, per creator when there are several) | everything / captions / pace and zooms / visuals and colours |
| `audience` | Who is it for, and what should they do after watching? | free text, one line each. Default: "people curious about the topic" and "follow" |

**Call 2: what makes it yours**

| id | question | options |
|---|---|---|
| `brand` | Colours and fonts for the graphics? | use the creator's look / my brand colours (paste hex codes) and font / a logo file too (give the path) |
| `assets_dir` | Do you have your own photos, screenshots or b-roll for this? | no, find real screenshots and logos / yes, this folder: (path) |
| `names` | Which products, tools, websites or people will you name? | free text, comma separated (add a website for anything not famous). These get their real logos and real page captures |
| `avoid` | Anything you never want on screen? (multi-select) | emoji, stock photos, generic icons (all three on by default) / a colour (hex) / other (free text) |

**Call 3: finish**

| id | question | options |
|---|---|---|
| `liked_videos` | Any specific videos you love the edit of? Paste 1-5 links (any creator). | skip / I'll paste links |
| `captions` | Captions? | like the creator / bold, a few words at a time / karaoke, the line fills as you speak / minimal / no captions |
| `sound` | Sound effects and music? | subtle sound effects, no music / no sound effects / sound effects and I'll add music myself |
| `behind` | Let graphics sit behind you? (screenshots and logos tuck behind your head and shoulders) | Yes / No, keep them beside and above me |

Save each answer as soon as it comes in (values are JSON):

```bash
python3 "$P" set platform '"tiktok"'                      # tiktok | reels | shorts | youtube (sets aspect)
python3 "$P" set creators '[{"handle": "somecreator", "take": ["captions", "pace", "visuals"]}]'
python3 "$P" set liked_videos '["https://www.tiktok.com/@someone/video/123"]'
python3 "$P" set audience '"developers who use Claude"'
python3 "$P" set goal '"follow, then comment router for the guide"'
python3 "$P" set brand '{"use_creator": true}'           # or {"colors": ["#F2EEE6", "#E5482C"], "font": "Archivo", "logo": "/path/logo.svg"}
python3 "$P" set assets_dir '"/Users/me/Pictures/screens"'
python3 "$P" set names '[{"name": "Jev", "domain": "typesafe.ai"}, {"name": "Claude", "domain": "claude.com"}]'
python3 "$P" set avoid '{"emoji": true, "stock": true, "icons": true, "colors": ["#7B61FF"]}'
python3 "$P" set captions '{"on": true, "style": "creator"}'   # creator | bold | karaoke | minimal; "on": false for none
python3 "$P" set sound '{"sfx": true, "music": false}'
python3 "$P" set behind true                              # false: cards stay beside and above, no cutout step
```

`goal` and `names` belong to this video: ask "Same goal and names as last time?" on later videos
(one question, yes as the first option) instead of the full intake. Everything else is asked once.
The profile lives in `~/.ai-video-editor/profile.json`; `python3 "$P" show` prints it.

If the user says "just edit it" or "use the defaults", save nothing and go on: every answer has a
default (vertical, no creator unless named, the editorial look, emoji, stock and icons avoided,
the creator's captions, subtle sound).

## 3. Route

Do each step in order, skipping what is already done. Read each skill's SKILL.md before its step.

1. **setup**, if any step fails because a tool is missing (`setup.py doctor` says `FIX`).
2. **creator-teardown** in quick mode (its SKILL.md "Quick mode") for every profile creator without
   `creator-teardowns/<handle>/style.json`. Say the time first (about a minute per creator). Run
   several creators in parallel when the platform allows.
3. **Blend the style**: `python3 "$P" style edits/<name>` writes `edits/<name>/style.json`, each part
   (captions, pace, visuals) from the creator the user picked for it, with the caption and sound
   answers laid over. With no creator, skip it and give style-edit the plain defaults. If it stops
   with `no creator style.json found`, step 2 did not finish for a creator: run it again.
4. **cut** on the raw take, from its step 0b (start has already decided: cut, wait for the cut page
   approval, then style). The user approves the cut page. This is approval 1 of 2.
5. **style-edit** with `edits/<name>/style.json`. Its stills sheet is approval 2 of 2. It reads the
   profile itself: the brand kit sets the look, `names` get real logos and captures, `assets_dir`
   images go on screen first, `avoid` is enforced by plan.py.

Between steps say one line about what is happening next. Never ask the user to do a step the skill
can do itself.

## 4. After

Open the render, give its full path, and ask for notes. Corrections go to the taste skill so they
are never needed again; a change of brand, creators or platform goes back into the profile with
`python3 "$P" set ...`.

## Files

- `../../lib/ai_editor/links.py`: pasted links to a kind and a skill (`route`, `classify`), and the
  downloader for the user's own footage (`fetch`). `links.py demo` self-checks 60 URL shapes.
- `../../lib/ai_editor/profile.py`: the profile (load, save, missing questions), the creator blend
  and the look resolution plan.py uses. `profile.py demo` self-checks.
