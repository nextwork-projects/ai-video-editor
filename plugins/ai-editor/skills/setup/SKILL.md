---
name: setup
description: Installs and checks everything the AI video editor needs on Mac, Windows or Linux (Python, ffmpeg, Node, git, the Python packages, the free transcription model and the Remotion renderer), one step at a time with a check after each. Use when the user says "set up the editor", "install ai-editor", "setup", "get started", when they have just installed the plugin, or when any other ai-editor or creator-teardown step fails because a tool is missing. Also walks the user through the API keys (TypeSafe for cheaper cuts, Gemini for reading a creator's look, ElevenLabs optional), the optional CrisperWhisper model, cloud renders on Modal (offered: $30 free credit a month), the optional GitHub CLI for free GitHub Actions renders and the optional AWS Lambda setup. Also when the user says "set up Modal", "cloud renders", "finish setup", "add my TypeSafe/Gemini/ElevenLabs key", or wants to do a skipped step.
license: MIT
compatibility: Claude Code or any agent with a shell, on Mac, Windows or Linux. Installs Python 3.9+, ffmpeg, Node 20+, git and the Remotion renderer; needs internet. Runs from the full ai-editor plugin folder.
---

# Setup

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the default first). Only in an agent without that tool, ask numbered questions in text.

The user may never have used a terminal. Go one step at a time. Before each install, say in one
sentence what the tool is for. Run the command once they say yes. Check after every step.

## 0. Say the plan first

Before running anything, tell the user in plain words what setup does and why, as this list
(fill the times from doctor once it has run):

1. **Tools** (2-10 min, free): the programs that cut and draw the video. Required.
2. **Keys** (about 5 min, free or under a cent a video): three accounts that make every edit
   cheaper. Each is optional; skipping one means Claude does that job and uses more of your usage.
3. **Cloud renders** (optional, 3 min): finish long videos faster on Modal.
4. **Your style** (2 min): the creators and videos you like, so edits look like what you want.

Every step can be skipped and finished later: on a skip, run
`python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" later <step>` (`typesafe`, `gemini`, `elevenlabs`,
`modal`, `style`, `matte`) and say "Saved. Say *finish setup* any time to add it." When the user says
"finish setup" (or "add my <x> key"), run `setup.py todo` and go straight to those steps only.

Then work through them with a header on every step, e.g. **Step 2 of 4, keys: TypeSafe (1 of 3)**.
For each step say: what it is, why it helps them, what it costs, and what skipping it means. One
short line each. Never jump into a step without that line.

If a script prints an error, read its message to the user in plain words and ask again. Do not
open, grep or debug the setup scripts: their messages already say what to do.

Run `setup.py` with `python3` on Mac and Linux, `py` on Windows.

## 1. Doctor

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" doctor
```

Every line reads `ok` or `FIX` with the exact command for this computer. `Ready.` at the end means
done: skip to step 5 (keys).

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

## 5. API keys

Three keys, one at a time. Each one is optional: if the user says no, the editor still works and
Claude does that job instead (it just uses more of their Claude usage). Recommend the first two.
For each key, say in plain words what it is for and what it costs (the lines below), walk the
click path, save it, then check it.

**Never ask for a key in the chat.** Anything pasted here stays in the conversation. The key goes
from the clipboard straight into the key file:

The direct links (give them as clickable links and open them too):
- TypeSafe: https://console.typesafe.ai/keys
- Gemini: https://aistudio.google.com/apikey
- ElevenLabs: https://elevenlabs.io/app/settings/api-keys (sign up first at https://elevenlabs.io/app/sign-up)
- Modal: https://modal.com/signup

For each key: open the sign-up page for them (`open <url>` on Mac, `start <url>` on Windows,
`xdg-open <url>` on Linux), list the clicks, say what the key looks like (a long line of letters and
numbers), then ask in the question box: "Copied (I save it from your clipboard)" / "Skip". Tell
them to copy only the key, nothing else, right before they pick Copied.

- **Mac:** on "Copied" you run
  `pbpaste | python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" setkey <name>`.
- **Windows:** the user copies the key and says "copied". You run
  `powershell -NoProfile -Command Get-Clipboard | py "${CLAUDE_SKILL_DIR}/scripts/setup.py" setkey <name>`.
- **Linux, or if that fails:** the user opens a terminal themselves (Ctrl+Alt+T on most Linux,
  Terminal from Spotlight on a Mac, PowerShell from the Start menu on Windows). Give them
  `python3 "<full path>/setup.py" setkey <name>` to paste in; they paste the key when it asks (it
  stays hidden).

`setkey` sends one free test request before saving. `Tested: the <name> key works.` means done.
`Not saved: the service rejected this key` means they copied it wrong or only part of it: ask them
to copy it again. It never prints the key. Keys live in `~/.config/creator-teardown/.env`, readable
by the user only and shared with creator-teardown.

### TypeSafe (recommended): decides the cut

- **What for:** finding retakes and false starts. Without it Claude reads the whole transcript and
  decides every cut itself, which uses several times more of the user's Claude usage per video.
- **Cost:** pay as you go, $0.042 per million tokens (pieces of words) it reads. A 3-minute video
  is about 5,000 tokens, well under one cent.
- **Get it:** https://console.typesafe.ai/keys : sign up or log in, create a key, copy it.
- **Save:** `setkey typesafe`.

### Gemini (recommended): reads a creator's look

- **What for:** creator-teardown sends a few frames of each video to Google's Gemini to name the
  font, colours and graphics style. Without it the teardown shows Claude one picture per video
  instead, which uses more Claude usage.
