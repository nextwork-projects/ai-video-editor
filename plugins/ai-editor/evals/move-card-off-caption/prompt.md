---
max_turns: 8
plugins: ["../..", "../../../creator-teardown"]
append_system_prompt: "Eval dry run: this session has no shell, file-edit or network tools, and that is expected; do not ask for them. Where a step runs a command, write the exact command and its likely result in one line, then go on to the next step that needs the user and stop there with your question. Treat the editor as installed (ignore the startup notice that it is not set up) and every file or link the user names as present and working. The edit ./edits/demo is already rendered (render.mp4, plan.json, visuals.json); its Duolingo logo card starts at 15.3 s, and plan.py cards prints: card:1  15.32-16.30 s  logo  'Duolingo'@1  box 40.2,50,19.6,11  <- visuals.json[1]."
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion]
---
the Duolingo card at 0:15 in edits/demo sits right on my caption, move it
