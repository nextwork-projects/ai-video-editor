#!/usr/bin/env python3
"""The teardown page: hook anatomy, winners against the control group, an AI-tell scan, and
one self-contained teardown.html to look at instead of reading numbers.

  build <handle>   reads what the other passes wrote (videos.json, transcripts, video/<id>.visual,
                   look, graphics and sound files, style.json), then:
                   - hook: the first 3 s of every video (face, title on screen, first cut, first
                     graphic, first caption, the opening words), medians for winners and control
                   - winners: every measured field, winners against the control group, with n
                   - ai_tells: ai-editor's ai_tells.py checks run on the creator's own look
                   merges hook / winners / ai_tells into style.json, writes report.json and
                   teardown.html (opens in any browser; images are embedded).
  demo             self-check on made-up per-video numbers and a synthetic clip. No network.

Winners and control. A video is a winner at 2x or more of the creator's median views; the
control group sits between 0.5x and 2x. A field differs when the two medians are 25% or more
apart (0.5 s for times), and it is "every" when every winner sits on one side of every
control video. Nothing here is a significance test: the page says n for both groups.

Usage (the tool venv python: numpy, pillow, opencv for the pixel checks):
  ~/.ai-video-editor/venv/bin/python scripts/report.py build <handle>
  ~/.ai-video-editor/venv/bin/python scripts/report.py demo

Exit codes: 0 ok - 1 error - 2 usage
"""
import argparse
import base64
import glob
import html
import io
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, slug  # noqa: E402

HOOK_S = 3.0
WIN_X, CONTROL_LO = 2.0, 0.5


# ---------- per video ----------

def load(p):
    return json.loads(p.read_text()) if p.exists() else None


def role(v):
    x = v.get("vs_median")
    if x is None:
        return None
    return "winner" if x >= WIN_X else "control" if x >= CONTROL_LO else "low"


def words_of(outdir, vid):
    d = load(outdir / "transcripts" / f"{vid}.json")
    return [w for w in (d or {}).get("words", []) if w.get("type") == "word"]


def hook(vid, words, look, vis, gfx):
    """The first HOOK_S seconds of one video, every value measured."""
    ss = [s for s in (look or {}).get("samples", []) if s["t"] < HOOK_S]
    titles = []
    for s in ss:
        for text, box, cap in s["lines"]:
            if not cap and text not in titles and len(text) > 2:
                titles.append(text)
    gs = [g for g in (gfx or {}).get("graphics", []) if g.get("kind") != "set"]
    caps = [s["t"] for s in (look or {}).get("samples", []) if any(c for _, _, c in s["lines"])]
    # Words the editor laid on screen (a title), from the OCR, apart from the graphics pass.
    text_t = next((s["t"] for s in (look or {}).get("samples", []) if any(not c and len(t) > 2 for t, _, c in s["lines"])), None)
    cuts = (vis or {}).get("cuts", [])
    return {
        "id": vid,
        "face_pct": round(100 * sum(1 for s in ss if s["face"]) / len(ss)) if ss else None,
        "title_on_screen": " / ".join(titles[:4]) or None,
        "first_cut_s": round(cuts[0], 2) if cuts else None,
        "first_graphic_s": round(min(g["t_in"] for g in gs), 2) if gs else None,
        "first_graphic_kind": min(gs, key=lambda g: g["t_in"])["kind"] if gs else None,
        "first_caption_s": round(caps[0], 2) if caps else None,
        "first_text_s": text_t,
        "first_word_s": round(words[0]["start"], 2) if words else None,
        "opening_line": " ".join(w["text"].strip() for w in words if w["start"] < HOOK_S) or None,
        "cuts_in_hook": sum(1 for c in cuts if c < HOOK_S),
    }


def fields(v, words, look, vis, gfx, snd):
    """One row of measured numbers per video, for winners against control."""
    dur = (vis or gfx or snd or {}).get("duration_s") or v.get("duration") or 0
    gs = [g for g in (gfx or {}).get("graphics", []) if g.get("kind") != "set"]
    kinds = {}
    for g in gs:
        kinds[g["kind"]] = kinds.get(g["kind"], 0) + g["hold_s"]
    tot = sum(kinds.values()) or 1
    ents = [g["entrance"] for g in gs if g.get("entrance")]
    h = hook(v["id"], words, look, vis, gfx)
    cap = (look or {}).get("captions") or {}
    f = {
        "words a minute": round(len(words) / dur * 60) if words and dur else None,
        "cuts a minute": round(len(vis["cuts"]) / dur * 60, 1) if vis and dur else None,
        "median shot (s)": (vis or {}).get("median_shot_s"),
        "zooms a minute": (vis or {}).get("zooms_per_min"),
        "graphics a minute": round(len(gs) / dur * 60, 1) if gfx and dur else None,
        "graphics on screen (% of runtime)": round(100 * min(dur, sum(g["hold_s"] for g in gs)) / dur) if gfx and dur else None,
        "graphic hold (s)": round(statistics.median(g["hold_s"] for g in gs), 2) if gs else None,
        "screenshots (% of graphic time)": round(100 * (kinds.get("real screenshot", 0) + kinds.get("UI recording", 0)) / tot) if gs else None,
        "text cards (% of graphic time)": round(100 * kinds.get("text card", 0) / tot) if gs else None,
        "animated entrances (%)": round(100 * sum(e["kind"] != "cut" for e in ents) / len(ents)) if ents else None,
        "first graphic (s)": h["first_graphic_s"],
        "first cut (s)": h["first_cut_s"],
        "first words on screen (s)": h["first_text_s"],
        "first word (s)": h["first_word_s"],
        "face on screen (%)": (look or {}).get("face", {}).get("present_pct"),
        "caption size (% of frame)": cap.get("size_pct"),
        "sound effects a minute": (snd or {}).get("sfx_per_min"),
    }
    return f


