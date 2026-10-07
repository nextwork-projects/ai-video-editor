#!/usr/bin/env python3
"""The product film's sound: a score written for this cut, UI sound effects on the real clicks and keys,
mixed to -14 LUFS with a -1 dBTP ceiling. numpy + ffmpeg, deterministic, nothing downloaded.

    python3 sound.py demo                         self-check (renders 12 s of each mood, measures it)
    python3 sound.py sample OUT.wav --mood linear --length 20   hear a mood on its own

product.py plan calls score() with the plan's cuts, clicks, keystrokes and end card. Everything here is
synthesised from code in this file, so the audio is an original work with nothing to licence
(audio/LICENSES.md). What it copies from Linear's and Apple's films is measured, not sampled
(references/sound.md): Linear's ~110 BPM bed of warm pads under 1 kHz, a sub pulse once a bar, no
hi-hats, UI ticks only while the UI acts, the pulse stopping on the logo and the pads ringing out;
Apple's 120 BPM rhythmic bed with cuts on the beat and a hard button ending.

Music sources: "generated" (this file), "eleven" (ElevenLabs Music with the user's own key: their terms
allow online commercial use on every paid plan, not film/TV, no resale), a file the user owns, or none.
"""
import json
import math
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

import numpy as np

SR = 48000
TARGET_LUFS = -14.0      # social platforms normalise to about -14
CEILING_DBTP = -1.0
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "style-edit" / "scripts"))

# A mood is the music's grammar, never anyone's track. Measured or chosen per style family (references/sound.md).
#   bpm, chords (semitones from the key's root, a chord a `bars_per_chord` bars), key root (Hz),
#   cutoff: pad brightness (Hz, opens over the film), pluck: arpeggio steps a beat (0 = none),
#   kick: beats a bar that thump (sub pulse), hat: 8th-note ticks, end: "ring" (pulse stops, chord rings
#   out) or "button" (everything stops on one hit).
MOODS = {
    # Linear: measured 110 BPM, sub every bar, pads 300-1000 Hz, nothing above 4 kHz, pulse stops, rings out
    "linear": dict(bpm=110, root=73.42, chords=[[0, 3, 7, 10], [-4, 0, 3, 7], [-7, -3, 0, 5], [-2, 2, 5, 9]], bars_per_chord=2,
                   cutoff=(1100, 2000), pluck=2, pluck_from_bar=2, kick=[0], hat=False, end="ring", air=0.0),
    # Apple: measured 117-120 BPM, cuts within a few frames of the beat, hard stop on a hit, silence on the logo
    "apple": dict(bpm=120, root=82.41, chords=[[0, 4, 7, 11], [-3, 0, 4, 7], [-7, -3, 0, 4], [-5, -1, 2, 7]], bars_per_chord=1,
                  cutoff=(1400, 2800), pluck=2, pluck_from_bar=0, kick=[0, 2], hat=True, end="button", air=0.0),
    # Stripe: light and exact, glassy bell plucks, slow open harmony
    "stripe": dict(bpm=100, root=87.31, chords=[[0, 4, 7, 14], [5, 9, 12, 16], [-3, 4, 7, 12], [2, 5, 9, 14]], bars_per_chord=2,
                   cutoff=(1800, 3200), pluck=4, pluck_from_bar=1, kick=[0], hat=False, end="ring", air=0.15),
    # Arc / The Browser Company: warm, playful, major, a bounce on 2 and 4
    "arc": dict(bpm=96, root=98.0, chords=[[0, 4, 7, 9], [5, 9, 12, 16], [7, 11, 14, 17], [-3, 0, 4, 7]], bars_per_chord=1,
                cutoff=(1200, 2200), pluck=2, pluck_from_bar=0, kick=[0, 2], hat=False, end="ring", air=0.1),
    # Raycast: fast, dark, keyboard-first, a 16th pulse
    "raycast": dict(bpm=128, root=69.30, chords=[[0, 3, 7, 10], [-2, 2, 5, 9], [-4, 0, 3, 7], [-5, -2, 2, 5]], bars_per_chord=1,
                    cutoff=(900, 2400), pluck=4, pluck_from_bar=0, kick=[0, 1, 2, 3], hat=True, end="button", air=0.0),
}


# ---------------------------------------------------------------- building blocks

def t_axis(n):
    return np.arange(n) / SR


def spectral(x, fn, n_fft=2048, hop=512):
    """Time-varying EQ: STFT, gain = fn(freqs Hz, frame times s) -> (frames, bins), overlap-add."""
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    win = np.hanning(n_fft)
    n = 1 + (len(x) - n_fft) // hop
    idx = np.arange(n_fft)[None, :] + hop * np.arange(n)[:, None]
    X = np.fft.rfft(x[idx] * win, axis=1)
    f = np.fft.rfftfreq(n_fft, 1 / SR)
    tt = (np.arange(n) * hop + n_fft / 2) / SR
    y = np.fft.irfft(X * fn(f[None, :], tt[:, None]), n_fft, axis=1) * win
    out = np.zeros(len(x))
    np.add.at(out, idx, y)
    return out / (np.sum(win ** 2) / hop)


