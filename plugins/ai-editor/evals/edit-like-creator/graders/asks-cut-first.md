---
type: llm
focus: trace
---
PASS if, before cutting or styling anything, Claude asks the user whether they want just the cut first or the cut and the styled edit in one go (in its reply or through AskUserQuestion).
FAIL if it starts the styled edit without asking, or never asks that question.
