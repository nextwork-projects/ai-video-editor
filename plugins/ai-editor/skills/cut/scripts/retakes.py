#!/usr/bin/env python3
"""The cheap way to decide the cut: code finds the candidates, Jev judges them, Claude
reviews only what Jev was unsure of.

    python3 retakes.py text    <edit_dir>              transcript.txt, one line per phrase
    python3 retakes.py propose <edit_dir> [--force]    spans.json + review.md (needs a TypeSafe key)
    python3 retakes.py fix     <edit_dir> cloud=Claude [jiv=Jev ...]   fix misheard words
    python3 retakes.py captions <edit_dir>             captions.json + captions.txt for style-edit
    python3 retakes.py hook    <edit_dir> <n>          <edit_dir>-hook<n>/: the cut opening on alternate hook n

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
         Alternate hooks are the exception: takes of the opening line recorded after the body
         (after the call to action) are cut from the main cut as `alt_hook` and listed in
         hooks.json, so the hook stays at the start and the cut never ends on one.
         With no TypeSafe key it writes transcript.txt and candidates.md and exits 4: decide
         the cut yourself from those (references/retake-detection.md).
fix      Replaces one whole word everywhere in words.raw.json, words.json, cut.transcript.json
         and captions.json (style-edit's caption text), keeping
         punctuation and timings. A misheard name costs one command, not a rewrite. Each pair is
         kept in fixes.json, so captions applies it again.
hook     A variant edit dir for alternate hook n (1-based, from hooks.json): the same spans,
         with the opening hook cut, that alternate kept, and lead.json telling build_timeline.py
         to play it first. Build, render, verify and style-edit it like any edit dir.
captions The caption words: what the verify pass heard in cut.mp4 (cut.transcript.json), timed to
         it, with every word it heard differently at the same time (textnorm.pair_by_time) taken
         from the approved cut text (words.json), names spelled as the profile's `names`, and
         every fix in fixes.json applied. Writes captions.json and captions.txt (proofread this).

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
from textnorm import load_words, norm, nwords, pair_by_time  # noqa: E402
from ai_editor import jev, keys, profile  # noqa: E402

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


def say(toks, a, b, mark=False):
    """The words a..b. mark: a label transcribe.py found holding more speech than its word gets
    "[N.Ns of speech not transcribed]" after it (transcript.txt only)."""
    return " ".join(t["text"].strip() + (f" [{t['unheard_s']:.1f}s of speech not transcribed]"
                                         if mark and t.get("unheard_s") else "") for t in toks[a:b + 1])


SPANS_HINT = "Quote words from here in spans.json; use \"after\": <a start time> when a phrase repeats."


def text_view(toks, name="", hint=SPANS_HINT):
    lines = [f"# {name} {len(toks)} tokens. [start-end] seconds, then the words. "
             f"(+N.Ns) = the pause before a phrase. {hint}"]
    prev = None
    for a, b in phrases(toks):
        gap = toks[a]["start"] - prev if prev is not None else 0
        lines.append((f"(+{gap:.1f}s) " if gap >= 1.0 else "") +
                     f"[{toks[a]['start']:.2f}-{toks[b]['end']:.2f}] {say(toks, a, b, mark=True)}")
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
            # "a lot of tokens and a lot of money": the first run finished its thing, then "and"
            # starts a second item in the same shape. A list, not a retry.
            rest = [w for w, _ in seq[m + k:n]]
            c = max((x for x, w in enumerate(rest) if w in ("and", "or")), default=None)
            listed = c is not None and any(w not in STOP for w in rest[:c]) and all(w in STOP for w in rest[c:])
            if k >= (2 if n - m <= NEAR_WORDS else 3) and (content or k >= 4) and not listed:
                best = (m, k)
                break
        i, j = (seq[best[0]][1], seq[n][1]) if best else (None, None)
        if best and i < j and not taken(i) and not taken(j - 1):
            out.append((i, j))
            n += best[1]
        else:
            n += 1
    return sorted(out)


ALT_HOOK_MAX_WORDS = 30   # an alternate take longer than this is a second take of the video, not a hook


def alt_hooks(toks):
    """Takes of the opening line recorded after the body: [(a, b)] token ranges, each running to the
    next take or the end of the recording. Only a tail counts: walking back from the end, every
    stretch from a take of the opening to the next one is short. A callback to the hook mid-video
    is followed by the rest of the body, so it is never a tail. Matched more than WINDOW_S after
    the opening, so it is never a plain retake of it."""
    phr = phrases(toks)
    if not phr:
        return []
    first, t0 = opening(toks, *phr[0]), toks[phr[0][0]]["start"]
    hits = []
    for a, b in clauses(toks):
        if toks[a]["start"] - t0 <= WINDOW_S:
            continue
        if similar_openings(first, opening(toks, a, b)):
            hits.append(a)
        # matched on the word sequence, not the phrase edge: Whisper can hang the take's first word on
        # the phrase before it ("more tips I | built a model router"), the "I" stretched over the pause
        elif not toks[a - 1]["text"].strip().endswith((".", "?", "!", ",", ";", ":")) \
                and similar_openings(first, opening(toks, a - 1, b)):
            hits.append(a - 1)
    takes, e = [], len(toks)
    for a in reversed(hits):
        if sum(len(nwords(t["text"])) for t in toks[a:e]) > ALT_HOOK_MAX_WORDS:
            break
        takes.insert(0, (a, e - 1))
        e = a
    return takes


def hook_line(toks, take):
    """(opening_keeper_first, opening_end, take_end): the opening hook the main cut keeps, and how
    far the alternate `take` says the same line. The keeper is the last take of the opening within
    WINDOW_S of the start (last take wins). Both ends are the last word the two takes share,
    stretched to the end of its phrase.
    ponytail: word alignment, not meaning; a hook reworded past its first words ends early, and
    the variant's paper-edit.md read-through catches that."""
    phr = phrases(toks)
    first, t0 = opening(toks, *phr[0]), toks[phr[0][0]]["start"]
    keep = max(a for a, b in clauses(toks) if toks[a]["start"] - t0 <= WINDOW_S
               and similar_openings(first, opening(toks, a, b)))
    end_of = {i: b for a, b in phr for i in range(a, b + 1)}
    seq = norm_seq(toks)
    x = [p for p in seq if keep <= p[1] < take[0]][:ALT_HOOK_MAX_WORDS + 10]
    y = [p for p in seq if take[0] <= p[1] <= take[1]]
    ea = eb = 0      # the shared run from the start: blocks of 2+ words, at most 3 words apart
    for bl in difflib.SequenceMatcher(a=[w for w, _ in x], b=[w for w, _ in y], autojunk=False).get_matching_blocks():
        if bl.size < (1 if not ea else 2) or bl.a - ea > 3 or bl.b - eb > 3:
            break
        ea, eb = bl.a + bl.size, bl.b + bl.size
    xe, ye = (x[ea - 1][1], y[eb - 1][1]) if ea else (keep, take[0])
    return keep, end_of[xe], min(end_of[ye], take[1])


