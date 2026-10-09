---
name: setup
description: Installs and checks everything the AI video editor needs on Mac, Windows or Linux (Python, ffmpeg, Node, git, the Python packages, the free transcription model and the Remotion renderer), one step at a time with a check after each, then saves the user's style once (platform, creators, brand). Also walks through the optional API keys (TypeSafe for cheaper cuts, Gemini for reading a creator's look, ElevenLabs for verbatim transcripts), the optional CrisperWhisper model, cloud renders on Modal ($30 free credit a month), the GitHub CLI for free GitHub Actions renders and AWS Lambda. Use when the user says "set up the editor", "install ai-editor", "setup", "finish setup", "set up Modal", "cloud renders", "add my TypeSafe key", "add my Gemini key", "add my ElevenLabs key", when they have just installed the plugin, or when another ai-editor or creator-teardown step fails because a tool is missing. Not for editing a video (that is start) and not for changing one edit preference (that is taste).
license: MIT
compatibility: Claude Code or any agent with a shell, on Mac, Windows or Linux. Installs Python 3.10+, ffmpeg 4.4+, Node 20+, git and the Remotion renderer; needs internet. Runs from the full ai-editor plugin folder.
---

# Setup

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

The user may never have used a terminal. Go one step at a time. Before each install, say in one
sentence what the tool is for. Run the command once they say yes. Check after every step.

`U="${CLAUDE_SKILL_DIR}/scripts/setup.py"`. Run it with `python3` on Mac and Linux, `py` on Windows.

## 0. Say the plan first

Before running anything, tell the user in plain words what setup does and why, as this list
(the times are typical; say them as given):

1. **Tools** (2-10 min, free): the programs that cut and draw the video. Required.
2. **Keys** (about 5 min, free or under a cent a video): three accounts that make every edit
   cheaper. Each is optional; skipping one means Claude does that job and uses more of your usage.
3. **Cloud renders** (optional, 3 min): finish long videos faster on Modal.
4. **Your style** (2 min): the creators and videos you like, so edits look like what you want.

Then ask in the question box: **Start with the tools (Recommended)** / **Only add a key** / **Later**.

Every step can be skipped and finished later: on a skip, run `python3 "$U" later <step>`
(`typesafe`, `gemini`, `elevenlabs`, `modal`, `style`, `matte`) and say "Saved. Say *finish setup*
any time to add it." When the user says "finish setup" (or "add my <x> key"), run
`python3 "$U" todo` and go straight to the steps it lists (every optional step not done yet).

Work through them with a header on every step, e.g. **Step 2 of 4, keys: TypeSafe (1 of 3)**. For
each step say what it is, why it helps them, what it costs, and what skipping it means. One short
line each.

If a script prints an error, read its message to the user in plain words and ask again. Do not
open, grep or debug the setup scripts: their messages already say what to do.

## 1. Doctor

```bash
python3 "$U" doctor
```

Every line reads `ok` or `FIX` with the exact command for this computer. `Ready.` at the end means
the tools are done: skip to step 5 (keys). A `FIX ... run: setup.py repair` line means something
moved off the pinned versions (an update, or a package changed by hand): run `python3 "$U" repair`,
it puts back the exact pinned set. What is installed is recorded in `~/.ai-video-editor/env.json`.

A `saved login` row is a browser profile product-video logged in to a site with: it stays logged in
on this computer. Say which sites and how long ago each was used, and ask in the question box
"Delete these saved logins?" (Keep them (Recommended) / Delete <domain>, one option a site); on a
delete, `node "${CLAUDE_PLUGIN_ROOT}/skills/product-video/scripts/login.mjs" logout <domain>`.

If `python3` itself is missing:
- Mac: `brew install python`. No Homebrew? See step 2.
- Windows: `winget install -e --id Python.Python.3.12`, then open a new terminal.
- Linux: `sudo apt install -y python3 python3-venv` (Fedora: `sudo dnf install -y python3`; Arch:
  `sudo pacman -S --needed python`).

## 2. System tools (ffmpeg, Node, git)

Fix each `FIX` line top to bottom with the command doctor printed. What each one is for:
- **ffmpeg** cuts and joins video.
- **Node** runs the renderer that draws captions, zooms and cards.
- **git** is needed by the package installers.

