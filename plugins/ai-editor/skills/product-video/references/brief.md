# Brief detail: music rights and logging in

Moved out of SKILL.md step 1. Read "Music" when the user picks a link or their own track, and
"Logging in" when they pick "Yes, log in now".

## Music

The options: generated here for this cut (Recommended: synthesised, nothing to licence) /
ElevenLabs Music with their key (offer only if `keys.get("elevenlabs")` finds one; their terms allow
online commercial use, not film or TV) / their own track (a file) / a YouTube link (or any link
yt-dlp reads: SoundCloud, Bandcamp) / none.

For a link: ask for an optional start and end time, then ask **who holds the rights**: "It's my own
track" / "YouTube Audio Library or Creative Commons (I'll credit it)" / "Licensed (Epidemic, Artlist
etc.)" / "Not sure". Then:

```bash
python3 "$S/product.py" music product/<name> --url '<link>' [--start 0:12 --end 0:52] --rights own|cc|licensed|unsure [--credit '<the credit line>']
```

Audio only, into `audio/track.wav`; the link's title, channel and licence field (YouTube shows
"Creative Commons Attribution license" there), the user's answer and the date go to
`audio/MUSIC-LICENSE.md`; a CC-BY credit line goes into `share.txt`. Use `--yt-cookies` (their
Chrome's YouTube login) only if YouTube blocks the download, and only after asking. On "Not sure",
say plainly that Instagram, TikTok and YouTube may mute or claim the video and offer the generated
score instead; then do what they choose.

For their own file, ask the same rights question, then
`python3 "$S/product.py" music product/<name> --file audio/<their track> --rights own|cc|licensed|unsure`.
`plan --music audio/<file>` refuses a track with no recorded rights. The download never leaves the
project folder. Plan with `--music audio/track.wav`: cuts snap to its detected beats.

## Logging in

Say this plainly first: the login is kept in a browser profile of its own,
`~/.ai-video-editor/browser/<domain>/`, on this computer only; it is outside every repo, never
uploaded (Modal, Lambda and GitHub renders only ever receive rendered captures), a demo or test
account is best, and `node "$S/login.mjs" logout <domain>` deletes it. Then:

```bash
node "$S/login.mjs" login <the site's login or home URL> [--check <a page that needs a login>]
```

A visible Chrome window opens on that profile (never their own Chrome profile, never their cookie
database). They log in by hand; you never see or type a password. When they close the window it
checks a page that needs the login and prints `logged in` or why not (a redirect to a login page, a
password field, a "Log in" button). If they say "done" without closing it, close only that window's
Chrome (the process whose `--user-data-dir` is that profile), then `node "$S/login.mjs" check <url>`.
From then on `record.mjs` uses that profile for that domain (installed Chrome, headless).

While recording a logged-in product:
- **Read-only.** `record.mjs` refuses to press create, delete, remove, pay, buy, upgrade, subscribe,
  billing, publish, invite, transfer, log out, unless the step carries `"allow": true`, which you add
  only after asking in the question box. Creating something (a project from a prompt) is a write:
  ask first, then do one, with an obviously test prompt (starting "TEST, safe to delete:"), and tell
  the user its name so they can delete it.
- **Personal data blurred** in the page before capture: email addresses, avatars, billing panels,
  email fields, and any names in `flows.json` `"blur": {"text": [...], "selectors": [...]}`. Each
  flow writes `flows/<id>-blurred.png` (what was blurred, outlined in red) and the list in
  `<id>.json` `blurred`. Show the user those sheets before rendering.