def band(lo, hi, slope=2):
    """A smooth band-pass gain for spectral(); lo/hi may be arrays over time."""
    return lambda f, t: 1 / (1 + (np.maximum(lo, 1) / np.maximum(f, 1)) ** (2 * slope)) / (1 + (f / hi) ** (2 * slope))


def noise(n, seed):
    return np.random.default_rng(seed).standard_normal(n)


def env_ad(n, attack, decay, shape=1.0):
    t = t_axis(n)
    a = np.clip(t / max(attack, 1e-4), 0, 1) ** shape
    return a * np.exp(-np.maximum(0, t - attack) / max(decay, 1e-4))


def reverb_ir(seconds=2.4, seed=5, bright=3500):
    """Stereo decorrelated noise tail, exponentially decaying and darkening: a soft hall."""
    n = int(seconds * SR)
    ir = []
    for s in (seed, seed + 1):
        r = noise(n, s) * np.exp(-t_axis(n) * 6.9 / seconds)
        r = spectral(r, lambda f, t: 1 / (1 + (f / (bright * np.exp(-t * 0.8))) ** 2))[:n]
        r[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))   # pre-delay feel
        ir.append(r / np.sqrt(np.sum(r ** 2)))
    return ir


def convolve(x, ir):
    n = len(x) + len(ir) - 1
    m = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, m) * np.fft.rfft(ir, m), m)[:len(x)]


def wet(stereo, amount, seconds=2.4, seed=5):
    L, R = stereo
    irL, irR = reverb_ir(seconds, seed)
    m = (L + R) / 2
    return np.stack([L + amount * convolve(m, irL), R + amount * convolve(m, irR)])


def place(buf, x, at, gain=1.0, pan=0.0):
    """Add mono or stereo x into stereo buf at time `at` (s), equal-power pan -1..1."""
    i = int(round(at * SR))
    if i >= buf.shape[1] or i + (x.shape[-1]) <= 0:
        return
    if x.ndim == 1:
        a = (pan + 1) * math.pi / 4
        x = np.stack([x * math.cos(a), x * math.sin(a)]) * math.sqrt(2)
    j0, k0 = max(0, i), max(0, -i)
    k1 = min(x.shape[1], buf.shape[1] - i)
    buf[:, j0:i + k1] += gain * x[:, k0:k1]


def db(x):
    return 20 * math.log10(max(1e-9, x))


# ---------------------------------------------------------------- the instruments

def pad_note(freq, dur, cutoff, seed):
    """Three detuned voices of a soft saw, harmonics rolled off at `cutoff`: warm, no filter loop."""
    n = int(dur * SR)
    t = t_axis(n)
    out = np.zeros(n)
    rng = np.random.default_rng(seed)
    for cents in (-7, 0, 7):
        f0 = freq * 2 ** (cents / 1200)
        ph = rng.uniform(0, 2 * math.pi)
        for h in range(1, 14):
            fh = f0 * h
            if fh > 9000:
                break
            out += np.sin(2 * math.pi * fh * t + ph * h) / h / (1 + (fh / cutoff) ** 4)
    vib = 1 + 0.0025 * np.sin(2 * math.pi * 0.23 * t + seed)
    return out * vib / 3


def pluck(freq, seed, bright=1.0, dur=1.2):
    """A soft mallet: sine + a little 2nd and 3rd harmonic, fast attack, ~0.3 s decay."""
    n = int(dur * SR)
    t = t_axis(n)
    tone = np.sin(2 * math.pi * freq * t) + 0.35 * bright * np.sin(2 * math.pi * 2 * freq * t) * np.exp(-t * 9) \
        + 0.12 * bright * np.sin(2 * math.pi * 3.01 * freq * t) * np.exp(-t * 14)
    return tone * env_ad(n, 0.004, 0.32)


def sub_thump(freq, dur=1.1):
    """The bar's sub pulse: a sine that drops from 2x into the root, soft attack (no click)."""
    n = int(dur * SR)
    t = t_axis(n)
    f = freq * (1 + np.exp(-t * 38))
    ph = 2 * math.pi * np.cumsum(f) / SR
    return np.sin(ph) * env_ad(n, 0.012, 0.32) * 0.9


def hat(seed):
    n = int(0.06 * SR)
    return spectral(noise(n, seed), band(7000, 14000))[:n] * env_ad(n, 0.001, 0.018)