LIKE_BEFORE = {"and", "so", "but", "or", "um", "uh", "was", "were"}


def loose_like(toks, i):
    """Is "like" at token i set off as a hesitation? A pause or comma either side, or after
    "and"/"so"/"was"..., or opening a clause. "models like Claude" is a comparison: never a filler."""
    prev = toks[i - 1] if i else None
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if prev is None or prev["text"].strip().endswith((".", "?", "!", ",")) or toks[i]["text"].strip().endswith(","):
        return True
    if toks[i]["start"] - prev["end"] >= 0.3 or (nxt and nxt["start"] - toks[i]["end"] >= 0.3):
        return True
    return bool(set(nwords(prev["text"])) & LIKE_BEFORE)


def find(toks):
    """Every candidate, each with the Jev questions that decide it."""
    phr = phrases(toks)
    end_of = {i: b for a, b in phr for i in range(a, b + 1)}
    cands = []
    alts = alt_hooks(toks)
    tail = alts[0][0] if alts else len(toks)   # nothing in the alternate hooks is judged: all of it is cut

    def add(kind, a, b, qs=None, **extra):
        if kind != "alt_hook":
            b = min(b, tail - 1)    # a phrase can run into the first alternate hook (a word hung on it)
        cands.append({"id": f"c{len(cands)}", "kind": kind, "cut": [a, b], "at": toks[a]["start"],
                      "text": say(toks, a, b), "questions": qs or {}, **extra})

    for i, j in restarts(toks):
        if j >= tail:
            continue
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
        if a in restarted or pi + 1 >= len(phr) or words > 8 or a >= tail:
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
            if a >= tail or (kind == "filler" and m.group(0) == "like" and not loose_like(toks, a)):
                continue
            ctx = say(toks, max(0, a - 12), min(len(toks) - 1, b + 12))
            cid = f"c{len(cands)}"
            q = (jev.noul("In `text`, are the words `words` the speaker talking to themself about "
                          "the recording (like \"wait\", \"sorry\", \"let me start again\"), not "
                          "to the viewer?", text=ctx, words=m.group(0)) if kind == "meta" else
                 jev.noul("In `text`, is `word` a hesitation filler that can be removed without "
                          "changing what is said?", text=ctx, word=m.group(0)))
            add(kind, a, b, {f"{cid}_{kind}": q})

    for n, (a, b) in enumerate(alts, 1):
        add("alt_hook", a, b, hook=n)
    for i, t in enumerate(toks[:tail]):
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
            note = {"filler": "hesitation", "alt_hook": f"alternate hook {c.get('hook')}: retakes.py hook"}
            cuts.append({**c, "confidence": "high", "note": note.get(c["kind"], "")})
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
    rank = {"alt_hook": 5, "retake": 4, "false_start": 3, "meta": 2, "filler": 1, "audio_event": 0}
    level = {"low": 0, "medium": 1, "high": 2}
    merged = []
    for c in sorted(cuts, key=lambda c: c["cut"][0]):
        a, b = c["cut"]
        if merged and a <= merged[-1]["b"] + 1 and (merged[-1]["kind"] == "alt_hook") == (c["kind"] == "alt_hook"):
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
    alts = [c for c in cands if c["kind"] == "alt_hook"]
    n = sum(1 for c in cands if not c["questions"]) - len(alts)
    lines += ["", f"Plus {n} um/uh/audio-event token(s), always cut."]
    if alts:
        lines += ["", "Alternate hooks (takes of the opening line after the body). Not retakes: cut each "
                  "from the main cut as `alt_hook`, the opening stays first (references/retake-detection.md):"]
        lines += [f"- hook {c['hook']}: {c['at']:.2f}s \"{c['text']}\"" for c in alts]
    return "\n".join(lines) + "\n"


