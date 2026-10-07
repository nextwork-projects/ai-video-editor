---
max_turns: 6
plugins: ["../..", "../../../creator-teardown"]
append_system_prompt: "Eval dry run: this session has no shell or file-edit tools, and that is expected; do not ask for them. Where a step runs a command, write the exact command and its likely result in one line, then go on. Treat the editor as installed and every file the user names as present: clips/talk/ has its shortlist and picks page, and `clips.py trim clips/talk c12 c40 c7` has written edits/talk-clip1, -clip2 and -clip3. The profile says sound.music false. Agents you launch are stubs that return their JSON at once."
allowed_tools: [Read, Glob, Grep, Skill, AskUserQuestion, Agent]
---
use the clips skill on ./talk.mp4. I already answered: 3 clips, 20-40 s each, one speaker, vertical source. I picked c12, c40 and c7 on the picks page and you trimmed them. Now edit all three clips.
