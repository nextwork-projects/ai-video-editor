#!/usr/bin/env python3
"""The user's own taste: every correction they give, kept so they never give it twice.

    python3 taste.py add <section> "<rule>" [--set key.path=value] [--video edits/NAME] [--edit edits/NAME]
                                  a correction as a rule. Same rule again = the old one is edited, never a
                                  second copy. --set: the setting the scripts read. --video: only this video
                                  (default: every video). --edit: the edit it was said on (for the report).
    python3 taste.py report       every rule: times applied, times corrected, the last edit where the user
                                  had to correct it again after it was applied (a regression)
    python3 taste.py show [--edit edits/NAME]   taste.md + taste.json; with --edit, also that video's own
                                  rules, and the word rules count as applied to it
    python3 taste.py forget <id>  remove a rule (and its setting and its taste.md line)
    python3 taste.py rule <section> "<rule>"      a word rule into taste.md only (older form of add)
    python3 taste.py set <key.path> <value>       set a setting in taste.json (value parsed as JSON if it can be)
    python3 taste.py unset <key.path>
    python3 taste.py get                          taste.json as JSON
    python3 taste.py suggest "<what was wrong>" "<the general rule>" --owner <skill or check> [--example "..."]
                                  a correction that would help every user: one line in suggestions.jsonl,
                                  scrubbed of paths, emails, handles and file names (the improve skill reads it)
    python3 taste.py issue [--yes]                the latest suggestion as a GitHub issue on the editor's repo:
                                  without --yes, only shows it; with --yes (after the user said yes), gh opens it
    python3 taste.py demo                         self-check

Files in ~/.ai-video-editor/ (AI_EDITOR_HOME overrides; outside the plugin, so updates never wipe them):
  taste.md    rules in plain words, one bullet each, under ## Cut / Captions / Visuals / Sound / Layout.
              Claude reads it before every edit. Every-video rules only.
  taste.json  settings the scripts read. They win over the creator's measured style.json:
              {"cut": {"max_pause": 0.2}, "captions": {"size_pct": 7}, "zoom": {"per_min": 4},
               "sfx": false, "layout": {"mode": "split"}}
  rules.json  the same rules with their history: [{"id", "section", "rule", "setting", "value", "scope"
              ("all" | "video:<name>"), "corrections": [{"edit", "at", "rule", "value"}], "applied",
              "applied_in": [edit names], "since_fix", "regressions": [{"edit", "at"}]}]
  suggestions.jsonl  corrections the user said would help everyone: {"at", "what", "rule", "owner", "example"}

How a rule is applied: plan.py and build_timeline.py call load_json() (their only hook). It returns
taste.json plus the "this video only" settings of the edit being worked on, and counts every setting
rule it hands over as applied to that edit. Word rules are counted by `show --edit`.
Stdlib only. Exit codes: 0 ok, 1 error, 2 usage
"""
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
SECTIONS = ["Cut", "Captions", "Visuals", "Sound", "Layout"]
SAME = 0.8   # rules this similar are the same rule said again: replace, don't append
KEEP_EDITS = 30   # applied_in keeps the last this many edit names


def md_path():
    return HOME / "taste.md"


def json_path():
    return HOME / "taste.json"


def rules_path():
    return HOME / "rules.json"


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def read_json():
    """taste.json as it is on disk. No counting: for the CLI and for writes."""
    p = json_path()
    return json.loads(p.read_text()) if p.exists() else {}


def save_json(data):
    HOME.mkdir(parents=True, exist_ok=True)
    json_path().write_text(json.dumps(data, indent=1))


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


