#!/usr/bin/env python3
"""Learn how the user cuts from one raw take and the version they posted, and save it as their taste.

    python3 learn.py <raw take> <posted cut> [--out DIR] [--engine whisper|crisper|scribe] [--dry-run]
    python3 learn.py demo                       self-check (made-up word lists, no audio)

Each input is a video or audio file, or a transcript JSON already made by the cut skill's transcribe.py
(saves a second transcription). Both are transcribed into --out (default edits/learn-<raw name>/) and
reused on a re-run. The words are lined up, then it measures:

  pauses     the gap the posted cut left where the raw take paused (0.3 s or more) -> cut.max_pause
  breaths    how many of those pauses were tightened, and how many left whole
  retakes    a line said twice: which take the posted cut kept (last, first, both, neither)
  fillers    "um"/"uh" kept or cut -> cut.keep_fillers; "like" / "you know" / "i mean" kept or cut
  FALSE CUTS words the posted cut kept that our default cut removes (fillers, earlier takes, alternate
             hooks). Each one is a good take our first edit would destroy.
  missed     words the posted cut removed that our default cut keeps (their taste we do not cut yet)

Writes learn.json in --out, then the settings into the user's taste with the counts as the rule text
(lib/ai_editor/taste.py add): only what was measured often enough, and only what differs from the default.
--dry-run measures and prints without saving. Exit codes: 0 ok, 1 error, 2 usage
"""
import argparse
import difflib
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CUT = HERE.parents[1] / "cut" / "scripts"
sys.path.insert(0, str(CUT))
sys.path.insert(0, str(HERE.parents[2] / "lib"))
import retakes  # noqa: E402
from textnorm import canon_src, nwords  # noqa: E402
from ai_editor import taste  # noqa: E402

PAUSE_S = 0.3        # a raw gap this long is a pause the cut had to decide on
TIGHTENED = 0.7      # a posted gap under this share of the raw one was tightened
MIN_PAUSES, MIN_RETAKES, MIN_FILLERS = 5, 2, 3   # fewer than this: too little to learn from
SOFT = {"like", "you know", "i mean"}


def words_of(payload):
    return [w for w in (payload["words"] if isinstance(payload, dict) else payload) if w.get("type", "word") == "word"]


def keyed(words):
    """[(canonical token, indexes of the words it came from)]: numbers and contractions folded like verify
    does, so "fifteen hundred" (two words) is one token "1500" owned by both."""
    flat, owner = [], []
    for i, w in enumerate(words):
        for x in nwords(w["text"]):
            flat.append(x)
            owner.append(i)
    c = canon_src(flat)
    ends = [k for _, k in c[1:]] + [len(flat)]
    return [(t, sorted(set(owner[k:max(e, k + 1)]))) for (t, k), e in zip(c, ends)]


def align(raw, pub):
    """{raw word index: posted word index} for every raw word the posted cut kept."""
    a, b = keyed(raw), keyed(pub)
    sm = difflib.SequenceMatcher(a=[t for t, _ in a], b=[t for t, _ in b], autojunk=False)
    match = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            for i in a[blk.a + k][1]:
                match.setdefault(i, b[blk.b + k][1][0])
    return match


def default_cut(raw):
    """What our cut removes with no taste saved: every candidate the cut code removes on its own or
    with the usual answer (last take wins). Soft fillers and unfinished lines are a judgement call: left out."""
    out = []
    for c in retakes.find(raw):
        hard = c["kind"] in ("filler", "audio_event") and not c["questions"]
        if hard or c["kind"] == "alt_hook" or "keeper_at" in c:
            out.append(c)
    return out


def runs(idx):
    """Consecutive indexes as [(first, last)]."""
    out = []
    for i in sorted(idx):
        if out and i == out[-1][1] + 1:
            out[-1][1] = i
        else:
            out.append([i, i])
    return out


def say(raw, a, b):
    return " ".join(w["text"].strip() for w in raw[a:b + 1])


