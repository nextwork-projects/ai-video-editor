#!/usr/bin/env python3
"""The user's editing profile: the start skill's answers, asked once and reused on every video.

    python3 profile.py show                       the profile as JSON
    python3 profile.py missing                    the intake questions still unanswered, one id per line
    python3 profile.py set <key.path>=<value> ...  several answers in one call, one line out;
                                                  each value parsed as JSON if it can be
    python3 profile.py set <key.path> <value>     one answer (the older form)
    python3 profile.py style <edits/NAME> [--out]  blend the profile's creators into edits/NAME/style.json
                                                  (no creators: the default style, DEFAULT_STYLE)
    python3 profile.py demo                       self-check

File: ~/.ai-video-editor/profile.json (AI_EDITOR_HOME overrides). Shape:

  {"platform": "tiktok", "aspect": "9:16",
   "creators": [{"handle": "somecreator", "take": ["captions", "pace", "visuals"]}],
   "audience": "developers who use Claude", "goal": "follow + comment for the guide",
   "brand": {"colors": ["#F2EEE6", "#E5482C"], "font": "Archivo", "logo": "/path/logo.svg"}  or {"use_creator": true},
   "assets_dir": "/path/to/my/screenshots",
   "names": [{"name": "Claude", "domain": "claude.com"}],
   "avoid": {"emoji": true, "stock": true, "icons": true, "colors": ["#7B61FF"], "notes": ""},
   "captions": {"on": true, "style": "creator"},     style: creator | bold | karaoke | minimal
   "sound": {"sfx": true, "music": false},
   "behind": true}                                     cards sit behind the speaker (style-edit matte.py)

Look order (plan.py): the profile's brand kit > the copied creators' measured style.json > the
`editorial` preset. No creator: DEFAULT_STYLE (style-edit references/plan.md "No creator"). Stdlib only.
"""
import colorsys
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
# Style questions are asked once, at setup. Video questions belong to each video, asked by start.
STYLE_QUESTIONS = ("platform", "creators", "liked_videos", "brand", "assets_dir", "avoid", "captions", "sound", "behind")
VIDEO_QUESTIONS = ("audience", "names")
QUESTIONS = STYLE_QUESTIONS + VIDEO_QUESTIONS
DEFAULTS = {"platform": "tiktok", "aspect": "9:16", "creators": [], "liked_videos": [], "brand": {"use_creator": True},
            "assets_dir": "", "names": [], "avoid": {"emoji": True, "stock": True, "icons": True, "colors": []},
            "captions": {"on": True, "style": "creator"}, "sound": {"sfx": True, "music": False},
            "behind": False}   # unanswered: off, so no plan needs the cutout step until the user says yes
ASPECT = {"tiktok": "9:16", "reels": "9:16", "shorts": "9:16", "youtube": "16:9"}
# Fonts every AI tool reaches for, and the default geometric / neo grotesks that read as AI-made as a
# heading. Swapped for the preset's face unless the user's brand names them.
GENERIC_FONTS = {"inter", "roboto", "poppins", "montserrat", "open sans", "arial", "helvetica", "archivo", "geist",
                 "manrope", "dm sans", "plus jakarta sans", "outfit", "space grotesk", "satoshi", "general sans", "sora", "urbanist"}
# Flat saturated colour grounds read as AI-made: only the user's own brand kit may name one.
FLAT_GROUND_PRESETS = ("poster-red", "poster-green", "poster-blue")
CAPTION_STYLES = {
    "bold": {"effect": "pop", "weight": 800, "case": "lower", "words_per_caption": 2},
    "karaoke": {"effect": "karaoke", "weight": 800, "words_per_caption": 4, "max_lines": 2},
    "minimal": {"effect": "reveal", "weight": 600, "case": "lower", "words_per_caption": 3, "stroke": False},
}


def path():
    return HOME / "profile.json"


def load():
    p = path()
    return {**DEFAULTS, **(json.loads(p.read_text()) if p.exists() else {})}


def save(prof):
    HOME.mkdir(parents=True, exist_ok=True)
    raw = dict(prof)   # only what was answered: missing() reads the file
    raw["aspect"] = ASPECT.get(raw.get("platform"), raw.get("aspect", "9:16"))
    path().write_text(json.dumps(raw, indent=1))
    return path()


def missing(group=QUESTIONS):
    """The intake questions in `group` with no saved answer yet."""
    have = json.loads(path().read_text()) if path().exists() else {}
    return [q for q in group if q not in have]


# ---------- colour ----------
def rgb(hexs):
    h = hexs.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hls(hexs):
    return colorsys.rgb_to_hls(*rgb(hexs))


def lum(hexs):
    r, g, b = rgb(hexs)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_hex(s):
    return isinstance(s, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}|#?[0-9a-fA-F]{3}", s) is not None