TIME_FIELDS = {"first graphic (s)", "first words on screen (s)", "first cut (s)", "first word (s)", "median shot (s)", "graphic hold (s)"}


def compare(rows):
    """rows: [{"role", "views", "fields"}]. Per field: medians, n, how far apart, and whether
    every winner sits on one side of every control video."""
    W = [r for r in rows if r["role"] == "winner"]
    C = [r for r in rows if r["role"] == "control"]
    out = []
    for k in (rows[0]["fields"] if rows else {}):
        w = [r["fields"][k] for r in W if r["fields"].get(k) is not None]
        c = [r["fields"][k] for r in C if r["fields"].get(k) is not None]
        if not w or not c:
            out.append({"field": k, "n_winners": len(w), "n_control": len(c), "verdict": "not enough"})
            continue
        mw, mc = statistics.median(w), statistics.median(c)
        apart = abs(mw - mc) >= (0.5 if k in TIME_FIELDS else 0.25 * max(abs(mw), abs(mc), 1e-9))
        every = min(w) > max(c) or max(w) < min(c)
        out.append({"field": k, "winners": round(mw, 2), "control": round(mc, 2), "n_winners": len(w),
                    "n_control": len(c), "winner_values": w, "control_values": c,
                    "verdict": ("differs, every winner" if every else "differs, overlaps") if apart else "same"})
    return out


def sentence(c):
    if not c.get("winners") and c.get("winners") != 0:
        return None
    hi = "higher" if c["winners"] > c["control"] else "lower"
    tail = "every winner on that side" if c["verdict"].endswith("every winner") else "the groups overlap"
    return (f"{c['field']}: winners {c['winners']} (n={c['n_winners']}), control {c['control']} "
            f"(n={c['n_control']}), {hi} for winners; {tail}.")


# ---------- AI tells ----------

def ai_tells_module():
    """ai-editor's ai_tells.py: this repo's copy, AI_EDITOR_STYLE_SCRIPTS, or an installed plugin."""
    here = Path(__file__).resolve()
    cands = [os.environ.get("AI_EDITOR_STYLE_SCRIPTS"),
             here.parents[4] / "ai-editor" / "skills" / "style-edit" / "scripts"]
    cands += sorted(glob.glob(str(Path.home() / ".claude" / "plugins" / "**" / "style-edit" / "scripts"),
                              recursive=True))
    for c in cands:
        if c and (Path(c) / "ai_tells.py").exists():
            sys.path.insert(0, str(c))
            try:
                import ai_tells
                return ai_tells
            except Exception as e:  # a broken install must not stop the teardown
                print(f"  ai_tells.py at {c} did not load: {e}", file=sys.stderr)
    return None