# ---------------------------------------------------------------- sound effects (each a different job)

def sfx_click(seed=0):
    """A soft UI press: a 3 ms band-limited tap, a tiny 2.3 kHz body and a 160 Hz thock, short room."""
    n = int(0.16 * SR)
    t = t_axis(n)
    rng = np.random.default_rng(seed)
    tap = spectral(noise(n, 11 + seed), band(1800, 7500))[:n] * env_ad(n, 0.0006, 0.004)
    body = np.sin(2 * math.pi * 2300 * rng.uniform(0.95, 1.05) * t) * env_ad(n, 0.0005, 0.006) * 0.35
    thock = np.sin(2 * math.pi * 160 * t) * env_ad(n, 0.001, 0.018) * 0.5
    x = tap + body + thock
    return wet(np.stack([x, x]), 0.08, 0.35, 21 + seed)


def sfx_tick(seed=0):
    """A keystroke: lighter and higher than a click, a little different every time."""
    n = int(0.09 * SR)
    t = t_axis(n)
    rng = np.random.default_rng(100 + seed)
    f = rng.uniform(3000, 3800)
    x = spectral(noise(n, 200 + seed), band(2500, 9000))[:n] * env_ad(n, 0.0004, 0.003) \
        + 0.25 * np.sin(2 * math.pi * f * t) * env_ad(n, 0.0004, 0.004) + 0.2 * np.sin(2 * math.pi * 210 * t) * env_ad(n, 0.0008, 0.01)
    return wet(np.stack([x, x]), 0.06, 0.25, 31) * rng.uniform(0.75, 1.0)


def sfx_whoosh(dur=0.7, rise=True, seed=0):
    """Air whose band sweeps (up into a cut when rise), peaking at the end, panning across."""
    n = int(dur * SR)
    x = noise(n, 1729 + seed)
    lo = lambda t: 300 + 1600 * (t / dur if rise else 1 - t / dur)
    y = spectral(x, lambda f, t: band(lo(t), np.minimum(6000, lo(t) * 3.2), 2)(f, t))[:n]
    t = t_axis(n)
    e = (t / dur) ** 2.2 * np.exp(-np.maximum(0, t - dur * 0.86) * 40) if rise else env_ad(n, dur * 0.25, dur * 0.3)
    y *= e
    pan = np.linspace(-0.5, 0.5, n)
    a = (pan + 1) * math.pi / 4
    return wet(np.stack([y * np.cos(a), y * np.sin(a)]) * math.sqrt(2), 0.25, 1.2, 41)


def sfx_swell(dur=1.6, root=55.0, seed=0):
    """A riser into the logo: air climbing in band and level, a sine gliding up an octave under it."""
    n = int(dur * SR)
    t = t_axis(n)
    lo = lambda tt: 200 + 2400 * (tt / dur) ** 1.6
    air = spectral(noise(n, 77 + seed), lambda f, tt: band(lo(tt), lo(tt) * 2.5)(f, tt))[:n] * (t / dur) ** 2.5
    f = root * 2 * 2 ** (t / dur)
    tone = np.sin(2 * math.pi * np.cumsum(f) / SR) * (t / dur) ** 3 * 0.35
    x = air + tone
    x[-int(0.02 * SR):] *= np.linspace(1, 0, int(0.02 * SR))
    return wet(np.stack([x, x]), 0.3, 1.6, 51)


def sfx_hit(root=55.0, seed=0):
    """The landing: a sub boom and a soft bell a fifth and two octaves up, long tail."""
    n = int(3.0 * SR)
    t = t_axis(n)
    boom = np.sin(2 * math.pi * np.cumsum(root * (1 + 0.8 * np.exp(-t * 20))) / SR) * env_ad(n, 0.008, 0.7)
    bell = sum(a * np.sin(2 * math.pi * root * 4 * m * t) * env_ad(n, 0.002, d) for m, a, d in
               [(1.5, 0.22, 1.2), (3.0, 0.1, 0.8), (4.02, 0.05, 0.5)])
    x = boom + bell
    return wet(np.stack([x, x]), 0.35, 2.8, 61)


# ---------------------------------------------------------------- the score

def voice(chord, prev, lo=-3, hi=19):
    """The chord's notes placed so each voice moves as little as it can from the last chord (voice leading),
    kept within an octave and a bit, between lo and hi semitones over the pad's root."""
    import itertools
    opts = [[x + 12 * k for k in range(-2, 3) if lo <= x + 12 * k <= hi] for x in chord]
    best = None
    for combo in itertools.product(*opts):
        s = sorted(combo)
        if len(set(s)) < len(s) or s[-1] - s[0] > 15:
            continue
        cost = sum(abs(a - b) for a, b in zip(s, prev)) if prev else abs(sum(s) / len(s) - 7)
        if best is None or cost < best[0]:
            best = (cost, s)
    return best[1] if best else sorted(chord)


