# Learn from a past edit

A video the user already cut by hand is a labelled example. The raw take is the input and their
posted cut is the answer. Lining the two transcripts up shows how they cut, with no questions asked.

## What to ask

In the question box: "Have a raw take and the version you posted? I can learn how you cut." with
`No, use the default cut (Recommended)` and `Yes, I'll give both paths`. On yes, ask for the two
paths. The raw take must be the same recording the posted cut was made from. A posted cut with
music, a voice-over or new lines added still works, but those words count as cut.

Downloading their own posted video from a link: the start skill's `links.py fetch` (only a video
they have the right to edit).

## Run it

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/run.py" "${CLAUDE_SKILL_DIR}/scripts/learn.py" <raw take> <posted cut>
```

- Both files are transcribed with the cut skill's `transcribe.py` (its default engine: local Whisper
  with no key) into `edits/learn-<raw name>/`. A re-run reuses them. A transcript JSON from
  `transcribe.py` can stand in for either file.
- `--engine scribe` or `--engine crisper` for verbatim transcripts. Whisper drops many "um"s, so with
  it the filler counts are low and the filler rule is rarely learned. Pauses and retakes still work.
- `--dry-run` measures and prints without saving anything.

## What it measures

| line | what it is | saved as |
|---|---|---|
| pauses | the gap their cut left where the raw take paused 0.3 s or more | `cut.max_pause` (1.5 x their median gap: the cut tightens a pause to two thirds of it) |
| breaths cut | how many of those pauses they tightened, and how many they left whole | shown only |
| retakes | a line said twice: did they keep the last take, the first, both or neither | a word rule, only when it is not "last take wins" |
| fillers | "um"/"uh" kept or cut; "like", "you know", "i mean" kept or cut | `cut.keep_fillers=true` when they kept two thirds or more of the ums; a word rule for the soft ones |
| FALSE CUTS | words their cut kept that our default cut removes | shown, with the time and the words |
| missed | words their cut removed that our default cut keeps | shown, the five longest runs |

A setting is saved only from enough evidence: 5 pauses, 2 retakes, 3 fillers. Fewer than that is
one habit, not a style. Each rule's text carries its counts ("you kept the first 3 of 4 times"), so
`taste.py report` shows where it came from. A second past edit updates the same rules, never a copy.

## Tell the user

One line per saved rule, the same as any correction:
`Saved to your taste: "Pauses left at about 0.20 s, as in your own edit (14 of 16 pauses tightened)" (cut, every video)`.

Then the false cuts, because those are good takes the first edit would have destroyed. A false cut the
saved settings do not cover (a retake they kept on purpose, a line our cut calls a false start) becomes
a word rule through the usual `taste.py add`, after asking "this video, your style, or would it help
everyone?". Missed runs are their taste we do not cut yet: name the biggest one and ask if it is a habit
worth a rule ("you cut the recap at the end").
