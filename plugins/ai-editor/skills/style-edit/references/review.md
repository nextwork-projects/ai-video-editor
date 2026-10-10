# The review page

Every render is handed over on one local page, never as a file path alone: the cut (cut skill), the
styled edit (style-edit), each clip (clips) and a product video (product-video). The user watches it,
pauses, and leaves a note at the moment. Claude reads the notes, fixes, renders again and opens the
next round on the same page. This is after the render. The live preview (`preview.py`) is before it.

Script: `${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py` (stdlib), page `review.html` beside it.
`review.py demo` self-checks. Mac, Windows and Linux: it opens the default browser.

Notes save in the edit folder: `review.json` (rounds, notes, replies, send and approve) and
`review/` (a frame still per note, any image the user pasted or dropped on a note, and a copy of
each round's video, so a new render to the same path never changes an earlier round's tab).

## The loop

```bash
R="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py"
python3 "$R" edits/<name> start --video edits/<name>/cut.mp4 --stage cut --transcript edits/<name>/words.json
python3 "$R" edits/<name> serve      # run in the background: opens the page; one server per folder, reused
python3 "$R" edits/<name> wait       # run in the background: it exits when the user presses send or approve
```

(`py` instead of `python3` on Windows.) Tell the user in one line that the page is open: watch,
pause, add a note, then **send notes** or **approve**. Then wait for `wait` to exit. Do not ask in
the question box meanwhile.

`wait` prints `SEND` or `APPROVE`, then every note of the round:

```
SEND: <name> the cut, round 1, 2 notes. video /abs/edits/<name>/review/v-cut1.mp4
#1 0:02.6 (2.6s): the pause before "editor" still feels long
    said: "is how I cut my videos in one go"
    frame: /abs/edits/<name>/review/rcut1-c1.jpg
```

An edit-stage note started with `--plan plan.json` also names the card on screen
(`[card 3 image 'notion']`: the index in `plan.json` `cards`). Look at the frame still and any
`image:` line before deciding the fix. `wait` ends with a `LEARN:` line and the `learn` command.

## After send or approve: learn from the notes

Review notes flow into the user's taste (memory) and, when marked for everyone, to the maintainers.

1. Pick the notes that are preferences: "captions too small", "too many zooms". Leave out one-off
   fixes ("cut the 'um' at 0:12"). Write each as a general rule, as the taste skill does.
2. If any, ask the scope ONCE for the whole batch in the question box: `My style (Recommended)` /
   `Just this video` / `Would help everyone`.
3. Run `learn`. One `--rule` per preference note; add `key=value` when a taste setting maps:

```bash
python3 "$R" edits/<name> learn --scope style --rule 2 captions "Captions bigger" captions.size_pct=6 --rule 4 visuals "Logos stay small"
python3 "$R" edits/<name> learn --none     # no preferences in this round
```

It saves each rule with `taste.py add` (`everyone` also adds a suggestion), marks every other note of
the round one-off, and writes on each note what happened: `"taste"` = rule id, `video-only`,
`suggested` or `one-off`. Tell the user in one line what was saved. On `everyone`, offer the GitHub
issue as the taste skill does (`taste.py issue`). `round` lists notes not learned yet.

With no `wait` running the page says Claude is not listening, and notes still save. The next
`wait` returns at once with them.

## After send: fix, show the work, open the next round

Show each step on the page while working. Each `status` ticks off the one before:

```bash
python3 "$R" edits/<name> status "moved the card on 'notion' 0.3 s later"
python3 "$R" edits/<name> status "rendering" --log edits/<name>/render.log
```

`--log` shows the last `N/M` in that file as a progress bar (Remotion prints `Rendered 812/3255`), so
write the render's output to a log. Never make up a percent.

While Claude works the user can keep adding notes. They are queued for the next round (`"queued": true`)
and `wait` does not see them. `round` makes them open notes of the new round: each moves to where its
words are said on the new cut when both rounds have the cut's transcript (`"moved": "words"`, old time
in `t_was`), else it keeps its time (`"moved": "time"` when the length changed: check it), with a new
frame still and the words said there. The next `wait` hands them over like any note.

The page has a **Stop** button while Claude works. When the user presses it, the round's notes open
again (queued notes join them) and the next `status` exits 3 with `STOPPED`: stop the work, say so in one line, run `wait`.

Answer every note, then open the round with the new render:

```bash
python3 "$R" edits/<name> resolve 1 fixed --reply "pause is 0.10 s now" --new-t 2.4
python3 "$R" edits/<name> resolve 2 wontfix --reply "<why>" --new-t 8.0
python3 "$R" edits/<name> round --video edits/<name>/cut.mp4
```

`--new-t` pins the note on the new render's timeline (a cut moves later moments). `wontfix` shows as
**left as is** with the reply as the reason; the user can press **fix it anyway**, which comes back
as a new note starting `fix it anyway:`. Do it. Then run `wait` in the background again. The open
tab follows the new round by itself; `round` never opens another.

## After approve

- **The cut:** the cut is approved. Go on to style-edit (or stop, on "just the cut first").
- **The styled edit:** the same page moves on to it:
  `round --stage edit --video edits/<name>/render.mp4 --transcript edits/<name>/words.json --plan edits/<name>/plan.json`.
  Approve there finishes the video. Stop the background `serve`.

## Several videos in one round

Both shapes of one edit, or every clip of a long video, go on one page as tabs over the player:

```bash
python3 "$R" clips/<name> start --video edits/<name>-clip1/render.mp4 --name clip1 --transcript edits/<name>-clip1/words.json
python3 "$R" clips/<name> alt clip2 --video edits/<name>-clip2/render.mp4 --transcript edits/<name>-clip2/words.json
```

Each video keeps its own notes; a note can be ticked **all videos** (`wait` tags it `[all videos]`;
fix it in each). `wait` tags the rest with the video's name. **compare** puts two side by side,
in sync. **approve all** approves every video in the round. `round` clears the extra videos: add
the ones still in play again with `alt`.

## On the page

The cut stage shows the transcript beside the video: every word, cut words and removed pauses struck
through, the line playing now highlighted (built from `decisions.json` and `words.raw.json` when they
add up to the video). The timeline is split at the cut points, or at `chapters.txt` on the edit, and
the edit adds Cards / Zooms / Captions tracks from `plan.json`. A missing file leaves that part out.
**Compare** plays an earlier round (or another version) beside this one, in sync. The **Rounds** tab
replays every earlier render. The timeline has a pin per note, and last round's notes
pinned where `--new-t` put them. A vertical render gets a **safe zone** button (`z`) that shades
where the app's buttons and text sit (plan.py's `SAFE` for 9:16). The cut stage links to
`cut-check.html` (the transcript, cut words struck through) when it exists. Shortcuts: space,
`j`/`l`, arrows, `,`/`.` one frame, `[`/`]` speed, `c` add a note, `i`/`o` mark a range.

The server listens on 127.0.0.1 only, and every request needs the random token in the URL `serve`
prints, so another page in the browser cannot read the notes or press send.