def bass_note(freq, dur, bright=1.0):
    """A round synth bass: sine with a little 2nd and 3rd harmonic, quick attack, settling to a sustain."""
    n = max(1, int(dur * SR))
    t = t_axis(n)
    x = np.sin(2 * math.pi * freq * t) + 0.22 * bright * np.sin(2 * math.pi * 2 * freq * t) \
        + 0.07 * bright * np.sin(2 * math.pi * 3 * freq * t) * np.exp(-t * 6)
    return x * np.clip(t / 0.008, 0, 1) * (0.6 + 0.4 * np.exp(-t / 0.2)) * np.clip((dur - t) / 0.05, 0, 1)


_BRUSH = {}


def brush(k):
    """A soft brushed tick, 700-3500 Hz (no hi-hat air: Linear's films have nothing over 4 kHz)."""
    k %= 6
    if k not in _BRUSH:
        n = int(0.12 * SR)
        _BRUSH[k] = spectral(noise(n, 300 + k), band(700, 3500))[:n] * env_ad(n, 0.003, 0.03 + 0.004 * k)
    return _BRUSH[k]


def riser(dur, root, seed=0):
    """Into the payoff: air whose band climbs, and two soft tones gliding up an octave, peaking at the end."""
    n = int(dur * SR)
    t = t_axis(n)
    p = t / dur
    lo = lambda tt: 160 + 1600 * (tt / dur) ** 2
    air = spectral(noise(n, 900 + seed), lambda f, tt: band(lo(tt), lo(tt) * 2.2)(f, tt))[:n] * p ** 2.2
    tone = sum(np.sin(2 * math.pi * np.cumsum(root * m * 2 ** p) / SR) for m in (4, 6)) * 0.1 * p ** 2.5
    x = air * 0.8 + tone
    k = int(0.03 * SR)
    x[-k:] *= np.linspace(1, 0, k)
    return x


# what each story job asks of the music: 0 pads and air, 1 the groove (sub, bass line, brushes, plucks), 2 the
# fullest (brighter pads, a busier bass), -1 the ending
INTENSITY = {"hook": 0, "reveal": 0, "transition": 0, "action": 1, "result": 1, "comparison": 1, "feature-list": 1, "payoff": 2, "end": -1}


def sections_of(sections, end_at):
    """[(start, intensity)] from the story's beats [(start s, job)], or a default arc when there are none."""
    if sections:
        out = [(float(t), INTENSITY.get(j, 1)) for t, j in sorted(sections) if t < end_at - 0.2 and INTENSITY.get(j, 1) >= 0]
        return out or [(0.0, 1)]
    return [(0.0, 0), (min(4.4, end_at * 0.15), 1), (end_at * 0.75, 2)]


