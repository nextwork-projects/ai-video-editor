---
type: llm
focus: trace
---
PASS if Claude asks (AskUserQuestion, or choices in its reply when the session has no AskUserQuestion) whether the correction is about this video only, the user's own style, or would help everyone using the editor (any wording with those three choices).
FAIL if it never offers the "would help everyone" choice.
