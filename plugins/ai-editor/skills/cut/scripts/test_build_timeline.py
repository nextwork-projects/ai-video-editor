#!/usr/bin/env python3
"""Self-check for build_timeline.py. No ffmpeg, no fixtures, runs in milliseconds.

    python3 test_build_timeline.py
"""
import contextlib
import io
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
    noise, d = B.derive_noise_db(levels(-13, -28))              # music bed: quietest 10% + 1/3
    assert d["bed"] == -27.6 and noise == round(-27.6 + 14.6 / 3, 1), d
    noise, d = B.derive_noise_db(levels(-13, -28, n_speech=50, n_floor=4000))
    assert d["speech"] == -13 and d["bed"] == -27.6, d           # busy floor is not speech
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
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):  # the expected ERROR stays out of the CI log
            B.resolve_spans([{"text": "the thing about", "kind": "false_start"}], toks)
        raise AssertionError("an ambiguous span must fail")
    except SystemExit:
        assert "appears 2x" in err.getvalue(), err.getvalue()


def test_frames_and_retime():
    cuts = [{"start": 1.01, "end": 1.99, "_next": 2.0}, {"start": 3.0, "end": math.inf}]
    frames = B.kept_frames(cuts, 30, 4.0)
    assert frames == [[0, 30], [60, 90]], frames                 # floor start, clamp end
    spans = [{"start": s / 30, "end": e / 30} for s, e in frames]
    w = B.retime([{"text": "a", "start": 0.2, "end": 0.5, "type": "word"},
                  {"text": "gone", "start": 1.2, "end": 1.5, "type": "word"},
                  {"text": "b", "start": 2.1, "end": 2.4, "type": "word"}], spans)
    assert [x["text"] for x in w] == ["a", "b"] and abs(w[1]["start"] - 1.1) < 1e-6, w


def test_stretched_label_is_not_clipped():
    """Whisper labels "if" 0.4-3.4 s, 3 s ahead of its audio at 3.45 s (the sample take's "If" at
    173 s). Judged on that label, the pause cut "clips" a word the render plays, and the paper edit
    sends the model into raising --pad for nothing. Fitted to the audio, nothing is clipped and the
    paper edit plays exactly the words words.json keeps."""
    import preview_cut as P
    words = [{"text": "so", "start": 0.0, "end": 0.3, "type": "word"},
             {"text": "if", "start": 0.4, "end": 3.4, "type": "word"},
             {"text": "you", "start": 3.6, "end": 3.9, "type": "word"}]
    loud = [(0.0, 0.3), (3.45, 3.55), (3.6, 3.9)]
    lvl = [-20.0 if any(a <= i * B.RMS_WIN_S < b for a, b in loud) else -60.0 for i in range(int(4.5 / B.RMS_WIN_S))]

    def paper(ws):
        cuts = B.merge(B.silence_cuts(ws, 0.15, 0.1, [(0.3, 3.45)]) + B.lead_trail_cuts(ws, 4.5, 0.1))
        B.enforce_splice_budget(cuts, ws, [], 0.15, lvl, -40.0)
        spans = [{"start": a / 30, "end": b / 30} for a, b in B.kept_frames(cuts, 30, 4.5)]
        md = P.paper_edit(P.label(ws, [], spans), [], 4.5, sum(s["end"] - s["start"] for s in spans))
        return md, [w["text"] for w in B.retime(ws, spans)]

    assert "CLIPPED" in paper(words)[0]                       # the raw label: a false CLIPPED
    labels = B.fit_labels(words, lvl, -40.0)
    assert list(labels) == [1] and 3.4 <= labels[1][0] < labels[1][1] <= 3.6, labels
    md, kept = paper(B.apply_labels(words, labels))
    assert "CLIPPED" not in md and kept == ["so", "if", "you"], (md, kept)
    assert md.split("## What plays")[1].split("## Cuts")[0].split("\n")[-3] == "so if you", md


def test_label_after_the_previous_words_tail():
    """The real take: "you" 192.63-192.75 then "if" labelled 192.75-193.41. The audio: "you" sounds to
    192.86, silence to 193.30, "if" at 193.30. Fitted from its label start, "if" landed on the tail of
    "you", fell in the pause cut and was CLIPPED whatever the --pad. It is fitted after the silence."""
    words = [{"text": "you", "start": 192.63, "end": 192.75, "type": "word"},
             {"text": "if", "start": 192.75, "end": 193.41, "type": "word"},
             {"text": "you", "start": 193.41, "end": 193.51, "type": "word"}]
    loud = [(192.58, 192.86), (193.30, 193.60)]
    lvl = [-20.0 if any(a <= i * B.RMS_WIN_S < b for a, b in loud) else -60.0 for i in range(int(194 / B.RMS_WIN_S))]
    got = B.fit_labels(words, lvl, -40.0)
    assert list(got) == [1] and 193.2 <= got[1][0] < got[1][1] <= 193.41, got


