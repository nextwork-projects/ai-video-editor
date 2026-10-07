---
type: llm
focus: trace
---
PASS if Claude launches one clip-editor agent per chosen clip (three) in a single assistant message, so they run at the same time, each given its own clip folder, and then works from their short JSON summaries.
FAIL if it launches them one per message, waits for one before launching the next, launches fewer than three, or edits the clips itself one after another while the Agent tool is available.
