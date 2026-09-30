#!/usr/bin/env python3
"""The user's own taste: every correction they give, kept so they never give it twice.

    python3 taste.py show                         both files
    python3 taste.py rule <section> "<rule>"      add a rule to taste.md (a near-duplicate is replaced)
    python3 taste.py set <key.path> <value>       set a setting in taste.json (value parsed as JSON if it can be)
    python3 taste.py unset <key.path>
    python3 taste.py get                          taste.json as JSON (what the scripts read)
    python3 taste.py demo                         self-check

Two files in ~/.ai-video-editor/ (outside the plugin, so updates never wipe them):
  taste.md    rules in plain words, one bullet each, under ## Cut / Captions / Visuals / Sound / Layout.
              Claude reads it before every edit.
  taste.json  settings the scripts read. They win over the creator's measured style.json:
              {"cut": {"max_pause": 0.2}, "captions": {"size_pct": 7}, "zoom": {"per_min": 4},
               "sfx": false, "layout": "split"}
Stdlib only. Exit codes: 0 ok, 1 error, 2 usage
"""
import difflib
import json
import os
import sys
import tempfile
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
SECTIONS = ["Cut", "Captions", "Visuals", "Sound", "Layout"]
SAME = 0.8   # rules this similar are the same rule said again: replace, don't append


def md_path():
    return HOME / "taste.md"


def json_path():
    return HOME / "taste.json"


def load_json():
    p = json_path()
    return json.loads(p.read_text()) if p.exists() else {}


def load_md():
    """{section: [rules]} in SECTIONS order."""
    out = {s: [] for s in SECTIONS}
    cur = None
    p = md_path()
    for line in (p.read_text().splitlines() if p.exists() else []):
        if line.startswith("## "):
            cur = line[3:].strip().title()
            out.setdefault(cur, [])
        elif line.startswith("- ") and cur:
            out[cur].append(line[2:].strip())
    return out


def save_md(md):
    HOME.mkdir(parents=True, exist_ok=True)
    lines = ["# My editing taste", "",
             "Rules I've given the AI video editor. It reads this before every edit.", ""]
    for s, rules in md.items():
        lines += [f"## {s}", ""] + [f"- {r}" for r in rules] + [""]
    md_path().write_text("\n".join(lines))


def add_rule(section, rule):
    """Returns ('added' | 'replaced <old>', md)."""
    section = section.strip().title()
    md = load_md()
    rules = md.setdefault(section, [])
    for i, old in enumerate(rules):
        if difflib.SequenceMatcher(None, old.lower(), rule.lower()).ratio() >= SAME:
            rules[i] = rule
            save_md(md)
            return f"replaced: {old}", md
    rules.append(rule)
    save_md(md)
    return "added", md


def set_key(data, path, value):
    *head, last = path.split(".")
    cur = data
    for k in head:
        cur = cur.setdefault(k, {})
    cur[last] = value
    return data


def unset_key(data, path):
    *head, last = path.split(".")
    cur = data
    for k in head:
        cur = cur.get(k, {})
    cur.pop(last, None)
    return data


def merge(style, taste):
    """taste.json over a style.json: nested dicts merge, anything else is replaced."""
    out = dict(style)
    for k, v in taste.items():
        out[k] = merge(out.get(k) or {}, v) if isinstance(v, dict) and isinstance(out.get(k), (dict, type(None))) else v
    return out


def parse(v):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def demo():
    global HOME
    with tempfile.TemporaryDirectory() as d:
        HOME = Path(d)
        assert add_rule("visuals", "Logos smaller than the captions")[0] == "added"
        assert add_rule("visuals", "Logos smaller than the caption")[0].startswith("replaced")
        assert load_md()["Visuals"] == ["Logos smaller than the caption"]
        t = set_key({}, "captions.size_pct", 7)
        assert merge({"captions": {"size_pct": 4, "y_pct": 68}, "sfx": True}, {**t, "sfx": False}) == \
            {"captions": {"size_pct": 7, "y_pct": 68}, "sfx": False}
        assert unset_key(t, "captions.size_pct") == {"captions": {}}
    print("demo ok")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    cmd = a[0]
    if cmd == "demo":
        return demo()
    if cmd == "show":
        print(md_path().read_text() if md_path().exists() else "(no taste.md yet)")
        print(json.dumps(load_json(), indent=1))
    elif cmd == "get":
        print(json.dumps(load_json()))
    elif cmd == "rule" and len(a) == 3:
        what, _ = add_rule(a[1], a[2])
        print(f"{what} -> {md_path()}")
    elif cmd in ("set", "unset") and len(a) >= 2:
        data = load_json()
        data = set_key(data, a[1], parse(a[2])) if cmd == "set" and len(a) == 3 else unset_key(data, a[1])
        HOME.mkdir(parents=True, exist_ok=True)
        json_path().write_text(json.dumps(data, indent=1))
        print(f"{cmd} {a[1]} -> {json_path()}")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
