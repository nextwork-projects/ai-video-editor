#!/usr/bin/env python3
"""Score a cut on paper before it renders, apply the judge's fixes, loop until clean.

    spans.json -> paper edit -> cut-judge agent (references/judge-rubric.md) -> judge.json
        ^                                                                        |
        +------------------ apply: restore / trim / add, on spans.json ----------+

    python3 judge_cut.py prompt <edit_dir> [--script script.md]   writes judge-prompt.md (rubric,
                                         the user's cut taste, the paper edit). No audio, no render.
    python3 judge_cut.py apply  <edit_dir> [--tighten]   reads judge.json, drops findings that fail the
                                         rubric's own bar, applies the rest to spans.json.
                                         Exit 0: nothing left to apply (done). Exit 3: spans changed, judge again.
    python3 judge_cut.py score  <edit_dir>   after the user approves: which judge changes the user
                                         reverted. One line per edit in $AI_EDITOR_HOME/judge-eval.jsonl.
    python3 judge_cut.py precision       the running precision, and whether apply may still auto-apply
    python3 judge_cut.py demo            self-check

The judge quotes text; this script resolves the quote to token edges and edits spans.json. No model
types a timestamp. A restored cut is frozen in judge-ledger.json, so a later round cannot re-cut it.
W6 (under-cut) adds never auto-apply without --tighten: an add on a warning can destroy a good take.

Precision gate: once 5+ applied findings are scored and fewer than 60% survived the user's review,
apply stops writing and lists the findings for Claude to weigh by hand.
Stdlib only. Exit codes: 0 ok, 1 error, 2 usage, 3 changed (judge again)
"""
import datetime
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_timeline import KINDS, resolve_spans  # noqa: E402
from preview_cut import label, paper_edit  # noqa: E402
from textnorm import load_words, locate, nwords  # noqa: E402

RUBRIC = HERE.parent / "references" / "judge-rubric.md"
CHECKS = {"B1", "B2", "B3", "B4", "W5", "W6"}
BLOCKING = {"B1", "B2", "B3", "B4"}
ACTIONS = {"restore", "trim", "add", "none"}
DEFAULT_ADD_KIND = "filler"   # the mildest kind: an added cut is the loop's one risky move
GATE, GATE_MIN = 0.60, 5      # auto-apply stops below this precision, once this many are scored


def home():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor")


def toks_of(d):
    return [t for t in load_words(Path(d) / "words.raw.json") if t.get("type", "word") in ("word", "audio_event")]


def spans_of(d):
    p = Path(d) / "spans.json"
    return json.loads(p.read_text()) if p.exists() else []


def cuts_of(spans, toks):
    """Each span resolved to its cut, sorted by time, as paper-edit.md numbers them. c["_i"] = span index."""
    out = []
    for i, sp in enumerate(spans):
        c = resolve_spans([sp], toks)[0]
        c["_i"] = i
        out.append(c)
    return sorted(out, key=lambda c: c["start"])


def inside(t, c):
    return c["start"] <= (t["start"] + t["end"]) / 2 <= c["end"]


def flat(text):
    """Normalised words with the `<<n>>` join markers dropped: the paper and every quote both go through it."""
    return " ".join(nwords(re.sub(r"<<[\d,]+>>", " ", text)))


def paper(spans, toks):
    """paper-edit.md's text from spans alone (pauses ignored: the judge reads words, not timing).
    Its lengths are words only; the real cut with pauses is in report.json."""
    cuts = cuts_of(spans, toks)
    dur = max((t["end"] for t in toks), default=0.0)
    kept, at = [], 0.0
    for c in cuts:
        if c["start"] > at:
            kept.append({"start": at, "end": c["start"]})
        at = max(at, c["end"])
    if at < dur:
        kept.append({"start": at, "end": dur})
    final = sum(k["end"] - k["start"] for k in kept)
    return paper_edit(label(toks, cuts, kept), cuts, dur, final, words_only=True), cuts


def taste_cut_rules():
    p = home() / "taste.md"
    if not p.exists():
        return ""
    m = re.search(r"^## Cut\n(.*?)(?=^## |\Z)", p.read_text(encoding="utf-8"), re.S | re.M)
    return m.group(1).strip() if m else ""


