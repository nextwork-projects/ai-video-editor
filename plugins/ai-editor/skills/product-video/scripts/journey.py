#!/usr/bin/env python3
"""The rendered product film: UI states (record.mjs --states) laid out on one canvas, one camera moving
through them, every frame drawn by Remotion (nothing recorded plays back).

    product.py plan DIR --story story-v4.json ...   (a story with "beats" comes here)
    python3 journey.py demo                          self-check, no network

A story is beats, in the order the film tells them (references/story.md "Story first"):
    {"beats": [{"job": "hook", "flow": "search", "text": "Learn anything by building"},
               {"job": "action", "flow": "search", "steps": [0, 1], "text": "Search NextWork"},
               {"job": "result", "flow": "search"}, ...,
               {"job": "payoff", "flow": "library", "steps": [1]}, {"job": "end"}]}
A beat's "steps" index the flow's steps (its states.json, auto scrolls skipped); "result" pushes onto
what the last step changed; "payoff" pulls slowly out.

The plan carries the camera and the cursor for every frame, so the framing check below reads exactly
what will be drawn. Units: canvas px = the page's CSS px; a plate is one page.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

# one easing language for the whole film: every move on MOVE, every arrival on SETTLE (cubic-bezier)
MOVE = (0.38, 0.0, 0.45, 1.0)   # peak speed 1.9x the average (a sine is 1.6), a touch longer settle
SETTLE = (0.2, 0.8, 0.2, 1.0)
SMOOTH_S = 0.2       # the camera path is low-passed: the next move starts before the last settles
HOLD_PUSH = 0.035    # a held framing keeps pushing in, 3.5% over the hold: nothing stops dead
SAFE = 0.045         # the safe frame's margin, share of the short side
CPS = 14             # typed characters a second
GAP = 0.06           # space between pages on the canvas, share of a page's width
JOBS = {             # job -> the shots that do it (references/story.md)
    "hook": "the first page, wide, pushing in, the promise in the site's words",
    "reveal": "a push from wide onto the product",
    "action": "cursor click-through at readable scale",
    "result": "a push onto what changed",
    "payoff": "a slow pull-out",
    "end": "logo and address",
}


def bezier(p1x, p1y, p2x, p2y):
    def f(p):
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            t = (lo + hi) / 2
            x = 3 * (1 - t) ** 2 * t * p1x + 3 * (1 - t) * t * t * p2x + t ** 3
            lo, hi = (t, hi) if x < p else (lo, t)
        t = (lo + hi) / 2
        return 3 * (1 - t) ** 2 * t * p1y + 3 * (1 - t) * t * t * p2y + t ** 3
    return f


ease_move, ease_settle = bezier(*MOVE), bezier(*SETTLE)


# ---------------------------------------------------------------- reading the captures

def gray(d, src, size):
    """A state as grey at CSS size (one px per CSS px)."""
    import numpy as np
    from PIL import Image
    with Image.open(Path(d) / src) as im:
        return np.asarray(im.convert("L").resize((int(size[0]), int(size[1])), Image.BILINEAR), dtype=np.int16)


def bbox(mask, pad=0):
    import numpy as np
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    return [max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad), int(xs.max() - xs.min()) + 1 + 2 * pad, int(ys.max() - ys.min()) + 1 + 2 * pad]


def content_box(img):
    """Where the UI has detail (edges), ignoring flat ground: the part of a page worth framing."""
    import cv2
    import numpy as np
    e = cv2.Canny(img.astype(np.uint8), 40, 120)
    e = cv2.dilate(e, np.ones((9, 9), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats((e > 0).astype(np.uint8))
    keep = np.zeros_like(e, bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] > 400:
            keep |= lab == i
    return bbox(keep) or [0, 0, img.shape[1], img.shape[0]]


def change(d, a, b):
    """What a step changed between two states of the same viewport: the kind of reveal and its rects
    (viewport px). sweep = most of the content replaced (results arriving); modal = the page dims and a
    panel appears; pop = one region changes."""
    import cv2
    import numpy as np
    if a["size"] != b["size"]:
        return {"kind": "fade", "strong": [0, 0, *b["size"]], "weak": [0, 0, *b["size"]]}
    A, B = gray(d, a["src"], a["size"]), gray(d, b["src"], b["size"])
    diff = np.abs(A - B).astype(np.uint8)
    k = np.ones((5, 5), np.uint8)
    weak = cv2.morphologyEx((diff > 10).astype(np.uint8), cv2.MORPH_OPEN, k)
    strong = cv2.morphologyEx((diff > 45).astype(np.uint8), cv2.MORPH_OPEN, k)
    W, H = a["size"]
    wb, sb = bbox(weak, 6), bbox(cv2.dilate(strong, np.ones((25, 25), np.uint8)), 4)
    if not sb:
        return {"kind": "none", "strong": None, "weak": wb}
    area = lambda r: r[2] * r[3] / (W * H)
    # a panel over a dimmed page: most pixels are the old ones times one factor (the backdrop); the panel is
    # where they are not
    lit = A > 24
    ratio = float(np.median(B[lit] / A[lit])) if lit.any() else 1.0
    off = np.abs(B - A * ratio)
    if ratio < 0.85 and float((off[lit] < 10).mean()) > 0.4:
        panel = cv2.morphologyEx((off > 28).astype(np.uint8), cv2.MORPH_OPEN, k)
        pb = bbox(cv2.dilate(panel, np.ones((15, 15), np.uint8)), 2)
        if pb and area(pb) < 0.85:
            return {"kind": "modal", "strong": pb, "weak": [0, 0, W, H]}
    if area(sb) > 0.35:
        kind = "sweep"
    else:
        kind = "pop"
    return {"kind": kind, "strong": sb, "weak": wb or sb}


def load_flow(d, fid, vertical):
    d = Path(d)
    if vertical and (d / "flows" / f"{fid}-m.states.json").exists():
        fid += "-m"
    p = d / "flows" / f"{fid}.states.json"
    if not p.exists():
        sys.exit(f"ERROR: {p} missing: node record.mjs {d} <flows.json> --states" + (" --mobile" if vertical else ""))
    f = json.loads(p.read_text())
    f["real"] = [i for i, s in enumerate(f["steps"]) if not s.get("auto")]   # what a story's step numbers index
    return f


# ---------------------------------------------------------------- the plan

def fit(T, plate, frame, words=False, wmin=0.0, pad=1.2):
    """The camera rect (cx, cy, w) that shows T (canvas px) at a readable size, inside the plate when it can,
    above the words band when the beat has words."""
    W, H = frame
    A = W / H
    vertical = H > W
    usable = (0.6 if vertical else 0.55) if words else 0.88   # share of the height above the words
    w = max(T[2] * pad, T[3] * pad / usable * A, wmin)
    w = min(w, plate["w"] * (1.06 if vertical else 1.12))     # a phone page fills a tall frame edge to edge
    w = max(w, wmin)
    h = w / A
    cx = T[0] + T[2] / 2
    cy = T[1] + T[3] / 2
    if words:      # T sits in the top part: its centre at the middle of the usable band
        cy += h * (0.5 - (0.05 + usable / 2))
    if w <= plate["w"]:
        cx = min(max(cx, plate["x"] + w / 2), plate["x"] + plate["w"] - w / 2)
    else:
        cx = plate["x"] + plate["w"] / 2
    if h <= plate["h"]:
        cy = min(max(cy, plate["y"] + h / 2), plate["y"] + plate["h"] - h / 2)
    # clamping must never push T out: if it did, centre on T instead
    if not (cx - w / 2 <= T[0] and T[0] + T[2] <= cx + w / 2):
        cx = T[0] + T[2] / 2
    return [cx, cy, w]


def readable(r, vw, vh):
    """A focus small enough to read: at most ~0.7 of a desktop page wide (a phone page whole) and under half
    its height, kept from its top left (where a list or a page starts)."""
    capw = max(0.6 * vw, min(vw, 600))
    # a page's outer 4% is its margin: a full-width block is read from inside it
    x0, x1 = max(r[0], 0.04 * vw), min(r[0] + r[2], 0.96 * vw)
    return [x0, r[1], min(x1 - x0, capw), min(r[3], 0.4 * vh)]


def dense_focus(img, w, h):
    """The readable-size window (w x h, page px) with the most UI detail in it, leaning to the top: where a
    page's content is, rather than its empty header or margins."""
    import cv2
    import numpy as np
    e = (cv2.Canny(img.astype(np.uint8), 40, 120) > 0).astype(np.float64)
    H, W = e.shape
    w, h = int(min(w, W)), int(min(h, H))
    ii = np.pad(e.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    best, at = -1.0, (0, 0)
    for y in range(0, H - h + 1, 20):
        for x in range(0, W - w + 1, 20):
            v = ii[y + h, x + w] - ii[y, x + w] - ii[y + h, x] + ii[y, x]
            v *= 1 - 0.35 * y / max(1, H - h)
            if v > best:
                best, at = v, (x, y)
    return [at[0], at[1], w, h]


def redact(d, src, tokens):
    """The state with the logged-in account's name or handle blurred wherever it is still readable, including
    text inside pictures the page shows (a screenshot with a home folder path in it). OCR finds the words, a
    word close to a token (difflib ratio 0.75 or more) counts. Writes <src>.redacted.jpg once; returns the src to use."""
    import difflib
    import re
    from PIL import Image, ImageFilter
    if not tokens:
        return src
    d = Path(d)
    out = str(Path(src).with_suffix("")) + ".redacted.jpg"
    if (d / out).exists() and (d / out).stat().st_mtime >= (d / src).stat().st_mtime:
        return out if (d / out).stat().st_size else src
    read = ocr_boxes()
    if not read:
        return src
    im = Image.open(d / src).convert("RGB")
    hits = []
    for text, (x, y, w, h) in read(im):
        for word in re.split(r"[^0-9a-z]+", text.lower()):
            if len(word) >= 4 and any(t in word or difflib.SequenceMatcher(None, word, t).ratio() >= 0.75 for t in tokens):
                hits.append((x, y, w, h))
                break
    if not hits:
        (d / out).write_bytes(b"")          # checked, nothing to hide
        return src
    W, H = im.size
    for x, y, w, h in hits:
        box = [int((x - 0.01) * W), int((y - 0.25 * h) * H), int((x + w + 0.01) * W), int((y + 1.25 * h) * H)]
        reg = im.crop(box)
        im.paste(reg.filter(ImageFilter.GaussianBlur(max(10, (box[3] - box[1]) * 0.45))), box)
    im.save(d / out, quality=92)
    return out


def ocr_boxes():
    """fn(PIL image) -> [(text, [x, y, w, h] as fractions, top-left origin)], or None."""
    try:
        from ocrmac import ocrmac
        return lambda im: [(t, [x, 1 - y - h, w, h]) for t, c, (x, y, w, h) in ocrmac.OCR(im, recognition_level="accurate").recognize() if c >= 0.2]
    except ImportError:
        pass
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
        eng = RapidOCR()

        def rapid(im):
            W, H = im.size
            out = []
            for b, t, _ in (eng(np.asarray(im)[:, :, ::-1])[0] or []):
                b = np.asarray(b, float)
                (x0, y0), (x1, y1) = b.min(0), b.max(0)
                out.append((t, [x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H]))
            return out
        return rapid
    except ImportError:
        return None


def union(*rs):
    rs = [r for r in rs if r]
    x0, y0 = min(r[0] for r in rs), min(r[1] for r in rs)
    x1, y1 = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
    return [x0, y0, x1 - x0, y1 - y0]


def build(d, story, aspect="16:9", fps=60, variant="linear"):
    """story (with beats) -> the journey part of a plan: canvas, per-frame camera and cursor, words, beats,
    sound cues, and the focus each held framing must keep in frame."""
    import numpy as np
    d = Path(d)
    W, H = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    vertical = H > W * 1.2
    beats = [b for b in story["beats"]]
    flows, order = {}, []
    for b in beats:
        if b.get("flow") and b["flow"] not in flows:
            flows[b["flow"]] = load_flow(d, b["flow"], vertical)
            order.append(b["flow"])
    dsf = min(f["dsf"] for f in flows.values())
    vw = next(iter(flows.values()))["viewport"][0]
    wmin = W / dsf                       # never upscale a capture past 1.0 (3x captures: a third of the frame)

    # ---- canvas: one plate per page, left to right; a flow that starts where the last ended reuses its plate
    plates, where = [], {}
    prev = None
    for fid in order:
        f = flows[fid]
        for pi, p in enumerate(f["plates"]):
            hgt = max(s["y"] + s["size"][1] for s in f["states"] if s["plate"] == pi)
            alias = None
            if pi == 0 and prev:
                pf = flows[prev]
                last = pf["states"][-1]["plate"]
                first = f["states"][0]
                cand = [s for s in pf["states"] if s["plate"] == last and s["y"] == 0 and s["size"] == first["size"]]
                g0 = gray(d, first["src"], first["size"])
                if any(np.abs(gray(d, s["src"], s["size"]) - g0).mean() < 6 for s in cand):
                    alias = where[(prev, last)]
            if alias is not None:
                where[(fid, pi)] = alias
                plates[alias]["h"] = max(plates[alias]["h"], hgt)
                continue
            # the next page sits level with where the camera leaves the last one, so the travel is sideways
            x = plates[-1]["x"] + plates[-1]["w"] * (1 + GAP) if plates else 0
            y = plates[-1]["endy"] if plates else 0
            plates.append({"x": x, "y": y, "w": f["viewport"][0], "h": hgt, "endy": y})
            where[(fid, pi)] = len(plates) - 1
        for pi in range(len(f["plates"])):
            last = [s for s in f["states"] if s["plate"] == pi][-1]
            pl = plates[where[(fid, pi)]]
            pl["endy"] = pl["y"] + max(0, last["y"] + last["size"][1] - f["viewport"][1])
        prev = fid
    for pl in plates:
        pl.pop("endy", None)

    def at(fid, state):
        s = flows[fid]["states"][state]
        p = plates[where[(fid, s["plate"])]]
        return p, [p["x"], p["y"] + s["y"], s["size"][0], s["size"][1]]

    layers, keys, cues, words, out_beats, clicks, cursor_moves, presses = [], [], [], [], [], [], [], []
    t = 0.0
    shown = set()
    cur = None                      # cursor position (canvas px)
    plate_of_view = None

    def layer(fid, state, t0, kind, dur=0.0, **kw):
        p, r = at(fid, state)
        L = {"plate": plates.index(p), "src": flows[fid]["states"][state]["src"], "x": r[0], "y": r[1], "w": r[2], "h": r[3],
             "t": round(t0, 3), "kind": kind, "dur": round(dur, 3)}
        for k, v in kw.items():
            L[k] = [round(x, 1) for x in v] if isinstance(v, list) and v and isinstance(v[0], (int, float)) else v
        layers.append(L)
        return L

    wend = [-1.0]       # when this beat's words leave

    def key(t0, T, plate, words_on, focus=None, wide=False):
        words_on = bool(words_on) and t0 - 1.2 <= wend[0]     # a framing held after the words have gone needs no room for them
        if words_on and T[3] * 1.2 / (0.6 if H > W else 0.55) * W / H > plate["w"] * 1.12:
            # too tall to sit above the words at a readable size: the words leave before the camera gets there
            wend[0] = min(wend[0], t0 - 1.3)
            words_on = False
        cam = fit(T, plate, (W, H), words_on, wmin, pad=1.06 if wide else 1.2)
        keys.append({"t": round(t0, 3), "cam": cam, "focus": focus or T, "words": words_on, "wmax": plate["w"] * (1.06 if vertical else 1.3)})

    def view_rect(fid, state):
        p, r = at(fid, state)
        return p, [r[0], r[1], r[2], min(r[3], flows[fid]["viewport"][1])]

    for bi, b in enumerate(beats):
        job = b["job"]
        if job not in JOBS:
            sys.exit(f"ERROR: beat {bi}: job {job!r} is not one of {', '.join(JOBS)}")
        start = t
        text = b.get("text")
        wend[0] = start + 0.15 + max(2.0, 1.0 + 0.32 * len(text.split())) if text else -1.0
        if job == "end":
            out_beats.append({"job": "end", "start": round(t, 3), "end": round(t + 3.4, 3)})
            cues += [{"t": round(t, 3), "kind": "swell"}, {"t": round(t + 0.05, 3), "kind": "hit"}]
            t += 3.4
            break
        f = flows[b["flow"]]
        fid = b["flow"]
        # the flow's first state, the first time it is shown
        if fid not in shown:
            shown.add(fid)
            p, r = at(fid, 0)
            fresh = not any(L["plate"] == plates.index(p) for L in layers)
            layer(fid, 0, t, "base" if not layers else ("plate-in" if fresh else "fade"), 0.0 if not layers else 0.6)
            if layers[-1]["kind"] == "plate-in":
                cues.append({"t": round(t, 3), "kind": "whoosh"})
                t += 1.0          # the camera's travel to a new page takes its time: nothing streaks past
        steps = [f["real"][i] for i in b.get("steps", [])]
        panel = f.get("_open_panel")
        if job in ("hook", "reveal"):
            p, vr = view_rect(fid, 0)
            dur = b.get("dur", 3.0)
            # wide on the whole page, pushing in to where the next beat acts
            top = [vr[0] + vr[2] * 0.06, vr[1] + vr[3] * 0.03, vr[2] * 0.88, vr[3] * 0.5]
            w0 = p["w"] * (1.06 if vertical else 1.12)
            keys.append({"t": round(t, 3), "cam": [vr[0] + vr[2] / 2, top[1] + top[3] / 2 + w0 * H / W * 0.17 if text else vr[1] + vr[3] / 2, w0],
                         "focus": top, "words": bool(text), "wide": True, "wmax": p["w"] * (1.06 if vertical else 1.3)})
            nxt = next((bb for bb in beats[bi + 1:] if bb.get("steps")), None)
            if nxt and nxt["flow"] == fid:
                s0 = f["steps"][f["real"][nxt["steps"][0]]]
                T = union(s0.get("rect") and [vr[0] + s0["rect"][0], vr[1] + s0["rect"][1], s0["rect"][2], s0["rect"][3]], [vr[0] + vr[2] * 0.02, vr[1], vr[2] * 0.96, vr[3] * 0.4])
                key(t + dur, T, p, bool(text))
            t += dur
        # ---- the steps this beat performs (an action with words lets them land first: words, then the hand)
        if job == "action" and text and steps:
            t += 0.8
        for si in steps:
            s = f["steps"][si]
            # auto scrolls (a target scrolled into view) just before this step
            for ai in range(si - 1, -1, -1):
                if not f["steps"][ai].get("auto"):
                    break
                a = f["steps"][ai]
                layer(fid, a["to"], t, "fade", 0.35)
                t += 0.4
            kind = s["kind"]
            p, vr = view_rect(fid, s["from"])
            if kind in ("click", "hover", "type"):
                # rect and at are plate px; the plate sits at p.x, p.y
                tgt = [p["x"] + s["rect"][0], p["y"] + s["rect"][1], s["rect"][2], s["rect"][3]]
                hand = [p["x"] + s["at"][0], p["y"] + s["at"][1]]
                extra = None
                if kind == "type" and s.get("caret"):
                    c = s["caret"]
                    lines = max(x[1] for x in c["pos"]) + 1
                    extra = [p["x"] + c["left"], p["y"] + c["top"], max(x[0] for x in c["pos"]) + 12, lines * c["lh"]]
                T = union(tgt, extra)
                if panel and panel[2] <= max(0.7 * f["viewport"][0], min(f["viewport"][0], 600)) * 1.1:
                    T = union(T, panel)       # a step inside an open panel frames the whole panel
                # the hand enters from low right of where the camera will be
                cam = fit(T, p, (W, H), bool(text), wmin)
                if cur is None or vertical:
                    cur = [cam[0] + cam[2] * 0.3, cam[1] + cam[2] / (W / H) * 0.32]
                dist = math.hypot(hand[0] - cur[0], hand[1] - cur[1])
                mv = min(1.0, max(0.55, 0.5 + dist / 1800))
                t_click = t + max(1.25, mv + 0.5)      # the camera settles, then the hand clicks
                # the camera frames what the hand acts on; the hand fades in once it is wholly in frame (gate_cursor)
                key(t_click - 0.45, T, p, bool(text), focus=T)
                cursor_moves.append({"t0": round(t_click - mv - 0.1, 3), "t1": round(t_click - 0.1, 3), "a": cur, "b": hand, "hand": kind == "click"})
                cur = hand
                if kind == "hover":
                    ch = change(d, f["states"][s["from"]], f["states"][s["to"]])
                    r = ch["weak"] or s["rect"]
                    layer(fid, s["to"], t_click - 0.05, "pop", 0.25, rect=[vr[0] + r[0], vr[1] + r[1], r[2], r[3]])
                    # a hover's result is the panel it sits in, whole, not the button alone
                    s["_focus"] = union(tgt, panel) if panel else tgt
                    t = t_click + 0.5
                    continue
                presses.append(round(t_click, 3))
                clicks.append({"t": round(t_click, 3), "x": hand[0], "y": hand[1]})
                cues.append({"t": round(t_click, 3), "kind": "click"})
                if kind == "type":
                    c = s["caret"]
                    layer(fid, s["empty"], t_click + 0.05, "fade", 0.18)
                    t0 = t_click + 0.35
                    n = len(s["text"])
                    layer(fid, s["to"], t0, "type", n / CPS, caret={**c, "top": c["top"] + p["y"]}, cps=CPS, n=n)
                    s["_focus"] = T
                    for j in range(n):
                        if j % 2 == 0:
                            cues.append({"t": round(t0 + j / CPS, 3), "kind": "tick"})
                    t = t0 + n / CPS + 0.45
                    continue
                if s.get("navigates"):
                    np_, nr = view_rect(fid, s["to"])
                    layer(fid, s["to"], t_click + 0.12, "plate-in", 0.7)
                    cues.append({"t": round(t_click + 0.1, 3), "kind": "whoosh"})
                    vwp, vhp = f["viewport"]
                    cb = dense_focus(gray(d, f["states"][s["to"]]["src"], f["states"][s["to"]]["size"])[:vhp], max(0.6 * vwp, min(vwp, 600)), 0.4 * vhp)
                    cb = readable(cb, vwp, vhp)
                    T2 = [nr[0] + cb[0], nr[1] + cb[1], cb[2], cb[3]]
                    panel = None
                    key(t_click + 1.7, T2, np_, bool(text))
                    s["_focus"] = T2
                    t = t_click + 1.9
                    cur = None if vertical else [np_["x"] + hand[0] - p["x"], np_["y"] + hand[1] - p["y"]]
                    continue
                ch = change(d, f["states"][s["from"]], f["states"][s["to"]])
                s["_change"] = ch
                r = ch["strong"] or s["rect"]
                mask = union(r, ch["weak"]) if ch["kind"] == "pop" and ch.get("weak") else r
                if ch["kind"] == "modal":
                    vwp = f["viewport"][0]
                    x0, x1 = max(r[0], 0.04 * vwp), min(r[0] + r[2], 0.96 * vwp)     # inside the page margin
                    s["_panel"] = panel = [vr[0] + x0, vr[1] + r[1], x1 - x0, r[3]]
                layer(fid, s["to"], t_click + 0.08, ch["kind"] if ch["kind"] != "none" else "fade", {"sweep": 0.75, "modal": 0.5, "pop": 0.4}.get(ch["kind"], 0.3),
                      rect=[vr[0] + mask[0], vr[1] + mask[1], mask[2], mask[3]],
                      weak=[vr[0] + ch["weak"][0], vr[1] + ch["weak"][1], ch["weak"][2], ch["weak"][3]] if ch.get("weak") else None)
                s["_focus"] = panel if ch["kind"] == "modal" else readable([vr[0] + r[0], vr[1] + r[1], r[2], r[3]], *f["viewport"])
                t = t_click + 0.55
            elif kind == "key":
                t_key = t + 0.25
                presses.append(None)
                cues.append({"t": round(t_key, 3), "kind": "click"})
                if s.get("navigates"):
                    np_, nr = view_rect(fid, s["to"])
                    layer(fid, s["to"], t_key + 0.1, "plate-in", 0.7)
                    s["_focus"] = nr
                else:
                    ch = change(d, f["states"][s["from"]], f["states"][s["to"]])
                    r = ch["strong"] or [0, 0, *f["viewport"]]
                    mask = union(r, ch["weak"]) if ch["kind"] == "pop" and ch.get("weak") else r
                    layer(fid, s["to"], t_key + 0.06, ch["kind"] if ch["kind"] != "none" else "fade", {"sweep": 0.8, "modal": 0.5, "pop": 0.4}.get(ch["kind"], 0.3),
                          rect=[vr[0] + mask[0], vr[1] + mask[1], mask[2], mask[3]],
                          weak=[vr[0] + ch["weak"][0], vr[1] + ch["weak"][1], ch["weak"][2], ch["weak"][3]] if ch.get("weak") else None)
                    s["_focus"] = readable([vr[0] + r[0], vr[1] + r[1], r[2], r[3]], *f["viewport"])
                t = t_key + 0.6
            elif kind == "scroll":
                tall = f["states"][s["to"]]
                p, tr = at(fid, s["to"])
                layer(fid, s["to"], t, "base")
                dur = min(3.4, max(1.6, abs(s["dy"]) / 750))
                # the camera travels down the page: from the top of the tall still to its bottom viewport
                cbt = content_box(gray(d, tall["src"], tall["size"]))
                x0, x1 = tr[0] + cbt[0], cbt[2]
                vh = f["viewport"][1]
                x1 = min(x1, max(0.55 * f["viewport"][0], min(f["viewport"][0], 600)))   # read at phone size
                top = [x0, tr[1] + 40, x1, vh * 0.42]
                bot = [x0, tr[1] + tall["size"][1] - vh * 0.6, x1, vh * 0.42]
                # from where the camera already is on this page (never back up to the top first), down to the end
                prior = next((f["steps"][q].get("_focus") for q in range(si - 1, -1, -1) if f["steps"][q].get("_focus")), None)
                if not (prior and f["states"][f["steps"][si - 1]["to"]]["plate"] == tall["plate"]):
                    key(t + 0.2, top, p, bool(text))
                key(t + 0.2 + dur, bot, p, bool(text))
                s["_focus"] = bot
                cur = None
                t += dur + 0.4
        f["_open_panel"] = panel
        # ---- what the beat does with the camera after its steps
        last = f["steps"][steps[-1]] if steps else (f["steps"][f["real"][b["after"]]] if "after" in b else None)
        if job == "result":
            prev_step = None
            for bb in reversed(beats[:bi]):
                if bb.get("flow") == fid and bb.get("steps"):
                    prev_step = f["steps"][f["real"][bb["steps"][-1]]]
                    break
            st = last or prev_step
            if st is not None and st.get("_focus"):
                p = plates[where[(fid, f["states"][st["to"]]["plate"])]]
                key(t + 0.9, st["_focus"], p, bool(text))
            t += max(b.get("dur", 2.4), 1.2 + 0.3 * len((text or "").split()))
        elif job == "payoff":
            st = last
            if st is None:
                for bb in reversed(beats[:bi]):
                    if bb.get("flow") == fid and bb.get("steps"):
                        st = f["steps"][f["real"][bb["steps"][-1]]]
                        break
            p = plates[where[(fid, f["states"][st["to"]]["plate"])]] if st else plates[-1]
            # slow pull-out to the whole page, held on what the beat ended on
            fr = (st or {}).get("_focus") or [p["x"], p["y"], p["w"], f["viewport"][1]]
            dur = b.get("dur", 3.2)
            keys.append({"t": round(t + dur, 3), "cam": [p["x"] + p["w"] / 2, fr[1] + fr[3] / 2, min(p["w"] * 1.1, max(wmin, p["w"] * (1.06 if vertical else 1.1)))],
                         "focus": fr, "words": bool(text), "wide": True, "wmax": p["w"] * (1.06 if vertical else 1.3)})
            t += dur
        elif job == "action":
            t += 0.35
        if text:
            # the words open the beat and leave before the hand is busy: the UI carries the rest
            if wend[0] - start > 1.2:
                words.append({"text": text, "start": round(start + 0.15, 3), "end": round(min(t, wend[0]), 3)})
        out_beats.append({"job": job, "start": round(start, 3), "end": round(t, 3), "text": text, "flow": fid})
    total = t
    who = d / "flows" / "whoami.json"
    toks = [x.lower() for x in json.loads(who.read_text()).get("tokens", []) if len(x) >= 4] if who.exists() else []
    for L in layers:
        L["src"] = redact(d, L["src"], toks)
    n = int(round(total * fps))
    cam, hold_focus = camera(keys, n, fps, W, H, wmin)
    cursor = cursor_path(cursor_moves, presses, n, fps, vertical, out_beats)
    raw_cursor = [list(c) for c in cursor]
    gate_cursor(cursor, cam, W, H, fps, vertical)
    end_t = next((b["start"] for b in out_beats if b["job"] == "end"), total)
    tone = "dark" if np.median([gray(d, L["src"], (64, 40)).mean() for L in layers]) < 100 else "light"
    return {"journey": True, "width": W, "height": H, "fps": fps, "durationInFrames": n, "tone": tone, "dsf": dsf, "wmin": round(wmin, 2),
            "canvas": {"plates": [{k: round(v, 1) for k, v in p.items()} for p in plates], "layers": layers},
            "cam": [[round(x, 2) for x in c] for c in cam], "cursor": cursor, "cursor_raw": raw_cursor, "touch": vertical and any(f.get("mobile") for f in flows.values()),
            "clicks": [{**c, "x": round(c["x"], 1), "y": round(c["y"], 1)} for c in clicks],
            "words": words, "beats": out_beats, "end": round(end_t, 3), "keys": keys, "cues": cues}


def camera(keys, n, fps, W, H, wmin=0.0):
    """Per-frame (cx, cy, w): each key is arrived at on MOVE (zooming in log space about the focal point),
    a held key keeps pushing in, then the whole path is low-passed so moves overlap and nothing stops dead."""
    import numpy as np
    keys = sorted(keys, key=lambda k: k["t"])
    # merge keys that land within 0.3 s of each other (the later wins)
    merged = []
    for k in keys:
        if merged and k["t"] - merged[-1]["t"] < 0.3:
            merged[-1] = k
        else:
            merged.append(k)
    keys = merged
    ts = np.arange(n) / fps
    out = np.zeros((n, 3))
    for i, t in enumerate(ts):
        if t <= keys[0]["t"]:
            c = keys[0]["cam"]
            out[i] = c
            continue
        j = max(k for k in range(len(keys)) if keys[k]["t"] <= t) if t < keys[-1]["t"] else len(keys) - 1
        a = keys[j]
        if j == len(keys) - 1:
            hold = t - a["t"]
            out[i] = [a["cam"][0], a["cam"][1], a["cam"][2] * math.exp(-HOLD_PUSH * min(hold, 4) / 3)]
            continue
        b = keys[j + 1]
        far = math.hypot(b["cam"][0] - a["cam"][0], b["cam"][1] - a["cam"][1]) / max(a["cam"][2], 1)   # in frame widths
        D = min(b["t"] - a["t"], max(1.0, min(2.4, 1.0 + 0.35 * abs(math.log(b["cam"][2] / a["cam"][2])) + 0.6 * far)))
        b["D"] = round(D, 3)       # the framing check holds a key's focus until the next move begins
        s = b["t"] - D
        # the held framing pushes in gently until the next move takes over
        wa = a["cam"][2] * math.exp(-HOLD_PUSH * min(max(0, min(t, s) - a["t"]), 4) / 3)
        if t < s:
            out[i] = [a["cam"][0], a["cam"][1], wa]
            continue
        p = ease_move((t - s) / D)
        wa0 = a["cam"][2] * math.exp(-HOLD_PUSH * min(max(0, s - a["t"]), 4) / 3)
        w = math.exp(math.log(wa0) + (math.log(b["cam"][2]) - math.log(wa0)) * p)
        q = (w - wa0) / (b["cam"][2] - wa0) if abs(b["cam"][2] - wa0) > 1 else p
        if far > 0.6:
            # a long travel lifts away and comes back down (a crane, not a dolly): the page never streaks past
            q = p
            w *= math.exp(min(0.45, 0.22 * far) * math.sin(math.pi * p))
        out[i] = [a["cam"][0] + (b["cam"][0] - a["cam"][0]) * q, a["cam"][1] + (b["cam"][1] - a["cam"][1]) * q, w]
    # low-pass: x, y and log w, with the ends held (no pull toward zero)
    sig = SMOOTH_S * fps
    r = int(3 * sig)
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    lw = np.log(out[:, 2])
    for c, arr in ((0, out[:, 0]), (1, out[:, 1]), (2, lw)):
        padded = np.concatenate([np.full(r, arr[0]), arr, np.full(r, arr[-1])])
        sm = np.convolve(padded, k, mode="valid")
        if c == 2:
            out[:, 2] = np.maximum(np.exp(sm), wmin)     # the push never goes past 1:1 on the capture
        else:
            out[:, c] = sm
    return out.tolist(), keys


def gate_cursor(cursor, cam, W, H, fps, touch):
    """The cursor wholly inside the frame or not shown: hidden on every frame where any part of it would be
    cut, faded out over 0.2 s before it gets there and in after (in place, never sliding off an edge)."""
    import numpy as np
    S = min(W, H) / 1080 * 1.25
    cw, ch = (44 * S, 44 * S) if touch else (30 * S, 42 * S)
    m = 6
    ok = np.zeros(len(cursor), bool)
    for i, ((x, y, a, _, _), (cx, cy, w)) in enumerate(zip(cursor, cam)):
        k = W / w
        sx, sy = (x - cx) * k + W / 2, (y - cy) * k + H / 2
        x0, y0 = (sx - cw / 2, sy - ch / 2) if touch else (sx - 9 * S, sy - 2 * S)
        ok[i] = x0 > m and y0 > m and x0 + cw < W - m and y0 + ch < H - m
    r = max(1, int(0.2 * fps))
    gate = np.array([ok[max(0, i - r):i + r + 1].all() for i in range(len(ok))], float)   # inside for 0.2 s either side
    fade = np.convolve(np.pad(gate, r, mode="edge"), np.ones(2 * r + 1) / (2 * r + 1), mode="valid")
    for i, c in enumerate(cursor):
        c[2] = round(min(c[2], fade[i]) if ok[i] else 0.0, 2)


def cursor_path(moves, presses, n, fps, touch, beats):
    """Per frame [x, y, alpha, press, hand]: glides on MOVE along a slight arc; a press dips 0.18 s; a hand
    over what it is about to click. On a phone, a fingertip shown only around each touch."""
    out = []
    pos = None
    mi = 0
    act = [(b["start"], b["end"]) for b in beats if b["job"] == "action"]
    for i in range(n):
        t = i / fps
        while mi < len(moves) and moves[mi]["t1"] < t:
            pos = moves[mi]["b"]
            mi += 1
        m = moves[mi] if mi < len(moves) else None
        x, y, hand = (pos or [0, 0])[0], (pos or [0, 0])[1], 0
        if m and m["t0"] <= t <= m["t1"]:
            p = ease_move((t - m["t0"]) / max(1e-3, m["t1"] - m["t0"]))
            dx, dy = m["b"][0] - m["a"][0], m["b"][1] - m["a"][1]
            bow = min(60, math.hypot(dx, dy) * 0.12) * math.sin(p * math.pi)
            x, y = m["a"][0] + dx * p, m["a"][1] + dy * p - bow
            hand = 1 if m["hand"] and p > 0.7 else 0
            if pos is None:
                pos = m["a"]
        elif m and t < m["t0"] and pos is None:
            x, y = m["a"]
        elif mi > 0 and moves[mi - 1]["hand"] and t - moves[mi - 1]["t1"] < 0.5:
            hand = 1
        press = max([0.0] + [max(0.0, 1 - abs(t - pt) / 0.09) for pt in presses if pt is not None])
        if touch:
            alpha = max([0.0] + [min(1.0, max(0.0, 1 - (abs(t - pt) - 0.12) / 0.2)) for pt in presses if pt is not None])
        else:
            inside = any(a - 0.05 <= t <= b + 0.3 for a, b in act) and (pos is not None or (m and t >= m["t0"] - 0.3))
            alpha = 1.0 if inside else 0.0
        out.append([round(x, 1), round(y, 1), alpha, round(press, 2), hand])
    # fade the cursor in and out over 0.25 s instead of popping
    a = [c[2] for c in out]
    k = max(1, int(0.25 * fps))
    for i in range(n):
        lo, hi = max(0, i - k), min(n, i + k + 1)
        out[i][2] = round(min(a[i], sum(a[lo:hi]) / (hi - lo)) if a[i] else 0.0, 2) if not touch else round(a[i], 2)
    return out


# ---------------------------------------------------------------- the framing guarantee

def framing(plan, words_box=None):
    """Every frame, from the plan's own camera: the held focus inside the safe frame, never under the words,
    the cursor wholly in frame or not shown, no capture shown bigger than it was taken. [(t, problem, key i)]"""
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    m = SAFE * min(W, H)
    keys = plan["keys"]
    out = []
    S = min(W, H) / 1080 * 1.25
    words = plan.get("words", [])
    wb = words_box or words_rect(W, H)
    for i, (cx, cy, w) in enumerate(plan["cam"]):
        t = i / fps
        k = W / w
        tf = lambda x, y: ((x - cx) * k + W / 2, (y - cy) * k + H / 2)
        if k > plan.get("dsf", 3) * 1.02:
            out.append((t, f"zoomed past the capture ({k:.2f} frame px per page px, the capture has {plan.get('dsf', 3)})", None))
        # the key being held at t (after its arrival, before the next move starts)
        j = max((n for n, kk in enumerate(keys) if kk["t"] <= t), default=None)
        if j is not None and (j + 1 >= len(keys) or t < keys[j + 1]["t"] - keys[j + 1].get("D", 1.5) - 2 * SMOOTH_S):
            F = keys[j]["focus"]
            if t - keys[j]["t"] > 0.25:
                x0, y0 = tf(F[0], F[1])
                x1, y1 = tf(F[0] + F[2], F[1] + F[3])
                if x0 < m - 1 or y0 < m - 1 or x1 > W - m + 1 or y1 > H - m + 1:
                    out.append((t, f"the focus [{F[0]:.0f}, {F[1]:.0f}, {F[2]:.0f}, {F[3]:.0f}] leaves the safe frame "
                                   f"({x0:.0f}, {y0:.0f})-({x1:.0f}, {y1:.0f})", j))
                if any(wd["start"] + 0.3 <= t <= wd["end"] for wd in words):
                    ov = max(0, min(x1, wb[0] + wb[2]) - max(x0, wb[0])) * max(0, min(y1, wb[1] + wb[3]) - max(y0, wb[1]))
                    if ov > 0.04 * max(1, (x1 - x0) * (y1 - y0)):
                        out.append((t, "the words sit over the focus", j))
        c = plan["cursor"][i]
        if c[2] > 0.05:
            x, y = tf(c[0], c[1])
            cw, ch = (44 * S, 44 * S) if plan.get("touch") else (28 * S, 40 * S)
            x0, y0 = (x - cw / 2, y - ch / 2) if plan.get("touch") else (x - 3 * S, y - 2 * S)
            if x0 < 0 or y0 < 0 or x0 + cw > W or y0 + ch > H:
                out.append((t, f"the cursor is cut by the frame edge at ({x:.0f}, {y:.0f})", j))
    return out


def words_rect(W, H):
    """Where the words sit (kit.tsx wordsBox, low-left): the block a line of words can cover."""
    vertical = H > W * 1.2
    y = H * (0.7 if vertical else 0.64)
    h = H * (0.22 if vertical else 0.28)
    return [W * 0.07, y + h * 0.35, W * 0.6, h * 0.65]


def replan(plan, rounds=6):
    """Fix framing failures at their root, the key's framing: widen it (up to the page) and re-centre on its
    focus, then rebuild the camera. Returns the problems left."""
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    for _ in range(rounds):
        bad = framing(plan)
        idx = sorted({j for _, _, j in bad if j is not None})
        if not bad or not idx:
            return bad
        for j in idx:
            k = plan["keys"][j]
            cx, cy, w = k["cam"]
            F = k["focus"]
            w2 = min(w * 1.12, k.get("wmax", w * 1.12))
            h2 = w2 * H / W
            fx, fy = F[0] + F[2] / 2, F[1] + F[3] / 2
            # move the centre toward the focus so it sits inside, then keep words below it
            cx = fx if F[2] > w2 * 0.8 else min(max(cx, F[0] + F[2] - w2 / 2 + w2 * 0.06), F[0] + w2 / 2 - w2 * 0.06)
            cy = fy + (h2 * 0.17 if k.get("words") else 0) if F[3] > h2 * 0.5 else min(max(cy, F[1] + F[3] - h2 / 2 + h2 * 0.08 + (h2 * 0.3 if k.get("words") else 0)), F[1] + h2 / 2 - h2 * 0.08)
            k["cam"] = [cx, cy, w2]
        cam, _ = camera(plan["keys"], plan["durationInFrames"], fps, W, H, plan.get("wmin", 0))
        plan["cam"] = [[round(x, 2) for x in c] for c in cam]
        if plan.get("cursor_raw"):
            plan["cursor"] = [list(c) for c in plan["cursor_raw"]]
            gate_cursor(plan["cursor"], plan["cam"], W, H, fps, plan.get("touch"))
    return framing(plan)


def stills_at(plan):
    """Start, middle and end of every beat (the animatic), frame numbers."""
    out = {}
    fps, n = plan["fps"], plan["durationInFrames"]
    for i, b in enumerate(plan["beats"]):
        for tag, t in (("a", b["start"] + 0.35), ("b", (b["start"] + b["end"]) / 2), ("c", b["end"] - 0.2)):
            out[f"{i + 1:02d}-{b['job']}-{tag}"] = min(n - 1, max(0, round(t * fps)))
    return out


# ---------------------------------------------------------------- checks on the render

def content_fill(img):
    """Share of the frame that is product detail: 24 px blocks (at 960 px) with edges in them, grown by a
    block. Flat ground counts as nothing, whatever its colour: an empty dark panel is not product."""
    import cv2
    import numpy as np
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    h, w = g.shape
    s = 960 / max(h, w)
    g = cv2.resize(g, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    e = cv2.Canny(g, 30, 90) > 0
    bs = 24
    H2, W2 = (g.shape[0] // bs) * bs, (g.shape[1] // bs) * bs
    blk = e[:H2, :W2].reshape(H2 // bs, bs, W2 // bs, bs).mean(axis=(1, 3)) > 0.015
    return float((cv2.dilate(blk.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0).mean())


def ocr():
    """fn(bgr) -> text, or None: Apple Vision (ocrmac) on a Mac, else RapidOCR."""
    try:
        from ocrmac import ocrmac
        from PIL import Image
        return lambda im: " ".join(t for t, c, _ in ocrmac.OCR(Image.fromarray(im[:, :, ::-1]), recognition_level="accurate").recognize() if c >= 0.3)
    except ImportError:
        pass
    try:
        from rapidocr_onnxruntime import RapidOCR
        eng = RapidOCR()
        return lambda im: " ".join(t for _, t, _ in (eng(im)[0] or []))
    except ImportError:
        return None


def runs(ts, gap=0.2):
    """[(t0, t1)] spans of the times, joined when closer than gap."""
    out = []
    for t in sorted(ts):
        if out and t - out[-1][1] <= gap:
            out[-1][1] = t
        else:
            out.append([t, t])
    return out


def check_render(d, plan, video):
    """[(level, what, fix)]: the framing from the camera path (every frame), then on the rendered frames:
    the held focus found where the plan put it (template match), the product filling the frame (edges, not
    colour), no logged-in name readable (OCR), and the smoothness meter against the reference films."""
    import cv2
    import numpy as np
    import subprocess
    d = Path(d)
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    out = []
    bad = framing(plan)
    for a, b in runs([t for t, _, _ in bad], 1 / fps * 1.5):
        what = next(w for t, w, _ in bad if a <= t <= b)
        out.append(("FAIL", f"framing {a:.2f}-{b:.2f} s: {what}", "product.py plan re-plans the camera; widen the beat or give it fewer words"))
    # frames at 2 a second, at half size
    w2, h2 = W // 2, H // 2
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=2,scale={w2}:{h2}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    frames = np.frombuffer(raw, np.uint8).reshape(-1, h2, w2, 3)
    end = plan.get("end", 1e9)
    thin = []
    for i, f in enumerate(frames):
        t = i / 2
        if t < 0.5 or t > end - 0.3:
            continue
        c = content_fill(f)
        if c < 0.35:
            thin.append((t, c))
    def moving(t):    # the camera travelling faster than a fifth of the frame a second
        i = min(len(plan["cam"]) - 2, round(t * fps))
        a, b = plan["cam"][i], plan["cam"][i + 1]
        return (math.hypot(b[0] - a[0], b[1] - a[1]) / a[2] + abs(math.log(b[2] / a[2]))) * fps > 0.2
    for a, b in runs([t for t, _ in thin], 0.6):
        lo = min(c for t, c in thin if a <= t <= b)
        held = [t for t, _ in thin if a <= t <= b and not moving(t)]
        out.append(("FAIL" if held else "WARN", f"{a:.1f}-{b:.1f} s: the product fills only {lo:.0%} of the frame (edges, not colour; flat panels count as empty)"
                    + ("" if held else ", while the camera travels"), "frame the content box, not the page"))
    # the held focus, found by template match where the plan put it
    m = SAFE * min(W, H) / 2
    keys = plan["keys"]
    layers = plan["canvas"]["layers"]
    miss = 0
    for j, k in enumerate(keys):
        t1 = keys[j + 1]["t"] - keys[j + 1].get("D", 1.5) - 2 * SMOOTH_S if j + 1 < len(keys) else end - 0.3
        t = (k["t"] + 0.3 + t1) / 2
        if t1 - k["t"] < 0.6 or t >= end:
            continue
        F = k["focus"]
        L = next((L for L in reversed(layers) if L["t"] + L["dur"] <= t and L["x"] <= F[0] and L["y"] <= F[1]
                  and L["x"] + L["w"] >= F[0] + F[2] and L["y"] + L["h"] >= F[1] + F[3]), None)
        if not L or F[2] < 20 or F[3] < 12:
            continue
        fi = min(len(plan["cam"]) - 1, round(t * fps))
        cx, cy, cw = plan["cam"][fi]
        kk = W / cw / 2                          # half-size frames
        from PIL import Image
        with Image.open(d / L["src"]) as im:
            sc = im.size[0] / L["w"]
            box = [(F[0] - L["x"]) * sc, (F[1] - L["y"]) * sc, (F[0] - L["x"] + F[2]) * sc, (F[1] - L["y"] + F[3]) * sc]
            tw, th = max(8, int(F[2] * kk)), max(8, int(F[3] * kk))
            tpl = np.asarray(im.convert("L").crop([int(v) for v in box]).resize((tw, th), Image.LANCZOS))
        fr = cv2.cvtColor(np.ascontiguousarray(frames[min(len(frames) - 1, int(round(t * 2)))]), cv2.COLOR_BGR2GRAY)
        if tpl.shape[0] >= fr.shape[0] or tpl.shape[1] >= fr.shape[1] or tpl.std() < 6:
            continue
        res = cv2.matchTemplate(fr, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, (x, y) = cv2.minMaxLoc(res)
        px, py = (F[0] - cx) * kk + w2 / 2, (F[1] - cy) * kk + h2 / 2
        if score < 0.5:
            miss += 1
            out.append(("WARN", f"{t:.1f} s: the held focus was not found in the frame (match {score:.2f})", "look at this frame"))
        elif x < m - 2 or y < m - 2 or x + tw > w2 - m + 2 or y + th > h2 - m + 2:
            out.append(("FAIL", f"{t:.1f} s: the focus is drawn at ({x * 2}, {y * 2}) and runs past the safe frame", "re-plan the camera"))
        elif abs(x - px) > 12 or abs(y - py) > 12:
            out.append(("WARN", f"{t:.1f} s: the focus is drawn {abs(x - px) * 2:.0f}, {abs(y - py) * 2:.0f} px from where the plan put it", "the renderer and journey.py disagree"))
    # names: the logged-in account's own name or handle, readable anywhere
    who = d / "flows" / "whoami.json"
    toks = [x.lower() for x in json.loads(who.read_text()).get("tokens", []) if len(x) >= 4] if who.exists() else []
    read = ocr() if toks else None
    if toks and not read:
        out.append(("WARN", "no OCR engine (ocrmac or rapidocr): the name check did not run", "setup installs one"))
    elif read:
        seen = []
        full = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=1,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                              capture_output=True).stdout
        big = np.frombuffer(full, np.uint8).reshape(-1, H, W, 3)
        for i, f in enumerate(big):
            txt = read(np.ascontiguousarray(f)).lower()
            if any(tk in txt for tk in toks):
                seen.append(i)
        for i in seen:
            out.append(("FAIL", f"{i} s: the logged-in account's name or handle is readable", "record again (record.mjs blurs it from flows/whoami.json)"))
    # smoothness, against the reference films (references/style.md "Smoothness")
    import meter
    r = meter.measure(str(video))
    msg = (f"meter: judder {r['judder_per_10s']}/10 s, dead stops {r['stops_per_10s']}/10 s, jerk p95 {r['jerk_p95']}, "
           f"speed {r['speed_median']} %/s, cuts {r['cuts_per_10s']}/10 s, carry {r['carry_moving_cuts']}")
    lvl = "WARN" if r["judder_per_10s"] > 0.2 or r["stops_per_10s"] > 0.5 or r["jerk_p95"] > 3000 else "INFO"
    out.append((lvl, msg, "the bar: Linear's films, judder 0, stops under 0.5/10 s, jerk p95 under 3000" if lvl == "WARN" else ""))
    return out


def demo():
    f = bezier(*MOVE)
    assert f(0) == 0 and f(1) == 1 and f(0.25) < f(0.5) < f(0.75) and max((f((i + 1) / 100) - f(i / 100)) * 100 for i in range(100)) < 2.2
    plate = {"x": 0, "y": 0, "w": 1440, "h": 900}
    cam = fit([600, 100, 200, 40], plate, (1920, 1080), words=True, wmin=640)
    assert cam[2] >= 640, cam
    keys = [{"t": 0, "cam": [720, 450, 1500], "focus": [0, 0, 1440, 900], "words": False},
            {"t": 2, "cam": cam, "focus": [600, 100, 200, 40], "words": True},
            {"t": 5, "cam": [720, 450, 1500], "focus": [0, 0, 1440, 900], "words": False}]
    c, _ = camera(keys, 6 * 60, 60, 1920, 1080)
    import numpy as np
    w = np.log(np.array(c)[:, 2])
    acc = np.abs(np.diff(w, 2))
    assert acc.max() < 0.002, acc.max()          # no snaps: the zoom's acceleration stays small every frame
    sp = np.abs(np.diff(w))
    assert sp[100:130].max() > 0 and min(sp[60:300]) >= 0     # moving through the move
    plan = {"width": 1920, "height": 1080, "fps": 60, "dsf": 3, "keys": keys, "cam": c, "words": [],
            "cursor": [[0, 0, 0, 0, 0]] * len(c), "durationInFrames": len(c)}
    plan["keys"][1]["cam"] = [200, 100, 700]            # a framing that cuts the focus off
    plan["cam"], _ = camera(plan["keys"], len(c), 60, 1920, 1080)
    assert framing(plan), "a cut-off focus must fail"
    assert not replan(plan), framing(plan)[:3]
    print("demo ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
