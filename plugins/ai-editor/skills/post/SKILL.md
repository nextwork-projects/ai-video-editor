---
name: post
description: Posts a finished video to the user's own social accounts through their Zernio account (lib/ai_editor/post.py), now or at a set time. Any number of accounts per platform (two TikToks, a brand and a personal Instagram): the user picks which ones each time. Writes the caption from the video, shows it, and sends only after the user says yes, then hands back each live link. Also sets posting up: the Zernio key and connected accounts live in the editor's Settings, Auto-post your videos. Use when the user says "post it", "post this video", "post to TikTok", "post to Instagram", "upload it to YouTube", "schedule the post", "post it tomorrow at 9", "connect my accounts", "connect Zernio", "add another TikTok account", or approves a finished video and says yes to posting. Not for making or changing the video (start, style-edit, overlays).
license: MIT
compatibility: Python 3.9+ (stdlib only). A Zernio account with its API key saved in Settings, Auto-post your videos, and at least one account connected there.
---

# Post

Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md, and `${CLAUDE_PLUGIN_ROOT}` the plugin folder two levels above it.

Every question to the user goes in the question box: call the AskUserQuestion tool (2-4 options, the recommended one first). Only in an agent without that tool, ask numbered questions in text.

`P="${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/post.py"`. On Windows, use `py` wherever these commands say `python3`.

## 1. Accounts

```bash
python3 "$P" accounts
```

- **Exit 2 (no key):** posting is not set up. Open the home window on Settings
  (`python3 "${CLAUDE_PLUGIN_ROOT}/lib/ai_editor/home.py" serve`, then the Settings page) and say in one line:
  "Make a Zernio account (the link is on the Auto-post card in Settings), connect your apps there, then paste its API key on
  that card." Never ask for the key in the chat. Run `accounts` again when they say it is done.
- **No accounts:** the Auto-post card in Settings has a Connect button per app. Each press adds one account, so pressing TikTok
  twice adds two TikToks. In a terminal only: `python3 "$P" connect tiktok` prints the sign-in link to open.
- An account marked `"active": false` is signed out: its Sign in again button on the Auto-post card in Settings fixes it.

## 2. What to post

- **The video:** the approved render (`edits/<name>/render.mp4`, a clip's render, or a file the user names).
- **Accounts:** one AskUserQuestion with `multiSelect: true`, one option per account, labelled
  `@username (Platform)`. With more than 4 accounts, ask per platform. Never guess between two accounts on one
  platform. If the user already named them ("all of them", "just my TikTok"), use that and skip the question.
- **Caption:** write it from the video's own words (`edits/<name>/captions.json` or `words.json`): the hook line,
  one short line on what it shows, no hashtag wall. YouTube also needs a title (100 characters at most).
- **When:** now, unless the user gave a time. A time needs their time zone (`--tz America/Chicago`).

## 3. Confirm, then send

Show the caption, title, accounts and time in one AskUserQuestion: Post it / Change the caption / Not now. TikTok
requires the user to have seen the post before it goes out, so never send without this yes.

```bash
python3 "$P" send edits/<name>/render.mp4 --to <id>,<id> --caption "..." [--title "..."] [--at 2026-10-20T09:00 --tz America/Chicago] [--trial]
```

`--trial` posts an Instagram Trial Reel (only when the user asks for one). `send` uploads, posts, and waits until
every account is published or failed. A retry with the same video, accounts and caption never posts twice.

## 4. Hand back

One line per account: platform, @username, and the live link (or the time it is scheduled for). A failed account:
say its error in plain words and offer to retry just that one (`send` with only its id). Exit 1 is Zernio
refusing: give its message as it is.