def propose(d, key=None, canned=None, force=False):
    """Returns 0, or 4 with no key. canned={qid: answer} runs offline (tests)."""
    d = Path(d)
    toks = load(d)
    (d / "transcript.txt").write_text(text_view(toks, d.name))
    cands = find(toks)
    write_hooks(d, toks)
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
    n = sum(c["kind"] == "alt_hook" for c in cands)
    if n:
        print(f"{n} alternate hook(s) after the body, cut from the main cut: {d / 'hooks.json'}")
    print(f"{len(cands)} candidates, {len(qs)} questions, {u['input_tokens']} Jev tokens "
          f"(${u['cost_usd']:.4f}); {len(spans)} spans, {len(review)} to review")
    return 0


# --- alternate hooks -------------------------------------------------------------

def write_hooks(d, toks):
    """hooks.json: the opening the main cut keeps and every alternate take, quoted for spans.json."""
    alts = alt_hooks(toks)
    f = Path(d) / "hooks.json"
    if not alts:
        f.unlink(missing_ok=True)
        return []
    q = lambda a, b: {"text": say(toks, a, b), "after": max(0.0, round(toks[a]["start"] - 0.001, 3))}  # noqa: E731
    keep, oe, _ = hook_line(toks, alts[0])
    out = {"opening": q(keep, oe),
           "alternates": [{"n": n, **q(a, hook_line(toks, (a, b))[2])} for n, (a, b) in enumerate(alts, 1)]}
    f.write_text(json.dumps(out, indent=1))
    return out["alternates"]


