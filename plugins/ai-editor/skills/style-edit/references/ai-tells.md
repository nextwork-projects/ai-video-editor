# AI tells

What makes an edit read as AI-made, and what to do instead. `scripts/ai_tells.py` checks every pattern
marked **code** (the id in backticks is the `tell` it returns). The rest are for the LOOK pass on the stills.

- **BAN**: never by default. Only when the user's own brand kit or request names it.
- **WARN**: allowed when there is a reason. Say the reason in the plan note.

Run: `~/.ai-video-editor/venv/bin/python scripts/ai_tells.py edits/NAME --plan plan.json --stills stills`

Sources (numbered in the lists below):
1. Anthropic, frontend-design skill: https://github.com/anthropics/claude-code/blob/main/plugins/frontend-design/skills/frontend-design/SKILL.md
2. Capital and Compute, "How to fix AI slop in web design, tell by tell": https://capitalandcompute.net/blog/fix-ai-slop-design/
3. prg.sh, "Why your AI keeps building the same purple gradient website": https://prg.sh/ramblings/Why-Your-AI-Keeps-Building-the-Same-Purple-Gradient-Website
4. Impeccable, "The visible tells of AI design": https://www.impeccable.style/slop
5. Opus Clip, "The AI slop aesthetic: 12 tells": https://www.opus.pro/blog/ai-slop-aesthetic-12-tells
6. Wikipedia, "Signs of AI writing": https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
7. Nielsen Norman Group, "The AI sparkles icon problem": https://www.nngroup.com/articles/ai-sparkles-icon-problem/
8. Flitto DataLab, orange-and-teal bias in AI art: https://datalab.flitto.com/en/company/blog/?p=425
9. Submagic, auto video editor (auto emoji, auto B-roll, Magic Zoom): https://www.submagic.co/it/features/auto-video-editor
10. Submagic, "How to make Alex Hormozi captions": https://www.submagic.co/blog/how-to-make-alex-hormozi-captions
11. Know Your Meme, Vine boom: https://knowyourmeme.com/memes/vine-thud-boom-sound-effect
12. invideo, faceless channel format (AI images + Ken Burns + TTS + word-synced captions): https://info.invideo.io/whats-the-best-ai-to-create-a-faceless-youtube-channel-about
13. Pangram, "Signs of AI writing": https://www.pangram.com/signs-of-ai-writing
14. Owner rejections in this plugin (look.tsx comments, 2026-10): heading + grey subline + accent rule; beige, dark green and vermilion grounds; Archivo/Geist display; Lucide tiles on dark glass with neon; purple/blue gradients; emoji; text-only slides; "200x faster" stat cards.

---

## Colour

