#!/usr/bin/env python3
"""The AI-made look, caught before render (plan.json, visuals.json, the look) and after (settled stills).
Every tell, its source and its fix: references/ai-tells.md. Ids here match the ids there.

    ~/.ai-video-editor/venv/bin/python ai_tells.py edits/NAME [--plan plan.json] [--stills DIR]
    ~/.ai-video-editor/venv/bin/python ai_tells.py demo

Each finding: {"level": "BAN" | "WARN", "tell": id, "where": ..., "fix": ...}. BAN = never by default,
only when the user's own brand or request names it. Exit 1 when anything is BAN.
"""
import colorsys
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plan import EMOJI, STOCK, TYPE_ONLY, icon_only  # noqa: E402
from quality import ai_title_card, generic_pixels, text_bands  # noqa: E402

LOOK_TSX = HERE.parents[2] / "remotion" / "src" / "look.tsx"

# id -> (level, fix). One fix per tell, shared by the plan and pixel checks.
TELLS = {
    "default-grotesk-display": ("BAN", "a serif or the creator's own measured display face; grotesks only for small UI labels"),
    "default-grotesk-body": ("WARN", "fine for UI labels; for anything read as a heading use the creator's face or a serif"),
    "cream-paper-ground": ("BAN", "no ground: put the real capture or the footage behind it, or white/the app's own surface"),
    "flat-saturated-ground": ("BAN", "the real thing on the footage, or the creator's measured palette; no poster grounds"),
    "neon-on-black": ("BAN", "a real dark UI (terminal, app) if the subject has one; otherwise white card, near-black ink"),
    "purple-blue": ("BAN", "colour comes from the real content (logos, captures); no indigo/violet accents or gradients"),
    "gradient-ground": ("WARN", "a flat neutral or the real capture; gradients only when the brand uses one"),
    "glass-panel": ("BAN", "a plain card with a soft real shadow, or no card (the capture itself)"),
    "glow-halo": ("BAN", "crisp edges; depth from a real shadow, never a coloured glow"),
    "emoji": ("BAN", "the word, or the real logo/screenshot"),
    "slop-icon": ("BAN", "the real logo or product UI; sparkles/rocket/wand mean 'AI' and nothing else"),
    "icon-only-card": ("BAN", "a logo, a capture or the user's own image; stock icons only inside a real layout"),
    "text-only-cards": ("BAN", "show the source: capture the page and mark the line; type cards are a rare opt-in"),
    "type-card": ("WARN", "is there a real page, post or product shot that says this? show that instead"),
    "multiplier-stat": ("BAN", "capture the page that published the number and highlight it"),
    "big-number": ("WARN", "a number is a proving beat: show where it was published"),
    "heading-subline-rule": ("BAN", "one line in the speaker's words, or a real capture; no kicker/subline/accent bar stack"),
    "eyebrow-label": ("WARN", "drop the small label above the heading"),
    "one-accent-word": ("WARN", "set the line plainly; emphasis comes from timing to the spoken word"),
    "accent-rule": ("WARN", "remove the short bar under the heading"),
    "dead-centre": ("WARN", "align to an edge or to the subject (head, the object); not every block on the centre line"),
    "title-case": ("WARN", "sentence case or the speaker's own casing"),
    "slop-copy": ("BAN", "the speaker's own words from the transcript; name the concrete thing"),
    "slop-structure": ("WARN", "say the claim plainly, once"),
    "same-entrance": ("WARN", "vary entrances by what the card is (a post slides, a capture lifts, a logo pops)"),
    "same-transition": ("WARN", "cut most scenes hard; keep a designed transition for one or two moments"),
    "bounce-ease": ("WARN", "expo/quart out for entrances; overshoot only on one hero moment"),
    "zoom-every-line": ("WARN", "zoom on the few lines that earn it; the creator's measured rate"),
    "whoosh-every-card": ("WARN", "sound on a few events; most cards land silent"),
    "one-sfx-repeated": ("WARN", "every cue a different file, quieter than the voice"),
    "meme-sfx": ("WARN", "no meme sounds unless the creator uses them"),
    "preset-captions": ("WARN", "the creator's measured caption style; not the one-tap uppercase/yellow/stroke preset"),
    "ai-image-broll": ("BAN", "real footage, real screenshots, real photos of the named thing"),
    "stock-broll": ("WARN", "the named thing itself, captured; stock only when nothing real exists"),
}