def scan_tells(style, outdir, gfx_rows, at=None):
    """The creator's own look through ai-editor's checks, so copying it is a choice, not an accident."""
    at = at or ai_tells_module()
    if not at:
        return {"ran": False, "why": "ai-editor's ai_tells.py not found (install the ai-editor plugin)"}
    cap = style.get("captions") or {}
    # The palette look.md prints and ai-editor copies (profile.creator_look): the frames with graphics.
    # crop_palette is the colours inside the cards (captured pages, logos), real content, not their look.
    g = style.get("graphics") or {}
    pal = sorted(g.get("palette") or g.get("crop_palette") or [], key=lambda p: -p.get("pct", 0))
    sat = [p for p in pal if (at.hsv(p["hex"]) or (0, 0, 0))[1] >= 0.4]
    look = {"preset": "creator", "font": cap.get("font_match"), "font_display": cap.get("font_match"),
            "ground": pal[0]["hex"] if pal else None, "accent": sat[0]["hex"] if sat else None}
    found = at.check_look(look, {})
    found += at.check_plan({"captions": {"style": cap}, "cards": []}, [], {})
    for p in pal:
        if p["pct"] >= 8 and at.is_purple_blue(p["hex"]):
            found.append(at.tell("purple-blue", "graphics palette", f"{p['hex']} is {p['pct']}% of the graphics"))
    stills = []
    try:
        import cv2
        for r in gfx_rows:
            for g in r["graphics"]:
                if g.get("kind") == "text card" and g.get("crop"):
                    img = cv2.imread(str(outdir / g["crop"]))
                    if img is not None:
                        hits = at.check_still(img, f"{g['crop']} ({g.get('what') or 'text card'})")
                        stills += hits
    except ImportError:
        pass
    found += stills
    seen, out = set(), []
    for f in found:
        k = (f["tell"], f["where"].split(":")[0] if f["where"].startswith("graphics/") else f["where"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return {"ran": True, "found": out, "bans": sum(f["level"] == "BAN" for f in out),
            "warns": sum(f["level"] == "WARN" for f in out), "look_checked": look}


# ---------- the page ----------

def b64(path_or_bytes, mime="image/jpeg"):
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    return f"data:{mime};base64," + base64.b64encode(data).decode()


def frame_jpeg(video, t, width=180, crop=None):
    """One frame as JPEG bytes (crop: x, y, w, h fractions)."""
    from PIL import Image
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t):.2f}", "-i", str(video), "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    if not raw:
        return None
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    if crop:
        W, H = im.size
        x, y, w, h = crop
        im = im.crop((int(max(0, x) * W), int(max(0, y) * H), int(min(1, x + w) * W), int(min(1, y + h) * H)))
    im.thumbnail((width, width * 4))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=78)
    return buf.getvalue()


def ease_svg(ease, w=120, h=64):
    """The fitted ease as a small curve (graphics.ease_value), 0 to 1 over its duration."""
    from graphics import ease_value
    import numpy as np
    t = np.linspace(0, 1, 40)
    try:
        y = ease_value(ease, t) if ease and ease != "none" else (t >= 0.02).astype(float)
    except KeyError:
        return ""
    lo, hi = min(0.0, float(y.min())), max(1.0, float(y.max()))
    pts = " ".join(f"{6 + x * (w - 12):.1f},{h - 6 - (v - lo) / (hi - lo) * (h - 12):.1f}" for x, v in zip(t, y))
    one = h - 6 - (1 - lo) / (hi - lo) * (h - 12)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="curve" role="img" aria-label="{html.escape(ease)}">'
            f'<line x1="6" x2="{w - 6}" y1="{one:.1f}" y2="{one:.1f}" class="guide"/>'
            f'<polyline points="{pts}" class="ease"/></svg>')


def dots_svg(c, w=220, h=34):
    """Every video's value on one line: winners filled, control hollow."""
    vals = c.get("winner_values", []) + c.get("control_values", [])
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1

    def x(v):
        return 10 + (v - lo) / span * (w - 20)
    out = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="dots" role="img">',
           f'<line x1="10" x2="{w - 10}" y1="{h / 2}" y2="{h / 2}" class="guide"/>']
    out += [f'<circle cx="{x(v):.1f}" cy="{h / 2}" r="5" class="win"/>' for v in c.get("winner_values", [])]
    out += [f'<circle cx="{x(v):.1f}" cy="{h / 2}" r="5" class="ctl"/>' for v in c.get("control_values", [])]
    out.append("</svg>")
    return "".join(out)


CSS = """
:root{--bg:#fbfaf8;--card:#ffffff;--ink:#17171a;--mute:#6b6b73;--line:#e6e4df;--win:#1f7a4d;--ctl:#9a9aa3;--warn:#a15c00;--ban:#b42318;--chip:#f1efea}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141416;--card:#1c1c20;--ink:#ececef;--mute:#9a9aa3;--line:#2c2c31;--win:#4cc38a;--ctl:#77777f;--warn:#e0a03a;--ban:#f0716a;--chip:#26262b}}
:root[data-theme="dark"]{--bg:#141416;--card:#1c1c20;--ink:#ececef;--mute:#9a9aa3;--line:#2c2c31;--win:#4cc38a;--ctl:#77777f;--warn:#e0a03a;--ban:#f0716a;--chip:#26262b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}h1{font-size:28px;margin:0 0 4px}h2{font-size:19px;margin:40px 0 12px}
.mute{color:var(--mute)}.grid{display:grid;gap:12px}.stats{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.stat b{display:block;font-size:20px}
.strip{display:flex;gap:4px;overflow-x:auto;padding-bottom:4px}.strip img{height:150px;border-radius:6px;flex:none}
.vid{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:10px}
.badge{display:inline-block;font-size:12px;padding:1px 8px;border-radius:99px;background:var(--chip);margin-left:6px}
.badge.winner{color:var(--win)}.gallery{display:flex;flex-wrap:wrap;gap:10px}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}
.g{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px;font-size:12px}
.g img{width:100%;border-radius:4px;display:block;max-height:200px;object-fit:contain;background:var(--chip)}
.two{display:grid;grid-template-columns:minmax(0,260px) minmax(0,1fr);gap:16px;align-items:start}
@media (max-width:700px){.two{grid-template-columns:1fr}}
.heat{width:100%;max-width:260px;border-radius:10px}.bar{height:10px;background:var(--chip);border-radius:5px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--ink)}table{border-collapse:collapse;width:100%;font-size:14px}
td,th{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:middle}th{color:var(--mute);font-weight:500}
.scroll{overflow-x:auto}.ease{fill:none;stroke:var(--ink);stroke-width:2}.guide{stroke:var(--line);stroke-width:1}
.win{fill:var(--win)}.ctl{fill:none;stroke:var(--ctl);stroke-width:2}.cards{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
.lvl-BAN{color:var(--ban);font-weight:600}.lvl-WARN{color:var(--warn);font-weight:600}
.take label{display:block;padding:6px 0}code{background:var(--chip);padding:2px 6px;border-radius:5px;font-size:13px;word-break:break-all}
button{font:inherit;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.strip img.capimg{height:64px;border-radius:6px}
"""

