# AI Video Editor skills

**Most people who open this folder want to edit a video.** When the user asks for an edit, drops a
video, pastes a link, names a creator, or asks how to start: read
`plugins/ai-editor/skills/start/SKILL.md` in full and follow it (paths are explained under "Paths"
below). It asks its own questions and runs the other skills in order. If the user is changing this
repo itself (skills, scripts, tests, docs), skip this and follow "Rules for every agent". Claude
Code follows `CLAUDE.md` instead, which loads the same skill as a plugin.

Instructions for any coding agent (Codex, Cursor, Gemini CLI, Copilot, Claude Code) using the
skills in this repo.

## The skills

Each skill is a folder with a `SKILL.md` ([Agent Skills format](https://agentskills.io/specification)).
Read a skill's `SKILL.md` in full before doing its task.

| Skill | Folder | Use when the user says |
|---|---|---|
| `start` | `plugins/ai-editor/skills/start/` | "edit my video", "make my video look like @creator", drops a video |
| `setup` | `plugins/ai-editor/skills/setup/` | "set up the editor", or a tool is missing |
| `cut` | `plugins/ai-editor/skills/cut/` | "cut my video", "remove my mistakes" |
| `style-edit` | `plugins/ai-editor/skills/style-edit/` | "style it", "add captions and zooms", "render the edit" |
| `taste` | `plugins/ai-editor/skills/taste/` | a reaction to an edit: "captions too small", "fewer zooms" |
| `product-video` | `plugins/ai-editor/skills/product-video/` | "make a launch video for <url>", "product video of my site", pastes a website |
| `clips` | `plugins/ai-editor/skills/clips/` | "clip this video", "make shorts from my podcast", drops a long video or YouTube link |
| `improve` | `plugins/ai-editor/skills/improve/` | maintainers: "improve the editor", "turn feedback into fixes", "process suggestions" |
| `creator-teardown` | `plugins/creator-teardown/skills/creator-teardown/` | "break down @handle", "tear down @handle" |

Order: `start` asks a few questions once, then runs setup, creator-teardown, cut and style-edit in order.
`creator-teardown` measures a creator, `cut` cleans the user's take, `style-edit` renders
it in that creator's style. `taste` runs whenever the user corrects an edit; a correction the user says would help everyone goes to
`~/.ai-video-editor/suggestions.jsonl` (and, if they agree, a GitHub issue), which `improve` turns into fixes here.
`product-video` stands alone: a URL in, a product video out (no footage, no creator).

## Paths

The skills are written for Claude Code, which fills in two variables. Elsewhere, read them as:

- `${CLAUDE_SKILL_DIR}`: the folder containing that `SKILL.md`.
- `${CLAUDE_PLUGIN_ROOT}`: the plugin folder two levels above it (`plugins/ai-editor/`).

The ai-editor skills share code in `plugins/ai-editor/lib/` and the renderer in
`plugins/ai-editor/remotion/`, so keep the repo layout. Clone the whole repo rather than copying
single skill folders.

## Install

- **Claude Code:** `/plugin marketplace add nextwork-projects/ai-video-editor`, then
  `/plugin install ai-editor@nextwork`. See the README.
- **Any agent with the skills CLI:** `npx skills add nextwork-projects/ai-video-editor`.
- **Cursor and Codex:** this repo ships `.cursor-plugin/plugin.json` and `.codex-plugin/plugin.json`,
  both pointing at the same skill folders.

## Rules for every agent

- Never ask the user to paste an API key into the chat. Keys are saved with the commands the
  skills give, in the user's own terminal.
- Ask before creating a GitHub repo or spending money on AWS.
- Work in the folder the user started in: `creator-teardowns/<handle>/` and `edits/<name>/`.
- Self-checks: `python3 tests/check_plugins.py`, plus each script's `demo` (see
  `.github/workflows/check.yml`).


The rules every video follows, for every user: [plugins/ai-editor/PRINCIPLES.md](plugins/ai-editor/PRINCIPLES.md).
