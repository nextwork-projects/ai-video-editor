#!/usr/bin/env python3
"""The sound cues: synthesised by ffmpeg from pinned seeds, then level-matched to this cut's speech.

    python3 sfx.py build edits/NAME     writes edits/NAME/.sfx/*.wav + kit.json
    ~/.ai-video-editor/venv/bin/python sfx.py music edits/NAME [--track audio/track.wav | --mood linear] [--under-db 18]
                                        the music bed: .sfx/music.wav, ducked under the speech
    python3 sfx.py demo                 self-check

Every cue is generated, not sampled, so there is nothing to licence. Level is baked into
the file, because Remotion clamps <Audio volume> to 1: a cue can only get louder here.
Levels are matched on the loudest 50 ms RMS, not peak (a noise whoosh and a tonal hit at
the same peak are not the same loudness). Each cue lands OFFSET dB under the speech of
cut.mp4 (the mean RMS of its 50 ms windows that carry speech).
kit.json: {"speech_db": -21.3, "cut_mtime": ..., "cues": {"whoosh-in": {"attack_s": 0.17, "db": -25.3}}}
attack_s is when the cue's loudest moment hits, so plan.py can start it that much early.
Stdlib + ffmpeg. Deterministic.
"""
import array
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

SR = 48000
SPEECH_GATE_DB = -45   # a 50 ms window louder than this counts as speech
MIN_S = 0.3            # shorter files are padded with silence: the renderer drops some 2-frame clips

# name: (ffmpeg source graph with no input, dB relative to speech on the loudest 50 ms)
KIT = {
    # A card lands: filtered pink noise whose band sweeps down.
    "whoosh-in": ("anoisesrc=d=0.68:c=pink:a=1:r=48000:seed=1729,highpass=f=200,highpass=f=200,"
                  "afade=t=in:st=0:d=0.14:curve=exp,afade=t=out:st=0.22:d=0.46:curve=log,"
                  "afftfilt=real='re*exp(-pow((b/nb)/(0.14-0.112*min(1,(pts/sr)/0.62)),4))':"
                  "imag='im*exp(-pow((b/nb)/(0.14-0.112*min(1,(pts/sr)/0.62)),4))':"
                  "win_size=1024:overlap=0.75,lowpass=f=5000", -4),
    # A card leaves mid-sentence: the same air, band sweeping up.
    "whoosh-out": ("anoisesrc=d=0.60:c=pink:a=1:r=48000:seed=1729,highpass=f=200,highpass=f=200,"
                   "afade=t=in:st=0:d=0.14:curve=exp,afade=t=out:st=0.20:d=0.40:curve=log,"
                   "afftfilt=real='re*exp(-pow((b/nb)/(0.035+0.075*min(1,(pts/sr)/0.55)),4))':"
                   "imag='im*exp(-pow((b/nb)/(0.035+0.075*min(1,(pts/sr)/0.55)),4))':"
                   "win_size=1024:overlap=0.75,lowpass=f=4200", -4),
    # A scene part or logo lands: a 45 ms band-passed noise tap plus a 12 ms 1.1 kHz body.
    "pop": ("anoisesrc=d=0.06:c=white:a=1:r=48000:seed=7,highpass=f=2200,lowpass=f=7000,"
            "afade=t=out:st=0.002:d=0.043:curve=exp[n];"
            "sine=f=1100:d=0.06:sample_rate=48000,afade=t=out:st=0.001:d=0.012:curve=exp,volume=0.6[b];"
            "[n][b]amix=inputs=2:normalize=0,afade=t=in:st=0:d=0.001", -4),   # -6 measured as not heard in renders
    # A big number lands: air swelling into a soft 200 Hz body at 0.5 s.
    "hit": ("anoisesrc=d=0.7:c=pink:a=1:r=48000:seed=1729,highpass=f=900,highpass=f=900,"
            "lowpass=f=5000,lowpass=f=5000,"
            "aeval='val(0)*(0.26*pow(min(1\\,t/0.5)\\,2)+0.85*gt(t\\,0.5)*(1-exp(-(t-0.5)*200))"
            "*exp(-(t-0.5)*40))'[air];"
            "aevalsrc='gt(t\\,0.5)*sin(2*PI*200*(t-0.5))*(1-exp(-(t-0.5)*170))*exp(-(t-0.5)*26)'"
            ":d=0.7:s=48000[body];"
            "[air][body]amix=inputs=2:weights=1 0.60:normalize=0,highpass=f=130,highpass=f=130,"
            "lowpass=f=6000,afade=t=in:st=0:d=0.06:curve=exp,afade=t=out:st=0.61:d=0.09:curve=log", -4),
    # A zoom punch: a short noise rise that snaps into a 150 Hz thump at 0.2 s.
    "zoom": ("anoisesrc=d=0.4:c=pink:a=1:r=48000:seed=31,highpass=f=400,lowpass=f=4000,"
             "aeval='val(0)*(pow(min(1\\,t/0.2)\\,3)*exp(-max(0\\,t-0.2)*28))'[air];"
             "aevalsrc='gt(t\\,0.2)*sin(2*PI*150*(t-0.2))*(1-exp(-(t-0.2)*300))*exp(-(t-0.2)*30)'"
             ":d=0.4:s=48000[body];"
             "[air][body]amix=inputs=2:weights=1 0.5:normalize=0,highpass=f=90,"
             "afade=t=out:st=0.32:d=0.08:curve=log", -5),
}


