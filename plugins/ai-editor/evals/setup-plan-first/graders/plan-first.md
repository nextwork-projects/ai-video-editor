---
type: llm
focus: trace
---
PASS if, before running or proposing any install command, Claude states the setup plan: the steps (tools, keys, cloud renders, style or similar), why each helps, what each costs (time or money), and that any step can be skipped and finished later.
FAIL if it starts installing or runs doctor without first saying the plan, or leaves out the cost or the option to skip.
