#!/usr/bin/env python3
"""Static checks on the plugin files: manifests, skill and agent frontmatter, shared docs. Stdlib only.

    python3 tests/check_plugins.py

Skill frontmatter follows https://agentskills.io/specification. `claude plugin validate --strict`
covers the Claude Code manifests; this covers what it does not, and runs where the CLI is missing.
Exit 1 with one line per problem.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
PATHS_LINE = "Paths: `${CLAUDE_SKILL_DIR}` means the folder containing this SKILL.md"
errors = []
KEY_URLS = ("https://console.typesafe.ai/keys", "https://aistudio.google.com/apikey",
            "https://elevenlabs.io/app/settings/api-keys", "https://modal.com/signup")
EVALS = [("plugins/ai-editor/evals/setup-plan-first", "AskUserQuestion"),
         ("plugins/ai-editor/evals/setup-plan-first", "what each costs"),
         ("plugins/ai-editor/evals/start-asks", "AskUserQuestion"),
         ("plugins/ai-editor/evals/launch-video-url", "AskUserQuestion"),
         ("plugins/ai-editor/evals/launch-video-url", "what the video must show"),
         ("plugins/ai-editor/evals/render-unapproved", "Approve"),
         ("plugins/ai-editor/evals/captions-too-small", "help everyone"),
         ("plugins/ai-editor/evals/improve-from-feedback", "improve"),
         ("plugins/ai-editor/evals/clips-fan-out", "clip-editor"),
         ("plugins/ai-editor/evals/paste-website-link", "product-video"),
         ("plugins/ai-editor/evals/paste-tiktok-profile", "creator-teardown"),
         ("plugins/ai-editor/evals/repo-no-plugin", "ai-editor@nextwork"),
         ("plugins/creator-teardown/evals/tear-down-handle", "AskUserQuestion")]


# What Claude must read before a skill's first step: SKILL.md plus every file it says to "Read `X` first".
# Each byte is a token cost on every run, so the talking-head path has a ceiling (bytes).
READ_BUDGET = {"start": 12000, "cut": 15000, "style-edit": 25000, "product-video": 30000}
READ_FIRST = re.compile(r"[Rr]ead \**`([^`]+)`\**:?\s+first")


def required_reads(skill_md):
    """SKILL.md and the files it marks "read first", resolved against the skill and plugin folders."""
    text = skill_md.read_text(encoding="utf-8")
    plugin = skill_md.parents[2]
    files = [skill_md]
    for ref in READ_FIRST.findall(text):
        ref = ref.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin)).replace("${CLAUDE_SKILL_DIR}", str(skill_md.parent))
        files.append(Path(ref) if Path(ref).is_absolute() else skill_md.parent / ref)
    return files


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        errors.append(f"{path}: no frontmatter")
        return {}, text
    head, body = text[4:].split("\n---\n", 1)
    # ponytail: one `key: value` per line is all these files use; nested YAML would need a real parser
    fm = dict(line.split(":", 1) for line in head.splitlines() if re.match(r"^[a-z-]+:", line))
    return {k.strip(): v.strip() for k, v in fm.items()}, body


MAX_LINES = 250
TRIGGERS = {}  # quoted trigger phrase -> skill that claims it


def check_skill(path):
    fm, body = frontmatter(path)
    vendored = (path.parent / "LICENSE").exists()
    # PRINCIPLES.md "Cost": a skill is read every time it fires; detail goes in references/
    lines = path.read_text(encoding="utf-8").count("\n")
    if not vendored and lines > MAX_LINES:
        errors.append(f"{path}: {lines} lines, over {MAX_LINES}; move detail into references/")
    # Two skills claiming the same quoted phrase both fire on it. Phrases after "Not for" are disclaimers.
    claims = re.split(r"\bnot for\b", fm.get("description", ""), flags=re.I)[0]
    for phrase in re.findall(r'"([^"]{3,})"', claims):
        key = re.sub(r"\s+", " ", phrase.lower().strip(" .,"))
        other = TRIGGERS.setdefault(key, path.parent.name)
        if other != path.parent.name:
            errors.append(f"{path}: trigger \"{phrase}\" is also claimed by {other}; give it to one skill")
    name = fm.get("name", "")
    if not NAME.match(name) or len(name) > 64 or name != path.parent.name:
        errors.append(f"{path}: name {name!r} must be kebab-case, at most 64 chars, and match its folder")
    if not 0 < len(fm.get("description", "")) <= 1024:
        errors.append(f"{path}: description must be 1-1024 chars (is {len(fm.get('description', ''))})")
    if not fm.get("license"):
        errors.append(f"{path}: no license")
    if not 0 < len(fm.get("compatibility", "")) <= 500:
        errors.append(f"{path}: compatibility must be 1-500 chars")
    if PATHS_LINE not in body:
        errors.append(f"{path}: missing the line {PATHS_LINE!r}")
    # every question goes in the question box (PRINCIPLES.md "Asking"); vendored skills keep their own text
    if not vendored and "AskUserQuestion" not in body:
        errors.append(f"{path}: never says to ask in the question box (AskUserQuestion)")
    for ref in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/((?:references|scripts)/[\w./-]+)", body):
        if not (path.parent / ref).exists():
            errors.append(f"{path}: points at {ref}, which does not exist")
    # PRINCIPLES.md "Speed": a skill that hands work to an agent names one that ships, with its model and tools set
    agents = path.parents[2] / "agents"
    for ref in set(re.findall(r"agents/([\w-]+)\.md", body) + re.findall(r"`([a-z]+(?:-[a-z]+)+)(?:\.md)?` agents?\b", body)):
        fm_a = frontmatter(agents / f"{ref}.md")[0] if (agents / f"{ref}.md").exists() else None
        if fm_a is None:
            errors.append(f"{path}: names the agent {ref}, but {agents / (ref + '.md')} does not exist")
        elif not (fm_a.get("model") and fm_a.get("tools")):
            errors.append(f"{agents / (ref + '.md')}: {path.parent.name} launches it, so it needs model and tools set")


def check_body(path):
    """Runs after every skill's triggers are in TRIGGERS."""
    _, body = frontmatter(path)
    # Quoting another skill's trigger without naming that skill acts on a request the router sends elsewhere.
    for m in re.finditer(r'"([^"]{3,80})"', body):
        key = re.sub(r"\s+", " ", m.group(1).lower().strip(" .,"))
        lines = body[body.rfind("\n", 0, m.start()) + 1:body.find("\n", m.end())]
        for phrase, owner in TRIGGERS.items():
            if owner != path.parent.name and (key == phrase or key.startswith(phrase + " ")) and not re.search(rf"\b{owner}\b", lines):
                errors.append(f"{path}: quotes \"{key}\", which routes to {owner}; name {owner} or drop it")
    # A `python3 "<script>"` command (not the run.py launcher) needs the Windows line the other skills have.
    if re.search(r'python3 "[^"\n]*(?<!run\.py)"', body) and not re.search(r"`python3`[^.]*`py`|`py`[^.]*`python3`", body):
        errors.append(f"{path}: runs `python3` with no line saying `py` on Windows")