def build_prompt(d, script=None):
    md, _ = paper(spans_of(d), toks_of(d))
    parts = ["You are the critic in a video-editing loop. Grade the paper edit below against the rubric. "
             "Follow the rubric exactly, including its output format.", "", "# RUBRIC", "", RUBRIC.read_text()]
    rules = taste_cut_rules()
    if rules:
        parts += ["", "# THE USER'S OWN CUT RULES", "",
                  "Corrections this user gave before. They outrank your sense of what an edit should keep. "
                  "Do not raise a blocker against a cut one of these asks for, unless the removed take carries "
                  "a detail that survives nowhere else.", "", rules]
    built, rep = Path(d) / "paper-edit.md", Path(d) / "report.json"   # spans alone cannot show the pauses
    extra = [x + " (last build)" for x in (built.read_text().splitlines() if built.exists() else []) if "CLIPPED" in x]
    if rep.exists():
        r = json.loads(rep.read_text())
        extra.insert(0, f"- last build, pauses cut: source {r['duration']:.1f}s, cut {r['final_s']:.1f}s")
    if extra:
        md = md.replace("\n## What plays", "\n" + "\n".join(extra) + "\n\n## What plays", 1)
    parts += ["", "# PAPER EDIT TO GRADE", "", md]
    if script:
        parts += ["", "# SCRIPT (TIEBREAKER ONLY)", "", "Context for choosing between takes of one line. "
                  "Nothing is a defect for being off-script.", "", script]
    return "\n".join(parts + ["", "Return only the fenced json block."])