**`cream-paper-ground`** BAN, code
- Tell: cards on a warm cream/beige paper ground (#F4F1EA, #F2EEE6, #DFDCCE).
- Why: it is the Claude interface palette; the first thing a model reaches for after "make it less AI" [1][2][14].
- Detect: look ground hue 20-60, saturation 4-30%, value 78%+; still: one such colour over 50% of the card.
- Instead: no ground. The capture or the footage behind it, or white / the app's own surface.

**`flat-saturated-ground`** BAN, code
- Tell: one flat saturated colour (vermilion, forest green, cobalt) filling the card.
- Why: the poster preset with no subject behind it; rejected [14]. Impeccable "lazy cool/impact" [4].
- Detect: look ground saturation 45%+; still: one saturated colour over 60% of the card (`quality.ai_title_card`).
- Instead: the real thing on the footage, or the creator's measured palette.

**`neon-on-black`** BAN, code
- Tell: near-black panel lit by one acid-green, cyan, magenta or vermilion accent.
- Why: "near-black background with a single bright acid-green or vermilion accent" is a named AI default [1][2].
- Detect: look ground value < 16% with accent saturation 60%+, value 85%+; still: `quality.generic_pixels` (dark 45%+ plus one bright hue).
- Instead: a real dark UI only when the subject has one (terminal, the app). Otherwise white card, near-black ink.

**`purple-blue`** BAN, code
- Tell: indigo/violet accents, purple-to-blue gradients, gradient headline text.
- Why: Tailwind's `bg-indigo-500` default saturated the training data [3]; "purple gradients everywhere" [4][2].
- Detect: any colour with hue 225-295, saturation 40%+ in the look; any `gradient(` holding one; still: blue-purple over 30% of the card.
- Instead: colour comes from the real content: logos, captures, the creator's palette.

**`gradient-ground`** WARN, code
- Tell: a smooth two-colour gradient behind the card.
- Why: the "unchosen gradient" [2]; decoration with no subject.
- Detect: still: blur text away, fit a plane to Lab colour on a 16x9 grid; range over 20 and R2 over 0.9.
- Instead: flat neutral or the real capture. Gradients only when the brand has one.

**Orange-teal / yellow cast** WARN
- Tell: AI images and grades leaning orange-teal or sepia-yellow; "too green" grass, orange skin.
- Why: generators default to the teal-orange grade of their training films [8]; over-saturated synthetic colour [5].
- Detect: on image b-roll, mean a* and b* both high in shadows-to-highlights split (warm highlights, cyan shadows).
- Instead: real photos; keep the camera's own grade.

**Invented palette** WARN
- Tell: a palette nobody chose: brand-less accent picked by the model.
- Why: [1] says grounding in the subject is where distinctive colour comes from; owner rejected invented palettes [14].
- Detect: look colours that appear in neither style.json (creator measured) nor the user's brand kit.
- Instead: measured palette from the teardown, or neutral chrome with colour from the content.

## Type

**`default-grotesk-display`** BAN, code
- Tell: headings set in Inter, Geist, Archivo, Roboto, Poppins, Montserrat, Manrope, DM Sans and friends.
- Why: "Inter everywhere" is the most named web tell [3][4][2]; rejected for display [14].
- Detect: look `font_display` in the blocklist (`GROTESK` in ai_tells.py), resolved through look.tsx presets.
- Instead: a serif, or the creator's measured display face.

**`default-grotesk-body`** WARN, code
- Tell: the same faces on labels, kickers and captions.
- Why: as above; fine for small UI labels, a tell on anything read as a heading.
- Detect: look `font` or captions `font_match` in the blocklist. Captions measured from the creator are theirs: keep.
- Instead: the creator's face for captions; UI labels may stay grotesk.

**`one-accent-word`** WARN, code
- Tell: one word in a headline set in italic, bold or the accent colour (`*five cents*`).
- Why: "accenting just a single word or phrase in a headline" is a named tell [1][2].
- Detect: `*word*` markup in a type card's text.
- Instead: set the line plainly. Emphasis comes from landing on the spoken word.

**`eyebrow-label`** WARN, code
- Tell: small tracked-out label above the heading ("PEOPLE USE IT TO").
- Why: "tracked-out ALL-CAPS eyebrow label above every heading" [1][2].
- Detect: `kicker` / `eyebrow` / `overline` prop on a type card.
- Instead: drop it. One line in the speaker's words.

**`title-case`** WARN, code
- Tell: Title Case On Every Word Of A Heading.
- Why: title case for non-proper nouns is a listed LLM formatting tell [6].
- Detect: 3+ words over 3 letters, all capitalised, in a heading prop.
- Instead: sentence case or the speaker's own casing.

**Template chrome** WARN
- Tell: meta strings joined by middle dots ("A · B · C"), `WORD / fragment` labels, monospace small print, arrow links.
- Why: decoration regardless of subject [1][2].
- Detect: regex ` · .* · ` or `→` in card text.
- Instead: delete it.

**Numbered sequence on non-sequential content** WARN
- Tell: 01 / 02 / 03 on things that are not steps.
- Why: listed typographic tell [2].
- Detect: `^0\d` labels on cards whose items have no order in the transcript.
- Instead: no numbers unless the speaker counts.

## Layout and composition

**`heading-subline-rule`** BAN, code
- Tell: a big centred heading, a small grey line under it, a short accent bar.
- Why: the slide-template title card; rejected [14]; the "card kit" and "copy-paste layouts" [2][4].
- Detect: plan: a type card with `sub`/`subtitle`/`tagline`; still: `quality.ai_title_card` (centred band 15%+ tall, thin band under, solid bar under 50% width).
- Instead: one line in the speaker's words, or a real capture.

**`accent-rule`** WARN, code
- Tell: a short solid bar under the heading.
- Why: part of the same stack [14]; "decorative strokes" in template output.
- Detect: still: a band under the tallest text band, under 20% of its height, 75%+ filled, 3-50% of the width.
- Instead: remove it.

**`dead-centre`** WARN, code
- Tell: every block on the vertical centre line, equal space above and below.
- Why: "boringly centred hero" and "predictable layouts" [1][4]; [1] asks for asymmetry and grid-breaking.
- Detect: still: 2+ text bands, every band centre within 1.2% of the middle, top and bottom margins within 4%.
- Instead: align to an edge or to the subject (the head, the object being shown).

**Three cards in a row** WARN
- Tell: three rounded boxes, icon + heading + one sentence each.
- Why: the SaaS feature grid, the single most cited layout tell [3][2][4].
- Detect: a card with exactly 3 equal children each holding `icon` + `title` + `text`.
- Instead: one thing at a time, the real thing.

**Card kit** WARN
- Tell: everything in identical rounded cards, one radius, the same soft grey shadow; cards nested in cards.
- Why: "Cardocalypse" [4]; SaaS card kit [1][2]; "subtle shadows (exactly 0.1 opacity)" [3].
- Detect: look radius and shadow identical across every card type; a card whose props contain another boxed card.
- Instead: no container on captures (the capture is the object); vary weight by importance.

**Side-tab accent** WARN
- Tell: a thick coloured stripe down one side of a card.
- Why: called "the most recognizable tell of AI-generated UIs" [4].
- Detect: still: a solid column under 3% of card width, full card height, saturated, at the left edge.
- Instead: remove it.

**Bento grid** WARN
- Tell: a mosaic of mismatched rounded tiles.
- Why: listed slop layout [4].
- Detect: 4+ boxed children of different sizes in one card.
- Instead: one exhibit at a time.

**Floating badges and pills** WARN
- Tell: pill badges ("NEW", "AI-powered") and floating chips around the main object.
- Why: "pill badge" in the stock hero [2]; floating badges [4].
- Detect: short (1-3 word) labels with full-radius boxes, more than one per card.
- Instead: none.

## Icons and illustration

**`emoji`** BAN, code
- Tell: emoji in captions, cards or labels (🚀 ✨ 🤯 👇).
- Why: emoji as formatting is a listed tell [6]; auto-emoji captions are a one-tap preset [9]; rejected [14].
- Detect: Unicode emoji ranges in any text prop or caption chunk.
- Instead: the word, or the real logo.

**`slop-icon`** BAN (sparkles, wand, rocket, stars, bot) / WARN (zap, brain, bulb, trophy, target, gem, crown), code
- Tell: the sparkle for "AI", a rocket for "launch", a lightning bolt for "fast".
- Why: sparkles have no agreed meaning beyond "special" and read as "beta" [7].
- Detect: `icon` prop names.
- Instead: the real logo or product UI.

**`icon-only-card`** BAN, code
- Tell: a card whose only pictures are stock line icons (Lucide), often in tiles on dark glass.
- Why: "massive icons" [4]; three-icon feature grids [3]; rejected [14].
- Detect: `plan.icon_only(props)`: icons present, no logo / image / capture.
- Instead: a logo, a capture, the user's own image.

**`glass-panel`** BAN, code
- Tell: frosted glass panel, backdrop blur, glow borders.
- Why: "reflexive glass" [2]; "lazy cool" [4]; rejected [14].
- Detect: look `surface: glass`.
- Instead: a plain card with a real soft shadow, or no card.

**`glow-halo`** BAN, code
- Tell: neon glow or bloom round shapes and text.
- Why: "glowing elements without functional purpose" [4]; glow with no reason [2].
- Detect: still on a dark ground: share of the 3-14 px ring round bright cores that is a dimmer copy of the core, over 35%.
- Instead: crisp edges; depth from a real shadow.

**Isometric / 3D blob illustration** WARN
- Tell: generic 3D glossy shapes, isometric blocks, abstract blobs as filler.
- Why: decoration with no subject [1]; same elements across unrelated designs (template output).
- Detect: LOOK pass only.
- Instead: the real object.

## Motion and easing

**`same-entrance`** WARN, code
- Tell: every card enters the same way (all pop, all fade-up).
- Why: "the same fade-and-slide-up on every section" [2][1]; "motion on everything".
- Detect: 4+ cards, one distinct `entrance`.
- Instead: entrance by what the card is: a post slides, a capture lifts, a logo pops.

**`bounce-ease`** WARN, code
- Tell: overshoot/bounce/elastic on everything.
- Why: "bounce easing" [2]; "bouncing buttons, wiggling icons" [4].
- Detect: `back.out`, `elastic`, `bounce` in plan motion or card props.
- Instead: expo/quart out for entrances; one overshoot on one hero moment.

**Floating idle motion** WARN
- Tell: cards that bob, drift or pulse while held.
- Why: "floating badges", "lazy impact" [4].
- Detect: render: card outline oscillating with constant period while held (quality.py jitter series).
- Instead: land, then hold still; move when something new happens.

**Too-smooth camera** WARN
- Tell: virtual camera moves with zero micro-jitter, flight-simulator smooth.
- Why: "weirdly smooth motion" is an AI video tell [5].
- Detect: zoom keyframes with identical ease on every move.
- Instead: fewer moves; cut instead of glide.

**Ken Burns on stills** WARN
- Tell: slow pan-and-zoom over every still image.
- Why: the "classic faceless video format" of AI images + Ken Burns + TTS [12].
- Detect: image cards whose only motion is a scale ramp over the whole hold.
- Instead: a real clip, or a still that holds and gets marked.

## Transitions and pacing

**`same-transition`** WARN, code
- Tell: every scene uses the same designed transition (all match/iris, all whip).
- Why: template packs; motion on everything [2].
- Detect: 3+ scenes, one (in, out) pair.
- Instead: hard cuts for most; a designed transition for one or two moments.

**`zoom-every-line`** WARN, code
- Tell: a punch zoom on every sentence.
- Why: auto zoom is a one-click feature with AI-chosen placement [9]; Hormozi-style punchy zooms every 1-3 s [10].
- Detect: zooms over 15 a minute.
- Instead: the creator's measured rate; zoom on the lines that earn it.

**Auto B-roll on every noun** WARN
- Tell: a literal stock clip for each noun said ("money" = cash pile).
- Why: auto B-roll reads the transcript and inserts library clips [9].
- Detect: visuals.json beats whose `word` is a common noun and source is a stock library.
- Instead: show the named thing, or stay on the face.

## Captions

**`preset-captions`** WARN, code
- Tell: UPPERCASE, heavy stroke, yellow active word, pop-in, one word at a time.
- Why: the Hormozi preset is a one-tap template in every caption app [10].
- Detect: captions `case: upper` + yellow `highlight_color` + stroke or box.
- Instead: the creator's measured caption style (style.json).

**Auto-emoji in captions** BAN, code (`emoji`)
- Tell: an emoji popping beside keywords.
- Why: auto-emoji is a Submagic feature category [9].
- Detect: emoji in caption chunks.
- Instead: none.

**Keyword colour roulette** WARN
- Tell: random words in green/red/yellow by "sentiment".
- Why: auto-highlight of keywords is a preset [9].
- Detect: 3+ distinct highlight colours in captions.
- Instead: one highlight colour, or none.

## On-screen copy

**`slop-copy`** BAN, code
- Tell: Unlock, Supercharge, Game-changer, Level up, Seamless, Elevate, Revolutionize, Effortless, Harness, Empower, Leverage, Delve, Unleash, Skyrocket, Cutting-edge.
- Why: marketing verbs that name no product [2][3]; "delve", "tapestry", "testament" cluster in LLM text [6].
- Detect: `COPY_BAN` regex over every text prop we wrote (real posts and captures skipped).
- Instead: the speaker's words from the transcript; name the concrete thing.

**`slop-structure`** WARN, code
- Tell: "It's not just X, it's Y", "here's the thing", "the future of", "changes everything".
- Why: negative parallelism is one of the strongest AI tells [6][13].
- Detect: `COPY_WARN` regex.
- Instead: say the claim once, plainly.

**`multiplier-stat`** BAN, code
- Tell: a big "200x faster than Claude" counter.
- Why: invented metrics ("10,000% ROI") are filler copy [2]; rejected [14].
- Detect: an `x` suffix or `Nx` in a card with faster/cheaper/better/than.
- Instead: capture the page that published the number and highlight it.

**`big-number`** WARN, code
- Tell: any counter card standing alone.
- Why: same as above when the source is not on screen.
- Detect: `counter` type without a capture next to it.
- Instead: show where the number came from.

**Redundant labels** WARN
- Tell: a label that repeats what the picture already says ("Jev" under the Jev logo).
- Why: "redundant UX writing" [4]; "unnecessary typographic labels" [1].
- Detect: a `label` equal to the logo name or capture domain.
- Instead: drop it.

**Em dashes and triples** WARN
- Tell: em dashes in on-screen copy; lists padded to three.
- Why: em dashes appear far more often in AI text [13][6]; rule of three [6].
- Detect: U+2014 in any text prop; 3-item lists where the transcript names two.
- Instead: comma or period; list what was said.

## Imagery and b-roll

**`ai-image-broll`** BAN, code
- Tell: generated images as b-roll: plastic skin, gibberish text in signs, extra fingers, warping backgrounds, flat even light.
- Why: text turning to gibberish, hand morphs, flat uncanny lighting, background physics [5].
- Detect: url/src from a generator (midjourney, dall-e, lexica, civitai, ideogram, firefly, "ai-generated").
- Instead: real footage, real screenshots, real photos of the named thing.

**`stock-broll`** WARN, code
- Tell: generic stock (handshake, laptop typing, city timelapse).
- Why: auto B-roll pulls from stock libraries [9]; stock-photo heroes [2].
- Detect: url from a stock site (`plan.STOCK`).
- Instead: capture the named thing.

**`text-only-cards`** BAN, code / **`type-card`** WARN, code
- Tell: words on a plain ground instead of a picture; half the edit or more.
- Why: text-only slides were rejected [14]; [1] wants the subject's own material.
- Detect: `type` in `plan.TYPE_ONLY`; BAN when 50%+ of content cards.
- Instead: the real page with the line marked; type cards were removed from the product.

**Gibberish UI mockups** BAN
- Tell: invented dashboards with fake numbers and lorem-like rows.
- Why: AI renders text as shapes [5]; invented metrics [2].
- Detect: LOOK pass; a built UI card whose strings appear in neither the transcript nor a capture.
- Instead: the real product, captured.

## Sound

**`whoosh-every-card`** WARN, code
- Tell: a whoosh on every card in and out.
- Why: template sound packs; motion on everything [2].
- Detect: whoosh cues at least as many as content cards.
- Instead: sound on a few events; most cards land silent.

**`one-sfx-repeated`** WARN, code
- Tell: the same file on most cues.
- Detect: one file over half of 6+ cues.
- Instead: every cue a different file, quieter than the voice.

**`meme-sfx`** WARN, code
- Tell: Vine boom, bruh, airhorn, ka-ching, record scratch.
- Why: overused to the point of irony [11].
- Detect: sfx file names.
- Instead: none unless the creator uses them.

**TTS plateau / no breaths** BAN
- Tell: a voice with no breaths between clauses and one flat pitch level.
- Why: voice-clone breath patterns and the "TTS plateau" cadence [5].
- Detect: cut audio: no inhale gaps 0.15-0.4 s between clauses; pitch range per sentence under 2 semitones.
- Instead: the speaker's real voice, breaths kept.

**Stock music bed under everything** WARN
- Tell: an upbeat library track at constant level from first frame to last.
- Why: the faceless-channel template [12].
- Detect: music cue spanning 90%+ of the duration with no level change.
- Instead: music only where the creator uses it.

## Thumbnails and social graphics

**Shocked face + red arrow + red circle** WARN
- Tell: the stock high-CTR formula, often generated: glowing outlines, shocked face, red circle.
- Why: AI thumbnail makers ship it as a preset [CapCut AI thumbnail maker: https://www.capcut.com/tools/ai-thumbnail-maker].
- Detect: LOOK pass.
- Instead: families counted from the niche's outliers.

**Canva template look** WARN
- Tell: oversized headline, decorative strokes, generic icons, boxed info, the same on every post.
- Why: AI layout tools fill a pre-made template [Sivi: https://sivi.ai/blog/most-ai-design-tools-are-ai-wrappers].
- Detect: LOOK pass.
- Instead: the creator's own layout, measured.
