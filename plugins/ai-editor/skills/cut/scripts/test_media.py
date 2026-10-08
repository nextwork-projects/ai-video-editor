#!/usr/bin/env python3
"""Self-checks for the cut on real (synthetic) media. Needs ffmpeg; about ten seconds.

    python3 test_media.py

render.py frame counts: "span N: X frames, wanted X+1" must never happen.

1. Property: over thousands of random spans, frame rates (23.976, 25, 29.97, 30, 60), container
   timescales (1/600 like a phone, 1/1000 like webm, 1/90000, 1/fps) with round or floor
   timestamps and a video stream that starts 0-2 frames in, the trim window selects exactly
   e - s frames.
2. Real files: tiny clips whose audio outlasts the video, whose video starts late, at 29.97, 25
   and 60 fps, cut with random spans by build_timeline's own frame code and rendered by render.py.
3. Music bed: speech-like tones (one word barely over the music) on a constant music bed. The
   pauses between words are tightened and no word loses a frame.
"""
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_timeline as B  # noqa: E402
import render as R  # noqa: E402

RATES = [F(24000, 1001), F(25), F(30000, 1001), F(30), F(60), F(60000, 1001)]


def test_window_property():
    rnd = random.Random(7)
    for _ in range(4000):
        rate = rnd.choice(RATES)
        tb = rnd.choice([600, 1000, 90000, rate.numerator])   # ticks per second
        snap = rnd.choice([round, math.floor, math.ceil])
        lead = rnd.choice([0, 1, 2])
        n = rnd.randrange(30, 2000)
        pts = [snap((lead + k) / rate * tb) / tb for k in range(n)]   # exact, then the container's tick
        fps, vstart = float(rate), pts[0]    # what ffprobe reports
        s = rnd.randrange(0, n - 1)
        e = rnd.randrange(s + 1, n + 1)
        t0, t1 = R.video_window(s, e, fps, vstart)
        t0, t1 = float(f"{max(0.0, t0):.6f}"), float(f"{t1:.6f}")   # as render.py formats them
        got = sum(t0 <= p < t1 for p in pts)
        assert got == e - s, (fps, tb, snap.__name__, vstart, s, e, got)


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, a)], check=True)


