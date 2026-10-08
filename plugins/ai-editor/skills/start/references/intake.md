# Intake questions

The questions start step 2 asks, grouped into at most four per call, and the command that saves each
answer. Ask only the ids `profile.py missing` printed. The first option of each is the one a beginner
can accept as is: list it first and mark it "(Recommended)". Free text ("Other") is always allowed.

The ids are `profile.py`'s two lists: the video questions (`audience`, `names`), asked by start for
every video, and the style questions, asked once at the end of setup (start asks them only when setup
was skipped). Keep these calls and their order.

**This video (start, every video)**

| id | question | options |
|---|---|---|
| `audience` | Who is it for, and what should they do after watching? | free text, one line each. Default: "people curious about the topic" and "follow". Saves `audience` and `goal` in one `set` |
| `names` | Which products, tools, websites or people will you name? | free text, comma separated (add a website for anything not famous). These get their real logos and real page captures |

**Style call 1: what to copy (setup)**

| id | question | options |
|---|---|---|
| `platform` | Where will this be posted? | TikTok, Reels or Shorts (vertical 9:16) / YouTube (wide 16:9) |
| `creators` | Which creators' videos do you want yours to look like? Give 1-3 handles or links. | the creator they named in their message / I'll paste handles / no one: a clean editorial look |
| `creators` (take) | What should we take from each? (multi-select, per creator when there are several) | everything / captions / pace and zooms / visuals and colours |
| `liked_videos` | Any specific videos you love the edit of? Paste 1-5 links (any creator). | skip / I'll paste links |

**Style call 2: what makes it yours (setup)**

| id | question | options |
|---|---|---|
| `brand` | Colours and fonts for the graphics? | use the creator's look (no creator: the clean editorial look) / my brand colours (paste hex codes) and font / a logo file too (give the path) |
| `assets_dir` | Do you have your own photos, screenshots or b-roll for this? | no, find real screenshots and logos / yes, this folder: (path) |
| `avoid` | Anything you never want on screen? (multi-select) | emoji, stock photos, generic icons (all three on by default) / a colour (hex) / other (free text) |
| `captions` | Captions? | like the creator (no creator: "clean, 3 words at a time", saved the same way) / bold, a few words at a time / karaoke, the line fills as you speak / minimal / no captions |

**Style call 3: sound and layout (setup)**

| id | question | options |
|---|---|---|
| `sound` | Sound effects and music? | subtle sound effects, no music / no sound effects / sound effects and I'll add music myself |
| `behind` | Let graphics sit behind you? (screenshots and logos tuck behind your head and shoulders) | Yes / No, keep them beside and above me |

Save each call's answers as soon as they come in, all in one command (values are JSON), for example
`python3 "$P" set 'audience="developers who use Claude"' 'goal="follow"' 'names=[{"name": "Jev", "domain": "typesafe.ai"}]'`.
Every argument is `key=value`; the `key value` form below takes one answer alone:

```bash
python3 "$P" set platform '"tiktok"'                      # tiktok | reels | shorts | youtube (sets aspect)
python3 "$P" set creators '[{"handle": "somecreator", "take": ["captions", "pace", "visuals"]}]'
python3 "$P" set liked_videos '["https://www.tiktok.com/@someone/video/123"]'
python3 "$P" set audience '"developers who use Claude"'
python3 "$P" set goal '"follow, then comment router for the guide"'   # saved with audience
python3 "$P" set brand '{"use_creator": true}'           # or {"colors": ["#F2EEE6", "#E5482C"], "font": "Archivo", "logo": "/path/logo.svg"}
python3 "$P" set assets_dir '"/Users/me/Pictures/screens"'
python3 "$P" set names '[{"name": "Jev", "domain": "typesafe.ai"}, {"name": "Claude", "domain": "claude.com"}]'
python3 "$P" set avoid '{"emoji": true, "stock": true, "icons": true, "colors": ["#7B61FF"]}'
python3 "$P" set captions '{"on": true, "style": "creator"}'   # creator | bold | karaoke | minimal; "on": false for none
python3 "$P" set sound '{"sfx": true, "music": false}'
python3 "$P" set behind true                              # false: cards stay beside and above, no cutout step
```

If the user says "just edit it" or "use the defaults", save nothing and go on: every answer has a
default (vertical, no creator unless named, the editorial look, emoji, stock and icons avoided,
the creator's captions, subtle sound).