- **Cost:** free. Google AI Studio's free tier needs no card. It has a daily limit that a teardown
  stays inside.
- **Get it:** https://aistudio.google.com/apikey : sign in with a Google account, click
  **Create API key** (pick or create a project if it asks), copy the key.
- **Save:** `setkey gemini`.

### ElevenLabs (optional): better transcripts

- **What for:** the free transcription on this computer tidies speech and drops some "um"s and
  false starts. ElevenLabs Scribe keeps every one, and the cut uses them to find retakes.
- **Cost:** the free ElevenLabs plan includes a few hours of transcription a month.
- **Get it:** https://elevenlabs.io/app/settings/api-keys (sign up first if asked), create a key. Keep **Restrict Key** on, allow **Speech to Text** only, and set a credit limit.
- **Save:** `setkey elevenlabs`.

Check them all at the end:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" keys
```

### Optional: CrisperWhisper (free verbatim transcripts, no key)

Only offer it to a user without an ElevenLabs key who wants better cuts. It runs on this computer,
keeps every "um", repeat and false start like Scribe does, and costs nothing per video. It is about
a 1 GB download and needs Python 3.10 or newer. **Its model weights are licensed for
non-commercial use only**: say this before installing, and skip it for anyone making videos for a
business or paid work.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" crisper
```

Once installed, the cut uses it automatically when there is no ElevenLabs key.

## 5b. Cloud renders with Modal (offer it)

Offer it once, in the question box: "Set up cloud renders with Modal? (about 5 minutes)" with
**Later** first and **Set it up now** second. Also run it when the user picks Modal at render time
and doctor shows `modal` as not ready. Say these three things first:

- **What it is:** Modal (modal.com) rents computers by the second. The video is split into pieces,
  each piece renders on its own machine at the same time, and the finished video comes back here.
  The laptop stays free while it runs.
- **What it costs:** Modal's pricing page says the free Starter plan includes **$30 of free credit
  a month**. A 60-second video costs about **$0.02** and a 10-minute video about **$0.17**, so the
  credit covers well over a hundred long videos a month. These are estimates from Modal's rates;
  the first real render measures the speed and every quote after uses it.
- **The card:** a third-party listing says Modal gives $1 of credit at sign-up and the rest once a
  card is added. Say that, and that the sign-up page shows the current terms.

Then, one step at a time, checking each:

1. **Account.** Open modal.com, click **Sign up**, sign in with GitHub or Google. Check: they see
   the Modal dashboard.
2. **Install Modal into the editor's Python.**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" modal
   ```

   Check: it prints `Modal installed.`
3. **Log in this computer.** Run the command it printed (Mac and Linux:
   `~/.ai-video-editor/venv/bin/modal token new`, Windows:
   `%USERPROFILE%\.ai-video-editor\venv\Scripts\modal.exe token new`). It opens the browser: they
   approve the new token on the Modal page. If no browser opens, give them the link it printed.
   Run it in the background and wait for it to finish. Check: it says the token was verified and
   saved.
4. **Prove it works.**

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" modal-check
   ```

   The first run takes a few minutes: it builds the render machine in their Modal account (Node,
   the renderer, Chrome) and caches it, so later renders start in seconds. Check:
   `Tested: Modal works.`

Doctor shows `ok modal` once it is logged in. The style-edit skill quotes the time and cost before
every Modal render.

## 6. Check

Run doctor again until it prints `Ready.` Skipped keys show as `--`; that is fine.

## 7. Your style (asked once)

The last part of setup is about taste, not tools. Ask what is still missing:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/profile.py" missing --style
```

Ask those ids in the question box, at most four per call, using the wording, options and
`set` commands in `${CLAUDE_PLUGIN_ROOT}/skills/start/SKILL.md` section 2 (Calls 1-3, the rows
that are not per video). Two calls usually cover it: first platform, creators, what to take from
each, and the specific videos they love (links); then brand, own photos folder, what to avoid,
captions, sound and "Let graphics sit behind you?". Every question has a recommended first option a beginner can accept.

On **Yes** to graphics behind you, download the matting model now (15 MB, once), so the first edit
does not stop for it:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/setup.py" matte
```

Check: it prints `Tested: cutting the speaker out works.` On **No**, skip it: the cutout step never runs.

Then offer, in one question box, to study those creators now so the first edit is quick:
"Break down @handle's style now? (about a minute per creator)" with yes first. On yes, run the
creator-teardown skill for each creator and each liked video link. On no, start does it later.
End with: "Ready. Drop a video and say edit my video."

## Optional: the GitHub CLI (free cloud renders)

Only when the user picks **Other: GitHub Actions** at render time. Doctor shows `gh` as optional.

1. Install it: Mac `brew install gh`, Windows `winget install --id GitHub.CLI` (then a new
   terminal), Linux: follow github.com/cli/cli/blob/trunk/docs/install_linux.md.
2. A free GitHub account (github.com/signup).
3. In their own terminal, not this chat: `gh auth login --web`. Pick GitHub.com and HTTPS, and say
   yes to logging in git with it. It opens the browser.

The footage goes in a private repo in their account. Only they can see it.

## Optional: rendering in the cloud (AWS Lambda)

Only when the user picks **Other: AWS Lambda** at render time, or asks. It renders on many machines at once, so a
long video takes minutes instead of an hour. It costs money on their own AWS account. The
style-edit skill quotes the cost before every render.

Follow `references/lambda.md`.