def measure(raw, pub):
    match = align(raw, pub)
    kept = set(match)
    m = {"raw_words": len(raw), "posted_words": len(pub), "kept_words": len(kept)}

    gaps = []   # (raw gap, posted gap) at every raw pause both sides of which the posted cut kept, joined
    for i in range(len(raw) - 1):
        g = raw[i + 1]["start"] - raw[i]["end"]
        if g >= PAUSE_S and i in match and i + 1 in match and match[i + 1] == match[i] + 1:
            j = match[i]
            gaps.append((g, max(0.0, pub[j + 1]["start"] - pub[j]["end"])))
    left = sorted(p for _, p in gaps)
    m["pauses"] = {"count": len(gaps), "tightened": sum(p < TIGHTENED * g for g, p in gaps),
                   "median_left_s": round(statistics.median(left), 3) if left else None,
                   "longest_left_s": round(left[-1], 3) if left else None}

    cands = retakes.find(raw)
    share = lambda a, b: sum(i in kept for i in range(a, b + 1)) / (b - a + 1)  # noqa: E731
    rt = {"last": 0, "first": 0, "both": 0, "neither": 0}
    for c in cands:
        if "keeper_at" not in c:
            continue
        a, b = c["cut"]
        j = b + 1
        first, second = share(a, b) >= 0.5, share(j, min(len(raw) - 1, j + b - a)) >= 0.5
        rt[{(False, True): "last", (True, False): "first", (True, True): "both"}.get((first, second), "neither")] += 1
    m["retakes"] = rt

    hard = [c for c in cands if c["kind"] == "filler" and not c["questions"]]
    soft = [c for c in cands if c["kind"] == "filler" and c["questions"]]
    m["fillers"] = {"hard": {"count": len(hard), "kept": sum(share(*c["cut"]) >= 0.5 for c in hard)},
                    "soft": {"count": len(soft), "kept": sum(share(*c["cut"]) >= 0.5 for c in soft)}}

    ours = default_cut(raw)
    ours_idx = {i for c in ours for i in range(c["cut"][0], c["cut"][1] + 1)}
    false = [c for c in ours if any(i in kept for i in range(c["cut"][0], c["cut"][1] + 1))]
    m["false_cuts"] = {"words": len(ours_idx & kept),
                       "where": [{"kind": c["kind"], "at": round(c["at"], 2), "text": c["text"][:80]} for c in false]}
    missed = runs(set(range(len(raw))) - kept - ours_idx)
    m["missed"] = {"words": sum(b - a + 1 for a, b in missed),
                   "longest": [{"at": round(raw[a]["start"], 2), "text": say(raw, a, b)[:80]}
                               for a, b in sorted(missed, key=lambda r: r[0] - r[1])[:5]]}
    return m


def settings(m):
    """[(section, rule, setting, value)] worth saving: measured often enough, and not already the default."""
    out = []
    p = m["pauses"]
    if p["count"] >= MIN_PAUSES and p["median_left_s"] is not None:
        # the cut tightens a pause over max_pause to two thirds of it, so their median gap is two thirds of it
        mp = round(min(0.6, max(0.08, 1.5 * p["median_left_s"])), 2)
        out.append(("cut", f"Pauses left at about {p['median_left_s']:.2f} s, as in your own edit "
                           f"({p['tightened']} of {p['count']} pauses tightened)", "cut.max_pause", mp))
    rt = m["retakes"]
    n = sum(rt.values())
    if n >= MIN_RETAKES and rt["first"] > rt["last"] and rt["first"] >= rt["both"]:
        out.append(("cut", f"A line said twice keeps the first take, not the last (you kept the first "
                           f"{rt['first']} of {n} times)", None, None))
    elif n >= MIN_RETAKES and rt["both"] > rt["last"] and rt["both"] > rt["first"]:
        out.append(("cut", f"A line said twice keeps both takes unless one breaks off (you kept both "
                           f"{rt['both']} of {n} times)", None, None))
    h, s = m["fillers"]["hard"], m["fillers"]["soft"]
    if h["count"] >= MIN_FILLERS and h["kept"] * 3 >= h["count"] * 2:
        out.append(("cut", f"Keep the ums and uhs (you kept {h['kept']} of {h['count']})", "cut.keep_fillers", True))
    if s["count"] >= MIN_FILLERS and s["kept"] * 3 >= s["count"] * 2 and not (out and out[-1][2] == "cut.keep_fillers"):
        out.append(("cut", f"Keep \"like\", \"you know\" and \"i mean\" (you kept {s['kept']} of {s['count']})", None, None))
    return out