def extract_json(text, key="findings"):
    """The last fenced (or bare) JSON object in a reply that carries `key`."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S) or re.findall(r"\{.*\}", text, re.S)
    for b in reversed(blocks):
        try:
            obj = json.loads(b)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and key in obj:
            return obj
    return None


def validate(obj, cuts, paper_md):
    """(findings, dropped). Drops findings that fail the rubric's own bar; B3 on a `redundant` cut
    becomes a W5 spot-check (a redundant cut removes content that survives nowhere, by design)."""
    good, dropped = [], []
    paper_flat = flat(paper_md)
    for f in obj.get("findings", []):
        chk = str(f.get("check", "")).upper()
        fix = f.get("fix") or {}
        act = str(fix.get("action", "none")).lower()
        quote = str(f.get("quote", "")).strip()
        ci = f.get("cut")
        why = None
        if chk not in CHECKS:
            why = f"unknown check {f.get('check')!r}"
        elif not quote:
            why = "no quote, no finding"
        elif act not in ACTIONS:
            why = f"unknown fix action {fix.get('action')!r}"
        elif act in ("restore", "trim") and not isinstance(ci, int):
            why = f"{act} needs a cut index"
        elif isinstance(ci, int) and not 0 <= ci < len(cuts):
            why = f"cut index {ci} out of range"
        elif act == "trim" and not str(fix.get("keep_words", "")).strip():
            why = "trim needs keep_words"
        elif act == "add" and not str(fix.get("evidence", "")).strip():
            why = "add needs evidence"
        elif flat(quote) not in paper_flat:
            why = "quote is not in the paper edit"
        if why:
            dropped.append({**f, "_dropped": why})
            continue
        if chk == "B3" and isinstance(ci, int) and cuts[ci]["kind"] == "redundant":
            chk = "W5"
            f["problem"] = "[B3 on a redundant cut: spot-check only] " + str(f.get("problem", ""))
            if act == "restore":
                fix["action"] = act = "none"
        f["check"], f["severity"], f["fix"] = chk, ("blocker" if chk in BLOCKING else "warn"), fix
        good.append(f)
    return good, dropped


def text_of(toks, a, b):
    return " ".join(toks[x]["text"].strip() for x in range(a, b + 1))


def apply_findings(d, findings, rnd=0):
    """Edit spans.json. Returns (applied, refused) as lists of one-line strings."""
    d = Path(d)
    toks, spans = toks_of(d), spans_of(d)
    cuts = cuts_of(spans, toks)
    lp = d / "judge-ledger.json"
    ledger = json.loads(lp.read_text()) if lp.exists() else {"restored": [], "applied": []}
    drop, applied, refused, new = set(), [], [], []
    for f in findings:
        fix, act, ci, tag = f.get("fix") or {}, (f.get("fix") or {}).get("action", "none"), f.get("cut"), f["check"]
        if act == "none":
            continue
        if act == "restore":
            c = cuts[ci]
            drop.add(c["_i"])
            ledger["restored"].append(" ".join(nwords(c["evidence"])))
            ledger["applied"].append({"action": "restore", "check": tag, "start": c["start"], "end": c["end"],
                                      "text": c["evidence"], "round": rnd})
            applied.append(f"{tag} restore C{ci} {c['evidence'][:50]!r}")
        elif act == "trim":
            c = cuts[ci]
            ids = [i for i, t in enumerate(toks) if inside(t, c)]
            span = [toks[i] for i in ids]
            hits = locate(fix["keep_words"], span)
            if len(hits) != 1:
                refused.append(f"{tag} trim C{ci}: keep_words matched {len(hits)}x inside the cut (need 1)")
                continue
            a, b = hits[0]
            if a == 0 and b == len(span) - 1:
                drop.add(c["_i"])
                lo, hi = ids[0], ids[-1]
            elif a == 0:
                lo, hi = ids[b + 1], ids[-1]
            elif b == len(span) - 1:
                lo, hi = ids[0], ids[a - 1]
            else:
                refused.append(f"{tag} trim C{ci}: keep_words are mid-cut; a trim gives back the head or the tail")
                continue
            if c["_i"] not in drop:
                sp = {k: v for k, v in spans[c["_i"]].items() if k not in ("occurrence", "after")}
                sp.update(text=text_of(toks, lo, hi), after=round(toks[lo]["start"] - 0.001, 3))
                spans[c["_i"]] = sp
            kept = " ".join(s["text"].strip() for s in span[a:b + 1])
            ledger["restored"].append(" ".join(nwords(kept)))
            ledger["applied"].append({"action": "trim", "check": tag, "start": span[a]["start"],
                                      "end": span[b]["end"], "text": kept, "round": rnd})
            applied.append(f"{tag} trim C{ci}: gives back {kept[:50]!r}")
        elif act == "add":
            ev = fix["evidence"]
            key = " ".join(nwords(ev))
            if any(key and r and (key in r or r in key) for r in ledger["restored"]):
                refused.append(f"{tag} add {ev[:40]!r}: an earlier round gave this back; frozen")
                continue
            live = [c for c in cuts if c["_i"] not in drop]
            hits = [(a, b) for a, b in locate(ev, toks)
                    if not any(inside(toks[x], c) for x in range(a, b + 1) for c in live)]
            if len(hits) != 1:
                refused.append(f"{tag} add {ev[:40]!r}: matched {len(hits)}x in kept text (need 1)")
                continue
            a, b = hits[0]
            kind = fix.get("kind") if fix.get("kind") in KINDS - {"alt_hook"} else DEFAULT_ADD_KIND
            new.append({"text": text_of(toks, a, b), "kind": kind, "after": round(toks[a]["start"] - 0.001, 3),
                        "confidence": "low", "note": f"judge {tag}: {f.get('problem', '')}"[:160]})
            ledger["applied"].append({"action": "add", "check": tag, "start": toks[a]["start"],
                                      "end": toks[b]["end"], "text": new[-1]["text"], "round": rnd})
            applied.append(f"{tag} add {new[-1]['text'][:50]!r} [{kind}]")
    out = [s for i, s in enumerate(spans) if i not in drop] + new
    try:
        resolve_spans(out, toks)   # the edit must still build; on any doubt keep the old spans
    except SystemExit:
        return [], [f"the fixed spans.json would not build; nothing applied ({len(applied)} fix(es) dropped)"]
    if applied:
        bak = d / f"spans.judge{rnd}.json"
        if not bak.exists():
            bak.write_text(json.dumps(spans_of(d), indent=1))
        (d / "spans.json").write_text(json.dumps(out, indent=1))
        lp.write_text(json.dumps(ledger, indent=1))
    return applied, refused


def score(d):
    """{"kept", "reverted"} over the judge changes recorded in judge-ledger.json, against spans.json now."""
    d = Path(d)
    lp = d / "judge-ledger.json"
    if not lp.exists():
        return {"kept": 0, "reverted": 0, "lines": []}
    toks = toks_of(d)
    cuts = cuts_of(spans_of(d), toks)
    kept = reverted = 0
    lines = []
    for x in json.loads(lp.read_text()).get("applied", []):
        ts = [t for t in toks if x["start"] <= (t["start"] + t["end"]) / 2 <= x["end"]]
        if not ts:
            continue
        gone = sum(any(inside(t, c) for c in cuts) for t in ts) / len(ts)
        undone = gone >= 0.5 if x["action"] in ("restore", "trim") else gone < 0.5
        reverted += undone
        kept += not undone
        lines.append(f"{'REVERTED' if undone else 'kept':8s} {x['check']} {x['action']:7s} {x['text'][:60]!r}")
    return {"kept": kept, "reverted": reverted, "lines": lines}


def record(d, s):
    """One line per edit (a re-score replaces it) in $AI_EDITOR_HOME/judge-eval.jsonl."""
    p = home() / "judge-eval.jsonl"
    name = Path(d).resolve().name
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
    rows = [r for r in rows if r.get("edit") != name]
    rows.append({"at": datetime.date.today().isoformat(), "edit": name, "kept": s["kept"], "reverted": s["reverted"]})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))


def precision():
    """(precision or None, scored)."""
    p = home() / "judge-eval.jsonl"
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
    k, r = sum(x["kept"] for x in rows), sum(x["reverted"] for x in rows)
    return (k / (k + r) if k + r else None), k + r


def gated():
    p, n = precision()
    return p is not None and n >= GATE_MIN and p < GATE


def cmd_apply(d, tighten=False):
    d = Path(d)
    obj = json.loads((d / "judge.json").read_text()) if (d / "judge.json").exists() else None
    if obj is None or "findings" not in obj:
        sys.exit(f"ERROR: {d / 'judge.json'} missing or has no findings list")
    md, cuts = paper(spans_of(d), toks_of(d))
    findings, dropped = validate(obj, cuts, md)
    for f in dropped:
        print(f"  drop     {f.get('check', '?')}: {f['_dropped']}")
    todo = [f for f in findings if (f.get("fix") or {}).get("action", "none") != "none"
            and (tighten or not (f["check"] == "W6" and f["fix"]["action"] == "add"))]
    for f in findings:
        if f not in todo:
            print(f"  suggest  {f['check']} {f.get('quote', '')[:70]!r}: {f.get('problem', '')}")
    if todo and gated():
        p, n = precision()
        print(f"precision {p:.2f} over {n} scored findings is under {GATE}: suggest only, spans.json unchanged")
        for f in todo:
            print(f"  suggest  {f['check']} {f['fix']['action']} {f.get('quote', '')[:70]!r}: {f.get('problem', '')}")
        return 0
    log = d / "judge-log.jsonl"
    rnd = len(log.read_text().splitlines()) + 1 if log.exists() else 1
    applied, refused = apply_findings(d, todo, rnd)
    for a in applied:
        print(f"  applied  {a}")
    for r in refused:
        print(f"  REFUSED  {r}")
    with log.open("a") as fh:
        fh.write(json.dumps({"round": rnd, "blockers": sum(f["severity"] == "blocker" for f in findings),
                             "warns": sum(f["severity"] == "warn" for f in findings), "dropped": len(dropped),
                             "applied": len(applied), "summary": obj.get("summary", "")}) + "\n")
    if applied:
        print("spans.json changed: judge again (prompt, judge, apply), then build")
        return 3
    print("PASS: nothing left to apply" if not any(f["severity"] == "blocker" for f in findings)
          else "STOP: blockers left that no fix could apply; show them to the user")
    return 0


def demo():
    W = lambda s, t0=0.0: [{"text": w, "start": t0 + i * 0.5, "end": t0 + i * 0.5 + 0.4, "type": "word"}
                           for i, w in enumerate(s.split())]
    toks = W("so the first thing so the first thing is speed and wait sorry the price is low")
    global home
    real_home = home
    with tempfile.TemporaryDirectory() as tmp:
        home = lambda: Path(tmp) / "home"
        d = Path(tmp) / "edits" / "vid"
        d.mkdir(parents=True)
        (d / "words.raw.json").write_text(json.dumps(toks))
        spans = [{"text": "so the first thing", "kind": "retake", "occurrence": 1},
                 {"text": "speed and wait sorry", "kind": "meta"}]   # over-cut: "speed and" is a real line
        (d / "spans.json").write_text(json.dumps(spans))
        md, cuts = paper(spans, toks)
        assert "<<0>> so the first thing is <<1>> the price is low" in md, md
        assert "PAPER EDIT TO GRADE" in build_prompt(d) and "B1" in build_prompt(d)
        # a hallucinated quote and a bad index are dropped; B3 on a redundant cut is downgraded
        f, dr = validate({"findings": [
            {"check": "B3", "cut": 1, "quote": "is the price", "fix": {"action": "trim", "keep_words": "speed and"}},
            {"check": "B1", "cut": None, "quote": "never said", "fix": {"action": "add", "evidence": "x"}},
            {"check": "B2", "cut": 9, "quote": "the price", "fix": {"action": "restore"}}]}, cuts, md)
        assert len(f) == 1 and len(dr) == 2 and f[0]["severity"] == "blocker"
        # a quote across a join keeps its <<n>> marker (every broken-splice finding, the rubric's example)
        j, _ = validate({"findings": [{"check": "B2", "cut": 1, "quote": "first thing is <<1>> the price",
                                       "fix": {"action": "none"}}]}, cuts, md)
        assert len(j) == 1, j
        assert flat("x he ended up <<7>> he ended up being the y").find(flat("he ended up <<7>> he ended up being the")) > 0
        assert "words only, pauses not counted" in md and "removed" not in md.split("## What plays")[0], md
        (d / "paper-edit.md").write_text("# Paper edit\n\n- **CLIPPED by a pause cut, not asked for:** if\n")
        assert "CLIPPED by a pause cut, not asked for:** if (last build)" in build_prompt(d)
        (d / "paper-edit.md").unlink()
        rc = [dict(c, kind="redundant") for c in cuts]
        g, _ = validate({"findings": [{"check": "B3", "cut": 1, "quote": "the price", "fix": {"action": "restore"}}]}, rc, md)
        assert g[0]["check"] == "W5" and g[0]["fix"]["action"] == "none"
        # trim gives back the head of C1; spans.json still builds
        (d / "judge.json").write_text(json.dumps({"findings": f}))
        assert cmd_apply(d) == 3
        sp = spans_of(d)
        assert sp[1]["text"] == "wait sorry" and "after" in sp[1], sp
        assert "speed and <<1>> the price" in paper(sp, toks)[0]
        # an add of text an earlier round gave back is frozen; a W6 add is only suggested
        (d / "judge.json").write_text(json.dumps({"findings": [
            {"check": "B1", "cut": None, "quote": "speed and", "fix": {"action": "add", "evidence": "speed and"}},
            {"check": "W6", "cut": None, "quote": "is low", "fix": {"action": "add", "evidence": "low"}}]}))
        assert cmd_apply(d) == 0 and spans_of(d) == sp
        # restore deletes the span; an add cuts kept text with confidence low
        applied, _ = apply_findings(d, [{"check": "B3", "cut": 0, "fix": {"action": "restore"}},
                                        {"check": "B1", "cut": None, "fix": {"action": "add", "evidence": "the price is"}}], 9)
        assert len(applied) == 2, applied
        sp = spans_of(d)
        assert [s["text"] for s in sp] == ["wait sorry", "the price is"] and sp[1]["confidence"] == "low"
        # the user reverts the add ("keep the price is") and keeps the rest: 3 kept, 1 reverted
        (d / "spans.json").write_text(json.dumps(sp[:1]))
        s = score(d)
        assert (s["kept"], s["reverted"]) == (2, 1), s
        record(d, s)
        record(d, s)                     # a re-score replaces, never doubles
        assert precision() == (2 / 3, 3) and not gated()
        (home() / "judge-eval.jsonl").write_text(json.dumps({"edit": "old", "kept": 0, "reverted": 4}) + "\n")
        record(d, s)
        assert gated()                   # 2/7 under 0.60 with 7 scored: suggest only
        (d / "judge.json").write_text(json.dumps({"findings": [
            {"check": "B1", "cut": None, "quote": "speed and", "fix": {"action": "add", "evidence": "and"}}]}))
        before = spans_of(d)
        assert cmd_apply(d) == 0 and spans_of(d) == before
        assert extract_json('noise ```json\n{"findings": []}\n``` end') == {"findings": []}
    home = real_home
    print("demo ok")


def main():
    a = sys.argv[1:]
    if a == ["demo"]:
        return demo()
    if a == ["precision"]:
        p, n = precision()
        print(f"precision {'n/a' if p is None else f'{p:.2f}'} over {n} scored judge change(s); "
              + ("auto-apply OFF (suggest only)" if gated() else "auto-apply on"))
        return 0
    if len(a) < 2 or a[0] not in ("prompt", "apply", "score"):
        sys.exit(__doc__)
    d = Path(a[1])
    if not (d / "words.raw.json").exists():
        sys.exit(f"ERROR: no such file: {d / 'words.raw.json'}")
    if a[0] == "prompt":
        script = Path(a[a.index("--script") + 1]).read_text() if "--script" in a else None
        (d / "judge-prompt.md").write_text(build_prompt(d, script))
        print(d / "judge-prompt.md")
        return 0
    if a[0] == "apply":
        return cmd_apply(d, "--tighten" in a)
    s = score(d)
    for line in s["lines"]:
        print("  " + line)
    record(d, s)
    p, n = precision()
    print(f"{s['kept']} kept, {s['reverted']} reverted; precision {'n/a' if p is None else f'{p:.2f}'} over {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