def compose(mood, length, end_at=None, cuts=(), seed=0, sections=None):
    """A score for `length` s that follows the cut: a section per story beat (pads alone on the hook, the groove
    on the actions and results, the fullest on the payoff), the chord changing where the picture does (snapped
    to the beat), voice-led pads, a bass line that walks into each change, a riser into the payoff, and the
    ending at end_at (the pulse stops and the tonic rings, or a button). Returns (stereo array, beat times)."""
    m = MOODS[mood]
    beat = 60 / m["bpm"]
    bar = 4 * beat
    end_at = length if end_at is None else end_at
    n = int((length + 0.05) * SR)
    pads, bass, rhythm, fxb = (np.zeros((2, n)) for _ in range(4))
    chords = m["chords"]
    secs = sections_of(sections, end_at)
    snap_b = lambda x: round(x / beat) * beat
    # ---- the harmony: a change at every section (snapped to the beat), and every `bars_per_chord` bars inside one
    cpb = m["bars_per_chord"] * bar
    marks = sorted({0.0} | {snap_b(t) for t, _ in secs if beat < snap_b(t) < end_at - beat})
    changes = []
    for i, a in enumerate(marks):
        b = marks[i + 1] if i + 1 < len(marks) else end_at
        x = a
        while x < b - 1e-6:
            changes.append(x)
            x = x + cpb if b - (x + cpb) >= bar * 0.99 else b
    segs = []
    prev = None
    for i, a in enumerate(changes):
        b = changes[i + 1] if i + 1 < len(changes) else end_at
        last = i == len(changes) - 1 and len(changes) > 2
        ch = chords[-1] if last else chords[i % (len(chords) - 1 if len(changes) > 2 else len(chords))]
        prev = voice(ch, prev)
        lvl = next((s for t, s in reversed(secs) if t <= a + 1e-6), secs[0][1])
        segs.append({"t0": a, "t1": b, "chord": ch, "voicing": prev, "lvl": lvl})
    level_at = lambda t: next((s for t0, s in reversed(secs) if t0 <= t + 1e-6), secs[0][1])
    pad_root = m["root"] * 4
    for k, sg in enumerate(segs):
        dur = sg["t1"] - sg["t0"] + 0.9
        prog = min(1, sg["t0"] / max(1, end_at))
        cutoff = (m["cutoff"][0] + (m["cutoff"][1] - m["cutoff"][0]) * prog) * (1.25 if sg["lvl"] == 2 else 1.0)
        gain = {0: 0.17, 1: 0.19, 2: 0.22}[max(0, sg["lvl"])]
        for j, st in enumerate(sg["voicing"]):
            x = pad_note(pad_root * 2 ** (st / 12), dur, cutoff, seed + k * 7 + j)
            e = np.minimum(1, t_axis(len(x)) / 0.5) * np.minimum(1, (dur - t_axis(len(x))) / 0.9)
            place(pads, x * e * gain, sg["t0"], pan=(j - 1.5) * 0.35)
    # ---- the bass line: the root on the change, the fifth and octave in the bar, a step into the next chord
    groot = m["root"] if m["root"] < 80 else m["root"] / 2
    for k, sg in enumerate(segs):
        r = sg["chord"][0] % 12
        r = r - 12 if r > 6 else r
        nxt = segs[k + 1]["chord"][0] % 12 if k + 1 < len(segs) else 0
        nxt = nxt - 12 if nxt > 6 else nxt
        b = sg["t0"]
        while b < sg["t1"] - 1e-6:
            lvl = level_at(b)
            in_bar = round((b % bar) / beat) % 4
            last_bar = b + bar >= sg["t1"] - 1e-6
            if lvl <= 0:
                notes = [(0, r, 4)] if in_bar == 0 or b == sg["t0"] else []
            elif lvl == 1:
                notes = [(0, r, 1.5), (1.5, r, 0.5), (2, r + 7, 1.5)] + ([(3.5, nxt + (1 if nxt < r else -1), 0.5)] if last_bar else [(3.5, r + 12, 0.5)])
            else:
                notes = [(q * 0.5, r + (12 if q % 2 else 0), 0.5) for q in range(7)] + [(3.5, nxt + (1 if nxt < r else -1) if last_bar else r + 7, 0.5)]
            for off, semi, ln in notes:
                at = b + off * beat
                if at >= min(sg["t1"], end_at) - 0.02:
                    continue
                d = min(ln * beat * 0.92, sg["t1"] - at, end_at - at)
                place(bass, bass_note(groot * 2 ** (semi / 12), d, 0.8 + 0.4 * (lvl == 2)), at, (0.35 if lvl <= 0 else 0.42) * (1.0 if off == 0 else 0.8))
            b += bar
    # ---- the pulse, the plucks and the brushes, only where the section has the groove
    n_beats = int(end_at / beat + 1e-6)
    pump = np.ones(n)
    for bi in range(n_beats):
        tb = bi * beat
        lvl = level_at(tb)
        if lvl < 1:
            continue
        in_bar = bi % 4
        sg = next(s for s in segs if s["t0"] <= tb + 1e-6 < s["t1"] + 1e-6) if any(s["t0"] <= tb + 1e-6 < s["t1"] + 1e-6 for s in segs) else segs[-1]
        root_f = groot * 2 ** ((sg["chord"][0] % 12 - (12 if sg["chord"][0] % 12 > 6 else 0)) / 12)
        if in_bar in m["kick"]:
            place(rhythm, sub_thump(root_f), tb, 0.36 if in_bar == 0 else 0.22)
            i0 = int(tb * SR)
            k = min(n - i0, int(0.35 * SR))
            if k > 0:
                pump[i0:i0 + k] = np.minimum(pump[i0:i0 + k], 1 - 0.18 * np.exp(-t_axis(k) / 0.12))   # the pads breathe with the pulse
        if m["pluck"]:
            for s in range(m["pluck"]):
                ts = tb + s * beat / m["pluck"]
                step = bi * m["pluck"] + s
                v = sg["voicing"]
                note = v[(step * 3 + step // 4) % len(v)] + 12 * (step // 8 % 2)
                place(rhythm, pluck(pad_root * 2 ** (note / 12), seed + step, bright=1.2 + 0.3 * (lvl == 2)), ts,
                      (0.06 + 0.02 * (s == 0)) * (1.15 if lvl == 2 else 1.0), pan=0.4 * math.sin(step * 1.7))
        if m["hat"]:
            for s in range(2):
                place(rhythm, hat(seed + bi * 2 + s), tb + s * beat / 2, 0.05 if s else 0.03, pan=0.3)
        else:
            for s in range(2):
                acc = (0.032 if s else 0.02) * (1.2 if lvl == 2 else 1.0)
                place(rhythm, brush(bi * 2 + s), tb + s * beat / 2, acc, pan=-0.25 if s else 0.2)
    # ---- a riser into the payoff (or into the logo when the story has no payoff)
    pay = next((t for t, s in secs if s == 2), None)
    hit_at = snap_b(pay) if pay and pay > 3 else None
    if hit_at:
        rd = max(1.2, min(2 * bar, hit_at - 1.0))
        place(fxb, riser(rd, m["root"], seed), hit_at - rd, 0.16)
        place(rhythm, sub_thump(groot * 2 ** ((segs[-1]["chord"][0] % 12 - (12 if segs[-1]["chord"][0] % 12 > 6 else 0)) / 12)), hit_at, 0.42)
    # every cut: the pads lift a touch for the half second after it (the music answers the picture)
    env = np.ones(n)
    for c in cuts:
        i0, i1 = int(c * SR), int((c + 0.6) * SR)
        if i0 < n:
            env[i0:min(n, i1)] += 0.1 * np.exp(-t_axis(min(n, i1) - i0) * 6)
    pads *= env * pump
    # the groove and the bass stop on the end card (a 0.12 s release, no click)
    i_end = int(end_at * SR)
    rel = int(0.12 * SR)
    for bus in (bass, rhythm):
        bus[:, i_end:i_end + rel] *= np.linspace(1, 0, min(rel, max(0, n - i_end)))
        bus[:, i_end + rel:] = 0
    bed = wet(pads, 0.45, 2.6, seed + 3) + wet(rhythm, 0.2, 1.4, seed + 4) + bass + wet(fxb, 0.35, 2.0, seed + 6)
    if m["air"]:
        air = spectral(noise(n, seed + 9), band(5000, 12000))[:n] * 0.004 * m["air"] * 50
        bed += np.stack([air, np.roll(air, 900)])
    root_end = m["root"]
    tail = n - i_end
    if m["end"] == "button":
        bed[:, i_end:] = 0
        bed[:, max(0, i_end - 240):i_end] *= np.linspace(1, 0, min(240, i_end))
    elif tail > 0:
        # the pulse stops on the end card; the last pads ring and fade under the resolved chord: the tonic in
        # major with a 9th, voiced next to the last chord, a low tonic under it and one soft bell on the root
        bed[:, i_end:] = wet(pads[:, i_end:], 0.45, 2.6, seed + 3)[:, :tail] * np.linspace(1, 0, tail) ** 2
        res = np.zeros((2, tail))
        for j, st in enumerate(voice([0, 4, 7, 14], segs[-1]["voicing"] if segs else None)):
            x = pad_note(pad_root * 2 ** (st / 12), tail / SR, m["cutoff"][1] * 1.2, seed + 99 + j)
            x *= np.minimum(1, t_axis(len(x)) / 0.25) * np.linspace(1, 0, len(x)) ** 1.3
            place(res, x * 0.16, 0, pan=(j - 1.5) * 0.4)
        low = bass_note(groot, tail / SR, 0.5) * np.linspace(1, 0, tail) ** 1.5
        place(res, low, 0, 0.35)
        place(res, pluck(pad_root * 2, seed + 7, bright=0.8, dur=min(2.5, tail / SR)), 0.05, 0.08)
        bed[:, i_end:] += wet(res, 0.5, 3.0, seed + 5)[:, :tail]
    fade = int(0.08 * SR)
    bed[:, -fade:] *= np.linspace(1, 0, fade)
    beats = [round(b * beat, 4) for b in range(int(length / beat) + 1)]
    return bed, beats


def tonal(x):
    """(share of energy under 90 Hz, spectral centroid Hz, share over 4 kHz) of a stereo bed: the measures
    references/sound.md gives for Linear's films (25-32% under 90 Hz, centroid 750-810 Hz, almost nothing over 4 kHz)."""
    mono = x.mean(0)
    P = np.abs(np.fft.rfft(mono)) ** 2
    f = np.fft.rfftfreq(len(mono), 1 / SR)
    tot = P[f > 20].sum()
    return float(P[(f > 20) & (f < 90)].sum() / tot), float((P[f > 20] * f[f > 20]).sum() / tot), float(P[f > 4000].sum() / tot)


def beat_grid(mood, length):
    beat = 60 / MOODS[mood]["bpm"]
    return [round(k * beat, 4) for k in range(int(length / beat) + 2)]


# ---------------------------------------------------------------- outside music

def read_audio(path, length=None):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32).astype(np.float64).reshape(-1, 2).T
    if length:
        n = int(length * SR)
        x = np.pad(x, ((0, 0), (0, max(0, n - x.shape[1]))))[:, :n]
    return x


def eleven_music(prompt, seconds, out, key):
    """ElevenLabs Music with the user's own key ($0.15 a minute, 2026-07). Their terms (2026-05-26): online
    commercial use allowed on every self-serve plan, not film/TV/radio/games, no resale or redistribution
    of the track itself, attribution required on the free plan."""
    req = urllib.request.Request("https://api.elevenlabs.io/v1/music?output_format=mp3_44100_128",
                                 data=json.dumps({"prompt": prompt, "music_length_ms": int(seconds * 1000),
                                                  "force_instrumental": True}).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        Path(out).write_bytes(r.read())
    return out


def duck(music, vo, depth_db=-9, attack=0.08, release=0.35):
    """Music down by depth_db wherever the voice speaks, smooth both ways."""
    m = np.abs(vo).mean(0)
    win = int(0.05 * SR)
    rms = np.sqrt(np.convolve(m ** 2, np.ones(win) / win, "same"))
    speaking = (rms > 10 ** (-40 / 20)).astype(float)
    g = np.empty_like(speaking)
    a, r = 1 / (attack * SR), 1 / (release * SR)
    level = 0.0
    for i in range(0, len(g), 64):    # 64-sample blocks: fast enough, smooth enough
        target = speaking[i]
        level += (target - level) * min(1, (a if target > level else r) * 64)
        g[i:i + 64] = level
    return music * 10 ** (depth_db * g / 20)


# ---------------------------------------------------------------- mix + loudness

def write_wav(path, x):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x.T * 32767).astype("<i2").tobytes())