def transcript(src, out, engine):
    """A transcript JSON as is; a media file through the cut skill's transcribe.py, once."""
    src = Path(src)
    if src.suffix.lower() == ".json":
        return words_of(json.loads(src.read_text()))
    if not out.exists():
        cmd = [sys.executable, str(CUT / "transcribe.py"), str(src), str(out)] + (["--engine", engine] if engine else [])
        if subprocess.run(cmd).returncode != 0:
            sys.exit(f"ERROR: could not transcribe {src}")
    return words_of(json.loads(out.read_text()))


def report(m, saved):
    p, rt, f = m["pauses"], m["retakes"], m["fillers"]
    lines = [f"words      raw {m['raw_words']}, posted {m['posted_words']}, lined up {m['kept_words']}",
             f"pauses     {p['count']} measured, {p['tightened']} tightened (breaths cut), "
             f"median left {p['median_left_s']} s, longest {p['longest_left_s']} s",
             f"retakes    last take {rt['last']}, first take {rt['first']}, both {rt['both']}, neither {rt['neither']}",
             f"fillers    um/uh kept {f['hard']['kept']} of {f['hard']['count']}; "
             f"like/you know/i mean kept {f['soft']['kept']} of {f['soft']['count']}",
             f"FALSE CUTS {m['false_cuts']['words']} word(s) you kept that our default cut removes"]
    lines += [f"  {x['at']:7.2f}s [{x['kind']}] {x['text']}" for x in m["false_cuts"]["where"][:10]]
    lines += [f"missed     {m['missed']['words']} word(s) you cut that our default cut keeps"]
    lines += [f"  {x['at']:7.2f}s {x['text']}" for x in m["missed"]["longest"]]
    lines += [f"saved      {s}" for s in saved] or ["saved      nothing: too little measured, or it matches the default"]
    return "\n".join(lines)


def learn(raw, pub, dry=False):
    m = measure(raw, pub)
    saved = []
    for section, rule, setting, value in settings(m):
        if not dry:
            taste.add(section, rule, setting, value)
        saved.append(f"{rule}" + (f" [{setting} = {json.dumps(value)}]" if setting else "") + (" (dry run)" if dry else ""))
    return m, saved