GROTESK = {"inter", "inter tight", "geist", "archivo", "roboto", "poppins", "montserrat", "manrope", "dm sans",
           "plus jakarta sans", "outfit", "space grotesk", "satoshi", "general sans", "sora", "urbanist", "figtree",
           "onest", "lexend", "open sans", "work sans", "nunito", "raleway", "helvetica", "helvetica neue", "arial",
           "system-ui", "sf pro", "sf pro display", "segoe ui"}
SLOP_ICONS_BAN = {"sparkles", "sparkle", "wand", "wand-sparkles", "wand-2", "rocket", "stars", "bot", "brain-circuit"}
SLOP_ICONS_WARN = {"zap", "brain", "lightbulb", "trophy", "target", "flame", "gem", "crown", "trending-up", "bolt"}
COPY_BAN = re.compile(r"\b(unlock\w*|supercharg\w*|game[- ]?chang\w*|level[- ]up|seamless\w*|elevat\w*|revolutioni[sz]\w*|"
                      r"effortless\w*|next[- ]level|harness\w*|empower\w*|leverag\w*|delv\w*|unleash\w*|skyrocket\w*|"
                      r"cutting[- ]edge|unparalleled|transform your|boost your|10x your|look no further|"
                      r"in today's (?:fast[- ]paced )?world|the secret to|tapestry|testament to)\b", re.I)
COPY_WARN = re.compile(r"\b(not just\b|it'?s not \w+(?: \w+)?, it'?s|here'?s the thing|let that sink in|the future of|"
                       r"changes everything|mind[- ]?blowing|you won'?t believe)", re.I)
MEME_SFX = re.compile(r"vine|boom|bruh|airhorn|ding|scratch|ka-?ching|cash|bonk|fart|sus", re.I)
AI_IMAGE = ("midjourney", "dall-e", "dalle", "oaidalle", "lexica.art", "civitai", "leonardo.ai", "ideogram",
            "ai-generated", "generated-image", "/gen-", "firefly")
SKIP_KEYS = {"src", "url", "domain", "logo", "handle", "avatar", "time", "likes", "replies", "platform", "name",
             "app", "model", "word", "off_word", "highlight", "find", "target", "mark"}
REAL_TYPES = {"social_post"}          # a real post, quoted verbatim: its copy is not ours
HEAD_KEYS = ("text", "title", "heading", "headline")


def tell(t, where, extra=""):
    lvl, fix = TELLS[t]
    return {"level": lvl, "tell": t, "where": f"{where}{': ' + extra if extra else ''}", "fix": fix}


# ---------------------------------------------------------------- colours and the look

def hsv(c):
    """'#RRGGBB' / '#RGB' / 'rgb(a)(..)' -> (hue deg, s, v), or None."""
    c = (c or "").strip()
    m = re.match(r"#([0-9a-f]{3}|[0-9a-f]{6})\b", c, re.I)
    if m:
        h = m.group(1) if len(m.group(1)) == 6 else "".join(x * 2 for x in m.group(1))
        rgb = [int(h[k:k + 2], 16) / 255 for k in (0, 2, 4)]
    else:
        m = re.match(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)", c)
        if not m:
            return None
        rgb = [float(x) / 255 for x in m.groups()]
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return h * 360, s, v


def colours_in(s):
    return re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([^)]*\)", s or "")


def is_cream(c):
    x = hsv(c)
    return bool(x) and 20 <= x[0] <= 60 and 0.04 <= x[1] <= 0.3 and x[2] >= 0.78


def is_purple_blue(c):
    x = hsv(c)
    return bool(x) and 225 <= x[0] <= 295 and x[1] >= 0.4 and x[2] >= 0.3