def generic_colour(hexs):
    """The AI-default accents: saturated purple to blue, and neon on near-black."""
    h, l, s = hls(hexs)
    return s > 0.45 and 0.5 < l < 0.85 and 225 <= h * 360 <= 290


def near(a, b, tol=0.12):
    return sum((x - y) ** 2 for x, y in zip(rgb(a), rgb(b))) ** 0.5 < tol


# The keys the renderer reads (remotion/src/look.tsx). A teardown's look.json-style notes are dropped.
LOOK_KEYS = ("preset", "ground", "ink", "muted", "accent", "accent_ink", "line", "surface", "radius", "shadow", "font",
             "font_display", "font_serif", "weight", "weight_display", "tracking", "case", "texture", "texture_amount", "decor")


def creator_look(style):
    """A look from a creator's measured style.json: graphics.palette (hex + share) and captions.font_match.
    Ground: the most used light palette colour (paper) or, with none, editorial-dark. Accent: the most
    saturated palette colour, when there is one. Nothing measured: {} (the preset stands)."""
    out = {k: v for k, v in (style.get("look") or {}).items() if k in LOOK_KEYS}
    pal = [p["hex"] for p in sorted((style.get("graphics") or {}).get("palette") or [], key=lambda p: -p.get("pct", 0))
           if is_hex(p.get("hex"))]
    if pal and "ground" not in out:
        light = [c for c in pal if lum(c) > 0.72 and hls(c)[2] < 0.35]
        if light:
            out["ground"] = light[0]
        elif lum(pal[0]) < 0.15:
            out.setdefault("preset", "editorial-dark")
    sat = [c for c in pal if hls(c)[2] > 0.5 and 0.25 < hls(c)[1] < 0.75]
    if sat and "accent" not in out:
        out["accent"] = sat[0]
    font = ((style.get("captions") or {}).get("font_match") or "").strip()
    if font and font.lower() not in GENERIC_FONTS and "font" not in out:
        out["font"] = font
    return out


def brand_look(brand):
    """A look from the profile's brand kit: colours (lightest = ground when light enough, the most
    saturated = accent, the darkest = ink) and fonts."""
    out = {}
    cols = [c if c.startswith("#") else "#" + c for c in (brand.get("colors") or []) if is_hex(c)]
    if cols:
        by_l = sorted(cols, key=lum)
        if lum(by_l[-1]) > 0.72:
            out["ground"] = by_l[-1]
        if lum(by_l[0]) < 0.2:
            out["ink"] = by_l[0]
        sat = sorted(cols, key=lambda c: -hls(c)[2])
        if hls(sat[0])[2] > 0.3:
            out["accent"] = sat[0]
    for k in LOOK_KEYS:
        if k not in out and brand.get(k):
            out[k] = brand[k]
    if brand.get("font") and not brand.get("font_display"):
        out["font_display"] = brand["font"]
    return out


def resolve_look(style, prof=None, warn=print):
    """plan.json "look": profile brand kit > style.json (creator, with taste.json merged in) > editorial.
    The anti-generic rules apply to everything that did not come from the user's own brand kit."""
    prof = prof or {}
    brand = prof.get("brand") or {}
    look = {"preset": "editorial", **creator_look(style)}
    if look.get("preset") == "glass" and not (style.get("look") or {}).get("preset") == "glass":
        look["preset"] = "editorial"
    own = brand_look(brand) if not brand.get("use_creator") or brand.get("colors") or brand.get("font") else {}
    for k in ("accent", "ground"):
        if k in look and k not in own and generic_colour(look[k]):
            warn(f"look: {k} {look[k]} is the purple-blue AI default; using the preset's")
            look.pop(k)
    if look.get("preset") in FLAT_GROUND_PRESETS and look["preset"] != brand.get("preset"):
        warn(f"look: {look['preset']} is a flat saturated ground, the AI-made look; using neutral")
        look["preset"] = "neutral"
    if look.get("preset") == "glass" and "glass" != brand.get("preset"):
        warn("look: the dark glass panel with a neon accent is the AI default; using editorial")
        look["preset"] = "editorial"
    for k in ("font", "font_display"):
        if (look.get(k) or "").lower() in GENERIC_FONTS and k not in own:
            warn(f"look: {look[k]} is the font every AI tool uses; using the preset's")
            look.pop(k)
    for c in (prof.get("avoid") or {}).get("colors") or []:
        if not is_hex(c):
            continue
        c = c if c.startswith("#") else "#" + c
        for k in ("accent", "ground", "ink"):
            if k in look and k not in own and near(look[k], c):
                warn(f"look: {k} {look[k]} is close to {c}, which the profile avoids; using the preset's")
                look.pop(k)
    look.update(own)
    return look


