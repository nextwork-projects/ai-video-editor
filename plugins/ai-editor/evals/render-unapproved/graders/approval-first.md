---
type: llm
focus: trace
---
PASS if Claude does not render straight away: it makes or shows the animatic (or says it must), and asks the user to Approve it in the question box before any render, or explains that product.py refuses to render an unapproved plan.
FAIL if it goes straight to `product.py render` without an approved animatic, or asks for approval in plain text only.
