---
name: setup
description: Installs and checks everything the AI video editor needs on Mac, Windows or Linux (Python, ffmpeg, Node, git, the Python packages, the free transcription model and the Remotion renderer), one step at a time with a check after each. Use when the user says "set up the editor", "install ai-editor", "setup", "get started", when they have just installed the plugin, or when any other ai-editor or creator-teardown step fails because a tool is missing. Also covers the optional ElevenLabs key, the optional GitHub CLI for free GitHub Actions renders and the optional AWS Lambda setup for cloud renders.
---

# Setup

The user may never have used a terminal. Go one step at a time. Before each install, say in one
sentence what the tool is for. Run the command once they say yes. Check after every step.

Run `setup.py` with `python3` on Mac and Linux, `py` on Windows.

## 1. Doctor

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" doctor
```

Every line reads `ok` or `FIX` with the exact command for this computer. `Ready.` at the end means
done: skip to step 5.

If `python3` itself is missing:
- Mac: `brew install python`. No Homebrew? See step 2.
- Windows: `winget install -e --id Python.Python.3.12`, then open a new terminal.
- Linux: `sudo apt install -y python3 python3-venv`.

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

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" venv
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" model
```

`venv` installs faster-whisper (free transcription on this computer), numpy, pillow and yt-dlp
into `~/.ai-video-editor/venv`. `model` downloads the transcription model once, about 500 MB.

## 4. The renderer

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" remotion
```

Copies the renderer to `~/.ai-video-editor/remotion` and installs it (about 700 MB, a few
minutes). This is the biggest download. If the user wants to start a creator teardown while it
runs, run it in the background and carry on: the teardown does not need it.

Remotion is free for individuals and companies of up to 3 people. Bigger companies need a
Remotion company licence (remotion.dev/license). Say this once.

## 5. Check

Run doctor again until it prints `Ready.` Then offer a first step: "Paste a creator you like, for
example @handle on TikTok, and I'll break down their style."

## Optional: the ElevenLabs key (better cuts)

The free Whisper model tidies speech: it drops some "um"s and false starts. The cut uses those to
find retakes. ElevenLabs Scribe keeps every one. The free ElevenLabs plan includes a few hours of
transcription a month.

**Never ask for the key in the chat.** Anything pasted here stays in the conversation.

1. Sign up at elevenlabs.io.
2. **Developers** in the left sidebar, then **API Keys**, then create a key.
3. Keep **Restrict Key** on and allow **Speech to Text** only. Set a credit limit.
4. In a terminal window (not this chat), run the creator-teardown `setkey` command:
   `python3 <creator-teardown skill folder>/scripts/fetch.py setkey`. It asks for the key and
   hides what they type. On a Mac, after copying the key: `pbpaste | python3 .../fetch.py setkey`.

Both plugins read the key from `~/.config/creator-teardown/.env`.

## Optional: the GitHub CLI (free cloud renders)

Only when the user picks GitHub Actions at render time. Doctor shows `gh` as optional.

1. Install it: Mac `brew install gh`, Windows `winget install --id GitHub.CLI` (then a new
   terminal), Linux: follow github.com/cli/cli/blob/trunk/docs/install_linux.md.
2. A free GitHub account (github.com/signup).
3. In their own terminal, not this chat: `gh auth login --web`. Pick GitHub.com and HTTPS, and say
   yes to logging in git with it. It opens the browser.

The footage goes in a private repo in their account. Only they can see it.

## Optional: rendering in the cloud (AWS Lambda)

Only when the user picks Lambda at render time, or asks. It renders on many machines at once, so a
long video takes minutes instead of an hour. It costs money on their own AWS account. The
style-edit skill quotes the cost before every render.

Follow `references/lambda.md`.
