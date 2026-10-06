# Third-party notices

## HyperFrames registry (Apache License 2.0)

Copyright 2026 HeyGen, Inc. https://github.com/heygen-com/hyperframes, `registry/`, read at commit
`5fad52f21d0cb4742245d0b13c012d53c952d7ef`. Licensed under the Apache License, Version 2.0
(http://www.apache.org/licenses/LICENSE-2.0).

Only motion was ported, by hand, into React templates: timeline structure, eases, durations,
staggers, masks and draw orders. No HTML, CSS, brand assets, copy or data were copied. Every ported
piece was modified (rewritten as a React component driven by a seeked GSAP timeline, retimed by a
motion personality, restyled by a look object). Files: `plugins/ai-editor/remotion/src/Templates.tsx`,
`motion.ts`, `Captions.tsx`, `Capture.tsx`, `Anims.tsx`, `Scene.tsx`, `StyleEdit.tsx`.

| upstream item | ported into | what was taken |
|---|---|---|
| `components/headline-slam` | `slam` | scale 1.6 -> 1 on expo.out over 0.58 s, three-frame impact shake, sine.inOut breathing hold |
| `components/caption-kinetic-slam` | `slam` | back.out / expo.out per-word slam entrances |
| `components/per-word-rise` | `title`, `settle` ease | masked staggered rise; the piecewise "settle" landing curve |
| `components/marker-highlight` | `phrase_mark` (marker) | stroke drawn on power2.inOut after the line rises, settle pop (1.045, yoyo) on the word |
| `components/hw-callout-circle` | `phrase_mark` (circle), `spring.*` eases | wobbled 14-point ellipse path, damped spring ease normalised to end on 1 |
| `components/strikethrough-replace` | `phrase_mark` (strike) | strike drawn on power2.out, the replacement word dropping in |
| `components/count-up` | `counter` | eased count then a 1.07 landing pulse |
| `components/number-wheel` | `counter` (wheel) | per-digit strips on power3.out with a 0.05 s stagger |
| `components/animated-bar-chart` | `bar_chart` | bars grow on power3.out over ~1.2 s |
| `blocks/mk-line-graph` | `line_chart` | axis fade, staggered x labels, line draw on power2.inOut, dots pop on back.out as the line reaches them |
| `components/comparison-split` | `versus` | split reveal timing |
| `components/before-after-wipe` | `versus` (wipe) | sine.inOut wipe of the after layer, handle riding the seam |
| `components/marker-checklist-card` | `checklist` | rows in turn, ticks drawn on power1.in |
| `blocks/flowchart` | `flow` | nodes pop on back.out(1.7), connectors draw before the next node |
| `components/logo-sting` | `logo_sting` | logo 1.15 -> 1 on expo.out, ring 0.34 -> 2.4 fading on power3.out, one-frame flash timing |
| `blocks/x-post`, `blocks/yt-comment-card`, `blocks/reddit-post` | `social_post` | card rises on power3.out 0.6 s, avatar back.out(1.6), meta then text, like bump |
| `blocks/lt-mask-reveal`, `blocks/lt-side-rule` | `lower_third` | rule scaleY on power3.out, name clip-path wipe with a sweep, role rising after |
| `components/hw-arrow` | `arrow_callout` | shaft drawn first, head after, pen-paced ease |
| `components/confetti` | `icon_burst` | burst of flat shapes from the subject |
| `blocks/transitions-cover`, `blocks/transitions-push` | card swap in `StyleEdit.tsx`; `block` and `push` scene transitions in `Scene.tsx` | two staggered colour blocks on power3.inOut (0.06 s apart), the scene switching under them; a push on power3.inOut |
| `components/caption-pill-karaoke` | `Captions.tsx` | per-word colour fill as the word is said |

## GSAP (GSAP Standard License)

`gsap` and its plugins (CustomEase, CustomWiggle, DrawSVGPlugin, MorphSVGPlugin, MotionPathPlugin,
Physics2DPlugin, SplitText) are free to use under the GSAP Standard "No Charge" License,
https://gsap.com/standard-license. They are installed from npm, not vendored.

## Remotion

`remotion` and `@remotion/*` packages are used under the Remotion License,
https://github.com/remotion-dev/remotion/blob/main/LICENSE.md (free for individuals and small
companies; larger companies need a company license).

## LottieFiles motion-design-skill (MIT)

`plugins/ai-editor/skills/motion-design/` is vendored from https://github.com/lottiefiles/motion-design-skill
at commit f9a8a041b85185ee4881b3471d3415e939aac772, Copyright (c) LottieFiles, MIT licence (kept in that
folder as LICENSE). Changed: a `compatibility` frontmatter line and a short note on how the editor uses it.

## brag (MIT)

https://github.com/latent-spaces/brag, read at commit `7079945d391573edebe48fdc0a23b39c4b4e8726`.
MIT licence, reproduced in full:

> MIT License
>
> Copyright (c) 2026 Shunit Haviv Hakimi
>
> Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all
> copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
> IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
> FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
> AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
> LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
> OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
> SOFTWARE.

No code, assets or music were copied. Rules were adapted, reworded, into
`plugins/ai-editor/skills/product-video/`:

| upstream | adapted into | what was taken |
|---|---|---|
| `skills/brag-slim/SKILL.md` (website mode) | `scripts/crawl.mjs` | scroll the page section by section before shooting so scroll-in content is not blank; dismiss overlays first |
| `skills/brag/references/step-2-plan.md` | `scripts/product.py` `durations`, `references/story.md` | the reading floor (about 0.3 s a word once settled) and "too much text means cut it, never speed it up" |
| `skills/brag/references/step-3-compose.md` (grounding) | `product.py` `check_story`, `references/story.md` | the grounding pass: names, numbers and claims on screen must exist in the source |
| `skills/brag/references/audio.md` | `product.py` `beats`/`snap` | cut on the beat of the user's track; sound starts with the motion |
| `skills/brag-slim/SKILL.md` §3 | `ProductVideo.tsx` | no muddy crossfades between busy layouts: cut, or dip through the ground |

## Robust Video Matting (GPL-3.0), downloaded at first use, not shipped

`skills/style-edit/scripts/matte.py` runs the `rvm_mobilenetv3_fp32.onnx` weights from
github.com/PeterL1n/RobustVideoMatting (Lin et al., "Robust High-Resolution Video Matting with
Temporal Guidance", 2021) through onnxruntime. The file is fetched from that project's release into
`~/.ai-video-editor/models/` on the user's computer when they turn on graphics behind the speaker. No
RVM code or weights are part of this repository.

## Product video: sound and reference films

`plugins/ai-editor/skills/product-video/` ships no third-party audio. Its music and sound effects are
synthesised per video by `scripts/sound.py` from code in this repository; the evidence for every sound is
in `skills/product-video/audio/LICENSES.md`. Kenney's "Interface Sounds" (CC0 1.0) was evaluated and not
used. ElevenLabs Music is an optional source the user calls with their own key, under ElevenLabs' Eleven
Music Model-Specific Terms (last updated 2026-05-26); its tracks stay in the user's project and are never
bundled.

The style and sound lessons in `references/style.md` and `references/sound.md` were measured from public
launch films by Apple, Linear, Stripe, The Browser Company (Arc, Dia) and Raycast (cut times, colours,
loudness, tempo, spectrograms). Nothing from those films (footage, audio, brand, type, colour) is copied
into the plugin or its output; the renderer uses only the target site's own UI, colours, fonts and words.
