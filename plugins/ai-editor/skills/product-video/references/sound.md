# Sound: what Linear's and Apple's films do, and what sound.py takes

Measured 2026-10-06 from the same films as `style.md` (in `product-videos/refs/`), plus Stripe, Arc and
Raycast launch films: ffmpeg ebur128 for loudness, numpy for tempo (autocorrelation of the sub-band
envelope), band energy and transients, spectrograms read by eye.

## Linear

| film | LUFS | music | voice | notes |
|---|---|---|---|---|
| Introducing Linear Agent (55 s) | -28.9 | ambient bed | none | sub swells at 3-5 s and 41-43 s, UI ticks only at 7.5-11.7 s and 17.9-20.6 s |
| Releases trailer (30 s) | -24.7 | 110 BPM, a sub hit every bar (2.18 s apart) | none | chord change every 4 bars (9.0 s, 18.0 s); pulse stops at 27 s, pads ring to silence by 30 s |
| Releases, Initiatives demos | -21.1, -25.4 | none | yes | silence (-78 dB) between sentences: no bed under the voice |

- **Warm and dark.** 25-32% of the energy under 90 Hz, 40% in 300-3000 Hz, almost nothing over 4 kHz.
  Spectral centroid 750-810 Hz. No hi-hats, no claps.
- **The pulse is a sub, once a bar**, about 110 BPM. Pads hold 300-1000 Hz and change chord every
  2-4 bars.
- **Sound effects are rare and earned**: 0.3-0.4 high transients a second over a whole film, all of
  them while the UI is acting (typing ticks about 0.4 s apart). None on cuts.
- **Sub swells mark the big reveals**, about 2 in 55 s.
- **Ending**: the pulse stops on the logo; the pads ring out to silence over 3-5 s. No hit.
- Mixed quiet for YouTube (-25 to -29 LUFS). For social we master to -14.

## Apple

- **Loud, rhythmic, voice-led**: -15.5 to -16.1 LUFS. Creator Studio: 120 BPM, cuts within 2-4
  frames of the beat (1.63, 3.25, 9.72 s against beats at 1.7, 3.2, 9.7 s).
- **Hard button ending**: the music stops dead on the last beat and the logo sits in silence 4-5 s.
- Under voice, the bed in the gaps between sentences sits about 8 dB under the speech.

## Stripe, Arc, Raycast (style families)

- Stripe: -11 to -14 LUFS, music only, 90-96 BPM four-on-the-floor, a dropout about 3 s before the
  end, then the logo sting.
- Arc: -10.5 to -11.5 LUFS, 92-144 BPM, bells and arpeggios, 1 s of silence before a bass drop on the
  reveal, thin UI ticks on colour flips, rings out.
- Raycast: -13.2 LUFS, ambient pad and sub swells in 2-4 s blocks, no drums, key ticks under typing,
  fades to a low tail.

## What sound.py does with it

| | linear (default) | apple | stripe | arc | raycast |
|---|---|---|---|---|---|
| BPM | 110 | 120 | 100 | 96 | 128 |
| pulse | sub, bar downbeat | sub on 1 and 3, 8th ticks | sub, bar | sub on 1 and 3 | sub every beat, 8th ticks |
| plucks | 8ths from bar 3 | 8ths | 16ths, glassy | 8ths, major | 16ths |
| ending | pulse stops, resolved chord rings out | button: stops dead | rings | rings | button |

- **Cuts land on the beat.** `product.py plan` snaps every shot end to the score's beat grid (the
  user's own track: its detected beats), and the pads lift slightly for half a second after each cut.
- **Sound effects only where the UI acts**: a soft click on every recorded click and key press, a tick
  per typed character (9 a second, as recorded), a whoosh into a whip, a push-through or a lift, a
  swell and a sub hit into the logo. Never on a plain cut.
- **One file**: music, effects and any voice are mixed in numpy, the music ducked 9 dB under a voice,
  then mastered by ffmpeg to -14 LUFS integrated with a -1 dBTP ceiling (limited at 4x oversampling,
  measured -1.6 dBTP). Remotion plays it at unity.
- Every sound is synthesised in `sound.py` (`../audio/LICENSES.md`): nothing to licence, nothing
  downloaded.

## Measured on our renders (2026-10-06, ffmpeg ebur128)

| render | integrated | LRA | true peak |
|---|---|---|---|
| nextwork v3 linear 16:9 (44 s) | -14.1 LUFS | 2.4 LU | -1.6 dBTP |
| nextwork v3 linear 9:16 (41 s) | -14.0 LUFS | 2.5 LU | -1.6 dBTP |
| nextwork v2 linear 16:9 | -14.0 LUFS | 3.3 LU | -1.6 dBTP |
| nextwork v2 apple 16:9 | -14.1 LUFS | 1.9 LU | -1.6 dBTP |
| typesafe linear 16:9 | -14.0 LUFS | 3.3 LU | -1.6 dBTP |

Each effect's loudest 50 ms against the music's level around it (linear bed): click -4.8 dB, typing tick
-22.8 dB (felt more than heard, as in Linear's films), whoosh -15.1 dB, swell -5.8 dB, the logo hit
+8.7 dB (the bed has stopped pulsing by then).