def presets(src=None):
    """look.tsx presets -> {name: {key: value}}, spreads resolved. Parsed, so it never drifts from the renderer."""
    try:
        text = src if src is not None else LOOK_TSX.read_text(encoding="utf-8")
    except OSError:
        return {}
    consts, named = {}, {}
    for m in re.finditer(r"(?:const\s+(\w+)\s*:\s*Look\s*=|\"?([\w-]+)\"?\s*:)\s*\{([^{}]*)\}", text):
        body = m.group(3)
        d = {"_spread": re.findall(r"\.\.\.(\w+)", body)}
        d.update(dict(re.findall(r"(\w+):\s*\"([^\"]*)\"", body)))
        if m.group(1):
            consts[m.group(1)] = d
        if d.get("preset"):
            named[d["preset"]] = d

    def flat(d):
        out = {}
        for s in d.get("_spread", []):
            out.update(flat(consts.get(s, {})))
        out.update({k: v for k, v in d.items() if k != "_spread"})
        return out
    return {k: flat(v) for k, v in named.items()}


def resolve_look(look, table=None):
    table = presets() if table is None else table
    look = look or {}
    return {**table.get(look.get("preset") or "neutral", {}), **look}


def check_look(look, table=None):
    lk = resolve_look(look, table)
    out = []
    name = f"look '{lk.get('preset', '?')}'"
    disp, body = (lk.get("font_display") or "").lower(), (lk.get("font") or "").lower()
    if disp in GROTESK:
        out.append(tell("default-grotesk-display", name, lk["font_display"]))
    if body in GROTESK:
        out.append(tell("default-grotesk-body", name, lk["font"]))
    g, acc = lk.get("ground") or "", lk.get("accent") or ""
    gx, ax = hsv(g), hsv(acc)
    if "gradient" in g:
        cols = colours_in(g)
        out.append(tell("purple-blue" if any(map(is_purple_blue, cols)) else "gradient-ground", name, g))
    elif gx:
        if is_cream(g):
            out.append(tell("cream-paper-ground", name, g))
        elif gx[1] >= 0.45 and gx[2] >= 0.2:
            out.append(tell("flat-saturated-ground", name, g))
        elif gx[2] < 0.16 and ax and ax[1] >= 0.6 and ax[2] >= 0.85:
            out.append(tell("neon-on-black", name, f"{g} + {acc}"))
    if is_purple_blue(acc):
        out.append(tell("purple-blue", name, f"accent {acc}"))
    if lk.get("surface") == "glass":
        out.append(tell("glass-panel", name))
    return out


# ---------------------------------------------------------------- cards, copy, motion, sound

