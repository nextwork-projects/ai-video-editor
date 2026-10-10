#!/usr/bin/env python3
"""Parallel readers for a long take: what word matching in retakes.py misses.

    paper edit -> one reader per ~180 s chunk (cut-reader agents, all in one message) -> proposed drops
               -> one verifier per drop (cut-reader agents, one message), arguing to keep it -> confirmed
               -> confirmed drops appended to spans.json; stitches and lost words listed for Claude

Readers catch a line re-said in different words (last take wins), a sentence stitched from two takes,
a word lost inside a cut, and a false start that survived. They quote text; this script resolves each
quote to transcript words and proves the new span resolves to those same words. No model types a time.

    python3 read_cut.py chunks <edit_dir> [--chunk 180] [--overlap 30]   writes read/reader-N.md
    python3 read_cut.py verify <edit_dir> [--context 45]   reads read/reader-N.json, writes read/verify-N.md
    python3 read_cut.py merge  <edit_dir>    reads read/verify-N.json, adds confirmed spans to spans.json
    python3 read_cut.py demo                 self-check

Each prompt prints with the path its agent writes its JSON to (the same name, .json).
Stdlib only. Exit codes: 0 ok, 1 error, 2 usage
"""
import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_timeline import resolve_spans  # noqa: E402
from judge_cut import cuts_of, extract_json, inside, spans_of, text_of, toks_of  # noqa: E402

END = re.compile(r'[.?!]["”]?$')
DROP, REPORT = {"repeat", "false_start"}, {"stitch", "lost_word"}
STOP_S = 5.0
nt = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())

HOW_TO_READ = """HOW TO READ THE PAPER EDIT
Each line is one kept sentence: [raw time in the take] then the words the viewer hears. Text
between ~~ ~~ was cut out at that point: the viewer never hears it, and the words either side of
it play back to back. An indented ~~ ~~ line is a block cut out between two sentences. A cut that
removed 5 s or more starts with its length, "(23 s)". That is a STOP: the speaker paused the take
there, to think or to start a passage over. A shorter cut is not a stop."""

READER = """You are checking the cut of a long talking-head take before anyone watches it. One speaker
talks to camera, improvises and re-says lines. An automatic pass already cut most mistakes. Find what
it left in.

{how}

FIND FOUR THINGS
1. repeat: a line said, then said again, and both copies kept. The last take wins, so quote the
   EARLIER copy. A restart is one of two things:
   a. the same sentence twice back to back, nearly word for word;
   b. a STOP between the two copies, and after it the same line or step said again in new words,
      often inside a longer sentence. Only a short aside may sit between the copies. At every stop,
      compare the kept sentence or two before it with the sentence after it.
   With no stop and different words, the speaker is building on the line, not restarting: leave it.
   That covers a line then its explanation, a heading then its body, a point restated after an
   example, list items ("Step one...", "Step two..."), a callback, a summary.
2. false_start: kept words that start a sentence and abandon it before starting again ("So what
   you, the thing you want is"). If the fix needs a cut word put back, it is a stitch or lost_word.
3. stitch: one sentence built from two takes, the words before a ~~cut~~ from one attempt and the
   words after from another, so it reads wrong.
4. lost_word: a word the sentence needs sits inside a ~~cut~~ ("then I ~~will~~ show you").

Report only what you are sure of. An empty list is a good answer. A wrong repeat cuts a line the
speaker meant to say.

OUTPUT: one fenced json block and nothing else:
{{"findings": [{{"kind": "repeat | false_start | stitch | lost_word",
  "quote": "exact kept words copied from one line, never text from inside ~~ ~~",
  "raw": <raw time printed at the start of that line>,
  "keeps": "repeat only: the exact kept words of the later copy that stays",
  "why": "one short sentence"}}]}}
For repeat and false_start the quote is exactly what to cut: the whole earlier copy and nothing the
sentence around it still needs.

THE PAPER EDIT ({span})
{text}
"""

