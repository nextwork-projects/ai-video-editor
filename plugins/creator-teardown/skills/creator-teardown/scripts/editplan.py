#!/usr/bin/env python3
"""Turn a creator's measured edit into a plan for your own video.

  style <events.json>   the creator's edit as numbers: cards per minute, when each
                        card lands against its word, time on screen, entrances,
                        placement. Writes style.json next to events.json.
  render <plan.json>    checks a plan and writes plan.srt (one cue per card:
                        import it into your editor as captions and every card
                        sits at its time) and plan.md (the same list as a table).
  blend <name> --from a,b [--weights a=0.6,b=0.4] [--captions a] [--pace b] [--visuals c]
                        [--take captions,pace,graphics,entrances,layout,sound]
                        several creators' style.json into one, at
                        creator-teardowns/<name>/style.json. Each part (captions;
                        pace = pace, zoom, motion; visuals = graphics, face, look, cards)
                        comes from its owner when one is named, else every creator
                        weighted: numbers averaged, words from the heaviest.
  demo                  self-check.

Usage:
  python3 scripts/editplan.py style creator-teardowns/<handle>/events.json
  python3 scripts/editplan.py render edit-plans/<name>/plan.json
  python3 scripts/editplan.py blend mix --from alice,bob --captions alice --pace bob

The events.json and plan.json shapes are in references/edit-plan.md.
Exit codes: 0 ok - 1 the plan has errors - 2 usage
"""
import argparse
import json
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 3) if xs else None


def style(doc):
    """Numbers a plan can be held to. Every value is a median over real events.

    lag_s is card in minus trigger-word start: -0.2 means the card lands 0.2 s
    before the word.
    """
    by_cat = defaultdict(list)
    rates, firsts, gaps, per_video = [], [], [], []
    for v in doc["videos"]:
        evs = sorted(v.get("events") or [], key=lambda e: e["in"])
        if v.get("duration") and evs:
            per_video.append((v["duration"], Counter(e.get("cat") or "other" for e in evs)))
            rates.append(len(evs) / v["duration"] * 60)
            firsts.append(evs[0]["in"])
            gaps += [b["in"] - a["out"] for a, b in zip(evs, evs[1:]) if a.get("out") is not None]
        for e in evs:
            by_cat[e.get("cat") or "other"].append(e)

    cats = {}
    for cat, evs in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        boxes = [e["box"] for e in evs if e.get("box")]
        cats[cat] = {
            "n": len(evs),
            "per_min": round(med([n[cat] / d * 60 for d, n in per_video]), 1) if per_video else None,
            "lag_s": med([e.get("lag") for e in evs if e.get("trigger_time") is not None]),
            "hold_s": med([e["out"] - e["in"] for e in evs if e.get("out") is not None]),
            "entrance": [[k, round(c / len(evs), 2)] for k, c in
                         Counter(e.get("entrance") or "?" for e in evs).most_common(3)],
            "layer": Counter(e.get("layer") or "?" for e in evs).most_common(1)[0][0],
            "box": [med([b[i] for b in boxes]) for i in range(4)] if boxes else None,
        }
    return {"handle": doc.get("handle"), "videos": len(doc["videos"]),
            "events": sum(c["n"] for c in cats.values()),
            "per_min": round(med(rates), 1) if rates else None,
            "first_in_s": med(firsts), "gap_s": med(gaps), "cats": cats}


def describe(s):
    lines = [f"@{s['handle']}: {s['videos']} videos, {s['events']} events",
             f"  {s['per_min']} cards a minute, first at {s['first_in_s']} s, "
             f"median gap {s['gap_s']} s"]
    for cat, c in s["cats"].items():
        ent = " / ".join(f"{k} {round(p * 100)}%" for k, p in c["entrance"])
        lag = f"{c['lag_s']:+.2f} s from its word" if c["lag_s"] is not None else "no trigger word"
        lines.append(f"  {cat} ({c['n']}, {c['per_min']} a minute): lands {lag}, holds {c['hold_s']} s, "
                     f"enters {ent}, {c['layer']}")
    return "\n".join(lines)


