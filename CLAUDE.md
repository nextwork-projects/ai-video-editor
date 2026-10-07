# AI Video Editor

Most people who open this folder want to edit a video. When the user asks for an edit, drops a
video, pastes a link, names a creator, or asks how to start:

1. If the `ai-editor:start` skill is in your skill list, use it. It asks its own questions and runs
   setup, the creator breakdown, the cut and the styled edit in order.
2. If it is not (the folder was not trusted, or this Claude Code is too old to load plugins from
   `.claude/settings.json`), ask in the question box (AskUserQuestion) whether to install the
   editor, recommended option first. On yes, run:
   `claude plugin marketplace add nextwork-projects/ai-video-editor` then
   `claude plugin install ai-editor@nextwork`. Then tell the user to type `/reload-plugins` and
   say "edit my video" again.

If the user is changing this repo itself (skills, scripts, tests, docs), skip the above: follow
`AGENTS.md`, `docs/BACKLOG.md` and the `improve` skill. To stop the plugins loading while you work
on them, set them to `false` under `enabledPlugins` in `.claude/settings.local.json`.
