#!/usr/bin/env python3
"""Feedback in, a queue of fixes out: every place users' corrections land, read and grouped, repeats first.

    python3 improve.py collect [--edits DIR ...] [--no-gh] [--json]   the queue: suggestions.jsonl, taste
                                    regressions (rules.json), preview corrections (edits/*/corrections.jsonl)
                                    and open GitHub issues labelled feedback, grouped by rule, repeats first
    python3 improve.py log "<one line: the rule, the check, the test>"   a CHANGELOG.md entry under Unreleased
    python3 improve.py demo         self-check, no network

Reads only. Never writes the user's taste files; the only write is CHANGELOG.md in a checkout of the repo.
Stdlib only.
"""
import difflib
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
    out = [{"source": "suggestion", "rule": r.get("rule", ""), "what": r.get("what", ""), "owner": r.get("owner", ""),
            "ref": r.get("example", "")} for r in jsonl(HOME / "suggestions.jsonl")]
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
    if gh and shutil.which("gh") and not subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        res = subprocess.run(["gh", "issue", "list", "--repo", REPO, "--label", "feedback", "--state", "open",
                              "--json", "number,title,body", "--limit", "100"], capture_output=True, text=True)
        for i in json.loads(res.stdout or "[]") if not res.returncode else []:
            out.append({"source": "github issue", "rule": i["title"].removeprefix("Suggestion: "), "what": i["body"][:300],
                        "owner": "", "ref": f"#{i['number']}"})
    return out


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
        edits = [a[i + 1] for i, x in enumerate(a) if x == "--edits" and i + 1 < len(a)] or ["edits"]
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