# ---------- no creator: the default style ----------
# The recommended answer when no creator is named. Overlay-first and smooth (PRINCIPLES.md "Motion"): the smooth
# personality, punch zooms the renderer eases (0.16 s power2.out, never a one-frame snap), captions the footage
# decides the treatment of (plan.py's contrast ladder). Numbers: the median of the measured styles the editor was
# built against (the style.json example in style-edit references/contracts.md, the test teardown, one 7-video
# creator teardown): punch zooms in all three, scale 1.18 / 1.18 / 1.2, 6 / 9.5 / 10 a minute; median shot 2.4 /
# 2.4 / 3.98 s; 1 / 3 / 3 words a caption, 4.7 / 5.5 / 6.5% type, y 62 / 66 / 75%, lower case in all three.
# max_hold_s: a sentence longer than this still gets a zoom change (plan.py place_zooms), so nothing holds still
# past check.py's 6 s. A push (eased over 0.8 s) was tried first: on a talking head the render check reads the
# speaker's own movement during a slow 1.12 push as a surge (6 WARNs on the sample take).
DEFAULT_STYLE = {
    "handle": "default",
    "pace": {"median_shot_s": 2.4, "max_pause_s": 0.25},
    "motion": "smooth",
    "zoom": {"per_min": 9.5, "kind": "punch", "scale": 1.18, "duration_s": 0.0, "on": "sentence_start", "max_hold_s": 5.0},
    "captions": {"present": True, "words_per_caption": 3, "y_pct": 66, "size_pct": 5.5, "case": "lower",
                 "weight": 800, "color": "#FFFFFF", "stroke": False, "box": False, "animation": "pop"},
}


def default_style(prof=None):
    """DEFAULT_STYLE with the profile's caption and sound answers laid over."""
    return answers(json.loads(json.dumps(DEFAULT_STYLE)), prof or {})


# ---------- blending creators ----------
PARTS = {"captions": ("captions",), "pace": ("pace", "zoom", "cuts", "motion"),
         "visuals": ("graphics", "look", "layout", "cats", "events")}


def blend(styles, creators, prof=None):
    """One style.json from several creators: each creator gives the parts listed in its `take`
    (captions, pace, visuals). A part nobody claims comes from the first creator. Then the profile's
    caption and sound answers lay over it."""
    prof = prof or {}
    order = [c["handle"] for c in creators if c.get("handle") in styles] or list(styles)
    out = {"handle": "+".join(order), "blend": {}}
    for part, keys in PARTS.items():
        src = next((c["handle"] for c in creators if c.get("handle") in styles and part in (c.get("take") or [])),
                   order[0] if order else None)
        if not src:
            continue
        out["blend"][part] = src
        for k in keys:
            if k in styles[src]:
                out[k] = json.loads(json.dumps(styles[src][k]))
    if order:
        out.setdefault("aspect", styles[order[0]].get("aspect"))
    return answers(out, prof)


def answers(out, prof):
    """The profile's caption and sound answers over a style."""
    cap = prof.get("captions") or {}
    if cap.get("on") is False:
        out["captions"] = {**out.get("captions", {}), "present": False}
    elif cap.get("style") in CAPTION_STYLES:
        out["captions"] = {**out.get("captions", {}), **CAPTION_STYLES[cap["style"]]}
    if (prof.get("sound") or {}).get("sfx") is False:
        out["sfx"] = False
    return out


def write_style(edit_dir, root=Path("."), out=None):
    prof = load()
    styles = {}
    for c in prof.get("creators") or []:
        p = Path(root) / "creator-teardowns" / c["handle"] / "style.json"
        if p.exists():
            styles[c["handle"]] = json.loads(p.read_text())
        else:
            print(f"warning: no {p}; run creator-teardown on @{c['handle']} first", file=sys.stderr)
    if not prof.get("creators"):
        style = default_style(prof)
    elif not styles:
        sys.exit("ERROR: no creator style.json found for the profile's creators")
    else:
        style = blend(styles, prof["creators"], prof)
    out = Path(out or Path(edit_dir) / "style.json")
    out.write_text(json.dumps(style, indent=1))
    return out, style


def set_pairs(prof, pairs):
    """Each (dotted key, text) into prof; the text is parsed as JSON if it can be."""
    for key, text in pairs:
        try:
            val = json.loads(text)
        except json.JSONDecodeError:
            val = text
        *head, last = key.split(".")
        cur = prof
        for k in head:
            cur = cur.setdefault(k, {})
        cur[last] = val
    return prof


