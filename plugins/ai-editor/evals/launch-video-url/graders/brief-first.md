---
type: llm
focus: trace
---
PASS if, before planning or recording any video, Claude asks the brief: what the video must show, who will watch, and the one action at the end (any two of these count), through AskUserQuestion, or as choices in its reply when the session has no AskUserQuestion (headless eval runs).
FAIL if it plans, records or renders a video without asking what it must show.