def test_no_head_sliver():
    """decisions.json started [0.0, 0.033] then [0.434, ...]: a one-frame flash, then a jump."""
    frames = B.kept_frames([{"start": 0.05, "end": 0.43}, {"start": 3.0, "end": math.inf}], 30, 4.0)
    assert frames == [[13, 90]], frames
    assert B.kept_frames([{"start": 0.5, "end": 1.0}], 30, 2.0) == [[0, 15], [30, 60]]   # a real head stays


def test_hidden_repeat_is_listed_and_shown():
    """The sample: Whisper labels "content" 117.07-119.01 s over "and to break down competitor ads and"
    (spoken 117.7-119.4 s). A label holding far more speech than its word is listed, re-transcribed
    when possible, and otherwise marked in transcript.txt. A long label over silence is not listed."""
    import retakes as R
    import transcribe as T
    words = [{"text": "ads", "start": 116.6, "end": 117.0, "type": "word"},
             {"text": "content", "start": 117.07, "end": 119.01, "type": "word"},
             {"text": "strategies", "start": 119.5, "end": 120.0, "type": "word"},
             {"text": "if", "start": 121.0, "end": 124.0, "type": "word"}]   # 3 s label, 0.1 s of audio
    loud = [(116.6, 117.0), (117.7, 119.4), (119.5, 120.0), (123.9, 124.0)]
    lvl = [-20.0 if any(a <= i * B.RMS_WIN_S < b for a, b in loud) else -60.0 for i in range(int(125 / B.RMS_WIN_S))]
    assert [i for i, _ in B.unheard(words, lvl, -40.0)] == [1], B.unheard(words, lvl, -40.0)

    old = B.window_rms_db, B.derive_noise_db
    B.window_rms_db, B.derive_noise_db = (lambda src: lvl), (lambda lv: (-40.0, {}))
    try:
        asked = []
        def again(s, e):
            asked.append((s, e))
            return [{"text": x, "start": 117.7 + n * 0.2, "end": 117.85 + n * 0.2, "type": "word"}
                    for n, x in enumerate("and to break down competitor ads and content".split())]
        got = [w["text"] for w in T.recheck("a.wav", T.with_spacing([dict(w) for w in words]), again)
               if w["type"] == "word"]
        assert asked == [(117.07, 119.01)] and got[1:9] == "and to break down competitor ads and content".split(), got
        kept = [w for w in T.recheck("a.wav", T.with_spacing([dict(w) for w in words]), lambda s, e: [])
                if w["type"] == "word"]
        assert kept[1]["unheard_s"] > 1.0 and "unheard_s" not in kept[3], kept
        view = R.text_view(kept)
        assert "content [1.3s of speech not transcribed]" in view, view
        assert "not transcribed" not in R.say(kept, 0, 3)    # Jev's questions and spans see the plain words
        one = T.recheck("a.wav", T.with_spacing([dict(w) for w in words]),
                        lambda s, e: [{"text": "content", "start": 117.7, "end": 119.4, "type": "word"}])
        assert not any(w.get("unheard_s") for w in one), one    # heard again as one word: drawn out
    finally:
        B.window_rms_db, B.derive_noise_db = old


def test_splice_never_reaches_a_removed_word():
    """Speech runs 1.0-2.0 s with no gap ("the the thing"); the first "the" (1.0-1.3) is removed and the
    keep starts at 1.3, inside speech. Walking back to the quiet would bring the stumble back, so the
    edge stays and is listed. Without the removed word it moves to the quiet at 1.0 s."""
    lvl = [-20.0 if 1.0 <= i * B.RMS_WIN_S < 2.0 else -70.0 for i in range(int(3 / B.RMS_WIN_S))]
    frames = [[0, 15], [39, 90]]
    got, moved, left = B.fix_splices(frames, 30, lvl, -40.0, 90, removed=[(1.0, 1.3)])
    assert got == frames and left == [1.3] and not moved, (got, moved, left)
    got, moved, left = B.fix_splices(frames, 30, lvl, -40.0, 90)
    assert got == [[0, 15], [30, 90]] and moved == [(1.3, 1.0)] and not left, (got, moved, left)
    assert B.fix_splices(got, 30, lvl, -40.0, 90)[1:] == ([], [])      # a second pass finds nothing


if __name__ == "__main__":
    test_derive()
    test_audible_end()
    test_splice_budget()
    test_spans()
    test_frames_and_retime()
    test_stretched_label_is_not_clipped()
    test_label_after_the_previous_words_tail()
    test_no_head_sliver()
    test_hidden_repeat_is_listed_and_shown()
    test_splice_never_reaches_a_removed_word()
    print("all ok")