VERIFIER = """You are the second opinion on one proposed cut in a long talking-head take. A reader
flagged a kept line as a {kind} and wants it cut. Argue against it, then decide.

{how}

PROPOSED CUT (the line marked >> below): "{quote}"
Reader: {why}
{keeps}
It is a restart, cut it, when (a) the two copies are the same sentence back to back, nearly word for
word; or (b) a STOP sits between them and after it the same line is said again in new words, with
at most a short aside between.
It is meant, keep it, when there is no stop and the words differ: building on the line, a list item
or pattern, a callback, a summary, or it carries a fact the other copy does not.
Read the text as it would play with only the quoted words removed. If that reads broken, keep it.
Default keep. Cut only if a viewer would notice the same thing said twice.

CONTEXT
{text}

OUTPUT: one fenced json block and nothing else:
{{"verdict": "cut" | "keep", "why": "one sentence"}}
"""


def kept_words(d):
    """(toks, words, kept): words = indices of word tokens, kept = the subset that plays."""
    toks = toks_of(d)
    cuts = cuts_of(spans_of(d), toks)
    words = [i for i, t in enumerate(toks) if t.get("type", "word") == "word"]
    return toks, words, [i for i in words if not any(inside(toks[i], c) for c in cuts)]


def paper_lines(toks, words, kept):
    """One line per kept sentence: {"raw", "text", "t"}; cut words struck through where they were cut.
    A cut block between sentences is its own line with raw None; t is when the next kept word starts."""
    pos = {i: n for n, i in enumerate(words)}

    def strike(a, b, g):
        ws = [toks[words[x]]["text"].strip() for x in range(a, b)]
        if len(ws) > 40:
            ws = ws[:15] + [f"[{len(ws) - 30} more words]"] + ws[-15:]
        head = f"({g:.0f} s) " if g >= STOP_S else ""
        return f"~~{head}{' '.join(ws)}~~" if ws else f"~~({g:.0f} s silence)~~"
    L, cur, prev = [], None, None
    for i in kept:
        g = toks[i]["start"] - toks[prev]["end"] if prev is not None else 0
        cut = prev is not None and (pos[i] > pos[prev] + 1 or g >= STOP_S)
        if cur is None:
            if cut:
                L.append({"raw": None, "t": toks[i]["start"], "text": "        " + strike(pos[prev] + 1, pos[i], g)})
            cur = {"raw": toks[i]["start"], "words": []}
        elif cut:
            cur["words"].append(strike(pos[prev] + 1, pos[i], g))
        cur["words"].append(toks[i]["text"].strip())
        if END.search(toks[i]["text"].strip()):
            L.append({"raw": cur["raw"], "t": cur["raw"], "text": " ".join(cur["words"])})
            cur = None
        prev = i
    if cur:
        L.append({"raw": cur["raw"], "t": cur["raw"], "text": " ".join(cur["words"])})
    return L


def fmt(lines, mark=None):
    return "\n".join(l["text"] if l["raw"] is None else
                     f"{'>> ' if l is mark else ''}[raw {l['raw']:.1f}] {l['text']}" for l in lines)


def find(quote, near, toks, kept, after=0):
    """(j, e): kept-word positions of a quote, the match nearest `near` raw seconds."""
    q = [nt(x) for x in str(quote).split() if nt(x)]
    kn = [nt(toks[i]["text"]) for i in kept]
    hits = [j for j in range(after, len(kept) - len(q) + 1) if q and kn[j:j + len(q)] == q]
    return (min(hits, key=lambda j: abs(toks[kept[j]]["start"] - near)), None) if hits else None


