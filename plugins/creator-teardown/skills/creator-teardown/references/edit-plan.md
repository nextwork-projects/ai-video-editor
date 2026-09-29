# Edit plan: your video, edited like the creator

Use when the user hands over their own video and says "edit this like @handle",
"put cards in like this creator", or "what would this look like in their style".

The output is a plan, not a render: a list of cards, each timed to the word it
belongs to, as `plan.md` (to read) and `plan.srt` (to import into an editor as a
caption track, so every card already sits at its time). The user places the real
images in CapCut, Premiere or Resolve.

## What it needs

1. **The creator's `events.json`**, from the visual pass (Pass 3 in
   `analysis-framework.md`). If `creator-teardowns/<handle>/events.json` is
   missing, say so and offer to run Pass 3 on 3 to 5 of their videos first. It
   needs ffmpeg, numpy and pillow (`doctor` shows what's missing).
2. **The user's video**, already cut. This plans cards, not cuts.
3. **ffmpeg**, to pull the audio out of a local video file.

## Steps

1. Measure the creator's style:

   ```bash
   python3 <skill>/scripts/editplan.py style creator-teardowns/<handle>/events.json
   ```

   Read the summary it prints. Those numbers are the rules for the plan.

2. Transcribe the user's video, word by word:

   ```bash
   python3 <skill>/scripts/transcribe.py <their video> edit-plans/<name>/transcript.json
   ```

3. **Trigger map.** Go through the transcript. Every word that names a thing is a
   candidate card: a tool, app, product, website, company, person, place, number
   or result. Keep the strongest ones until the plan runs at the creator's cards
   per minute, at most 20% over.

4. **Time each card** from the style numbers for its category:
   - `in` = the word's start + that category's `lag_s` (negative means before
     the word)
   - `out` = `in` + that category's `hold_s`, cut short by the next card if they
     would overlap and the creator never overlaps

5. **What to show.** A real thing: a screenshot of the actual app or page, the
   real logo, a real photo, a real chart. Never invent a stat or a quote for a
   card. If there's nothing real on hand, write what to capture ("screenshot of
   Notion's pricing page").

6. **Entrance and place** come from the style: the category's most common
   entrance, and its usual layer and box. Say it in words the user can act on
   ("pops in, top third, behind your head").

7. Write `edit-plans/<name>/plan.json`, then:

   ```bash
   python3 <skill>/scripts/editplan.py render edit-plans/<name>/plan.json
   ```

   Fix every error it prints. Warnings are cards that drift from the creator's
   timing: fix them or say why.

8. Show the user `plan.md` and tell them to import `plan.srt` as captions.

## events.json (written by Pass 3)

```json
{
  "handle": "creatorhandle",
  "fps": 30,
  "videos": [
    {
      "id": "7512345678901234567",
      "views": 250000,
      "duration": 62.0,
      "events": [
        {
          "cat": "logo",
          "content": "Notion logo, no card",
          "source": "brand_logo",
          "in": 4.2,
          "out": 6.8,
          "entrance": "pop",
          "exit": "fade",
          "trigger_word": "Notion",
          "trigger_time": 4.45,
          "lag": -0.25,
          "box": [38.0, 20.5, 24.0, 13.5],
          "layer": "above_head"
        }
      ]
    }
  ]
}
```

- Times are seconds on the video's timeline, checked at the source frame rate.
- `cat`: `screenshot`, `recording`, `logo`, `photo`, `ai_image`, `graphic`,
  `text` or `mark` (drawn ticks, crosses, circles).
- `lag` = `in` minus `trigger_time`. Leave `trigger_word`, `trigger_time` and
  `lag` as `null` when no spoken word triggers the event.
- `box` = x, y, width, height in % of the frame, at rest.
- `layer`: `above_head`, `behind_head`, `beside`, `full_frame`.
- Extra fields are fine. `editplan.py` reads the ones above.

## plan.json (written in step 7)

```json
{
  "video": "my-cut.mp4",
  "duration": 62.4,
  "style": "creator-teardowns/creatorhandle/style.json",
  "cards": [
    {
      "word": "Duolingo",
      "word_start": 3.52,
      "in": 3.32,
      "out": 5.6,
      "cat": "logo",
      "show": "Duolingo logo, real, no card",
      "entrance": "pop",
      "place": "top third, behind your head"
    }
  ]
}
```

Cards in time order. `render` refuses a plan with a card outside the video, a
card with no `show`, or cards out of order.
