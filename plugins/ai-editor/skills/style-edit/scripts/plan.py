#!/usr/bin/env python3
"""Turn a creator's style.json + a cut's words.json into plan.json for the Remotion render.

    python3 plan.py <style.json> <edits/NAME/captions.json> [--images images.json (default: next to it)]
                    [--aspect auto|9:16|16:9] [--layout overlay|split] [--out edits/NAME/plan.json]
    python3 plan.py demo      self-check

cut.mp4 is read from the words' folder (ffprobe gives its size, fps and length). A missing or empty
style.json plans with the default style (profile.py DEFAULT_STYLE) and says so.
images.json, optional: [{"src": "images/a.png", "word": "notion"}, ...]. src is relative
to the edit folder. Optional per image: "nth" (which time the word is said, default the
next one after the previous card), "box" [x, y, w, h] in percent, "entrance", "hold_s".
visuals.json next to words.json, optional: its "anim" beats become animated cards
(its "capture" beats arrive through images.json once capture.mjs has run).
Every card gets a "layout" (references/motion.md "Layout per template"): explaining templates are
full-frame scenes (a cut-away with a designed transition), pile/icon_burst and vertical captures sit in
the split panel (the speaker in a window under it, framed from face.json; the panel opens only when a
card needs it), and only logos, lower thirds, arrow callouts and caption pages stay boxes over the
footage. A beat's "layout" overrides, except that an explaining card on vertical is never a box.
--layout overlay never opens the panel: split cards become scenes.
Also writes "look" (profile brand kit > creator style.json > editorial; references/motion.md) and
"motion" (the personality, from the creator's pace). The anti-generic rules (visuals.md) run first.
The user's profile (~/.ai-video-editor/profile.json, the start skill) supplies brand, avoid and sound.
Shapes: references/contracts.md, references/motion.md. Stdlib only, deterministic.
"""
import argparse
import inspect
import json
import math
import re
import subprocess
import sys
from pathlib import Path

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
PAUSE_S = 0.3          # a gap this long starts a new caption chunk
MAX_WORD_S = 0.8       # longest a single spoken word is believed to last
HOLD_TAIL_S = 0.3      # a caption stays up this long after its last word
CARD_LEAD_S = 0.1      # a card lands this long before its word
ENTRANCES = ("pop", "slide", "fade", "scale")
# Entrance per overlay format, so cards do not all arrive the same way (ai-tells.md "same-entrance"):
# a capture lifts, a post or a chat slides, a sticker or a logo pops, a terminal fades up.
FORMAT_ENTRANCE = {"shot": "scale", "browser": "slide", "sticker": "pop", "plain": "scale", "social_post": "slide", "chat": "slide",
                   "terminal": "fade", "toasts": "slide", "logo_cluster": "pop", "side_by_side": "slide", "video_card": "scale",
                   "logo": "pop", "logo_sting": "pop"}
# Above the head in a vertical frame, the right side in a wide one.
DEFAULT_BOX = {"9:16": [10, 15, 74, 20], "16:9": [54, 10, 40, 48]}
# Where the app's own UI sits, in percent: left, top, right, bottom. Vertical: the
# TikTok/Reels/Shorts top bar, the like/comment/share rail on the right and the
# caption/username block at the bottom. Wide: YouTube's progress bar.
SAFE = {"9:16": (6, 14, 14, 22), "16:9": (3, 5, 3, 10)}
# Vertical overlays (free_regions) may go further than SAFE: up to 10% from the top (the top bar holds only
# small text), 3% from the sides, and over the right rail while they end above RAIL_TOP (the like/share
# rail starts lower down). check.py plan allows the same.
OVERLAY_TOP, OVERLAY_EDGE, RAIL_TOP = 10, 3, 40
LOGO_S = 1.2           # a logo stays up this long
LOGO_BOX_H = 11        # logo tile height, % of the frame
# logo_cluster on vertical (Overlays.tsx reads props.band and props.size): the logos' outer edges span this
# band of the width, centred, each this % of the width wide. check.py plan FAILs a vertical cluster whose
# ink is under INK_MIN_W of the width or off centre, the same as check.py render measures it.
LOGO_BAND, LOGO_SIZE = (17, 83), 20
INK_MIN_W = 60
TOP_CARD_MAX_H = {"9:16": 22, "16:9": 80}   # a top card taller than this reaches the head
SCENES = ("flow",)   # picture scenes: parts land on their own words
# Every template in remotion/src/Templates.tsx (references/motion.md), plus the two original names that remain.
TEMPLATES = ("flow", "logo_sting", "social_post", "arrow_callout", "icon_burst", "caption_page")
# The overlay formats (remotion/src/Overlays.tsx): real pictures floating over the footage. The default.
OVERLAYS = ("shot", "browser", "sticker", "chat", "terminal", "toasts", "logo_cluster", "side_by_side", "video_card")
FORMATS = ("shot", "browser", "sticker", "plain")    # how an image card is drawn
# Type cards (words on a ground) were removed from the product (2026-10-06): an old visuals.json naming one
# is skipped with a pointer to the overlay format that shows the real source instead.
TYPE_ONLY = ("slam", "title", "counter", "bar_chart", "line_chart", "checklist", "phrase_mark", "keyword", "steps", "race",
             "versus", "lower_third", "pile")
INSTEAD = {"counter": "a capture (sticker) of the page that published the number, the number highlighted",
           "bar_chart": "side_by_side of the two real pages, or a sticker of the sentence with the figures",
           "line_chart": "a capture of the real chart, ringed where the speaker points",
           "versus": "side_by_side with the two real screenshots", "lower_third": "the person's real post (post) or page (capture)",
           "pile": "a logo_cluster of the real logos"}
# Content aspect (width / height) of each overlay, to pick the free region around the head it fills best.
ASPECT = {"browser": 1.45, "chat": 1.9, "terminal": 1.8, "toasts": 3.2, "social_post": 2.2, "side_by_side": 2.6,
          "video_card": 16 / 9, "flow": 2.4, "icon_burst": 1.6}
FIXED_BOX = ("logo", "logo_sting", "arrow_callout", "caption_page")   # keep their own box
LEGACY = ("logo", "flow")
ANIMS = tuple(dict.fromkeys(TEMPLATES + OVERLAYS + LEGACY))
# Where each card sits (references/motion.md "Layout per template"). "scene": a full-frame cut-away on
# the look's ground. "split": the split layout's top panel. "box": a card over the footage, only for these.
BOX_OK = ("logo", "logo_sting", "arrow_callout", "caption_page")
SPLIT_FIRST = ("icon_burst",)    # scene or split: split keeps the speaker in shot
LAYOUTS = ("scene", "split", "box")
SCENE_BOX = [0, 0, 100, 100]            # "use the scene box" (the renderer's, clear of the app's UI)
SCENE_TYPE_BOX = {True: [6, 13, 88, 52], False: [6, 9, 88, 70]}   # Scene.tsx sceneBox, vertical / wide: where it draws
TRANSITIONS = ("match", "iris")         # renderer defaults: in, out
# A scene's transition in takes about 0.62 s x the personality's k (Scene.tsx). The scene starts this
# much earlier than a box card, so the ground has mostly grown by the word. A "cut" in has nothing to grow:
# it is whole on its first frame, so it starts where a box card does (CARD_LEAD_S before its word).
SCENE_LEAD_S = 0.3
# An overlay's entrance (motion.ts dropIn: expo.out over 0.62 s x k) carries half its ink, what quality.py counts as
# landed (LAND_SHARE), this long x k after it starts: 0.06 and 0.08 s on the sample take's captures. plan.py starts
# the card this much (x k) before CARD_LEAD_S ahead of its word, the renderer starts the drop-in there (motion.ts
# reads the same two numbers; the demo checks they match) and quality.py's word model reads it (scene_land).
OVERLAY_LEAD_S = 0.07
MOTION_K = {"punchy": 0.7, "snappy": 0.8, "smooth": 1.0, "calm": 1.35}
# Personality from the copied creator's median shot length (references/motion.md "Personalities").
PERSONALITY = ((1.4, "punchy"), (2.4, "snappy"), (4.0, "smooth"), (1e9, "calm"))
STOCK = ("unsplash.com", "pexels.com", "shutterstock.com", "istockphoto.com", "gettyimages.", "pixabay.com",
         "freepik.com", "stock.adobe.com", "depositphotos.com", "dreamstime.com", "123rf.com")
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")
READ_XH = 28           # px: a capture's x-height on a 1080-wide frame under this is too small to read on a phone
MIN_CARD_S = 0.5       # a card cut shorter than this by the next one is dropped
# Pacing (SKILL.md step 3, one rule): a card where a sentence names something real, never two at once. The
# longest stretch with no card is 2 x the copied creator's measured mean gap (120 / graphics.per_min), else
# GAP_S; inside a longer one the frame still changes (a zoom) at least every QUIET_HOLD_S. check.py plan WARNs
# a longer gap that holds a named thing or a stretch with no change.
GAP_S = 10.0
QUIET_HOLD_S = 5.0


def clean(text):
    return re.sub(r"[^\w'’-]+", "", text)


def cased(text, mode):
    text = clean(text)
    return text.lower() if mode == "lower" else text.upper() if mode == "upper" else text


def ends_sentence(text):
    return text.rstrip().endswith((".", "?", "!"))


def ends_clause(text):
    return text.rstrip().endswith((".", "?", "!", ",", ";", ":"))


def join_hyphens(words):
    """Whisper splits "one-for-one" into "one", "-for", "-one": a token starting with "-" joins the word before."""
    out = []
    for w in words:
        if out and w["text"].strip().startswith("-") and len(w["text"].strip()) > 1:
            out[-1] = {**out[-1], "text": out[-1]["text"].rstrip() + w["text"].strip(), "end": w["end"]}
        else:
            out.append(w)
    return out


def chunk_captions(words, n, mode):
    chunks, cur = [], []
    words = join_hyphens(words)
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or len(cur) >= n or ends_clause(w["text"]) or nxt["start"] - w["end"] > PAUSE_S:
            chunks.append(cur)
            cur = []
    out = []
    for i, c in enumerate(chunks):
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else None
        # A transcriber can stretch one word over a pause or a misheard run; never hold past
        # a plausible spoken length plus a short tail.
        last = c[-1]
        end = min(last["end"], last["start"] + MAX_WORD_S) + HOLD_TAIL_S
        if nxt is not None:
            end = min(end, nxt)
        ws = [{"text": cased(w["text"], mode), "start": w["start"], "end": w["end"]} for w in c]
        ws = [w for w in ws if w["text"]]
        if ws:
            out.append({"text": " ".join(w["text"] for w in ws), "start": c[0]["start"],
                        "end": round(end, 3), "words": ws})
    return out


def zoom_times(words, on, cuts):
    """Candidate moments for a zoom, in seconds."""
    if on == "every_cut" and cuts:
        return cuts
    starts = [w["start"] for i, w in enumerate(words)
              if i == 0 or ends_sentence(words[i - 1]["text"]) or w["start"] - words[i - 1]["end"] > 0.5]
    if on != "emphasis":
        return starts
    # Emphasis: the longest-held word of each phrase (people stretch the word they stress).
    out, phrase = [], []
    for i, w in enumerate(words):
        phrase.append(w)
        if i + 1 == len(words) or words[i + 1]["start"] - w["end"] > 0.2:
            out.append(max(phrase, key=lambda x: x["end"] - x["start"])["start"])
            phrase = []
    return out


def card_gap_s(style):
    """The longest stretch with no card: 2 x the creator's measured mean gap between cards, else GAP_S."""
    pm = graphics(style, "graphics").get("per_min")
    return round(120 / pm, 1) if pm else GAP_S


def named_beats(edit_dir):
    """route.py's beats.json sentences that name one of the profile's things ([] when there is none)."""
    bj = edit_dir and Path(edit_dir) / "beats.json"
    return [x for x in json.loads(bj.read_text()) if x.get("names")] if bj and bj.exists() else []


def card_gaps(cards, duration):
    """[(start, end)] stretches of the video with no card up, the opening and the end included."""
    out, t = [], 0.0
    for c in sorted(cards, key=lambda c: c["start"]):
        if c["start"] > t:
            out.append((round(t, 3), round(c["start"], 3)))
        t = max(t, c["end"])
    if duration > t:
        out.append((round(t, 3), round(duration, 3)))
    return out


def place_zooms(zoom, words, duration, cuts, cut_kinds=None, quiet=()):
    """quiet: stretches with no card longer than card_gap_s; inside them a zoom change comes at least every
    QUIET_HOLD_S, so the frame keeps changing while the speaker carries the line."""
    per_min = zoom.get("per_min") or 0
    if not per_min or not words:
        return []
    gap = 60 / per_min * 0.8
    picked = []
    cands = zoom_times(words, zoom.get("on", "sentence_start"), cuts)
    mix = cut_kinds or {}
    if mix.get("zoom-punch") and zoom.get("on") == "every_cut" and cuts:
        # pace.cut_kinds: her share of cuts that punch in; the rest are hard holds (no zoom)
        z = mix["zoom-punch"] / sum(mix.values())
        cands = [t for t, k in zip(cands, deal({"zoom": z, "hold": 1 - z}, len(cands))) if k == "zoom"]
    for t in cands:
        if not picked or t - picked[-1] >= gap:
            picked.append(t)
    hold = zoom.get("max_hold_s")
    starts = [w["start"] for w in words]
    longest = lambda a, b: min(hold or 1e9, QUIET_HOLD_S if any(qa < (a + b) / 2 < qb for qa, qb in quiet) else 1e9)
    while (hold or quiet) and picked:
        # the default style (and any stretch with no card): a long sentence still gets a zoom change, on the
        # word start nearest its middle
        add = {min(mids, key=lambda t: abs(t - (a + b) / 2))
               for a, b in zip(picked, picked[1:] + [duration]) if b - a > longest(a, b)
               for mids in [[t for t in starts if a + 1 < t < b - 1]] if mids}
        if not add:
            break
        picked = sorted(set(picked) | add)
    kind = zoom.get("kind", "punch")
    ease = 0.0 if kind == "punch" else (zoom.get("duration_s") or 0.4)
    # Alternate in / out so the frame never creeps tighter: every other change goes back to 1x.
    ends = picked[1:] + [duration]
    named = {"ease": zoom["ease"]} if kind != "punch" and zoom.get("ease") not in (None, "none") else {}
    return [{"start": round(s, 3), "end": round(e, 3), "scale": zoom.get("scale", 1.15),
             "kind": kind, "ease_s": ease, **named}
            for i, (s, e) in enumerate(zip(picked, ends)) if i % 2 == 0 and e > s]


ENTER_S = (0.15, 0.75)   # a card's entrance window: from just before its start to when it has settled


def clear_entrances(zooms, cards):
    """A zoom change never lands while a card is entering: it moves to just before the card starts (a zoom that
    gets shorter than 0.5 s, or runs into the one before, is dropped). Two moves at once compete for the eye,
    and the render check cannot time a card's landing while the footage under it jumps."""
    for c in cards:
        a, b = c["start"] - ENTER_S[0], c["start"] + ENTER_S[1]
        for z in zooms:
            for k in ("start", "end"):
                if a < z[k] < b:
                    z[k] = round(max(0.0, a), 3)
    out = []
    for z in zooms:
        if z["end"] - z["start"] >= 0.5 and (not out or z["start"] >= out[-1]["end"]):
            out.append(z)
    return out


def card_defaults(style):
    cats = style.get("cats") or (style["events"] if isinstance(style.get("events"), dict) else {})
    top = next(iter(cats.values()), {}) if cats else {}
    ent = next((e[0] for e in top.get("entrance") or [] if e[0] in ENTRANCES), None)   # None: per format (FORMAT_ENTRANCE)
    return top.get("hold_s") or 2.5, ent, top.get("box") or (graphics(style, "layout").get("layout") or {}).get("median_box")