def tc_srt(t):
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def tc(t):
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:05.2f}"


def check(plan, sty=None):
    errors, warnings = [], []
    dur, cards = plan["duration"], plan["cards"]
    for i, c in enumerate(cards, 1):
        name = f"card {i} ({c.get('word') or c.get('show', '')[:30]})"
        if not (0 <= c["in"] < c["out"] <= dur + 0.05):
            errors.append(f"{name}: {c['in']} to {c['out']} is outside the video (0 to {dur})")
        if not c.get("show"):
            errors.append(f"{name}: says nothing about what to show")
        want = ((sty or {}).get("cats", {}).get(c.get("cat")) or {}).get("lag_s")
        if want is not None and c.get("word_start") is not None:
            got = c["in"] - c["word_start"]
            if abs(got - want) > 0.25:
                warnings.append(f"{name}: lands {got:+.2f} s from its word, "
                                f"the creator's {c.get('cat')} cards land {want:+.2f} s")
    ins = [c["in"] for c in cards]
    if ins != sorted(ins):
        errors.append("cards are not in time order")
    if sty and dur:
        # Held to the creator's rate for the kinds of card this plan uses, so a
        # captions-heavy style doesn't license a wall of screenshots.
        rate = len(cards) / dur * 60
        kinds = {c.get("cat") for c in cards}
        cap = sum((sty["cats"].get(k) or {}).get("per_min") or 0 for k in kinds) or sty.get("per_min")
        if cap and rate > cap * 1.2:
            warnings.append(f"{rate:.1f} cards a minute, the creator runs {cap:.1f} "
                            f"for these kinds of card")
    return errors, warnings


def load_style(plan, plan_path):
    if not plan.get("style"):
        return None
    for p in (Path(plan["style"]), plan_path.parent / plan["style"]):
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def render(plan_path):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    sty = load_style(plan, plan_path)
    errors, warnings = check(plan, sty)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    cards = plan["cards"]
    srt = []
    for i, c in enumerate(cards, 1):
        where = " · ".join(x for x in (c.get("entrance") and f"{c['entrance']} in", c.get("place")) if x)
        srt.append(f"{i}\n{tc_srt(c['in'])} --> {tc_srt(c['out'])}\n{c['show']}\n{where}\n")
    (plan_path.parent / "plan.srt").write_text("\n".join(srt), encoding="utf-8")

    dur = plan["duration"]
    head = [f"# Edit plan: {plan.get('video', plan_path.parent.name)}", ""]
    if sty:
        head.append(f"Style from @{sty['handle']}, measured over {sty['events']} events in "
                    f"{sty['videos']} videos: {sty['per_min']} cards a minute.")
    head += [f"This plan: {len(cards)} cards in {dur:.1f} s, "
             f"{len(cards) / dur * 60:.1f} a minute.", "",
             "Import `plan.srt` into your editor as a caption track. Each cue marks one card.", "",
             "| # | In | Out | On the word | Show | Entrance | Where |",
             "|---|---|---|---|---|---|---|"]
    rows = [f"| {i} | {tc(c['in'])} | {tc(c['out'])} | {c.get('word') or ''} | {c['show']} "
            f"| {c.get('entrance') or ''} | {c.get('place') or ''} |" for i, c in enumerate(cards, 1)]
    (plan_path.parent / "plan.md").write_text("\n".join(head + rows) + "\n", encoding="utf-8")
    print(f"{len(cards)} cards -> {plan_path.parent / 'plan.srt'} and plan.md")


# camera goes with pace and hook with visuals, as style-edit reads them (took "pace" / "graphics")
PARTS = {"captions": ["captions"], "pace": ["pace", "zoom", "camera", "motion", "transitions"],
         "visuals": ["graphics", "face", "look", "cats", "per_min", "first_in_s", "gap_s", "events",
                     "layout", "hook"],
         "sound": ["sound"]}


def shares(d):
    """A {name: percent} dict (cut kinds, graphic kinds, zones): a name one creator lacks is 0% there."""
    vals = list(d.values())
    return bool(vals) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in vals) \
        and 95 <= sum(vals) <= 105