The user runs these themselves, in their own terminal, because they ask for a password or open a
window:
- **Homebrew on a Mac** (if `brew` is missing). Give them
  `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
  and tell them to run the **Next steps** lines it prints at the end.
- Anything starting with `sudo`.
- `xcode-select --install` opens a window. Tell them to click **Install** and wait.

On Windows, a `winget` install only shows up in a **new** terminal. Ask them to close and reopen
Claude Code after installing, then run doctor again.

## 3. Python packages and the transcription model

Steps 3 and 4 are the steps of `setup.py bootstrap`, run one at a time so the user sees each.
Every step is safe to re-run: done work prints `up to date` and downloads nothing. Without the
user watching (CI, a re-install), `python3 "$U" bootstrap` runs all of them and ends with doctor.

```bash
python3 "$U" venv
python3 "$U" model
```

`venv` installs faster-whisper (free transcription on this computer), numpy, pillow and yt-dlp
into the venv in `~/.ai-video-editor` (`AI_EDITOR_HOME` moves it), at the exact versions in `requirements/requirements.lock` (11-33 s
on GitHub's clean runners). `model` downloads the transcription model once, about 500 MB, and checks its sha256.
`Python 3.10+ needed`: go back to step 1's Python line. `Run the venv step first.`: run `venv`.

## 4. The renderer

```bash
python3 "$U" remotion
```

Copies the renderer to `~/.ai-video-editor/remotion` and installs exactly its `package-lock.json`
with `npm ci` (about 700 MB; with Chrome's headless shell, 8-33 s on GitHub's clean runners). This is the biggest download: say so
first. If the user wants to start a creator teardown while it runs, run it in the background and
carry on: the teardown does not need it. `npm missing`: install Node (step 2) first.

Remotion is free for individuals and companies of up to 3 people. Bigger companies need a
Remotion company licence (remotion.dev/license). Say this once.

## 5. API keys

Three keys, one at a time, each optional. Recommend the first two. For each key, say what it is for
and what it costs (`references/keys.md` has both lines per key), walk the click path, save it, then
check it. If the user says no, the editor still works and Claude does that job instead.

The direct links (give them as clickable links and open them too):
- TypeSafe: https://console.typesafe.ai/keys
- Gemini: https://aistudio.google.com/apikey
- ElevenLabs: https://elevenlabs.io/app/settings/api-keys (sign up first at https://elevenlabs.io/app/sign-up)
- Modal: https://modal.com/signup

**Never ask for a key in the chat.** Anything pasted here stays in the conversation. The key goes
from the clipboard straight into the key file. For each key: open its page (`open <url>` on Mac,
`start <url>` on Windows, `xdg-open <url>` on Linux), list the clicks, say what the key looks like
(a long line of letters and numbers), then ask in the question box: **Copied (I save it from your
clipboard) (Recommended)** / **Skip**. Tell them to copy only the key right before they pick Copied.

- **Mac:** on "Copied" run `pbpaste | python3 "$U" setkey <name>`.
- **Windows:** run `powershell -NoProfile -Command Get-Clipboard | py "$U" setkey <name>`.
- **Linux, or if that fails:** the user opens a terminal themselves (Ctrl+Alt+T on most Linux,
  Terminal from Spotlight on a Mac, PowerShell from the Start menu on Windows). Give them
  `python3 "<full path>/setup.py" setkey <name>` to paste in; they paste the key when it asks (it
  stays hidden).

`<name>` is `typesafe`, `gemini` or `elevenlabs`. `setkey` sends one free test request before saving
and never prints the key:
- `Tested: the <name> key works.`: done.
- `Nothing saved: ...` (the clipboard held something else) or `Not saved: the service rejected this
  key`: they copied it wrong or only part of it; ask them to copy it again.

Keys live in `~/.config/creator-teardown/.env`, readable by the user only and shared with
creator-teardown (`$AI_EDITOR_HOME/.env` instead when `AI_EDITOR_HOME` is set). Check them all at the end:

```bash
python3 "$U" keys
```

Only to a user who skipped ElevenLabs and wants better cuts, offer CrisperWhisper
(`references/keys.md`, last section: non-commercial weights, 1 GB).

## 6. Cloud renders with Modal (offer it)

Offer it once, in the question box: "Set up cloud renders with Modal? (about 5 minutes)" with
**Later (Recommended)** first and **Set it up now** second. Also run it when the user picks Modal at
render time and doctor shows `modal` as not ready. Follow `references/cloud.md` "Modal": what it
is, what it costs, the card, then four checked steps.

## 7. Check

Run doctor again until it prints `Ready.` Skipped keys show as `--`; that is fine.

## 8. Your style (asked once)

The last part of setup is about taste, not tools. Ask what is still missing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" missing --style
```

Ask those ids in the question box, at most four per call, using the wording, options and `set`
commands in `${CLAUDE_PLUGIN_ROOT}/skills/start/references/intake.md` (the rows that are not
per video), in its three style calls: what to copy (platform, creators, what to take, liked videos),
what makes it yours (brand, own photos, avoid, captions), then sound, "Let graphics sit behind
you?" and "Have a raw take and the version you posted? I can learn how you cut." Every question has
a recommended first option. On yes to the last, run the taste skill's "Learn from a past edit".

On **Yes** to graphics behind you, download the matting model now (15 MB, once), so the first edit
does not stop for it:

```bash
python3 "$U" matte
```

Check: it prints `Tested: cutting the speaker out works.` On **No**, skip it: the cutout step never runs.

Then offer, in one question box, to study those creators now so the first edit is quick:
"Break down @handle's style now? (about a minute per creator)" with yes first. On yes, run the
creator-teardown skill in quick mode for each creator and each liked video link. On no, start does
it later. End with: "Ready. Drop a video and say edit my video."

## Optional: GitHub Actions and AWS Lambda renders

Only when the user picks **Other** at render time, or asks:
- **GitHub Actions** (free, a private repo in their account): `references/cloud.md` "The GitHub CLI".
- **AWS Lambda** (many machines at once, costs money on their own AWS account; style-edit quotes
  each render first): `references/lambda.md`.
