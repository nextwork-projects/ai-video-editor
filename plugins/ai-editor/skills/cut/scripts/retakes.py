#!/usr/bin/env python3
"""The cheap way to decide the cut: code finds the candidates, Jev judges them, Claude
reviews only what Jev was unsure of.

    python3 retakes.py text    <edit_dir>              transcript.txt, one line per phrase
    python3 retakes.py propose <edit_dir> [--force]    spans.json + review.md (needs a TypeSafe key)
    python3 retakes.py fix     <edit_dir> cloud=Claude [jiv=Jev ...]   fix misheard words

text     words.raw.json as "[start-end] words" per phrase, about a fifth of its size. Read
         this, never the raw JSON.
propose  1. Code finds every candidate: a restart (words said again within 40 s: a retake
            or a false start), an unfinished phrase followed by a pause, talking-to-self
            ("wait", "let me start again"), and soft fillers ("like", "you know").
         2. Jev judges each one in a single batched request, seeing only the words that
            candidate is about. "um"/"uh" and audio events are cut without asking.
         3. Writes spans.json (what build_timeline.py reads), review.md (only the items Jev
            was unsure of) and candidates.json (every candidate with its answers).
         Last take wins: a restart cuts the earlier attempt, unless Jev says the later one
         is the broken one; that case is never cut automatically, it goes to review.md.
         With no TypeSafe key it writes transcript.txt and candidates.md and exits 4: decide
         the cut yourself from those (references/retake-detection.md).
fix      Replaces one whole word everywhere in words.raw.json and words.json, keeping
         punctuation and timings. A misheard name costs one command, not a rewrite.

Exit codes: 0 ok, 1 error, 2 usage, 4 no TypeSafe key (fall back to deciding yourself)
"""
import argparse
import difflib
import functools
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from textnorm import load_words, nwords  # noqa: E402
from ai_editor import jev, keys  # noqa: E402

PHRASE_GAP_S = 0.5        # a silence this long ends a phrase
WINDOW_S = 40.0           # a restart this far back is still a retake
WINDOW_WORDS = 80
NEAR_WORDS = 8            # a 2-word repeat counts only this close
HARD_FILLERS = {"um", "uh", "umm", "uhh", "erm", "er", "hmm", "mm", "ah", "eh"}
SOFT_FILLERS = ["you know", "i mean", "like"]
STOP = {"a", "an", "the", "and", "or", "but", "so", "of", "to", "in", "on", "at", "it", "is",
        "i", "you", "we", "that", "this", "for", "with", "be", "was", "are", "my", "me", "if",
        "it's", "it'll", "i'm", "they", "he", "she", "do", "not", "there", "then", "just"}
META = re.compile(r"\b(wait|sorry|hold on|shoot|oops|start (?:again|over)|one more time|"
                  r"let me (?:start|do (?:that|this|it)|try|say (?:that|it))(?: (?:again|over))?|"
                  r"take two|again)\b")
# Noul bands (cookbooks/consistency_noul_cookbook.md): 0.3-0.7 is uncertain and goes to review.
CUT, SURE, UNSURE, FILLER_CUT, KEEPER_CONF = 0.7, 0.85, 0.3, 0.8, 0.6

STATE = ("Lines from the transcript of one person recording a talking-head video in a single "
         "take. Speakers often stop mid-sentence and say the line again, and the later attempt "
         "replaces the earlier one. Transcription can misspell names.")


# --- transcript ---------------------------------------------------------------

def load(d):
    return [t for t in load_words(Path(d) / "words.raw.json") if t.get("type") in ("word", "audio_event")]


def phrases(toks):
    """[(first, last)] token ranges, split at silences and sentence ends."""
    out, a = [], 0
    for i in range(1, len(toks) + 1):
        if i == len(toks) or toks[i]["start"] - toks[i - 1]["end"] >= PHRASE_GAP_S \
                or toks[i - 1]["text"].strip().endswith((".", "?", "!")):
            out.append((a, i - 1))
            a = i
    return out


def say(toks, a, b):
    return " ".join(t["text"].strip() for t in toks[a:b + 1])


