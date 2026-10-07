# Shapes

The files Claude writes in style-edit, and the rules plan.py holds them to. Read this before writing
visuals.json. More on each format and where it comes from: `visuals.md`; every file's full shape:
`contracts.md` (for people, not needed to run the skill).

## images.json (the user's own pictures, first on screen)

`[{"src": "images/dashboard.png", "word": "dashboard", "nth": 1}]`, optional `layout`, `hold_s`,
`entrance`, `box`. Transparent PNG and Lottie `.json` work.

## visuals.json

One beat per visual, in this order of preference: the user's own assets (images.json), the real
thing captured (`capture`, `post`, `app`, `youtube`, `github`), UI rebuilt from real parts (`chat`,
`terminal`, `toasts`), real logos (`logo`, `logo_cluster`, `flow`). Most sentences get nothing.

Every beat: `word` (as captions.json spells it), `nth`, `hold_s` so the card is still up on its last
word (omit it for the creator's measured hold), a `word` on each part that lands on its own word.
About one card every 4-6 s, never two at once, none in the first second unless it is the hook's subject.

| pick | beat |
|---|---|
| `capture:shot` | `{"kind": "capture", "url", "format": "shot", "clip"?, "marks": [{"kind": "highlight" or "ring", "find": "exact page text", "at_word"}], "props": {"label"?}}` |
| `capture:browser` | the same with `"format": "browser"` (`props.url` defaults to the beat's) |
| `capture:sticker` | `{"kind": "capture", "url", "format": "sticker", "marks": [{"kind": "highlight", "find": "the said words as the page writes them", "at_word"}]}`. No `crop`: capture.mjs cuts the sentence holding the first mark and sets it at a phone-readable size |
| `post` | `{"kind": "post", "url", "highlight": "the phrase said, as the post writes it"}` |
| `logo` | `{"kind": "logo", "brand", "domain"?}` |
| `logo_cluster` | `{"kind": "anim", "type": "logo_cluster", "props": {"logos": [{"logo", "domain"?, "word"?}]}}` |
| `chat` | `{"kind": "anim", "type": "chat", "props": {"app", "logo": {"logo"}, "model"?, "messages": [{"from": "user" or "app", "text", "word"}]}}` |
| `terminal` | `{"kind": "anim", "type": "terminal", "props": {"title"?, "lines": [{"text", "kind": "cmd" or "out", "word"?}]}}` |
| `toasts` | `{"kind": "anim", "type": "toasts", "props": {"items": [{"app", "logo": {"logo"}, "title", "body"?, "word"}]}}` |
| `side_by_side` | `{"kind": "anim", "type": "side_by_side", "props": {"a": {"src", "size", "crop"?, "label"?}, "b": {...}}}` (`src`: a capture's file) |
| `video_card` | `{"kind": "anim", "type": "video_card", "props": {"src", "start_s"?, "label"?}}` |
| `flow` | `{"kind": "anim", "type": "flow", "props": {"nodes": [{"logo", "label", "word"}], "split"?: [{"logo", "label" or "lines": [{"text", "word"}], "word"}], "tasks"?: [{"text", "word", "heavy"?}], "accent"?}}`: one beat for the whole explanation, `hold_s` to its last word |
| `app` | `{"kind": "app", "url" or "app_id", "brand"?}`: the App Store icon and first screenshot |
| `youtube` / `github` | `{"kind": "youtube", "url"}` / `{"kind": "github", "repo": "owner/name"}`: the thumbnail / the repo's social card |

Capture options: `clip` `[x, y, w, h]` in page px or `selector` (CSS); `width` (viewport, default
1000; 400-550 reflows docs to read on a phone); `highlight` (an exact sentence on the page, `hold_s`
3+); `page_text: true` to pick the sentence later with `route.py highlight`; `wait_ms`. Each mark adds
something the capture does not already show.

## Rules (plan.py enforces them and warns)

- Only the speaker's words and the product's real names. Never invent a figure, quote, like count or date.
- Pictures are `{"logo": "brand"}` or a file in `images/`. Never `{"icon": ...}` alone, never emoji.
- No type cards (a big number, heading, list or chart on a plain ground): they were removed. A stat
  is shown inside the real page that published it, marked as it is said.
- No stock photo sites, no purple-blue accent, no dark glass with neon, no Inter-style display face.
- Labels of a few words, `find` text copied exactly as the page writes it.
