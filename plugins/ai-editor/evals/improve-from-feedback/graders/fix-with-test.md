---
type: llm
focus: trace
---
PASS if Claude works toward reading the collected feedback (suggestions.jsonl, the taste report, preview corrections or feedback-labelled GitHub issues) and treats each accepted item as a rule plus an enforcing check plus a test that fails before the fix.
FAIL if it only writes notes, edits the user's own taste file, or makes changes with no test.
