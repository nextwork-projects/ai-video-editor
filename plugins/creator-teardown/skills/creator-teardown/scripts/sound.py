#!/usr/bin/env python3
"""The sound teardown: sound effects, what kind, how often, and the music under the voice.

  measure <handle>   per video: sound-effect onsets (spectral flux peaks that are not the
                     voice), each one's kind (whoosh, pop, click, riser, impact, ding) from
                     simple spectral features, whether music plays and how far under the
                     voice. Writes video/<id>.sound.json and merges `sound` into style.json.
  demo               self-check on synthetic audio (a voice, a music bed, five effects).

The voice mask is the transcript's word timings (the voice is where the words are), else a
plain energy gate in the speech band. Inside the voice an onset only counts when the band
the voice barely uses (under 120 Hz or over 7 kHz) jumps with it: a whoosh or a boom under
a sentence still counts, a hard consonant does not.

Kinds, from the 0.8 s after the onset:
  click   under 0.06 s, bright (centroid over 2.5 kHz)
  pop     under 0.18 s, tonal or mid
  impact  low (centroid under 500 Hz) with a tail
  ding    tonal, bright, rings 0.3 s or more
  whoosh  noisy, 0.2-1.2 s, swells to its peak
  riser   over 1 s, its centroid and level climb to the end
Music: a gap between phrases has music when it sits 10-40 dB under the voice, its spectrum
has peaks 20 dB over its floor (room tone is flat), and they hold for 0.1 s (a word the
timings missed glides). Two such gaps, or half of them, and the video has a bed; `span_s`
says where (an intro-only bed is common). `level_db`: gap level minus the median voice frame.

Usage (the tool venv python: numpy + ffmpeg):
  ~/.ai-video-editor/venv/bin/python scripts/sound.py measure <handle> [--force]
  ~/.ai-video-editor/venv/bin/python scripts/sound.py demo

Exit codes: 0 ok - 1 error - 2 usage
"""
import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, slug  # noqa: E402

SR = 22050
N_FFT, HOP = 1024, 256
KINDS = ["whoosh", "pop", "click", "riser", "impact", "ding", "other"]


