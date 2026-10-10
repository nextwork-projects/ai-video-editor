#!/usr/bin/env python3
"""YouTube chapters timed off the final cut, checked against YouTube's rules.

    python3 chapters.py edits/NAME [--chapters edits/NAME/chapters.json] [--intro "text"]
    python3 chapters.py demo        self-check, offline

chapters.json is Claude's pick from the transcript, one entry per section:
    [["the words spoken where the section starts", "chapter title"], ...]
Each phrase is found in cut.transcript.json (else words.json), after the previous one, so a
re-cut re-times every chapter. The first chapter is always 0:00.

Writes edits/NAME/chapters.txt ("0:00 title" lines). With --intro, also description.txt: the intro,
a blank line, the chapters; without it an older description.txt is removed (its chapters would be stale).
Exit 1 on a failed check, writing nothing: fewer than 3 chapters, the first not at 0:00, a chapter
under 10 s, times out of order, a < or > (YouTube rejects them in descriptions).
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MIN_LEN = 10.0
norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())


def stamp(s):
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def chapter_times(words, chapters):
    """Each phrase -> the cut time of its first word, searched after the previous one."""
    toks = [norm(w["text"]) for w in words]
    out, i0 = [], 0
    for n, (phrase, title) in enumerate(chapters):
        want = [t for t in (norm(x) for x in phrase.split()) if t]
        hit = next((i for i in range(i0, len(toks) - len(want) + 1) if toks[i:i + len(want)] == want), None)
        if hit is None:
            sys.exit(f'ERROR: chapter phrase not found in the cut (after the previous chapter): "{phrase}"')
        out.append((0.0 if n == 0 else words[hit]["start"], title))
        i0 = hit + len(want)
    return out


def problems(times, total):
    p = []
    if len(times) < 3:
        p.append("YouTube needs at least 3 chapters")
    if times and times[0][0] != 0:
        p.append("the first chapter must be 0:00")
    ends = [t for t, _ in times[1:]] + [total]
    for (t, title), e in zip(times, ends):
        if e <= t:
            p.append(f'"{title}" is out of order; times must go up')
        elif e - t < MIN_LEN:
            p.append(f'"{title}" is {e - t:.1f} s; YouTube needs {MIN_LEN:.0f} s per chapter')
        if re.search("[<>]", title):
            p.append(f'"{title}" has a < or >; YouTube rejects them')
    return p


def duration(edit, words):
    """cut.mp4's length; the last word's end when ffprobe or the file is missing."""
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                            str(edit / "cut.mp4")], capture_output=True, text=True)
        return float(r.stdout.strip())
    except (OSError, ValueError):
        return max((w["end"] for w in words), default=0.0)


def load_words(edit):
    p = next((edit / f for f in ("cut.transcript.json", "words.json") if (edit / f).exists()), None)
    if p is None:
        sys.exit(f"ERROR: no cut.transcript.json or words.json in {edit}. Run the cut skill first.")
    data = json.loads(p.read_text(encoding="utf-8"))
    return [w for w in (data["words"] if isinstance(data, dict) else data) if w.get("type", "word") == "word"]


def write(edit, words, chapters, total, intro=None):
    times = chapter_times(words, chapters)
    text = "\n".join(f"{stamp(t)} {title}" for t, title in times) + "\n"
    p = problems(times, total)
    if p:                     # a failed check writes nothing: no file YouTube would reject is left to paste
        return text, p
    (edit / "chapters.txt").write_text(text, encoding="utf-8")
    if intro:
        (edit / "description.txt").write_text(f"{intro.strip()}\n\n{text}", encoding="utf-8")
    else:
        (edit / "description.txt").unlink(missing_ok=True)
    return text, p


def demo():
    W = [{"text": t, "start": s, "end": s + 0.2} for t, s in
         [("Hi", 0.2), ("So", 30.0), ("firstly,", 30.2), ("here", 30.5), ("Now", 61.0), ("here's", 61.2)]]
    T = chapter_times(W, [["Hi", "Intro"], ["So firstly", "What it is"], ["now here's", "When not to"]])
    assert [(round(t, 1), n) for t, n in T] == [(0.0, "Intro"), (30.0, "What it is"), (61.0, "When not to")], T
    assert problems(T, 90) == []
    assert any("10 s" in x for x in problems([(0, "a"), (5, "b"), (20, "c")], 60))
    assert any("at least 3" in x for x in problems([(0, "a"), (20, "b")], 60))
    assert any("0:00" in x for x in problems([(1, "a"), (20, "b"), (40, "c")], 60))
    assert any("order" in x for x in problems([(0, "a"), (40, "b"), (20, "c")], 60))
    assert any("<" in x for x in problems([(0, "a <b>"), (20, "b"), (40, "c")], 60))
    assert any("10 s" in x for x in problems(T, 65)), "the last chapter runs to the end of the video"
    assert stamp(0) == "0:00" and stamp(605.9) == "10:05" and stamp(3725) == "1:02:05"
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "words.json").write_text(json.dumps(W + [{"text": " ", "start": 61.4, "end": 61.5, "type": "spacing"}]), encoding="utf-8")
        words = load_words(d)
        assert len(words) == 6
        text, p = write(d, words, [["Hi", "Intro"], ["So firstly", "What it is"], ["now here's", "When not to"]], 90, "A plain intro.")
        assert text == "0:00 Intro\n0:30 What it is\n1:01 When not to\n" and p == []
        assert (d / "description.txt").read_text(encoding="utf-8") == "A plain intro.\n\n" + text
        assert round(duration(d, words), 2) == 61.4, "no cut.mp4: the last word's end"
        # a passing run without --intro removes the old description.txt (its chapters would be stale)
        write(d, words, [["Hi", "Intro"], ["So firstly", "Start"], ["now here's", "End"]], 90)
        assert (d / "chapters.txt").read_text(encoding="utf-8").endswith("1:01 End\n") and not (d / "description.txt").exists()
        # a failed check writes nothing: the last good chapters.txt stays, no description.txt appears
        _, p = write(d, words, [["Hi", "Intro"], ["So firstly", "Too short"]], 90, "intro")
        assert p and (d / "chapters.txt").read_text(encoding="utf-8").endswith("1:01 End\n") and not (d / "description.txt").exists()
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit")
    ap.add_argument("--chapters", help="default: edits/NAME/chapters.json")
    ap.add_argument("--intro", help="a plain description draft; writes description.txt")
    a = ap.parse_args()
    edit = Path(a.edit)
    cp = Path(a.chapters) if a.chapters else edit / "chapters.json"
    if not cp.exists():
        sys.exit(f'ERROR: no {cp}. Write it first: [["words spoken where the section starts", "title"], ...]')
    words = load_words(edit)
    text, p = write(edit, words, json.loads(cp.read_text(encoding="utf-8")), duration(edit, words), a.intro)
    print(text, end="")
    if not p:
        print(f"-> {edit / 'chapters.txt'}" + (f" and {edit / 'description.txt'}" if a.intro else ""))
    for x in p:
        print("FAIL ", x)
    if p:
        print("nothing written: fix chapters.json and run again")
    sys.exit(1 if p else 0)


if __name__ == "__main__":
    main()
