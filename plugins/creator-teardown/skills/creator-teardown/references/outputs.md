# What a teardown writes

Everything lands under the folder Claude Code was started in. Claude reads `look.md` and
`transcripts/<id>.txt`; the JSON files, frames and sheets are for the scripts.

```
creator-teardowns/<handle>/
  videos.json                 stats for every video pulled
  transcripts/<id>.json       verbatim, word-level timings
  transcripts/<id>.txt        flat text + role/views/duration/wpm header
  metrics.json                measured pace, pauses, fillers per video
  video/<id>.mp4              the picked videos (visual pass)
  video/<id>.visual.json      cut times, shot lengths, zoom events per video
  video/<id>.look.json        OCR lines, faces and graphics per sample (look.py)
  video/<id>.look-ai.json     the look pass's words per video (Gemini or fallback)
  video/<id>.graphics.json    every graphic: box, kind, entrance, exit, hold, motion
  video/<id>.sound.json       sound effects and music
  graphics/                   one crop per graphic + heatmap.png
  sheets/<id>.jpg             one 3 x 3 sheet per video, read only in the fallback
  style.json                  every measured number, for editing in this style
  look.md                     the look in under 48 lines: what Claude reads
  teardown.html               THE PAGE: what the user looks at (report.py)
  report.json                 hook, winners against control, AI tells
  teardown.md                 THE ANALYSIS
  events.json                 card events, when the card pass ran
edit-plans/<name>/
  plan.md, plan.srt           the user's video, planned in the creator's style
```