def text_view(toks, name=""):
    lines = [f"# {name} {len(toks)} tokens. [start-end] seconds, then the words. "
             "(+N.Ns) = the pause before a phrase. Quote words from here in spans.json; "
             "use \"after\": <a start time> when a phrase repeats."]
    prev = None
    for a, b in phrases(toks):
        gap = toks[a]["start"] - prev if prev is not None else 0
        lines.append((f"(+{gap:.1f}s) " if gap >= 1.0 else "") +
                     f"[{toks[a]['start']:.2f}-{toks[b]['end']:.2f}] {say(toks, a, b)}")
        prev = toks[b]["end"]
    return "\n".join(lines) + "\n"


# --- candidates (code) -----------------------------------------------------------

@functools.lru_cache(maxsize=None)
def same(x, y):
    """Same word, allowing a transcriber's spelling drift on names (jev / jv)."""
    return x == y or (len(x) >= 3 and len(y) >= 2 and difflib.SequenceMatcher(a=x, b=y).ratio() >= 0.75)


def norm_seq(toks):
    """[(normalized word, token index)] with hard fillers dropped, so 'the, um, the' matches."""
    out = []
    for i, t in enumerate(toks):
        if t.get("type") != "word":
            continue
        out += [(w, i) for w in nwords(t["text"]) if w not in HARD_FILLERS]
    return out


def clauses(toks):
    """[(first, last)] token ranges: phrases, split again after , ; : and after um/uh."""
    out = []
    for a, b in phrases(toks):
        start = a
        for i in range(a, b):
            t = toks[i]["text"].strip()
            if t.endswith((",", ";", ":", "-")) or (nwords(t) and all(w in HARD_FILLERS for w in nwords(t))):
                out.append((start, i))
                start = i + 1
        out.append((start, b))
    return out


def opening(toks, a, b, n=6):
    return [w for t in toks[a:b + 1] for w in nwords(t["text"]) if w not in HARD_FILLERS][:n]


def similar_openings(x, y):
    """Do two clauses open the same way? Fuzzy on spelling, so 'jev is this new' and
    'jv is this new' match, and 'it's 40 to 200 times' matches '40 to 200 times'."""
    n = min(len(x), len(y))
    if n < 2:
        return False
    x, y = x[:n], [next((w for w in x if same(w, v)), v) for v in y[:n]]
    blocks = difflib.SequenceMatcher(a=x, b=y, autojunk=False).get_matching_blocks()
    hit = [w for bl in blocks for w in x[bl.a:bl.a + bl.size]]
    return len(hit) >= 2 and len(hit) / n >= 0.6 and (len(hit) >= 3 or any(w not in STOP for w in hit))


def restarts(toks):
    """(i, j): the attempt from token i is abandoned and started again at token j.

    1. A clause that opens like an earlier clause (within WINDOW_S): the nearest such
       clause is the abandoned attempt, cut from its start up to the new one. A line said
       four times gives three restarts, each cutting the attempt before it.
    2. Inside a clause, words said twice in a row ("people have been using it to sort
       people have been using it to sort ..."): cut the first run up to the repeat.
       The kept words read as the speaker's own, because the repeat starts with the same
       words the cut one did."""
    out, cl = [], clauses(toks)
    for bi in range(1, len(cl)):
        b0 = cl[bi][0]
        ob = opening(toks, *cl[bi])
        for ai in range(bi - 1, -1, -1):
            a0 = cl[ai][0]
            if toks[b0]["start"] - toks[a0]["start"] > WINDOW_S:
                break
            if similar_openings(opening(toks, *cl[ai]), ob):
                out.append((a0, b0))
                break
    taken = lambda x: any(i <= x < j for i, j in out)  # noqa: E731
    seq, n = norm_seq(toks), 0
    while n < len(seq):
        best = None
        for m in range(n - 1, max(-1, n - 30), -1):
            k = 0
            while n + k < len(seq) and m + k < n and seq[m + k][0] == seq[n + k][0]:
                k += 1
            content = any(w not in STOP for w, _ in seq[n:n + k])
            if k >= (2 if n - m <= NEAR_WORDS else 3) and (content or k >= 4):
                best = (m, k)
                break
        i, j = (seq[best[0]][1], seq[n][1]) if best else (None, None)
        if best and i < j and not taken(i) and not taken(j - 1):
            out.append((i, j))
            n += best[1]
        else:
            n += 1
    return sorted(out)