def hook_variant(d, n):
    """<d>-hook<n>/: words.raw.json, fixes.json, spans.json with the opening hook cut and alternate n
    kept, and lead.json (alternate n plays first). Returns the new dir."""
    import shutil
    import build_timeline as B
    d = Path(d)
    toks = load(d)
    alts = alt_hooks(toks)
    if not 1 <= n <= len(alts):
        sys.exit(f"ERROR: no alternate hook {n}; {d.name} has {len(alts)} (retakes.py propose lists them)")
    take = alts[n - 1]
    keep, oe, le = hook_line(toks, take)
    spans = json.loads((d / "spans.json").read_text())
    t_open, t_tail = toks[oe]["end"], toks[alts[0][0]]["start"]
    # the opening (replaced) and the alternate hooks (rebuilt below, one span per take)
    out = [sp for sp in spans if t_open <= B.resolve_spans([sp], toks)[0]["start"] < t_tail]
    q = lambda a, b, kind, note: {"text": say(toks, a, b), "kind": kind, "note": note,  # noqa: E731
                                  "after": max(0.0, round(toks[a]["start"] - 0.001, 3))}
    out.append(q(0, oe, "alt_hook", f"opening hook, replaced by alternate hook {n}"))
    for m, (a, b) in enumerate(alts, 1):
        if m != n:
            out.append(q(a, b, "alt_hook", f"alternate hook {m}"))
        elif le < b:
            out.append(q(le + 1, b, "alt_hook", f"after alternate hook {n}"))
    v = d.parent / f"{d.name}-hook{n}"
    v.mkdir(exist_ok=True)
    for name in ("words.raw.json", "fixes.json"):
        if (d / name).exists():
            shutil.copyfile(d / name, v / name)
    (v / "spans.json").write_text(json.dumps(sorted(out, key=lambda s: s["after"]), indent=1))
    (v / "lead.json").write_text(json.dumps(q(take[0], le, "alt_hook", f"alternate hook {n}, played first"), indent=1))
    return v


# --- fix -------------------------------------------------------------------------

def swap(text, old, new):
    """`old` -> `new` as a whole word (case-insensitive), the token's punctuation kept."""
    return re.sub(rf"(?i)(?<![\w']){re.escape(old)}(?![\w'])", lambda _: new, text)


def fix(d, pairs):
    """Replace whole words (case-insensitive), keeping each token's punctuation. Remembered in fixes.json."""
    d, n = Path(d), 0
    fj = d / "fixes.json"
    kept = json.loads(fj.read_text()) if fj.exists() else {}
    kept.update({old.lower(): new for old, new in pairs})
    fj.write_text(json.dumps(kept, indent=1))
    for name in ("words.raw.json", "words.json", "cut.transcript.json", "captions.json"):
        f = d / name
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        toks = data["words"] if isinstance(data, dict) else data
        for t in toks:
            for old, new in pairs:
                s = swap(t["text"], old, new)
                if s != t["text"]:
                    t["text"], n = s, n + 1
        f.write_text(json.dumps(data, indent=1))
    return n


