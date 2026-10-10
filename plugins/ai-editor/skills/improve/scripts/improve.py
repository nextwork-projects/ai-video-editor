#!/usr/bin/env python3
"""Feedback in, a queue of fixes out: every place users' corrections land, read and grouped, repeats first.

    python3 improve.py collect [--edits DIR ...] [--no-gh] [--json]   the queue: suggestions.jsonl, taste
                                    regressions (rules.json), preview corrections (edits/*/corrections.jsonl),
                                    review-page notes (*/review.json: marked would-help-everyone, or the same
                                    rule on two or more videos) and open GitHub issues labelled feedback,
                                    grouped by rule, repeats first. Default DIRs: edits, clips, product
    python3 improve.py log "<one line: the rule, the check, the test>"   a CHANGELOG.md entry under Unreleased
    python3 improve.py demo         self-check, no network

Reads only. Never writes the user's taste files; the only write is CHANGELOG.md in a checkout of the repo.
Stdlib only.
"""
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
REPO = "nextwork-projects/ai-video-editor"
SAME = 0.6     # rules this similar are the same feedback said again


def jsonl(p):
    try:
        return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
    except (OSError, ValueError):
        return []


def items(edits=(), gh=True):
    """Every piece of feedback as {"source", "rule", "what", "owner", "ref"}."""
    sug = jsonl(HOME / "suggestions.jsonl")
    out = [{"source": "suggestion", "rule": r.get("rule", ""), "what": r.get("what", ""), "owner": r.get("owner", ""),
            "ref": r.get("example", "")} for r in sug]
    try:
        rules = json.loads((HOME / "rules.json").read_text())
    except (OSError, ValueError):
        rules = []
    out += [{"source": "taste regression", "rule": r["rule"], "what": f"said again after it was applied ({len(r['regressions'])}x)",
             "owner": r.get("setting") or r.get("section", ""), "ref": f"rule #{r['id']}"} for r in rules if r.get("regressions")]
    for d in edits:
        for f in sorted(Path(d).glob("*/corrections.jsonl")):
            out += [{"source": "preview correction", "rule": r.get("what") or f"{r.get('change')} {r.get('target')}",
                     "what": f"{r.get('from')} -> {r.get('to')}", "owner": r.get("change", ""), "ref": f.parent.name} for r in jsonl(f)]
    out += review_notes(edits, {r.get("note") for r in sug})
    if gh and shutil.which("gh") and not subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        res = subprocess.run(["gh", "issue", "list", "--repo", REPO, "--label", "feedback", "--state", "open",
                              "--json", "number,title,body", "--limit", "100"], capture_output=True, text=True)
        for i in json.loads(res.stdout or "[]") if not res.returncode else []:
            out.append({"source": "github issue", "rule": i["title"].removeprefix("Suggestion: "), "what": i["body"][:300],
                        "owner": "", "ref": f"#{i['number']}"})
    return out


def review_notes(edits, suggested):
    """Review-page notes: the ones marked would-help-everyone (unless already a suggestion), and the ones whose
    rule (or text, when never learned) comes back on another video. One-off fixes are left out."""
    notes = []
    for d in edits:
        for f in sorted(Path(d).glob("*/review.json")):
            try:
                rv = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            for c in rv.get("comments", []):
                if c.get("taste") == "one-off" or not c.get("text"):
                    continue
                key = hashlib.sha256(f"{rv.get('name', f.parent.name)}#{c['id']}".encode()).hexdigest()[:12]
                notes.append({"source": "review note", "rule": c.get("rule") or c["text"], "what": c["text"],
                              "owner": "", "ref": f.parent.name, "everyone": c.get("taste") == "suggested", "key": key})
    same = lambda a, b: difflib.SequenceMatcher(None, a["rule"].lower(), b["rule"].lower()).ratio() >= SAME
    keep = [n for n in notes if (n["everyone"] and n["key"] not in suggested)
            or any(m["ref"] != n["ref"] and same(m, n) for m in notes)]
    return [{k: v for k, v in n.items() if k not in ("everyone", "key")} for n in keep]


def group(found):
    """Feedback grouped by rule (similar wording is the same rule), most repeated first."""
    groups = []
    for it in found:
        g = next((g for g in groups if difflib.SequenceMatcher(None, g["rule"].lower(), it["rule"].lower()).ratio() >= SAME), None)
        if g:
            g["items"].append(it)
        else:
            groups.append({"rule": it["rule"], "items": [it]})
    for g in groups:
        g["count"] = len(g["items"])
        g["sources"] = sorted({i["source"] for i in g["items"]})
        g["owner"] = next((i["owner"] for i in g["items"] if i["owner"]), "")
    return sorted(groups, key=lambda g: (-g["count"], g["rule"]))