def mix(vals):
    """[(value, weight)] -> one value. Numbers: weighted mean. Dicts: per key. Anything
    else (words, colours, lists, booleans): the heaviest creator's."""
    vals = [(v, w) for v, w in vals if v is not None]
    if not vals:
        return None
    if all(isinstance(v, dict) for v, _ in vals):
        keys = dict.fromkeys(k for v, _ in vals for k in v)
        fill = 0 if all(shares(v) for v, _ in vals) else None
        return {k: mix([(v.get(k, fill), w) for v, w in vals]) for k in keys}
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v, _ in vals):
        tw = sum(w for _, w in vals)
        x = sum(v * w for v, w in vals) / tw
        return round(x) if all(isinstance(v, int) for v, _ in vals) else round(x, 3)
    return max(vals, key=lambda vw: vw[1])[0]


def blend(styles, weights, owners):
    """styles: {handle: style}. weights: {handle: w}. owners: {part: handle}."""
    tw = sum(weights.values())
    weights = {h: w / tw for h, w in weights.items()}
    heavy = max(weights, key=weights.get)
    out = {k: v for k, v in styles[heavy].items()}
    for part, keys in PARTS.items():
        src = [(styles[owners[part]], 1.0)] if owners.get(part) else \
            [(styles[h], weights[h]) for h in styles]
        for k in keys:
            v = mix([(s.get(k), w) for s, w in src])
            if v is None:
                out.pop(k, None)
            else:
                out[k] = v
    out["videos"] = sum(s.get("videos") or 0 for s in styles.values())
    out["blend"] = {"weights": {h: round(w, 3) for h, w in weights.items()},
                    "owners": {p: owners.get(p) or "weighted" for p in PARTS}}
    return out


# What each box on the teardown page (and the question in SKILL.md) copies: top-level keys,
# or "graphics.<key>" for one part of the graphics block.
TAKE = {"captions": ["captions"],
        "pace": ["pace", "zoom", "camera", "motion", "transitions"],
        "graphics": ["graphics.kinds", "graphics.kinds_source", "graphics.per_min", "graphics.share_pct",
                     "graphics.hold_s", "graphics.palette", "graphics.crop_palette", "graphics.per_min_measured",
                     "graphics.hold_s_measured", "graphics.measured", "graphics.blur_behind_pct", "cats", "events",
                     "per_min", "first_in_s", "gap_s"],
        "entrances": ["graphics.entrances", "graphics.exits", "graphics.secondary_motion", "graphics.ease_in_s"],
        "layout": ["graphics.layout", "face", "layout"],
        "sound": ["sound"]}


def take(style, parts):
    """Keeps only the parts the user chose; style-edit falls back to its defaults for the rest."""
    keep = {k for p in parts for k in TAKE[p]}
    out = dict(style)
    for p, keys in TAKE.items():
        for k in keys:
            if k in keep:
                continue
            if k.startswith("graphics."):
                if isinstance(out.get("graphics"), dict):
                    out["graphics"] = {kk: vv for kk, vv in out["graphics"].items() if kk != k.split(".", 1)[1]}
            else:
                out.pop(k, None)
    if "sound" not in parts:
        out["sfx"] = False if style.get("sfx") is False else out.get("sfx", True)
    out.setdefault("blend", {})["take"] = list(parts)
    return out


