#!/usr/bin/env python3
"""Measured voice/cadence metrics off Scribe word timings.

Everything here is computed, never estimated. Agents label beats; this file
supplies the numbers they label against, so no timing is ever eyeballed.

  python3 scripts/metrics.py <handle> [--id ID]

Exit codes: 0 ok - 1 error - 2 usage
"""
import argparse
import json
import re
import statistics as st
import sys
from collections import Counter
from pathlib import Path

OUT_ROOT = Path.cwd() / "creator-teardowns"

FILLERS = {"um", "uh", "like", "you know", "i mean", "literally", "actually",
           "basically", "so", "right", "okay", "just"}
HYPE = {"unlock", "leverage", "seamless", "elevate", "empower", "delve",
        "dive", "supercharge", "gamechanger", "insane", "crazy", "wild"}


def load(p):
    d = json.loads(p.read_text(encoding="utf-8"))
    return d, [w for w in d["words"] if w.get("type") == "word"]


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def video_metrics(d, words, meta):
    dur = d.get("audio_duration_secs") or 0
    text = d.get("text", "")
    toks = re.findall(r"[a-z']+", text.lower())
    n = len(toks) or 1
    sents = sentences(text)
    slens = [len(re.findall(r"[a-z']+", s.lower())) for s in sents] or [0]

    # Pauses: gap between consecutive words. This is the cadence signal that
    # cleaned transcripts (TikTok captions, Whisper) throw away entirely.
    gaps = [round(b["start"] - a["end"], 3) for a, b in zip(words, words[1:])]
    gaps = [g for g in gaps if g > 0]
    long_pauses = [g for g in gaps if g >= 0.30]

    # WPM over each third, to show whether they accelerate into the body.
    thirds = []
    if dur:
        for i in range(3):
            lo, hi = dur * i / 3, dur * (i + 1) / 3
            c = sum(1 for w in words if lo <= w["start"] < hi)
            thirds.append(round(c / (dur / 3) * 60))

    counts = Counter(toks)
    you = counts["you"] + counts["your"] + counts["yours"]
    i_ = counts["i"] + counts["my"] + counts["me"] + counts["mine"]
    we = counts["we"] + counts["our"] + counts["us"]

    ngrams = Counter()
    for k in (3, 4, 5):
        for j in range(len(toks) - k + 1):
            ngrams[" ".join(toks[j:j + k])] += 1

    return {
        "id": meta["id"],
        "views": meta.get("view_count"),
        "vs_median": meta.get("vs_median"),
        "duration_s": round(dur, 1),
        "words": len(toks),
        "wpm": round(len(toks) / dur * 60) if dur else 0,
        "wpm_thirds": thirds,
        "first_word_at": round(words[0]["start"], 2) if words else None,
        "sentences": len(sents),
        "sent_len_median": round(st.median(slens), 1),
        "sent_len_range": [min(slens), max(slens)],
        "pause_median_ms": round(st.median(gaps) * 1000) if gaps else 0,
        "pauses_over_300ms": len(long_pauses),
        "pauses_per_min": round(len(long_pauses) / dur * 60, 1) if dur else 0,
        "longest_pause_s": round(max(gaps), 2) if gaps else 0,
        "filler_rate_per_100w": round(
            sum(counts[f] for f in FILLERS if " " not in f) / n * 100, 1),
        "hype_hits": {h: counts[h] for h in HYPE if counts[h]},
        "you": you, "i": i_, "we": we,
        "you_per_100w": round(you / n * 100, 1),
        "top_ngrams": [g for g, c in ngrams.most_common(400) if c >= 2][:12],
        "hook_text": " ".join(w["text"] for w in words if w["start"] < 3.0),
        "close_text": " ".join(w["text"] for w in words if w["start"] > dur - 6),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--id")
    a = ap.parse_args()

    outdir = OUT_ROOT / a.handle
    meta = json.loads((outdir / "videos.json").read_text(encoding="utf-8"))
    by_id = {v["id"]: v for v in meta["videos"]}
    tdir = outdir / "transcripts"

    paths = [tdir / f"{a.id}.json"] if a.id else sorted(tdir.glob("*.json"))
    rows = []
    for p in paths:
        if not p.exists():
            sys.exit(f"missing {p}")
        d, words = load(p)
        if not words:
            print(f"skip {p.stem}: no words", file=sys.stderr)
            continue
        rows.append(video_metrics(d, words, by_id[p.stem]))

    rows.sort(key=lambda r: -(r["views"] or 0))
    (outdir / "metrics.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    hdr = f"{'views':>10} {'sec':>5} {'wpm':>4} {'thirds':>14} {'hook@':>6} {'sent':>5} {'paus/m':>7} {'fill':>5} {'you%':>5}  id"
    print(hdr)
    for r in rows:
        print(f"{(r['views'] or 0):>10,} {r['duration_s']:>5} {r['wpm']:>4} "
              f"{str(r['wpm_thirds']):>14} {r['first_word_at']:>6} "
              f"{r['sent_len_median']:>5} {r['pauses_per_min']:>7} "
              f"{r['filler_rate_per_100w']:>5} {r['you_per_100w']:>5}  {r['id']}")
    print(f"\n-> {outdir / 'metrics.json'}")


if __name__ == "__main__":
    main()
