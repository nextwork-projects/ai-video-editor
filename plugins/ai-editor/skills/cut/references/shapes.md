# Shapes

The one file Claude writes in the cut skill. Rules for what to cut: `retake-detection.md`.

## spans.json

```json
[
  {"text": "so the thing about, um,", "kind": "false_start", "note": "restarts at 5.8s"},
  {"text": "wait, sorry", "kind": "meta"},
  {"text": "the second thing is that you", "kind": "retake", "occurrence": 1,
   "confidence": "medium", "note": "keeper is the take at 70.4s"}
]
```

| field | rule |
|---|---|
| `text` | Words copied from the transcript. Punctuation and case do not matter. |
| `kind` | `retake`, `false_start`, `filler`, `meta`, `audio_event`, `redundant` |
| `occurrence` / `after` | Required when the phrase appears more than once. `occurrence` is 1-based. `after` takes the first match starting after that many seconds: use the phrase's start time from `transcript.txt`. |
| `confidence` | `high` (default), `medium`, `low`. `low` cuts are highlighted for the user. |
| `note` | Why, in a few words. For a retake, where the keeper is. |

Two spans must not overlap. Merge them into one.