# ---------- the creator's measured fields (creator-teardown style.json; references/visuals.md "From the teardown") ----------
# Each is used only when present and only when the blend took its part (editplan.py --take strips the rest).
# Absent: the defaults above, unchanged.

def took(style, part):
    """A teardown part ("graphics", "entrances", "layout", "pace", "sound") counts only when the blend took it.
    No blend.take (a single creator, or an older file): every part present counts."""
    take = (style.get("blend") or {}).get("take")
    return take is None or part in take


def graphics(style, part):
    """style.json "graphics" when `part` was taken, else {}."""
    return (style.get("graphics") or {}) if took(style, part) else {}


def deal(shares, n):
    """n picks that follow shares {name: weight}, spread out (smooth weighted round robin). Deterministic."""
    shares = {k: v for k, v in shares.items() if v and v > 0}
    if not shares:
        return [None] * n
    cur, tot, out = dict.fromkeys(shares, 0.0), sum(shares.values()), []
    for _ in range(n):
        for k in cur:
            cur[k] += shares[k]
        k = max(cur, key=cur.get)
        cur[k] -= tot
        out.append(k)
    return out


def fit_of(e, aspect, out=False):
    """One graphics.entrances[] / exits[] row -> the renderer's fit (motion.ts Fit): kind, GSAP ease, dur (s),
    dir, dist (% of the frame's short side), fade, scale. distance_pct is % of the frame along the move."""
    W, H = SIZES[aspect]
    side = e.get("to" if out else "from")
    f = {"kind": e.get("kind") or "cut", "ease": e.get("ease") or "none", "dur": round(e.get("duration_s") or 0, 3)}
    if f["kind"] in ("slide", "mask") and side:
        f["dir"] = side
    if f["kind"] == "slide":
        f["dist"] = round((e.get("distance_pct") or 0) * (H if side in ("top", "bottom") else W) / min(W, H), 1)
    if e.get("fade"):
        f["fade"] = True
    sc = e.get("scale_to" if out else "scale_from")
    if f["kind"] == "scale" and sc:
        f["scale"] = sc
    return f


# A measured entrance kind -> the card's "entrance" (sfx.py cues and ai_tells read it)
FIT_ENTRANCE = {"cut": "cut", "slide": "slide", "fade": "fade", "scale": "scale", "mask": "slide"}
# graphics.kinds -> the capture format that shows it with a real source. A text card is never built
# (type cards were removed): it becomes a sticker of the real sentence.
KIND_FORMAT = {"real screenshot": "shot", "photo": "shot", "meme": "shot", "UI recording": "browser",
               "text card": "sticker", "chart": "sticker"}
# graphics.secondary_motion -> the ambient move a card makes while up (motion.ts camera). "video": the picture
# itself moves in hers; a still capture stands in with the default push and drift.
AMBIENT = {"still": "still", "push": "push", "drift": "drift", "video": "video"}


def creator_motion(cards, style, aspect):
    """Deals the creator's measured entrances, exits and ambient moves over the box cards, in her shares
    (props.enter / props.exit / props.ambient; motion.ts plays them in place of dropIn / exitUp / the camera)."""
    g = graphics(style, "entrances")
    # logo_cluster keeps its own pop round the head: a measured slide carries its logos across the face
    box = [c for c in cards if c.get("layout") != "scene" and (c.get("anim") or {}).get("type") != "logo_cluster"]
    for key, out in (("entrances", False), ("exits", True)):
        rows = g.get(key) or []
        if not rows:
            continue
        for c, i in zip(box, deal({i: r.get("share_pct") or r.get("n") or 0 for i, r in enumerate(rows)}, len(box))):
            if i is None:
                continue
            f = fit_of(rows[i], aspect, out)
            props(c)["exit" if out else "enter"] = f
            if not out:
                c["entrance"] = FIT_ENTRANCE.get(f["kind"], c.get("entrance"))
    sec = g.get("secondary_motion") or {}
    for c, a in zip(box, deal({AMBIENT[k]: v for k, v in sec.items() if k in AMBIENT}, len(box))):
        if a:
            props(c)["ambient"] = a
    return cards


def props(c):
    """The props the renderer reads for a card: the anim's, or (an image card) the card's own, copied so the
    images.json item they came from is never written into."""
    if c.get("anim"):
        c["anim"] = {**c["anim"], "props": dict(c["anim"].get("props") or {})}
        return c["anim"]["props"]
    c["props"] = dict(c.get("props") or {})
    return c["props"]


def kind_formats(images, style):
    """Captures with no format take one from the creator's graphics.kinds mix, dealt in her shares."""
    mix = {}
    for k, v in (graphics(style, "graphics").get("kinds") or {}).items():
        if k in KIND_FORMAT:
            mix[KIND_FORMAT[k]] = mix.get(KIND_FORMAT[k], 0) + v
    free = [i for i, im in enumerate(images) if not im.get("format") and str(im.get("src", "")).startswith("images/capture-")]
    images = [dict(im) for im in images]
    for i, f in zip(free, deal(mix, len(free))):
        if f:
            images[i]["format"] = f
    return images


def place_pans(cam, duration):
    """camera.pan_per_min -> slow sideways drifts of the footage: each 1.5 s, PAN_PCT of the width, alternating
    out and back so the frame never walks off. [] without a measured camera."""
    n = round(duration / 60 * (cam.get("pan_per_min") or 0))
    out = []
    for i in range(n):
        s = (i + 0.5) * duration / n - PAN_S / 2
        a, b = (0, PAN_PCT) if i % 2 == 0 else (PAN_PCT, 0)
        out.append({"start": round(max(0.0, s), 3), "end": round(min(duration, s + PAN_S), 3), "from": a, "to": b})
    return out


PAN_S, PAN_PCT = 1.5, 2.5    # visual.py counts a pan at 2% of the width a second for 1 s


def safe_box(box, aspect):
    """Move then shrink a card box so none of it sits under the app's UI."""
    l, t, r, b = SAFE[aspect]
    x, y, w, h = box
    if aspect == "9:16":    # vertical cards are centred on the frame, not on the gap between the UI
        l = r = max(l, r)
    # ponytail: fixed height cap, not a head measurement; measure the head if framings vary a lot
    w, h = min(w, 100 - l - r), min(h, 100 - t - b, TOP_CARD_MAX_H[aspect] if y < 50 else 100)
    x = (100 - w) / 2 if aspect == "9:16" else min(max(x, l), 100 - r - w)
    y = min(max(y, t), 100 - b - h)
    return [x, y, w, h]


def logo_items(visuals, edit_dir, cap_y, aspect):
    """logo beats -> small logo cards just above the captions. They run in their own lane,
    so a logo can land while a bigger card is up. capture.mjs fetches the files."""
    out = []
    for v in visuals:
        if v.get("kind") != "logo":
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (v.get("brand") or v["word"]).lower()).strip("-")
        src = next((f"images/logo-{slug}.{e}" for e in ("svg", "png")
                    if edit_dir and (edit_dir / f"images/logo-{slug}.{e}").exists()), None)
        if not src:
            print(f"warning: no logo file for '{slug}', run capture.mjs first; skipped", file=sys.stderr)
            continue
        w = LOGO_BOX_H * (16 / 9 if aspect == "9:16" else 9 / 16)   # a square tile
        item = {k: v[k] for k in ("word", "nth", "entrance") if k in v}
        item.update({"anim": {"type": "logo", "props": {"src": src}}, "hold_s": v.get("hold_s", LOGO_S),
                     "box": v.get("box") or [50 - w / 2, cap_y - LOGO_BOX_H - 5, w, LOGO_BOX_H], "lane": "logo"})
        out.append(item)
    return out


def strip_emoji(node, where, warn):
    """Emoji never reach the screen: removed from every text prop, with a warning."""
    if isinstance(node, list):
        return [strip_emoji(x, where, warn) for x in node]
    if isinstance(node, dict):
        return {k: strip_emoji(v, where, warn) for k, v in node.items()}
    if isinstance(node, str) and EMOJI.search(node):
        warn(f"anti-generic: emoji removed from '{where}': {node!r}")
        return EMOJI.sub("", node).strip()
    return node


def icon_only(props):
    """True when a card's pictures are all stock icons (Lucide) and nothing real: no logo, image or capture."""
    icons, real = [], []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if "icon" in n:
                icons.append(n["icon"])
            if "logo" in n or ("src" in n and not str(n["src"]).startswith("images/icon-")):
                real.append(1)
            for v in n.values():
                walk(v)
    walk(props)
    return bool(icons) and not real


def anti_generic(visuals, profile=None, warn=None):
    """The visuals.md anti-generic rules on visuals.json, before anything is placed. Returns the beats
    that pass. Dropped: captures of stock-photo sites, anim cards whose only pictures are stock icons
    (a beat may set "allow_icons": true when nothing real exists and the icon sits in a type layout).
    Emoji are stripped from every text."""
    warn = warn or (lambda m: print(f"warning: {m}", file=sys.stderr))
    avoid = (profile or {}).get("avoid") or {}
    out = []
    for v in visuals:
        where = v.get("word", "?")
        url = (v.get("url") or "").lower()
        if avoid.get("stock", True) and any(d in url for d in STOCK):
            warn(f"anti-generic: '{where}' captures a stock-photo site ({url}); capture the named thing instead. Skipped")
            continue
        if v.get("kind") == "anim" and avoid.get("icons", True) and not v.get("allow_icons") \
                and icon_only(v.get("props") or {}):
            warn(f"anti-generic: the '{where}' {v.get('type')} card is only stock icons; use a logo, a capture, the "
                 f"user's own image or a type-led template (or set \"allow_icons\": true). Skipped")
            continue
        out.append(strip_emoji(v, where, warn) if avoid.get("emoji", True) else v)
    return out


def type_only(v):
    """A removed words-on-a-ground card."""
    return v.get("type") in TYPE_ONLY


def anim_items(visuals, edit_dir=None, style=None):
    """The built-animation beats of visuals.json as card items. Capture beats reach the
    plan through images.json (capture.mjs writes them there). "post" beats become social_post
    cards from the real post capture.mjs fetched (images/post-<id>.json)."""
    out = []
    for v in visuals:
        if v.get("kind") == "post":
            pid = v.get("id") or (re.search(r"status(?:es)?/(\d+)", v.get("url", "")) or [None, None])[1]
            f = edit_dir and pid and Path(edit_dir) / f"images/post-{pid}.json"
            if not f or not f.exists():
                print(f"warning: no images/post-{pid}.json for '{v.get('word')}', run capture.mjs first; skipped", file=sys.stderr)
                continue
            props = {k: x for k, x in json.loads(f.read_text()).items() if k != "url"}
            props.update(v.get("props") or {})
            v = {**v, "kind": "anim", "type": "social_post", "props": props}
        if v.get("kind") != "anim":
            continue
        if type_only(v):
            print(f"warning: '{v.get('word')}' {v['type']} is a type card (words on a ground); type cards were removed. "
                  f"Use {INSTEAD.get(v['type'], 'a capture of the real source with the words marked (sticker, shot or browser)')}. Skipped",
                  file=sys.stderr)
            continue
        if v.get("type") not in ANIMS:
            print(f"warning: unknown anim type {v.get('type')!r} on '{v.get('word')}', skipped", file=sys.stderr)
            continue
        item = {k: v[k] for k in ("word", "nth", "box", "entrance", "hold_s", "layout", "transition_in", "transition_out", "focus") if k in v}
        if "box" in v:
            item["_own_box"] = True
        item["anim"] = {"type": v["type"], "props": v.get("props") or {}}
        out.append(item)
    return out


def resolve_src(node, edit_dir):
    """{"icon": name} / {"logo": brand} -> the file capture.mjs fetched, or None."""
    slug = lambda x: re.sub(r"[^a-z0-9]+", "-", x.lower()).strip("-")
    if "icon" in node:
        return f"images/icon-{slug(node['icon'])}.svg"
    s = slug(node["logo"])
    src = next((f"images/logo-{s}.{e}" for e in ("svg", "png")
                if edit_dir and (Path(edit_dir) / f"images/logo-{s}.{e}").exists()), None)
    if not src:
        print(f"warning: no logo file for '{s}', run capture.mjs first", file=sys.stderr)
    return src


def word_at(words, card, node, key):
    """Seconds after the card lands that node[key] is said ("nth" picks a later time), or None."""
    target = clean(node[key]).lower()
    hits = [w for w in words if clean(w["text"]).lower() == target and w["start"] >= card["start"]]
    n = node.get("nth", 1)
    if len(hits) < n:
        print(f"warning: '{node[key]}' is not said during the '{card['trigger_word']}' card", file=sys.stderr)
        return None
    at = round(hits[n - 1]["start"] - card["start"], 3)
    if card["start"] + at > card["end"]:
        print(f"warning: '{node[key]}' lands after the '{card['trigger_word']}' card ends; raise hold_s", file=sys.stderr)
    return at


def scene_parts(cards, words, edit_dir):
    """Fill in every anim card's props, anywhere they nest: "icon" / "logo" -> "src" (the file capture.mjs
    fetched), "word" / "off_word" -> "at" / "off_at", seconds after the card lands. A word is the
    first time it is said once the card is up ("nth" picks a later time). No word: the template staggers.
    A prop that wants a file path ("avatar", "logo_src", "src", "a_src", "b_src") may be given as
    {"logo": ...} and becomes the path. caption_page with no "words" gets the words said while it is up.
    Capture cards: each mark's "at_word" -> "at" (an "at_s" is kept as "at"; neither: 0.8 s)."""
    def walk(node, card):
        if isinstance(node, list):
            for x in node:
                walk(x, card)
            return
        if not isinstance(node, dict):
            return
        if (isinstance(node.get("icon"), str) or isinstance(node.get("logo"), str)) and "src" not in node:
            src = resolve_src(node, edit_dir)
            if src:
                node["src"] = src
        for key, out in (("word", "at"), ("off_word", "off_at")):
            if key in node:
                at = word_at(words, card, node, key)
                if at is not None:
                    node[out] = at
        for k, v in list(node.items()):
            if k in ("avatar", "logo_src", "src", "a_src", "b_src", "logo") and isinstance(v, dict) and ("logo" in v or "icon" in v):
                node[k] = resolve_src(v, edit_dir)
            else:
                walk(v, card)

    for c in cards:
        if c.get("anim"):
            c["anim"] = json.loads(json.dumps(c["anim"]))   # never write back into visuals
            walk(c["anim"]["props"], c)
            if c["anim"]["type"] == "caption_page" and not c["anim"]["props"].get("words"):
                c["anim"]["props"]["words"] = [
                    {"text": w["text"], "start": round(max(0.0, w["start"] - c["start"]), 3),
                     "end": round(min(c["end"], w["end"]) - c["start"], 3)}
                    for w in words if c["start"] <= w["start"] < c["end"]]
        wt = c.pop("_word_t", None)
        if wt is not None and c.get("layout") != "scene":
            # seconds from the card's start to its own word: motion.ts landAt lands the entrance there
            props(c)["word_at"] = round(max(0.0, wt - c["start"]), 3)
        for mk in c.get("marks") or []:
            if "at_word" in mk:
                at = word_at(words, c, {"word": mk["at_word"], "nth": mk.get("nth", 1)}, "word")
                mk["at"] = at if at is not None else 0.8
            elif "at_s" in mk:
                mk["at"] = mk["at_s"]
            mk.setdefault("at", 0.8)
            for k in ("at_word", "at_s", "nth"):   # "find" stays: check.py plan reads it (a capture on the hook)
                mk.pop(k, None)
    return cards