def demo():
    def take(text, gaps=None, t=0.0):
        out = []
        for k, w in enumerate(text.split()):
            t += (gaps or {}).get(k, 0.05)
            out.append({"text": w, "start": round(t, 3), "end": round(t + 0.3, 3), "type": "word"})
            t += 0.3
        return out
    # raw: pauses between sentences and before an "um" they keep; a line said twice where they keep the first take
    raw_text = ("so here is um the thing. it works every time. and you ship it. "
                "the model reads the file. the model reads the whole file. then it writes code. um done")
    raw = take(raw_text, {3: 0.6, 6: 0.9, 10: 0.7, 14: 1.0, 19: 0.8, 25: 0.6, 29: 0.7})
    # posted: kept both ums and the first take, cut the second take and "then"; pauses left at 0.2 s
    kept_text = "so here is um the thing. it works every time. and you ship it. the model reads the file. it writes code. um done"
    pub = take(kept_text, {3: 0.2, 6: 0.2, 10: 0.2, 14: 0.2, 19: 0.2, 22: 0.2})
    m = measure(raw, pub)
    assert m["kept_words"] == len(pub), m
    assert m["pauses"]["count"] >= 5 and m["pauses"]["median_left_s"] == 0.2 and m["pauses"]["tightened"] == m["pauses"]["count"], m["pauses"]
    assert m["retakes"]["first"] == 1, m["retakes"]
    assert m["fillers"]["hard"] == {"count": 2, "kept": 2}, m["fillers"]
    fc = {x["kind"] for x in m["false_cuts"]["where"]}
    assert m["false_cuts"]["words"] >= 2 and {"filler", "retake"} <= fc, m["false_cuts"]
    assert m["missed"]["words"] == 7 and m["missed"]["longest"][0]["text"] == "the model reads the whole file. then", m["missed"]
    # numbers spelled differently by two transcriptions still line up
    assert align(take("it costs fifteen hundred dollars"), take("it costs 1,500 dollars")).keys() == {0, 1, 2, 3, 4}
    rules = settings(m)
    assert ("cut.max_pause", 0.3) in [(s, v) for _, _, s, v in rules], rules   # 0.2 s left = 2/3 of 0.3
    assert not any(s == "cut.keep_fillers" for _, _, s, _ in rules)           # 2 ums: too few to learn from
    m["fillers"]["hard"] = {"count": 4, "kept": 3}
    m["retakes"] = {"last": 0, "first": 2, "both": 0, "neither": 0}
    rules = settings(m)
    assert any(s == "cut.keep_fillers" for _, _, s, _ in rules) and any("first take" in r for _, r, _, _ in rules), rules
    # saved into the taste with counts; a second run updates the same rules, never a copy
    with tempfile.TemporaryDirectory() as d:
        taste.HOME = Path(d)
        for _ in range(2):
            m2, saved = learn(raw, pub)
        rs = taste.load_rules()
        assert len(rs) == 1 and rs[0]["setting"] == "cut.max_pause" and len(rs[0]["corrections"]) == 2, rs
        assert taste.read_json() == {"cut": {"max_pause": 0.3}} and "pauses tightened" in rs[0]["rule"], taste.read_json()
        assert "Pauses left" in taste.md_path().read_text()
        _, saved = learn(raw, pub, dry=True)
        assert saved and "dry run" in saved[0]
        # the CLI end to end on transcript JSONs, dry run: nothing written
        (Path(d) / "raw.json").write_text(json.dumps(raw))
        (Path(d) / "pub.json").write_text(json.dumps({"words": pub}))
        r = subprocess.run([sys.executable, __file__, str(Path(d) / "raw.json"), str(Path(d) / "pub.json"),
                            "--out", str(Path(d) / "o"), "--dry-run"], capture_output=True, text=True,
                           env=dict(os.environ, AI_EDITOR_HOME=str(Path(d) / "h")))
        assert r.returncode == 0 and "FALSE CUTS" in r.stdout and not (Path(d) / "h").exists(), (r.stdout, r.stderr)
        assert json.loads((Path(d) / "o" / "learn.json").read_text())["retakes"]["first"] == 1
    print("learn ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("raw")
    ap.add_argument("posted")
    ap.add_argument("--out", default=None)
    ap.add_argument("--engine", default=None, help="transcribe.py engine (default: its own, local Whisper with no key)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = Path(a.out or Path("edits") / f"learn-{Path(a.raw).stem.lower()}")
    out.mkdir(parents=True, exist_ok=True)
    raw = transcript(a.raw, out / "raw.words.json", a.engine)
    pub = transcript(a.posted, out / "posted.words.json", a.engine)
    if not raw or not pub:
        sys.exit("ERROR: a transcript has no words")
    m, saved = learn(raw, pub, a.dry_run)
    (out / "learn.json").write_text(json.dumps({**m, "saved": saved}, indent=1))
    print(report(m, saved))
    print(out / "learn.json")


if __name__ == "__main__":
    main()