def cmd_blend(a, root=None):
    root = root or Path.cwd() / "creator-teardowns"
    handles = [h.strip().lstrip("@").lower() for h in a.sources.split(",") if h.strip()]
    styles = {}
    for h in handles:
        p = root / h / "style.json"
        if not p.exists():
            sys.exit(f"no {p}. Run the teardown on @{h} first.")
        styles[h] = json.loads(p.read_text(encoding="utf-8"))
    weights = {h: 1.0 for h in handles}
    for kv in (a.weights or "").split(","):
        if "=" in kv:
            h, w = kv.split("=")
            weights[h.strip().lstrip("@").lower()] = float(w)
    owners = {p: getattr(a, p).lstrip("@").lower() for p in PARTS if getattr(a, p, None)}
    bad = [h for h in list(weights) + list(owners.values()) if h not in styles]
    if bad:
        sys.exit(f"not in --from: {', '.join(bad)}")
    out = blend(styles, weights, owners)
    if getattr(a, "take", None):
        parts = [p.strip() for p in a.take.split(",") if p.strip() and p.strip() != "none"]
        bad = [p for p in parts if p not in TAKE]
        if bad:
            sys.exit(f"--take: unknown part(s) {', '.join(bad)}; choose from {', '.join(TAKE)}")
        out = take(out, parts)
    out["handle"] = a.name
    d = root / a.name
    d.mkdir(parents=True, exist_ok=True)
    (d / "style.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    try:  # look.md, when the venv's numpy is here
        from look import write_summary
        print(write_summary(d))
    except ImportError:
        pass
    print(f"blend of {', '.join(handles)}: " + ", ".join(f"{p} from {o}" for p, o in out["blend"]["owners"].items()))
    print(f"-> {d / 'style.json'}")
    return out


def demo():
    a = {"handle": "a", "videos": 5, "aspect": "9:16", "pace": {"wpm": 200, "median_shot_s": 2.0},
         "captions": {"present": True, "size_pct": 6.0, "color": "#FFFFFF", "words_per_caption": 3},
         "motion": {"personality": "snappy", "ease_in_s": 0.1}, "graphics": {"share_pct": 40}}
    b = {"handle": "b", "videos": 3, "aspect": "9:16", "pace": {"wpm": 150, "median_shot_s": 4.0},
         "captions": {"present": True, "size_pct": 4.0, "color": "#FFE14D", "words_per_caption": 1},
         "motion": {"personality": "calm", "ease_in_s": 0.4}, "face": {"framing": "close"}}
    m = blend({"a": a, "b": b}, {"a": 3, "b": 1}, {})
    assert m["pace"] == {"wpm": 188, "median_shot_s": 2.5}, m["pace"]
    assert m["captions"]["size_pct"] == 5.5 and m["captions"]["color"] == "#FFFFFF", m["captions"]
    assert m["captions"]["words_per_caption"] == 2 and m["motion"]["personality"] == "snappy"
    assert m["face"] == {"framing": "close"} and m["videos"] == 8
    m = blend({"a": a, "b": b}, {"a": 1, "b": 1}, {"captions": "b", "pace": "a"})
    assert m["captions"] == b["captions"] and m["pace"] == a["pace"], m
    assert m["blend"]["owners"] == {"captions": "b", "pace": "a", "visuals": "weighted", "sound": "weighted"}
    # camera follows the pace owner; percentage dicts still add to 100 when a key is missing on one side
    m = blend({"a": {**a, "camera": {"pan_per_min": 0.0}}, "b": {**b, "camera": {"pan_per_min": 4.4}}},
              {"a": 1, "b": 1}, {"pace": "a"})
    assert m["camera"] == {"pan_per_min": 0.0}, m["camera"]
    m = blend({"a": {**a, "pace": {"cut_kinds": {"hard": 100}}}, "b": {**b, "pace": {"cut_kinds": {"jump": 100}}}},
              {"a": 1, "b": 1}, {})
    assert m["pace"]["cut_kinds"] == {"hard": 50, "jump": 50}, m["pace"]
    with tempfile.TemporaryDirectory() as d:
        for h, s in (("a", a), ("b", b)):
            (Path(d) / h).mkdir()
            (Path(d) / h / "style.json").write_text(json.dumps(s), encoding="utf-8")
        t = take({"captions": {"size_pct": 4}, "pace": {"wpm": 200}, "sound": {"sfx_per_min": 3},
                  "graphics": {"kinds": {"chart": 100}, "entrances": [{"kind": "slide"}], "layout": {"zones_pct": {}}}},
                 ["captions", "entrances"])
        assert set(t) == {"captions", "graphics", "sfx", "blend"} and set(t["graphics"]) == {"entrances"}, t
        assert t["sfx"] is True and t["blend"]["take"] == ["captions", "entrances"]
        # top-level transitions go with pace, the split layout with layout
        t = take({"pace": {}, "transitions": ["push"], "layout": {"mode": "split"}, "graphics": {}}, ["captions"])
        assert "transitions" not in t and "layout" not in t, t
        t = take({"pace": {}, "transitions": ["push"], "layout": {"mode": "split"}, "graphics": {}}, ["pace", "layout"])
        assert t["transitions"] == ["push"] and t["layout"] == {"mode": "split"}, t
        assert "transitions" in PARTS["pace"] and "layout" in PARTS["visuals"]
        args = argparse.Namespace(name="mix", sources="@A,b", weights="a=2", captions="b",
                                  pace=None, visuals=None, sound=None, take=None)
        out = cmd_blend(args, Path(d))
        assert json.loads((Path(d) / "mix" / "style.json").read_text(encoding="utf-8")) == out
        assert out["handle"] == "mix" and out["captions"]["color"] == "#FFE14D"

    doc = {"handle": "demo", "videos": [
        {"duration": 60, "events": [
            {"cat": "logo", "in": 2.7, "out": 5.9, "entrance": "pop", "layer": "above_head",
             "trigger_time": 2.9, "lag": -0.2, "box": [30, 10, 40, 20]},
            {"cat": "logo", "in": 10.0, "out": 12.0, "entrance": "pop", "layer": "above_head",
             "trigger_time": 10.2, "lag": -0.2, "box": [30, 12, 40, 20]},
            {"cat": "text", "in": 0.0, "out": 3.0, "entrance": "cut", "layer": "above_head"}]}]}
    s = style(doc)
    assert s["per_min"] == 3 and s["first_in_s"] == 0.0, s
    assert s["cats"]["logo"]["per_min"] == 2 and s["cats"]["text"]["per_min"] == 1, s
    assert s["cats"]["logo"]["lag_s"] == -0.2 and s["cats"]["logo"]["hold_s"] == 2.6, s
    assert s["cats"]["logo"]["entrance"][0] == ["pop", 1.0] and s["cats"]["text"]["lag_s"] is None

    plan = {"video": "me.mp4", "duration": 30.0, "cards": [
        {"word": "Duolingo", "word_start": 3.52, "in": 3.32, "out": 5.6, "cat": "logo",
         "show": "Duolingo logo", "entrance": "pop", "place": "top band"}]}
    assert check(plan, s) == ([], [])
    late = dict(plan, cards=[dict(plan["cards"][0], **{"in": 4.0})])
    assert "lands +0.48 s" in check(late, s)[1][0]
    assert check(dict(plan, duration=5.0), s)[0], "a card past the end must be an error"

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "plan.json"
        p.write_text(json.dumps(plan), encoding="utf-8")
        render(p)
        srt = (Path(d) / "plan.srt").read_text(encoding="utf-8")
        assert "00:00:03,320 --> 00:00:05,600" in srt and "pop in · top band" in srt, srt
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("style")
    p.add_argument("events")
    p = sub.add_parser("render")
    p.add_argument("plan")
    p = sub.add_parser("blend")
    p.add_argument("name", help="the blend's folder name under creator-teardowns/")
    p.add_argument("--from", dest="sources", required=True, help="handles, comma-separated")
    p.add_argument("--weights", help="handle=weight,... (default equal)")
    for part in PARTS:
        p.add_argument(f"--{part}", help=f"the one creator whose {part} to take")
    p.add_argument("--take", help=f"only these parts, comma-separated: {','.join(TAKE)} (the teardown page's boxes)")
    sub.add_parser("demo")
    a = ap.parse_args()

    if a.cmd == "style":
        src = Path(a.events)
        s = style(json.loads(src.read_text(encoding="utf-8")))
        out = src.parent / "style.json"
        # Merge: visual.py writes pace/zoom/captions into the same file.
        old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
        out.write_text(json.dumps({**old, **s, "videos": old.get("videos", s["videos"])}, indent=2), encoding="utf-8")
        print(describe(s))
        print(f"\n-> {src.parent / 'style.json'}")
    elif a.cmd == "render":
        render(Path(a.plan))
    elif a.cmd == "blend":
        cmd_blend(a)
    else:
        demo()


if __name__ == "__main__":
    main()
