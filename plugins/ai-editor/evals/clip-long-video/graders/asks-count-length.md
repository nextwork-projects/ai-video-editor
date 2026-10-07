---
type: llm
focus: trace
---
PASS if, before transcribing or cutting anything, Claude asks how many clips the user wants and how long each should be (in its reply or through AskUserQuestion), with a recommended option first.
FAIL if it starts cutting clips without asking, or asks neither question.