def check_agent(path):
    fm, _ = frontmatter(path)
    for key in ("name", "description", "model", "tools"):
        if not fm.get(key):
            errors.append(f"{path}: no {key}")
    if fm.get("name") != path.stem:
        errors.append(f"{path}: name {fm.get('name')!r} must match the file name")
    # An agent prompt is not a skill: ${CLAUDE_PLUGIN_ROOT} and ${CLAUDE_SKILL_DIR} may reach it unexpanded.
    if "${CLAUDE_" in path.read_text(encoding="utf-8"):
        errors.append(f"{path}: uses a ${{CLAUDE_...}} path, which may not expand in an agent; have the caller pass the path")


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        errors.append(f"{path}: {e}")
        return {}


def main():
    market = load(ROOT / ".claude-plugin" / "marketplace.json")
    for entry in market.get("plugins", []):
        plugin = ROOT / entry["source"]
        manifest = load(plugin / ".claude-plugin" / "plugin.json")
        if manifest.get("version") != entry.get("version"):
            errors.append(f"{entry['name']}: version {entry.get('version')} in marketplace.json, "
                          f"{manifest.get('version')} in plugin.json")
        listed = {(plugin / s).resolve() for s in entry.get("skills", [])}
        found = {p.parent.resolve() for p in plugin.glob("skills/*/SKILL.md")}
        if listed != found:
            errors.append(f"{entry['name']}: marketplace skills list {sorted(map(str, listed))} "
                          f"!= skill folders {sorted(map(str, found))}")
        for skill in plugin.glob("skills/*/SKILL.md"):
            check_skill(skill)
        for skill in plugin.glob("skills/*/SKILL.md"):
            check_body(skill)
        for agent in plugin.glob("agents/*.md"):
            check_agent(agent)
        if (plugin / "hooks" / "hooks.json").exists():
            load(plugin / "hooks" / "hooks.json")
    for extra in (".codex-plugin/plugin.json", ".cursor-plugin/plugin.json"):
        for s in load(ROOT / extra).get("skills", []):
            if not (ROOT / s).is_dir():
                errors.append(f"{extra}: skills path {s} does not exist")

    # Opening the repo in Claude Code loads the editor from this folder (README "Start here", Way 1).
    proj = load(ROOT / ".claude" / "settings.json")
    src = proj.get("extraKnownMarketplaces", {}).get(market.get("name"), {}).get("source", {})
    if src != {"source": "directory", "path": "./"}:
        errors.append(".claude/settings.json: extraKnownMarketplaces must register this repo as a directory marketplace at ./")
    for entry in market.get("plugins", []):
        if proj.get("enabledPlugins", {}).get(f"{entry['name']}@{market.get('name')}") is not True:
            errors.append(f".claude/settings.json: enabledPlugins does not turn on {entry['name']}@{market.get('name')}")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for path in ("Way 1: open this folder in Claude Code", "/plugin marketplace add nextwork-projects/ai-video-editor",
                 "npx skills add nextwork-projects/ai-video-editor"):
        if path not in readme:
            errors.append(f"README.md: lost the start path {path!r}")
    case = (ROOT / "plugins/ai-editor/evals/repo-no-plugin/prompt.md").read_text(encoding="utf-8")
    if any(line.strip() not in case for line in (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()):
        errors.append("plugins/ai-editor/evals/repo-no-plugin/prompt.md: its copy of CLAUDE.md is out of date")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    if "plugins/ai-editor/skills/start/SKILL.md" not in agents[:600]:
        errors.append("AGENTS.md: the first lines must send an agent to the start skill")
    if agents != (ROOT / "GEMINI.md").read_text(encoding="utf-8"):
        errors.append("GEMINI.md: differs from AGENTS.md; copy it across")

    # Setup links straight to each key's page (PRINCIPLES.md "Asking"), so nobody hunts for it.
    setup = (ROOT / "plugins/ai-editor/skills/setup/SKILL.md").read_text(encoding="utf-8")
    for url in KEY_URLS:
        if url not in setup:
            errors.append(f"plugins/ai-editor/skills/setup/SKILL.md: lost the direct key link {url}")

    # The rules only an agent can follow are proven by evals (docs/feedback-matrix.md); they must not vanish.
    for case, grader in EVALS:
        d = ROOT / case
        if not (d / "prompt.md").exists() or not any(grader in g.read_text(encoding="utf-8") for g in d.glob("graders/*.md")):
            errors.append(f"{case}: missing, or no grader with {grader!r}")

    # The style.json contract is copied into creator-teardown so it ships with that plugin.
    def section(p):
        t = p.read_text(encoding="utf-8")
        return t[t.index("## style.json"):].split("\n## ", 1)[0].strip()
    a = ROOT / "plugins/ai-editor/skills/style-edit/references/contracts.md"
    b = ROOT / "plugins/creator-teardown/skills/creator-teardown/references/contracts.md"
    if section(a) != section(b):
        errors.append(f"{b}: style.json section differs from {a}; copy it across")

    # creator-teardown ships ai-editor's pins for what it installs, so its fix lines never go unpinned.
    sys.path.insert(0, str(ROOT / "plugins/ai-editor/lib"))
    from ai_editor import lock
    if not lock.TEARDOWN_LOCK.exists() or lock.TEARDOWN_LOCK.read_text(encoding="utf-8") != lock.subset(lock.TEARDOWN_ROOTS):
        errors.append(f"{lock.TEARDOWN_LOCK}: out of sync with requirements.lock; "
                      "run python3 plugins/ai-editor/lib/ai_editor/lock.py teardown")

    for p in ROOT.rglob("*"):
        # Vendored third-party skills (their own LICENSE file next to SKILL.md) stay verbatim.
        vendored = any((q / "LICENSE").exists() and (q / "SKILL.md").exists() for q in p.parents)
        if p.suffix in (".md", ".json", ".py", ".yml") and "node_modules" not in p.parts and ".git" not in p.parts and not vendored and "results" not in p.parts:
            if chr(0x2014) in p.read_text(encoding="utf-8", errors="ignore"):
                errors.append(f"{p}: contains an em dash")


    # Personal names and test-file names never ship. Stored as hashes so this file does not name them.
    import hashlib
    PRIVATE = {'8e3c16abe7053e2a', '73ea4d074e1e099e', '34517c83d2a1c75c', 'f2486dfd64f3a9a7', 'f68d9243b3f95c38', 'aef9b0cbd5d5c214', '9ba138bfd348ae5e', '085caa96e51d45cd', 'a4ba610f97acea14', '97599235748ff4a0', 'f5f9cc117d31860b'}
    for p in ROOT.rglob("*"):
        if p.suffix not in (".md", ".json", ".py", ".mjs", ".ts", ".tsx", ".yml") or "node_modules" in p.parts or ".git" in p.parts or p.name.endswith("lock.json"):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"\bIMG[-_](?!1234\b)\d{4}\b", text, re.I):
            errors.append(f"{p}: names a personal test file (IMG_####); say 'the sample take'")
        for w in set(re.findall(r"[a-z0-9]{4,}", text.lower())):
            if hashlib.sha256(w.encode()).hexdigest()[:16] in PRIVATE:
                errors.append(f"{p}: contains a private name; keep public files generic")
                break

    # Skills run scripts through run.py, which finds the venv under AI_EDITOR_HOME; a hardcoded home
    # path ignores it, and %USERPROFILE% does not expand in Git Bash.
    for p in [*ROOT.glob("plugins/*/skills/*/SKILL.md"), *ROOT.glob("plugins/*/skills/*/references/*.md"),
              *ROOT.glob("plugins/*/agents/*.md")]:
        if re.search(r"~/\.ai-video-editor/venv|%USERPROFILE%", p.read_text(encoding="utf-8")):
            errors.append(f"{p}: hardcodes the venv path; run scripts with lib/ai_editor/run.py")
    run_a = ROOT / "plugins/ai-editor/lib/ai_editor/run.py"
    run_b = ROOT / "plugins/creator-teardown/skills/creator-teardown/scripts/run.py"
    if run_a.read_bytes() != run_b.read_bytes():
        errors.append(f"{run_b}: differs from {run_a}; copy it across")

    for name, budget in READ_BUDGET.items():
        files = required_reads(ROOT / "plugins/ai-editor/skills" / name / "SKILL.md")
        missing = [str(f) for f in files if not f.exists()]
        total = sum(f.stat().st_size for f in files if f.exists())
        if missing or total > budget:
            errors.append(f"{name}: required reads {total} bytes (budget {budget}): "
                          + ", ".join(f"{f.name} {f.stat().st_size}" if f.exists() else f"{f} missing" for f in files))

    for e in errors:
        print("FAIL", e)
    print("plugins ok" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