def caption_words(heard, cut, names=(), fixes=None):
    """heard: cut.transcript.json words; cut: words.json (the approved cut text, timed on the cut). The heard
    words and times, each word heard differently at the same time spelled as the cut has it, then the fixes
    and the profile's name spellings. Returns (words, [(was, now)])."""
    strip = lambda t: re.sub(r"^\W+|\W+$", "", t)
    hw = [dict(w) for w in heard if w.get("type", "word") == "word" and norm(w["text"])]
    cw = [w for w in cut if w.get("type", "word") == "word" and norm(w["text"])]
    key = lambda ws: [(norm(w["text"]), w["start"], w["end"]) for w in ws]
    was = [w["text"] for w in hw]
    _, differ, _, _ = pair_by_time(key(cw), key(hw))
    got = {}
    for i, js in differ:            # the first heard word carries the cut word; two cut words in one are joined
        got.setdefault(js[0], []).append(strip(cw[i]["text"]))
        for j in js[1:]:
            got.setdefault(j, [])
    for j, ws in got.items():
        core = strip(hw[j]["text"])
        new = " ".join(ws)
        hw[j]["text"] = hw[j]["text"].replace(core, new, 1) if core and ws else new
    spell = {n.lower(): n for n in names}
    for w in hw:
        for old, new in (fixes or {}).items():
            w["text"] = swap(w["text"], old, new)
        core = strip(w["text"])
        if core.lower() in spell:
            w["text"] = w["text"].replace(core, spell[core.lower()], 1)
    changed = [(a, w["text"]) for a, w in zip(was, hw) if a != w["text"]]
    return [w for w in hw if w["text"].strip()], changed


def captions(d):
    d = Path(d)
    heard = load_words(d / "cut.transcript.json")
    cut = load_words(d / "words.json") if (d / "words.json").exists() else []
    fj = d / "fixes.json"
    names = [n["name"] for n in profile.load().get("names") or [] if isinstance(n, dict) and n.get("name")]
    words, changed = caption_words(heard, cut, names, json.loads(fj.read_text()) if fj.exists() else {})
    (d / "captions.json").write_text(json.dumps(words, indent=1))
    (d / "captions.txt").write_text(text_view(words, "captions", "A misheard word: retakes.py fix <edit_dir> old=new."))
    return words, changed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["text", "propose", "fix", "captions", "hook"])
    ap.add_argument("edit_dir")
    ap.add_argument("pairs", nargs="*", help="fix: old=new; hook: the alternate's number")
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
    elif a.cmd == "hook":
        if not a.pairs or not a.pairs[0].isdigit():
            sys.exit("usage: retakes.py hook <edit_dir> <n>")
        if not (d / "spans.json").exists():
            sys.exit(f"ERROR: no spans.json in {d}: decide the main cut first")
        print(hook_variant(d, int(a.pairs[0])))
    elif a.cmd == "captions":
        if not (d / "cut.transcript.json").exists():
            sys.exit(f"ERROR: no cut.transcript.json in {d}: run the cut skill's verify step first")
        words, changed = captions(d)
        n = {}
        for x in changed:
            n[x] = n.get(x, 0) + 1
        print(f"{d / 'captions.json'}: {len(words)} words" + (": " + ", ".join(
            f"{w} -> {v}" + (f" x{k}" if k > 1 else "") for (w, v), k in n.items()) if n else ""))
        print(f"{d / 'captions.txt'}: proofread this; a misheard word is retakes.py fix {d} old=new")
    else:
        key, _ = keys.get("typesafe")
        try:
            code = propose(d, key=key, force=a.force)
        except jev.JevError as e:
            (d / "candidates.md").write_text(candidates_md(find(load(d))))
            if e.rejected_key:
                print(f"TypeSafe rejected the saved key ({e}). Save a new one with the setup skill's setkey step. "
                      "Meanwhile decide the cut yourself from transcript.txt and candidates.md.", file=sys.stderr)
                return 5
            print(f"{e}. Falling back: decide the cut yourself from transcript.txt.", file=sys.stderr)
            return 4
        if code == 4:
            print(f"No TypeSafe key. Wrote {d / 'transcript.txt'} and {d / 'candidates.md'}: "
                  "decide the cut yourself from those.")
        return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
