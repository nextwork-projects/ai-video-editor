---
type: llm
focus: trace
---
PASS if Claude stops and waits on a question to the user that offers concrete choices, recommended option first: through AskUserQuestion when the session has it, or as a short list of options in its reply when it does not (headless eval runs have no AskUserQuestion).
FAIL if it asks nothing, asks only an open question with no choices, or carries on working past the question.