def find(toks):
    """Every candidate, each with the Jev questions that decide it."""
    phr = phrases(toks)
    end_of = {i: b for a, b in phr for i in range(a, b + 1)}
    cands = []

    def add(kind, a, b, qs=None, **extra):
        cands.append({"id": f"c{len(cands)}", "kind": kind, "cut": [a, b], "at": toks[a]["start"],
                      "text": say(toks, a, b), "questions": qs or {}, **extra})

    for i, j in restarts(toks):
        cid = f"c{len(cands)}"
        gap = toks[j]["start"] - toks[j - 1]["end"]
        second = say(toks, j, min(end_of[j], j + 25))
        qs = {f"{cid}_same": jev.noul(
            "Is `second_attempt` the speaker starting over on what they began in `first_attempt`, "
            "to replace it?",
            true="Yes: the second attempt says the same words or the same idea again, as a retry.",
            false="No: the second attempt moves on to new content, or repeats words on purpose "
                  "for emphasis or as a list.",
            first_attempt=say(toks, i, j - 1), second_attempt=second,
            pause_between="a long pause" if gap >= 1.0 else "a short pause" if gap >= 0.3 else "no pause")}
        add("false_start" if j - i <= 4 and gap < 1.0 else "retake",
            i, j - 1, qs, second=second, keeper_at=toks[j]["start"])

    # A fragment that is already the first attempt of a restart needs no second question.
    restarted = {c["cut"][0] for c in cands}
    # Chain ends get the keeper question: a middle attempt is replaced by a later one anyway.
    for c in cands:
        nxt = next((d for d in cands if d["kind"] in ("retake", "false_start")
                    and d["cut"][0] <= c["cut"][1] + 1 <= d["cut"][1]), None)
        if nxt is None:
            c["questions"][f"{c['id']}_keep"] = jev.choice(
                "Which attempt should stay in the finished video?",
                {"second": "`second_attempt`, the later one. Pick this unless it breaks off "
                           "unfinished or stumbles worse than the first.",
                 "first": "`first_attempt`, only if `second_attempt` breaks off unfinished or is "
                          "clearly worse."},
                first_attempt=c["text"], second_attempt=c["second"])

    for pi, (a, b) in enumerate(phr):
        words = sum(len(nwords(t["text"])) for t in toks[a:b + 1])
        if a in restarted or pi + 1 >= len(phr) or words > 8:
            continue
        if toks[b]["text"].strip().endswith((".", "?", "!")):
            continue
        na, nb = phr[pi + 1]
        cid = f"c{len(cands)}"
        add("false_start", a, b, {f"{cid}_frag": jev.noul(
            "Does the speaker leave `fragment` unfinished and abandon it, then start a "
            "different sentence in `next`?",
            true="Yes: `fragment` breaks off and `next` does not complete it.",
            false="No: `next` carries on and completes the thought in `fragment`.",
            fragment=say(toks, a, b), next=say(toks, na, min(nb, na + 20)))})

    seq = [(w, i) for i, t in enumerate(toks) for w in nwords(t["text"])]
    flat = " ".join(w for w, _ in seq)
    for rx, kind in ((META, "meta"),) + tuple((re.compile(rf"\b{f}\b"), "filler") for f in SOFT_FILLERS):
        for m in rx.finditer(flat):
            w0 = flat[:m.start()].count(" ")
            w1 = w0 + m.group(0).count(" ")
            a, b = seq[w0][1], seq[w1][1]
            ctx = say(toks, max(0, a - 12), min(len(toks) - 1, b + 12))
            cid = f"c{len(cands)}"
            q = (jev.noul("In `text`, are the words `words` the speaker talking to themself about "
                          "the recording (like \"wait\", \"sorry\", \"let me start again\"), not "
                          "to the viewer?", text=ctx, words=m.group(0)) if kind == "meta" else
                 jev.noul("In `text`, is `word` a hesitation filler that can be removed without "
                          "changing what is said?", text=ctx, word=m.group(0)))
            add(kind, a, b, {f"{cid}_{kind}": q})

    for i, t in enumerate(toks):
        ws = nwords(t["text"])
        if t.get("type") == "audio_event":
            add("audio_event", i, i)
        elif ws and all(w in HARD_FILLERS for w in ws):
            add("filler", i, i)
    return sorted(cands, key=lambda c: c["cut"][0])