def strings(node, skip=SKIP_KEYS, key=None):
    """(key, text) for every text in a props tree, skipping ids, urls and quoted real content."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in skip:
                yield from strings(v, skip, k)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v, skip, key)
    elif isinstance(node, str):
        yield key, node


def icons_in(node):
    if isinstance(node, dict):
        if isinstance(node.get("icon"), str):
            yield node["icon"].lower()
        for v in node.values():
            yield from icons_in(v)
    elif isinstance(node, list):
        for v in node:
            yield from icons_in(v)


def check_copy(text, where):
    out = []
    m = COPY_BAN.search(text)
    if m:
        out.append(tell("slop-copy", where, f"'{m.group(0)}' in {text!r}"))
    m = COPY_WARN.search(text)
    if m:
        out.append(tell("slop-structure", where, f"'{m.group(0)}' in {text!r}"))
    if EMOJI.search(text):
        out.append(tell("emoji", where, repr(text)))
    return out


def check_card(c, where):
    anim = c.get("anim") or {}
    typ, props = anim.get("type"), anim.get("props") or {}
    out = []
    if typ not in REAL_TYPES:
        for k, s in strings(props):
            out += check_copy(s, where)
        for s in (c.get("props") or {}).values():
            if isinstance(s, str):
                out += check_copy(s, where)
    for ic in set(icons_in(props)):
        if ic in SLOP_ICONS_BAN or ic in SLOP_ICONS_WARN:
            out.append({**tell("slop-icon", where, ic), "level": "BAN" if ic in SLOP_ICONS_BAN else "WARN"})
    if anim and icon_only(props):
        out.append(tell("icon-only-card", where))
    if typ in TYPE_ONLY:
        out.append(tell("type-card", where, typ))
    blob = " ".join(s for _, s in strings(props))
    if re.search(r"\d\s*[x×]\b", blob) or str(props.get("suffix", "")).lower() in ("x", "×"):
        if re.search(r"faster|cheaper|better|more|less|than|times", blob, re.I):
            out.append(tell("multiplier-stat", where, blob.strip()[:80]))
    elif typ == "counter":
        out.append(tell("big-number", where))
    if typ in TYPE_ONLY or typ in ("lower_third", "caption_page"):
        if any(props.get(k) for k in ("sub", "subtitle", "subline", "tagline", "caption")):
            out.append(tell("heading-subline-rule", where, "heading + small line under it"))
        if any(props.get(k) for k in ("kicker", "eyebrow", "overline")):
            out.append(tell("eyebrow-label", where, props.get("kicker") or props.get("eyebrow") or props.get("overline")))
        for k in HEAD_KEYS:
            h = props.get(k)
            if isinstance(h, str):
                if re.search(r"\*[^*]+\*", h):
                    out.append(tell("one-accent-word", where, h.replace("\n", " ")))
                words = [w for w in re.findall(r"[A-Za-z][\w']*", h) if len(w) > 3]
                if len(words) >= 3 and all(w[0].isupper() for w in words):
                    out.append(tell("title-case", where, h))
    return out


def check_plan(plan, visuals=None, table=None):
    """Every plan-side tell: [{"level", "tell", "where", "fix"}]."""
    out = check_look(plan.get("look"), table)
    cards = plan.get("cards") or []
    content = [c for c in cards if c.get("lane") != "logo"]
    for i, c in enumerate(cards):
        where = f"card {i} '{c.get('trigger_word', '?')}' {(c.get('anim') or {}).get('type') or c.get('src') or c.get('lane')}"
        out += check_card(c, where)
    typed = [c for c in content if (c.get("anim") or {}).get("type") in TYPE_ONLY]
    if content and len(typed) / len(content) >= 0.5:
        out.append(tell("text-only-cards", "cards", f"{len(typed)} of {len(content)} cards are words on a ground"))
    if len(content) >= 4:
        ents = {c.get("entrance") for c in content}
        if len(ents) == 1:
            out.append(tell("same-entrance", "cards", f"all {len(content)} enter with '{ents.pop()}'"))
    scenes = [c for c in content if c.get("layout") == "scene"]
    pairs = {(c.get("transition_in"), c.get("transition_out")) for c in scenes}
    if len(scenes) >= 3 and len(pairs) == 1 and pairs != {("cut", "cut")}:
        out.append(tell("same-transition", "scenes", f"all {len(scenes)} use {scenes[0].get('transition_in')}/{scenes[0].get('transition_out')}"))
    m = re.search(r"\b(back\.out|elastic|bounce)\w*", json.dumps(plan.get("motion")) + json.dumps(cards), re.I)
    if m:
        out.append(tell("bounce-ease", "motion", m.group(0)))
    dur = (plan.get("durationInFrames") or 0) / (plan.get("fps") or 30)
    zooms = plan.get("zooms") or []
    if dur and len(zooms) / dur * 60 > 15:
        out.append(tell("zoom-every-line", "zooms", f"{len(zooms) / dur * 60:.0f} a minute"))
    sfx = [s.get("src", "") for s in plan.get("sfx") or []]
    whoosh = sum("whoosh" in s for s in sfx)
    if len(content) >= 4 and whoosh >= len(content):
        out.append(tell("whoosh-every-card", "sfx", f"{whoosh} whooshes for {len(content)} cards"))
    if len(sfx) >= 6:
        top = max(set(sfx), key=sfx.count)
        if sfx.count(top) / len(sfx) > 0.5:
            out.append(tell("one-sfx-repeated", "sfx", f"{Path(top).name} is {sfx.count(top)} of {len(sfx)} cues"))
    for s in sorted({Path(s).stem for s in sfx if MEME_SFX.search(Path(s).stem)}):
        out.append(tell("meme-sfx", "sfx", s))
    cap = plan.get("captions") or {}
    st = cap.get("style") or {}
    hl = hsv(st.get("highlight_color") or "")
    if st.get("case") == "upper" and hl and 40 <= hl[0] <= 65 and hl[1] > 0.6 and (st.get("stroke") or st.get("box")):
        out.append(tell("preset-captions", "captions", "uppercase + yellow active word + stroke"))
    if (st.get("font_match") or st.get("font") or "").lower() in GROTESK:
        out.append(tell("default-grotesk-body", "captions", f"{st.get('font_match') or st.get('font')} (fine if measured from the creator)"))
    em = sorted({e for ch in cap.get("chunks") or [] for e in EMOJI.findall(ch.get("text", ""))})
    if em:
        out.append(tell("emoji", "captions", " ".join(em)))
    for v in visuals or []:
        where = f"visual '{v.get('word', '?')}'"
        u = f"{v.get('url', '')} {v.get('src', '')}".lower()
        if any(a in u for a in AI_IMAGE):
            out.append(tell("ai-image-broll", where, u.strip()))
        elif any(s in u for s in STOCK):
            out.append(tell("stock-broll", where, u.strip()))
    return dedupe(out)


def for_brand(found, brand=None):
    """A BAN that the user's own brand kit names (its font, colour or preset) is theirs to choose: WARN."""
    named = [str(v).lower() for v in (brand or {}).values() if isinstance(v, (str, int, float)) and str(v).strip()]
    named += [str(c).lower().lstrip("#") for c in (brand or {}).get("colors") or []]
    out = []
    for f in found:
        if f["level"] == "BAN" and any(n and n in f["where"].lower() for n in named):
            f = {**f, "level": "WARN", "fix": f["fix"] + " (your brand kit names it, so only a warning)"}
        out.append(f)
    return out