def similar(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SAME


def add_rule(section, rule):
    """A word rule into taste.md. A near-duplicate is replaced instead of piling up.
    Returns ('added' | 'replaced: <old>', md)."""
    section = section.strip().title()
    md = load_md()
    rules = md.setdefault(section, [])
    for i, old in enumerate(rules):
        if similar(old, rule):
            rules[i] = rule
            save_md(md)
            return f"replaced: {old}", md
    rules.append(rule)
    save_md(md)
    return "added", md


def drop_rule(section, rule):
    md = load_md()
    if rule in md.get(section, []):
        md[section].remove(rule)
        save_md(md)


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


# ---------- structured rules ----------

def new_rule(i, section, rule, setting, value, scope):
    return {"id": i, "section": section, "rule": rule, "setting": setting, "value": value, "scope": scope,
            "corrections": [], "applied": 0, "applied_in": [], "since_fix": 0, "regressions": []}


def load_rules():
    """rules.json. Before the first one, taste.md's bullets are the rules (every video, never applied)."""
    p = rules_path()
    if p.exists():
        return json.loads(p.read_text())
    md = [(s, r) for s, rs in load_md().items() for r in rs]
    return [new_rule(i, s, r, None, None, "all") for i, (s, r) in enumerate(md, 1)]


def save_rules(rules):
    HOME.mkdir(parents=True, exist_ok=True)
    tmp = rules_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(rules, indent=1))
    tmp.replace(rules_path())   # a crash mid-write never leaves half a file


def edit_name(edit):
    return Path(edit).resolve().name if edit else None


def find(rules, section, rule, setting, scope):
    """The rule this correction repeats: same scope, and the same setting or near-identical words."""
    for r in rules:
        if r["scope"] != scope:
            continue
        if setting and r.get("setting") == setting:
            return r
        if r["section"] == section and similar(r["rule"], rule):
            return r
    return None


def add(section, rule, setting=None, value=None, scope="all", edit=None):
    """Capture one correction. Returns (status, rule): 'added', 'updated', or 'regression' (the rule
    was applied at least once since it was last corrected, and the user had to say it again)."""
    section = section.strip().title()
    edit = edit_name(edit)
    rules = load_rules()
    r = find(rules, section, rule, setting, scope)
    status = "added"
    if r is None:
        r = new_rule(max((x["id"] for x in rules), default=0) + 1, section, rule, setting, value, scope)
        rules.append(r)
    else:
        status = "regression" if r["since_fix"] > 0 else "updated"
        if status == "regression":
            r["regressions"].append({"edit": edit, "at": now()})
        if scope == "all":
            drop_rule(r["section"], r["rule"])
            if setting and r.get("setting") not in (None, setting):
                save_json(unset_key(read_json(), r["setting"]))
        r.update(section=section, rule=rule)
        if setting:
            r.update(setting=setting, value=value)
    r["corrections"].append({"edit": edit, "at": now(), "rule": rule, "value": value})
    r["since_fix"] = 0
    if scope == "all":
        add_rule(section, rule)
        if r.get("setting"):
            save_json(set_key(read_json(), r["setting"], r["value"]))
    save_rules(rules)
    return status, r


def forget(rule_id):
    rules = load_rules()
    r = next((x for x in rules if x["id"] == rule_id), None)
    if r is None:
        return None
    rules.remove(r)
    save_rules(rules)
    if r["scope"] == "all":
        drop_rule(r["section"], r["rule"])
        if r.get("setting"):
            save_json(unset_key(read_json(), r["setting"]))
    return r


def mark_applied(rules, which, edit):
    for r in rules:
        if which(r):
            r["applied"] += 1
            r["since_fix"] += 1
            if edit and edit not in r["applied_in"]:
                r["applied_in"] = (r["applied_in"] + [edit])[-KEEP_EDITS:]


def guess_edit(argv):
    """The edit folder a script was pointed at: an argument that is (or sits in) a folder holding
    the cut's files. plan.py gets edits/NAME/words.json, build_timeline.py gets edits/NAME."""
    for a in argv:
        p = Path(a)
        d = p if p.is_dir() else p.parent
        if any((d / f).exists() for f in ("words.raw.json", "cut.mp4", "decisions.json")):
            return d
    return None


# Which settings each caller acts on, so a plan.py run does not count the cut's pause rule.
CALLERS = {"build_timeline.py": lambda k: k.startswith("cut."),
           "plan.py": lambda k: not k.startswith("cut.")}