def place_cards(images, words, duration, style, aspect):
    """images: image items and anim items (anim_items). Each group without "nth" takes the
    next time its word is said after that group's previous card."""
    hold, ent, box = card_defaults(style)
    out = []
    logos = [i for i in images if i.get("lane") == "logo"]
    images = [i for i in images if i.get("lane") != "logo"]
    for lane in ([i for i in images if "anim" not in i] + [i for i in images if "anim" in i], logos):
        cards = []
        for group in ([i for i in lane if "anim" not in i], [i for i in lane if "anim" in i]):
            cards += _place(group, words, duration, hold, ent, box, aspect)
        cards.sort(key=lambda c: c["start"])
        for a, b in zip(cards, cards[1:]):     # never two cards at once in a lane
            a["end"] = min(a["end"], b["start"])
        for c in cards:
            if c["end"] - c["start"] < MIN_CARD_S:
                print(f"warning: '{c['trigger_word']}' card cut to {c['end'] - c['start']:.2f} s by the next one, dropped",
                      file=sys.stderr)
        out += [c for c in cards if c["end"] - c["start"] >= MIN_CARD_S]
    return sorted(out, key=lambda c: c["start"])


def _place(images, words, duration, hold, ent, box, aspect):
    cards, after = [], -1.0
    for im in images:
        target = clean(im["word"]).lower()
        hits = [w for w in words if clean(w["text"]).lower() == target]
        if im.get("nth"):
            hits = hits[im["nth"] - 1:im["nth"]]
        else:
            hits = [w for w in hits if w["start"] > after]
        if not hits:
            print(f"warning: '{im['word']}' is never said after the previous card, "
                  f"skipped {im.get('src') or im['anim']['type']}", file=sys.stderr)
            continue
        start = round(max(0.0, hits[0]["start"] - CARD_LEAD_S), 3)
        card = {"src": im["src"]} if "src" in im else {"anim": im["anim"]}
        if im.get("lane"):
            card["lane"] = im["lane"]
        for k in ("highlight", "size", "layout", "transition_in", "transition_out", "focus", "format", "props", "_own_box", "xh", "lines"):
            if im.get(k):
                card[k] = im[k]
        if im.get("marks"):
            card["marks"] = json.loads(json.dumps(im["marks"]))
        kind = im.get("format") or (im.get("anim") or {}).get("type") or ("shot" if "src" in im else None)
        end = min(duration, start + (im.get("hold_s") or hold))
        if im.get("lane") == "logo":    # a logo in passing leaves when its sentence does
            i = words.index(hits[0])
            nxt = next((words[j + 1]["start"] for j in range(i, len(words) - 1) if ends_sentence(words[j]["text"])), None)
            end = min(end, nxt) if nxt is not None else end
        card.update({"start": start, "end": round(end, 3),
                     "_word_t": hits[0]["start"], "trigger_word": im["word"], "entrance": im.get("entrance") or ent or FORMAT_ENTRANCE.get(kind, "pop"),
                     "box": safe_box(im.get("box") or box or DEFAULT_BOX[aspect], aspect)})
        cards.append(card)
        after = start
    return cards


HEAD_GAP = 2           # % kept between a card and the head (a zoom punch grows the head a little)
MIN_CARD_H = 9         # a card squeezed shorter than this above the head is dropped instead


def head_during(heads, step, start, end):
    """Union of the head boxes sampled while a card is up, as (left, top, right, bottom)."""
    bs = [h["box"] for h in heads if h["box"] and start - step <= h["t"] <= end]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs))


def avoid_heads(cards, face, cap_y, aspect):
    """Keep every card off the speaker's head (face.json from face.py). A top card shrinks to
    the band above the head; a logo drops below the chin or moves beside or above the head. A card
    that cannot fit is dropped: covering the face is worse than losing the visual."""
    if not face:
        return cards
    l_safe, t_safe, r_safe, _ = SAFE[aspect]
    if aspect == "9:16":    # vertical cards keep the wider side margin on both sides, as check.py plan does
        l_safe = r_safe = max(l_safe, r_safe)
    out = []
    for c in cards:
        if (c.get("anim") or {}).get("type") == "logo_cluster":   # the whole frame, its logos placed round the head
            out.append(c)
            continue
        hd = head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        x, y, w, h = c["box"]
        if hd is None or not (x < hd[2] and x + w > hd[0] and y < hd[3] and y + h > hd[1]):
            out.append(c)
            continue
        left, top, right, bottom = hd
        new = None
        if (c.get("anim") or {}).get("type") == "logo" and h < 20:
            if bottom + HEAD_GAP + h <= cap_y - 1:
                new = [x, bottom + HEAD_GAP, w, h]
            elif 100 - r_safe - (right + HEAD_GAP) >= w:
                new = [right + HEAD_GAP, (top + bottom - h) / 2, w, h]
            elif left - HEAD_GAP - l_safe >= w:
                new = [left - HEAD_GAP - w, (top + bottom - h) / 2, w, h]
            elif top - HEAD_GAP - h >= t_safe:
                new = [(left + right - w) / 2, top - HEAD_GAP - h, w, h]
        elif top - HEAD_GAP - y >= MIN_CARD_H:
            new = [x, y, w, top - HEAD_GAP - y]
        if new is None:
            print(f"warning: no room off the head for the '{c['trigger_word']}' card, dropped", file=sys.stderr)
            continue
        c["box"] = [round(v, 1) for v in new]
        out.append(c)
    return out


def free_regions(hd, cap_y, aspect):
    """The frame around the head, as boxes clear of the app's UI and the captions: above, left, right."""
    l, t, r, b = SAFE[aspect]
    top = OVERLAY_TOP if aspect == "9:16" else t       # overlays may use the top bar's margin: it holds only small text
    left, htop, right, hbot = hd
    floor = min(cap_y - 5, 100 - b) if aspect == "9:16" else 100 - b
    out = [[4, top, 92, htop - HEAD_GAP - top]]
    if aspect == "9:16":
        out += [[OVERLAY_EDGE, htop, left - HEAD_GAP - OVERLAY_EDGE, floor - htop], [right + HEAD_GAP, htop, 100 - r - (right + HEAD_GAP), floor - htop]]
    else:
        out += [[l, top, left - HEAD_GAP - l, floor - top], [right + HEAD_GAP, top, 100 - r - (right + HEAD_GAP), floor - top]]
    return [[round(v, 1) for v in bx] for bx in out if bx[2] >= 12 and bx[3] >= 9]


def content_aspect(c):
    a = c.get("anim") or {}
    p = {**(a.get("props") or {}), **(c.get("props") or {})}
    size = c.get("size") or p.get("size")
    if c.get("format") == "sticker" and p.get("crop"):
        return p["crop"][2] / p["crop"][3]
    if size:
        return size[0] / size[1] * (1.25 if c.get("format") == "browser" else 1)
    return ASPECT.get(a.get("type"), 1.6)


def sticker_xh(c, aspect):
    """The rendered x-height (px) of a sticker's text, from capture.mjs's "xh" (PNG px) and the fit
    Overlays.tsx Sticker uses: the crop inside 90% x 86% of the box, less a white edge each side."""
    p = c.get("props") or {}
    iw, ih = (p.get("crop") or [0, 0, *c["size"]])[2:]
    W, H = SIZES[aspect]
    w, h = c["box"][2] / 100 * W, c["box"][3] / 100 * H
    e = max(8, min(w, h) / 100 * 1.6)
    return c["xh"] * min((w * 0.9 - 2 * e) / iw, (h * 0.86 - 2 * e) / ih)


XH_PER_LINE = 0.42     # a DOM line box is about 1.2 em tall and a Latin x-height about 0.5 em
# ponytail: a crop cut to the evidence may show the capture up to 2 frame px per PNG px (a 2x capture's body text
# needs about 1.8 to read); soft but legible. Upgrade: re-shoot the crop at a higher deviceScaleFactor instead.
MAX_UP = 2.0


def evidence_lines(c):
    """The text lines (image px) a capture is shown for: those under its marks or highlight, else its largest
    type (the headline). Inside a sticker's crop only."""
    lines = [ln[:4] for ln in c.get("lines") or []]
    if c.get("format") == "sticker":
        x, y, w, h = sticker_crop(c)
        lines = [ln for ln in lines if ln[0] >= x - 1 and ln[1] >= y - 1 and ln[0] + ln[2] <= x + w + 1 and ln[1] + ln[3] <= y + h + 1]
    if not lines:
        return []
    iw, ih = c["size"]
    rects = [r for mk in c.get("marks") or [] for r in (mk.get("rects") or ([mk["rect"]] if mk.get("rect") else []))]
    rects += [[a * iw, b * ih, cw * iw, ch * ih] for a, b, cw, ch in (c.get("highlight") or {}).get("rects") or []]
    hit = [ln for ln in lines if any(r[0] - 4 <= ln[0] + ln[2] / 2 <= r[0] + r[2] + 4 and r[1] - 4 <= ln[1] + ln[3] / 2 <= r[1] + r[3] + 4
                                     for r in rects)]
    top = max(ln[3] for ln in lines)
    return hit or [ln for ln in lines if ln[3] >= 0.85 * top]


def capture_scale(c, aspect):
    """Frame px per image px of a capture card as Overlays.tsx draws it in its box (no push-in counted)."""
    W, H = SIZES[aspect]
    w, h = c["box"][2] / 100 * W, c["box"][3] / 100 * H
    iw, ih = c["size"]
    f = c.get("format") or "shot"
    if f == "sticker":
        e = max(8, min(w, h) / 100 * 1.6)
        cw, ch = sticker_crop(c)[2:]
        return min((w * 0.9 - 2 * e) / cw, (h * 0.86 - 2 * e) / ch)
    if f == "browser":
        bar = max(28, h * 0.09)
        bw, vh = min(w * 0.96, (h * 0.94 - bar) * 1.7), h * 0.94 - bar
        follows = c.get("marks") or c.get("highlight") or ih / iw > vh / bw * 1.6
        return bw / iw if follows else min(bw / iw, vh / ih)
    return min(w * 0.96 / iw, h * 0.92 / ih)


