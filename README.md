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
| `ai-editor` | `start` is the front door: it asks, then runs the rest. `setup` installs everything. `cut` removes retakes, false starts and dead air from your video. `style-edit` renders it in the creator's style. `taste` remembers every correction you give. `product-video` turns a website URL into a launch video made of its real UI. `clips` finds the best 3-5 short clips in a long video or podcast and edits each one. `improve` (for maintainers) turns the corrections users mark as helping everyone into rules, checks and tests in this repo. |

What `style-edit` adds on its own, each timed to the word you say:

- Captions in the creator's look, and zoom punches at the creator's rate.
- A logo when you name a brand, and a real screenshot when you name a website, scrolled to the
  sentence and highlighted.
- Animated scenes built from logos and icons: a flow (this goes into that), a race (how much
  faster), a pile (thousands of emails sorted).
- Sound effects, generated on your computer and levelled under your voice.
- Two layouts: **overlay** (you full frame, visuals above your head) or **split** (the visual on
  top, you underneath).

`product-video` needs no footage: paste a URL and it captures the site's real pages, its own colours,
fonts and logo, picks lines from the site's own copy, and renders two versions to pick from (an
Apple-style straight-on push with cursor clicks, and a Linear-style tilted plane), stills first.

Before it renders you can watch the edit in your browser and fix it by hand: move, trim, place,
swap or delete a visual, correct a caption word, set a sound's level.

Nothing lands on your face or under the app's buttons, and an automatic check measures every edit
for that before you see it.

## Install