def load_json(edit_dir=None, count=True):
    """THE HOOK. What plan.py and build_timeline.py read: taste.json, plus the "this video only"
    settings of the edit being worked on (found from the script's arguments when not passed).
    Counts each setting rule it hands over as applied to that edit."""
    data = read_json()
    if not rules_path().exists():
        return data
    edit = Path(edit_dir) if edit_dir else guess_edit(sys.argv[1:])
    name = edit.resolve().name if edit else None
    rules = load_rules()
    mine = [r for r in rules if r.get("setting") and r["scope"] in ("all", f"video:{name}")]
    for r in mine:
        if r["scope"] != "all":
            data = set_key(data, r["setting"], r["value"])
    if count:
        # ponytail: caller found by script name; give load_json a key filter if a third caller appears
        acts = CALLERS.get(Path(sys.argv[0]).name, lambda k: True)
        ids = {r["id"] for r in mine if acts(r["setting"])}
        mark_applied(rules, lambda r: r["id"] in ids, name)
        save_rules(rules)
    return data


def show(edit=None):
    """taste.md and taste.json; with an edit, also that video's own rules, and the word rules count
    as applied to it (Claude follows them in that edit)."""
    out = [md_path().read_text() if md_path().exists() else "(no taste.md yet)", json.dumps(read_json(), indent=1)]
    name = edit_name(edit)
    if name and (rules_path().exists() or md_path().exists()):
        rules = load_rules()
        own = [r for r in rules if r["scope"] == f"video:{name}"]
        if own:
            out.append(f"## This video only ({name})\n" + "\n".join(f"- {r['rule']}" for r in own))
        mark_applied(rules, lambda r: not r.get("setting") and r["scope"] in ("all", f"video:{name}"), name)
        save_rules(rules)
    return "\n".join(out)


def report():
    rules = load_rules()
    if not rules:
        return "No rules yet. Correct an edit and the editor saves it here."
    order = lambda x: (SECTIONS.index(x["section"]) if x["section"] in SECTIONS else 9, x["id"])
    lines = []
    for r in sorted(rules, key=order):
        setting = f"  [{r['setting']} = {json.dumps(r['value'])}]" if r.get("setting") else ""
        scope = "every video" if r["scope"] == "all" else r["scope"].replace("video:", "only ")
        reg = r["regressions"][-1] if r["regressions"] else None
        lines.append(f"#{r['id']} {r['section']}: {r['rule']}{setting}")
        lines.append(f"    {scope}. applied {r['applied']}x in {len(r['applied_in'])} edit(s), "
                     f"corrected {len(r['corrections'])}x. "
                     + (f"Corrected again after it was applied: {len(r['regressions'])}x, last on "
                        f"{reg['edit'] or 'an edit'} ({reg['at'][:10]})." if reg else "Never had to be said twice."))
    regs = [r for r in rules if r["regressions"]]
    lines += ["", f"{len(rules)} rules, {sum(r['applied'] for r in rules)} applications, "
                  f"{len(regs)} said twice after being applied" + (": " + ", ".join(f"#{r['id']}" for r in regs) if regs else ".")]
    return "\n".join(lines)


REPO = "nextwork-projects/ai-video-editor"
MEDIA = r"[\w.-]+\.(?:mov|mp4|m4v|mkv|webm|avi|wav|mp3|m4a|aac|png|jpe?g|heic|gif)"


def scrub(text):
    """A suggestion leaves the computer only without the user's media or names: paths, file names, emails,
    @handles and URLs become placeholders."""
    text = text.replace(str(Path.home()), "~")
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", text)
    text = re.sub(r"https?://\S+", "<link>", text)
    text = re.sub(r"(?<![\w])@[\w.]{2,}", "@creator", text)
    text = re.sub(r"(?<!\S)(?:~|\.{1,2})?(?:/[\w.-]+){2,}/?", "<path>", text)
    return re.sub(MEDIA, "<file>", text, flags=re.I)


def suggestions_path():
    return HOME / "suggestions.jsonl"


