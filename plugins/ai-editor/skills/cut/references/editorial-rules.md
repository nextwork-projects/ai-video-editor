# Editorial rules: generic defaults

These rules cut content that is not a mistake. They are riskier than removing retakes, so they are
off unless the user wants the video shorter. Every cut made under them uses `kind: "redundant"`,
and cut-check.html highlights it for the user.

## The bar

A cut that removes something the user wanted is far worse than a cut that leaves something in.
Leaving a line costs them a trim. Removing a good take can cost them the take, and they may not
notice it is gone. When unsure, keep it, or cut it with `confidence: "low"`.

## Rules

### 1. Subsumed line
Cut a complete line when the next line says the same thing better.

> "She got the job after three interviews." then "After three rounds of interviews, she got the
> offer." Keep the second.

Keep the first if it carries a detail the second drops.

### 2. Doubled discourse marker
"You see, you see", "So, so", "But, but": cut the doubling, even when both are fluent. This covers
connecting words only. Repeated content ("I know a man... I know a man") can be deliberate and
stays. `verify_cut.py` lists every word or two-word pair said twice in a row in the render
(`DOUBLED`), with the span that cuts the first one.

### 3. Restating the point after it lands
Once the point has landed, cut the sentences that only say it again.

### 4. Announce, then ask
"Let's start with what an API is." then "So, what is an API?" Cut the announcement, keep the
question. Keep whichever line does the job; cut the one that only points at it.

## Pauses are not only dead air

The pause target comes from `style.json` (`pace.max_pause_s`) or the default 0.30 s. Two cases
where a pause is doing work:

- **Before a number or a reveal.** A short beat before a figure lets it land. If the cut feels
  rushed there, rebuild with a higher `--max-pause`.
- **Inside a spoken list.** Very tight pauses between list items make them run together.

Very short function words ("so", "I", "you") right after a join need a little lead-in or they
get swallowed. `build_timeline.py` leaves that room automatically. `verify_cut.py` reports any that
went missing.

## Opening and closing

- Cut dead air before the first kept word and after the last. The script does this.
- A breath or sigh that opens a personal story can be part of the story. If the user asks for it
  back, keep it with no pause cut between it and the first word.
