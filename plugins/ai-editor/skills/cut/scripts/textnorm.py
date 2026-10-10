#!/usr/bin/env python3
"""Compare two transcripts of the same speech, and find quoted text in one.

Transcribers do not spell the same sound the same way twice: one pass writes
"fifteen hundred / eighty percent", the next "1,500 / 80%". Every diff here
(verify: render vs intent) compares two such transcripts, so formatting noise
must fold away before comparing.

Rules, deliberately narrow:
  - punctuation and case are dropped; hyphens become spaces
  - "%" becomes the word "percent"
  - number words fold to digits, but a bare small number word does not ("one of
    the best" stays "one")
  - a few same-sound contractions ("wanna" / "want to"). Never a real word
    difference.
"""
import json
import re

UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
         "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
        "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000}
SPOKEN_SAME = {"wanna": "want to", "gonna": "going to", "gotta": "got to",
               "kinda": "kind of", "sorta": "sort of", "til": "till",
               "cuz": "because", "yall": "you all"}
# A single number word only folds to a digit above this, so the pronoun "one"
# and counting words like "two" survive as words.
BARE_FOLD_MIN = 13


def norm(s):
    """Spoken content only. Hyphens split; '%' spoken; everything else dropped."""
    s = str(s).lower().replace("%", " percent ")
    # Thousands separators die BEFORE punctuation becomes whitespace, or a transcriber's
    # "1,500" splits into "1" and "500" and never matches "fifteen hundred".
    s = re.sub(r"(?<=\d),(?=\d)", "", s)
    return re.sub(r"[^a-z0-9' ]+", " ", s).strip()


def canon(toks):
    """Fold number phrases to digits and expand same-sound contractions."""
    return [t for t, _ in canon_src(toks)]


def canon_src(toks):
    """canon, with the index in `toks` each output token came from: [(token, index)]."""
    out, i = [], 0
    while i < len(toks):
        t = toks[i]
        if t in SPOKEN_SAME:
            out.extend((x, i) for x in SPOKEN_SAME[t].split())
            i += 1
            continue
        if t in UNITS or t in TENS:
            total, cur, j = 0, 0, i
            while j < len(toks):
                w = toks[j]
                if w in UNITS:
                    cur += UNITS[w]
                elif w in TENS:
                    cur += TENS[w]
                elif w in SCALES:
                    cur = (cur or 1) * 100 if SCALES[w] == 100 else cur
                    if SCALES[w] != 100:
                        total += (cur or 1) * SCALES[w]
                        cur = 0
                else:
                    break
                j += 1
            value = total + cur
            # One small number word on its own is almost always a word, not a
            # statistic. Folding it turns "one of the greats" into "1 of the
            # greats", which is wrong even if it diffs symmetrically.
            if j - i == 1 and value < BARE_FOLD_MIN and t in UNITS:
                out.append((t, i))
                i += 1
            else:
                out.append((str(value), i))
                i = j
            continue
        out.append((t, i))
        i += 1
    return out


def words(text):
    return canon([w for w in norm(text).split() if w])


def transcript_words(words, types=("word",)):
    """Canonical comparable token list from a list of word dicts."""
    out = []
    for w in words:
        if w.get("type") not in types:
            continue
        out.extend([x for x in norm(w["text"]).split() if x])
    return canon(out)


def timed_words(words):
    """transcript_words with times: [(token, start, end)], each token timed by the word it came from."""
    toks, owner = [], []
    for w in words:
        if w.get("type", "word") != "word":
            continue
        for x in norm(w["text"]).split():
            toks.append(x)
            owner.append(w)
    return [(t, owner[i]["start"], owner[i]["end"]) for t, i in canon_src(toks)]


def pair_by_time(a, b, tol=0.25):
    """Two transcripts of the same audio, each [(key, start, end)] on the same timeline. difflib lines up the
    keys; inside a replaced run, an `a` item and the `b` items it overlaps in time (within tol s) are the same
    sound heard differently (a re-transcription that wrote "Jev" as "Jeff"). Returns
    (same [(i, j)], differ [(i, [j, ...])], gone [i] (only in a), new [j] (only in b))."""
    import difflib
    sm = difflib.SequenceMatcher(a=[x[0] for x in a], b=[x[0] for x in b], autojunk=False)
    same, differ, gone, new = [], [], [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            same += list(zip(range(i1, i2), range(j1, j2)))
            continue
        used = set()
        for i in range(i1, i2):
            js = [j for j in range(j1, j2) if b[j][1] < a[i][2] + tol and a[i][1] < b[j][2] + tol] if tag == "replace" else []
            if js:
                differ.append((i, js))
                used.update(js)
            else:
                gone.append(i)
        new += [j for j in range(j1, j2) if j not in used]
    return same, differ, gone, new


def load_words(path):
    """A transcript file as a list of tokens. Accepts the contract's plain list
    or a {"words": [...]} payload."""
    d = json.load(open(path, encoding="utf-8"))
    return d["words"] if isinstance(d, dict) else d


def nwords(s):
    return [w for w in norm(s).split() if w]


def locate(needle, toks):
    """Every token span whose words match `needle`. Returns [(first, last)]."""
    hay, owner = [], []
    for i, t in enumerate(toks):
        for w in nwords(t.get("text", "")):
            hay.append(w)
            owner.append(i)
    need = nwords(needle)
    if not need:
        return []
    return [(owner[i], owner[i + len(need) - 1])
            for i in range(len(hay) - len(need) + 1) if hay[i:i + len(need)] == need]