You need [Claude Code](https://claude.com/claude-code). Then, inside Claude Code:

```
/plugin marketplace add nextwork-projects/ai-video-editor
/plugin install ai-editor@nextwork
```

`ai-editor` installs `creator-teardown` (this repo) with it. Optional, if you also want Claude to
write your own GSAP or HyperFrames animations outside the editor: add `greensock/gsap-skills` and
`heygen-com/hyperframes` as marketplaces and install their plugins. The editor does not need them.
Then say **"set up the editor"**. Claude checks your computer
and installs what is missing (Python, ffmpeg, Node, the transcription model and the renderer),
asking before each step. Works on Mac, Windows and Linux.

The full install is about 1.5 GB, most of it the renderer.

### Other agents (Codex, Cursor, Gemini CLI, Copilot)

```
npx skills add nextwork-projects/ai-video-editor
```

The skills follow the [Agent Skills](https://agentskills.io/specification) format. `AGENTS.md` (and
its copy `GEMINI.md`) tells any agent how to use them, and `.cursor-plugin/` and `.codex-plugin/`
point Cursor and Codex at the same skill folders. The ai-editor skills share `plugins/ai-editor/lib/`
and the renderer in `plugins/ai-editor/remotion/`: when an agent copies single skill folders,
clone the repo too and point it there.

## Use it

Start Claude Code in an empty folder, then:

Beginner path: install, say **"edit my video"**, answer the questions, approve the cut, approve
the stills. `start` asks a few questions once (platform, creators, brand, names to show, captions,
sound), saves them to `~/.ai-video-editor/profile.json`, then runs setup, creator-teardown, cut and
style-edit in order.

1. **"Edit my video"** (or **"edit my video like @creator"**) and give the path to your video (an
   mp4 or mov of you talking to camera).
   No video of your own yet? Practise on the sample take (a raw take with retakes and
   pauses left in): say **"use the sample video"**, or download it yourself:
   `curl -L -o sample-take.mp4 https://github.com/nextwork-projects/ai-video-editor/releases/download/sample-video/sample-take.mp4`
2. Answer the multiple-choice questions. The first option of each is fine to accept.
3. Claude shows you the cut: your transcript with the removed parts struck through. Approve it, or
   say which lines to keep.
4. Claude shows stills of the styled edit. Approve them, or say what to change.
5. Pick where to render. Claude times each option on your video first and shows the cost:
   - **Laptop** (free).
   - **Modal** (cloud, a few cents a video, $30 of free credit a month). See
     [Render on Modal](#render-on-modal).
   - **Other: GitHub Actions or AWS Lambda.** GitHub Actions is free, in a private repo (see
     [Render on GitHub](#render-on-github-actions)); Lambda runs on your own AWS account (see
     [Render on AWS Lambda](#render-on-aws-lambda)).

6. Tell Claude what you'd change ("captions too small", "fewer zooms"). It saves that to your
   taste in `~/.ai-video-editor/taste.md` and uses it on every video after.

7. Want to finish it by hand? Say "export to Final Cut" (or Premiere, Resolve, CapCut). The cut
   arrives as trims of your original take, with the captions, cards and sounds on their own tracks.

Single steps still work on their own: **"break down @creator"**, **"cut my video"**, **"style it"**.

Everything lands in the folder you started in: `creator-teardowns/<handle>/` and `edits/<name>/`.

## Costs

| Part | Cost |
|---|---|
| Transcription (default) | Free. Whisper runs on your computer. |
| Transcription (optional) | ElevenLabs Scribe keeps every "um" and false start, so cuts are better. The free ElevenLabs plan covers a few hours a month. |
| Render on your laptop | Free. |
| Render on Modal | About $0.02 for a 60-second video, $0.17 for a 10-minute one (estimates). The Starter plan includes $30 of free credit a month. |
| Render on GitHub Actions | Free: 2,000 minutes a month on private repos. |
| Render on AWS Lambda | Pay-as-you-go on your own AWS account. Claude quotes it before each render. |

Licences for the tools it uses are under [License](#license).

## Render on Modal

Modal (modal.com) rents computers by the second. Your video is split into pieces of about 90
seconds of work, each piece renders on its own machine at the same time, and the pieces join back
into one video on your laptop. Your laptop stays free while it runs.

Modal's pricing page says the Starter plan includes $30 of free credit a month. A 60-second video
costs about $0.02 and a 10-minute video about $0.17 (worked out from Modal's rates; your first
render measures the real speed, and every quote after uses it). Claude prints the time and cost for
each video before you choose, and the real cost after.

Say **"set up Modal"**: Claude walks you through the free account, installs Modal into the editor
and logs this computer in (it opens your browser once). The first check builds the render machine
in your account, which takes a few minutes once.

## Render on AWS Lambda

If your laptop is slow or the video is long, you can also render on AWS Lambda. Your video is split
across many machines and comes back in minutes.

You need an AWS account with a card on it. Say **"set up Lambda rendering"** and Claude walks you
through creating the access key, deploying the renderer to your account once, and checking it
works. After that, pick **Lambda** when Claude asks where to render.

## Render on GitHub Actions

Free, no card. The video is split into pieces of about 2 minutes, up to 20 GitHub machines render
them at once, and a last step joins them. A 44-second vertical video takes about 7 minutes; a
40-minute take about 20. Each machine-minute counts against the 2,000 free minutes a month that
private repos get, and Claude prints the count before you choose. You need a GitHub account and
the GitHub CLI (`gh`); say **"set up GitHub rendering"** and Claude installs it and logs you in.

Pick **GitHub Actions** when Claude asks where to render. Claude packs the renderer and your plan
into a **private** repo in your account, uploads the footage to that repo as a release file,
starts the render and downloads the finished video when it is done. Footage over 2 GB goes up in
parts. Claude asks before creating
the repo. The footage stays private to you.

## Troubleshooting

Say **"run the editor doctor"**. Every line reads `ok`, or `FIX` with the exact command for your
computer.

## License

This repo is MIT. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The tools it runs have their own licences:

| Tool | Licence | What it means for you |
|---|---|---|
| [Remotion](https://www.remotion.dev/license) (the renderer) | Remotion License | Free for individuals and for companies of up to 3 people. Bigger companies need a Remotion company licence. |
| [GSAP](https://gsap.com/community/standard-license/) (animation in the renderer, and the `gsap-skills` plugin) | GSAP Standard License | Free, commercial use included, every plugin too. Not an OSI open-source licence. It bans using GSAP in a no-code visual animation builder that competes with Webflow's. |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (the `hyperframes` plugin, and code ported from it) | Apache-2.0 | Free. Ported code keeps HeyGen's copyright, listed in [NOTICE](NOTICE). |

Assets fetched while editing: brand logos from [Simple Icons](https://simpleicons.org) (CC0), icons
from [Lucide](https://lucide.dev) ([ISC licence](https://lucide.dev/license)).


The rules every video follows, for every user: [plugins/ai-editor/PRINCIPLES.md](plugins/ai-editor/PRINCIPLES.md).
