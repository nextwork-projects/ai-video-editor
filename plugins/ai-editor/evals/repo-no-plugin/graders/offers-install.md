---
type: llm
focus: trace
---
The editor plugin is not loaded in this session. PASS only if all three hold:
1. Claude asks the user whether to install the editor before installing anything, with concrete choices (yes first), through AskUserQuestion or as a short list of options in its reply.
2. It names the install commands: `claude plugin marketplace add nextwork-projects/ai-video-editor` and `claude plugin install ai-editor@nextwork` (the `/plugin` forms of the same two count).
3. It says what comes after the install: `/reload-plugins` (or a restart), then the edit begins with the `start` skill (or the user says "edit my video" again, which starts it).
FAIL if it tries to edit the video without the plugin, asks for the video first, runs or claims to run the install without asking, or never says how the edit starts after installing.
