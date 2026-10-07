---
name: improve
description: For the editor's maintainers. Turns what users corrected into lasting fixes in this repo, for every user, enforced by code and tests rather than notes. Reads the suggestions users marked "would help everyone" (~/.ai-video-editor/suggestions.jsonl), taste rules that had to be said twice (taste.py report), preview corrections (edits/*/corrections.jsonl) and open GitHub issues labelled feedback; groups repeats; for each item the maintainer accepts, writes the general rule into PRINCIPLES.md and the skill that owns it, adds or tightens the check that enforces it, adds a test that fails before and passes after, runs the full test set and leaves a CHANGELOG.md entry to commit. Use when the maintainer says "improve the editor", "turn feedback into fixes", "process suggestions", "what are users complaining about", "go through the feedback issues". Not for one user's own preferences (that is taste), and not for editing a video.
license: MIT
compatibility: Python 3.9+, standard library only. Runs in a git checkout of the ai-video-editor repo; the GitHub CLI (gh) is optional, for the feedback issues.
---

# Improve

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

This runs in a checkout of the repo, for the person who maintains it. A fix here reaches every user on
their next plugin update. `S="${CLAUDE_SKILL_DIR}/scripts"`.

## 1. Collect

```bash
python3 "$S/improve.py" collect [--edits edits --edits product] [--no-gh]
```

One line a rule, most repeated first: how many times it came in, from where (suggestion, taste
regression, preview correction, GitHub issue), the owner the user named, and up to three examples.
A rule said by several users, or said again after it was applied, comes first.

## 2. Pick

Show the top of the queue and ask in the question box which to fix now (multi-select, the most repeated
first, recommended). For each one, also ask when it is unclear: **Every user** (Recommended) / **Only
some creators' styles** (it belongs in a style.json field, not a rule) / **Not a fix** (close it).

## 3. Fix each one, in this order

1. **The rule.** One line in `${CLAUDE_PLUGIN_ROOT}/PRINCIPLES.md` under the right heading, naming
   where it is enforced, and the same rule in the owning SKILL.md or reference. General, never about
   one video: "Zooms ease over at least 0.5 s", not "the zoom at 0:12 snapped".
2. **The enforcement.** The smallest code that makes the rule hold without anyone remembering it:
   a FAIL in a check (`check.py`, `quality.py`, `product.py check`, `ai_tells.py`), a refusal in
   the script that would break it (`gates.py`), a default that cannot produce it, or a line in
   `tests/check_plugins.py` for a repo rule. Prefer tightening an existing check to adding one.
3. **The test.** An assert in that script's `demo()` (or `tests/`), built from a small synthetic
   example of the failure. Run it before the fix and see it fail, then after and see it pass. A rule
   only an agent can follow (asking, explaining) gets an eval case in `evals/` instead: `prompt.md`
   plus a `tool_used` or `llm` grader.
4. **The record.** `docs/feedback-matrix.md`: the rule, where it is written, what enforces it, what
   tests it. Then the changelog line:

```bash
python3 "$S/improve.py" log "quality.py: a zoom faster than 0.5 s is a FAIL (quality.py demo)"
```

## 4. Run everything

```bash
python3 tests/check_plugins.py
for p in . plugins/ai-editor plugins/creator-teardown; do claude plugin validate --strict "$p"; done
```

Then every demo in `.github/workflows/check.yml`, `node tests/test_record.mjs`, and when the renderer
is set up `tests/smoke.py` and `tests/golden.py`. All green before handing over. Do not commit; the
maintainer reviews the diff and the CHANGELOG.md entry and commits.

On a GitHub issue that is now fixed, offer to comment the changelog line and close it
(`gh issue close <n> --comment "..."`), only after asking.

## Never

- Never edit a user's taste.md, taste.json, rules.json or suggestions.jsonl: they are theirs.
- Never put personal data in the repo: no names, handles, emails, file names or footage from the
  feedback. Write the general rule and a synthetic example. `tests/check_plugins.py` fails on known
  private names; read every example before it goes in.
- Never close the loop with a note alone. A rule with no enforcement and no test is not done.

## Files

- `scripts/improve.py`: `collect`, `log`, `demo`. Reads only, except CHANGELOG.md.
- `${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py`: where `suggest` and `issue` write the user side.
