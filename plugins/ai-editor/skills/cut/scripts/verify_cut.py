#!/usr/bin/env python3
"""Re-transcribe cut.mp4 and diff it against the words the cut meant to keep.

    python verify_cut.py <edit_dir> [--engine auto|whisper|scribe]

Run it with the venv python (it calls transcribe.py). Use the same engine as the
raw transcript, or the diff fills with spelling noise.

  MISSING   a kept word is not in the render: a boundary landed too tight.
            Fix: raise --pad, or narrow the span that ate it, rebuild, re-render.
  SURVIVED  a removed word is still audible, including a fragment ("open" left
            from a sliced "opening"): a boundary landed too loose.

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
from build_timeline import is_kept, retime  # noqa: E402
from textnorm import load_words, pair_by_time, timed_words, transcript_words  # noqa: E402

FILLERS = {"um", "uh", "umm", "uhh", "hmm", "mm", "ah", "er", "erm"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edit_dir")
    ap.add_argument("--engine", default="auto")
    a = ap.parse_args()
    d = Path(a.edit_dir)

    spans = json.loads((d / "decisions.json").read_text())
    raw = [w for w in load_words(d / "words.raw.json") if w.get("type") == "word"]
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
    return report(d, expected, actual, removed, *pair_by_time(exp, act))


def report(d, expected, actual, removed, same, differ, gone, new):
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
    if heard:
        print(f"\nHEARD DIFFERENTLY ({sum(heard.values())}), the same time in the cut spelled another way by the second "
              "pass (a misheard name, not a cut error; captions take the cut's spelling):")
        print("  " + ", ".join(f"{k} x{n}" if n > 1 else k for k, n in heard.items()))
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


if __name__ == "__main__":
    sys.exit(main())
