#!/usr/bin/env python3
"""The steps a product film cannot skip, enforced in code (product.py calls these):

    the brief       plan refuses without brief.json (the answers to the brief questions, SKILL.md step 1)
    the approval    render refuses unless `product.py approve` stamped this exact plan and story, after the
                    animatic (or stills) sheet was made and the user chose Approve in the question box
    the music       a plan on the user's own track refuses unless audio/music.json records who holds the rights
    the story order hook first, end last, every result after an action, payoff just before the end;
                    making something before discovering anything is a WARN (references/story.md)
    the length      about 8 s a use case unless the user or the story asked for one

    python3 gates.py demo     self-check, no network
"""
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))

BRIEF_KEYS = ("must_show", "audience", "action")
RIGHTS = ("own", "cc", "licensed", "unsure")
DISCOVER = re.compile(r"\b(search|browse|explore|learn|find|discover|template|guide|roadmap|demo)", re.I)
MAKE = re.compile(r"\b(create|build|prompt|generate|write|new|make|configure)", re.I)


def need_brief(d):
    """None when brief.json holds the brief's answers, else what to do."""
    f = Path(d) / "brief.json"
    try:
        b = json.loads(f.read_text())
    except (OSError, ValueError):
        return f"no brief: ask the brief in the question box (SKILL.md step 1) and write {f} first"
    missing = [k for k in BRIEF_KEYS if k not in b]
    return f"{f} has no {', '.join(missing)}: ask those in the question box first" if missing else None


def stamp(d, plan_name):
    """What an approval covers: the plan and the story it was made from, byte for byte."""
    d = Path(d)
    plan = json.loads((d / plan_name).read_text())
    h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
    return {"plan": h(d / plan_name), "story": h(d / plan.get("story", "story.json"))}


def tag_of(plan_name):
    return Path(plan_name).stem[len("plan-"):]


def approve(d, plan_name):
    """Stamp the plan as approved. Only after the user chose Approve in the question box on the sheet."""
    d, tag = Path(d), tag_of(plan_name)
    if not any((d / f"{k}-{tag}" / "sheet.png").exists() for k in ("animatic", "stills")):
        sys.exit(f"ERROR: no animatic-{tag}/sheet.png: run product.py animatic, show it, ask Approve in the question box")
    out = d / f"approved-{tag}.json"
    out.write_text(json.dumps({**stamp(d, plan_name), "at": datetime.datetime.now().isoformat(timespec="seconds")}, indent=1))
    return out


def need_approval(d, plan_name):
    """None when this exact plan and story were approved, else why the render must wait."""
    d, tag = Path(d), tag_of(plan_name)
    f = d / f"approved-{tag}.json"
    if not f.exists():
        return f"plan-{tag} is not approved: show the animatic, ask Approve in the question box, then product.py approve"
    got = json.loads(f.read_text())
    if {k: got.get(k) for k in ("plan", "story")} != stamp(d, plan_name):
        return f"plan-{tag} or its story changed after it was approved: show the new animatic and ask again"
    return None


def need_licence(d, own):
    """None when the user's own track has its rights recorded (product.py music), else what to do."""
    if not own:
        return None
    f = Path(d) / "audio" / "music.json"
    try:
        m = json.loads(f.read_text())
    except (OSError, ValueError):
        m = {}
    if m.get("rights") not in RIGHTS or m.get("file") != own:
        return (f"{own} has no recorded licence: ask who holds the rights in the question box, then "
                f"product.py music DIR --url LINK --rights ... (a link) or --file {own} --rights ... (a file)")
    return None


def record_file(d, file, rights, credit=None):
    """The licence of a track the user handed over as a file, in the same place a link's goes."""
    d = Path(d)
    if not (d / file).exists():
        sys.exit(f"ERROR: {d / file} missing")
    (d / "audio").mkdir(exist_ok=True)
    info = {"source": "a file from the user", "file": file, "rights": rights, "credit": credit,
            "date": datetime.date.today().isoformat()}
    (d / "audio" / "music.json").write_text(json.dumps(info, indent=1))
    (d / "audio" / "MUSIC-LICENSE.md").write_text("# Music licence\n\n| field | value |\n|---|---|\n"
                                                    + "".join(f"| {k} | {v} |\n" for k, v in info.items()))
    return info


