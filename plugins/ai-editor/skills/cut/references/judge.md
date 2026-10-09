# Judging the cut on paper

The read-through in step 3 is scored, not eyeballed. A cheap agent grades the paper edit against
`judge-rubric.md` and returns findings as JSON; `judge_cut.py` applies them to `spans.json`. It is
free next to a render, so it loops until nothing is left to apply.

`J="${CLAUDE_SKILL_DIR}/scripts/judge_cut.py"`, `R="${CLAUDE_SKILL_DIR}/scripts/read_cut.py"`. On
Windows, `py` for `python3`.

## 1. Long take only (over 5 minutes): parallel readers

Word matching in `retakes.py` misses a line re-said in different words and a sentence stitched from
two takes. Readers catch those. Run them before the judge:

```bash
python3 "$R" chunks edits/<name>        # one reader prompt per ~180 s, 30 s overlap
```

Launch one `cut-reader` agent (`ai-editor:cut-reader`) per printed prompt, **all in one message**.
Give each `PROMPT` and `OUT` exactly as printed. Then:

```bash
python3 "$R" verify edits/<name>        # one verifier prompt per proposed cut
```

Launch one `cut-reader` per verifier prompt, again all in one message. Each argues to keep its line.
Then `python3 "$R" merge edits/<name>`: confirmed cuts go into `spans.json` (confidence medium).
`FIX BY HAND` lines (a stitch, a word lost inside a cut) need a restore: narrow or delete that span
yourself. Under 5 minutes, skip this section: the judge alone covers a short take.

## 2. The judge loop (every take)

Launch the `cut-judge` agent (`ai-editor:cut-judge`) with `EDIT=edits/<name>`, `ROOT` (the plugin
folder, absolute) and `SCRIPT` if the user gave one. It runs `prompt`, grades, writes `judge.json`,
runs `apply`, and repeats until `apply` exits 0, at most 3 rounds. It returns a short JSON.

- `spans_changed: true`: build again (step 3), then go on.
- `left` holds blockers no fix could apply, and suggestions (W6 adds, W5 spot-checks). Weigh each
  yourself. Fix a real one in `spans.json` by its quote; never re-cut what the judge restored.
- In an agent without subagents, do the agent's steps yourself.

What `apply` does, so its output reads right:

- A finding whose quote is not in the paper edit, with a bad cut number, or with no quote, is dropped.
- `restore` deletes a span, `trim` gives back the head or tail of one, `add` writes a new span with
  `confidence: "low"` (highlighted on the cut page). A restored line is frozen: no later round re-cuts it.
- W6 adds (under-cut) are only suggested, unless the user asked for a tighter cut: then `apply --tighten`.
- A fix that would leave `spans.json` unbuildable is not applied.
- Each round backs up the old spans as `spans.judge<N>.json`.

## 3. Precision: does the judge earn its write access

After the user approves the cut (step 6), before the hook check:

```bash
python3 "$J" score edits/<name>
```

It compares every change the judge made with the approved `spans.json`. A restore the user cut again,
or an add the user put back, counts as reverted. One line per edit goes to
`$AI_EDITOR_HOME/judge-eval.jsonl` (default `~/.ai-video-editor/`); a re-score replaces it.

Once 5 or more changes are scored and fewer than 60% survived, `apply` stops writing: it prints the
findings as suggestions and leaves `spans.json` alone. `python3 "$J" precision` shows where it stands.
Tell the user once when the judge has been switched to suggest-only.

## Clips

Each `clip-editor` agent grades its own clip with `judge_cut.py prompt` and `apply` (clips are short,
so no readers). The clips skill runs `score` on each clip the user approves.
