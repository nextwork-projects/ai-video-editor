---
name: taste
description: Remembers how the user likes their videos edited, so they never give the same correction twice. Saves every correction or preference about an edit (the cut, captions, visuals, sound, layout) into ~/.ai-video-editor/taste.md as a plain rule, and into taste.json when it maps to a setting the scripts read (pause length, fillers, caption size, words per caption, zooms, sound, layout), deduplicated, scoped to every video or just this one, and counted each time it is applied so `report` shows what it learned; one that would help everyone goes to the maintainers. Every other AI editor skill reads both before it starts. Use whenever the user reacts to an edit ("too slow", "captions are too small", "fewer zooms", "I hate the whoosh", "that's perfect, keep it like that"), and when they ask "what do you know about my taste", "show my settings", "forget that rule" or "are you learning". Also learns how they cut from a raw take and their posted version ("I already edit by hand", "learn from my edit").
license: MIT
compatibility: Python 3.9+, standard library only. Runs from the full ai-editor plugin folder (uses its lib/).
---

# Taste

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

The user's own rules, kept outside the plugin (plugin updates never touch them):

```
~/.ai-video-editor/taste.md     rules in plain words, one bullet each, by section
~/.ai-video-editor/taste.json   settings the scripts read; they win over the creator's style.json
```

`S="${CLAUDE_SKILL_DIR}/scripts"`. Stdlib only, any `python3` (`py` on Windows).

## When the user reacts to an edit

1. Find the behaviour behind what they said, not the one instance. "The 'router' card is too
   small" becomes "Cards fill the space they have", not "make the router card bigger".
2. Scope. After every correction, ask in the question box: "Is this about this video, your style, or
   would it help everyone?" with the options `My style (Recommended)`, `Just this video` and
   `Would help everyone`. Skip the question only when they already said it ("always", "just this one").
   `Would help everyone` saves it to their style too, then step 6.
3. Save it with `add`, with the setting when one maps (table below) and the edit it was said on:

```bash
python3 "$S/taste.py" add captions "Captions bigger" --set captions.size_pct=6 --edit edits/<name>
python3 "$S/taste.py" add sound "Whooshes quieter on this one" --video edits/<name>
python3 "$S/taste.py" add visuals "Logos stay smaller than the captions" --edit edits/<name>
```

   The same rule said again (same setting, or near-identical words, same scope) edits the old
   one instead of adding a copy. Every-video rules also land in taste.md (words) and taste.json
   (the setting); this-video rules stay in rules.json and reach only that edit.

| they say | `--set` |
|---|---|
| cut is too slow / too rushed / too tight | `cut.max_pause=` (default 0.15 s; slower 0.25, faster 0.12) |
| captions too small / too big | `captions.size_pct=` (cap height, % of frame height) |
| more / fewer words on screen | `captions.words_per_caption=` |
| captions higher / lower | `captions.y_pct=` |
| caption colour / highlight colour | `captions.color=` / `captions.highlight_color=` (`"#RRGGBB"`) |
| fewer / more zooms | `zoom.per_min=` (0 turns zooms off) |
| no sound effects | `sfx=false` |
| always split / always overlay | `layout.mode=split` or `overlay` |
| keep my ums / don't cut fillers | `cut.keep_fillers=true` (retakes.py proposes no filler cuts) |

   No setting fits (card timing, a capture cropped wrong, a look), so it is a word rule: write it
   so it can be followed next time ("Captures crop to the sentence that proves the point").

4. Tell the user in one line what was saved, so they can catch a wrong one:
   `Saved to your taste: "Logos stay smaller than the captions" (visuals, every video)`.
   If `add` prints `regression`, the rule was already applied and did not hold: say so, and
   make it more concrete (a setting, a number) instead of saving the same words again.
5. Then redo the edit with it.
6. On `Would help everyone`, write it as a rule for every user of the editor, never about this video:
   what was wrong, the general rule, the skill or check that should own it, and a small example
   without their media, names or links (the script scrubs paths, file names, emails, handles and links too):

```bash
python3 "$S/taste.py" suggest "Zoom snapped in over 2 frames" "Zooms ease in over at least 0.5 s" --owner "style-edit quality.py zoom check" --example "a 1.2x punch at 0.07 s"
python3 "$S/taste.py" issue          # shows the issue it would open
```

   If `gh auth status` succeeds, ask in the question box: "Send it to the editor's maintainers as a
   GitHub issue?" with `Yes, open an issue (Recommended)` / `No, keep it on my computer`. On yes:
   `python3 "$S/taste.py" issue --yes`, and give them the issue link. No gh, or no: it stays in
   `~/.ai-video-editor/suggestions.jsonl`, where the maintainers' `improve` skill reads it.

## Learn from a past edit

When the user already edits by hand (or says yes to setup's "Have a raw take and the version you
posted? I can learn how you cut."), ask for both paths and read `references/learn-from-edit.md`.
It runs `learn.py <raw> <posted>`, which saves their pause length, retake and filler habits as
rules with counts, so the first edit already cuts like them.

## Is it learning

```bash
python3 "$S/taste.py" report
```

Each rule with times applied, in how many edits, corrections, and the last edit where it
was said again after it was applied. Rules from review-page notes (`review.py learn`) say so.
Show it on "what have you learned", "are you learning", or after a regression.

## Before any edit

Every AI editor skill starts by reading the taste for the edit it is on:

```bash
python3 "$S/taste.py" show --edit edits/<name>
```

That also counts the word rules as applied to this edit. plan.py and build_timeline.py read the
settings themselves (`load_json()` in the plugin's `lib/ai_editor/taste.py`) and count them.

Follow every rule in taste.md. They beat the creator's style: the user chose them. If a rule and
the creator's style disagree, say so once and follow the rule.

## Show, change, forget

- "What do you know about my taste": `taste.py show`, then summarise it in a few lines.
- Forget a rule: `taste.py report` for its number, then `taste.py forget <id>` (its setting and
  taste.md line go with it).
- Reset everything: delete taste.md, taste.json and rules.json (ask first).

## Files

- `scripts/learn.py`: a raw take and the user's posted cut of it in, their cut settings out; `demo`.
- `scripts/taste.py`: `add`, `report`, `show`, `forget`, `rule`, `set`, `unset`, `get`, `suggest`, `issue`, `demo`. A thin
  CLI over the plugin's `lib/ai_editor/taste.py`, whose `load_json()` and `merge()` are what plan.py
  and the cut use to lay the taste over the defaults and style.json.
- `~/.ai-video-editor/rules.json`: every rule with its scope, corrections, times applied and
  regressions (shape in the lib's docstring).