def story_order(beats):
    """FAIL/WARN lines for a story of beats told out of order (references/story.md "The arc")."""
    jobs = [b.get("job") for b in beats]
    out = []
    if not jobs:
        return out
    if jobs[0] != "hook":
        out.append(f"FAIL beat 0: the film opens on {jobs[0]!r}; open on the hook (the promise in the site's words)")
    if jobs[-1] != "end":
        out.append(f"FAIL beat {len(jobs) - 1}: the film ends on {jobs[-1]!r}; end on the logo and address (job 'end')")
    for i, j in enumerate(jobs):
        if j == "result" and (not i or jobs[i - 1] not in ("action", "result")):
            out.append(f"FAIL beat {i}: a result with no action before it; show the hand doing it first")
        if j == "payoff" and jobs[i + 1:] not in ([], ["end"]):
            out.append(f"FAIL beat {i}: the payoff comes before {jobs[i + 1]!r}; it goes last, just before the end")
    said = lambda b: f"{b.get('flow', '')} {b.get('text', '')}".replace("-", " ")
    made = next((i for i, b in enumerate(beats) if b.get("job") == "action" and MAKE.search(said(b))), None)
    if made is not None:
        later = next((i for i, b in enumerate(beats[made + 1:], made + 1) if b.get("job") == "action" and DISCOVER.search(said(b))
                      and not MAKE.search(said(b))), None)
        if later is not None:
            out.append(f"WARN beat {made}: makes something before beat {later} discovers anything; order the use cases "
                       "as a new user's journey, discover and learn first, make later (references/story.md)")
    return out


def target_length(story, length=None):
    """Seconds the film aims at: the user's, the story's, else SECONDS_PER_USE_CASE an action (40 s for five)."""
    import journey
    cases = sum(1 for b in story.get("beats", []) if b.get("job") == "action")
    return length or story.get("length") or journey.SECONDS_PER_USE_CASE * max(1, cases)


def demo():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        assert "no brief" in need_brief(d)
        (d / "brief.json").write_text(json.dumps({"must_show": ["search"]}))
        assert "audience" in need_brief(d)
        (d / "brief.json").write_text(json.dumps({"must_show": ["search"], "audience": "new users", "action": "visit"}))
        assert need_brief(d) is None
        (d / "story.json").write_text(json.dumps({"beats": [{"job": "hook"}, {"job": "end"}]}))
        (d / "plan-linear-16x9.json").write_text(json.dumps({"story": "story.json"}))
        assert "not approved" in need_approval(d, "plan-linear-16x9.json")
        try:
            approve(d, "plan-linear-16x9.json")
            raise AssertionError("approved without an animatic")
        except SystemExit:
            pass
        (d / "animatic-linear-16x9").mkdir()
        (d / "animatic-linear-16x9" / "sheet.png").write_bytes(b"png")
        approve(d, "plan-linear-16x9.json")
        assert need_approval(d, "plan-linear-16x9.json") is None
        (d / "story.json").write_text(json.dumps({"beats": [{"job": "hook"}, {"job": "payoff"}, {"job": "end"}]}))
        assert "changed" in need_approval(d, "plan-linear-16x9.json"), "a changed story needs a new yes"
        (d / "audio").mkdir()
        (d / "audio" / "mine.wav").write_bytes(b"")
        assert need_licence(d, None) is None and "no recorded licence" in need_licence(d, "audio/mine.wav")
        record_file(d, "audio/mine.wav", "own")
        assert need_licence(d, "audio/mine.wav") is None and "no recorded licence" in need_licence(d, "audio/other.wav")
    good = [{"job": "hook"}, {"job": "reveal"}, {"job": "action", "flow": "search"}, {"job": "result"},
            {"job": "action", "flow": "create-project"}, {"job": "result"}, {"job": "payoff"}, {"job": "end"}]
    assert story_order(good) == [], story_order(good)
    bad = [{"job": "reveal"}, {"job": "result"}, {"job": "payoff"}, {"job": "action"}]
    got = " | ".join(story_order(bad))
    assert "opens on 'reveal'" in got and "ends on 'action'" in got and "result with no action" in got and "payoff comes before" in got, got
    flipped = [{"job": "hook"}, {"job": "action", "text": "Create a project"}, {"job": "action", "flow": "search"}, {"job": "end"}]
    assert any(p.startswith("WARN") and "discover" in p for p in story_order(flipped)), story_order(flipped)
    assert target_length({"beats": [{"job": "action"}] * 5}) == 40 and target_length({"beats": []}, 25) == 25
    assert target_length({"beats": [{"job": "action"}], "length": 12}) == 12
    print("demo ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
    else:
        print(__doc__)