def chunks(d, size=180.0, overlap=30.0):
    """(prompts written, chunks skipped as [(k, start, end)]: no kept line, nothing to read)."""
    toks, words, kept = kept_words(d)
    L = paper_lines(toks, words, kept)
    r = Path(d) / "read"
    r.mkdir(exist_ok=True)
    (r / "paper-cut.md").write_text(f"# Paper edit\n\n{HOW_TO_READ}\n\n{fmt(L)}\n", encoding="utf-8")
    end = toks[kept[-1]]["end"] if kept else 0.0
    step = size - overlap
    n = max(1, int(-(-(end - overlap) // step)))
    out, skipped = [], []
    for k in range(n):
        s = k * step
        part = [l for l in L if s <= l["t"] < s + size]
        p = r / f"reader-{k}.md"
        if not any(l["raw"] is not None for l in part):
            p.unlink(missing_ok=True)
            skipped.append((k, s, min(end, s + size)))
            continue
        p.write_text(READER.format(how=HOW_TO_READ, span=f"{s:.0f}-{min(end, s + size):.0f} s of {end:.0f} s",
                                   text=fmt(part)), encoding="utf-8")
        out.append(p)
    return out, skipped


def proposals(d):
    """Every reader finding, resolved: status proposed, report, or why it was dropped."""
    toks, words, kept = kept_words(d)
    r = Path(d) / "read"
    F = []
    for p in sorted(r.glob("reader-*.json")):
        o = extract_json(p.read_text(encoding="utf-8"), "findings") or {}
        for f in o.get("findings", []):
            f = {**f, "kind": str(f.get("kind", "")).strip()}
            try:
                f["raw"] = float(f.get("raw") or 0)
            except (TypeError, ValueError):
                f["raw"] = 0.0
            q = [x for x in str(f.get("quote", "")).split() if nt(x)]
            hit = find(f.get("quote", ""), f["raw"], toks, kept)
            if f["kind"] not in DROP | REPORT:
                f["status"] = "bad kind"
            elif not hit:
                f["status"] = "quote not in kept text"
            else:
                j, e = hit[0], hit[0] + len(q)
                ids = kept[j:e]
                f.update(raw=round(toks[ids[0]]["start"], 2), span=[ids[0], ids[-1]])
                if f["kind"] in REPORT:
                    f["status"] = "report"
                elif ids != words[words.index(ids[0]):words.index(ids[0]) + len(ids)]:
                    f["status"] = "spans a cut, fix by hand"
                elif (f["kind"] == "repeat" and f.get("keeps")
                      and find(f["keeps"], f["raw"], toks, kept) and not find(f["keeps"], f["raw"], toks, kept, e)):
                    f["status"] = "the copy that stays comes first"
                else:
                    f["text"] = text_of(toks, ids[0], ids[-1])
                    f["status"] = "proposed"
            F.append(f)
    acc = []   # the same find from two overlapping readers: keep the longest
    for f in sorted([f for f in F if "span" in f], key=lambda f: f["span"][0] - f["span"][1]):
        if any((g["kind"] in DROP) == (f["kind"] in DROP) and g["span"][0] <= f["span"][1] and f["span"][0] <= g["span"][1]
               for g in acc):
            f["status"] = "dup"
        else:
            acc.append(f)
    return sorted(F, key=lambda f: f["raw"])


def verify(d, context=45.0):
    toks, words, kept = kept_words(d)
    L = paper_lines(toks, words, kept)
    r = Path(d) / "read"
    for old in r.glob("verify-*"):
        old.unlink()
    gone = [p.with_suffix(".json").name for p in sorted(r.glob("reader-*.md")) if not p.with_suffix(".json").exists()]
    if gone:
        print(f"  missing {', '.join(gone)}: those readers wrote nothing, their chunks are unread")
    F = proposals(d)
    (r / "proposed.json").write_text(json.dumps(F, indent=1), encoding="utf-8")
    out = []
    for n, f in enumerate(x for x in F if x["status"] == "proposed"):
        ctx = [l for l in L if f["raw"] - context <= l["t"] <= f["raw"] + context]
        mark = max((l for l in ctx if l["raw"] is not None and l["raw"] <= f["raw"] + 0.01),
                   key=lambda l: l["raw"], default=None)
        keeps = f'The copy the reader says stays: "{f["keeps"]}"' if f.get("keeps") else ""
        p = r / f"verify-{n}.md"
        p.write_text(VERIFIER.format(kind=f["kind"].replace("_", " "), how=HOW_TO_READ, quote=f["quote"],
                                     why=f.get("why", ""), keeps=keeps, text=fmt(ctx, mark)), encoding="utf-8")
        f["prompt"] = p.name
        out.append(p)
    (r / "proposed.json").write_text(json.dumps(F, indent=1), encoding="utf-8")
    for f in F:
        if f["status"] not in ("proposed", "dup"):
            print(f"  {f['status']:30s} {f['kind']:11s} raw {f['raw']:7.1f} {f.get('quote', '')!r}")
    return out


def merge(d):
    """Confirmed drops into spans.json. Returns (added, report lines)."""
    d = Path(d)
    r = d / "read"
    F = json.loads((r / "proposed.json").read_text(encoding="utf-8"))
    toks, spans = toks_of(d), spans_of(d)
    added, lines = [], []
    for f in F:
        if f["status"] == "report":
            lines.append(f"FIX BY HAND {f['kind']:9s} raw {f['raw']:7.1f} {f['quote']!r}: {f.get('why', '')}")
        if f["status"] != "proposed":
            continue
        v = extract_json((r / f["prompt"].replace(".md", ".json")).read_text(encoding="utf-8"), "verdict") \
            if (r / f["prompt"].replace(".md", ".json")).exists() else None
        if not v or str(v.get("verdict", "")).lower() != "cut":
            lines.append(f"kept by verifier raw {f['raw']:7.1f} {f['quote']!r}: {(v or {}).get('why', 'no verdict')}")
            continue
        a, b = f["span"]
        sp = {"text": f["text"], "kind": "retake" if f["kind"] == "repeat" else "false_start",
              "after": round(toks[a]["start"] - 0.001, 3), "confidence": "medium",
              "note": f"reader: {f.get('why', '')}"[:160]}
        try:   # proved: the span resolves to exactly these words, and spans.json still builds
            c = resolve_spans([sp], toks)[0]
            assert abs(c["start"] - toks[a]["start"]) < 1e-6 and abs(c["end"] - toks[b]["end"]) < 1e-6
            resolve_spans(spans + added + [sp], toks)
        except (SystemExit, AssertionError):
            lines.append(f"would not build, fix by hand raw {f['raw']:7.1f} {f['quote']!r}")
            continue
        added.append(sp)
        lines.append(f"CUT {sp['kind']:11s} raw {f['raw']:7.1f} {f['text']!r}: {f.get('why', '')}")
    if added:
        (d / "spans.json").write_text(json.dumps(spans + added, indent=1), encoding="utf-8")
    return added, lines


def demo():
    W = lambda s, t0: [{"text": w, "start": t0 + i * 0.4, "end": t0 + i * 0.4 + 0.3, "type": "word"}
                       for i, w in enumerate(s.split())]
    toks = (W("Open the settings page first.", 0) + W("Then pick a model.", 3)
            + W("So you open settings, the page with the gear.", 15) + W("Then save it.", 19)
            + W("And it works well.", 400))
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "words.raw.json").write_text(json.dumps(toks), encoding="utf-8")
        (d / "spans.json").write_text(json.dumps([{"text": "then pick a model", "kind": "retake"}]), encoding="utf-8")
        ps, skipped = chunks(d)
        assert [p.name for p in ps] == ["reader-0.md", "reader-2.md"], ps   # 400 s, 150 s steps: three chunks,
        assert [k for k, _, _ in skipped] == [1]                              # the all-cut middle one unread
        assert "~~(13 s) Then pick a model.~~" in ps[0].read_text(encoding="utf-8")            # a cut line reaches its reader
        assert "~~(380 s silence)~~" in ps[1].read_text(encoding="utf-8") and "380 s" not in ps[0].read_text(encoding="utf-8")
        paper = (d / "read" / "paper-cut.md").read_text(encoding="utf-8")
        assert "~~(13 s) Then pick a model.~~" in paper, paper
        assert "[raw 0.0] Open the settings page first." in paper
        # reader 0: the re-said line (a STOP between, new words), a hallucination, and a stitch
        (d / "read" / "reader-0.json").write_text(json.dumps({"findings": [
            {"kind": "repeat", "quote": "Open the settings page first.", "raw": 0, "keeps": "So you open settings", "why": "re-said"},
            {"kind": "repeat", "quote": "words nobody said", "raw": 2},
            {"kind": "lost_word", "quote": "Then save it.", "raw": 19, "why": "needs 'and'"}]}), encoding="utf-8")
        # reader 1 overlaps and finds the same line again: a dup, not a second span
        (d / "read" / "reader-1.json").write_text('```json\n{"findings": [{"kind": "repeat", "quote": "the settings page", "raw": 0.4}]}\n```', encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            vs = verify(d)
        assert "missing reader-2.json" in out.getvalue(), out.getvalue()
        assert [p.name for p in vs] == ["verify-0.md"], vs
        assert "380 s" not in vs[0].read_text(encoding="utf-8")          # context: the lines around the finding only
        assert ">> [raw 0.0] Open the settings page first." in vs[0].read_text(encoding="utf-8")
        st = {f.get("quote"): f["status"] for f in json.loads((d / "read" / "proposed.json").read_text(encoding="utf-8"))}
        assert st["words nobody said"] == "quote not in kept text" and st["the settings page"] == "dup"
        assert st["Then save it."] == "report"
        (d / "read" / "verify-0.json").write_text('{"verdict": "cut", "why": "same step twice"}', encoding="utf-8")
        added, lines = merge(d)
        assert [s["text"] for s in added] == ["Open the settings page first."] and added[0]["kind"] == "retake"
        assert any(x.startswith("FIX BY HAND lost_word") for x in lines)
        assert len(spans_of(d)) == 2 and len(cuts_of(spans_of(d), toks)) == 2
        # a verifier that keeps it: nothing added
        (d / "spans.json").write_text(json.dumps([{"text": "then pick a model", "kind": "retake"}]), encoding="utf-8")
        (d / "read" / "verify-0.json").write_text('{"verdict": "keep", "why": "builds on it"}', encoding="utf-8")
        assert merge(d)[0] == []
    print("demo ok")


def main():
    a = sys.argv[1:]
    if a == ["demo"]:
        return demo()
    if "-h" in a or "--help" in a:
        print(__doc__)
        return 0
    if len(a) < 2 or a[0] not in ("chunks", "verify", "merge"):
        sys.exit(__doc__)
    d = Path(a[1])
    if not (d / "words.raw.json").exists():
        sys.exit(f"ERROR: no such file: {d / 'words.raw.json'}")
    opt = lambda k, v: float(a[a.index(k) + 1]) if k in a else v
    if a[0] == "chunks":
        ps, skipped = chunks(d, opt("--chunk", 180.0), opt("--overlap", 30.0))
        for k, s, e in skipped:
            print(f"  chunk {k} ({s:.0f}-{e:.0f} s) is all cut, no kept line: no prompt")
        print(f"{len(ps)} reader prompt(s): launch one cut-reader per prompt, all in one message")
    elif a[0] == "verify":
        ps = verify(d, opt("--context", 45.0))
        print(f"{len(ps)} verifier prompt(s)" + (": launch one cut-reader per prompt, all in one message"
                                                 if ps else ": nothing to verify, run merge for the report"))
    else:
        added, lines = merge(d)
        for x in lines:
            print("  " + x)
        print(f"{len(added)} span(s) added to spans.json" + (": build again" if added else ""))
        return 0
    for p in ps:
        print(f"  {p}  ->  {p.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
