# Style: what Apple, Linear, Stripe, Arc and Raycast films do, and what the styles take

Measured 2026-10-06 from 3 Apple software films (Siri next step, Child safety, Creator Studio) and 4
Linear videos (Introducing Linear Agent, Releases trailer, two feature demos), all from the official
YouTube channels: ffmpeg scene detection for cuts, PIL for colours, the frames read by eye.

The variants borrow camera language, pacing, framing and restraint. Never their brand: colour, type
and logo always come from the target site's CSS (`site.json` "brand").

## Apple

- **One idea a shot.** Hard-cut median 1.9-3.5 s; long shots are continuous moves with a new beat
  every 2-4 s inside them.
- **Ground**: pure black for hero pieces, a light cool grey (#DDDCE1) for feature explainers. Never a
  gradient on the ground; light comes from the objects.
- **UI shown huge and crisp.** A device is either whole (about a quarter of the frame wide) or cropped
  so the UI runs off the bottom edge at about three quarters of the width.
- **Camera**: a push of about 3x over about 1 s, eased, then a 2-4 s hold. A pull back marks a new
  section.
- **Lift-out**: one card scales out of the screen to about 57% of the frame width; the screen behind
  blurs and fades. Cards then morph into the next card rather than cut.
- **UI moves as in the real app**; interaction is shown, not described.
- **Words**: 1-3 words a card in the system font, sentence case, about 1-1.5 s each; or one centred
  line above the product. Never a kicker, a subline and a rule.
- **End**: the logo, centred, about 6% of the width, held 2-6 s.

## Linear

- **Long shots, few cuts**: 2-4 hard cuts in 30-55 s. Inside a shot the camera never stops: a slow
  drift of 2-5% of the frame width a second plus a slow push onto the active component.
- **The app as a plane in perspective**, tilted 20-30 degrees, filling 75-95% of the frame and
  running off the edges. No device frame. The near edge sharp, the far edge darker.
- **Dark monochrome** (#000000-#101010, UI surfaces #0A0E0F-#161B1E); the only colour is status dots.
  Light comes from the UI itself.
- **Keyboard, not cursor**: typed input at about 8 characters a second, results staggering in row by
  row from blur.
- **Words**: small (about 3% cap height), typed or focusing in from blur, 1.5-2 s a card.
- **Transitions**: blur-dissolves between UI scenes; cuts to black only for words.
- **End**: "Linear" focusing in from blur over about 1 s, then the mark, centred, held 3-5 s.

## Stripe

Measured from "Stripe Sessions 2024 | Payments updates" (64 s) and "New Revenue and Finance Automation
tools" (67 s): 6-7.5 cuts per 30 s, median shot 2.0-2.7 s, music only, 90-96 BPM.

- **Type carries the story**: kinetic word cards on a plain ground, 1-3 words landing a beat, 3-5 words
  a line, 8-10% of the frame height (20-25% for the opening words).
- **One UI card a shot**, flat and centred, 25-40% of the frame wide. No device, no tilt.
- **No camera move.** Components fade or blur in place and step through states about 1 s apart.
- **The cursor drives every shot**: it glides to a control and clicks; the state changes on the click.
- **A/B features get a split screen**, the same component mirrored.
- **Cuts are hard and on the beat**; the end is a roll-call of names, then the wordmark, held 2 s.

## Arc / The Browser Company

Measured from "Boosts by Arc" (42 s), "Arc 1.0" (34 s), Dia (78 s, UI inserts only): 16-43 cuts per 30 s,
median shot 0.9-1.3 s, 92-144 BPM.

- **The fastest**: a cut on every beat and half-beat.
- **UI flat and large**, 60-90% of the frame wide, often cropped off one edge.
- **Word cards small**: 2-3 words, lowercase, about 4% of the height, centred.
- **Cursor POV**: the real cursor clicks, drags, toggles; panels slide in from the side.
- **Hard cuts only**, no camera moves. A bell and arpeggio bed, 1 s of silence, then a bass drop on the
  reveal; the end rings out.

## Raycast

Measured from "New Raycast. Coming 2026" (39 s, pure UI): 4-7 cuts per 30 s, median shot 2.7-4.7 s, no voice.

- **Long, calm shots**; dissolves and blur between scenes, almost no hard cuts.
- **Macro crop of the launcher**: the search field fills the frame and runs off the edge.
- **Keyboard, not cursor**: typed at about 7 characters a second, hotkey keycaps shown.
- **Results arrive staggered**, rows filling top to bottom; a grid of tiles assembles.
- **Camera**: slow drift and gentle push, 2-3% of the frame width a second.
- **Words tiny**: monospace caps, about 1.5% of the height, one feature a card.
- **Sound is a bed, not a beat**: pad swells, key ticks synced to the typing.

## How the variants use it

- `apple`: the window straight on, its shadow soft and real, running off the bottom; a hold then an
  eased push into one component; consecutive page shots are one continuous camera; the real cursor
  glides in on an arc and clicks a real button (its captured hover state swaps in on the press);
  lifted components scale to the middle while the page blurs and fades; words big and centred above
  the UI, the UI cut off just below them; hard cuts; the logo sting at the end.
- `linear`: the page as a tilted plane (26 degrees on X, a little on Y and Z) bleeding off the frame;
  a slow push and a constant drift; a glow behind the plane made by blurring the UI itself (on a dark
  site it reads as the screen's own light; on a light site it is barely there, as it should be);
  lifts arrive tilted and settle flat; every cut is a blur-dissolve through the site's ground; words
  small, low left, each one focusing in from blur.
- `stripe`: flat window, still camera (a 1.5% push), hard cuts, big words low left landing word by word;
  favours `type`, `flow` with clicks, `split`, `grid`. 100 BPM, glassy plucks.
- `arc`: flat and large, cropped off an edge, hard cuts, shots 0.7x Linear's length, small lowercase words
  with a bounce, springy entrances; favours `flow`, `whip`, `grid`, `type`. 96 BPM, major.
- `raycast`: flat, slow drift and a 6% push, blur-dissolves, shots 1.2x, tiny monospace caps; favours
  `keys`, `macro`, `grid`. 128 BPM, button ending.
- Linear stays the default and is recommended first in the question box.
- All: the site's own ground, ink, accent, fonts (its font files, else the same family from Google
  Fonts) and logo. Vertical frames show about two screens of page and crop the sides, starting from
  the left edge of a line, never shrinking the page to a strip.

## Look for, on every sheet and strip

- The UI fills the frame. A thin strip of page with ground above and below is a failed shot: a
  narrower focus rect, a lift, or on 9:16 the phone-layout recording (`check` measures it: 75% on 9:16).
- No half words at the frame edge on the shot's own subject (page content cut at the edge elsewhere is
  fine; it is a crop).
- Nothing holds still for more than about 2 s.
- No shot type twice in a row; at least 5 types in 30 s.
- Words never sit over UI, never repeat a headline in frame, never more than 5.
- The lifted element is sharp (crops are 2x) and clearly in front: shadow on light sites, a hairline on
  dark ones.
- The end card is the site's own logo, not a screenshot of the header.
- Against the owner's bans: no centred heading + subline + rule, no flat saturated ground the site
  does not use, no purple-blue the site does not use, no emoji, no icon tiles, no text-only slides, no
  stat the site does not state.