def suggest(what, rule, owner, example=""):
    """A correction the user said would help everyone, as a general rule for the maintainers."""
    row = {"at": now(), "what": scrub(what), "rule": scrub(rule), "owner": scrub(owner), "example": scrub(example)}
    HOME.mkdir(parents=True, exist_ok=True)
    with open(suggestions_path(), "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def issue(yes=False):
    """The latest suggestion as a GitHub issue. Shows it unless yes; opens it with gh only when gh is logged in."""
    rows = [json.loads(x) for x in suggestions_path().read_text().splitlines() if x.strip()] if suggestions_path().exists() else []
    if not rows:
        return "No suggestions yet."
    r = rows[-1]
    title = f"Suggestion: {r['rule'][:80]}"
    body = (f"**What was wrong:** {r['what']}\n\n**The general rule:** {r['rule']}\n\n**Owner:** {r['owner']}\n\n"
            + (f"**Example:** {r['example']}\n\n" if r["example"] else "") + "Sent from the AI video editor's taste skill.")
    if not yes:
        return f"{title}\n\n{body}"
    if not shutil.which("gh") or subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        return "gh is not logged in: the suggestion stays in suggestions.jsonl."
    cmd = ["gh", "issue", "create", "--repo", REPO, "--title", title, "--body", body]
    res = subprocess.run(cmd + ["--label", "feedback"], capture_output=True, text=True)
    if res.returncode:      # the label may not exist on the repo
        res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout.strip() or res.stderr.strip()


def demo():
    global HOME
    old_argv = sys.argv
    with tempfile.TemporaryDirectory() as d:
        HOME = Path(d) / "home"
        assert add_rule("visuals", "Logos smaller than the captions")[0] == "added"
        assert add_rule("visuals", "Logos smaller than the caption")[0].startswith("replaced")
        assert load_md()["Visuals"] == ["Logos smaller than the caption"]
        t = set_key({}, "captions.size_pct", 7)
        assert merge({"captions": {"size_pct": 4, "y_pct": 68}, "sfx": True}, {**t, "sfx": False}) == \
            {"captions": {"size_pct": 7, "y_pct": 68}, "sfx": False}
        assert unset_key(t, "captions.size_pct") == {"captions": {}}

        # taste.md's older bullet becomes a tracked rule
        assert [r["rule"] for r in load_rules()] == ["Logos smaller than the caption"]
        ed = Path(d) / "edits" / "vid-a"   # an edit folder as the cut leaves it
        ed.mkdir(parents=True)
        (ed / "cut.mp4").write_bytes(b"")
        st, r = add("captions", "Captions bigger", "captions.size_pct", 6, edit=ed)
        assert st == "added" and read_json() == {"captions": {"size_pct": 6}} and "Captions bigger" in load_md()["Captions"]
        # said again before it was ever applied: the same rule edited, no second copy
        st, r = add("captions", "Captions a touch larger", "captions.size_pct", 6.5, edit=ed)
        assert st == "updated" and len([x for x in load_rules() if x.get("setting")]) == 1
        assert load_md()["Captions"] == ["Captions a touch larger"] and read_json()["captions"]["size_pct"] == 6.5
        # plan.py's real call shape counts the caption rule, not the cut's pause rule
        add("cut", "Cut is too tight, leave more air", "cut.max_pause", 0.25, edit=ed)
        sys.argv = ["plan.py", str(Path(d) / "style.json"), str(ed / "words.json")]
        assert load_json() == {"captions": {"size_pct": 6.5}, "cut": {"max_pause": 0.25}}
        rs = {x["setting"]: x for x in load_rules() if x.get("setting")}
        assert rs["captions.size_pct"]["applied"] == 1 and rs["captions.size_pct"]["applied_in"] == ["vid-a"]
        assert rs["cut.max_pause"]["applied"] == 0
        sys.argv = ["build_timeline.py", "/raw/take.mov", str(ed)]
        load_json()
        assert {x["setting"]: x["applied"] for x in load_rules() if x.get("setting")} == {"captions.size_pct": 1, "cut.max_pause": 1}
        # "this video only": in that edit's settings, never in taste.json, taste.md or another edit
        add("sound", "Quieter whooshes on this one", "sfx_db", -30, scope="video:vid-b", edit="vid-b")
        assert "sfx_db" not in read_json() and "Quieter whooshes on this one" not in load_md()["Sound"]
        eb = Path(d) / "edits" / "vid-b"
        eb.mkdir()
        (eb / "cut.mp4").write_bytes(b"")
        sys.argv = ["plan.py", "s.json", str(eb / "words.json")]
        assert load_json()["sfx_db"] == -30 and "sfx_db" not in load_json(ed, count=False)
        # the caption size is corrected again on the next video, after being applied: a regression
        st, r = add("captions", "Captions bigger again", "captions.size_pct", 7, edit=eb)
        assert st == "regression" and r["regressions"][-1]["edit"] == "vid-b" and r["since_fix"] == 0
        assert len(r["corrections"]) == 3 and read_json()["captions"]["size_pct"] == 7
        assert load_md()["Captions"] == ["Captions bigger again"]
        # word rules count when Claude reads them for an edit
        show(ed)
        assert next(x for x in load_rules() if x["rule"].startswith("Logos"))["applied_in"] == ["vid-a"]
        rep = report()
        assert "corrected 3x" in rep and "last on vid-b" in rep and "only vid-b" in rep, rep
        assert "said twice after being applied: #2" in rep, rep
        # forget takes the setting and the bullet with it
        forget(next(x for x in load_rules() if x.get("setting") == "cut.max_pause")["id"])
        assert "max_pause" not in read_json().get("cut", {}) and load_md()["Cut"] == []
        # a suggestion for everyone carries the rule, never the user's files, names or links
        r = suggest(f"zoom snapped on {Path.home()}/Movies/take 3.mov for @someone", "Zooms ease over at least 0.5 s",
                    "style-edit quality.py", "jane@example.org saw it on https://example.com/x, IMG.MOV")
        assert "Movies" not in json.dumps(r) and "@someone" not in r["what"] and "<file>" in r["example"], r
        assert "<email>" in r["example"] and "<link>" in r["example"] and r["rule"] == "Zooms ease over at least 0.5 s", r
        assert scrub("captions at 1/3 height") == "captions at 1/3 height"
        assert issue().startswith("Suggestion: Zooms ease") and "**Owner:** style-edit quality.py" in issue()
    sys.argv = old_argv
    print("demo ok")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(2)
    cmd = a[0]
    flag = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
    if cmd == "demo":
        return demo()
    if cmd == "show":
        print(show(flag("--edit")))
    elif cmd == "report":
        print(report())
    elif cmd == "get":
        print(json.dumps(read_json()))
    elif cmd == "add" and len(a) >= 3:
        setting = value = None
        if flag("--set"):
            setting, _, raw = flag("--set").partition("=")
            value = parse(raw)
        video = flag("--video")
        scope = f"video:{edit_name(video)}" if video else "all"
        status, r = add(a[1], a[2], setting, value, scope, flag("--edit") or video)
        print(f"{status}: #{r['id']} {r['section']}: {r['rule']}" + (f" [{setting} = {json.dumps(value)}]" if setting else "")
              + f" ({'this video only' if video else 'every video'}) -> {rules_path()}")
        if status == "regression":
            print(f"note: already applied {r['applied']}x, and it had to be said again. Check why it did not "
                  "hold: a setting no script reads, or a word rule too vague to follow.")
    elif cmd == "suggest" and len(a) >= 3 and flag("--owner"):
        r = suggest(a[1], a[2], flag("--owner"), flag("--example") or "")
        print(f"suggested: {r['rule']} ({r['owner']}) -> {suggestions_path()}")
    elif cmd == "issue":
        print(issue("--yes" in a))
    elif cmd == "forget" and len(a) == 2:
        r = forget(int(a[1]))
        print(f"forgot #{a[1]}: {r['rule']}" if r else f"no rule #{a[1]}")
        sys.exit(0 if r else 1)
    elif cmd == "rule" and len(a) == 3:
        what, _ = add_rule(a[1], a[2])
        print(f"{what} -> {md_path()}")
    elif cmd in ("set", "unset") and len(a) >= 2:
        data = read_json()
        data = set_key(data, a[1], parse(a[2])) if cmd == "set" and len(a) == 3 else unset_key(data, a[1])
        save_json(data)
        print(f"{cmd} {a[1]} -> {json_path()}")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
