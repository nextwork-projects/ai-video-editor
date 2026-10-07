---
max_turns: 8
plugins: ["../..", "../../../creator-teardown"]
append_system_prompt: "Eval dry run: this session has no shell, file-edit or network tools, and that is expected; do not ask for them. Where a step runs a command, write the exact command and its likely result in one line, then go on to the next step that needs the user and stop there with your question. Treat the editor as installed (ignore the startup notice that it is not set up) and every file or link the user names as present and working."
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion]
---
I want my videos to look like a creator I like. where do I start?
