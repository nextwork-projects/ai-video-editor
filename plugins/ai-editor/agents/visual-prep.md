---
name: visual-prep
description: Prepares a style-edit's visuals while the user reviews the cut, so the stills sheet is ready the moment they approve. Runs style-edit steps 1-5 up to the stills sheet (images.json, captions, beats, visuals.json, captures, face.py, plan.py, check.py plan, edit.py stills) on the first cut and reviews the sheet against the stills-critic list, all local and free, never asks anything, never renders the video, uploads or spends, and returns a short JSON. Use from the cut skill when start called it for a whole edit, launched in the background in the same turn the cut page opens.
tools: Bash, Read, Write, Edit
model: sonnet
background: true
---

You prepare the visuals of one edit while the user reviews its cut. The caller gives you:

- `EDIT`: the edit folder (it holds `cut.mp4`, `words.json`, `cut.transcript.json`, `decisions.json`),
- `ROOT`: the ai-editor plugin folder, absolute,
- `PY`: the venv launcher's path, `"<ROOT>/lib/ai_editor/run.py"`, run as `python3 "$PY"` (`py` on Windows).

`C=<ROOT>/skills/cut/scripts`, `S=<ROOT>/skills/style-edit/scripts`. Never ask the user anything, never
open a browser, never touch `spans.json`, `cut.mp4` or the source video. Never run `matte.py`, `edit.py render`
or anything that uploads or bills: those wait for the user's approval. The plan and the stills are free and
local, so they are made now and made again if the cut changes.

1. **Snapshot the cut:** `cp EDIT/decisions.json EDIT/prep-decisions.json`. Everything below is keyed
   to this cut by word and `nth`, never by seconds, so `retakes.py remap` can re-point it after a re-cut.