def capture_xh(c, aspect):
    """The rendered x-height (px on a 1080-wide frame) of a capture card's evidence text, from its DOM line
    boxes; None when it has none. A capture.mjs sticker's own measured "xh" wins."""
    if c.get("format") == "sticker" and c.get("xh") and c.get("size"):
        return sticker_xh(c, aspect) * 1080 / min(SIZES[aspect])
    if not c.get("size") or c.get("format") == "plain":
        return None
    ev = evidence_lines(c)
    if not ev:
        return None
    hl = sorted(ln[3] for ln in ev)[len(ev) // 2]
    return XH_PER_LINE * hl * capture_scale(c, aspect) * 1080 / min(SIZES[aspect])


def small_lines(c, aspect):
    """The text lines inside a sticker's crop (one cut from a shot: capture.mjs's own stickers carry "xh") that
    render under READ_XH x-height: a kicker or footnote too small to read beside the evidence."""
    if c.get("format") != "sticker" or c.get("xh") or not c.get("lines") or not c.get("size") or not c.get("box"):
        return []
    x, y, w, h = sticker_crop(c)
    k = capture_scale(c, aspect) * 1080 / min(SIZES[aspect])
    return [ln[:4] for ln in c["lines"] if ln[0] >= x - 1 and ln[1] >= y - 1 and ln[0] + ln[2] <= x + w + 1
            and ln[1] + ln[3] <= y + h + 1 and XH_PER_LINE * ln[3] * k < READ_XH]


def readable_captures(cards, aspect):
    """On vertical a capture whose evidence would render under READ_XH becomes a sticker cropped to that
    evidence: the crop takes the band's shape around the evidence's first lines (as many as still read) at the
    largest size that holds them (at most MAX_UP frame px per picture px), every line whole. One that still reads small is left for check.py to FAIL."""
    if aspect != "9:16":
        return cards
    W, H = SIZES[aspect]
    for c in cards:
        if c.get("layout") == "scene" or not c.get("src") or c.get("format") in ("sticker", "plain") or not c.get("lines"):
            continue
        xh = capture_xh(c, aspect)
        if xh is None or xh >= READ_XH:
            continue
        w, h = c["box"][2] / 100 * W, c["box"][3] / 100 * H
        e = max(8, min(w, h) / 100 * 1.6)
        aw, ah = w * 0.9 - 2 * e, h * 0.86 - 2 * e
        unit = 1080 / min(W, H)

        def fit(group):
            gx0, gy0 = min(ln[0] for ln in group), min(ln[1] for ln in group)
            gx1, gy1 = max(ln[0] + ln[2] for ln in group), max(ln[1] + ln[3] for ln in group)
            pad = 0.25 * min(ln[3] for ln in group)
            f = min(MAX_UP, aw / (gx1 - gx0 + 2 * pad), ah / (gy1 - gy0 + 2 * pad))
            return f, (gx0, gy0, gx1, gy1), XH_PER_LINE * sorted(ln[3] for ln in group)[len(group) // 2] * f * unit

        # the evidence from its first line on, as many lines as still read at READ_XH
        ev = sorted(evidence_lines(c), key=lambda ln: (ln[1], ln[0]))
        group = ev[:1]
        for ln in ev[1:]:
            if fit(group + [ln])[2] < READ_XH:
                break
            group.append(ln)
        f, (x0, y0, x1, y1), _ = fit(group)
        iw, ih = c["size"]
        cw, ch = min(iw, aw / f), min(ih, ah / f)
        cx = min(max((x0 + x1) / 2, cw / 2), iw - cw / 2)
        cy = min(max((y0 + y1) / 2, ch / 2), ih - ch / 2)
        new = {**c, "format": "sticker", "props": {k: v for k, v in (c.get("props") or {}).items() if k != "url"}}
        new["props"]["crop"] = whole_lines([cx - cw / 2, cy - ch / 2, cw, ch], c["lines"], c["size"])
        # a kicker or footnote above or below the evidence that would read under READ_XH is left out of the
        # crop (the card hugs it), never shown too small to read
        ours = [ln[:4] for ln in group]
        for ln in small_lines(new, aspect):
            x, y, w, h = new["props"]["crop"]
            if ln in ours:
                continue
            top, bot = (max(y, ln[1] + ln[3]), y + h) if ln[1] + ln[3] <= y0 else (y, min(y + h, ln[1]))
            new["props"]["crop"] = [x, round(top), w, round(bot - top)]
        got = capture_xh(new, aspect)
        if got and got > xh:
            print(f"'{c['trigger_word']}' {c['src']}: {c.get('format') or 'shot'} text would read at {xh:.0f} px x-height; "
                  f"cut to the evidence as a sticker, {got:.0f} px", file=sys.stderr)
            c.clear()
            c.update(new)
    return cards


def heat(gl, bx):
    """How much the creator's graphics sat in box bx (% of the frame), 0-1: the mean of her layout grid over
    it (graphics.layout.grid, seconds of cover per cell, 0-100), else her zone share (zones_pct)."""
    grid = gl.get("grid")
    if grid:
        gh, gw = len(grid), len(grid[0])
        r0, c0 = int(bx[1] / 100 * gh), int(bx[0] / 100 * gw)
        r1, c1 = max(r0 + 1, math.ceil((bx[1] + bx[3]) / 100 * gh)), max(c0 + 1, math.ceil((bx[0] + bx[2]) / 100 * gw))
        cells = [grid[r][c] for r in range(r0, min(r1, gh)) for c in range(c0, min(c1, gw))]
        return sum(cells) / len(cells) / 100 if cells else 0
    cy = bx[1] + bx[3] / 2
    z = "full" if bx[2] * bx[3] >= 6000 else "top" if cy < 38 else "bottom" if cy > 62 else "middle"
    return (gl.get("zones_pct") or {}).get(z, 0) / 100


HEAT_FLOOR = 0.25      # a region she never used still scores this much of its area: her heat leans, never forbids


def place_overlays(cards, face, cap_y, aspect, prefer=None):
    """Overlay cards (captures, overlay formats, social posts) go to the free region around the head that
    their picture fills best. logo_cluster takes the whole frame and is told where the head is. A card with
    its own box, and the small fixed ones (logo tile, lower third, arrow, caption page), keep their box.
    prefer: the creator's graphics.layout; each region's area is weighted by where her graphics sat (heat).
    The regions are the same free ones either way: never the head, never under the app's UI."""
    W, H = SIZES[aspect]
    out = []
    for c in cards:
        t = (c.get("anim") or {}).get("type")
        hd = face and head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        if t == "logo_cluster":
            c["box"] = [0, 0, 100, 100]
            if hd:
                c["anim"]["props"]["head"] = [round(hd[0], 1), round(hd[1], 1), round(hd[2] - hd[0], 1), round(hd[3] - hd[1], 1)]
            if aspect == "9:16":    # readable logos spread over a band centred on the frame, not round the head
                c["anim"]["props"].setdefault("band", list(LOGO_BAND))
                c["anim"]["props"].setdefault("size", LOGO_SIZE)
            out.append(c)
            continue
        if c.get("lane") == "logo" or t in FIXED_BOX or c.get("_own_box") or not hd:
            if not hd and aspect == "9:16" and c.get("src") and not c.get("_own_box") and c.get("lane") != "logo":
                c["box"] = [4, OVERLAY_TOP, 92, c["box"][3]]   # no head found: a capture takes the band above where it would be
            out.append(c)
            continue
        ar = content_aspect(c)

        def area(bx):
            bw, bh = bx[2] / 100 * W, bx[3] / 100 * H
            a = min(bw, bh * ar) * min(bh, bw / ar)
            return a * (HEAT_FLOOR + heat(prefer, bx)) if prefer else a
        regions = free_regions(hd, cap_y, aspect)
        if not regions:
            print(f"warning: no room around the head for the '{c['trigger_word']}' card, dropped", file=sys.stderr)
            continue
        c["box"] = max(regions, key=area)
        out.append(c)
    return out


# Cards behind the speaker (references/motion.md "Behind the speaker"): these formats sit above the
# footage and under the speaker's cutout (matte.py), so a card may tuck behind the hair and grow.
BEHIND = ("shot", "sticker", "logo_cluster", "social_post")
BEHIND_TUCK = 0.4      # a behind card reaches at most this far down the head (share of the head's height)
FILL = 0.92            # an overlay's picture fills about this much of its box (Overlays.tsx fitBox)


def kind_of(c):
    return c.get("format") or (c.get("anim") or {}).get("type") or ("shot" if c.get("src") else None)


def content_rect(c, box, aspect):
    """Where the picture lands in the box, % of the frame: fitted at its aspect, centred."""
    W, H = SIZES[aspect]
    x, y, w, h = box
    bw, bh, ar = w / 100 * W * FILL, h / 100 * H * FILL, content_aspect(c)
    cw, ch = (bw, bw / ar) if ar > bw / bh else (bh * ar, bh)
    return [x + (w - cw / W * 100) / 2, y + (h - ch / H * 100) / 2, cw / W * 100, ch / H * 100]


def key_rect(c, content):
    """What must stay in view, % of the frame: the marks (grown by the shot's push-in), else the
    picture less its bottom fifth (a post's stats row, a page's foot)."""
    x, y, w, h = content
    p = {**((c.get("anim") or {}).get("props") or {}), **(c.get("props") or {})}
    marks = c.get("marks") or p.get("marks") or []
    size = c.get("size") or p.get("size")
    if not (marks and size):
        return [x, y, w, h * 0.8]
    ox, oy, iw, ih = p.get("crop") or [0, 0, *size]
    z = (p.get("zoom") or 1.45) if kind_of(c) == "shot" else 1
    rs = [r for mk in marks for r in [mk["rect"]] + (mk.get("rects") or [])]
    l, t = min(r[0] for r in rs), min(r[1] for r in rs)
    r_, b = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
    cx, cy, hw, hh = (l + r_) / 2, (t + b) / 2, (r_ - l) / 2 * z, (b - t) / 2 * z
    fx = lambda v: x + max(0, min(1, (v - ox) / iw)) * w
    fy = lambda v: y + max(0, min(1, (v - oy) / ih)) * h
    return [fx(cx - hw), fy(cy - hh), fx(cx + hw) - fx(cx - hw), fy(cy + hh) - fy(cy - hh)]


def tuck_behind(cards, face, aspect):
    """Behind formats get "layer": "behind". A card above the head grows down behind the hair, as far
    as BEHIND_TUCK of the head, keeping its key region (marks, or the post's text) clear of the head;
    "key" is written for matte.py to check against the real cutout."""
    hit = lambda a, hd: a[0] < hd[2] + HEAD_GAP and a[0] + a[2] > hd[0] - HEAD_GAP and a[1] < hd[3] + HEAD_GAP and a[1] + a[3] > hd[1] - HEAD_GAP
    for c in cards:
        if kind_of(c) not in BEHIND or c.get("layout") == "scene":
            continue
        c["layer"] = "behind"
        hd = face and head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        if kind_of(c) == "logo_cluster" or not hd:
            continue
        x, y, w, h = c["box"]
        if y + h > hd[1]:       # beside the head, not above it: stays as placed
            c["key"] = [round(v, 1) for v in key_rect(c, content_rect(c, c["box"], aspect))]
            continue
        best = c["box"]
        steps = 20
        for i in range(steps, -1, -1):
            box = [x, y, w, hd[1] + BEHIND_TUCK * (hd[3] - hd[1]) * i / steps - y]
            if not hit(key_rect(c, content_rect(c, box, aspect)), hd):
                best = box
                break
        c["box"] = [round(v, 1) for v in best]
        c["key"] = [round(v, 1) for v in key_rect(c, content_rect(c, c["box"], aspect))]
    return cards


SFX_GAP_S = 0.25       # never two cues closer than this
SFX_EVERY_S = 5.0      # at most one cue per this many seconds, on average: most cards land silent (ai-tells.md)
SFX_RANK = ("hit", "whoosh-in", "whoosh-out", "pop", "zoom")   # who keeps its slot when cues crowd


# sound.kinds (sound.py) -> the kit's cues that sound like them
SOUND_CUES = {"whoosh": ("whoosh-in", "whoosh-out"), "pop": ("pop",), "click": ("pop",), "ding": ("pop",),
              "impact": ("hit", "zoom"), "riser": ("hit",), "other": SFX_RANK}


def place_sfx(plan, words, kit, sound=None):
    """Sound cues for a few of the plan's visual events, about one per SFX_EVERY_S: a card that slides
    in gets whoosh-in, one that pops (a logo, a sticker) a pop, a scene's tag the soft hit,
    a card that scales or fades in lands silent; a scene part lands on its word (pop), a zoom starts
    (zoom). No exit whooshes, and never the same cue twice in a row. A cue starts its attack early so
    its hit is heard on the event. kit: sfx.py's kit.json.
    sound: the creator's measured style.json "sound". Its sfx_per_min sets the budget (0 is allowed: she
    uses none), its kinds keep only the cues that sound like hers, on_graphic_pct / on_cut_pct 0 drop the
    card / zoom cues."""
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    ev = []

    def parts(node, key, start):
        if isinstance(node, list):
            for x in node:
                parts(x, key, start)
        elif isinstance(node, dict):
            if "at" in node and key != "label":   # a label swapping its text stays quiet
                ev.append((start + node["at"], "hit" if key == "tag" else "pop"))
            for k, v in node.items():
                parts(v, k, start)

    def mid_sentence(t):
        before = [w for w in words if w["end"] <= t + 0.05]
        return bool(before) and t - before[-1]["end"] < PAUSE_S and not ends_sentence(before[-1]["text"]) \
            and any(0 <= w["start"] - t < PAUSE_S for w in words)

    for c in plan["cards"]:
        kind = (c.get("anim") or {}).get("type")
        lands = c["start"] + CARD_LEAD_S
        logo = kind in ("logo", "logo_sting")
        ent = c.get("entrance", "slide")
        cue = "pop" if logo or ent == "pop" else "whoosh-in" if ent == "slide" else None
        if cue:
            ev.append((lands, cue))
        parts((c.get("anim") or {}).get("props"), None, c["start"])
    ev += [(z["start"], "zoom") for z in plan["zooms"]]

    duration = plan["durationInFrames"] / plan["fps"]
    budget = max(1, int(duration / SFX_EVERY_S))
    sound = sound or {}
    if sound.get("sfx_per_min") is not None:
        budget = round(duration / 60 * sound["sfx_per_min"])
    if sound.get("kinds"):
        ok = {c for k, v in sound["kinds"].items() if v > 0 for c in SOUND_CUES.get(k, ())}
        ev = [e for e in ev if e[1] in ok]
    if sound.get("on_graphic_pct") == 0 and sound.get("on_cut_pct") == 0:
        ev = []   # all of hers sit inside the voice, on nothing the edit draws
    elif sound.get("on_graphic_pct") == 0:
        ev = [e for e in ev if e[1] == "zoom"]
    elif sound.get("on_cut_pct") == 0:
        ev = [e for e in ev if e[1] != "zoom"]
    kept = []
    # ponytail: rank-then-time greedy, so a crowded video loses its LATER low-rank cues first;
    # spread the budget over time if that ever reads lopsided.
    for t, name in sorted(ev, key=lambda e: (SFX_RANK.index(e[1]), e[0])):
        if name in kit["cues"] and len(kept) < budget and 0 <= t < duration \
                and all(abs(t - k) >= SFX_GAP_S for k, _ in kept):
            kept.append((t, name))
    kept = [k for i, k in enumerate(sorted(kept)) if i == 0 or k[1] != sorted(kept)[i - 1][1]]   # never the same cue twice running
    return [{"t": round(max(0.0, t - kit["cues"][n]["attack_s"]), 3), "src": f".sfx/{n}.wav", "event": round(t, 3)}
            for t, n in kept]


def with_sfx(build):
    """Adds plan["sfx"] (place_sfx) to build()'s plan. Off when style.json has "sfx": false or
    there is no edit folder (sfx.py level-matches the kit to the folder's cut.mp4)."""
    sig = inspect.signature(build)

    def wrap(*a, **k):
        plan = build(*a, **k)
        v = sig.bind(*a, **k)
        v.apply_defaults()
        style, edit_dir = v.arguments["style"], v.arguments["edit_dir"]
        if style.get("sfx", True) is False or not edit_dir:
            plan["sfx"] = []
            return plan
        import sfx
        plan["sfx"] = place_sfx(plan, v.arguments["words"], sfx.kit(edit_dir), style.get("sound") if took(style, "sound") else None)
        return plan
    return wrap


# Split layout: the visual owns a top panel, the speaker a window under the seam. In percent of the frame.
SPLIT = {"seam": 50, "ground": "#F4F4F2"}
SPLIT_GAP = 2          # art stops this far above the seam
SPLIT_CAP_BELOW = 4.5  # captions sit this far under the seam, over the top of the speaker's window
HEAD_ROOM = 4          # the top of the head (hair included) sits this far into the window
MIN_HEAD = 22          # a head shorter than this is scaled up to it, so a face is never tiny
MAX_SPEAKER_SCALE = 1.6
PANEL_T = 0.3          # the panel opens this long before a card lands (StyleEdit.tsx PANEL_T)
SPLIT_LOGO_S = 1.5     # a logo alone in the panel stays at least this long


def split_art_box(seam):
    """The part of the top panel clear of the app's UI and the seam: every split card fills it."""
    l, t, r, _ = SAFE["9:16"]
    m = max(l, r)       # equal side margins: the art is centred on the frame
    return [m, t, 100 - 2 * m, seam - SPLIT_GAP - t]


def speaker_frame(face, seam):
    """How the cut sits in the window under the seam: scaled so the head is at least MIN_HEAD tall,
    moved so the hair sits HEAD_ROOM below the window's top and the head is centred left to right.
    x, y: how far the scaled video's top-left is pulled left and up, in % of the frame. origin: the
    head's centre on the video, for zooms."""
    win = 100 - seam
    bs = sorted((h["box"] for h in (face or {}).get("heads", []) if h["box"]), key=lambda b: b[1])
    if not bs:
        return {"scale": 1, "x": 0, "y": round(seam / 2, 1), "origin": [50, 40]}
    q = lambda xs, f: sorted(xs)[min(len(xs) - 1, int(f * len(xs)))]
    top = q([b[1] for b in bs], 0.1)                  # the highest the head goes, near enough
    bottom = q([b[1] + b[3] for b in bs], 0.9)
    cx = q([b[0] + b[2] / 2 for b in bs], 0.5)
    k = min(max(1, MIN_HEAD / max(1, bottom - top)), MAX_SPEAKER_SCALE)
    y = min(max(0, k * top - HEAD_ROOM), k * 100 - win)
    x = min(max(0, k * cx - 50), k * 100 - 100)
    if k * bottom - y > win:
        print("warning: the head is taller than the split window; the chin is cut off", file=sys.stderr)
    return {"scale": round(k, 3), "x": round(x, 1), "y": round(y, 1), "origin": [round(cx, 1), round((top + bottom) / 2, 1)]}


def split_cards(cards, art):
    """Every card fills the top panel's art box. A logo tile gets the panel to itself for a moment,
    unless a bigger card is up then (the panel is already showing the visual): that logo is dropped."""
    main = [c for c in cards if c.get("lane") != "logo"]
    out = []
    for c in cards:
        if c.get("lane") == "logo":
            if any(m["start"] - 2 * PANEL_T < c["end"] and c["start"] < m["end"] + 2 * PANEL_T for m in main):
                continue
            c = {k: v for k, v in c.items() if k != "lane"}
            nxt = min((m["start"] for m in main if m["start"] > c["start"]), default=c["end"] + 9)
            c["end"] = round(max(c["end"], min(c["start"] + SPLIT_LOGO_S, nxt - 2 * PANEL_T)), 3)
        out.append({**c, "box": list(art)})
    return sorted(out, key=lambda c: c["start"])


def mark_emph(chunks):
    """The stressed word of a caption line: in a line of 3+ words, the one held clearly longest
    (people stretch the word they stress). Marked "emph": true for the renderer."""
    for c in chunks:
        ws = c["words"]
        if len(ws) < 3:
            continue
        d = sorted(w["end"] - w["start"] for w in ws)
        top = max(ws, key=lambda w: w["end"] - w["start"])
        if top["end"] - top["start"] > 1.4 * d[len(d) // 2] and len(top["text"]) > 3:
            top["emph"] = True
    return chunks


def pick_motion(style):
    """plan.json "motion": style.json motion (a name, or motion.personality), else from the creator's
    median shot length (references/motion.md "Personalities"), else smooth."""
    m = style.get("motion")
    if isinstance(m, str):
        return m
    if isinstance(m, dict) and m.get("personality"):
        return m["personality"]
    shot = (style.get("pace") or {}).get("median_shot_s")
    return next(name for top, name in PERSONALITY if shot < top) if shot else "smooth"


def frame_of(card, aspect):
    """"scene", "split" or "box" for one card (references/motion.md "Layout per template"). A visuals.json
    beat's "layout" wins, except that an explaining card on vertical is never a box over the face.
    Captures: split on vertical (a screen needs the room), a box on wide. Split is vertical only."""
    # Overlay first: every card floats over the footage beside or above the head. A full-frame scene when a
    # beat asks for one ("layout": "scene", a chapter title) or for a flow on vertical; the split panel when
    # asked, or for an icon_burst on vertical.
    want = card.get("layout")
    got = want if want in LAYOUTS else "box"
    t = (card.get("anim") or {}).get("type")
    if aspect == "9:16" and got == "box" and t in SCENES + SPLIT_FIRST:
        # SKILL.md step 3: on vertical an explaining card is a full-frame scene or sits in the split panel
        got = "split" if t in SPLIT_FIRST else "scene"
    return "box" if got == "split" and aspect != "9:16" else got


def head_centre(face, t):
    hd = face and head_during(face["heads"], face.get("step_s", 0.5), t, t + 0.01)
    return [round((hd[0] + hd[2]) / 2, 1), round((hd[1] + hd[3]) / 2, 1)] if hd else [50, 31]


def as_scene(card, face, style, n):
    """A full-frame cut-away: the scene box, the transitions (style.json "transitions" cycled; an empty
    list, a creator who only cuts, gives hard cuts; no list gives match in / iris out; a beat's own win)
    and the focus they grow from (the head at the card's start)."""
    cyc = scene_cycle(style)
    card.update({"layout": "scene", "box": list(SCENE_BOX), "focus": card.get("focus") or head_centre(face, card["start"])})
    card.setdefault("transition_in", cyc[n % len(cyc)] if cyc else TRANSITIONS[0])
    card.setdefault("transition_out", cyc[n % len(cyc)] if cyc else TRANSITIONS[1])
    return card


def scene_cycle(style):
    """The transitions scene cards cycle through: style.json "transitions", ["cut"] when it is []."""
    return ["cut"] if style.get("transitions") == [] else style.get("transitions") or []


def _tw(text, fs, wt=700):
    """A bold sans line's width in px, about. ponytail: a per-character average, not measureText; the
    FAIL line (INK_MIN_W) sits well clear of the error."""
    return len(text or " ") * fs * (0.58 if wt >= 800 else 0.55)


def _label(lab):
    return lab if isinstance(lab, str) or not lab else max((x.get("text", "") for x in lab), key=len, default="")


def flow_ink(c, W, H):
    """[x0, x1] in % of the frame: where Diagrams.tsx draws a flow's cards (nodes and branches; the task chips
    are swallowed by the time it settles). The same layout as the renderer: shrink to fit, spread the spare
    width into the wires, centre the cards (a portrait box stacks the chips over the source, no side lane)."""
    p = (c.get("anim") or {}).get("props") or {}
    bx, _, bw, bh = SCENE_TYPE_BOX[H > W] if c.get("layout") == "scene" else c["box"]
    w, h = bw / 100 * W, bh / 100 * H
    s = min(W, H) / 100 / 10.8
    lab_min = 40 * s
    chain = (p.get("nodes") or [])[:6]
    if not chain:
        return None
    n = len(chain)
    branches = (p.get("split") or [])[:max(0, min(4, 6 - n))]
    k = len(branches)
    tasks = [x for x in (p.get("tasks") or []) if (x or {}).get("text")][:4]
    pad = min(w, h) * 0.03
    chip_fs = max(lab_min, min(44 * s, h * 0.11))
    lane = max((_tw(x["text"], chip_fs, 800) + chip_fs * (2.3 if x.get("heavy") else 1.6) + chip_fs * 1.3 for x in tasks),
               default=0) + 28 * s if k and tasks and w >= h else 0
    rows = 2 if not k and n >= 4 else 1
    per = math.ceil(n / rows)
    gap = max(16 * s, h * (0.08 if rows > 1 else 0.05))
    f = 1.0
    while f >= 0.45 - 1e-9:
        row_h = (h - 2 * pad - (rows - 1) * gap) / rows
        S = min(row_h * (0.94 if rows > 1 else 1), (h * 0.6 if k else row_h) * f, (340 if w < h else 240) * s * f)
        nfs = max(lab_min, min(46 * s, S * 0.23))
        nw = [max(S * 0.92, _tw(_label(x.get("label")), nfs) + 40 * s) for x in chain]
        rh = min(h * 0.46, 190 * s, (h - 2 * pad - gap * (k - 1)) / k) if k else 0
        logo_b = min(rh * 0.5, 70 * s * max(f, 0.8))
        bw_ = max((logo_b + 22 * s + max(_tw(t, max(lab_min, min(58 * s, rh * 0.8 / (len(names) * 1.08))), 800) for t in names) + 56 * s
                   for names in ([l.get("text", "") for l in x["lines"]] if x.get("lines") else [_label(x.get("label"))]
                                 for x in branches)), default=0)
        wire_min, wire_b = 56 * s * f, 120 * s * f
        row_w = sum(nw[:per]) + max(0, per - 1) * wire_min
        need = lane + row_w + (wire_b + bw_ if k else 0) + 2 * pad
        if need > w and f > 0.5:
            f -= 0.05
            continue
        wires = max(0, per - 1) + (1.6 if k else 0)
        add = min(max(0.0, w - need) / wires, 90 * s) if wires else 0
        core = row_w + max(0, per - 1) * add + (wire_b + add * 1.6 + bw_ if k else 0)
        x0 = max(pad, (w - core) / 2 - lane) + lane
        return [round(bx + x0 / W * 100, 1), round(bx + (x0 + core) / W * 100, 1)]
    return None


def cluster_ink(c):
    """[x0, x1] in % of the frame for a vertical logo_cluster laid out in its band (Overlays.tsx), else None."""
    p = (c.get("anim") or {}).get("props") or {}
    if not p.get("band"):
        return None
    if len(p.get("logos") or []) < 2:
        return [50 - p.get("size", LOGO_SIZE) / 2, 50 + p.get("size", LOGO_SIZE) / 2]
    return list(p["band"])


def explain_ink(c, W, H):
    """Where a flow or logo_cluster card draws, [x0, x1] % of the width; None for any other card."""
    t = (c.get("anim") or {}).get("type")
    return flow_ink(c, W, H) if t == "flow" else cluster_ink(c) or [0, 0] if t == "logo_cluster" else None


def overlay_led(c):
    """A box card drawn by an overlay format (a capture, chat, post, the flow diagram...): lay_out starts it OVERLAY_LEAD_S x k
    before its word so its entrance has landed on the word. quality.py times its landing the same way."""
    return (c.get("layout") != "scene" and c.get("lane") != "logo"
            and bool(c.get("src") or (c.get("anim") or {}).get("type") in OVERLAYS + ("social_post", "flow")))


def lay_out(cards, aspect, face, style, split_ok):
    """Gives every card its layout. A scene starts SCENE_LEAD_S x k earlier, a hard cut in no earlier (never before the card
    before it in its lane ends). Returns (cards, any card in the split panel)."""
    n = 0
    lead = SCENE_LEAD_S * MOTION_K.get(pick_motion(style), 1.0)
    prev_end = {}
    for c in sorted(cards, key=lambda c: c["start"]):
        f = frame_of(c, aspect)
        if f == "split" and not split_ok:
            f = "scene"        # no panel in overlay: a full-frame cut-away instead
        c["_f"] = f
        if f == "scene":
            cyc = scene_cycle(style)
            tin = c.get("transition_in") or (cyc[n % len(cyc)] if cyc else TRANSITIONS[0])
            c["start"] = round(max(0.0, prev_end.get(c.get("lane"), 0.0), c["start"] - (0 if tin == "cut" else lead)), 3)
            as_scene(c, face, style, n)
            n += 1
        else:
            c["layout"] = "box"
            if overlay_led(c):
                c["start"] = round(max(0.0, prev_end.get(c.get("lane"), 0.0), c["start"] - OVERLAY_LEAD_S * MOTION_K.get(pick_motion(style), 1.0)), 3)
        prev_end[c.get("lane")] = c["end"]
    return cards, any(c["_f"] == "split" for c in cards)


def pick_look(style, prof, prof_mod):
    """plan.json "look". No house palette: overlays are neutral chrome (white cards, near-black text, a soft
    shadow) and colour comes from the real content. Order: the user's brand kit > the copied creator's
    measured palette (only its saturated accent, as the highlighter) > neutral. A style.json look that
    names a preset (editorial, poster-*, ...) opts in to that preset whole."""
    if (style.get("look") or {}).get("preset"):
        return prof_mod.resolve_look(style, prof, warn=lambda m: print(f"warning: {m}", file=sys.stderr))
    brand = prof_mod.brand_look((prof or {}).get("brand") or {})
    creator = prof_mod.creator_look(style)
    look = {"preset": "neutral"}
    accent = brand.get("accent") or creator.get("accent")
    if accent:
        look["mark"] = accent
    for k in ("font", "font_display"):
        if brand.get(k) or creator.get(k):
            look[k] = brand.get(k) or creator.get(k)
    if brand.get("ink"):
        look["ink"] = brand["ink"]
    return look


def sticker_crop(c):
    """The part of a sticker's picture the card shows, image px: its "crop", else Overlays.tsx Sticker's trim of
    capture.mjs's padding."""
    p = c.get("props") or {}
    if p.get("crop"):
        return list(p["crop"])
    w0, h0 = c["size"]
    t = round(min(h0 * 0.08, w0 * 0.035))
    return [t, t, w0 - 2 * t, h0 - 2 * t]


def cut_lines(crop, lines):
    """The text lines (image px) a crop [x, y, w, h] crosses: neither wholly inside it nor wholly out."""
    x0, y0, x1, y1 = crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]
    return [ln for ln in lines if ln[0] < x1 and ln[0] + ln[2] > x0 and ln[1] < y1 and ln[1] + ln[3] > y0
            and not (ln[0] >= x0 and ln[1] >= y0 and ln[0] + ln[2] <= x1 and ln[1] + ln[3] <= y1)]


def whole_lines(crop, lines, size, pad=4):
    """The crop grown (or, past the picture's edge, shrunk) until no line of text crosses its edge: every line
    wholly shown or wholly out (capture.mjs snapClip, on the picture)."""
    x0, y0, x1, y1 = crop[0], crop[1], crop[0] + crop[2], crop[1] + crop[3]
    for _ in range(6):
        hit = cut_lines([x0, y0, x1 - x0, y1 - y0], lines)
        if not hit:
            break
        for lx, ly, lw, lh in (ln[:4] for ln in hit):
            if ly < y0:
                y0 = ly - pad if ly - pad >= 0 else ly + lh + pad
            if ly + lh > y1:
                y1 = ly + lh + pad if ly + lh + pad <= size[1] else ly - pad
            if lx < x0:
                x0 = lx - pad if lx - pad >= 0 else lx + lw + pad
            if lx + lw > x1:
                x1 = lx + lw + pad if lx + lw + pad <= size[0] else lx - pad
    x0, y0 = max(0, x0), max(0, y0)
    return [round(x0), round(y0), round(min(size[0], x1) - x0), round(min(size[1], y1) - y0)]


def with_formats(images, visuals):
    """A capture beat's "format" (shot | browser | sticker | plain) and "props" (label, crop, rotate, zoom,
    cursor) reach its card. capture.mjs names a capture images/capture-<i>-<word>.png after the i-th capture
    beat, so the beat is found by that index; a browser gets the beat's url when it has none."""
    beats = [v for v in visuals if v.get("kind") == "capture"]
    out = []
    for im in images:
        m = re.match(r"images/capture-(\d+)-", im.get("src", ""))
        b = beats[int(m.group(1)) - 1] if m and int(m.group(1)) <= len(beats) else {}
        im = dict(im)
        if b.get("format") and "format" not in im:
            im["format"] = b["format"]
        props = {**(b.get("props") or {}), **(im.get("props") or {})}
        if im.get("format") == "browser" and b.get("url"):
            props.setdefault("url", b["url"])
        if props:
            im["props"] = props
        if im.get("format") == "sticker" and im.get("lines") and im.get("size"):
            # the card's crop keeps every line of the sentence whole (a trim into the text cut words off)
            im["props"] = {**props, "crop": whole_lines(sticker_crop(im), im["lines"], im["size"])}
        if b.get("box") or im.get("box"):
            im["_own_box"] = True
        out.append(im)
    return out


@with_sfx
def build(style, words, meta, images=(), aspect="auto", cuts=(), visuals=(), edit_dir=None, layout=None, profile=None,
          behind=None):
    """behind: cards in BEHIND formats sit behind the speaker (default: the profile's "behind" answer)."""
    if behind is None:
        behind = bool((profile or {}).get("behind"))
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    if aspect == "auto":
        aspect = "9:16" if meta["height"] > meta["width"] else "16:9"
    width, height = SIZES[aspect]
    fps = round(meta["fps"]) or 30
    duration = meta["duration"]
    visuals = anti_generic(list(visuals), profile)
    cap = dict(style.get("captions") or {})
    _, top, _, bottom = SAFE[aspect]
    cap["y_pct"] = min(max(cap.get("y_pct") or 70, top + 5), 100 - bottom - 4)   # clear of the app's UI
    chunks = mark_emph(chunk_captions(words, cap.get("words_per_caption") or 3, cap.get("case", "sentence"))) \
        if cap.get("present", True) else []
    fj = edit_dir and Path(edit_dir) / "face.json"
    face = json.loads(fj.read_text()) if fj and fj.exists() else None
    lay = {**SPLIT, **(style.get("layout") or {}), **(layout or {})}
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import profile as prof_mod
    head = {"video": meta["video"], "width": width, "height": height, "fps": fps,
            "durationInFrames": int(duration * fps),
            "look": pick_look(style, profile, prof_mod),
            "motion": pick_motion(style)}
    pace = (style.get("pace") or {}) if took(style, "pace") else {}
    # Explaining cards are scenes or sit in the split panel; the panel opens only when a card needs it,
    # unless the layout was set by hand (overlay: split cards become scenes).
    explicit = (layout or {}).get("mode") or (style.get("layout") or {}).get("mode")
    if lay.get("mode") == "split" and aspect != "9:16" and explicit:
        sys.exit("ERROR: the split layout is vertical only; use --layout overlay for 16:9")
    split_ok = aspect == "9:16" and explicit != "overlay"
    seam = lay["seam"]
    split_y = min(seam + SPLIT_CAP_BELOW, 100 - bottom - 4)
    split_now = split_ok and (explicit == "split")
    images = kind_formats(with_formats(images, visuals), style)
    probe_cards = place_cards(list(images) + anim_items(visuals, edit_dir, style), words, duration, style, aspect)
    _, wants_split = lay_out(probe_cards, aspect, face, style, split_ok)
    split_now = split_now or wants_split
    logo_y = split_y if split_now else cap["y_pct"]
    cards = place_cards(list(images) + anim_items(visuals, edit_dir, style) + logo_items(visuals, edit_dir, logo_y, aspect),
                        words, duration, style, aspect)
    cards, _ = lay_out(cards, aspect, face, style, split_ok)
    gap = card_gap_s(style)
    quiet = [g for g in card_gaps(cards, duration) if g[1] - g[0] > gap]
    zooms = place_zooms(style.get("zoom") or {}, words, duration, list(cuts), pace.get("cut_kinds"), quiet)
    for z in zooms if face else []:
        # grow from the top of the head, centred on it: the face holds its place and the hair never rises
        # into a card placed above the head (a zoom about the face's middle pushed the hair up into it)
        hd = head_during(face["heads"], face.get("step_s", 0.5), z["start"], z["end"])
        if hd:
            z["origin"] = [round((hd[0] + hd[2]) / 2, 1), round(hd[1], 1)]
    for a, b in quiet:
        said = [f"'{n}' at {x['start']:.1f} s" for x in named_beats(edit_dir) if a <= x["start"] < b for n in x["names"]]
        print(f"warning: no card for {b - a:.1f} s ({a:.1f}-{b:.1f} s, the rule is {gap:.0f} s): "
              + (f"{', '.join(said)} is named there: show it (a capture, post or logo in visuals.json)" if said else
                 f"nothing named there, so the speaker carries it with a zoom change every {QUIET_HOLD_S:.0f} s"),
              file=sys.stderr)
    zooms = clear_entrances(zooms, cards)
    scenes = [c for c in cards if c["_f"] == "scene"]
    rest = [c for c in cards if c["_f"] != "scene"]
    if split_now:
        art = split_art_box(seam)
        full_y = cap["y_pct"]   # where captions sit while the speaker has the whole frame
        cap["y_pct"] = split_y
        # a logo is dropped while a scene or a panel card is up (the frame is already showing the visual)
        rest = split_cards(rest + [{**c, "lane": None} for c in scenes], art)
        rest = readable_captures([c for c in rest if c.get("_f") != "scene"], aspect)
        out = {**head, "layout": {"mode": "split", "ground": lay["ground"], "seam": seam, "art": art,
                                  "speaker": speaker_frame(face, seam), "caption_full_y": full_y}}
    else:
        rest = [c for c in rest if c.get("lane") != "logo"
                or not any(sc["start"] - 0.5 < c["end"] and c["start"] < sc["end"] + 0.5 for sc in scenes)]
        # the head as it is drawn: grown by the zooms (and moved by the pans), as check.py plan measures it
        from check import on_screen
        moved = {"zooms": zooms, "pans": place_pans((style.get("camera") or {}) if took(style, "pace") else {}, duration)}
        seen = face and {**face, "heads": [{**h, "box": on_screen(h["box"], h["t"], moved) if h.get("box") else None}
                                           for h in face["heads"]]}
        rest = place_overlays(rest, seen, cap["y_pct"], aspect, graphics(style, "layout").get("layout"))
        rest = avoid_heads(rest, seen, cap["y_pct"], aspect)
        rest = readable_captures(rest, aspect)
        if behind:
            rest = tuck_behind(rest, face, aspect)
        out = dict(head)
    cards = creator_motion(sorted(rest + scenes, key=lambda c: c["start"]), style, aspect)
    for c in cards:
        px = c.get("layout") != "scene" and c.get("size") and capture_xh(c, aspect)
        if px and px < READ_XH and (aspect == "9:16" or c.get("format") == "sticker"):
            print(f"warning: '{c['trigger_word']}' capture text renders at {px:.0f} px x-height (under {READ_XH}: "
                  "too small on a phone; check.py plan FAILs it on vertical). Cut it to a shorter sentence, a smaller \"fit\", "
                  "or a \"crop\" round the evidence in visuals.json", file=sys.stderr)
        c.pop("_f", None)
        c.pop("_own_box", None)
    for c in cards:   # logos sit round the head as drawn: grown by a zoom up while they are
        hd = ((c.get("anim") or {}).get("props") or {}).get("head") if (c.get("anim") or {}).get("type") == "logo_cluster" else None
        z = hd and next((z for z in zooms if z["start"] < c["end"] and c["start"] < z["end"]), None)
        if z:
            ox, oy = z.get("origin") or [50, 30]
            k = z["scale"]
            c["anim"]["props"]["head"] = [round(ox + (hd[0] - ox) * k, 1), round(oy + (hd[1] - oy) * k, 1), round(hd[2] * k, 1), round(hd[3] * k, 1)]
    extra = {}
    pans = place_pans((style.get("camera") or {}) if took(style, "pace") else {}, duration)
    if pans and not split_now:
        extra["pans"] = pans
    hook = ((style.get("hook") or {}).get("winner") or {}) if took(style, "graphics") else {}
    if hook.get("first_graphic_s") is not None:
        # a soft rule, checked by check.py plan: the creator's winners show a graphic by then
        extra["targets"] = {"first_graphic_s": hook["first_graphic_s"],
                            "control_first_graphic_s": ((style.get("hook") or {}).get("control") or {}).get("first_graphic_s")}
    return {**out, "captions": {"style": cap, "chunks": chunks}, "zooms": zooms, "card_gap_s": gap,
            "cards": scene_parts(cards, words, edit_dir), **extra}


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", str(video)], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"ERROR: ffprobe could not read {video}")
    d = json.loads(out.stdout)
    s = d["streams"][0]
    w, h = s["width"], s["height"]
    if any(abs(sd.get("rotation", 0)) == 90 for sd in s.get("side_data_list", [])):
        w, h = h, w
    num, den = s["r_frame_rate"].split("/")
    return {"video": Path(video).name, "width": w, "height": h,
            "fps": int(num) / int(den or 1), "duration": float(d["format"]["duration"])}


# --- caption contrast: the footage behind each caption page, measured on the cut --------------------------
CONTRAST_MIN = 3.0     # WCAG 1.4.3 for large text; quality.py fails a caption under it (its CONTRAST_FAIL)
# What plan.py aims at: the render check's 4.5:1 WARN line (quality.py CONTRAST_WARN) plus 0.2. Plan estimates the
# footage in the caption's box at a quarter size; the render check reads the ring round the real glyphs at full
# size, which came out 0.1-0.2 lower on the sample. Aiming at the FAIL line (3.3) left pages the render WARNed
# that a new plan never touched (the sample's 4.36:1 at 20.77 s).
CONTRAST_TARGET = 4.7
# How far each step pulls the footage round the glyphs toward treat_color (alpha-composite in sRGB), as
# quality.py's contrast check sees it: fitted to renders of white captions on a bright (#E6E1D8) and a
# grey (#9A9A9A) desk, which agree to 0.04, rounded down. The renderer's default soft shadow, the
# treatment's denser shadow, that plus a 0.1 em stroke, and all of it on a 0.45 backing (Captions.tsx).
PULL = {"plain": 0.07, "shadow": 0.12, "stroke": 0.45, "backing": 0.7}
TREATS = ("shadow", "stroke", "backing")
LUM = [((v / 255) / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4) for v in range(256)]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))