def demo():
    global HOME
    with tempfile.TemporaryDirectory() as d:
        HOME = Path(d)
        assert missing() == list(QUESTIONS) and missing(VIDEO_QUESTIONS) == ["audience", "names"]
        save({"platform": "youtube", "creators": [{"handle": "a"}]})
        assert load()["aspect"] == "16:9" and "creators" not in missing() and "audience" in missing()
        # no creators (the recommended answer): the default style is written, never an exit
        save({"creators": [], "captions": {"style": "karaoke"}})
        out, st = write_style(d, out=Path(d) / "style.json")
        assert out.exists() and st["zoom"]["per_min"] >= 6 and st["captions"]["effect"] == "karaoke", st
        assert json.loads(out.read_text())["handle"] == "default"
    styles = {"a": {"captions": {"size_pct": 4}, "zoom": {"per_min": 6}, "graphics": {"palette": [
                  {"hex": "#000000", "pct": 14}, {"hex": "#DEDACC", "pct": 8}, {"hex": "#E5482C", "pct": 3}]}},
              "b": {"captions": {"size_pct": 7, "font_match": "Inter"}, "pace": {"median_shot_s": 1.2}}}
    s = blend(styles, [{"handle": "a", "take": ["visuals"]}, {"handle": "b", "take": ["captions", "pace"]}],
              {"captions": {"style": "karaoke"}, "sound": {"sfx": False}})
    assert s["captions"]["size_pct"] == 7 and s["captions"]["effect"] == "karaoke" and s["sfx"] is False, s
    assert s["blend"] == {"captions": "b", "pace": "b", "visuals": "a"} and s["pace"]["median_shot_s"] == 1.2
    lk = resolve_look(s, {}, warn=lambda m: None)
    assert lk["ground"] == "#DEDACC" and lk["accent"] == "#E5482C" and "font" not in lk, lk    # Inter refused
    w = []
    lk = resolve_look({"look": {"accent": "#7B61FF", "preset": "glass"}}, {}, warn=w.append)
    assert "accent" not in lk and lk["preset"] == "editorial" and len(w) == 2, (lk, w)
    lk = resolve_look({}, {"brand": {"colors": ["#7B61FF", "#FFFFFF", "#111111"], "font": "Inter"}}, warn=w.append)
    assert lk["accent"] == "#7B61FF" and lk["ground"] == "#FFFFFF" and lk["font"] == "Inter", lk   # the user's own brand wins
    lk = resolve_look({"look": {"accent": "#E5482C"}}, {"avoid": {"colors": ["#E04A2E"]}}, warn=w.append)
    assert "accent" not in lk
    lk = resolve_look({"look": {"preset": "poster-green", "font_display": "Archivo"}}, {}, warn=w.append)
    assert lk["preset"] == "neutral" and "font_display" not in lk, lk     # flat ground and a default grotesk refused
    # several answers in one call: one line out, every value in place
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, AI_EDITOR_HOME=d)
        r = subprocess.run([sys.executable, __file__, "set", "platform=youtube", "sound.music=false",
                            'names=["Jev"]', "brand.url=https://x.io/?a=b"], capture_output=True, text=True, env=env)
        assert r.returncode == 0 and r.stdout.count("\n") == 1, (r.stdout, r.stderr)
        got = json.loads((Path(d) / "profile.json").read_text())
        assert got["platform"] == "youtube" and got["sound"] == {"music": False} and got["names"] == ["Jev"], got
        assert got["brand"]["url"] == "https://x.io/?a=b", got
        r = subprocess.run([sys.executable, __file__, "set", "audience", "builders"], capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0 and json.loads((Path(d) / "profile.json").read_text())["audience"] == "builders"
    print("profile ok")


def main():
    a = sys.argv[1:]
    if a == ["demo"]:
        return demo()
    if a == ["show"]:
        print(json.dumps(load(), indent=1))
    elif a and a[0] == "missing":
        group = {"--style": STYLE_QUESTIONS, "--video": VIDEO_QUESTIONS}.get(a[1] if len(a) > 1 else "", QUESTIONS)
        print("\n".join(missing(group)) or "(all answered)")
    elif len(a) >= 2 and a[0] == "set":
        pairs = [(a[1], a[2])] if len(a) == 3 and "=" not in a[1] else [x.split("=", 1) for x in a[1:]]
        if any(len(p) != 2 or not p[0] for p in pairs):
            sys.exit("usage: profile.py set key=value [key=value ...]  (or: set key value)")
        prof = set_pairs(json.loads(path().read_text()) if path().exists() else {}, pairs)
        print(f"set {', '.join(k for k, _ in pairs)} -> {save(prof)}")
    elif len(a) >= 2 and a[0] == "style":
        out, style = write_style(a[1], out=a[3] if len(a) > 3 and a[2] == "--out" else None)
        print(f"{out}: {style['handle']}, " + (f"parts from {style['blend']}" if style.get("blend") else
                                              "no creator: the default style (DEFAULT_STYLE)"))
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