def dedupe(found):
    seen, out = set(), []
    for f in found:
        k = (f["tell"], f["where"])
        if k not in seen:
            seen.add(k)
            out.append(f)
    return out


# ---------------------------------------------------------------- rendered pixels (a settled card crop, BGR)

def cream_ground(bgr):
    """Share of the crop in its one dominant colour when that colour is cream paper, else 0."""
    import numpy as np
    q = (bgr >> 4).reshape(-1, 3).astype(np.int32)
    keys, counts = np.unique(q[:, 0] * 256 + q[:, 1] * 16 + q[:, 2], return_counts=True)
    k = int(keys[counts.argmax()])
    b, g, r = ((k >> 8) & 15) * 16 + 8, ((k >> 4) & 15) * 16 + 8, (k & 15) * 16 + 8
    share = counts.max() / len(q)
    return share if share > 0.5 and is_cream(f"#{r:02x}{g:02x}{b:02x}") else 0.0


def glow(bgr):
    """A soft halo round bright cores: share of the 3-14 px ring that is a dimmer copy of the core."""
    import cv2
    import numpy as np
    hsv_ = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(float)
    h, s, v = hsv_[..., 0] * 2, hsv_[..., 1] / 255, hsv_[..., 2] / 255
    vg = float(np.median(v))
    if vg > 0.35:                    # a glow is drawn on dark grounds; on light ones it is a shadow
        return 0.0
    best = 0.0
    for core, like in (((v > 0.85) & (s > 0.45), lambda hc: (s > 0.3) & (np.abs((h - hc + 180) % 360 - 180) < 25)),
                       ((v > 0.95) & (s < 0.15), lambda hc: s < 0.3)):
        if core.sum() < 0.001 * core.size:
            continue
        dist = cv2.distanceTransform((~core).astype(np.uint8), cv2.DIST_L2, 3)
        ring = (dist >= 3) & (dist <= 14)
        if not ring.any():
            continue
        hc = float(np.median(h[core]))
        halo = ring & like(hc) & (v > vg + 0.12) & (v < 0.9)
        best = max(best, halo.sum() / ring.sum())
    return best


