#!/usr/bin/env python3
"""Self-check for build_timeline.py. No ffmpeg, no fixtures, runs in milliseconds.

    python3 test_build_timeline.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_timeline as B  # noqa: E402


def levels(speech_db, floor_db, n_speech=200, n_floor=800):
    return [speech_db + 0.4] * n_speech + [floor_db + 0.4] * n_floor


def test_derive():
    assert B.derive_noise_db(levels(-14, -64))[0] == -40.0      # quiet room: speech - 26
    assert B.derive_noise_db(levels(-21, -65))[0] == -47.0      # quieter speaker moves it
    noise, d = B.derive_noise_db(levels(-13, -28))              # no separation: refuse
    assert noise is None and "15 dB apart" in d["reason"], d
    noise, d = B.derive_noise_db(levels(-13, -28, n_speech=50, n_floor=4000))
    assert noise is None, d                                     # busy floor is not speech
    assert B.derive_noise_db(levels(-11, -38))[0] == -32.0      # never under floor + 6


def test_audible_end():
    lvl = [-20.0] * 10 + [-60.0] * 10
    assert abs(B.audible_end(lvl, -40.0, 0.34) - 0.20) < 1e-9
    assert B.audible_end(lvl, -40.0, 0.10) == 0.10
    assert B.audible_end([-60.0] * 10, -40.0, 0.10) is None


def splice(left, right, next_dur, budget=0.18):
    words = [{"start": 0.0, "end": 1.0, "text": "prev"}, {"start": 1.5, "end": 1.6, "text": "flub"},
             {"start": 3.0, "end": 3.0 + next_dur, "text": "next"}]
    cut = {"start": 1.0 + left, "end": 3.0 - right, "kind": "retake", "evidence": "flub",
           "confidence": "high"}
    B.enforce_splice_budget([cut], words, [{"start": 1.5, "end": 1.6}], budget)
    return (cut["start"] - 1.0) + (3.0 - cut["end"]), cut


def test_splice_budget():
    total, cut = splice(0.125, 0.125, 0.06)
    assert abs(total - 0.18) < 1e-6 and 3.0 - cut["end"] >= 0.125 - 1e-6, cut   # short word keeps runway
    assert abs(splice(0.10, 0.10, 0.30)[0] - 0.18) < 1e-6
    total, cut = splice(0.05, 0.05, 0.30)                                         # in budget: untouched
    assert abs(total - 0.10) < 1e-9 and abs(cut["start"] - 1.05) < 1e-9
    for left, right, nd in [(0.4, 0.4, 0.06), (0.02, 0.5, 0.30), (0.5, 0.02, 0.06)]:
        _, cut = splice(left, right, nd)                                          # only widens,
        assert cut["start"] <= 1.0 + left + 1e-9 and cut["end"] >= 3.0 - right - 1e-9
        assert cut["start"] > 1.0 and cut["end"] < 3.0                           # never into a word
    _, cut = splice(0.4, 1.0, 0.06, budget=0.001)
    assert 1.0 <= cut["start"] and cut["end"] <= 3.0


def test_spans():
    toks = [{"text": t, "start": i, "end": i + 0.5, "type": "word"}
            for i, t in enumerate("so the thing about the thing about ducks".split())]
    cuts = B.resolve_spans([{"text": "the thing about", "occurrence": 1, "kind": "false_start"}], toks)
    assert (cuts[0]["start"], cuts[0]["end"]) == (1, 3.5), cuts
    try:
        B.resolve_spans([{"text": "the thing about", "kind": "false_start"}], toks)
        raise AssertionError("an ambiguous span must fail")
    except SystemExit:
        pass


def test_frames_and_retime():
    cuts = [{"start": 1.01, "end": 1.99, "_next": 2.0}, {"start": 3.0, "end": math.inf}]
    frames = B.kept_frames(cuts, 30, 4.0)
    assert frames == [[0, 30], [60, 90]], frames                 # floor start, clamp end
    spans = [{"start": s / 30, "end": e / 30} for s, e in frames]
    w = B.retime([{"text": "a", "start": 0.2, "end": 0.5, "type": "word"},
                  {"text": "gone", "start": 1.2, "end": 1.5, "type": "word"},
                  {"text": "b", "start": 2.1, "end": 2.4, "type": "word"}], spans)
    assert [x["text"] for x in w] == ["a", "b"] and abs(w[1]["start"] - 1.1) < 1e-6, w


if __name__ == "__main__":
    test_derive()
    test_audible_end()
    test_splice_budget()
    test_spans()
    test_frames_and_retime()
    print("all ok")
