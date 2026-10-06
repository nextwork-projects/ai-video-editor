# What this takes from brag, and what it does differently

latent-spaces/brag (MIT, Copyright (c) 2026 Shunit Haviv Hakimi; attribution in the repo's
`THIRD_PARTY_NOTICES.md`) makes a short video from a project or a URL. Read at commit 7079945.

## Kept

- Scroll the page section by section before shooting; scroll-in content is blank otherwise.
- The grounding pass: every name, number and claim on screen exists in the source.
- The reading floor: about 0.3 s a word once the line has settled. Too many words: cut, never speed up.
- Cut on the beat of the track; sound starts with the motion it belongs to.
- No muddy crossfade between two busy layouts: cut, or dip through the ground.
- Look at stills of every shot and mid-transition before the full render.

## Fixed

| brag | here |
|---|---|
| Recreates the UI in HTML and CSS, so the "product" on screen is a re-drawing | Only real captures of the live page at 2x, the page's own videos, its real hover states |
| Many centred headline-only cards; text slides take a large share of the runtime | No text slides. Words only over or above real UI, at most 5, on at most two thirds of the shots |
| Flat saturated grounds and a stock gradient outro | The site's own ground; the end card is its own logo file on that ground |
| Brand read from source files, so a deployed site's real font often differs | Brand from the browser's computed styles, and the site's own font files downloaded and used |
| One look, one pass | Two variants from measured references (Apple, Linear) for the user to pick from, on a stills sheet first |
| The only gate is a lint pass | Words checked against the site's copy, AI tells checked on rendered frames (brand-aware), motion, contrast and loudness checked on the render |
| Bundled music whose licence its own README says is unverified | A score and effects synthesised per video by `sound.py` (nothing to licence, `audio/LICENSES.md`), or the user's own track or key |
| Almost no questions | A brief up front (what it shows, for whom, the end action), then style, length, music; recommended option first |
| One page, shot still | Up to 20 pages read for use cases; each shown as a real recorded click-through |
