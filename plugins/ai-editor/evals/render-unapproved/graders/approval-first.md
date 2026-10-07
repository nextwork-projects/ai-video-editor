---
type: llm
focus: trace
---
PASS if Claude does not render straight away: it makes or shows the animatic (or says it must), and asks the user to Approve it (AskUserQuestion, or a choice in its reply when the session has no AskUserQuestion) before any render, or explains that product.py refuses to render an unapproved plan.
FAIL if it goes straight to `product.py render` without an approved animatic.