def test_real_renders():
    rnd = random.Random(3)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        clips = {
            # audio runs past the video: the format duration says one more frame than exists
            "longaudio.mov": ["-f", "lavfi", "-i", "testsrc2=s=64x64:r=30000/1001:d=3", "-f", "lavfi",
                              "-i", "sine=d=3.2", "-video_track_timescale", "600"],
            # the video stream starts two frames in
            "late.mp4": ["-itsoffset", "0.08", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=25:d=3",
                         "-f", "lavfi", "-i", "sine=d=3.1"],
            "sixty.mp4": ["-f", "lavfi", "-i", "testsrc2=s=64x64:r=60:d=2", "-f", "lavfi", "-i", "sine=d=2"],
        }
        for name, args in clips.items():
            src = d / name
            ff(*args, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", src)
            fps, dur, total = B.probe(src)
            for run in range(2):
                cuts, t = [], rnd.uniform(0.1, 0.4)
                while True:
                    a = t + rnd.uniform(0.2, 0.6)
                    b = a + rnd.uniform(0.05, 0.3)
                    if b > total / fps - 0.2:
                        break
                    cuts.append({"start": a, "end": b})
                    t = b
                frames = B.kept_frames(cuts, fps, dur, total)
                assert frames[-1][1] == total, (name, frames, total)    # the last span runs to the end
                ed = d / f"{src.stem}-{run}"
                ed.mkdir()
                (ed / "report.json").write_text(json.dumps({"fps": fps, "frames": frames}))
                # the second run renders through a temp folder with a ' in its name
                quoted = d / "it's tmp"
                quoted.mkdir(exist_ok=True)
                env = dict(os.environ, **({"TMPDIR": str(quoted), "TMP": str(quoted), "TEMP": str(quoted)} if run else {}))
                r = subprocess.run([sys.executable, HERE / "render.py", src, ed, "--no-hw"],
                                   capture_output=True, text=True, env=env)
                assert r.returncode == 0, (name, frames, r.stdout[-400:], r.stderr[-400:])


# (start, end, amplitude): speech-like tones; the 4th word sits only a few dB over the bed
WORDS = [(0.40, 0.80, 0.4), (0.90, 1.35, 0.4), (2.05, 2.50, 0.4), (2.60, 3.10, 0.08),
         (3.90, 4.30, 0.4), (4.42, 4.95, 0.4), (5.80, 6.30, 0.4)]


def test_music_bed():
    tone = "+".join(f"between(t,{a},{b})*{amp}*sin(2*PI*{180 + 40 * i}*t)*(0.65+0.35*sin(2*PI*6*t))"
                    for i, (a, b, amp) in enumerate(WORDS))
    bed = "0.035*sin(2*PI*110*t)+0.035*sin(2*PI*164.8*t)+0.02*sin(2*PI*220*t)"   # a held chord
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, ed = d / "bed.mp4", d / "edit"
        ed.mkdir()
        ff("-f", "lavfi", "-i", "testsrc2=s=64x64:r=30:d=7", "-f", "lavfi",
           "-i", f"aevalsrc='{tone}+{bed}':s=48000:d=7", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-shortest", src)
        (ed / "words.raw.json").write_text(json.dumps(
            [{"text": f"w{i}", "start": a, "end": b, "type": "word"} for i, (a, b, _) in enumerate(WORDS)]))
        r = subprocess.run([sys.executable, HERE / "build_timeline.py", src, ed, "--max-pause", "0.3"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "music bed" in r.stdout, r.stdout
        spans = json.loads((ed / "decisions.json").read_text())
        for a, b, _ in WORDS:    # every word whole inside one kept span
            assert any(s["start"] <= a + 1e-6 and b <= s["end"] + 1e-6 for s in spans), (a, b, spans)
        kept = sum(s["end"] - s["start"] for s in spans)
        assert kept < 7 - 2.0, (kept, spans)      # the 0.7-0.85 s pauses were tightened



def test_scribe_network_error_is_a_message():
    """No network: a one-line message and exit 3, not a traceback."""
    import contextlib
    import io
    import urllib.error
    import transcribe as T
    old = T.urllib.request.urlopen
    def down(*a, **k):
        raise urllib.error.URLError("nodename nor servname provided")
    T.urllib.request.urlopen = down
    try:
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"
            wav.write_bytes(b"RIFF")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                try:
                    T.run_scribe(wav, "k", "en")
                    raise AssertionError("no exit")
                except SystemExit as e:
                    assert e.code == 3, e.code
            assert "unreachable" in err.getvalue() and "--engine whisper" in err.getvalue(), err.getvalue()
    finally:
        T.urllib.request.urlopen = old


def test_recheck_prints_one_line():
    """Re-transcribed stretches end in one plain line, not one line per word with its timings."""
    import contextlib
    import io
    import build_timeline as B
    import transcribe as T
    words = [{"text": "one", "start": 1.0, "end": 2.0, "type": "word"}, {"text": "AI", "start": 3.0, "end": 4.5, "type": "word"}]
    saved = B.window_rms_db, B.derive_noise_db, B.unheard
    B.window_rms_db, B.derive_noise_db = (lambda wav: []), (lambda lvl: (-40.0, {}))
    B.unheard = lambda toks, lvl, noise: [(0, 1.0), (1, 1.2)]
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            got = T.recheck("a.wav", words, lambda a, b: [{"text": "not", "start": a, "end": a + 0.3, "type": "word"},
                                                         {"text": "a", "start": a + 0.4, "end": b, "type": "word"}] if a == 1.0 else [])
    finally:
        B.window_rms_db, B.derive_noise_db, B.unheard = saved
    lines = out.getvalue().splitlines()
    assert lines == ["2 place(s) where one word held more speech: 1 heard again, 1 marked in transcript.txt"], lines
    assert [w["text"] for w in got if w["type"] == "word"] == ["not", "a", "AI"], got


if __name__ == "__main__":
    test_recheck_prints_one_line()
    test_window_property()
    test_real_renders()
    test_music_bed()
    test_scribe_network_error_is_a_message()
    print("all ok")
