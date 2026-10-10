# The home page

The first-run page in the browser: setup checks, optional keys, pick a creator, watch their videos
get studied, see the style and the skill it became, drop a video. The page only queues jobs. Claude
does every job with the usual skills and reports back, so the page never decides anything itself.

`H="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/home.py"`. `python3` on Mac and Linux, `py` on Windows.

## Open it

Run both in the background (two Bash calls with `run_in_background`), from the folder the user
started in (creator studies and edits land there):

```bash
python3 "$H" serve          # prints the URL and opens the browser; reuses a running server
python3 "$H" wait           # exits with the next job as one line
```

Say in one line: "The home page is open in your browser. Pick a creator there, or drop a video."
Then wait for `wait` to finish. Each time it prints a job, start a new `wait` in the background
straight away (so Cancel and the next job reach you), then do the job. `ALREADY` means a `wait` is
running: leave it.

## Keys

The page saves keys itself through `keys.py` (prefix check, one free test request, then the key
file, readable by the user only). A key never reaches the chat, `state.json` or a job line. Never
ask for a key in the chat, and never read the key file. "Skip, add later" runs `setup.py later`.

## The jobs

Report progress with `status`. A new `--step` closes the step before it; `--done` or
`--failed "<plain sentence>"` ends the job:

```bash
python3 "$H" status <teardown|skill|video|modal|setup> --step "..." [--detail "video 3 of 7"] [--progress 0.4]
python3 "$H" status <job> --result '<json>' --done
```

### `JOB teardown @handle platform=<p> take=<parts> root=<dir>`

The user pasted a creator and pressed "Study their videos". Run the creator-teardown skill's
**Quick mode** (its SKILL.md) on that handle and platform, in `root`. With `urls=<file>` instead of
a platform, use `list <handle> --urls <file>`. Do not ask the parts question: the page asks it.
No Gemini key: skip `gemini.py` (do not offer the key in the chat; the page has it).

Report these steps, in this order and these words (the page lists the ones still to come):

1. `Listed their videos` (fetch.py list)
2. `Downloaded the top 5 and 2 median` (visual.py download --top 5)
3. `Transcribed every word` (fetch.py transcribe --top 5)
4. `Measured cuts, zooms and camera moves` (visual.py measure)
5. `Reading captions and faces` (look.py measure; `--detail "video N of 7"` as it goes)
6. `Naming graphics` (graphics.py measure, gemini.py kinds)
7. `Sound effects and music` (sound.py measure)
8. `Writing the style` (report.py build)

The page reads every number itself from `creator-teardowns/<handle>/style.json` and `videos.json`,
so it fills in as each script writes. Then read `look.md` and end the job with what not to copy,
one plain sentence per BAN-level AI tell and per move the teardown rejects:
`--result '{"reject": ["..."]}' --done`. Do not open `teardown.html`: the page links it.

A step that stops: say why with `--failed`, in the words of the skill's "If a script stops" table.

### `JOB skill @handle take=<parts> root=<dir>`

The user ticked what to copy and pressed "Build my skill".

1. `--step "Saving your style"`: `profile.py set 'creators=[{"handle":"<h>","take":[...]}]'`, the
   parts mapped `captions`->captions, `pace`->pace, `graphics`->visuals, `sound` kept for the
   sound answer (`sound.sfx=true`).
2. `--step "Checking whether it is a format of its own"`: creator-teardown's
   `references/skill-handoff.md` gate, from the numbers in `look.md` and `videos.json`.
3. Pass: `--step "Writing the skill"`, build it as that file says, then
   `--step "Testing it with one script"` (its "Finally"). Fail: no skill; the style is saved.
4. `--result` then `--done`, the JSON the page shows:

```json
{"passed": true, "check": "5 of 5 top videos use this format, all above their median",
 "name": "format-name", "what": "one sentence: what it edits and how, with measured numbers",
 "use_for": "...", "not_for": "...", "path": "~/.claude/skills/format-name",
 "prompts": [{"text": "edit my video like @handle", "what": "one line"}],
 "tools": [{"name": "Your photos folder", "why": "one line", "prompt": "use my photos folder for the cards"}],
 "tested": "Claude wrote one script with it: \"<title>\". 7 beats, 100 words."}
```

A fail sends `{"passed": false, "why": "<which gate question said no>", "prompts": [...], "tools": [...]}`.
Five prompts, each one the user can paste into Claude Code as it is. Every number in `what`,
`check` and `tested` comes from the teardown or the script; leave a field out rather than guess.

### `JOB video <path> as=<@handle|defaults> aspect=<9:16|16:9> root=<dir>`

The user dropped a video and pressed "Start the cut". `as=defaults`: `profile.py set creators=[]`.
`aspect`: `profile.py set aspect=<a>`. Then the start skill from step 2 on, with this file as the
video. Report `Transcribe every word`, `Cut retakes and pauses`, then the review page's URL:
`--result '{"review_url": "<url review.py serve printed>"}'`. The rest happens on the review page.

### `JOB modal`

The user pressed "Log in with your browser". Follow the setup skill's step 6 (Modal), reporting
each of its steps with `status modal --step "..."`, and `status modal --done` when it works.

### `JOB cancel teardown`

Stop the running teardown commands (TaskStop) and say so in one line.

## Setup from the page

When doctor shows `FIX` lines, the page says Claude installs them. Run the setup skill's steps 2-4
and report each with `status setup --step "Installing the renderer" --progress 0.6`; `--done` at the end.