def channels(src):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                          "stream=channels", "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout
    return int(out.strip() or 1)


def pcm(src=None, graph=None):
    """Mono float samples at SR: a media file's (L+R)/2, or a generated ffmpeg graph."""
    if graph:
        args = ["-filter_complex", graph]
    else:
        # not ffmpeg's -ac 1 alone: it reads a dual-mono stereo file 3 dB hot
        args = ["-i", str(src), "-vn"] + (["-af", "pan=mono|c0=0.5*c0+0.5*c1"] if channels(src) > 1 else [])
    raw = subprocess.run(["ffmpeg", "-v", "error", *args, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    x = array.array("f")
    x.frombytes(raw)
    return x


def windows(x, step=0.05):
    w = int(step * SR)
    return [math.sqrt(sum(v * v for v in x[i:i + w]) / w) for i in range(0, max(1, len(x) - w + 1), w // 4 or 1)]


def db(v):
    return 20 * math.log10(max(v, 1e-9))


def loudest50(x):
    return db(max(windows(x)))


def speech_db(video):
    """Mean power of the 50 ms windows that carry speech, in dBFS."""
    x = pcm(video)
    w = int(0.05 * SR)
    rms = [math.sqrt(sum(v * v for v in x[i:i + w]) / w) for i in range(0, len(x) - w, w)]
    loud = [r for r in rms if db(r) > SPEECH_GATE_DB]
    if not loud:
        sys.exit(f"ERROR: no speech found in {video}")
    return db(math.sqrt(sum(r * r for r in loud) / len(loud)))


def attack(x):
    """Seconds to the loudest 10 ms: where the cue's hit is heard."""
    r = windows(x, 0.01)
    return round(r.index(max(r)) * int(0.01 * SR) // 4 / SR + 0.005, 3)


def write(path, x, gain, nch=2):
    peak = db(max(abs(v) for v in x) * gain)
    assert peak < -1.0, f"{path.name}: peak {peak:.1f} dBFS would clip"
    y = array.array("h")
    for v in x:
        s = int(max(-1.0, min(1.0, v * gain)) * 32767)
        y.extend((s,) * nch)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(nch)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(y.tobytes())


def build(edit_dir, speech=None):
    edit_dir = Path(edit_dir)
    cut = edit_dir / "cut.mp4"
    speech = speech_db(cut) if speech is None else speech
    # Same channel count as the cut: the renderer spreads a mono file over stereo 3 dB down,
    # so a stereo cue over a mono cut would land 3 dB louder than measured here.
    nch = min(2, channels(cut)) if cut.exists() else 2
    out = edit_dir / ".sfx"
    out.mkdir(exist_ok=True)
    cues = {}
    for name, (graph, offset) in KIT.items():
        x = pcm(graph=graph)
        x.extend([0.0] * max(0, int(MIN_S * SR) - len(x)))
        target = speech + offset
        write(out / f"{name}.wav", x, 10 ** ((target - loudest50(x)) / 20), nch)
        cues[name] = {"attack_s": attack(x), "db": round(target, 1)}
        print(f".sfx/{name}.wav  {len(x) / SR:.2f} s  loudest 50 ms {target:.1f} dBFS  hit at {cues[name]['attack_s']} s")
    kit = {"speech_db": round(speech, 1), "cut_mtime": cut.stat().st_mtime if cut.exists() else 0, "cues": cues}
    (out / "kit.json").write_text(json.dumps(kit, indent=1))
    print(f"speech {speech:.1f} dBFS; cues sit {-min(o for _, o in KIT.values())}-{-max(o for _, o in KIT.values())} dB under it")
    return kit


def kit(edit_dir):
    """kit.json, built first when missing or older than cut.mp4."""
    p, cut = Path(edit_dir) / ".sfx" / "kit.json", Path(edit_dir) / "cut.mp4"
    if p.exists():
        k = json.loads(p.read_text())
        if not cut.exists() or k.get("cut_mtime", 0) >= cut.stat().st_mtime:
            return k
    return build(edit_dir)


def demo():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        k = build(d, speech=-21.0)
        for name, (_, offset) in KIT.items():
            x = pcm(Path(d) / ".sfx" / f"{name}.wav")
            got = loudest50(x)
            assert abs(got - (-21.0 + offset)) < 1.0, (name, got)
            assert 0 <= k["cues"][name]["attack_s"] < 0.7, (name, k["cues"][name])
        assert k["cues"]["pop"]["attack_s"] < 0.03 and k["cues"]["hit"]["attack_s"] > 0.45, k
        # speech_db on a known tone: a -20 dBFS RMS sine reads -20
        tone = Path(d) / "tone.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=300:d=1:sample_rate=48000",
                        "-af", "volume=-10dB", str(tone)], check=True)
        s = speech_db(tone)
        want = db(0.125 / math.sqrt(2)) - 10   # ffmpeg's sine is 1/8 full scale
        assert abs(s - want) < 0.5, (s, want)
    print("demo ok")


MUSIC_UNDER_DB = 18     # the bed's level under the speech in the gaps, when the creator measured none
DUCK_DB = -9            # and a further dip while he speaks (product-video sound.duck)


def music(edit_dir, track=None, mood="linear", under_db=None):
    """edits/NAME/.sfx/music.wav: the user's track (product.py music writes audio/track.wav) or a bed generated
    for this cut (product-video sound.py, nothing to licence), the cut's length, under_db under the speech,
    ducked DUCK_DB more under every word, faded out over the last 2 s. Needs numpy (the venv)."""
    import numpy as np
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "product-video" / "scripts"))
    import sound
    edit_dir = Path(edit_dir)
    cut = edit_dir / "cut.mp4"
    length = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(cut)],
                                  capture_output=True, text=True).stdout)
    bed = sound.read_audio(edit_dir / track, length) if track else sound.compose(mood, length)[0][:, :int(length * sound.SR)]
    vo = sound.read_audio(cut, length)
    rms = lambda x: float(np.sqrt(np.mean(x ** 2)) or 1e-9)  # noqa: E731
    under = MUSIC_UNDER_DB if under_db is None else abs(under_db)
    bed = bed * 10 ** ((speech_db(cut) - under - db(rms(bed))) / 20)
    bed = sound.duck(bed, vo, DUCK_DB)
    f = int(min(2.0, length / 5) * sound.SR)
    bed[:, -f:] *= np.linspace(1, 0, f) ** 1.5
    (edit_dir / ".sfx").mkdir(exist_ok=True)
    out = edit_dir / ".sfx" / "music.wav"
    sound.write_wav(out, bed)
    print(f"{out}: {'track ' + str(track) if track else 'generated (' + mood + ')'}, {under} dB under the speech, "
          f"{-DUCK_DB} dB more under each word")
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
    elif len(sys.argv) == 3 and sys.argv[1] == "build":
        build(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "music":
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument("cmd")
        ap.add_argument("edit")
        ap.add_argument("--track", help="a file in the edit folder, e.g. audio/track.wav (product.py music)")
        ap.add_argument("--mood", default="linear", help="the generated bed's mood (product-video sound.py MOODS)")
        ap.add_argument("--under-db", type=float, help=f"dB under the speech (default: the creator's sound.music.level_db, else {MUSIC_UNDER_DB})")
        a = ap.parse_args()
        st = Path(a.edit) / "style.json"
        lvl = a.under_db
        if lvl is None and st.exists():
            from plan import took
            sty = json.loads(st.read_text())
            lvl = ((sty.get("sound") or {}).get("music") or {}).get("level_db") if took(sty, "sound") else None
        music(a.edit, a.track, a.mood, lvl)
    else:
        sys.exit(__doc__)
