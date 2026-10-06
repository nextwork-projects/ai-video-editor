---
name: clips
description: Turns one long video or podcast (a local file or a YouTube link) into the best 3-5 short vertical clips, each cut and styled in the user's profile style. Transcribes once, splits the talk into candidate clips at sentence boundaries inside the chosen length, scores every candidate in code (speech rate, loudness, laughter, numbers and names said) and with TypeSafe's Jev (hook alone, self-contained, pays off, concrete, the creator's measured moves), shows the shortlist on one page with a preview of each, then trims, cuts and style-edits each pick as its own edit. Use when the user says "clip this video", "make shorts from my podcast", "find the best clips", "cut this into TikToks", "turn this YouTube video into reels", "repurpose this long video", or drops a long video (over about 3 minutes) or a YouTube link and wants short clips. Not for editing one short take (that is start or cut), and not for measuring someone else's style (that is creator-teardown).
license: MIT
compatibility: Python 3.9+, ffmpeg, yt-dlp for links, and the venv, Node and renderer the setup skill installs. Recommended TypeSafe key (Jev scores every candidate for about 2 cents a video; without it Claude judges an 8-clip shortlist). Runs from the full ai-editor plugin folder (uses its lib/ and the cut and style-edit skills).
---

# Clips

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

One long video in. The best few short clips out, each a finished vertical edit in the user's style.

```
clips/<name>/
  source.mp4          the long video (a symlink for a local file; never modify the original)
  words.raw.json      one transcript of the whole thing (never read it)
  candidates.json     every candidate with its features and Jev answers (never read it)
  shortlist.md        the top 8 that do not overlap, about 1,500 tokens: the only file you read
  shortlist.json      the same, for the page
  jev-usage.jsonl     what Jev cost
  picks.html          the page the user picks from
edits/<name>-clip<N>/ one edit per chosen clip: source.mp4, words.raw.json (re-timed), clip.json
```

`PY=~/.ai-video-editor/venv/bin/python` (Windows: `%USERPROFILE%\.ai-video-editor\venv\Scripts\python.exe`).
If it is missing, run the `setup` skill first. `K="${CLAUDE_SKILL_DIR}/scripts/clips.py"`,
`C="${CLAUDE_PLUGIN_ROOT}/skills/cut/scripts"`, `S="${CLAUDE_PLUGIN_ROOT}/skills/style-edit/scripts"`.

## 0. Ask, once

Read the profile and taste first (`python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" show`,
`python3 "${CLAUDE_PLUGIN_ROOT}/skills/taste/scripts/taste.py" show`). No profile yet: run the
`start` skill's style intake first, so the clips come out in the user's look.

Then one call to the question box (the AskUserQuestion tool; numbered text questions only in an
agent without it), the recommended option first:

| question | options |
|---|---|
| How many clips? | 3 (Recommended) / 5 / 1 |
| How long should each be? | 20-40 s (Recommended) / 40-60 s / 60-90 s |
| How many people talk in it? | one (Recommended) / two (a podcast or interview) |

Skip any the user already answered. These replace the cut skill's "cut first or everything at
once" question: clips run straight through, and the user approves the picks and the stills.

## 1. The video

A local file: `mkdir -p clips/<name> && ln -s "<absolute path>" clips/<name>/source.mp4` (Windows:
copy it). A link:

```bash
yt-dlp -f "bv*[height<=2160][ext=mp4]+ba[ext=m4a]/b" --merge-output-format mp4 -o clips/<name>/source.mp4 "<url>"
```

If YouTube asks to sign in ("confirm you're not a bot"), add `--cookies-from-browser chrome` (or
the user's browser). Only download what the user has the right to reuse: their own video, or one
they have permission for. Say so once if the link is someone else's.

## 2. Transcribe once

```bash
$PY "$C/transcribe.py" clips/<name>/source.mp4 clips/<name>/words.raw.json
```

Same engines as the cut skill. Scribe adds laughter and other audio events, which the score uses.
Every clip reuses this transcript: nothing is transcribed twice.

## 3. Candidates and the shortlist

```bash
python3 "$K" candidates clips/<name> --min 20 --max 40 [--speakers 2] [--style creator-teardowns/<handle>/style.json]
```

Pass the length the user picked. `--style` is the profile's first creator: the "what works" moves
measured there are scored too. Code splits the transcript into sentences and makes every run of
whole sentences inside the length a candidate (never starting on "Mm-hmm" or ending mid-word),
measures each, asks Jev four questions about each, and writes `shortlist.md`.

- **Exit 0.** Read `shortlist.md` only. Each entry has the hook, the opening words of every
  middle sentence, the last sentence, the Jev scores and the measured features.
- **Exit 4: no TypeSafe key.** The shortlist is ranked by the features alone. Read it and judge each
  entry yourself on the same four questions: does the hook work alone, can a stranger follow it,
  does it pay off, is there a concrete claim, number or story. Tell the user once that a
  TypeSafe key makes this cheaper and better (the `setup` skill walks them through it).

Never read `words.raw.json` or `candidates.json`. Pick the user's number of clips from the
shortlist, best first. Drop, whatever the score:
- an ad read, a sponsor segment, an intro or a sign-off;
- a hook that leans on earlier context ("as I said", "that's why", "this one");
- a clip whose point is a dated claim ("at the time I'm recording this, it's number 40") when the
  claim has since changed: a live capture of today's page would contradict it.

## 4. The picks page, then the question box

```bash
python3 "$K" page clips/<name> --recommend c12,c40,c7
open clips/<name>/picks.html    # Windows: start "" ..., Linux: xdg-open ...
```

One page: every shortlisted clip with a 360 px preview, its transcript (the hook in bold), the
score breakdown and the measured features, your picks marked. Then ask in the question box
(multi-select): your picks first, each labelled with its time and its hook, plus "a different one
from the page". Wait for the answer.

## 5. Each chosen clip

```bash
python3 "$K" trim clips/<name> c12 c40 c7          # -> edits/<name>-clip1, -clip2, -clip3
```

Each edit folder gets `source.mp4` (frame-accurate, padded without catching the next word) and
`words.raw.json` re-timed to it. For each one, in order:

1. **Vertical from a wide video:** `$PY "$K" reframe edits/<name>-clip<N>` crops to 9:16 with the
   crop following the speaker's head shot by shot (camera cuts found with ffmpeg). Skip it when the
   profile's platform is YouTube or the source is already vertical.
2. **Cut:** the cut skill from its step 2 (`retakes.py propose`): the transcript is already there.
   Then build, render, verify and the cut page, as that skill says. A published video often has
   music under the voice: when `build_timeline.py` stops on the silence threshold, pass `--noise`.
3. **Style:** `python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" style edits/<name>-clip<N>`,
   then the style-edit skill from its step 2. If the source already has captions burned in, set
   `"captions": {"present": false}` in that edit's `style.json`, or the captions stack.

Show all the clips' stills sheets together for one approval, ask the render question once for all
of them, and render. Open every render and give the full paths.

## Rules

1. Every word, number and name on screen comes from that clip's own words. Nothing from the rest of
   the video, and nothing the speaker did not say.
2. No AI-tell looks: `${CLAUDE_PLUGIN_ROOT}/skills/style-edit/references/ai-tells.md` applies to every clip.
3. A close-up podcast frame has no free space: no card or logo goes over the head. Fewer visuals is
   right; captions and zooms carry it.
4. Never cut a clip mid-sentence. Shorter or longer than asked beats a broken thought.

## Cost per long video

Measured on a 13-minute two-person podcast and a 12-minute talking-head video (2026-10):
- Transcription: Scribe took 16-18 s; Whisper is free and slower. Once per long video.
- Candidates and features: 4-6 s of code, $0.
- Jev: 1,250-1,300 questions over 380 candidates, about 310,000-390,000 input tokens: $0.013-0.016
  (sized from the requests; the live bill lands in `jev-usage.jsonl`).
- Claude reads `shortlist.md` (about 1,500 tokens), never the transcript (about 20,000).
- The picks page: 30-40 s of ffmpeg for 8 previews, 7-9 MB.
- Each clip then costs what one cut and one style edit cost.

## Self-check

```bash
python3 "$K" demo
```

## Files

- `scripts/clips.py`: candidates, page, trim, reframe and the offline demo (synthetic transcript,
  canned Jev answers). Stdlib only, except `reframe` (OpenCV, through the venv).