def lum(rgb):
    return 0.2126 * LUM[rgb[0]] + 0.7152 * LUM[rgb[1]] + 0.0722 * LUM[rgb[2]]


def contrast(a, b):
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def treat_for(pixels, fill, pull, tc):
    """The footage pixels round a caption pulled toward tc by `pull` -> contrast with the fill at the worst
    spot: the 90th percentile toward the fill's own luminance (quality.py worst_contrast)."""
    lf = lum(fill)
    ls = sorted(lum([round(v + (t - v) * pull) for v, t in zip(px, tc)]) for px in pixels)
    worst = ls[int(0.9 * (len(ls) - 1))] if lf > 0.18 else ls[int(0.1 * (len(ls) - 1))]
    return contrast(lf, worst)


def pick_treat(pixels, style):
    """(treat or None, treat colour, contrast it reaches) for one caption page over these footage pixels.
    The creator's look first; then the smallest step that reaches CONTRAST_TARGET."""
    fill = hex_rgb(style.get("color") or "#FFFFFF")
    light = lum(fill) > 0.18
    # the treatment colour: the darkest (or lightest, for dark text) of the creator's palette that
    # stands 4.5:1 off the fill, else near-black (near-white)
    pal = [hex_rgb(style[k]) for k in ("stroke_color", "box_color", "highlight_color", "emphasis_color")
           if re.fullmatch(r"#?[0-9a-fA-F]{6}", str(style.get(k) or ""))]
    pal = [c for c in pal if contrast(lum(c), lum(fill)) >= 4.5]
    tc = (min if light else max)(pal, key=lum, default=(17, 17, 17) if light else (245, 245, 245))
    hexc = "#%02X%02X%02X" % tc
    plain = 0.0 if style.get("shadow") is False else PULL["plain"]
    if light:     # the renderer's default shadow is black
        got = treat_for(pixels, fill, plain, (0, 0, 0))
    else:
        got = treat_for(pixels, fill, 0.0, tc)
    if got >= CONTRAST_TARGET:
        return None, hexc, got
    for t in TREATS:
        got = treat_for(pixels, fill, PULL[t], tc)
        if got >= CONTRAST_TARGET:
            break
    return t, hexc, got


