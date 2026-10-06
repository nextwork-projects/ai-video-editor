# story.json

You write it, from `use-cases.md`, `product.py copy` and a look at the tiles and the flow strips. The plan turns it into timings and
camera moves; you never write times.

```json
{
  "purpose": "launch",
  "shots": [
    {"kind": "page", "focus": "hero", "vertical": {"kind": "flow", "flow": "home", "from": 0.3, "to": 3.6}},
    {"kind": "type", "text": "Learn anything by building"},
    {"kind": "flow", "flow": "browse", "from": 0.4, "to": 7.4, "text": "Browse real-world projects"},
    {"kind": "grid", "els": ["el-13", "el-14", "el-15", "el-16", "el-17", "el-18"]},
    {"kind": "keys", "flow": "search", "from": 2.2, "to": 9.2, "text": "Search NextWork"},
    {"kind": "push", "el": "el-14", "to": "flow:project@0.5"},
    {"kind": "flow", "flow": "project", "from": 0.5, "to": 6.3, "text": "What You'll Build"},
    {"kind": "end"}
  ],
  "share": {"caption": "Learn anything by building. Browse real-world projects or tell NextWork what you want to learn."}
}
```

## The shot library

Every shot is the site's real UI: its captures (`images/`), its recorded click-throughs (`flows/`) or its
own videos (`media/`). A screen reference is `tile-N`, `page-N`, `flow:<id>@<seconds>` (a frame of a
recording) or a path.

| kind | what it shows | fields |
|---|---|---|
| `flow` | cursor POV: a recorded click-through; the camera stays wide until the hand is about to act, pushes onto what it acts on 0.45 s early, and pulls out when nothing happens | `flow`, `from`, `to` (s in the recording) |
| `keys` | the keyboard moment: a flow with the pressed keys drawn as keycaps as the UI answers, the camera tight on the field | as `flow` |
| `page` | the real page; the camera travels to `focus` (tilted plane drift in the linear style) | `focus`: `"hero"`, an element id, or `[x, y, w, h]`; `click` (apple) |
| `lift` | an element lifts out of the page, which blurs behind it | `el` |
| `macro` | so close the page has depth of field; focus racks from `a` to `b` | `a`, `b`: element ids or rects |
| `stack` | three real screens in isometric, fanning apart | `screens`: 3 refs |
| `push` | the camera dives into a component until it becomes the next screen; start the next shot on that screen (a match cut) | `el` or `focus`, `to`: a ref |
| `split` | two flows side by side (stacked on 9:16) | `flows`: [{`flow`, `from`}, {`flow`, `from`}] |
| `orbit` | one component lifted and turning slowly in 3D, its shadow sliding the other way | `el` |
| `whip` | a motion-blurred whip pan from one screen to the next | `screens`: 2 refs |
| `grid` | the site's real components flying in to a grid | `els`: 4-6 ids |
| `type` | a few of the site's words typed in its own font, low left | `text` |
| `media` | a video the page itself plays | `src` |
| `end` | the site's logo and its domain on its own ground | none |

Every shot may carry `text` and `dur` (seconds; a flow's length is `to - from`). The plan snaps every
cut to the beat.

**The mix**: use case by use case, each as its `flow` or `keys` shot with the site's own words for it,
other kinds between them. Never the same kind twice in a row (plan refuses; `page` runs warn, for the
apple style's one continuous camera). A 30 s film uses at least 5 kinds. Vary the lengths: a flow runs
5-7 s, a whip or push 2 s, a type moment 2 s.

## Flows

`flows.json` holds the click-throughs; `record.mjs` plays them in headless Chrome and records the screen.
Steps: `{"wait": s}`, `{"click": target}`, `{"hover": target}`, `{"move": target}`, `{"type": target,
"text": "..."}` (clicks the field, then types at 9 characters a second), `{"key": "Enter" | "Meta+k" |
"ArrowDown"}`, `{"write": "..."}` (types into whatever has focus, after a shortcut), `{"scroll": px}`,
`{"goto": url}`. A target is `text=<words on the page>` or a CSS selector. `"hold": s` after any step;
`"navigates": true` on a click that loads a page.

- One flow per use case, 5-9 s, the site's own path: the menu a visitor opens, the tab, the search box.
- Public pages only, unless the user gave cookies. A click that opens a sign-up modal is a dead end on a
  logged-out site: look at the strip and cut before it (`to`), or pick another control.
- Record both sizes for a 9:16 film (`--mobile`). The phone take is the site's real phone layout; the
  plan swaps a flow to `<id>-m` on 9:16 when it exists.

## 9:16

Every frame is filled by the product. `check` fails a shot where UI (anything that is not flat ground
of the site's colour) covers under 75% of the frame; type and the end card are exempt. So on 9:16:
recordings use their phone take, page shots get a `"vertical"` override (a phone flow, a `macro`, `{"skip": true}`, a
`grid`, a `lift`), and a shrunken desktop page with ground above and below is never shown.

## Choosing shots

- **One shot about every 3-4 s**: 15 s = 4 shots + end, 30 s = 6-8 + end, 45 s = 9-11 + end. Apple's
  feature films hold 1.9-3.5 s a beat; under 2.2 s nothing reads.
- **Open on the hero** with no words: the page's own headline is in frame, and the camera pushes into
  it. Words that repeat a headline already on screen read twice.
- **Show the product, not the marketing.** Prefer the app screenshot, the demo panel, the real cards
  and lists over a section heading on an empty ground. A shot whose focus rect is mostly empty ground
  in the tile is a wasted shot.
- **Lift what a user would touch**: a card, a composer box, a pricing tier, a single row. Not a
  heading (it is text, it reads in place) and not anything wider than about 900 px (it will not fit
  bigger than it already is).
- **Focus rects**: a wide region (a row of cards) is framed from its top edge, so start the rect at the
  row's own heading. Keep a rect inside one section: a rect that cuts through a big headline shows
  half words at the frame edge.
- **The page's own video** (`media`) is the best shot there is when it exists: it is the product moving.
- Stop the story where the page stops being product (footer, legal, hiring).

## Words on screen

- **Only the site's words.** A phrase must be a run of the site's copy (any heading, line, button or
  title), case and spacing aside. `plan` refuses anything else. No invented stats, taglines,
  testimonials, or "now with". A number on screen is the site's own claim, shown where the site
  shows it.
- **At most 5 words** (7 refuses). Cut a long heading to its strongest run: "The product development
  system for teams and agents" -> "The product development system".
- **About 0.3 s a word once settled**; the plan stretches a shot that is too short to read it. Too
  many words for a shot means cut the words, never speed up.
- **Words on at most two thirds of the shots.** The UI carries the rest.
- No emoji, no slogans that are not on the page, no title case the page does not use.

## Purposes

- **Launch** (default, 30 s): the hero, then the 2-3 use cases the user picked, each as its recorded flow
  with the site's words for it and one library shot after it; end on the logo.
- **Feature demo** (30-45 s): one use case, one flow, cut into 2-3 shots (`flow`, `keys`, a `macro` on the
  result); the logged-in app (`--app`, cookies) when they gave one. Words name the step in the app's labels.
- **Ad** (15 s): the strongest single line on the first shot that shows the product, 3 more shots, end on
  the URL. No hero hold.

## Share copy

`share.caption`: one or two sentences, each a sentence from the site (`share` checks), no hashtags
added, no "excited to share". The alt text is written for you: what is shown, in order.

## Secrets

A logged-in app page can show real customer names, emails and data. Look at `images/app.png` before
using it; if it shows anyone's data, do not use that shot and tell the user why.