TAKE = [("captions", "Captions: size, place, colour, words per line, how they enter"),
        ("pace", "Pace: cuts, zooms, camera moves"),
        ("graphics", "Graphic kinds: what they put on screen"),
        ("entrances", "Entrance motion: how graphics arrive and leave"),
        ("layout", "Layout: where graphics sit on the frame"),
        ("sound", "Sound: effects and music")]


def page(handle, outdir, style, videos, hooks, comp, tells, gfx_rows):
    E = html.escape
    by_id = {v["id"]: v for v in videos}
    vids = sorted((r for r in gfx_rows), key=lambda r: -(by_id.get(r["id"], {}).get("view_count") or 0))
    p, g, c, s = (style.get(k) or {} for k in ("pace", "graphics", "captions", "sound"))
    nW = sum(1 for v in videos if v.get("_role") == "winner")
    nC = sum(1 for v in videos if v.get("_role") == "control")
    H = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>@{E(handle)} teardown</title><style>{CSS}</style></head><body><main>",
         f"<h1>@{E(handle)}</h1><p class=mute>{len(videos)} videos measured: {nW} winners (2x their median views or more), "
         f"{nC} control (near the median). Every number on this page is measured from the videos; "
         f"the kinds and descriptions of graphics are named by a model.</p>"]
    stat = [("Words a minute", p.get("wpm")), ("Cut every", f"{p.get('median_shot_s')} s"),
            ("Graphics a minute", g.get("per_min_measured")), ("Graphic holds", f"{g.get('hold_s_measured')} s"),
            ("Captions", f"{c.get('words_per_caption')} word, {c.get('case')}"), ("Sound effects", f"{s.get('sfx_per_min')} a minute")]
    H.append("<div class='grid stats'>" + "".join(f"<div class=stat><span class=mute>{E(k)}</span><b>{E(str(v))}</b></div>"
                                                   for k, v in stat) + "</div>")

    H.append("<h2>Their videos, frame by frame</h2>")
    for r in vids:
        v = by_id.get(r["id"], {})
        mp4 = outdir / "video" / f"{r['id']}.mp4"
        dur = r["duration_s"]
        imgs = []
        for k in range(8):
            jb = frame_jpeg(mp4, dur * (k + 0.5) / 8, 120)
            if jb:
                imgs.append(f"<img alt='{dur * (k + 0.5) / 8:.0f} s' title='{dur * (k + 0.5) / 8:.1f} s' src='{b64(jb)}'>")
        rl = v.get("_role") or ""
        H.append(f"<div class=vid><b>{(v.get('view_count') or 0):,} views</b> <span class=mute>{v.get('vs_median')}x median, "
                 f"{dur:.0f} s</span><span class='badge {rl}'>{E(rl)}</span> "
                 f"<a href='{E(v.get('webpage_url') or '')}' class=mute>open</a>"
                 f"<div class=strip>{''.join(imgs)}</div></div>")

    H.append("<h2>Graphics they put on screen</h2>")
    kinds = g.get("kinds") or {}
    H.append("<p class=mute>Share of graphic screen time: " + ", ".join(f"{E(k)} {v}%" for k, v in kinds.items())
             + f". Named by {E(g.get('kinds_source') or 'code')}.</p>")
    groups = {}
    for r in vids:
        for gr in r["graphics"]:
            if gr.get("kind") != "set" and gr.get("crop"):
                groups.setdefault(gr["kind"], []).append((r["id"], gr))
    for kind in sorted(groups, key=lambda k: -kinds.get(k, 0)):
        # One card per distinct graphic: a list that comes back after each cut is one graphic.
        uniq = {}
        for vid, gr in groups[kind]:
            k_ = (vid, (gr.get("what") or "").lower(), tuple(round(x, 1) for x in gr["box"]))
            uniq.setdefault(k_, []).append(gr)
        H.append(f"<h3>{E(kind)} <span class=mute>({len(uniq)})</span></h3><div class=gallery>")
        for grs in list(uniq.values())[:24]:
            gr = grs[0]
            ent = gr.get("entrance") or {}
            move = "cuts in" if ent.get("kind") in (None, "cut") else f"{ent['kind']} in, {ent.get('ease')} {ent.get('duration_s')} s"
            again = f", back {len(grs) - 1} more times" if len(grs) > 1 else ""
            H.append(f"<div class=g><img loading=lazy alt='{E(gr.get('what') or kind)}' src='{b64(outdir / gr['crop'])}'>"
                     f"<div>{E(gr.get('what') or '')}</div><div class=mute>at {gr['t_in']} s, up {gr['hold_s']} s{again}; "
                     f"{E(move)}</div></div>")
        H.append("</div>")

    lay = g.get("layout") or {}
    heat = outdir / "graphics" / "heatmap.png"
    if lay:
        z = lay.get("zones_pct") or {}
        bars = "".join(f"<div style='margin:8px 0'>{E(k)} <span class=mute>{v}%</span><div class=bar><i style='width:{v}%'></i></div></div>"
                       for k, v in z.items())
        H.append("<h2>Where graphics sit</h2><div class=two>"
                 + (f"<img class=heat alt='where graphics sit, warmer is more time' src='{b64(heat)}'>" if heat.exists() else "")
                 + f"<div>{bars}<p class=mute>Median box: {lay.get('median_box')} (x, y, w, h, % of frame). "
                   f"Graphics cover the face {lay.get('covers_face_pct')}% of their time. "
                   f"Footage blurred behind the graphic: {g.get('blur_behind_pct')}% of graphics.</p></div></div>")

    H.append("<h2>How graphics move</h2><div class='grid cards'>")
    for e in (g.get("entrances") or [])[:5]:
        desc = {"cut": "cut in", "fade": "fade in"}.get(e["kind"], e["kind"]) + (f" from the {e['from']}, {e.get('distance_pct')}% of the frame" if e.get("from") else "") + \
            (f", from {e['scale_from']}x" if e.get("scale_from") else "") + (", fades" if e.get("fade") else "")
        how = "no animation, it is just there" if e["kind"] == "cut" else \
            f"{e['ease']} over {e['duration_s']} s" + (f", overshoots {round(100 * e['overshoot'])}%" if e["overshoot"] >= 0.03 else "")
        H.append(f"<div class=stat>{ease_svg(e['ease'])}<b>{e['share_pct']}% of entrances</b>{E(desc)}<br>"
                 f"<span class=mute>{E(how)}, n={e['n']}</span></div>")
    H.append("</div>")
    sec = g.get("secondary_motion") or {}
    H.append("<p class=mute>While up: " + ", ".join(f"{E(k)} {v}%" for k, v in sec.items())
             + ". Exits: " + ", ".join(f"{E(x['kind'])} {E(x['ease'])} {x['share_pct']}%" for x in (g.get('exits') or [])[:3]) + ".</p>")

    H.append("<h2>Captions</h2>")
    caps = []
    for r in vids[:6]:
        look = load(outdir / "video" / f"{r['id']}.look.json") or {}
        smp = [s_ for s_ in look.get("samples", []) if any(cp for _, _, cp in s_["lines"])]
        if smp:
            s_ = smp[len(smp) // 2]
            box = next(b for _, b, cp in s_["lines"] if cp)
            jb = frame_jpeg(outdir / "video" / f"{r['id']}.mp4", s_["t"], 360,
                            (0.05, box[1] - 0.04, 0.9, box[3] + 0.08))
            if jb:
                caps.append(f"<img class=capimg alt='caption sample' src='{b64(jb)}'>")
    H.append(f"<div class=strip>{''.join(caps)}</div><p>{c.get('words_per_caption')} word a caption, {E(str(c.get('case')))} case, "
             f"{c.get('size_pct')}% of the frame tall, {c.get('y_pct')}% down, fill {E(str(c.get('color')))}, "
             f"stroke {E(str(c.get('stroke_color') if c.get('stroke') else 'none'))}, font closest to {E(str(c.get('font_match')))}, "
             f"enters with a {E(str(c.get('entrance')))} in {c.get('ease_s')} s.</p>")

    ck = p.get("cut_kinds") or {}
    cam, zm = style.get("camera") or {}, style.get("zoom") or {}
    H.append("<h2>Pace, cuts and camera</h2><p>"
             f"A cut every {p.get('median_shot_s')} s. Cuts: " + ", ".join(f"{E(k)} {v}%" for k, v in ck.items()) +
             f". Zoom: {E(str(zm.get('kind')))} x{zm.get('scale')} {zm.get('per_min')} a minute, ease {E(str(zm.get('ease')))}. "
             f"Camera: {cam.get('push_per_min')} pushes and {cam.get('pan_per_min')} pans a minute, shake {cam.get('shake_pct')}% of the time.</p>")

    m = s.get("music") or {}
    H.append("<h2>Sound</h2><p>" + (f"{s.get('sfx_per_min')} sound effects a minute"
             + (" (" + ", ".join(f"{E(k)} {v}%" for k, v in (s.get('kinds') or {}).items()) + ")" if s.get("kinds") else "")
             + f". A music bed found in {m.get('present_pct')}% of the videos"
             + (f", about {abs(m.get('level_db'))} dB under the voice" if m.get("level_db") is not None else "")
             + ". Read from the gaps between words: listen to one to confirm." if s else "Not measured: run sound.py.") + "</p>")

    H.append("<h2>The first 3 seconds</h2><div class=scroll><table><tr><th>Views</th><th>Opening words</th><th>On screen</th>"
             "<th>Face</th><th>First cut</th><th>First words on screen</th><th>First graphic</th><th>First caption</th></tr>")
    for h_ in sorted(hooks, key=lambda h_: -(by_id.get(h_["id"], {}).get("view_count") or 0)):
        v = by_id.get(h_["id"], {})
        H.append(f"<tr><td>{(v.get('view_count') or 0):,}<span class='badge {v.get('_role') or ''}'>{E(v.get('_role') or '')}</span></td>"
                 f"<td>{E(h_['opening_line'] or '')}</td><td>{E(h_['title_on_screen'] or '')}</td><td>{h_['face_pct']}%</td>"
                 f"<td>{h_['first_cut_s']} s</td><td>{h_['first_text_s']} s</td><td>{h_['first_graphic_s']} s {E(h_['first_graphic_kind'] or '')}</td>"
                 f"<td>{h_['first_caption_s']} s</td></tr>")
    H.append("</table></div>")

    H.append(f"<h2>Winners against control</h2><p class=mute>Medians. n={nW} winners, n={nC} control. Filled dots are winners, "
             "hollow are control. With groups this small, read it as where to look, not as proof.</p>"
             "<div class=scroll><table><tr><th>Field</th><th>Winners</th><th>Control</th><th>Every video</th><th>Verdict</th></tr>")
    for c_ in sorted(comp, key=lambda c_: ("every" not in c_["verdict"], c_["verdict"] == "same")):
        H.append(f"<tr><td>{E(c_['field'])}</td><td>{c_.get('winners', '')}</td><td>{c_.get('control', '')}</td>"
                 f"<td>{dots_svg(c_)}</td><td>{E(c_['verdict'])}</td></tr>")
    H.append("</table></div>")

    H.append("<h2>Does their look read as AI-made?</h2>")
    if not tells.get("ran"):
        H.append(f"<p class=mute>{E(tells.get('why', ''))}</p>")
    elif not tells["found"]:
        H.append("<p>None of ai-editor's AI tells fire on this creator's fonts, palette, captions or text cards.</p>")
    else:
        H.append("<p>Copying these would carry the tell into your edit. BAN: never by default. WARN: only with a reason.</p><ul>")
        for f in tells["found"]:
            where = f["where"]
            thumb = ""
            if where.startswith("graphics/"):
                path, _, rest = where.partition(" ")
                if (outdir / path).exists():
                    thumb = f"<img alt='' src='{b64(outdir / path)}' style='height:56px;vertical-align:middle;border-radius:4px;margin-right:6px'>"
                where = rest.strip()
            H.append(f"<li style='margin:6px 0'>{thumb}<span class='lvl-{f['level']}'>{f['level']}</span> {E(f['tell'])}: {E(where)}. "
                     f"<span class=mute>Instead: {E(f['fix'])}</span></li>")
        H.append("</ul>")

    # Choices are asked in Claude's question box, never ticked here: a static page cannot reach Claude.
    H.append("<h2>What to take</h2><div class=take><p>Back in Claude, you will be asked which of these to copy:</p><ul>")
    for k, label in TAKE:
        H.append(f"<li>{E(label)}</li>")
    H.append("</ul></div>")
    H.append("</main></body></html>")
    return "\n".join(H)


# ---------- one creator ----------

def build(outdir, at=None):
    meta = load(outdir / "videos.json") or {"videos": []}
    by_id = {v["id"]: v for v in meta["videos"]}
    style = load(outdir / "style.json") or {"handle": outdir.name}
    rows, hooks, gfx_rows, videos = [], [], [], []
    for mp4 in sorted((outdir / "video").glob("*.mp4")):
        vid = mp4.stem
        v = dict(by_id.get(vid, {"id": vid}))
        v["_role"] = role(v)
        words = words_of(outdir, vid)
        look, vis = load(mp4.with_suffix(".look.json")), load(mp4.with_suffix(".visual.json"))
        gfx, snd = load(mp4.with_suffix(".graphics.json")), load(mp4.with_suffix(".sound.json"))
        hooks.append(hook(vid, words, look, vis, gfx))
        rows.append({"id": vid, "role": v["_role"], "views": v.get("view_count"),
                     "fields": fields(v, words, look, vis, gfx, snd)})
        gfx_rows.append(gfx or {"id": vid, "duration_s": (vis or {}).get("duration_s") or 0, "graphics": []})
        videos.append(v)
    comp = compare(rows)
    tells = scan_tells(style, outdir, gfx_rows, at)

    def med(role_, k):
        xs = [h[k] for h, r in zip(hooks, rows) if r["role"] == role_ and h[k] is not None]
        return round(statistics.median(xs), 2) if xs else None
    style["hook"] = {r_: {k: med(r_, k) for k in ("first_cut_s", "first_graphic_s", "first_text_s", "first_caption_s", "first_word_s", "face_pct")}
                     for r_ in ("winner", "control")}
    style["hook"]["title_on_screen_pct"] = round(100 * sum(1 for h in hooks if h["title_on_screen"]) / len(hooks)) if hooks else None
    style["winners"] = {"n_winners": sum(r["role"] == "winner" for r in rows),
                        "n_control": sum(r["role"] == "control" for r in rows),
                        "differs": [sentence(c) for c in sorted(comp, key=lambda c: not c["verdict"].endswith("every winner"))
                                    if c["verdict"].startswith("differs")]}
    style["ai_tells"] = {k: v for k, v in tells.items() if k != "look_checked"}
    (outdir / "style.json").write_text(json.dumps(style, indent=2))
    (outdir / "report.json").write_text(json.dumps({"hooks": hooks, "compare": comp, "ai_tells": tells}, indent=1))
    try:   # look.md was written before graphics, sound and the tells: rewrite it from the final style.json
        from look import write_summary
        write_summary(outdir)
    except Exception as e:
        print(f"  look.md not rewritten: {e}", file=sys.stderr)
    out = outdir / "teardown.html"
    out.write_text(page(style.get("handle") or outdir.name, outdir, style, videos, hooks, comp, tells, gfx_rows))
    return out, style, comp


def cmd_build(a):
    outdir = OUT_ROOT / slug(a.handle)
    if not (outdir / "video").exists():
        sys.exit(f"no {outdir / 'video'}. Run the visual pass first.")
    out, style, comp = build(outdir)
    w = style["winners"]
    print(f"winners n={w['n_winners']}, control n={w['n_control']}")
    for line in w["differs"]:
        print("  " + line)
    t = style["ai_tells"]
    print(f"AI tells: {t.get('bans', 0)} BAN, {t.get('warns', 0)} WARN" if t.get("ran") else f"AI tells: {t.get('why')}")
    print(f"-> {out}  ({out.stat().st_size // 1024} KB)")


# ---------- self-check ----------

def demo():
    rows = [{"role": "winner", "fields": {"first graphic (s)": x, "cuts a minute": 12}} for x in (1.0, 1.2, 1.5)]
    rows += [{"role": "control", "fields": {"first graphic (s)": x, "cuts a minute": 12.5}} for x in (3.0, 3.8)]
    c = {r["field"]: r for r in compare(rows)}
    assert c["first graphic (s)"]["verdict"] == "differs, every winner" and c["first graphic (s)"]["winners"] == 1.2, c
    assert c["cuts a minute"]["verdict"] == "same", c
    assert "n=3" in sentence(c["first graphic (s)"]) and "n=2" in sentence(c["first graphic (s)"])
    assert role({"vs_median": 3}) == "winner" and role({"vs_median": 1}) == "control" and role({"vs_median": 0.2}) == "low"
    look = {"samples": [{"t": 0.0, "face": [0.4, 0.4, 0.2, 0.15], "lines": [["They studied women", [0.2, 0.1, 0.6, 0.05], False]]},
                        {"t": 0.4, "face": None, "lines": [["read", [0.4, 0.7, 0.2, 0.05], True]]}]}
    h = hook("x", [{"start": 0.3, "text": "They"}, {"start": 0.6, "text": "studied"}, {"start": 3.4, "text": "late"}],
             look, {"cuts": [1.4, 5.0]}, {"graphics": [{"t_in": 2.2, "kind": "chart"}, {"t_in": 0.5, "kind": "set"}]})
    assert h["face_pct"] == 50 and h["first_cut_s"] == 1.4 and h["first_graphic_s"] == 2.2 and h["first_text_s"] == 0.0, h
    assert h["opening_line"] == "They studied" and h["title_on_screen"] == "They studied women" and h["first_caption_s"] == 0.4
    assert ease_svg("power3.out").startswith("<svg") and ease_svg("back.out(1.7)").count("polyline") == 1
    assert "circle" in dots_svg(c["first graphic (s)"])

    class FakeTells:   # the parts of ai_tells.py scan_tells calls
        @staticmethod
        def hsv(c):
            import colorsys
            r, g, b = (int(c[k:k + 2], 16) / 255 for k in (1, 3, 5))
            h_, s_, v_ = colorsys.rgb_to_hsv(r, g, b)
            return h_ * 360, s_, v_

        @staticmethod
        def tell(t, where, extra=""):
            return {"level": "BAN", "tell": t, "where": where + (": " + extra if extra else ""), "fix": "x"}

        @classmethod
        def is_purple_blue(cls, c):
            h_, s_, v_ = cls.hsv(c)
            return 225 <= h_ <= 295 and s_ >= 0.4

        @staticmethod
        def check_look(look, table):
            return [{"level": "WARN", "tell": "default-grotesk-body", "where": "look", "fix": "x"}] if look.get("font") == "Inter" else []

        @staticmethod
        def check_plan(plan, visuals, table):
            return []

        @staticmethod
        def check_still(img, where):
            return []
    t = scan_tells({"captions": {"font_match": "Inter"}, "graphics": {"palette": [{"hex": "#6A4CF0", "pct": 20}]}},
                   Path("."), [], FakeTells)
    assert t["ran"] and {f["tell"] for f in t["found"]} == {"default-grotesk-body", "purple-blue"}, t
    # A black and brown look whose cards hold a lavender page: no palette tell (the measured audit case).
    dark = {"graphics": {"palette": [{"hex": "#000000", "pct": 30}, {"hex": "#231914", "pct": 10},
                                     {"hex": "#D9C5B0", "pct": 8}, {"hex": "#422720", "pct": 4}],
                         "crop_palette": [{"hex": "#DCCAB8", "pct": 48}, {"hex": "#817EEB", "pct": 9}]}}
    assert not scan_tells(dark, Path("."), [], FakeTells)["found"]
    at = ai_tells_module()
    if at:   # the real checks, when the ai-editor plugin sits next to this one
        real = scan_tells({"captions": {"font_match": "Montserrat", "case": "upper", "highlight_color": "#FFD400", "stroke": True},
                           "graphics": {"palette": [{"hex": "#F2EEE6", "pct": 40}]}}, Path("."), [], at)
        got = {f["tell"] for f in real["found"]}
        assert {"preset-captions", "cream-paper-ground"} <= got, got
        got = {f["tell"] for f in scan_tells(dark, Path("."), [], at)["found"]}
        assert not got & {"purple-blue", "cream-paper-ground"}, got

    # The page, end to end, on a 2 s synthetic clip.
    with tempfile.TemporaryDirectory() as d:
        od = Path(d) / "creator-teardowns" / "demo"
        (od / "video").mkdir(parents=True)
        (od / "graphics").mkdir()
        mp4 = od / "video" / "v1.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=360x640:d=2:r=30",
                        "-pix_fmt", "yuv420p", str(mp4)], check=True)
        from PIL import Image
        Image.new("RGB", (100, 60), "white").save(od / "graphics" / "v1_0.jpg")
        (od / "videos.json").write_text(json.dumps({"videos": [{"id": "v1", "view_count": 9000, "vs_median": 3.0,
                                                                 "webpage_url": "https://example.com/v1"}]}))
        (od / "video" / "v1.graphics.json").write_text(json.dumps({"id": "v1", "duration_s": 2.0, "width": 360, "height": 640,
            "graphics": [{"t_in": 0.4, "t_out": 1.6, "hold_s": 1.2, "box": [0.1, 0.1, 0.8, 0.3], "kind": "real screenshot",
                          "what": "a pricing page", "crop": "graphics/v1_0.jpg",
                          "entrance": {"kind": "slide", "from": "bottom", "ease": "power3.out", "duration_s": 0.3}}]}))
        (od / "style.json").write_text(json.dumps({"handle": "demo", "graphics": {"entrances": [
            {"kind": "slide", "ease": "power3.out", "share_pct": 100, "n": 1, "duration_s": 0.3, "overshoot": 0.0,
             "fade": False, "from": "bottom", "distance_pct": 60}]}}))
        out, style, _ = build(od, FakeTells)
        text = out.read_text()
        assert "<title>@demo teardown</title>" in text and "a pricing page" in text and "data:image/jpeg;base64," in text
        assert "What to take" in text and "power3.out" in text and chr(0x2014) not in text
        assert style["winners"]["n_winners"] == 1 and "hook" in style
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("handle")
    p.set_defaults(fn=cmd_build)
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