def caption_backdrops(plan, edit_dir, meta):
    """{chunk index: [RGB pixels]}: the footage behind each caption page as the render draws it (zoom and
    pan on the cut, check.py footage_affine), at a quarter of the output size, 4 samples a second.
    ponytail: split layout is measured as if the panel were closed (full-frame footage under the
    caption's y); check.py render measures the real frames either way."""
    from check import footage_affine
    from edit import proxy_filter
    W, H = plan["width"] // 4, plan["height"] // 4
    cs, chunks = plan["captions"]["style"], plan["captions"]["chunks"]
    y = (plan.get("layout") or {}).get("caption_full_y") or cs.get("y_pct", 70)
    font = (cs.get("size_pct") or 6) / 100 * max(W, H)
    box_w = (cs.get("width_pct") or 86) / 100 * W
    scenes = [c for c in plan["cards"] if c.get("layout") == "scene"]
    want = {}
    for i, c in enumerate(chunks):
        if any(sc["start"] < c["end"] and c["start"] < sc["end"] for sc in scenes):
            continue    # a scene's ground is behind it, drawn in the scene's ink
        for t in (c["start"] + 0.05, (c["start"] + c["end"]) / 2, c["end"] - 0.05):
            want.setdefault(max(0, round(t * 4)), []).append(i)
    out = {}
    if not want:
        return out
    vf = proxy_filter(meta["width"], meta["height"], plan["width"], plan["height"]) + f",fps=4,scale={W}:{H}"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(Path(edit_dir) / plan["video"]), "-vf", vf,
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    n = 0
    while True:
        buf = p.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        for i in want.get(n, ()):
            c = chunks[i]
            half = min(box_w / 2, 0.28 * font * len(c["text"]) + font / 2)
            rows = 1.3 if 0.55 * font * len(c["text"]) > box_w else 0.75     # two lines when it wraps
            (s, _, tx), (_, _, ty) = footage_affine(n / 4, plan, W, H)
            px = out.setdefault(i, [])
            for yy in range(max(0, int(y / 100 * H - rows * font)), min(H, int(y / 100 * H + rows * font) + 1), 2):
                for xx in range(max(0, int(W / 2 - half)), min(W, int(W / 2 + half) + 1), 2):
                    sx, sy = int((xx - tx) / s), int((yy - ty) / s)
                    if 0 <= sx < W and 0 <= sy < H:
                        k = 3 * (sy * W + sx)
                        px.append(tuple(buf[k:k + 3]))
        n += 1
    p.stdout.close()
    p.wait()
    return out


def treat_captions(plan, edit_dir, meta, floors=None):
    """Every caption page that would read under CONTRAST_TARGET on the footage behind it gets the smallest
    treatment that fixes it, in "treat" (Captions.tsx). The creator's own stroke or box already is one.
    floors: {page start "%.2f": treat} from contrast_floors, the least a page gets.
    Returns [(chunk index, treat, contrast or None)] for the pages it changed."""
    cs, chunks = plan["captions"]["style"], plan["captions"]["chunks"]
    floors = floors or {}
    done = {}
    if chunks and not (cs.get("stroke") or cs.get("box")):
        for i, px in caption_backdrops(plan, edit_dir, meta).items():
            if not px:
                continue
            t, colour, got = pick_treat(px, cs)
            if t:
                chunks[i].update(treat=t, treat_color=colour)
                done[i] = (i, t, round(got, 2))
    for i, c in enumerate(chunks):
        least = floors.get(f"{c['start']:.2f}")
        if least and STEPS.index(least) > STEPS.index(c.get("treat")):
            c.update(treat=least, treat_color=c.get("treat_color") or pick_treat([(128, 128, 128)], cs)[1])
            done[i] = (i, least, None)
    return sorted(done.values())


STEPS = (None,) + TREATS


def contrast_floors(edit_dir, out):
    """{page start: treat}: the caption pages the last render check (check<tag>.json, caption_contrast.low_at)
    read under CONTRAST_TARGET get one treatment past the one that render drew (the plan at `out`). Kept in
    contrast.json, so every later plan keeps them; each check is read once. This is what "plan again" does."""
    f, ck = edit_dir / "contrast.json", edit_dir / f"check{out.stem[len('plan'):]}.json"
    doc = json.loads(f.read_text()) if f.exists() else {"pages": {}, "read": []}
    low = ((json.loads(ck.read_text()).get("render") or {}).get("caption_contrast") or {}).get("low_at") \
        if ck.exists() else None
    stamp = f"{ck.name}@{ck.stat().st_mtime:.0f}" if ck.exists() else None
    if low and out.exists() and stamp not in doc["read"]:
        for c in json.loads(out.read_text())["captions"]["chunks"]:
            if any(c["start"] - 0.05 <= t <= c["end"] + 0.05 for t in low):
                key, nxt = f"{c['start']:.2f}", STEPS[min(len(STEPS) - 1, STEPS.index(c.get("treat")) + 1)]
                if STEPS.index(nxt) > STEPS.index(doc["pages"].get(key)):
                    doc["pages"][key] = nxt
        doc["read"].append(stamp)
        f.write_text(json.dumps(doc, indent=1))
    return doc["pages"]


def cut_points(edit_dir):
    """Where the jump cuts fall on cut.mp4, from the cut skill's decisions.json."""
    p = edit_dir / "decisions.json"
    if not p.exists():
        return []
    t, out = 0.0, []
    for span in json.loads(p.read_text())[:-1]:
        t += span["end"] - span["start"]
        out.append(round(t, 3))
    return out


