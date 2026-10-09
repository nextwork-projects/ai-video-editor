#!/usr/bin/env python3
"""Re-transcribe cut.mp4 and diff it against the words the cut meant to keep.

    python verify_cut.py <edit_dir> [--engine auto|whisper|scribe]
    python verify_cut.py demo        self-check (offline)

Run it with the venv python (it calls transcribe.py). Use the same engine as the
raw transcript, or the diff fills with spelling noise.

  MISSING   a kept word is not in the render: a boundary landed too tight.
            Fix: raise --pad, or narrow the span that ate it, rebuild, re-render.
  SURVIVED  a removed word is still audible, including a fragment ("open" left
            from a sliced "opening"): a boundary landed too loose. Each line gives
            its time in the cut, its time in the source and the span to add.

  DOUBLED   the same word or two-word pair said twice back to back in the render ("now, now
            one thing"): a stumble every check above passes. Not an error: keep the natural
            ones ("very, very"); for a stumble, add the span it prints (cuts the first one).

Fillers ("um", "uh") that come and go between two passes are transcriber
variance and are listed separately, not as errors. So is a kept word the second pass
spelled differently at the same time in the cut ("Jev" heard as "Jeff"): HEARD
DIFFERENTLY, matched by time (textnorm.pair_by_time), never MISSING.

Writes <edit_dir>/cut.transcript.json (reused while it is newer than cut.mp4). Exit 0 clean, 1 missing or survived words.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_timeline import is_kept, load_fitted, retime  # noqa: E402
from textnorm import load_words, pair_by_time, timed_words, transcript_words  # noqa: E402

FILLERS = {"um", "uh", "umm", "uhh", "hmm", "mm", "ah", "er", "erm"}


def to_source(t, spans):
    """A time on the cut -> the same moment in the source (decisions.json spans are the kept parts)."""
    off = 0.0
    for s in spans:
        n = s["end"] - s["start"]
        if t <= off + n:
            return round(s["start"] + max(0.0, t - off), 2)
        off += n
    return round(spans[-1]["end"], 2) if spans else round(t, 2)


def span_to_add(raw, a, b):
    """The spans.json entry for the source words heard between a and b (source seconds), or None."""
    ws = [w for w in raw if a - 0.1 <= (w["start"] + w["end"]) / 2 <= b + 0.1]
    if not ws:
        return None
    return {"text": " ".join(w["text"].strip() for w in ws), "kind": "retake", "after": round(max(0.0, ws[0]["start"] - 0.05), 2)}


def doubled(act):
    """[(j, n)]: act[j:j+n] said again right after, n = 1 or 2 words, fillers ignored.
    act is [(token, start, end)] from textnorm.timed_words."""
    toks = [t for t, _, _ in act]
    out = []
    for j in range(len(toks)):
        for n in (2, 1):
            if toks[j:j + n] == toks[j + n:j + 2 * n] and toks[j] not in FILLERS \
                    and not any(j < k + m and k < j + n for k, m in out):
                out.append((j, n))
                break
    return out


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("edit_dir")
    ap.add_argument("--engine", default="auto")
    a = ap.parse_args()
    d = Path(a.edit_dir)

    spans = json.loads((d / "decisions.json").read_text())
    raw = [w for w in load_fitted(d) if w.get("type") == "word"]
    exp = timed_words(retime(raw, spans))      # the kept words, timed on the cut
    expected = [t for t, _, _ in exp]
    removed = set(transcript_words([w for w in raw if not is_kept(w, spans)]))

    ft = d / "cut.transcript.json"
    fresh = ft.exists() and ft.stat().st_mtime > (d / "cut.mp4").stat().st_mtime
    r = subprocess.CompletedProcess([], 0) if fresh else subprocess.run([sys.executable, str(HERE / "transcribe.py"), str(d / "cut.mp4"), str(ft),
                        "--engine", a.engine])
    if r.returncode:
        sys.exit(1)
    act = timed_words(load_words(ft))
    actual = [t for t, _, _ in act]
    return report(d, expected, actual, removed, *pair_by_time(exp, act), act=act, spans=spans, raw=raw)


def report(d, expected, actual, removed, same, differ, gone, new, act=None, spans=None, raw=None):
    missing = [(i, expected[i]) for i in gone]
    extra = [actual[j] for j in new]
    runs = []
    for j in sorted(new):          # runs of consecutive heard-only tokens, for the context lines
        if runs and runs[-1][1] == j:
            runs[-1][1] = j + 1
        else:
            runs.append([j, j + 1])
    heard = {}
    for i, js in differ:
        key = f"{expected[i]} -> {' '.join(actual[j] for j in js)}"
        heard[key] = heard.get(key, 0) + 1

    def fragment(tok):
        return tok in removed or any(len(tok) >= 2 and len(r) >= 2 and
                                     (r.startswith(tok) or tok.startswith(r)) for r in removed)

    noise = [t for _, t in missing if t in FILLERS] + [t for t in extra if t in FILLERS]
    missing = [(i, t) for i, t in missing if t not in FILLERS]
    survived = [t for t in extra if t not in FILLERS and fragment(t)]

    print(f"expected {len(expected)} words, heard {len(actual)}, match {len(same) / max(1, len(expected)) * 100:.1f}%")
    if missing:
        print(f"\nMISSING ({len(missing)}), with the kept words around each:")
        for i, t in missing[:30]:
            print(f"  {t!r:14} ... {' '.join(expected[max(0, i - 4):i + 5])} ...")
    if survived:
        print(f"\nSURVIVED ({len(survived)}), heard in the render where nothing was expected [in brackets].")
        print("A real survivor is a repeat or a stumble. Clean speech here means the raw transcript misheard it:")
        for j1, j2 in runs:
            if any(fragment(t) for t in actual[j1:j2] if t not in FILLERS):
                print(f"  ... {' '.join(actual[max(0, j1 - 4):j1])} [{' '.join(actual[j1:j2])}] "
                      f"{' '.join(actual[j2:j2 + 4])} ...")
                if act and spans:
                    a, b = act[j1][1], act[j2 - 1][2]
                    sa, sb = to_source(a, spans), to_source(b, spans)
                    print(f"    cut {a:.2f}-{b:.2f}s = source {sa:.2f}-{sb:.2f}s")
                    add = span_to_add(raw or [], sa, sb)
                    if add:
                        print(f"    span to add, if it is a real repeat: {json.dumps(add)}")
    if heard:
        print(f"\nHEARD DIFFERENTLY ({sum(heard.values())}), the same time in the cut spelled another way by the second "
              "pass (a misheard name, not a cut error; captions take the cut's spelling):")
        print("  " + ", ".join(f"{k} x{n}" if n > 1 else k for k, n in heard.items()))
    dbl = doubled(act or [])
    if dbl:
        print(f"\nDOUBLED ({len(dbl)}), the same words twice in a row in the render. Keep natural ones "
              "(\"very, very\"); for a stumble add the span to cut the first one:")
        for j, n in dbl:
            print(f"  {act[j][1]:7.2f}s  ... {' '.join(actual[max(0, j - 3):j])} [{' '.join(actual[j:j + n])}] "
                  f"{' '.join(actual[j + n:j + 2 * n + 3])} ...")
            if spans:
                add = span_to_add(raw or [], to_source(act[j][1], spans), to_source(act[j + n - 1][2], spans))
                if add:
                    print(f"    span to add: {json.dumps(dict(add, kind='false_start'))}")
    other = [t for t in extra if t not in FILLERS and not fragment(t)]
    if other:
        print(f"\nnote: {len(other)} other token(s) differ (transcriber variance): {' '.join(other[:15])}")
    if noise:
        print(f"note: fillers that differ between passes: {len(noise)}")

    rep = json.loads((d / "report.json").read_text()) if (d / "report.json").exists() else {"model_cuts": []}
    check = [c for c in rep["model_cuts"] if c["confidence"] == "low" or c["kind"] == "redundant"]
    if check:
        print(f"\nSPOT-CHECK {len(check)} judgement call(s):")
        for c in check:
            print(f"  {c['start']:7.2f}s [{c['kind']}] {c['evidence'][:60]!r}")
    print("\nOK: the render matches the intended cut." if not (missing or survived) else "")
    return 1 if (missing or survived) else 0


def demo():
    import contextlib
    import io
    spans = [{"start": 0.0, "end": 2.0}, {"start": 5.0, "end": 8.0}]
    assert to_source(1.0, spans) == 1.0 and to_source(2.5, spans) == 5.5 and to_source(9, spans) == 8.0
    raw = [{"text": t, "start": s, "end": s + 0.3, "type": "word"} for t, s in
           (("less", 0.8), ("than", 1.2), ("cents", 1.6), ("and", 4.6), ("and", 5.05), ("to", 5.4))]
    act = [("less", 0.8, 1.1), ("than", 1.2, 1.5), ("cents", 1.6, 1.9), ("and", 2.0, 2.2), ("and", 2.05, 2.35),
           ("to", 2.4, 2.7)]
    expected = ["less", "than", "cents", "and", "to"]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = report(Path("."), expected, [t for t, _, _ in act], {"and"}, [0, 1, 2, 3, 5], [], [], [4],
                    act=act, spans=spans, raw=raw)
    txt = out.getvalue()
    assert rc == 1 and "SURVIVED (1)" in txt, txt
    assert "cut 2.05-2.35s = source 5.05-5.35s" in txt, txt
    assert '"text": "and", "kind": "retake", "after": 5.0' in txt, txt
    act = [(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate("so now now one thing very very um um and the the".split())]
    assert [(act[j][0], n) for j, n in doubled(act)] == [("now", 1), ("very", 1), ("the", 1)], doubled(act)
    act = [(t, i * 0.3, i * 0.3 + 0.25) for i, t in enumerate("on the on the platform".split())]
    assert doubled(act) == [(0, 2)], doubled(act)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        report(Path("."), [], [], set(), [], [], [], [], act=[("now", 4.0, 4.2), ("now", 4.3, 4.5), ("one", 4.6, 4.8)],
               spans=[{"start": 10.0, "end": 20.0}],
               raw=[{"text": "now", "start": 14.0, "end": 14.2}, {"text": "now,", "start": 14.3, "end": 14.5}])
    assert "DOUBLED (1)" in out.getvalue() and '"text": "now"' in out.getvalue(), out.getvalue()
    print("verify_cut ok")


if __name__ == "__main__":
    sys.exit(main())