def gradient_ground(bgr):
    """(Lab range across the card, planar fit R2) of the ground with text blurred out. A gradient: a big
    range that a plane fits. Photos and captures vary but not as a plane; a flat card has no range."""
    import cv2
    import numpy as np
    H, W = bgr.shape[:2]
    small = cv2.resize(bgr, (160, max(8, round(160 * H / W))), interpolation=cv2.INTER_AREA)
    small = cv2.medianBlur(small, 15)
    lab = cv2.cvtColor(cv2.resize(small, (16, 9), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(float)
    lab[:, 0] *= 100 / 255
    yy, xx = np.mgrid[0:9, 0:16]
    A = np.c_[xx.ravel() / 15, yy.ravel() / 8, np.ones(144)]
    coef, *_ = np.linalg.lstsq(A, lab, rcond=None)
    fit = A @ coef
    ss_tot = ((lab - lab.mean(0)) ** 2).sum()
    r2 = 1 - ((lab - fit) ** 2).sum() / ss_tot if ss_tot > 1e-6 else 0.0
    rng = float(np.linalg.norm(coef[0]) + np.linalg.norm(coef[1]))
    return rng, float(r2)


def ink_bands(bgr):
    import cv2
    import numpy as np
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.int16)
    ink = np.abs(grey - int(np.median(grey))) > 50
    return ink, text_bands(ink)


def accent_rule(bgr):
    """A short solid bar just under the tallest text band: True/False."""
    ink, bands = ink_bands(bgr)
    if len(bands) < 2:
        return False
    H, W = ink.shape
    big = max(bands, key=lambda b: b[1] - b[0])
    bh = big[1] - big[0]
    return any(big[1] <= b[0] <= big[1] + 1.5 * bh and b[1] - b[0] <= 0.2 * bh and b[4] >= 0.75
               and 0.03 * W < b[3] - b[2] < 0.5 * W for b in bands)


def dead_centre(bgr):
    """Every text band on the centre line and the block mid-height: True/False."""
    ink, bands = ink_bands(bgr)
    H, W = ink.shape
    bands = [b for b in bands if b[1] - b[0] >= 0.005 * H]
    if len(bands) < 2 or not ink.any():
        return False
    top, bot = bands[0][0], H - bands[-1][1]
    return all(abs((b[2] + b[3]) / 2 - W / 2) < 0.012 * W for b in bands) and abs(top - bot) < 0.04 * H


def check_still(bgr, where):
    """Every pixel tell on one settled card crop."""
    out = []
    for g in generic_pixels(bgr):
        out.append(tell("neon-on-black" if "near-black" in g else "purple-blue", where, g))
    for g in ai_title_card(bgr):
        out.append(tell("flat-saturated-ground" if "flat" in g else "heading-subline-rule", where, g))
    c = cream_ground(bgr)
    if c:
        out.append(tell("cream-paper-ground", where, f"{c:.0%} of the card"))
    gl = glow(bgr)
    if gl > 0.35:
        out.append(tell("glow-halo", where, f"{gl:.0%} of the ring round bright shapes is halo"))
    rng, r2 = gradient_ground(bgr)
    if rng > 20 and r2 > 0.9 and not any(f["tell"] == "purple-blue" for f in out):
        out.append(tell("gradient-ground", where, f"{rng:.0f} Lab across, plane fit {r2:.2f}"))
    if accent_rule(bgr) and not any(f["tell"] == "heading-subline-rule" for f in out):
        out.append(tell("accent-rule", where))
    if dead_centre(bgr):
        out.append(tell("dead-centre", where))
    return out


def check_stills(stills, plan):
    """N-card.png stills (edit.py names: card i is N = 4 + i), cropped to each card's box."""
    import cv2
    out = []
    W, H = plan["width"], plan["height"]
    for i, c in enumerate(plan.get("cards") or []):
        f = Path(stills) / f"{4 + i}-card.png"
        if c.get("lane") == "logo" or c.get("src") or not f.exists():   # a capture is the real page, not our design
            continue
        img = cv2.imread(str(f))
        if img is None:
            continue
        sy, sx = img.shape[0] / H, img.shape[1] / W
        x, y, w, h = c.get("box") or [0, 0, 100, 100]
        if c.get("layout") != "scene" and [x, y, w, h] != [0, 0, 100, 100]:
            x0, y0 = int(x / 100 * W * sx), int(y / 100 * H * sy)
            img = img[y0:y0 + max(8, int(h / 100 * H * sy)), x0:x0 + max(8, int(w / 100 * W * sx))]
        out += check_still(img, f"{f.name} '{c.get('trigger_word', '?')}'")
    return out


# ---------------------------------------------------------------- demo

def demo():
    import cv2
    import numpy as np
    tsx = '''const EDITORIAL: Look = { preset: "editorial", ground: "#F2EEE6", accent: "#E5482C", surface: "card",
      font: "Archivo", font_display: "Newsreader" };
    const NEUTRAL: Look = { ...EDITORIAL, preset: "neutral", ground: "#FFFFFF", accent: "#0D0D0D", font: "Geist" };
    export const LOOKS = { neutral: NEUTRAL, editorial: EDITORIAL,
      "editorial-dark": { ...EDITORIAL, preset: "editorial-dark", ground: "#151413", accent: "#FF5A36" },
      glass: { ...EDITORIAL, preset: "glass", ground: "rgba(14,15,19,0.78)", surface: "glass", font: "Montserrat", font_display: "Montserrat" } };'''
    T = presets(tsx)
    assert for_brand([tell("default-grotesk-display", "look 'neutral'", "Inter")], {"font": "Inter"})[0]["level"] == "WARN"
    assert T["editorial-dark"]["font"] == "Archivo" and T["neutral"]["ground"] == "#FFFFFF", T
    ids = lambda fs: {f["tell"] for f in fs}  # noqa: E731
    assert ids(check_look({"preset": "editorial"}, T)) == {"cream-paper-ground", "default-grotesk-body"}
    assert "neon-on-black" in ids(check_look({"preset": "editorial-dark"}, T))
    assert {"glass-panel", "default-grotesk-display"} <= ids(check_look({"preset": "glass"}, T))
    assert "purple-blue" in ids(check_look({"preset": "neutral", "ground": "linear-gradient(135deg,#6366F1,#8B5CF6)"}, T))
    assert "flat-saturated-ground" in ids(check_look({"preset": "neutral", "ground": "#1E4A2C"}, T))
    assert ids(check_look({"preset": "neutral", "font": "Newsreader"}, T)) == set()

    card = lambda typ, props, **k: {"anim": {"type": typ, "props": props}, "trigger_word": typ, "entrance": "pop", **k}  # noqa: E731
    plan = {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 900, "look": {"preset": "neutral", "font": "Newsreader"},
            "cards": [card("counter", {"from": 40, "to": 200, "suffix": "x", "label": "faster than Claude"}, layout="scene"),
                      card("title", {"kicker": "people use it to", "text": "sort emails\nfor *five cents*", "sub": "really"}, layout="scene"),
                      card("icon_burst", {"items": [{"icon": "sparkles"}, {"icon": "rocket"}]}, layout="scene"),
                      card("slam", {"text": "Unlock Seamless Workflows 🚀"}),
                      card("social_post", {"text": "this tool is INSANE. unlock it", "name": "Real Person"}),
                      {"src": "images/capture-1.png", "trigger_word": "page", "entrance": "pop"}],
            "captions": {"style": {"case": "upper", "highlight_color": "#FFD400", "stroke": True, "font_match": "Montserrat"},
                         "chunks": [{"text": "wow 🤯"}]},
            "sfx": [{"src": ".sfx/whoosh-in.wav"}] * 7 + [{"src": ".sfx/vine-boom.wav"}]}
    got = check_plan(plan, [{"word": "city", "url": "https://www.pexels.com/photo/1"}, {"word": "robot", "src": "images/midjourney-robot.png"}], T)
    g = ids(got)
    for t in ("multiplier-stat", "heading-subline-rule", "eyebrow-label", "one-accent-word", "slop-icon", "icon-only-card",
              "slop-copy", "emoji", "title-case", "text-only-cards", "same-entrance", "whoosh-every-card", "one-sfx-repeated",
              "meme-sfx", "preset-captions", "default-grotesk-body", "ai-image-broll", "stock-broll"):
        assert t in g, (t, g)
    assert not any("social_post" in f["where"] and f["tell"] in ("slop-copy", "slop-structure") for f in got), got
    assert all(f["level"] in ("BAN", "WARN") and f["fix"] for f in got)
    assert check_plan({"width": 1080, "height": 1920, "look": {"preset": "neutral", "font": "Newsreader"},
                       "cards": [{"src": "images/capture-1.png", "entrance": "pop"}]}, [], T) == []
    # every scene cut hard (a creator who only cuts) is the fix, not the tell
    sc = [{"src": f"images/capture-{i}.png", "entrance": e, "layout": "scene", "transition_in": "cut", "transition_out": "cut"}
          for i, e in enumerate(("pop", "slide", "fade"))]
    assert not [f for f in check_plan({"cards": sc}, [], T) if f["tell"] == "same-transition"]

    # pixels: the rejected title card (cream ground, centred heading, small line, short bar)
    W, H = 540, 960
    crd = np.full((H, W, 3), (206, 220, 223), np.uint8)              # #DFDCCE in BGR
    cv2.rectangle(crd, (120, 330), (420, 480), (20, 20, 20), -1)       # the heading block
    for x in range(170, 370, 14):                                      # a small line under it, dashed (words)
        cv2.rectangle(crd, (x, 520), (x + 8, 545), (110, 110, 110), -1)
    cv2.rectangle(crd, (230, 590), (310, 600), (40, 72, 229), -1)      # a short accent bar
    got = ids(check_still(crd, "t"))
    assert {"cream-paper-ground", "dead-centre"} <= got and ({"heading-subline-rule", "accent-rule"} & got), got
    assert accent_rule(crd) and dead_centre(crd)

    # glow: a neon shape on near-black with a blurred halo; the same shape crisp has none
    dark = np.full((300, 400, 3), 18, np.uint8)
    crisp = dark.copy()
    cv2.rectangle(crisp, (150, 120), (250, 180), (255, 230, 0), -1)
    halo = dark.copy()
    cv2.rectangle(halo, (130, 100), (270, 200), (255, 230, 0), -1)
    halo = cv2.GaussianBlur(halo, (0, 0), 9)
    halo = np.maximum((halo * 0.75).astype(np.uint8), dark)
    cv2.rectangle(halo, (150, 120), (250, 180), (255, 230, 0), -1)
    assert glow(halo) > 0.35 and glow(crisp) < 0.1, (glow(halo), glow(crisp))

    # gradient: a planar blend reads; a flat card and noise do not
    t = np.linspace(0, 1, 400)[None, :, None]
    grad = ((1 - t) * np.array([100, 43, 29]) + t * np.array([218, 205, 248])).repeat(300, 0).astype(np.uint8)
    rng, r2 = gradient_ground(grad)
    assert rng > 20 and r2 > 0.9, (rng, r2)
    assert "purple-blue" in ids(check_still(grad, "g"))                # navy to pink: the purple-blue one
    warm = ((1 - t) * np.array([0, 120, 255]) + t * np.array([180, 160, 0])).repeat(300, 0).astype(np.uint8)
    assert "gradient-ground" in ids(check_still(warm, "g")), check_still(warm, "g")
    assert gradient_ground(np.full((300, 400, 3), 240, np.uint8))[0] < 1
    noise = np.random.default_rng(0).integers(0, 255, (300, 400, 3), dtype=np.uint8)
    assert gradient_ground(noise)[1] < 0.9

    # a white capture card, text left-aligned: nothing
    cap = np.full((400, 700, 3), 255, np.uint8)
    for y in range(40, 360, 40):
        cv2.rectangle(cap, (30, y), (30 + 200 + (y * 7) % 400, y + 18), (30, 30, 30), -1)
    assert check_still(cap, "c") == [], check_still(cap, "c")
    print("ai_tells demo: ok")


def main():
    a = sys.argv[1:]
    if a == ["demo"]:
        return demo()
    if not a:
        sys.exit(__doc__)
    edit = Path(a[0])
    opt = dict(zip(a[1::2], a[2::2]))
    plan = json.loads((edit / opt.get("--plan", "plan.json")).read_text(encoding="utf-8"))
    vis = edit / opt.get("--visuals", "visuals.json")
    found = check_plan(plan, json.loads(vis.read_text(encoding="utf-8")) if vis.exists() else None)
    if "--stills" in opt:
        found += check_stills(edit / opt["--stills"], plan)
    for f in found:
        print(f"{f['level']:4}  {f['tell']:24} {f['where']}\n      fix: {f['fix']}")
    print(f"{sum(f['level'] == 'BAN' for f in found)} BAN, {sum(f['level'] == 'WARN' for f in found)} WARN")
    sys.exit(1 if any(f["level"] == "BAN" for f in found) else 0)


if __name__ == "__main__":
    main()
