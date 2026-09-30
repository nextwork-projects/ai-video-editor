# AI Video Editor

Edit your own talking-head video in the style of a creator you like.

Give Claude Code a creator. It measures how they edit: how fast they cut, how often they zoom, what
their captions look like. Then it cuts your video (retakes and pauses out) and renders it in that
style, on your laptop or in the cloud.

Built by [NextWork](https://nextwork.ai). Free and open source (MIT).

<!-- demo video: before / after goes here -->

## What you get

Two Claude Code plugins, installed together:

| Plugin | What it does |
|---|---|
| `creator-teardown` | Breaks down a creator's top TikTok or YouTube Shorts videos: views, word-level transcripts, pace, cuts per 10 seconds, zooms and caption style. Writes `teardown.md` and `style.json`. |
| `ai-editor` | `setup` installs everything. `cut` removes retakes, false starts and dead air from your video. `style-edit` renders it in the creator's style. `taste` remembers every correction you give. |

What `style-edit` adds on its own, each timed to the word you say:

- Captions in the creator's look, and zoom punches at the creator's rate.
- A logo when you name a brand, and a real screenshot when you name a website, scrolled to the
  sentence and highlighted.
- Animated scenes built from logos and icons: a flow (this goes into that), a race (how much
  faster), a pile (thousands of emails sorted).
- Sound effects, generated on your computer and levelled under your voice.
- Two layouts: **overlay** (you full frame, visuals above your head) or **split** (the visual on
  top, you underneath).

Nothing lands on your face or under the app's buttons, and an automatic check measures every edit
for that before you see it.

## Install

You need [Claude Code](https://claude.com/claude-code). Then, inside Claude Code:

```
/plugin marketplace add nextwork-projects/ai-video-editor
/plugin install ai-editor@nextwork
```

`creator-teardown` installs with it. Then say **"set up the editor"**. Claude checks your computer
and installs what is missing (Python, ffmpeg, Node, the transcription model and the renderer),
asking before each step. Works on Mac, Windows and Linux.

The full install is about 1.5 GB, most of it the renderer.

## Use it

Start Claude Code in an empty folder, then:

1. **"Break down @creator on TikTok"** (or paste a few video links).
2. **"Edit my video like @creator"** and give the path to your video (an mp4 or mov of you talking
   to camera).
   No video of your own yet? Practise on the sample take (a raw take with retakes and
   pauses left in): say **"use the sample video"**, or download it yourself:
   `curl -L -o sample-take.mp4 https://github.com/nextwork-projects/ai-video-editor/releases/download/sample-video/sample-take.mp4`
3. Claude shows you the cut: your transcript with the removed parts struck through. Approve it, or
   say which lines to keep.
4. Claude asks overlay or split, then shows stills of the styled edit. Approve them, or say what
   to change.
5. Pick where to render. Claude estimates both first:
   - **Your laptop** (free, default).
   - **AWS Lambda** (fast, costs a little on your own AWS account). See
     [Render in the cloud](#render-in-the-cloud).

6. Tell Claude what you'd change ("captions too small", "fewer zooms"). It saves that to your
   taste in `~/.ai-video-editor/taste.md` and uses it on every video after.

Everything lands in the folder you started in: `creator-teardowns/<handle>/` and `edits/<name>/`.

## Costs

| Part | Cost |
|---|---|
| Transcription (default) | Free. Whisper runs on your computer. |
| Transcription (optional) | ElevenLabs Scribe keeps every "um" and false start, so cuts are better. The free ElevenLabs plan covers a few hours a month. |
| Render on your laptop | Free. |
| Render on AWS Lambda | Pay-as-you-go on your own AWS account. Claude quotes it before each render. |

Remotion, the renderer, is free for individuals and companies of up to 3 people. Larger companies
need a [Remotion company licence](https://www.remotion.dev/license).

## Render in the cloud

If your laptop is slow or the video is long, render on AWS Lambda instead. Your video is split
across many machines and comes back in minutes.

You need an AWS account with a card on it. Say **"set up Lambda rendering"** and Claude walks you
through creating the access key, deploying the renderer to your account once, and checking it
works. After that, pick **Lambda** when Claude asks where to render.

## Troubleshooting

Say **"run the editor doctor"**. Every line reads `ok`, or `FIX` with the exact command for your
computer.

## License

MIT. See [LICENSE](LICENSE).

Assets fetched while editing: brand logos from [Simple Icons](https://simpleicons.org) (CC0), icons
from [Lucide](https://lucide.dev) ([ISC licence](https://lucide.dev/license)).