def changelog(entry, root=None):
    """Append one line under '## Unreleased' in CHANGELOG.md at the repo root (created if missing)."""
    root = Path(root or subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or ".")
    if not (root / "plugins" / "ai-editor").is_dir():
        sys.exit(f"ERROR: {root} is not a checkout of the editor repo; run this from one")
    f = root / "CHANGELOG.md"
    text = f.read_text() if f.exists() else "# Changelog\n\nWhat changed for every user, newest first.\n"
    if "\n## Unreleased\n" not in text:
        head, sep, rest = text.partition("\n## ")
        text = head.rstrip() + "\n\n## Unreleased\n\n" + (sep.lstrip("\n") + rest if sep else "")
    text = text.replace("\n## Unreleased\n\n", f"\n## Unreleased\n\n- {entry.strip()}\n", 1)
    f.write_text(text.rstrip() + "\n")
    return f


def demo():
    global HOME
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        HOME = Path(t) / "home"
        HOME.mkdir()
        (HOME / "suggestions.jsonl").write_text(
            json.dumps({"rule": "Zooms ease in over at least 0.5 s", "what": "snap", "owner": "quality.py", "example": ""}) + "\n"
            + json.dumps({"rule": "Zooms ease in over at least half a second", "what": "jerk", "owner": "", "example": ""}) + "\n")
        (HOME / "rules.json").write_text(json.dumps([{"id": 3, "section": "Captions", "rule": "Captions bigger", "setting": "captions.size_pct",
                                                      "regressions": [{"edit": "a", "at": "x"}]},
                                                     {"id": 4, "section": "Cut", "rule": "Tighter", "regressions": []}]))
        ed = Path(t) / "edits" / "vid"
        ed.mkdir(parents=True)
        (ed / "corrections.jsonl").write_text(json.dumps({"change": "card.move", "target": "c1", "from": 1, "to": 2,
                                                          "what": "zooms ease in over at least 0.5 s"}) + "\n")
        g = group(items([Path(t) / "edits"], gh=False))
        assert g[0]["count"] == 3 and g[0]["owner"] == "quality.py" and g[0]["sources"] == ["preview correction", "suggestion"], g[0]
        assert [x["rule"] for x in g[1:]] == ["Captions bigger"], g      # a rule never said twice is not feedback
        # review-page notes (review.py learn): a would-help-everyone note, one already a suggestion (counted
        # once), the same rule on two videos, a rule on one video only and a one-off fix
        def review(name, comments):
            (Path(t) / "clips" / name).mkdir(parents=True)
            (Path(t) / "clips" / name / "review.json").write_text(json.dumps({"name": name, "comments": comments}))
        (HOME / "suggestions.jsonl").open("a").write(json.dumps({"rule": "Logos stay small", "note": hashlib.sha256(
            b"v2#2").hexdigest()[:12]}) + "\n")
        review("v1", [{"id": 1, "text": "captions are tiny", "rule": "Text readable on a small screen", "taste": 4},
                      {"id": 2, "text": "the music drowns me", "rule": "Music sits under the voice", "taste": "suggested"},
                      {"id": 3, "text": "cut the um at 0:12", "taste": "one-off"}])
        review("v2", [{"id": 1, "text": "captions too small again", "rule": "Text readable on small screens"},
                      {"id": 2, "text": "logo huge", "rule": "Logos stay small", "taste": "suggested"},
                      {"id": 3, "text": "slower here", "rule": "Slow the cut on this one", "taste": "video-only"}])
        g = {x["rule"]: x for x in group(items([Path(t) / "edits", Path(t) / "clips"], gh=False))}
        assert g["Text readable on a small screen"]["count"] == 2 and g["Text readable on a small screen"]["sources"] == ["review note"], g
        assert g["Music sits under the voice"]["count"] == 1 and g["Logos stay small"]["count"] == 1, g
        assert not {"Slow the cut on this one", "cut the um at 0:12"} & set(g), g
        root = Path(t) / "repo"
        (root / "plugins" / "ai-editor").mkdir(parents=True)
        changelog("quality.py: zooms faster than 0.5 s fail (demo assert)", root)
        f = changelog("record.mjs: create is on the deny list (tests/test_record.mjs)", root)
        text = f.read_text()
        assert text.startswith("# Changelog") and text.count("## Unreleased") == 1, text
        assert text.index("record.mjs") < text.index("quality.py"), text      # newest first
        assert not (HOME / "taste.md").exists()
    print("demo ok")


def main():
    a = sys.argv[1:]
    if a[:1] == ["demo"]:
        return demo()
    if a[:1] == ["log"] and len(a) == 2:
        return print(changelog(a[1]))
    if a[:1] == ["collect"]:
        edits = [a[i + 1] for i, x in enumerate(a) if x == "--edits" and i + 1 < len(a)] or ["edits", "clips", "product"]
        g = group(items(edits, "--no-gh" not in a))
        if "--json" in a:
            return print(json.dumps(g, indent=1))
        for n, x in enumerate(g, 1):
            print(f"{n}. [{x['count']}x, {', '.join(x['sources'])}] {x['rule']}" + (f"  (owner: {x['owner']})" if x["owner"] else ""))
            for i in x["items"][:3]:
                print(f"     {i['source']}: {i['what'][:120]}" + (f" ({i['ref']})" if i["ref"] else ""))
        return print(f"{len(g)} rule(s) from {sum(x['count'] for x in g)} piece(s) of feedback" if g else "No feedback yet.")
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
