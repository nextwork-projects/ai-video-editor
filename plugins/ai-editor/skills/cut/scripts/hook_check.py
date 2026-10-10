#!/usr/bin/env python3
"""When does the cut first say what the title promises?

Viewers who do not hear what the title promised leave in the first seconds. This finds the second
the title's key words are first spoken in the cut and prints the first 10 s of speech, so Claude
can tell the user when the opening does not deliver the promise.

    python3 hook_check.py edits/NAME "<title or the hook the user stated>"
    python3 hook_check.py <transcript.json> "<title>"
    python3 hook_check.py demo        self-check, offline

edits/NAME reads cut.transcript.json (the verify pass), else words.json. Exit 1 when the first key
word lands after 10 s or never.

Key words: the title's words minus stopwords and title verbs (become, stop, build...). A word in
GENERIC (ai, video, tool) only counts inside a two-word phrase ("AI engineer"), because most
videos about AI say "AI" early. Plurals and possessives match; other forms do not ("edited" is
not "editing").
ponytail: word matching, not meaning. A synonym, or a promise made only on screen, is missed;
read the first 10 s it prints before trusting a FAIL.
"""
import json
import re
import sys
from pathlib import Path

LIMIT = 10.0
STOP = set("""a an the and or but of to in on at for with without from by as is are was be been
this that these those it its i you your my our we us he she they them his her their me
how what why when where who which here there any every all some no not more most less
vs versus into out up so if then than too very just only also over about
do does did done doing make makes made making get gets got use using used build built
building become becomes stop start starting learn learning actually really still can will
should need want one way ways new like let lets""".split())
GENERIC = {"ai", "video", "tool", "thing", "guide", "tip"}


def norm(w):
    w = re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'"))
    w = re.sub(r"'s$", "", w).replace("'", "")
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith("es") and w[-3] in "sxh":
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


STOP = {norm(w) for w in STOP}   # compared after norm(): "this" -> "thi"


def tokens(text):
    """Split like a transcript: on spaces, hyphens and slashes, normalised, empties dropped."""
    return [t for t in (norm(w) for w in re.split(r"[\s\-/]+", text)) if t]


def key_terms(title):
    """Single key words, plus every adjacent pair of content words (so 'AI engineer' counts)."""
    words = [(t, t in STOP or re.fullmatch(r"(19|20)\d\d", t) is not None) for t in tokens(title)]
    terms = []
    for i, (t, stop) in enumerate(words):
        if stop:
            continue
        if t not in GENERIC and not re.fullmatch(r"\d+", t):
            terms.append((t,))
        if i + 1 < len(words) and not words[i + 1][1]:
            terms.append((t, words[i + 1][0]))
    return list(dict.fromkeys(terms))


def first_hit(toks, terms):
    """Index of the first token where any term starts, and the term. (None, None) if never."""
    for i in range(len(toks)):
        for term in terms:
            if tuple(toks[i:i + len(term)]) == term:
                return i, term
    return None, None


def load(arg):
    p = Path(arg)
    if p.is_dir():
        p = next((p / f for f in ("cut.transcript.json", "words.json") if (p / f).exists()), None)
        if p is None:
            sys.exit(f"ERROR: no cut.transcript.json or words.json in {arg}. Run the cut skill first.")
    data = json.loads(p.read_text(encoding="utf-8"))
    words = data["words"] if isinstance(data, dict) else data
    out = []  # (normalised token, start, raw text); a hyphenated word gives several tokens
    for w in words:
        if w.get("type", "word") == "word":
            out += [(t, w["start"], w["text"]) for t in tokens(w["text"])]
    return out


def check(words, title):
    """(seconds of the first key word or None, the term, first 10 s of speech)."""
    i, term = first_hit([t for t, _, _ in words], key_terms(title))
    first10 = " ".join(r for s, r in dict.fromkeys((s, r) for _, s, r in words if s < LIMIT))
    return (words[i][1] if i is not None else None), term, first10


def demo():
    assert norm("Creator's") == "creator" and norm("styles") == "style" and norm("AI?") == "ai"
    assert norm("boxes") == "box" and norm("stories") == "story" and norm("process") == "process"
    assert norm("edited") != norm("editing")
    T = key_terms("How to Become an AI Engineer in 2026")
    assert ("ai", "engineer") in T and ("engineer",) in T and ("ai",) not in T and ("become",) not in T, T
    W = lambda s: [(t, n * 0.5, t) for n, t in enumerate(tokens(s))]
    # "AI" alone never delivers the promise; the pair does.
    assert check(W("what if AI did all of it, my editing style"), "Copy Any Creator's Editing Style with AI")[0] == 4.0
    assert check(W("this is the way to become an AI engineer"), "How to Become an AI Engineer in 2026")[0] == 3.5
    assert check(W("nothing here matches"), "Forward Deployed Engineer Roadmap")[0] is None
    assert check(W("forward-deployed engineers are"), "Forward Deployed Engineer Roadmap")[0] == 0.0
    # loads the Transcription shape (a list, spacing skipped) and an edit folder
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "words.json").write_text(json.dumps(
            [{"text": "so", "start": 0.1, "end": 0.3, "type": "word"}, {"text": " ", "start": 0.3, "end": 0.4, "type": "spacing"},
             {"text": "engineers", "start": 12.0, "end": 12.5, "type": "word"}]), encoding="utf-8")
        t, term, first10 = check(load(d), "AI Engineer Roadmap")
        assert t == 12.0 and term == ("engineer",) and first10 == "so", (t, term, first10)
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    t, term, first10 = check(load(sys.argv[1]), sys.argv[2])
    print(f"title: {sys.argv[2]}\nkey words: {', '.join(' '.join(x) for x in key_terms(sys.argv[2]))}")
    print(f"first said: {'never' if t is None else f'{t:.1f} s'}" + (f" ({' '.join(term)})" if term else ""))
    print(f"first {LIMIT:.0f} s: {first10}")
    if t is None or t > LIMIT:
        print(f"FAIL: the title's promise is not said in the first {LIMIT:.0f} s.")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