def demo():
    hy = [{"text": t, "start": i * 0.3, "end": i * 0.3 + 0.25} for i, t in enumerate(["one", "-for", "-one", "deal"])]
    got = [c["text"] for c in chunk_captions(hy, 3, "sentence")]
    assert got == ["one-for-one deal"], got
    face = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 30, 40, 30]}, {"t": 0.5, "box": [30, 31, 40, 30]}]}
    top = {"start": 0.0, "end": 1.0, "box": [10, 15, 74, 22], "trigger_word": "a"}
    logo = {"start": 0.0, "end": 1.0, "box": [42, 50, 16, 9], "trigger_word": "b", "anim": {"type": "logo"}}
    tiny = {"start": 0.0, "end": 1.0, "box": [10, 25, 74, 22], "trigger_word": "c"}
    got = avoid_heads([top, logo, tiny], face, 68, "9:16")
    assert got[0]["box"] == [10, 15, 74, 13], got[0]["box"]           # shrunk to above the head
    lx, ly, lw, lh = got[1]["box"]
    # logo off the head (no room beside it inside the 14% side margins check.py plan holds: above it); tiny dropped
    assert (lx + lw <= 30 or lx >= 70 or ly + lh <= 30) and 14 <= lx and lx + lw <= 86 and len(got) == 2, got
    # placed off the head as drawn: a 1.2 zoom while the card is up grows the head past where face.json has it
    from check import check_plan, on_screen
    zs = [{"start": 0.0, "end": 2.0, "scale": 1.2, "kind": "punch", "ease_s": 0.0}]
    right = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [36, 30, 30, 30]}]}      # room only on its right
    seen = {**right, "heads": [{**h, "box": on_screen(h["box"], h["t"], {"zooms": zs})} for h in right["heads"]]}
    for f, fails in ((right, True), (seen, False)):
        lg = avoid_heads([{**logo, "box": [42, 50, 16, 9]}], f, 68, "9:16")
        pl = {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 60, "zooms": zs, "cards": lg,
              "captions": {"style": {"y_pct": 68}, "chunks": []}}
        assert any("covers the head" in x["what"] for x in check_plan(pl, right)) == fails, (f, lg)
    assert safe_box([6, 3, 88, 27], "9:16") == [14.0, 14, 72, 22], safe_box([6, 3, 88, 27], "9:16")
    assert safe_box([50, 90, 20, 10], "9:16")[1] == 68
    words = []
    t = 0.0
    for i, text in enumerate("so this is how I edit. every video gets zooms and captions now. try notion today."
                             .split()):
        words.append({"text": text, "start": round(t, 2), "end": round(t + 0.3, 2), "type": "word"})
        t += 0.35 + (0.6 if text.endswith(".") else 0)
    style = {"zoom": {"per_min": 60, "kind": "punch", "scale": 1.2, "on": "sentence_start"},
             "captions": {"words_per_caption": 3, "case": "upper"},
             "cats": {"logo": {"hold_s": 2.0, "entrance": [["slide", 0.7]], "box": None}}}
    meta = {"video": "cut.mp4", "width": 3840, "height": 2160, "fps": 29.97, "duration": t}
    imgs = [{"src": "images/n.png", "word": "Notion"}]
    p = build(style, words, meta, imgs)
    assert (p["width"], p["height"], p["fps"]) == (1920, 1080, 30), p
    chunks = p["captions"]["chunks"]
    assert all(len(c["words"]) <= 3 for c in chunks)
    assert chunks[0]["text"] == "SO THIS IS" and chunks[1]["text"] == "HOW I EDIT", chunks[:2]
    assert all(a["end"] <= b["start"] for a, b in zip(chunks, chunks[1:]))
    z = p["zooms"]
    assert z and all(x["ease_s"] == 0 and x["scale"] == 1.2 for x in z)
    assert all(a["end"] <= b["start"] for a, b in zip(z, z[1:])), "zooms overlap"
    assert z[0]["end"] < z[1]["start"], "zoom-out gap missing: the frame would creep"
    c = p["cards"][0]
    notion = next(w for w in words if w["text"] == "notion")
    assert abs(c["start"] - (notion["start"] - 0.1 - OVERLAY_LEAD_S)) < 1e-6 and c["entrance"] == "slide", c   # leads by its entrance
    assert c["box"] == DEFAULT_BOX["16:9"]
    v = build(style, words, meta, aspect="9:16")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert build(style, words, meta, imgs) == p, "not deterministic"
    push = place_zooms({"per_min": 30, "kind": "push", "duration_s": 0.5, "on": "emphasis"},
                       [w for w in words], t, [])
    assert push and push[0]["ease_s"] == 0.5
    vis = [{"word": "zooms", "kind": "anim", "type": "arrow_callout", "props": {"text": "zooms"}},
           {"word": "today", "kind": "anim", "type": "nope"},
           {"word": "edit", "kind": "capture", "url": "https://example.com"}]
    a = build(style, words, meta, imgs, visuals=vis)["cards"]
    assert [c.get("src") or c["anim"]["type"] for c in a] == ["arrow_callout", "images/n.png"], a
    zooms_w = next(w for w in words if w["text"] == "zooms")
    assert abs(a[0]["start"] - (zooms_w["start"] - 0.1)) < 1e-6 and "src" not in a[0] and a[0]["layout"] == "box"   # overlay first
    assert a[0]["anim"] == {"type": "arrow_callout", "props": {"text": "zooms", "word_at": 0.1}}   # its word, from its start
    assert a[0]["end"] <= a[1]["start"], "two cards at once"
    sc = [{"word": "every", "kind": "anim", "type": "flow", "hold_s": 3, "allow_icons": True,
           "props": {"nodes": [{"icon": "mail", "word": "video"}, {"label": "x", "word": "zooms", "off_word": "captions"}]}}]
    f = next(c for c in build(style, words, meta, visuals=sc)["cards"] if c["anim"]["type"] == "flow")
    every = next(w for w in words if w["text"] == "every")
    n0, n1 = f["anim"]["props"]["nodes"]
    assert n0["src"] == "images/icon-mail.svg" and abs(n0["at"] - (every["start"] + 0.35 - f["start"])) < 1e-6, f
    assert n1["off_at"] > n1["at"] > n0["at"] and "at" not in sc[0]["props"]["nodes"][0], f
    sp_face = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 31, 30, 29]}, {"t": 0.5, "box": None}]}
    fr = speaker_frame(sp_face, 50)
    assert fr["scale"] == 1 and fr["y"] == 27 and 31 - fr["y"] == HEAD_ROOM, fr      # hair HEAD_ROOM into the window
    assert abs(speaker_frame({"heads": [{"t": 0, "box": [45, 40, 10, 15]}]}, 50)["scale"] - MIN_HEAD / 15) < 1e-3   # small head scaled up
    assert speaker_frame(None, 50)["y"] == 25
    lg = {"start": 5.0, "end": 6.2, "box": [1, 1, 1, 1], "trigger_word": "l", "lane": "logo", "anim": {"type": "logo"}}
    big = {"start": 0.0, "end": 4.0, "box": [1, 1, 1, 1], "trigger_word": "b"}
    art = split_art_box(50)
    assert art == [14, 14, 72, 34]   # centred: equal side margins
    sc2 = split_cards([big, lg, {**lg, "start": 3.5, "end": 4.7}], art)
    assert [c["box"] for c in sc2] == [art, art] and "lane" not in sc2[1] and sc2[1]["end"] == 6.5, sc2   # overlapping logo dropped
    vs = build(style, words, {**meta, "width": 1080, "height": 1920}, imgs, layout={"mode": "split"})
    assert vs["layout"]["mode"] == "split" and vs["captions"]["style"]["y_pct"] == 50 + SPLIT_CAP_BELOW
    assert all(c["box"] == art for c in vs["cards"]) and "layout" not in p
    kit = {"cues": {n: {"attack_s": 0.2} for n in SFX_RANK}}
    sp = {"fps": 30, "durationInFrames": 300, "zooms": [{"start": 1.25}, {"start": 6.0}],
          "cards": [{"start": 1.0, "end": 3.0, "anim": {"type": "flow", "props": {"nodes": [{"at": 0.5}, {"at": 0.6}],
                                                                                   "tag": {"at": 1.5}}}},
                    {"start": 7.0, "end": 8.0, "src": "images/a.png"}]}
    sw = [{"text": t, "start": s, "end": s + 0.2} for t, s in (("a", 2.6), ("b", 2.9), ("c.", 7.5))]
    cues = place_sfx(sp, sw, kit)
    ev = [(c["event"], c["src"]) for c in cues]
    assert ev == [(1.1, ".sfx/whoosh-in.wav"), (2.5, ".sfx/hit.wav")], ev   # 10 s: two cues, the highest ranked
    assert all(abs(c["t"] - (c["event"] - 0.2)) < 1e-6 for c in cues)   # started early by the attack
    assert all(b["event"] - a["event"] >= SFX_GAP_S for a, b in zip(cues, cues[1:]))   # 1.25 zoom and 1.6 pop lost
    sp["durationInFrames"] = 90   # 3 s: room for one cue, the highest ranked
    assert [c["src"] for c in place_sfx(sp, sw, kit)] == [".sfx/hit.wav"]
    sp["cards"][1]["entrance"] = "scale"
    sp["durationInFrames"] = 600
    assert ".sfx/whoosh-in.wav" not in [c["src"] for c in place_sfx(sp, sw, kit) if c["event"] > 7]   # a scaled card lands silent
    # anti-generic: stock captures and icon-only cards dropped, emoji stripped
    quiet = []
    ag = anti_generic([{"word": "a", "kind": "capture", "url": "https://unsplash.com/photos/x"},
                       {"word": "b", "kind": "anim", "type": "flow", "props": {"nodes": [{"icon": "mail"}, {"icon": "inbox"}]}},
                       {"word": "c", "kind": "anim", "type": "flow", "props": {"nodes": [{"icon": "mail"}, {"logo": "notion"}]}},
                       {"word": "d", "kind": "anim", "type": "arrow_callout", "props": {"text": "ship it \U0001F680"}}], None, quiet.append)
    assert [v["word"] for v in ag] == ["c", "d"] and ag[1]["props"]["text"] == "ship it" and len(quiet) == 3, (ag, quiet)
    assert ANIMS[:len(TEMPLATES)] == TEMPLATES and all(t in ANIMS for t in LEGACY + OVERLAYS) and not set(ANIMS) & set(TYPE_ONLY)
    # layouts: overlay first; a scene or the split panel when a beat asks, and always for an explaining card on
    # vertical (SKILL.md step 3: the sample's flow in a box rendered small and off centre)
    fr = lambda t, a="9:16", **k: frame_of({"anim": {"type": t}, "trigger_word": "x", **k}, a)
    assert (fr("shot"), fr("flow"), fr("icon_burst"), fr("logo_sting"), fr("flow", layout="split"), fr("flow", layout="scene"),
            fr("flow", layout="box"), fr("flow", "16:9")) == ("box", "scene", "split", "box", "split", "scene", "scene", "box")
    assert frame_of({"src": "images/c.png", "trigger_word": "x"}, "9:16") == "box"
    assert (fr("chat", "16:9"), fr("icon_burst", "16:9", layout="split"), fr("arrow_callout", "16:9")) == ("box", "box", "box")
    # type cards are gone: an old visuals.json naming one is skipped
    assert type_only({"type": "counter"}) and type_only({"type": "versus"}) and not type_only({"type": "side_by_side"})
    vm = {**meta, "width": 1080, "height": 1920}
    tv = [{"word": "notion", "nth": 1, "kind": "anim", "type": "flow", "layout": "scene", "props": {"nodes": [{"logo": "notion"}]}},
          {"word": "every", "nth": 1, "kind": "anim", "type": "caption_page", "hold_s": 2, "props": {}}]
    vp = build(style, words, vm, visuals=tv)
    assert "layout" not in vp and vp["motion"] == "smooth" and vp["look"] == {"preset": "neutral"}, vp   # no panel, no house palette
    cp = next(c for c in vp["cards"] if c["anim"]["type"] == "caption_page")
    assert cp["layout"] == "box" and [w["text"] for w in cp["anim"]["props"]["words"]][:2] == ["every", "video"], cp
    assert cp["anim"]["props"]["words"][0]["start"] == round(next(w for w in words if w["text"] == "every")["start"] - cp["start"], 3)
    sl = next(c for c in vp["cards"] if c["anim"]["type"] == "flow")
    assert sl["layout"] == "scene" and sl["box"] == SCENE_BOX and sl["focus"] == [50, 31] \
        and (sl["transition_in"], sl["transition_out"]) == TRANSITIONS and "_f" not in sl, sl
    st = build({**style, "transitions": ["push", "block"]}, words, vm, visuals=tv + [
        {"word": "edit.", "nth": 1, "kind": "anim", "type": "flow", "layout": "scene", "props": {"nodes": [{"logo": "github"}]}}])
    assert [c["transition_in"] for c in st["cards"] if c.get("layout") == "scene"] == ["push", "block"]
    # a creator measured as only cutting ("transitions": []) gets hard cuts, not the match/iris default
    sc = [c for c in build({**style, "transitions": []}, words, vm, visuals=tv)["cards"] if c.get("layout") == "scene"]
    assert [(c["transition_in"], c["transition_out"]) for c in sc] == [("cut", "cut")], sc
    # a hard cut lands on its first frame: no SCENE_LEAD_S, it starts CARD_LEAD_S before its word like a box card;
    # a scene whose ground grows (match) keeps the lead
    wn = next(w["start"] for w in words if clean(w["text"]).lower() == "notion")
    assert sc[0]["start"] == round(wn - CARD_LEAD_S, 3), (sc[0]["start"], wn)
    assert sl["start"] == round(max(0.0, wn - CARD_LEAD_S - SCENE_LEAD_S * MOTION_K["smooth"]), 3) < sc[0]["start"], sl["start"]
    sp2 = build(style, words, vm, [{"src": "images/c.png", "word": "every", "nth": 1}], visuals=tv[:1])
    assert "layout" not in sp2 and [c["layout"] for c in sp2["cards"]] == ["box", "scene"], sp2["cards"]
    assert build(style, words, vm, visuals=[{"word": "zooms", "kind": "anim", "type": "counter", "opt_in": True, "props": {"to": 3}}])["cards"] == []
    # an overlay goes to the free region its picture fills best: a wide shot above the head, a tall one beside it
    hd_face = {"step_s": 0.5, "heads": [{"t": float(i) / 2, "box": [32, 34, 28, 23]} for i in range(30)]}
    wide = {"src": "images/w.png", "size": [1800, 600], "start": 0.0, "end": 2.0, "trigger_word": "w", "box": [1, 1, 1, 1]}
    tall = {"src": "images/t.png", "size": [600, 1400], "start": 0.0, "end": 2.0, "trigger_word": "t", "box": [1, 1, 1, 1]}
    lc = {"anim": {"type": "logo_cluster", "props": {}}, "start": 0.0, "end": 2.0, "trigger_word": "l", "box": [1, 1, 1, 1]}
    pw, pt, pl = place_overlays([wide, tall, lc], hd_face, 68, "9:16")
    assert pw["box"][1] == 10 and pw["box"][1] + pw["box"][3] <= 34 - HEAD_GAP + 1e-6, pw["box"]
    assert pt["box"][1] == 34 and (pt["box"][0] + pt["box"][2] <= 32 or pt["box"][0] >= 60), pt["box"]
    assert pl["box"] == [0, 0, 100, 100] and pl["anim"]["props"]["head"] == [32, 34, 28, 23], pl
    assert pl["anim"]["props"]["band"] == list(LOGO_BAND) and pl["anim"]["props"]["size"] == LOGO_SIZE, pl   # big, centred
    # a logo in passing leaves when its sentence ends, not 1.2 s later over the next one
    lw = [{"text": t, "start": 0.5 * i, "end": 0.5 * i + 0.4} for i, t in enumerate("models like Claude. jev is good".split())]
    lg2 = place_cards([{"word": "Claude", "anim": {"type": "logo"}, "lane": "logo", "hold_s": LOGO_S}], lw, 5, {}, "9:16")
    assert lg2[0]["end"] == lw[3]["start"], lg2
    # a sticker's rendered x-height: 26.5 PNG px, a 777 x 315 PNG in a 92% x 21.6% box on 1080 x 1920
    st = {"format": "sticker", "size": [777, 315], "xh": 26.5, "box": [4, 10, 92, 21.6]}
    assert 28 < sticker_xh(st, "9:16") < 29.5, sticker_xh(st, "9:16")
    # capture beat format and props reach the card by capture index; a browser gets the beat's url
    wf = with_formats([{"src": "images/capture-2-docs.png", "word": "x"}], [{"kind": "capture", "url": "https://a.b"},
        {"kind": "capture", "url": "https://c.d", "format": "browser", "props": {"label": "docs"}}])
    assert wf[0]["format"] == "browser" and wf[0]["props"] == {"label": "docs", "url": "https://c.d"}, wf
    # capture marks: at_word -> at, at_s -> at, neither -> 0.8
    mk = build(style, words, vm, [{"src": "images/c.png", "word": "every", "hold_s": 3, "marks": [
        {"kind": "box", "rect": [0, 0, 9, 9], "at_word": "zooms"}, {"kind": "ring", "rect": [0, 0, 9, 9], "at_s": 2.0},
        {"kind": "dim", "rect": [0, 0, 9, 9]}]}])["cards"][0]
    zw = next(w for w in words if w["text"] == "zooms")
    assert [m["at"] for m in mk["marks"]] == [round(zw["start"] - mk["start"], 3), 2.0, 0.8] and "at_word" not in mk["marks"][0], mk
    assert pick_motion({"pace": {"median_shot_s": 1.0}}) == "punchy" and pick_motion({"motion": {"personality": "calm"}}) == "calm"
    assert pick_motion({"pace": {"median_shot_s": 3.98}}) == "smooth" and pick_motion({}) == "smooth"
    em = mark_emph([{"words": [{"text": "so", "start": 0, "end": 0.1}, {"text": "really", "start": 0.1, "end": 0.6},
                               {"text": "fast", "start": 0.6, "end": 0.75}]}])
    assert em[0]["words"][1].get("emph") and not em[0]["words"][0].get("emph")
    # behind: a wide shot above the head grows down behind the hair, its mark stays clear of the head
    bf = {"step_s": 0.5, "heads": [{"t": float(i) / 2, "box": [32, 34, 28, 23]} for i in range(10)]}
    sh = {"src": "a.png", "format": "shot", "size": [1800, 800], "start": 0.0, "end": 3.0, "trigger_word": "s", "box": [4, 10, 92, 21.6],
          "marks": [{"kind": "highlight", "rect": [100, 100, 1600, 200]}]}
    low = {**sh, "marks": [{"kind": "highlight", "rect": [100, 650, 1600, 140]}], "trigger_word": "low"}
    chat = {"anim": {"type": "chat", "props": {}}, "start": 0.0, "end": 3.0, "trigger_word": "c", "box": [4, 10, 92, 21.6]}
    gs, gl, gc = tuck_behind([dict(sh), dict(low), dict(chat)], bf, "9:16")
    assert gs["layer"] == "behind" and gs["box"][1] + gs["box"][3] > 34 and gs["key"][1] + gs["key"][3] < 34 - HEAD_GAP, gs
    assert gl["box"][1] + gl["box"][3] < gs["box"][1] + gs["box"][3], (gl, gs)    # a low mark tucks less
    assert "layer" not in gc and gc["box"] == chat["box"]
    # the creator's measured fields: dealt in her shares, used only when the blend took their part
    d = deal({"cut": 58, "slide": 12}, 12)
    assert d.count("cut") == 10 and d[:2] == ["cut", "cut"] and deal({"x": 1}, 2) == ["x", "x"] and deal({}, 1) == [None]
    assert fit_of({"kind": "slide", "ease": "back.out(3.5)", "duration_s": 0.325, "from": "top", "distance_pct": 3.5}, "9:16") == \
        {"kind": "slide", "ease": "back.out(3.5)", "dur": 0.325, "dir": "top", "dist": 6.2}
    assert fit_of({"kind": "cut", "duration_s": 0.0}, "9:16", out=True) == {"kind": "cut", "ease": "none", "dur": 0}
    her = {**style, "graphics": {"entrances": [{"kind": "cut", "ease": "none", "share_pct": 60, "duration_s": 0},
                                              {"kind": "fade", "ease": "none", "share_pct": 40, "duration_s": 0.85, "fade": True}],
                                "exits": [{"kind": "cut", "ease": "none", "share_pct": 100, "duration_s": 0}],
                                "secondary_motion": {"still": 50, "push": 50}, "kinds": {"text card": 55, "real screenshot": 40},
                                "layout": {"zones_pct": {"top": 100}}},
           "hook": {"winner": {"first_graphic_s": 0.4}, "control": {"first_graphic_s": 4.3}},
           "camera": {"pan_per_min": 6.8}, "pace": {"cut_kinds": {"zoom-punch": 1, "hard": 3}}}
    caps = [{"src": f"images/capture-{i}-x.png", "word": w} for i, w in enumerate(("so", "every", "try"), 1)]
    hp = build(her, words, vm, caps)
    assert [c["entrance"] for c in hp["cards"]] == ["cut", "fade", "cut"], hp["cards"]
    c0 = hp["cards"][0]
    assert c0["props"]["enter"] == {"kind": "cut", "ease": "none", "dur": 0} and c0["props"]["exit"]["kind"] == "cut"
    assert c0["props"]["ambient"] == "still" and c0["format"] == "sticker" and hp["cards"][1]["format"] == "shot", hp["cards"]
    assert c0["props"]["word_at"] == round(words[0]["start"] - c0["start"], 3) and "_word_t" not in c0
    assert hp["targets"]["first_graphic_s"] == 0.4 and len(hp["pans"]) == round(t / 60 * 6.8) and "props" not in caps[0]
    no = build({**her, "blend": {"take": ["captions"]}}, words, vm, caps)   # parts not taken: the defaults
    assert all("enter" not in (c.get("props") or {}) for c in no["cards"]) and "targets" not in no and "pans" not in no
    assert [c["entrance"] for c in no["cards"]] == [c["entrance"] for c in build(style, words, vm, caps)["cards"]]
    # her layout leans a tall card to the top band, still clear of the head; without it, beside the head
    pt2 = place_overlays([dict(tall)], hd_face, 68, "9:16", {"zones_pct": {"top": 90, "middle": 10}})[0]
    assert pt2["box"][1] == 10 and pt2["box"][1] + pt2["box"][3] <= 34 - HEAD_GAP + 1e-6, pt2["box"]
    assert heat({"grid": [[100, 0], [0, 0]]}, [0, 0, 50, 50]) == 1 and heat({"zones_pct": {"top": 40}}, [0, 10, 90, 20]) == 0.4
    # cut_kinds: a quarter of the cuts punch in
    cz = place_zooms({"per_min": 600, "on": "every_cut"}, words, t, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0], {"zoom-punch": 1, "hard": 3})
    assert [(z["start"], z["end"]) for z in cz] == [(2.0, 6.0)], cz   # 2 of 8 cuts change the zoom: in at 2, out at 6
    # her sound: none a minute -> no cues; impact only -> no whooshes
    assert place_sfx(sp, sw, kit, {"sfx_per_min": 0}) == []
    assert all("whoosh" not in c["src"] for c in place_sfx(sp, sw, kit, {"kinds": {"impact": 100}}))
    # one lead model for plan, renderer and check: motion.ts carries the same two numbers
    ts = (Path(__file__).resolve().parents[3] / "remotion" / "src" / "motion.ts").read_text()
    assert f"CARD_LEAD_S = {CARD_LEAD_S};" in ts and f"OVERLAY_LEAD_S = {OVERLAY_LEAD_S};" in ts, "motion.ts lead drifted"
    # the default style (no creator) on a 47 s cut whose sentences run 2-7 s: a zoom change at least every 5 s,
    # so check.py render never finds 6 s with nothing moving (the editorial {} planned 0 zooms here)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor.profile import DEFAULT_STYLE
    t, words = 0.0, []
    for n in [5, 4, 3, 7, 2, 4, 3, 2, 4, 3, 2, 3, 3] * 2:
        for k in range(int(n / 0.3)):
            words.append({"text": "word." if k == int(n / 0.3) - 1 else "word", "start": round(t, 2), "end": round(t + 0.25, 2)})
            t += 0.3
        t += 0.1
        if t > 47:
            break
    z = place_zooms(DEFAULT_STYLE["zoom"], words, t, [])
    moves = sorted([x["start"] for x in z] + [x["end"] for x in z if x["end"] < t])
    assert len(z) >= t / 10 and max(b - a for a, b in zip([0.0] + moves, moves + [t])) <= 5.0 + 1e-6, (t, moves)
    assert place_zooms({}, words, t, []) == []
    # a creator's sparse zooms (no max_hold_s) leave 12 s still; inside a stretch with no card (quiet) the frame
    # changes at least every QUIET_HOLD_S, and outside it her rhythm is untouched
    sparse = {"per_min": 2, "kind": "punch", "on": "sentence_start"}
    mv = lambda zs, a, b: sorted(x for z in zs for x in (z["start"], z["end"]) if a < x < b)
    hold_in = lambda zs, a, b: max(y - x for x, y in zip([a] + mv(zs, a, b), mv(zs, a, b) + [b]))
    assert hold_in(place_zooms(sparse, words, t, []), 10, 22) > QUIET_HOLD_S
    zq = place_zooms(sparse, words, t, [], quiet=[(10, 22)])
    assert hold_in(zq, 10, 22) <= QUIET_HOLD_S + 1e-6, mv(zq, 10, 22)
    assert mv(zq, 30, t) == mv(place_zooms(sparse, words, t, []), 30, t)
    assert card_gaps([{"start": 1, "end": 3}, {"start": 2, "end": 4}, {"start": 9, "end": 10}], 12) == [(0.0, 1), (4, 9), (10, 12)]
    assert card_gap_s({}) == GAP_S and card_gap_s({"graphics": {"per_min": 5.0}}) == 24.0
    demo_contrast()
    print("demo ok")