def measure(path):
    import quality
    return quality.loudness(path)


def master(x, out, target=TARGET_LUFS):
    """Gain to the target loudness, then ffmpeg's limiter for the -1 dBTP ceiling; measured, corrected once."""
    tmp = Path(out).with_suffix(".pre.wav")
    peak = np.abs(x).max()
    write_wav(tmp, x / max(peak, 1e-9) * 0.5)
    lufs, _ = measure(tmp)
    gain_db = target - (lufs if lufs is not None else -20)
    for _ in range(2):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-af",
                        f"volume={gain_db:.2f}dB,alimiter=limit={10 ** ((CEILING_DBTP - 0.6) / 20):.4f}:attack=3:release=80:level=false:asc=1,"
                        f"aresample=192000,alimiter=limit={10 ** ((CEILING_DBTP - 0.3) / 20):.4f}:attack=1:release=50:level=false,aresample={SR}",
                        "-c:a", "pcm_s16le", str(out)], check=True)
        lufs2, tp = measure(out)
        if lufs2 is None or abs(lufs2 - target) < 0.4:
            break
        gain_db += target - lufs2
    tmp.unlink()
    return measure(out)


def score(out, length, mood="linear", music="generated", sfx="subtle", cues=(), cuts=(), end_at=None, vo=None,
          own=None, eleven_key=None, prompt=None, seed=0, sections=None):
    """The film's whole soundtrack as one file. cues: [{"t": s, "kind": click|tick|whoosh|swell|hit, "pan": -1..1}].
    Returns a report: loudness, true peak, the music-to-effects balance."""
    n = int((length + 0.05) * SR)
    bed = np.zeros((2, n))
    if music == "generated":
        bed, _ = compose(mood, length, end_at, cuts, seed, sections)
        bed = bed[:, :n]
    elif music in ("own", "eleven") and own:
        if music == "eleven" and not Path(own).exists():
            eleven_music(prompt or "minimal warm ambient electronic product launch bed, soft sub pulse, no drums", length, own, eleven_key)
        bed = read_audio(own, length)
        f_out = int(min(2.5, length * 0.1) * SR)
        bed[:, -f_out:] *= np.linspace(1, 0, f_out) ** 1.5
    bed = np.pad(bed, ((0, 0), (0, max(0, n - bed.shape[1]))))[:, :n]
    fx = np.zeros((2, n))
    if sfx != "none":
        root = MOODS[mood]["root"]
        k = 0
        for c in cues:
            k += 1
            kind = c["kind"]
            x, g = {"click": (lambda: sfx_click(k % 5), 0.55), "tick": (lambda: sfx_tick(k), 0.44),
                    "whoosh": (lambda: sfx_whoosh(0.7, True, k % 3), 0.14), "swell": (lambda: sfx_swell(1.6, root), 0.22),
                    "hit": (lambda: sfx_hit(root), 0.5)}[kind]
            x = x()
            # each cue starts early by its build, so its loudest moment lands on the picture
            lead = {"whoosh": 0.6, "swell": 1.6}.get(kind, 0.0)
            pan = c.get("pan", 0.0)
            if pan:
                a = (pan + 1) * math.pi / 4
                x = np.stack([x[0] * math.cos(a), x[1] * math.sin(a)]) * math.sqrt(2)
            place(fx, x, c["t"] - lead, g)
    mix = bed * (0.5 if music != "none" else 0) + fx
    if vo is not None:
        v = read_audio(vo, length)
        mix = duck(mix, v) + v
    if not np.any(mix):
        return None
    lufs, tp = master(mix, out)
    # balance: each effect's loudest 50 ms against the bed's level around it (dB, effect minus bed)
    bal = []
    w = int(0.05 * SR)
    for c in cues if sfx != "none" and music != "none" else []:
        i = int(c["t"] * SR)
        seg_fx, seg_bed = fx[:, max(0, i - w * 12):i + w * 12], bed[:, max(0, i - w * 12):i + w * 12] * 0.5
        if seg_fx.size and seg_bed.size:
            loud = max(np.sqrt(np.mean(seg_fx[:, j:j + w] ** 2)) for j in range(0, seg_fx.shape[1] - w, w // 2))
            bal.append(db(loud) - db(np.sqrt(np.mean(seg_bed ** 2))))
    return {"file": str(out), "lufs": lufs, "true_peak": tp, "mood": mood, "music": music, "bpm": MOODS[mood]["bpm"],
            "cues": len(cues), "fx_minus_bed_db": round(float(np.median(bal)), 1) if bal else None}


# ---------------------------------------------------------------- self-check

def demo():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        for mood in MOODS:
            out = Path(d) / f"{mood}.wav"
            r = score(out, 12, mood, cues=[{"t": 2.0, "kind": "click"}, {"t": 4.0, "kind": "tick"}, {"t": 6.0, "kind": "whoosh"},
                                         {"t": 9.0, "kind": "swell"}, {"t": 9.0, "kind": "hit"}], cuts=[6.0], end_at=9.0)
            assert r and abs(r["lufs"] - TARGET_LUFS) < 1.0, r
            assert r["true_peak"] is None or r["true_peak"] <= CEILING_DBTP + 0.5, r
            x = read_audio(out)
            assert x.shape[1] >= 12 * SR
            bed, _ = compose(mood, 12, 9.0)
            after = np.abs(bed[:, int(9.1 * SR):]).max()
            assert (after < 1e-6) if MOODS[mood]["end"] == "button" else (after > 1e-3), (mood, after)   # button stops; ring rings
            print(f"{mood:8} {r['lufs']:.1f} LUFS  TP {r['true_peak']}  fx-bed {r['fx_minus_bed_db']} dB")
    # the score follows the cut: the hook is pads alone, the groove arrives with the first action, the chord
    # changes where a beat starts, the tone sits where Linear's trailer does (references/sound.md)
    secs = [(0, "hook"), (3.0, "action"), (7.4, "result"), (10.0, "payoff"), (14.0, "end")]
    bed, _ = compose("linear", 18, 14.0, [3.0, 7.4, 10.0], 0, secs)
    # the groove's movement: how much the level swings 20 ms to 20 ms (a held pad barely moves, a pulse does)
    def swing(a, b):
        e = np.sqrt(np.convolve(bed[:, int(a * SR):int(b * SR)].mean(0) ** 2, np.ones(960) / 960, "valid")[::480])
        return float(np.mean(np.abs(np.diff(e))) / np.mean(e))
    assert swing(1.0, 2.8) < 0.5 * swing(4, 7), (swing(1.0, 2.8), swing(4, 7))     # no pulse on the hook, the groove after
    sub, cen, hi = tonal(bed[:, :int(14 * SR)])
    assert 0.18 < sub < 0.42 and hi < 0.01, (sub, cen, hi)
    assert voice([0, 4, 7, 11], [0, 3, 7, 10]) == [0, 4, 7, 11]           # voice leading: the nearest voicing
    g = beat_grid("linear", 5)
    assert abs(g[1] - 60 / 110) < 1e-3
    print("demo ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
    elif sys.argv[1:2] == ["sample"]:
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd"); ap.add_argument("out")
        ap.add_argument("--mood", default="linear", choices=list(MOODS)); ap.add_argument("--length", type=float, default=20)
        a = ap.parse_args()
        L = a.length
        cues = [{"t": 3.0, "kind": "click"}, {"t": 5.0, "kind": "whoosh"}] + [{"t": 7 + i * 0.11, "kind": "tick"} for i in range(8)] \
            + [{"t": L - 4, "kind": "swell"}, {"t": L - 4, "kind": "hit"}]
        print(json.dumps(score(a.out, L, a.mood, cues=cues, cuts=[5.0, 9.0], end_at=L - 4)))
    else:
        print(__doc__)
