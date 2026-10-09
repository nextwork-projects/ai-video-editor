# Judge rubric: grading a cut before it renders

The `cut-judge` agent grades the paper edit `judge_cut.py prompt` writes, against this file.
`judge_cut.py apply` applies the fixes to `spans.json`. The judge never edits a file itself.

**You are not deciding whether the edit is good. You are finding specific, quotable defects.**
"Feels a bit long" is not a finding. `he ended up <<7>> he ended up being` is a finding.

## The asymmetry (this decides every severity)

| failure | who pays | severity |
|---|---|---|
| a good take **destroyed** by a cut | the speaker: the take is gone and they may not notice | **blocker** |
| a mistake that **survived** into the edit | the viewer: it ships | **blocker** |
| the edit is **longer than it could be** | the speaker: one trim later | warn |

Restoring is safe; cutting is not. Unsure whether something should have been cut? Restore it and
say so. Never "cut more to be safe".

## Protocol

1. Read "What plays" end to end first, before any cut. Hear it the way a viewer does. Reading the
   cut list first anchors you into agreeing with it.
2. Mark every place it stops sounding like a person talking. Quote it exactly.
3. Then read "Cuts" one by one and apply B3, B4 and W5.
4. Emit the JSON. Nothing else.

## The six checks

### B1 · SURVIVING MISTAKE (blocker)
What plays still holds a flub: a stutter, an abandoned clause, a doubled phrase, a self-interrupt
(`wait`, `sorry`, `again`, `let me redo`), or the same line delivered twice. Fix `add`.

### B2 · BROKEN SPLICE (blocker)
At a `<<n>>` marker, the words either side do not join into speech a person would say:

- a word or phrase repeated across the join (`he ended up <<n>> he ended up being`)
- a clause that starts mid-thought because its head was removed
- a subject with no verb, or a verb with no subject, made by the join
- a pronoun whose antecedent was cut (`that door` when no door survives)
- two halves of different takes stitched into a sentence nobody said

**Not a broken splice:** a sentence starting `and`, `but` or `so`, or a fragment. That is how
people talk. Flag only a join that fails to parse as speech. Fix `restore` or `trim`.

### B3 · DESTROYED TAKE (blocker)
A cut that claims a better take exists removes content found **nowhere in what plays**.

Scope: kinds `retake`, `false_start`, `filler`, `meta`. Each says "this is said better
elsewhere". Search what plays for that better take. Two shapes:

- the better take does not survive (or never existed)
- the removed take carries a **detail the kept take drops**: a name, a number, a reason. A partly
  repeated line is not a repeat. Fix `restore`.

`redundant` cuts are out of scope for B3. They remove good content on purpose, so "the content
is gone" is true of every one and proves nothing. Judge them on B4, and raise W5 when the case is
weak. (`apply` turns B3 on a `redundant` cut into W5.)

### B4 · LOST DEPENDENCY (blocker)
What plays depends on something a cut removed: a name introduced only inside a cut, a number
referred back to, a payoff whose setup is gone. Fix `restore` of the cut carrying it.

### W5 · WEAK CASE (warn)
The cut may be right but its stated reason is not: the note names a better take that is not
there, the kind does not match (a fluent complete take marked `false_start`), or a `redundant`
cut argued from pace alone. Fix `none`, unless it also trips B3.

### W6 · UNDER-CUT (warn, never a blocker)
Something is still in that should probably go: a filler run, a line the next one says again,
trailing talk after the point lands. Fix `add`. At most **3 W6 per pass**. `apply` only
suggests W6 adds unless the user asked for a tighter cut.

## Do not flag

- Length or pacing. You cannot hear the cut. Silence is the build's job.
- Style or wording. You are not the writer.
- Departures from a script. A script breaks ties between takes; it never filters content.
- Speech habits: `and so`, lowercase openers, long sentences, a phrase repeated for rhythm.
- Silence, gaps, breaths.

## Output

Exactly one fenced `json` block, nothing outside it.

```json
{
  "verdict": "FAIL",
  "summary": "one line: what the edit does and the biggest risk left",
  "findings": [
    {"check": "B2", "severity": "blocker", "cut": 7,
     "quote": "he ended up <<7>> he ended up being the",
     "problem": "the join repeats 'he ended up': both takes' openers survive.",
     "fix": {"action": "trim", "keep_words": "being the"}}
  ]
}
```

| field | rule |
|---|---|
| `verdict` | `FAIL` if any finding is a blocker, else `PASS` |
| `check` | `B1` `B2` `B3` `B4` `W5` `W6` |
| `cut` | the `Cn` number the finding is about, or `null` for B1 or W6 on kept text |
| `quote` | **required**, copied exactly from the paper edit. No quote, no finding. |
| `problem` | one sentence: what is wrong, not what to do |
| `fix.action` | `restore`, `trim`, `add` or `none` |

| action | needs | what `apply` does |
|---|---|---|
| `restore` | `cut` | deletes that span: the words come back. Always safe. |
| `trim` | `cut`, `fix.keep_words` | gives back a run from the **head or tail** of the cut's words. Exact words. |
| `add` | `fix.evidence`, `fix.kind` | cuts that text. It must be kept now, quoted exactly, and unique in what plays. |
| `none` | | shown to the user, nothing changes |

An `add` of text an earlier round gave back is refused. Do not propose it again.

## Calibration

A first pass over real footage finds **0-4 findings**. Ten or more means you are grading style:
re-read "Do not flag" and keep only what you can quote. Blockers are rarer than warnings.