def demo_contrast():
    """Caption contrast: the ladder on flat colours, then measured on real clips (ffmpeg)."""
    import tempfile
    from pathlib import Path
    white = {"color": "#FFFFFF"}
    assert pick_treat([(38, 38, 38)] * 9, white)[0] is None                   # dark: the creator's look
    assert pick_treat([(126, 126, 126)] * 9, white)[:2] == ("shadow", "#111111")
    # a grey the shadow lifts only to 3.15:1 (over the FAIL line, under the margin the render needs) gets a stroke
    assert treat_for([(160, 160, 160)] * 9, (255, 255, 255), PULL["shadow"], (17, 17, 17)) > CONTRAST_MIN
    assert pick_treat([(160, 160, 160)] * 9, white)[0] == "stroke"
    assert all(pick_treat([(g, g, g)] * 9, white)[2] >= CONTRAST_TARGET for g in range(0, 256, 8))
    # mid-grey footage reads 4.48:1 with the plain shadow: under the render check's 4.5 WARN, so it gets a step
    assert pick_treat([(128, 128, 128)] * 9, white)[0] is not None
    # "plan again" after a render check read a page too low: that page gets the next step, once per check
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "plan.json").write_text(json.dumps({"captions": {"chunks": [{"start": 1.0, "end": 2.0, "treat": "shadow"},
                                                                          {"start": 2.0, "end": 3.0}]}}))
        (d / "check.json").write_text(json.dumps({"render": {"caption_contrast": {"low_at": [1.5]}}}))
        assert contrast_floors(d, d / "plan.json") == {"1.00": "stroke"}
        assert contrast_floors(d, d / "plan.json") == {"1.00": "stroke"}       # the same check is read once
        pl = {"captions": {"style": {"stroke": True}, "chunks": [{"start": 1.0, "end": 2.0, "text": "a"}]}}
        assert treat_captions(pl, d, None, {"1.00": "stroke"}) == [(0, "stroke", None)]
    assert pick_treat([(230, 225, 216)] * 9, white)[:2] == ("backing", "#111111")  # a bright desk
    assert pick_treat([(230, 225, 216)] * 9, {**white, "stroke_color": "#1B2A4A"})[1] == "#1B2A4A"   # her palette
    assert pick_treat([(250, 250, 250)] * 9, {**white, "highlight_color": "#5A5A5A"})[0] == "backing"
    assert pick_treat([(20, 20, 20)] * 9, {"color": "#111111"})[:2] == ("backing", "#F5F5F5")     # dark text
    words = [{"text": t, "start": round(0.2 + i * 0.32, 2), "end": round(0.5 + i * 0.32, 2), "type": "word"}
             for i, t in enumerate("this desk is far too bright".split())]
    style = {"captions": {"words_per_caption": 3, "y_pct": 68, "size_pct": 5, "color": "#FFFFFF", "stroke": False}}
    with tempfile.TemporaryDirectory() as d:
        for colour, want in (("0xE6E1D8", {"backing"}), ("0x262626", {None})):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=270x480:r=30:d=2.2",
                            "-f", "lavfi", "-i", "sine=d=2.2", "-vf", "noise=alls=12:allf=t", "-pix_fmt", "yuv420p",
                            f"{d}/cut.mp4"], check=True)
            meta = probe(Path(d) / "cut.mp4")
            pl = build(style, words, meta, edit_dir=d)
            treat_captions(pl, d, meta)
            got = {c.get("treat") for c in pl["captions"]["chunks"]}
            assert got == want, (colour, pl["captions"]["chunks"])
        # no style.json (the no-creator path): a note and the default style, never a traceback
        import os
        (Path(d) / "captions.json").write_text(json.dumps(words))
        r = subprocess.run([sys.executable, __file__, f"{d}/style.json", f"{d}/captions.json"], capture_output=True,
                           text=True, env={**os.environ, "AI_EDITOR_HOME": d})
        assert r.returncode == 0 and "default style" in r.stderr, r.stderr
        assert json.loads((Path(d) / "plan.json").read_text())["zooms"], r.stdout


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("style")
    ap.add_argument("words")
    ap.add_argument("--images")
    ap.add_argument("--aspect", choices=["auto", "9:16", "16:9"], default="auto")
    ap.add_argument("--layout", choices=["overlay", "split"], help="default: style.json layout.mode, else overlay")
    ap.add_argument("--out")
    ap.add_argument("--no-sfx", action="store_true", help="no sound cues (same as \"sfx\": false in style.json)")
    ap.add_argument("--behind", choices=["on", "off"], help="cards behind the speaker (default: the profile's answer); "
                    "on needs matte.py before stills")
    a = ap.parse_args()
    edit_dir = Path(a.words).resolve().parent
    video = edit_dir / "cut.mp4"
    if not video.exists():
        sys.exit(f"ERROR: no cut.mp4 in {edit_dir}. Run the cut skill first.")
    img = Path(a.images) if a.images else edit_dir / "images.json"
    images = json.loads(img.read_text()) if img.exists() else []
    vis = edit_dir / "visuals.json"
    visuals = json.loads(vis.read_text()) if vis.exists() else []
    # The user's own settings (taste skill) win over the creator's measured style.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import taste, profile
    prof = profile.load()   # the start skill's answers: brand kit, what to avoid, sound
    sp = Path(a.style)
    style = json.loads(sp.read_text() or "{}") if sp.is_file() else None
    if not style:
        print(f"note: {sp} {'is empty' if style == {} else 'not found'}; planning with the default style. To keep it "
              f"with the edit: python3 {Path(profile.__file__)} style {edit_dir}", file=sys.stderr)
        style = profile.default_style(prof)
    style = profile.fill_transitions(taste.merge(style, taste.load_json()),
                                     lambda m: print(f"note: {m}", file=sys.stderr))
    plan = build(style, json.loads(Path(a.words).read_text()),
                 probe(video), images, a.aspect, cut_points(edit_dir), visuals, edit_dir,
                 {"mode": a.layout} if a.layout else None, prof, None if a.behind is None else a.behind == "on")
    out = Path(a.out) if a.out else edit_dir / "plan.json"
    for i, t, got in treat_captions(plan, edit_dir, probe(video), contrast_floors(edit_dir, out)):
        print(f"caption {i} '{plan['captions']['chunks'][i]['text']}': {t} for contrast " +
              (f"(reaches {got}:1 on the footage behind it)" if got else "(the last render check read it too low)"),
              file=sys.stderr)
    if a.no_sfx or (prof.get("sound") or {}).get("sfx") is False:
        plan["sfx"] = []
    if (edit_dir / ".sfx" / "music.wav").exists() and (prof.get("sound") or {}).get("music") is not False:
        plan["music"] = {"src": ".sfx/music.wav"}   # sfx.py music: the bed, ducked under the speech
    music = ((style.get("sound") or {}).get("music") or {}) if took(style, "sound") else {}
    if music.get("present_pct") and "music" not in plan:   # guidance only: the renderer lays no music (references/visuals.md "From the teardown")
        print(f"music: the creator runs a bed under {music['present_pct']}% of her videos, {abs(music.get('level_db') or 0):.0f} dB "
              "under the voice; sfx.py music lays one at that level (the style-edit Sound step)", file=sys.stderr)
    from preview import apply_overrides   # edits/<name>/overrides.json, written by the preview page
    plan = apply_overrides(plan, edit_dir, out.name)
    import matte   # a re-plan keeps the speaker's cutout wherever matte.py already cut every frame it needs
    if matte.behind_ranges(plan):
        plan["cutouts"] = matte.kept(plan, edit_dir)
        if len(plan["cutouts"]) < len(matte.behind_ranges(plan)):
            print(f"behind cards: run matte.py {edit_dir}" + (f" --plan {out.name}" if out.name != "plan.json" else "")
                  + " (it cuts only the frames not cut yet)", file=sys.stderr)
    out.write_text(json.dumps(plan, indent=1))
    from ai_tells import check_plan as ai_tells, for_brand   # the AI-made look (references/ai-tells.md)
    for f in for_brand(ai_tells(plan, visuals), prof.get("brand")):
        print(f"{'error' if f['level'] == 'BAN' else 'warning'}: AI tell '{f['tell']}': {f['where']} -> {f['fix']}", file=sys.stderr)
    print(f"{out}: {plan['width']}x{plan['height']}, {plan['durationInFrames'] / plan['fps']:.1f} s, "
          f"{len(plan['captions']['chunks'])} captions, {len(plan['zooms'])} zooms, {len(plan['cards'])} cards")


if __name__ == "__main__":
    main()