def load_audio(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def stft(x):
    win = np.hanning(N_FFT).astype(np.float32)
    n = 1 + max(0, (len(x) - N_FFT) // HOP)
    idx = np.arange(N_FFT)[None, :] + HOP * np.arange(n)[:, None]
    return np.abs(np.fft.rfft(x[idx] * win, axis=1)).astype(np.float32)   # frames x bins


def db(x):
    return 20 * np.log10(np.maximum(x, 1e-9))


def voice_mask(words, n, dur, S=None, freqs=None):
    """Per STFT frame: True where someone is speaking."""
    m = np.zeros(n, bool)
    fr = HOP / SR
    if words:
        for a, b in words:
            m[max(0, int((a - 0.08) / fr)):min(n, int((b + 0.08) / fr) + 1)] = True
        # Word timings are loose: a silence under 0.25 s inside speech is still speech.
        idx = np.nonzero(~m)[0]
        if len(idx):
            for r in np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1):
                if 0 < r[0] and r[-1] < n - 1 and len(r) * fr < 0.25:
                    m[r] = True
        return m
    band = (freqs >= 250) & (freqs <= 3500)
    e = db(S[:, band].mean(1) + 1e-9)
    return e > np.percentile(e, 40) + 6


def onsets(S, freqs, voice):
    """(frame, flux z) of onsets that are not the voice."""
    L = np.log1p(S)
    flux = np.maximum(0, np.diff(L, axis=0, prepend=L[:1]))
    total = flux.sum(1)
    lin = np.maximum(0, np.diff(S, axis=0, prepend=S[:1]))   # linear: a loud low hit outweighs many quiet bins
    lo_share = lin[:, freqs < 120].sum(1) / (lin.sum(1) + 1e-9)
    k = int(2.0 * SR / HOP)
    out = []
    for i in range(1, len(total) - 1):
        a, b = max(0, i - k), min(len(total), i + k)
        base = np.median(total[a:b])
        mad = np.median(np.abs(total[a:b] - base)) + 1e-6
        z = (total[i] - base) / mad
        if z < 8 or total[i] < total[i - 1] or total[i] < total[i + 1]:
            continue
        # Inside speech only a low hit counts (a boom, a bass drop): an 's' is as bright and
        # noisy as a whoosh, so a whoosh under a word is not told apart and is missed.
        if voice[i] and lo_share[max(0, i - 1):i + 3].max() < 0.4:   # the low tail lands a frame or two late
            continue
        out.append((i, float(z)))
    return out


def classify(S, freqs, i, voice):
    """Kind of the effect starting at frame i, from the next 0.8 s (1.6 s for a riser). An
    effect in a gap is read only up to where the voice comes back."""
    fr = HOP / SR
    j = min(len(S), i + int(1.6 / fr))
    if not voice[i]:
        back = np.nonzero(voice[i:j])[0]
        j = i + int(back[0]) if len(back) else j
    j = max(j, i + 2)
    seg = S[i:j] ** 2                         # power: a low tone is not outweighed by wide noise
    edb = 10 * np.log10(seg.sum(1) + 1e-12)
    peak = int(edb[:int(0.8 / fr)].argmax())
    # The run of frames around the peak within 12 dB of it: how long the effect lasts.
    end = peak
    while end + 1 < len(edb) and edb[end + 1] >= edb[peak] - 12:
        end += 1
    dur = (end + 1) * fr
    rise = peak * fr
    sl = seg[:end + 1]
    cen = (sl * freqs).sum(1) / (sl.sum(1) + 1e-9)
    centroid = float(np.median(cen))
    spec = sl.mean(0) + 1e-9
    flat = float(np.exp(np.log(spec).mean()) / spec.mean())
    tonal = flat < 0.12
    climb = len(cen) > 8 and cen[-len(cen) // 4:].mean() > 1.3 * cen[:len(cen) // 4].mean() \
        and edb[end] >= edb[0] + 6
    if dur > 1.0 and (climb or rise > 0.6 * dur):
        kind = "riser"
    elif dur < 0.06 and centroid > 2500:
        kind = "click"
    elif centroid < 500 and dur >= 0.12:
        kind = "impact"
    elif tonal and centroid > 1000 and dur >= 0.3:
        kind = "ding"
    elif dur < 0.18:
        kind = "pop"
    elif not tonal and 0.15 <= dur <= 1.3 and rise >= 0.05:
        kind = "whoosh"
    else:
        kind = "other"
    return {"kind": kind, "dur_s": round(dur, 3), "rise_s": round(rise, 3), "centroid_hz": round(centroid),
            "flatness": round(flat, 3)}


def music(S, freqs, voice, words):
    """(present, level_db under the voice) from the gaps between phrases."""
    fr = HOP / SR
    gaps = []
    if words:
        pairs = list(zip(words, words[1:]))
        gaps = [(a[1] + 0.06, b[0] - 0.06) for a, b in pairs if b[0] - a[1] >= 0.3]
    else:
        idx = np.nonzero(~voice)[0]
        if len(idx):
            runs = np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1)
            gaps = [(r[0] * fr, r[-1] * fr) for r in runs if len(r) * fr >= 0.3]
    band = (freqs >= 60) & (freqs <= 5000)

    def level(seg):   # dB of the band's power, frame by frame
        return 10 * np.log10((seg ** 2).sum(1) + 1e-12)
    v_level = float(np.median(level(S[voice][:, band]))) if voice.any() else None
    levels, tonal, kept = [], [], []
    for a, b in gaps:
        seg = S[int(a / fr):int(b / fr)][:, band]
        if len(seg) < 3:
            continue
        kept.append((a, b))
        spec = np.median(seg, 0) ** 2 + 1e-12  # medians: an effect inside the gap does not count
        levels.append(float(np.median(level(seg))))
        # Steady tonal peaks: the median spectrum's peaks stand far above its floor (dB).
        # Room tone is flat noise; a held chord or a bass line is not.
        p2f = float(10 * np.log10(spec.max() / np.median(spec)))
        # Held: a bed's notes last; a word Whisper left out of the timings glides. The
        # correlation of the log spectrum with itself 0.1 s later, over the gap.
        lg = np.log(seg[:, (freqs[band] >= 100) & (freqs[band] <= 4000)] ** 2 + 1e-10)
        lg = lg - lg.mean(1, keepdims=True)
        k = max(1, int(0.1 / fr))
        held = [float((u * v).sum() / (np.linalg.norm(u) * np.linalg.norm(v) + 1e-9)) for u, v in zip(lg, lg[k:])]
        tonal.append((p2f, float(np.median(held)) if held else 0.0))
    if v_level is None or len(levels) < 2:
        return {"present": None, "level_db": None, "gaps": len(levels)}
    rel = [lv - v_level for lv in levels]
    # Louder than -10 dB is a voice the word timings missed, not a bed.
    hits = [-40 < r < -10 and t[0] > 20 and t[1] > 0.5 for r, t in zip(rel, tonal)]
    present = sum(hits) >= 2 or (len(hits) >= 2 and sum(hits) >= 0.5 * len(hits))
    spans = [g for g, h in zip(kept, hits) if h]
    return {"present": bool(present),
            "level_db": round(float(statistics.median(r for r, h in zip(rel, hits) if h)), 1) if present else None,
            "gaps": len(levels), "gaps_with_music": sum(hits),
            "span_s": [round(spans[0][0], 1), round(spans[-1][1], 1)] if present else None}


def measure_audio(x, words, cuts=(), graphics=()):
    S = stft(x)
    freqs = np.fft.rfftfreq(N_FFT, 1 / SR)
    dur = len(x) / SR
    voice = voice_mask(words, len(S), dur, S, freqs)
    fr = HOP / SR
    sfx = []
    busy = -1.0
    for i, z in onsets(S, freqs, voice):
        t = round(i * fr, 3)
        if t < busy:
            continue          # a swell or tail inside the effect before it
        c = classify(S, freqs, i, voice)
        busy = t + max(0.25, c["dur_s"])
        c.update({"t": t, "in_voice": bool(voice[i]), "z": round(z, 1),
                  "on_cut": any(abs(t - u) <= 0.15 for u in cuts),
                  "on_graphic": any(abs(t - g) <= 0.25 for g in graphics)})
        sfx.append(c)
    return {"duration_s": round(dur, 2), "sfx": sfx, "sfx_per_min": round(len(sfx) / dur * 60, 1) if dur else 0,
            "music": music(S, freqs, voice, words)}


def words_of(tdir, vid):
    p = tdir / f"{vid}.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    return [(w["start"], w["end"]) for w in d.get("words", []) if w.get("type") == "word"]


def summarise(rows):
    ss = [s for r in rows for s in r["sfx"]]
    mins = sum(r["duration_s"] for r in rows) / 60 or 1
    ms = [r["music"] for r in rows if r["music"]["present"] is not None]
    kinds = Counter(s["kind"] for s in ss)
    return {
        "sfx_per_min": round(len(ss) / mins, 1),
        "sfx_per_min_by_video": [r["sfx_per_min"] for r in rows],
        "kinds": {k: round(100 * v / len(ss)) for k, v in kinds.most_common()} if ss else {},
        "on_cut_pct": round(100 * sum(s["on_cut"] for s in ss) / len(ss)) if ss else None,
        "on_graphic_pct": round(100 * sum(s["on_graphic"] for s in ss) / len(ss)) if ss else None,
        "in_voice_pct": round(100 * sum(s["in_voice"] for s in ss) / len(ss)) if ss else None,
        "music": {"present_pct": round(100 * sum(m["present"] for m in ms) / len(ms)) if ms else None,
                  "level_db": statistics.median([m["level_db"] for m in ms if m["present"]])
                  if any(m["present"] for m in ms) else None},
        "measured": len(rows),
        "source": "code",
    }


def cmd_measure(a):
    outdir = OUT_ROOT / slug(a.handle)
    vids = sorted((outdir / "video").glob("*.mp4"))
    if not vids:
        sys.exit(f"no videos in {outdir / 'video'}. Run visual.py download first.")
    rows = []
    for p in vids:
        cache = p.with_suffix(".sound.json")
        if cache.exists() and not a.force:
            rows.append(json.loads(cache.read_text(encoding="utf-8")))
            continue
        vis = p.with_suffix(".visual.json")
        cuts = json.loads(vis.read_text(encoding="utf-8"))["cuts"] if vis.exists() else []
        gj = p.with_suffix(".graphics.json")
        gins = [g["t_in"] for g in json.loads(gj.read_text(encoding="utf-8"))["graphics"]] if gj.exists() else []
        r = measure_audio(load_audio(p), words_of(outdir / "transcripts", p.stem), cuts, gins)
        r["id"] = p.stem
        cache.write_text(json.dumps(r, indent=1), encoding="utf-8")
        rows.append(r)
        print(f"{p.stem}: {len(r['sfx'])} effects ({r['sfx_per_min']}/min) "
              f"{dict(Counter(s['kind'] for s in r['sfx']))}, music {r['music']}", file=sys.stderr)
    sp = outdir / "style.json"
    style = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {"handle": slug(a.handle)}
    style["sound"] = summarise(rows)
    sp.write_text(json.dumps(style, indent=2), encoding="utf-8")
    if a.json:
        print(json.dumps(style["sound"], indent=1))
    print(summary_line(style["sound"], sp))


def summary_line(s, path):
    """One line for Claude's context: the full block is style.json "sound", --json prints it."""
    kinds = ", ".join(f"{k} {v}%" for k, v in list(s["kinds"].items())[:4]) or "none"
    m = s["music"]
    music = "no music" if not m["present_pct"] else f"music in {m['present_pct']}% at {m['level_db']} dB"
    return f"sound: {s['sfx_per_min']} effects/min ({kinds}), {music}, {s['measured']} videos -> {path} (\"sound\")"


# ---------- self-check ----------

def demo():
    """10 s at 22.05 kHz. A voice (150 Hz harmonics, one swell a word) speaks 0.5-7.6 s with
    gaps at 2.0-2.6, 3.4-4.2 and 6.4-7.0 s; a chord bed 24 dB under it; a click at 2.2 s, a
    whoosh at 3.6 s, a boom at 5.5 s under the voice, a pop at 6.6 s and a riser 8.0-9.4 s."""
    rng = np.random.default_rng(0)
    t = np.arange(10 * SR) / SR
    gaps = [(2.0, 2.6), (3.4, 4.2), (6.4, 7.0)]
    words = []
    w0 = 0.5
    while w0 < 7.6:
        if not any(a - 0.25 <= w0 < b for a, b in gaps):
            words.append((w0, w0 + 0.22))
        w0 += 0.3
    env = np.zeros_like(t)
    for a, b in words:   # each word swells in and out, as a voice does
        i, j = int(a * SR), int(b * SR)
        env[i:j] = np.hanning(j - i)
    voice = sum(np.sin(2 * np.pi * 150 * k * t) / k for k in range(1, 20)) * env * 0.25
    bed = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.2, 329.6, 440)) * 0.25 * 10 ** (-24 / 20) * 0.6
    x = voice + bed + rng.normal(0, 1e-4, len(t))

    def put(t0, sig):
        i = int(t0 * SR)
        x[i:i + len(sig)] += sig[:len(x) - i]
    n = rng.normal(0, 1, int(0.02 * SR))
    put(2.2, n * np.exp(-np.arange(len(n)) / (0.004 * SR)) * 0.5)
    k = int(0.5 * SR)
    sw = np.fft.irfft(np.fft.rfft(rng.normal(0, 1, k)) * (np.fft.rfftfreq(k, 1 / SR) > 1500), k)
    put(3.6, sw * np.sin(np.pi * np.arange(k) / k) ** 2 * 0.6)
    k = int(0.6 * SR)
    put(5.5, (np.sin(2 * np.pi * 55 * np.arange(k) / SR) + 0.3 * rng.normal(0, 1, k) * (np.arange(k) < 0.01 * SR))
        * np.exp(-np.arange(k) / (0.15 * SR)) * 0.9)
    k = int(0.09 * SR)
    put(6.6, np.sin(2 * np.pi * 900 * np.arange(k) / SR) * np.exp(-np.arange(k) / (0.02 * SR)) * 0.6)
    k = int(1.4 * SR)
    noise = rng.normal(0, 1, k)
    rs = np.zeros(k)
    for j in range(0, k, 2048):
        f0 = 300 + 6000 * j / k
        seg = noise[j:j + 2048]
        F = np.fft.rfft(seg)
        F[np.fft.rfftfreq(len(seg), 1 / SR) < f0] = 0
        rs[j:j + 2048] = np.fft.irfft(F, len(seg))
    put(8.0, rs * np.linspace(0.05, 0.5, k))
    r = measure_audio(x.astype(np.float32), words, cuts=[5.5], graphics=[3.65])
    got = [(s["t"], s["kind"]) for s in r["sfx"]]
    print([(s["t"], s["kind"], s["dur_s"], s["centroid_hz"], s["flatness"], s["rise_s"]) for s in r["sfx"]], r["music"])
    want = {2.2: "click", 3.6: "whoosh", 5.5: "impact", 6.6: "pop", 8.0: "riser"}
    for t0, kind in want.items():
        hit = [s for s in r["sfx"] if abs(s["t"] - t0) <= 0.12]
        assert hit and hit[0]["kind"] == kind, (t0, kind, got)
    assert len(r["sfx"]) <= 6, got
    assert [s for s in r["sfx"] if abs(s["t"] - 5.5) <= 0.12][0]["on_cut"]
    assert [s for s in r["sfx"] if abs(s["t"] - 5.5) <= 0.12][0]["in_voice"]
    assert [s for s in r["sfx"] if abs(s["t"] - 3.6) <= 0.12][0]["on_graphic"]
    m = r["music"]
    assert m["present"] and -20 <= m["level_db"] <= -8, m   # 24 dB under the loudest word, ~12 under the median frame
    quiet = measure_audio((voice + rng.normal(0, 3e-4, len(t))).astype(np.float32), words)
    assert not quiet["music"]["present"] and not quiet["sfx"], (quiet["music"], quiet["sfx"])
    s = summarise([r])
    assert s["kinds"] and s["music"]["present_pct"] == 100, s
    line = summary_line(s, "style.json")   # measure prints one line, not the JSON block
    assert "\n" not in line and "{" not in line and "effects/min" in line, line
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure")
    p.add_argument("handle")
    p.add_argument("--force", action="store_true")
    p.add_argument("--json", action="store_true", help="print the measured block in full")
    p.set_defaults(fn=cmd_measure)
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
