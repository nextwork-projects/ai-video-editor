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
variance and are listed separately, not as errors.

Writes <edit_dir>/cut.transcript.json (reused while it is newer than cut.mp4). Exit 0 clean, 1 missing or survived words.
"""
import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_timeline import is_kept  # noqa: E402
from textnorm import load_words, transcript_words  # noqa: E402

FILLERS = {"um", "uh", "umm", "uhh", "hmm", "mm", "ah", "er", "erm"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edit_dir")
    ap.add_argument("--engine", default="auto")
    a = ap.parse_args()
    d = Path(a.edit_dir)

    spans = json.loads((d / "decisions.json").read_text())
    raw = [w for w in load_words(d / "words.raw.json") if w.get("type") == "word"]
    expected = transcript_words([w for w in raw if is_kept(w, spans)])
    removed = set(transcript_words([w for w in raw if not is_kept(w, spans)]))

    ft = d / "cut.transcript.json"
    fresh = ft.exists() and ft.stat().st_mtime > (d / "cut.mp4").stat().st_mtime
    r = subprocess.CompletedProcess([], 0) if fresh else subprocess.run([sys.executable, str(HERE / "transcribe.py"), str(d / "cut.mp4"), str(ft),
                        "--engine", a.engine])
    if r.returncode:
        sys.exit(1)
    actual = transcript_words([w for w in load_words(ft) if w.get("type") == "word"])

    sm = difflib.SequenceMatcher(a=expected, b=actual, autojunk=False)
    missing, extra, runs = [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            missing += [(i, expected[i]) for i in range(i1, i2)]
        if tag in ("insert", "replace"):
            extra += actual[j1:j2]
            runs.append((j1, j2))

    def fragment(tok):
        return tok in removed or any(len(tok) >= 2 and len(r) >= 2 and
                                     (r.startswith(tok) or tok.startswith(r)) for r in removed)

    noise = [t for _, t in missing if t in FILLERS] + [t for t in extra if t in FILLERS]
    missing = [(i, t) for i, t in missing if t not in FILLERS]
    survived = [t for t in extra if t not in FILLERS and fragment(t)]

    print(f"expected {len(expected)} words, heard {len(actual)}, match {sm.ratio() * 100:.1f}%")
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
    other = [t for t in extra if t not in FILLERS and not fragment(t)]
    if other:
        print(f"\nnote: {len(other)} other token(s) differ (transcriber variance): {' '.join(other[:15])}")
    if noise:
        print(f"note: fillers that differ between passes: {len(noise)}")

    rep = json.loads((d / "report.json").read_text())
    check = [c for c in rep["model_cuts"] if c["confidence"] == "low" or c["kind"] == "redundant"]
    if check:
        print(f"\nSPOT-CHECK {len(check)} judgement call(s):")
        for c in check:
            print(f"  {c['start']:7.2f}s [{c['kind']}] {c['evidence'][:60]!r}")
    print("\nOK: the render matches the intended cut." if not (missing or survived) else "")
    return 1 if (missing or survived) else 0


if __name__ == "__main__":
    sys.exit(main())
