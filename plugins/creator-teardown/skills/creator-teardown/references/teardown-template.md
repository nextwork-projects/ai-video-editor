# Teardown template

Fill this in. Write to `creator-teardowns/<handle>/teardown.md`.

---

```markdown
# Teardown: @<handle>

<N> videos pulled <date>. Median <X> views across the set. Transcribed: the
<n> outliers plus <n> median performers as a control.

Source: <profile url>  ·  Pulled with the creator-teardown skill

---

## The format in one block

<The buildable spec. Someone should be able to film from this alone.>

- Runtime: <X–Ys>
- Time to hook: <X.Xs>
- Hook: <N words, shape>
- Body: <N items, X–Ys each>
- Per item: <the internal shape>
- Close: <shape>
- WPM: <X> (<Y> in the body, <Z> on the close)

---

## #1: "<title>" · <duration> · **<views> views** · <likes> likes · <saves> saves
<url> · <X.X>× their median

**Transcript (verbatim):**
> <full transcript>

**Beat map:**

| Beat | Start | Dur | Words | WPM | Text |
|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... |

**What it does that the median videos don't:**
- <move>: <the evidence, with the timestamp>

**Patterns we keep:**
- <structural move worth stealing>

**Patterns we reject:**
- <banned move>: <the line it appears in>

---

## #2 ... (repeat per video)

---

## Control group: the median performers

<Which videos, what views.>

Moves present here AND in the winners (= habit, not lever):
- <move>

Moves present ONLY in the winners (= candidate levers, N of M videos):
- <move>: <N/M>

---

## Voice profile

| Measure | Value |
|---|---|
| Median sentence length | <N> words |
| you : I : we | <a : b : c> |
| Imperatives per 100 words | <N> |
| Recurring phrases | <list> |
| Register | <one line> |

**Banned moves found:** <count each, with one example line>

**Register call:** <one paragraph on what changes for the user's voice>

---

## The shared formula

| Beat | What every winner does |
|---|---|
| Hook | ... |
| Body | ... |
| Per-item | ... |
| Close | ... |

---

## Verdict

<Worth a skill? Which existing skill does it overlap? What is genuinely new?>
```

---

## Rules for filling it in

- **Every stat is real.** Copy from `videos.json`. Never round a view count up
  into a rounder story.
- **Transcripts are verbatim.** Including the stumbles. Do not tidy them.
- **"Patterns we reject" is never empty.** If a creator has no banned moves,
  say so explicitly: that itself is the finding.
- **Timestamps are measured** off `words[].start`, not guessed from reading.
- **The verdict can be no.** A format that overlaps one the user already has by 90%
  is a note, not a new skill. Say that.
