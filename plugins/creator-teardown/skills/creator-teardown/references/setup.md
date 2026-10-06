# Setup, done with Claude

Use when the user asks to install or set up creator-teardown, or when `doctor`
prints `Not ready`. The user may never have used a terminal. One step at a time,
plain words, and say what each tool is for before installing it.

## 1. Run doctor

```bash
python3 <skill>/scripts/fetch.py doctor
```

`<skill>` is this skill's folder. On Windows use `py` instead of `python3`.

If `python3` itself is missing, install Python first:
- Mac: `brew install python` if Homebrew exists. If it doesn't, see step 2.
- Windows: `winget install -e --id Python.Python.3.13`, then open a new terminal.
- Linux: `sudo apt install -y python3`.

## 2. Fix each line marked FIX

`doctor` prints the exact command for this computer. Say what it's for in one
sentence, then run it once the user says yes.

The user has to run these themselves, in a terminal window, because they ask for a
password or open a window:
- **Homebrew on a Mac.** Give them:
  `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
  and tell them to run the **Next steps** lines it prints at the end.
- Anything starting with `sudo`.
- Running `git` for the first time on a Mac opens an "install command line
  developer tools" window. Tell them to click **Install** and wait.

Lines marked `optional` can wait. Mention them only if the user wants frame
strips or edit plans.

## 3. The ElevenLabs key (optional)

Without a key, transcripts use Whisper on this computer, free. A key switches
them to ElevenLabs Scribe v2, which keeps every um and false start and makes the
voice profile better. Offer it once; skip it if the user says no.

**Never ask for the key in the chat.** Anything pasted here stays in the
conversation.

Walk them through it:
1. Sign up at elevenlabs.io. The free plan is fine: it includes 4 hours 30
   minutes of transcription.
2. **Developers** in the left sidebar, then the **API Keys** tab, then create a key.
3. Keep **Restrict Key** on and give it **Speech to Text** access only.
4. Copy the key.
5. In a terminal window (not this chat), run the `setkey` line doctor printed. It
   asks for the key and hides what they type. On a Mac, after copying the key,
   this works too: `pbpaste | python3 <skill>/scripts/fetch.py setkey`.

## 4. The Gemini key (optional, free)

It runs the look pass: Gemini Flash-Lite watches the creator's top videos and names
the font, graphics style and motion, so Claude never has to read frames. Without it,
a small model reads one frame sheet per video instead. Offer it once.

**Never ask for the key in the chat.**

1. Open https://aistudio.google.com/apikey and sign in with any Google account.
2. Click **Create API key**. Accept the terms if asked. If it asks for a project,
   let it create one. No card is needed: the free tier covers a teardown.
3. Copy the key (it starts with `AIza`).
4. In a terminal window (not this chat), run the `setkey --gemini` line doctor
   printed. It asks for the key and hides what they type. On a Mac, after copying:
   `pbpaste | python3 <skill>/scripts/fetch.py setkey --gemini`.
5. Tell them: on the free tier Google may use what is sent to improve its products.
   Only the creator's public videos are sent, silent and at 480 px.

## 5. The OCR engine (optional)

Doctor's OCR line installs the text reader that measures captions: `ocrmac` (Apple
Vision) on a Mac, `rapidocr` + `onnxruntime` on Windows and Linux. The first run of
RapidOCR fetches its models once.

## 6. Check

Run `doctor` again until it prints `Ready.` Then offer a first run:
"analyse @creatorhandle on tiktok".
