---
max_turns: 8
plugins: ["../..", "../../../creator-teardown"]
append_system_prompt: "Eval dry run: this session has no shell, file-edit or network tools, and that is expected; do not ask for them. Where a step runs a command, write the exact command and its likely result in one line, then go on to the next step that needs the user and stop there with your question."
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion]
---
set up the ai video editor for me
