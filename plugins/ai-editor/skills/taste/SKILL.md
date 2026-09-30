---
name: taste
description: Remembers how the user likes their videos edited, so they never give the same correction twice. Saves every correction or preference about an edit (the cut, captions, visuals, sound, layout) into ~/.ai-video-editor/taste.md as a plain rule, and into taste.json when it maps to a setting the scripts read (pause length, caption size, words per caption, zooms per minute, sound on or off, layout). Every other AI editor skill reads both before it starts. Use whenever the user reacts to an edit ("too slow", "captions are too small", "fewer zooms", "I hate the whoosh", "always use the split", "don't put logos there", "that's perfect, keep it like that"), and when they ask "what do you know about my taste", "show my settings", "forget that rule" or "reset my taste".
---

# Taste

The user's own rules, kept outside the plugin (plugin updates never touch them):

```
~/.ai-video-editor/taste.md     rules in plain words, one bullet each, by section
~/.ai-video-editor/taste.json   settings the scripts read; they win over the creator's style.json
```

`S="${CLAUDE_SKILL_DIR}/scripts"`. Stdlib only, any `python3` (`py` on Windows).

## When the user reacts to an edit

1. Find the behaviour behind what they said, not the one instance. "The 'router' card is too
   small" becomes "Cards fill the space they have", not "make the router card bigger".
   A fix that only applies to this one video is not taste: just fix the video.
2. If it maps to a setting, set it:

| they say | setting |
|---|---|
| cut is too slow / too rushed | `cut.max_pause` (default 0.15 s; slower 0.25, faster 0.12) |
| captions too small / too big | `captions.size_pct` (cap height, % of frame height) |
| more / fewer words on screen | `captions.words_per_caption` |
| captions higher / lower | `captions.y_pct` |
| fewer / more zooms | `zoom.per_min` (0 turns zooms off) |
| no sound effects | `sfx` false |
| always split / always overlay | `layout.mode` `split` or `overlay` |

```bash
python3 "$S/taste.py" set captions.size_pct 6
```

3. Always also write the rule in words, under Cut, Captions, Visuals, Sound or Layout. A rule
   close to one already there replaces it instead of piling up:

```bash
python3 "$S/taste.py" rule visuals "Logos stay smaller than the captions"
```

4. Tell the user in one line what was saved and where, so they can catch a wrong one:
   `Saved to your taste: "Logos stay smaller than the captions" (visuals)`.
5. Then redo the edit with it.

## Before any edit

Every AI editor skill starts by reading the taste:

```bash
python3 "$S/taste.py" show
```

Follow every rule in taste.md. They beat the creator's style: the user chose them. If a rule and
the creator's style disagree, say so once and follow the rule.

## Show, change, forget

- "What do you know about my taste": `taste.py show`, then summarise it in a few lines.
- Forget a setting: `taste.py unset <key>`. Forget a rule: open taste.md and delete its line.
- Reset everything: delete both files (ask first).

## Files

- `scripts/taste.py`: `show`, `rule`, `set`, `unset`, `get`, `demo`. `merge()` is what plan.py and
  the cut use to lay taste.json over the defaults and style.json.
