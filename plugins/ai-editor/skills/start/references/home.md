# The home page

The editor's window in the browser. A first run gets setup checks, optional keys, pick a creator, watch
their style get copied, see the style and the skill it became, drop a video. After that it opens on
Home (welcome back), New video (pick clips, then pick a style), Your videos, My style and Settings.
The page only queues jobs. Claude does every job with the usual skills and reports back, so the page
never decides anything itself.

Ask the user only through AskUserQuestion: the window shows it as a card on the open page. A question typed in your
reply never reaches the page; the Stop hook (toolhook.py) can only put "Claude needs you in the Terminal" on it.

The `nextwork-editor` command (`setup.py install-launcher`) starts Claude Code in the library with the
prompt "/ai-editor:start open the home page". When the page is already served it reopens it, and when no
Claude is listening it also opens a new Terminal window with a listening Claude (`--window-only` skips
that). Inside Claude Code, `/ai-editor:start` and "open the home page" do the same.

**Connect Claude.** When nobody listens, the page shows one button, Connect Claude. It opens a new
Terminal window in the library running Claude Code with the prompt `/ai-editor:start listen for jobs` and
only the editor's own commands allowed (`launcher.connect`, one at a time: a second press within a minute
opens nothing). On that prompt run `python3 "$H" serve --no-open` and `python3 "$H" wait` (both in the
background) and carry on as below. Do not say the page is open: it already is.

`H="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/home.py"`. `python3` on Mac and Linux, `py` on Windows.

## Open it

Run both in the background (two Bash calls with `run_in_background`). The page always works in the
library (`library.py path`, `~/Movies/AI Editor` on a Mac), wherever Claude Code started, and every job
line names it as `root=`:

```bash
python3 "$H" serve          # same address every time (port 47821, one token per install); reuses a running server
python3 "$H" wait           # exits with the next job as one line
```

Say in one line: "The home page is open in your browser. Pick a creator there, or drop a video."
Then wait for `wait` to finish. Each time it prints a job, start a new `wait` in the background
straight away (so Cancel and the next job reach you), then do the job. `ALREADY` means a `wait` is
running: leave it.

### One page, several Claude sessions