# --- decisions (code over Jev's answers) ----------------------------------------

def decide(cands, answers):
    """(cuts, review). A cut is {a, b, kind, confidence, note}. Review lists every item
    Jev was unsure of, cut or not, for Claude to look at."""
    cuts, review = [], []
    for c in cands:
        qs = {q.rsplit("_", 1)[1]: answers.get(q) for q in c["questions"]}
        c["answers"] = {k: v for k, v in qs.items() if v}
        if not qs:   # um, uh, audio events: always cut
            cuts.append({**c, "confidence": "high", "note": "hesitation" if c["kind"] == "filler" else ""})
            continue
        p = next(v["noul"] for k, v in qs.items() if k != "keep")
        keep = qs.get("keep")
        if c["kind"] == "filler":
            if p >= FILLER_CUT:
                cuts.append({**c, "confidence": "high", "note": f"filler, Jev {p:.2f}"})
            continue
        why = f"Jev {p:.2f}"
        if keep:
            why += f", keeps the {keep['choice']} attempt ({keep['confidence']:.2f})"
        if p >= CUT and keep and keep["choice"] == "first":
            review.append({**c, "p": p, "action": "kept: Jev says the later attempt is the broken one"})
            continue
        if p >= CUT and (not keep or keep["confidence"] >= KEEPER_CONF):
            note = (f"keeper at {c['keeper_at']:.1f}s, " if "keeper_at" in c else "") + why
            cuts.append({**c, "confidence": "high" if p >= SURE else "medium", "note": note})
        elif p >= 0.5 and (not keep or keep["choice"] == "second"):
            cuts.append({**c, "confidence": "low", "note": why})
            review.append({**c, "p": p, "action": "cut, low confidence"})
        elif p >= UNSURE or (p >= CUT and keep):
            review.append({**c, "p": p, "action": "kept"})
    return cuts, review


def to_spans(cuts, toks):
    """Merge overlapping or touching cuts and quote them for build_timeline.py."""
    rank = {"retake": 4, "false_start": 3, "meta": 2, "filler": 1, "audio_event": 0}
    level = {"low": 0, "medium": 1, "high": 2}
    merged = []
    for c in sorted(cuts, key=lambda c: c["cut"][0]):
        a, b = c["cut"]
        if merged and a <= merged[-1]["b"] + 1:
            m = merged[-1]
            m["b"] = max(m["b"], b)
            m["kind"] = max(m["kind"], c["kind"], key=rank.get)
            m["confidence"] = min(m["confidence"], c["confidence"], key=level.get)
            m["notes"].append(c["note"])
        else:
            merged.append({"a": a, "b": b, "kind": c["kind"], "confidence": c["confidence"],
                           "notes": [c["note"]]})
    spans = []
    for m in merged:
        a, b = m["a"], m["b"]
        while a < b and not nwords(toks[a]["text"]):
            a += 1
        while b > a and not nwords(toks[b]["text"]):
            b -= 1
        if not nwords(toks[a]["text"]):
            continue
        sp = {"text": say(toks, a, b), "kind": m["kind"], "after": max(0.0, round(toks[a]["start"] - 0.001, 3))}
        if m["confidence"] != "high":
            sp["confidence"] = m["confidence"]
        note = "; ".join(n for n in m["notes"] if n)
        if note:
            sp["note"] = note[:160]
        spans.append(sp)
    return spans


def review_md(review, toks):
    if not review:
        return "# Review\n\nNothing uncertain. Read paper-edit.md once, then render.\n"
    lines = ["# Review", "", f"{len(review)} item(s) Jev was unsure of. For each: leave it, or edit "
             "spans.json (add, delete or narrow the entry). Everything else is decided.", ""]
    for r in review:
        lines.append(f"- **{r['id']}** {r['at']:.2f}s `{r['kind']}`, {r['action']} (Jev {r['p']:.2f})")
        lines.append(f"  - cut candidate: \"{r['text']}\"")
        if r.get("second"):
            lines.append(f"  - said again as: \"{r['second']}\"")
    return "\n".join(lines) + "\n"


