# Several creators: the blend

Moved out of SKILL.md Step 3d. Read it when the user named more than one creator.

Run Steps 1 to 3b for each creator into its own folder; each keeps its own `style.json`. Then show
the user each `look.md` side by side (5 lines each: pace, motion, captions, face, graphics) and ask
the Step 0 parts question in the question box if it is still open. Blend:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/editplan.py" blend <name> --from alice,bob \
    --captions alice --pace bob --visuals bob --sound bob   # or --weights alice=0.7,bob=0.3
```

Writes `creator-teardowns/<name>/style.json` (and its `look.md`). A named owner gives its whole
part; otherwise numbers are averaged by weight and words come from the heaviest. Parts: `captions`;
`pace` = pace, zoom, camera, motion; `visuals` = graphics, face, look, hook, card events; `sound`. `--take` (Step 3c)
works on a blend too. style-edit takes the blend like any creator.