Every job remembers the session that took it (`CLAUDE_CODE_SESSION_ID`). `status` from another session
never writes to it, `status` never takes a queued job (only `wait` does), and each session makes one
video at a time. A taken job with no report for 15 minutes belonged to a session that stopped: the next
`status` or `wait --job` from another session adopts it and prints `adopted <id>`. Every video gets a Claude of its
own: when the user presses Make my video, each new video job (one per clip for "Separate videos") opens a new
Terminal window running Claude Code in the library with the prompt `/ai-editor:start take job <id>`, unless an idle
listening Claude can take it right now (then that one does, and the rest still get their own). The same goes for a chat box: a
`style-change` (a style page), `skill-change` or `skill-new` (Make a new skill) opens a Claude for that job unless
an idle listening Claude takes it. A listening Claude is
idle only with no active job: none it holds (a creator, a skill, a video's cut) and no video whose edit it is still on
(that editor's `wait` listening, or a review command there in the last 15 minutes). Setup and the sample stay with
the listening Claude; a creator's analysis is queued for it like any job. Where no terminal can
open (Linux without x-terminal-emulator), the editor shows that command to run instead. On that prompt run
`python3 "$H" serve --no-open` and `python3 "$H" wait --job <id>` (both in the background): it prints that
job's line (or `GONE` when it is done or another session has it), then do the job as below. Do not start a
plain `wait` afterwards unless the user asks for more.

"carry on edits/<name>" (`/ai-editor:start carry on edits/<name>`): the video's review page opened this Claude (the user sent notes or approved with no Claude on
that video, or pressed Open a new Claude). With `R="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py"`, run
`python3 "$R" edits/<name> serve --no-open` and `python3 "$R" edits/<name> wait` (both in the background), then do what
`wait` hands back, the same as after any round, with no intake.

## Questions

Ask with AskUserQuestion as usual. When the home page or a review page is open and showing, a hook
(`lib/ai_editor/askhook.py`) puts the question on that page. A question about a video goes to that video's editor
only: the hook takes the video your latest command named (its edit folder), so run a command on that edit (any
`review.py <edit> ...` or script on it) before asking about it. On the page: the options, an Other box with a paperclip (an image
can also be pasted or dropped on the card), and "Answer in Claude Code instead". Images are saved on this
computer (the review page: `<edit>/review/`; the home page: `<edit>/asks/`, or `$AI_EDITOR_HOME/asks` with no
edit folder yet) and the answer ends with `Attached images: /abs/a.png (Read each one to see it)`: Read every
listed image before acting on the answer. The answer comes back as the tool's result, the same as a terminal answer. No page
showing, "Answer in Claude Code instead", or every page that had it closed: the terminal box shows (an open page
waits for the answer however long it takes). Never ask
a question in plain chat text when AskUserQuestion fits: only the tool reaches the page. A question only
reaches pages this session works on (the home page while it holds a job there or listens, the review page
of an edit it ran `review.py` on), with the job's name on the card. Another session's questions stay in its
own terminal. A Claude Code without `CLAUDE_CODE_SESSION_ID` records no session, and then every question
reaches the page, as before. Permission
prompts (Allow or Deny for a command) stay in the terminal; a hook cannot answer them.

## Keys

The page saves keys itself through `keys.py` (prefix check, one free test request, then the key
file, readable by the user only). A key never reaches the chat, `state.json` or a job line. Never
ask for a key in the chat, and never read the key file. "Skip, add later" runs `setup.py later`.

## The jobs

Progress is automatic: once your `wait` has taken a job (inside Claude Code only `wait` takes a queued
one), the long scripts (creator-teardown's, the cut's transcribe, join, build and render,
setup's install-all) post their own steps with a count ("video 3 of 7") onto the job their edit folder
or handle names, and the page shows a live strip with a clock, so it never looks stopped. You still
report the steps you own (the result, `--done`, `--failed`, steps no script covers) with `status`. The
same words as the newest step update that row, never a second one. A new `--step` closes the step before it; `--done` or
`--failed "<plain sentence>"` ends the job:

```bash
python3 "$H" status <teardown|skill|video|setup|update> --step "..." [--detail "video 3 of 7"] [--progress 0.4]
python3 "$H" status <job> --result '<json>' --done
```

### `JOB teardown @handle platform=<p> take=<parts> [notes=<file>] root=<dir>`

The user pasted a creator and pressed "Copy this style". Run the creator-teardown skill's
**Quick mode** (its SKILL.md) on that handle and platform, in `root`. With `urls=<file>` instead of
a platform, use `list <handle> --urls <file>`. Do not ask the parts question: the page asks it.
With `notes=<likes.md>`, read it first: what the user wrote they like about these videos, and their own
files (example videos, screenshots, PDFs, notes, all in `<root>/references/`). Look closer at what they
named: watch those moments frame by frame, measure them, and say what you found first in `look.md` and in
the style's notes. Read or look at every file. An example video is one more video of the format: pull
frames from it with ffmpeg and compare it with the downloaded ones (fetch.py takes links only).
No Gemini key: skip `gemini.py` (do not offer the key in the chat; the page has it).

The scripts report these steps themselves; use these words if you report one (the page lists the ones still to come):

1. `Listed their videos` (fetch.py list)
2. `Downloaded the top 5 and 2 median` (visual.py download --top 5)
3. `Transcribed every word` (fetch.py transcribe --top 5)
4. `Measured cuts, zooms and camera moves` (visual.py measure)
5. `Reading captions and faces` (look.py measure; `--detail "video N of 9"` as it goes; then format_check.py
   check, and when it leaves videos out its first line as `--detail`)
6. `Naming graphics` (graphics.py measure, gemini.py kinds)
7. `Sound effects and music` (sound.py measure)
8. `Writing the style` (report.py build)

The page reads every number itself from `creator-teardowns/<handle>/style.json` and `videos.json`,
so it fills in as each script writes. `report.py build` also prints the style's skill
(`skill edit-like-<handle> -> <path>`). Then read `look.md` and end the job with what not to copy,
one plain sentence per BAN-level AI tell and per move the teardown rejects:
`--result '{"reject": ["..."]}' --done`. Do not open `teardown.html`: the page links it. The style's
`warnings` (report.py: not one format, graphics on the face) show on the finished analysis and the style page by
themselves; say them in chat as well, and never say something is on the page that the page does not show.

A step that stops: say why with `--failed`, in the words of the skill's "If a script stops" table.

### `JOB skill @handle take=<parts> root=<dir>`

The user ticked what to copy and pressed "Build my skill".

1. `--step "Saving your style"`: `profile.py set 'creators=[{"handle":"<h>","take":[...]}]'`, the
   parts mapped `captions`->captions, `pace`->pace, `graphics` (with `entrances` and `layout`)->visuals,
   `sound` kept for the sound answer (`sound.sfx=true`). Then creator-teardown's
   `editplan.py blend <h>-mine --from <h> --take <parts>`: it refreshes the style's skill
   `edit-like-<h>` on the ticked parts and prints its name.
2. `--step "Checking whether it is a format of its own"`: creator-teardown's
   `references/skill-handoff.md` gate, from the numbers in `look.md` and `videos.json`.
3. Pass: `--step "Writing the skill"`, build it as that file says, link it with
   `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/styleskill.py" write creator-teardowns/<h>-mine/style.json --format <name>`,
   then `--step "Testing it with one script"` (its "Finally"). Fail: no format skill; the style and its skill are saved.
4. `--result` then `--done`, the JSON the page shows:

```json
{"passed": true, "check": "5 of 5 top videos use this format, all above their median", "style_skill": "edit-like-handle",
 "name": "format-name", "what": "one sentence: what it edits and how, with measured numbers",
 "use_for": "...", "not_for": "...", "path": "~/.claude/skills/format-name",
 "prompts": [{"text": "edit my video like @handle", "what": "one line"}],
 "tools": [{"name": "Your photos folder", "why": "one line", "prompt": "use my photos folder for the cards"}],
 "tested": "Claude wrote one script with it: \"<title>\". 7 beats, 100 words."}
```

A fail sends `{"passed": false, "why": "<which gate question said no>", "style_skill": "edit-like-<h>", "prompts": [...], "tools": [...]}`.
Five prompts, each one the user can paste into Claude Code as it is. Every number in `what`,
`check` and `tested` comes from the teardown or the script; leave a field out rather than guess.

### `JOB video <path> as=<mine|@handle|defaults> aspect=<9:16|16:9> edit=<dir> root=<dir>`
### `JOB video takes=<dir>/takes.txt as=... aspect=... edit=<dir> root=<dir>`
### either one with ` script=<edit>/script.md`, ` skill=<skill>`, ` chain=<steps>`, ` sample=1` and/or ` assets=<edit>/assets.json` before `root=`

The user picked clips and a style and pressed "Make my video" (or "Start the cut" on a first run).
`edit=` is the edit folder the page already made and listed in the library: use it, never make
another. `takes=` lists several clips, one path per line, in the order the user set: they are one
video, so join them first (`cut/references/takes.md`, `join.py <edit>/joined.mp4 <the paths in order>`,
no question: the page asked it). "Separate videos" arrives as one JOB per clip; take them one by one.

`as=` is this video's style only: never `profile.py set creators` for it (only the page's Make default changes the
saved style). The page already wrote `<edit>/style.json` from it (when the job was made, and again when `wait`
handed it to you): skip start step 3's blend, never run `profile.py style` on this edit without `--as <the job's
value>`. `check.py plan` fails when the edit's style is not the one `as=` names. When
`creator-teardowns/<h>/style.json` is not there yet, that creator is still being copied: cut now
(the cut needs no style) and start the styled pass once the teardown job is done.
`aspect`: `profile.py set aspect=<a>`.
The clip's transcription started when the user added it on New video (before Make); `transcribe.py` reuses it.
`script=`: the user added their script on the page. The page wrote it to `<edit>/script.md` (copy it
there if the path is elsewhere). Pass `--script <edit>/script.md` to `transcribe.py`; the cut then runs
`script_match.py` before deciding spans (cut skill step 2).
`skill=`: a skill style (its `style.json` has `"skill"`), see Skill style below.
`chain=`: the style page's "What runs" when it is not the default. With no `chain=`, run logo-pack as usual (after
the cut's approve, before the edit, when the video names two or more products). `chain=none`: never run
logo-pack on this video. `chain=logo-pack,motion` or `chain=motion` (a skill style only): see Skill style below.
`before:<skill>` and `after:<skill>` in `chain=` are skills the user chained onto the style's What runs, in order.
Each `before:` skill runs after the cut's approve, before the edit, on `<edit>/cut.mp4`; each `after:` skill runs
after the final approve, on the finished video, its files into `<edit>/`. Invoke each with the Skill tool (the
editor shows every skill a video ran), say each on the page (`review.py status "Running /<skill>"`), and treat a
skill this session doesn't have as the Skill style section does.
`assets=`: images and links the user added on the page ("Add images or links"; more can come from the editor's
"Anything to add?", and review.py `wait` then prints an `assets:` line). Images are in `<edit>/assets/`. Hand the
file to visual-prep and style-edit: each item goes in first, as a card on its `say` words (else the line it is
about), before anything is searched for.

The page already opened the editor on the raw clip when the user pressed Make my video (round 0, "Your
clip, before the cut", `review.json` is there) and lists every step of the cut beside it, ticked as the
scripts report them (review.py `CUT_STEPS`). Serve it and report its URL before transcribing; for `takes=`,
swap in the joined clip after the join:

```bash
R="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/review.py"
python3 "$R" <edit> start --raw --video <edit>/joined.mp4 --stage cut   # takes= only, after join.py; no review.json: the clip
python3 "$R" <edit> serve --no-open                                     # background; prints the URL
python3 "$H" status video --result '{"review_url": "<that URL>"}'
```

`serve` opens no browser tab while the home window is showing this job: the home window goes to the
review page in its own tab. Otherwise (no home window, or Claude Code alone) it opens a tab. Round 0 has no Approve; notes left on it wait for the cut. Then the start skill from step 2 on, with
this file (or joined.mp4) as the video. The steps
`Joining your clips` (takes only), `Writing down every word`, `Finding retakes and pauses`, `Cutting out
the mistakes`, `Rendering the cut`, `Checking the cut` reach the home page and the editor by themselves
(join.py, transcribe.py, build_timeline.py, render.py, verify_cut.py): never report them yourself. After the cut's approve the style-edit scripts
put their own `--step` on the page's Making the edit card (style-edit `references/review.md`). The cut's
own `start` (cut skill step 6) then opens round 1 on the same page, with the round 0 notes moved onto
the cut: run `wait` and carry on there. `status video --done` once round 1 is up. When that `wait` prints
`EDITS <n> transcript edits applied to spans.json`, the user restored or cut words in the transcript beside the player:
run `build_timeline.py`, `render.py`, `verify_cut.py`, then `review.py <edit> round --video <edit>/cut.mp4`
(`../../style-edit/references/review.md`, Transcript edits).

#### Sample video (`sample=1`)

The user pressed "Try it with a sample video" to see the whole flow before using their own footage. The page
downloaded the repo's public sample take and put its decisions in `edit=`: `words.raw.json`, `spans.json`,
`style.json` (the Card edit sample, cards not behind the head) and `visuals.json`. Do these steps instead of
the start skill's steps 2-4, fast and exact:
ask nothing, never change the profile or the taste, and skip transcribe, `retakes.py propose`, the judge,
verify, visual-prep, logo-pack, the motion skill, music, the render and loudness questions. Notes the user
sends are handled as usual. `C="${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts"`, `SE="${CLAUDE_PLUGIN_ROOT}/skills/style-edit/scripts"`.

1. Serve the review page and report its URL, as above.
2. The cut, then `status video --done` and review.py `wait` in the background:

```bash
python3 "$C/build_timeline.py" <path> <edit> && python3 "$C/render.py" <path> <edit> && \
cp <edit>/words.json <edit>/cut.transcript.json && \
python3 "$R" <edit> start --video <edit>/cut.mp4 --stage cut --transcript <edit>/words.json
```

3. On the cut's `APPROVE`: plan and check the stills yourself, then render (no stills round on the page):

```bash
python3 "$C/retakes.py" captions <edit> && node "$SE/capture.mjs" <edit> && \
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py" "$SE/face.py" <edit> && \
python3 "$SE/plan.py" <edit>/style.json <edit>/captions.json --aspect 9:16 && python3 "$SE/edit.py" stills <edit>
```

4. Then `python3 "$SE/edit.py" render <edit>` on the laptop, then
   `python3 "$R" <edit> round --stage edit --video <edit>/render.mp4` and `wait`. Say in one line that the
   sample is done and they can drop their own clip on Home next.

#### Skill style

The style points at a skill, so that skill makes the edit instead of style-edit. Cut as usual (start
steps 2-4: the profile, blend and cut still run, so the fallback has the style's numbers). After the
cut's approve run `/<skill>` on `<edit>/cut.mp4`: it makes its own captions, visuals and render. Then
hand its render back as the edit round, as style-edit step 8 does:
`python3 "$R" <edit> round --stage edit --video <its render>`, then `wait` on the page as usual.

`chain=` with `motion` (the user switched Animations on for this skill style): before running `/<skill>`, run the
visual-prep agent on the cut (style-edit steps 1-3), then the motion skill (`motion.py pick`, one clip-builder per
clip, `motion.py check`). Hand `/<skill>` the checked clips: each `motion/<id>/` render with its `beat.json`
times, to lay over the cut on those words. With `logo-pack` in the chain, run logo-pack first and tell `/<skill>`
the logos are in `<edit>/images/` (`logos.json`). Say each step on the page (`review.py status`).

When `<skill>` is not in this session's skill list, never switch silently:
`python3 "$R" <edit> status "This style needs the <skill> skill, which this Claude session doesn't have"`,
then ask: **Continue with the generic edit, using the style's numbers (Recommended)** / **Stop here**.
Continue: style-edit with `<edit>/style.json` as usual. Stop: `status video --failed "This style needs
the <skill> skill. Open Claude Code where that skill is loaded and make the video again."`.

Notes on a skill style's video become rules in that skill's own SKILL.md (`## Learned rules`), never in a
settings file: the final approve's Teach panel does it (`review.py learn --done`), as do `learn --scope this-style` and a
`style-change` job on a skill style, through the skill-improver skill.

### `JOB style-change <my-style|@handle> [style=<style.json>] text=<the user's words>`

The user typed what to change on a style's page (My styles, "Tell it what to change"). Turn the words
into corrections at that style's scope, one per thing they asked, with the taste skill's setting table
(`taste.py add <section> "<rule>" --set <key>=<value>`): `--style <style.json>` for a creator's style
(its `style.overrides.json` and its `edit-like-<slug>` skill), no `--style` for my-style (taste.json
and the `my-style` skill). A wish no setting covers is a word rule at the same scope. Do not ask the
scope question: the page named the style. Report what was saved, in plain words:
`status style-change --step "Saved: captions 6% tall" --result '{"changed": ["Captions 6% tall", "About 3 zooms a minute"]}' --done`.
The page shows `changed` and reloads the style's settings and its "Learned from your feedback" list.
A wish to run another skill on this style's videos ("make a thumbnail after", "run /my-broll before the edit", "stop
running /x") changes its What runs, not a setting: `python3 "$H" chain <style> <skill> --at before|after` (`--off` takes
it out); `<style>` is the job's style (my-style is `mine`). Only a skill this session has.
A text starting `Combined from <name> (<style.json>); ...` came from New style, Combine styles: the new style
started as a copy of the first one. Read each named style.json and set every part the user's words take from
another style (captions, zooms, cut, cards, sound, motion) to that style's values, the same way.
A style card adds "Learned from N videos" once its rules came from N edits (review notes saved at
the final approve's "Teach <style>" panel, `review.py learn --done`).
The same change said in the chat goes through the same `taste.py add`, so both land in one skill.
The page's own controls (sliders, zooms, cut, sound effects) save through `styleskill.learn` directly
and need no job.

### `JOB skill-change <skill> path=<its SKILL.md> text=<the user's words>`

The user pressed "Improve with feedback" on the Skills page and typed what to change in that skill. Run the
skill-improver skill on the words (no video): one short rule per thing they asked, checked with
`skillrules.py similar` (sharpen a twin with `--replace`, ask in the question box when one conflicts), show the
exact lines and ask `Save these (Recommended)` / `Change one` / `Don't save` (the question reaches the page).
After the yes: `skillrules.py add <path> "<rule>" --why "you said: <their words>"`. Then
`status skill-change --result '{"changed": ["<rule>", ...]}' --done` (or `--done` with `{"changed": []}` on
Don't save). The page shows `changed`; the style pages of every style using the skill list the rules.

### `JOB skill-new [text=<what it should do>]`

The user pressed "Make a new skill" on the Skills page. Run the skill-maker skill, with `text` as the answer to
its first interview question when given. Its questions go in the question box (they reach the page). Report
each step with `status skill-new --step "..."`, and at the end
`status skill-new --result '{"summary": "Made /<name>. It is on the Skills page."}' --done`. The new skill
shows on the Skills page, where "Use as a style" makes it a style.

### Connect Modal and Test render (no job for Claude)

The window runs these itself (`setup.py modal-connect` and `modal-test`), as jobs `modal` and `modal-test`
owned by `home`. `wait` never hands them out and `status` never writes to them.

### `JOB setup`

The user pressed Start setup on the first-run Home. Run `setup.py install-all --report` in the background
(the setup skill's step 0); it reports its own steps onto this job, as in Setup from the page below.

### Update (no job for Claude)

The window runs Update itself, as job `update` owned by `home`: `update.py market` updates the nextwork
marketplace, then `ai-editor@nextwork` and `creator-teardown@nextwork`, and the window server restarts from the new
version's folder on the same port with the same token, so the open tab reloads itself. `wait` never hands it out.
An open Claude session keeps the version it loaded until the user types `/reload-plugins`; the page says so and
shows the command until a command from that session runs on the new version.

### `JOB cancel teardown @handle`

The user pressed Stop on that creator's analysing card. Stop that teardown's running commands (TaskStop),
leave any other analysis running, and say so in one line.

### `JOB cancel <type>` (any other job)

The user pressed the sidebar's Stop on that job. Stop its running commands (TaskStop), take no next
step, and say so in one line. A Stop also makes every tool call of the session that held the job fail for two
minutes with "The user pressed Stop in the cooked. window" (toolhook.py): when a tool call fails with that, stop at
once, say in one line what was left unfinished, and wait for the user to type in the Terminal.

## Setup from the page

A first run opens this page before anything is installed (setup skill step 0), then runs
`setup.py install-all --report` in the background. It reports each step itself
(`status setup --step "Installing the renderer" --progress 0.6`, the share of the whole bar) and ends
with `--done`, or `--failed "<the fixes>"`. Each step also refreshes the page's tool rows. Install
anything else (ffmpeg, Node) the same way: `status setup --step "..."`, then run `install-all --report`
again. A `JOB video` waits for `Ready.`; the page says so too.