def candidates_md(cands):
    lines = ["# Candidates found in code (no TypeSafe key, so nothing is judged)", "",
             "Each is a place to look, not a decision. Check each against transcript.txt and "
             "references/retake-detection.md, then write spans.json.", ""]
    for c in cands:
        if c["questions"]:
            extra = f" -> said again: \"{c['second']}\"" if c.get("second") else ""
            lines.append(f"- {c['at']:.2f}s `{c['kind']}` \"{c['text']}\"{extra}")
    n = sum(1 for c in cands if not c["questions"])
    lines += ["", f"Plus {n} um/uh/audio-event token(s), always cut."]
    return "\n".join(lines) + "\n"


def propose(d, key=None, canned=None, force=False):
    """Returns 0, or 4 with no key. canned={qid: answer} runs offline (tests)."""
    d = Path(d)
    toks = load(d)
    (d / "transcript.txt").write_text(text_view(toks, d.name))
    cands = find(toks)
    if key is None and canned is None:
        (d / "candidates.md").write_text(candidates_md(cands))
        return 4
    sp = d / "spans.json"
    if sp.exists() and not force:
        sys.exit(f"ERROR: {sp} exists. Pass --force to replace it (it is kept as spans.prev.json).")
    qs = {q: v for c in cands for q, v in c["questions"].items()}
    answers = jev.ask(STATE, qs, key=key, log_dir=d, canned=canned)
    cuts, review = decide(cands, answers)
    spans = to_spans(cuts, toks)
    if sp.exists():
        sp.replace(d / "spans.prev.json")
    sp.write_text(json.dumps(spans, indent=1))
    (d / "review.md").write_text(review_md(review, toks))
    (d / "candidates.json").write_text(json.dumps(
        [{k: v for k, v in c.items() if k != "questions"} for c in cands], indent=1))
    u = jev.ask.last_usage
    print(f"{len(cands)} candidates, {len(qs)} questions, {u['input_tokens']} Jev tokens "
          f"(${u['cost_usd']:.4f}); {len(spans)} spans, {len(review)} to review")
    return 0


# --- fix -------------------------------------------------------------------------

def fix(d, pairs):
    """Replace whole words (case-insensitive), keeping each token's punctuation."""
    d, n = Path(d), 0
    for name in ("words.raw.json", "words.json"):
        f = d / name
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        toks = data["words"] if isinstance(data, dict) else data
        for t in toks:
            for old, new in pairs:
                s = re.sub(rf"(?i)(?<![\w']){re.escape(old)}(?![\w'])", new, t["text"])
                if s != t["text"]:
                    t["text"], n = s, n + 1
        f.write_text(json.dumps(data, indent=1))
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["text", "propose", "fix"])
    ap.add_argument("edit_dir")
    ap.add_argument("pairs", nargs="*", help="fix: old=new")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    d = Path(a.edit_dir)
    if a.cmd == "text":
        out = d / "transcript.txt"
        out.write_text(text_view(load(d), d.name))
        raw = (d / "words.raw.json").stat().st_size
        print(f"{out}  ({out.stat().st_size} bytes, {raw / out.stat().st_size:.1f}x smaller than words.raw.json)")
    elif a.cmd == "fix":
        pairs = [p.split("=", 1) for p in a.pairs if "=" in p]
        if not pairs:
            sys.exit("usage: retakes.py fix <edit_dir> old=new [old=new ...]")
        print(f"{fix(d, pairs)} token(s) changed")
    else:
        key, _ = keys.get("typesafe")
        try:
            code = propose(d, key=key, force=a.force)
        except jev.JevError as e:
            print(f"{e}. Falling back: decide the cut yourself from transcript.txt.", file=sys.stderr)
            (d / "candidates.md").write_text(candidates_md(find(load(d))))
            return 4
        if code == 4:
            print(f"No TypeSafe key. Wrote {d / 'transcript.txt'} and {d / 'candidates.md'}: "
                  "decide the cut yourself from those.")
        return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