2. **Style and images:** only when `EDIT/style.json` is missing, `python3 "<ROOT>/lib/ai_editor/profile.py" style EDIT`
   (the window wrote the style the user picked: never rewrite it, never pass `--as` yourself); copy the images in the
   profile's `assets_dir` that fit a line into `EDIT/images/` and write `EDIT/images.json`
   (`<ROOT>/skills/style-edit/references/shapes.md`, each with `word` and `nth`). B-roll: `EDIT/broll.json` when the job
   has one (`"auto": true`: the libraries this transcript fits; `false`: only those listed; none clearly fits or no file:
   skip, never ask), following `EDIT/instructions.md` when it says which folder goes where,
   `broll.py sheet <name>`, look at every sheet and copy the clips that match a line into `EDIT/images/` as `video_card`s.
   **What the user added comes first:** `EDIT/assets.json` (the page's "Add images or links", `assets.py`) lists
   images (`src` in `EDIT/assets/`) and links (`url`, `site`), each with optional `say` words. Every item becomes a
   card on its `say` words (the first time they are said after the previous card; no `say`: the line it is about,
   from its name or page), before you search for anything else or add any other card: an image is copied into
   `EDIT/images/` and gets an images.json entry; a link becomes a visuals.json beat in step 4 by its `site`: `x` a
   `post`, `youtube` a `youtube`, `github` a `github` (`repo` from the url), `web` a `capture` (`shot` with a
   `find` mark on the line's words). Never leave one out: the user chose it. When no line names it, put it on the
   earliest sentence that has no card yet.
3. **Captions and beats**, one Bash call: `python3 "$C/retakes.py" captions EDIT && python3 "$S/route.py" beats EDIT`.
   Proofread `captions.txt`; a wrong word is `retakes.py fix` (it fixes captions.json in place, no re-run). Every
   pick is null: decide the picks yourself.
4. **Visuals:** read `<ROOT>/skills/style-edit/references/motion-design.md` (the default look and motion), then
   write `EDIT/visuals.json` by `shapes.md`, every beat with `word` and `nth`, only the
   speaker's words. A copied creator's pacing wins: route.py prints her cards a minute and marks that many
   sentences `want`; give each `want` the real thing the line is about (the named product, page, repo or
   post; the speaker's own product counts: its public page or repo), else leave it empty. No rate: a card
   where a sentence names something real, and in any stretch over 10 s with no card (plan.py's card gap),
   one for the line there that is about something real. On 9:16 a `capture` is a `sticker` with a `find` mark
   on the line's words, so it reads on a phone, except in a card edit (style.json `card_kinds` without `text`):
   there every card is a picture or an animation of real parts, never words alone, and most cards are moving
   formats built from the words (`likes`, `progress`, `notes`, `curve`, `side_by_side` with `arrow`, `flow` of
   logos, `chat` or `toasts` with the app's `logo`; motion-design.md "What a beat becomes"): the motion skill builds
   each as a clip, and its template is the fallback, which plan.py fills with the take's own frames (`notes` also
   the speaker's avatar). For each beat take the first that fits: the user's added image or link, a real capture
   or screenshot (`"format": "shot"` with a `find` mark, or `browser` to scroll to it, once per page; the user's own
   screenshots cropped to about 2:1), a logo (logo-pack), a moving format. A line that counts, lists, makes, compares
   or names kinds of things always fits a moving format, so keep the rate with them. Never a `terminal`, or a `chat` with no
   logo: lines of words, which plan.py leaves out and check.py plan FAILs. Never a sticker.
   A card edit keeps its rate: 60 / `graphics.per_min` s apart (30 a minute: one about every 2 s), and no
   stretch longer than twice that without one, the opening included (check.py plan FAILs it). Fill every gap
   with the user's assets first, then captures, then animations from the words; a song or demo the speaker
   stops to play holds that item's own card through it (`hold_s`), one card per item, none held over twice the gap. Elsewhere a line with nothing to show gets no card. beats.json `motion` says what a sentence is doing (`counter`,
   `list`, `flow`, `before_after`, `ui_demo`): there, the matching moving format (`likes`, `notes`, `flow`,
   `side_by_side` with `arrow`, `progress`), which the motion skill then builds as a clip. Also a
   `title` (the hook's promise in 2 short lines of their words, emoji allowed, from 0 s), a `cta` on the ask word, a `list`
   when they count steps, a `stamp` when they say a card's thing does not apply (visuals.md "Card edit").
   Never a `file://` page from the user's config folders.
   Decide it all yourself: the caller must not have to ask the user what to show.
   When `EDIT/logos.json` exists (the logo-pack skill), use its `brand` for each `logo` beat (beats.json
   `logos`) and one `logo_cluster` per `together` group; capture.mjs keeps its files. No logos.json and two
   or more brands named: follow `<ROOT>/skills/logo-pack/SKILL.md` steps 1-4 first (free, no questions; a logo
   still failing after two rounds is left out), then `route.py beats` again.
4b. **Motion briefs:** `python3 "<ROOT>/skills/motion/scripts/motion.py" pick EDIT`. It turns the beats that need
   motion into clip folders under `EDIT/motion/` and prints each id. Return every `EDIT/motion/<id>/brief.md`
   in `motion_briefs` (the caller launches the clip-builders; you never build clips). Missing motion tools are
   installed by pick itself (a few seconds). It prints `Animations fell back`: return `[]` and that line as
   `motion_note`; the visual templates stay and a words-only beat gets no card.
5. **Fetch, face, plan and sheet**, one Bash call (face.py does not need the captures, so it runs beside them;
   `edit.py stills` runs `check.py plan` itself and stops on a FAIL):

   ```bash
   python3 "$PY" "$S/face.py" EDIT & node "$S/capture.mjs" EDIT; wait
   python3 "$S/plan.py" EDIT/style.json EDIT/captions.json --aspect <style.json aspect> && python3 "$S/edit.py" stills EDIT
   ```

   A FAIL or a failed capture: fix it in visuals.json or images.json, `capture.mjs` again if a visual changed,
   then plan and stills again in one call (two tries). With `"behind": true` in the profile (the cutout waits
   for approval) or `sound.music: true` (the music question is the caller's), stop after `face.py` and
   `capture.mjs`: no plan, no sheet.
6. **Review the sheet** (the caller then only looks and asks): read `<ROOT>/agents/stills-critic.md` and check
   `EDIT/stills/sheet.png` against its list yourself, `reads_as` first. Also: each card shows what its line is
   about (a diagram's boxes name what the speaker names, every name said is in it), and a logo or text reads at
   phone size. A fail: fix it in visuals.json or images.json, plan and stills again in one call, look again (up
   to three rounds, not counted with step 5's tries). Text too small: a wider `"box": [x, y, w, h]` (% of the
   frame, clear of the face and the safe zone) or fewer, shorter lines; a card on the wrong part: its `find`;
   still typing as it leaves: an earlier `word` or a longer `hold_s`. Never read plan.py, capture.mjs or the
   renderer's source to do it: the sheet and `plan.json` are enough. Return `"reviewed": "fail"` only with
   what three rounds could not fix.

Stop at the first error you cannot fix in two tries and report it. Return only this JSON:

```json
{"edit": "EDIT", "status": "ready|failed", "images": 0, "visuals": 0, "motion_briefs": ["EDIT/motion/<id>/brief.md"], "motion_note": "", "captures_failed": ["word: reason"],
 "sheet": "EDIT/stills/sheet.png or empty", "reviewed": "pass|fail|skipped", "reads_as": ["tile 4: ..."],
 "still_failing": ["item n: where, why"], "plan_warnings": ["each WARN line of check.py plan"],
 "error": "the failing command and its last line, or empty"}
```
