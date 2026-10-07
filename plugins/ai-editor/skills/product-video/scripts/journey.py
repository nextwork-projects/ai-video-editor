#!/usr/bin/env python3
"""The rendered product film: UI states (record.mjs --states) laid out on one canvas, one camera moving
through them, every frame drawn by Remotion (nothing recorded plays back).

    product.py plan DIR --story story-v4.json ...   (a story with "beats" comes here)
    python3 journey.py demo                          self-check, no network

A story is beats, in the order the film tells them (references/story.md "Story first"):
    {"beats": [{"job": "hook", "flow": "search", "text": "<the promise, in the site's words>"},
               {"job": "action", "flow": "search", "steps": [0, 1], "text": "<the search box's own label>"},
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
SECONDS_PER_USE_CASE = 8   # default length: about 40 s for five use cases (action + result), the hook, payoff and end included
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


def text_lines(d, s):
    """A state's text line boxes, state px: the DOM's own (record.mjs, Range.getClientRects), plus OCR inside the
    pictures it shows (their text is pixels). A state recorded before record.mjs took them is read by OCR whole.
    The OCR part is cached beside the still as <src>.lines.json."""
    d = Path(d)
    if "lines" in s and not s.get("images"):
        return [list(r) for r in s["lines"]]
    cache = d / (str(Path(s["src"]).with_suffix("")) + ".lines.json")
    if cache.exists() and cache.stat().st_mtime >= (d / s["src"]).stat().st_mtime:
        return list(s.get("lines", [])) + json.loads(cache.read_text())
    read = ocr_boxes()
    if not read:
        return list(s.get("lines", []))
    from PIL import Image
    out = []
    W, H = s["size"]
    with Image.open(d / s["src"]) as im:
        im = im.convert("RGB")
        k = im.size[0] / W
        for a in (s["images"] if "lines" in s else [[0, 0, W, H]]):
            x0, y0, x1, y1 = max(0, a[0]), max(0, a[1]), min(W, a[0] + a[2]), min(H, a[1] + a[3])
            if x1 - x0 < 20 or y1 - y0 < 10:
                continue
            for _, (x, y, w, h) in read(im.crop([int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)])):
                out.append([round(x0 + x * (x1 - x0), 1), round(y0 + y * (y1 - y0), 1), round(w * (x1 - x0), 1), round(h * (y1 - y0), 1)])
    cache.write_text(json.dumps(out))
    return list(s.get("lines", [])) + out


def union(*rs):
    rs = [r for r in rs if r]
    x0, y0 = min(r[0] for r in rs), min(r[1] for r in rs)
    x1, y1 = max(r[0] + r[2] for r in rs), max(r[1] + r[3] for r in rs)
    return [x0, y0, x1 - x0, y1 - y0]


def build(d, story, aspect="16:9", fps=60, variant="linear", pace=1.0):
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
    # a flow whose first beat begins far down its page (the hand's target was scrolled into view from the top)
    # starts there: the page's top is not part of the story, and the camera would otherwise fall thousands of
    # px down it in a second
    for fid, f in flows.items():
        b0 = next((b for b in beats if b.get("flow") == fid), None)
        if not b0 or b0["job"] in ("hook", "reveal") or not b0.get("steps"):
            continue
        si = f["real"][b0["steps"][0]]
        autos = []
        for ai in range(si - 1, -1, -1):
            if not f["steps"][ai].get("auto"):
                break
            autos.append(f["steps"][ai])
        if autos and autos[-1]["from"] == 0 and sum(abs(a.get("dy", 0)) for a in autos) > 0.8 * f["viewport"][1]:
            f["_start"] = autos[0]["to"]
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
            # a phone page is framed with a sliver of ground each side: the gap keeps the next page out of it
            x = plates[-1]["x"] + plates[-1]["w"] * (1 + (0.3 if vertical else GAP)) if plates else 0
            y = plates[-1]["endy"] if plates else 0
            if pi == 0 and f.get("_start"):
                y -= f["states"][f["_start"]]["y"]       # level with where the flow starts, not with its page's top
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
        # the text this layer puts on the canvas (canvas px): a region reveal only what lands inside its region
        reg = (kw.get("weak") or kw.get("rect")) if kind in ("pop", "sweep", "modal") else [r[0], r[1], r[2], r[3]]
        lines = [[r[0] + a[0], r[1] + a[1], a[2], a[3]] for a in text_lines(d, flows[fid]["states"][state])] if kind != "type" else []
        L["lines"] = [[round(v) for v in a] for a in lines if reg and reg[0] <= a[0] + a[2] / 2 <= reg[0] + reg[2] and reg[1] <= a[1] + a[3] / 2 <= reg[1] + reg[3]]
        layers.append(L)
        return L

    wend = [-1.0]       # when this beat's words leave

    def key(t0, T, plate, words_on, focus=None, wide=False):
        words_on = bool(words_on) and t0 - 1.2 <= wend[0]     # a framing held after the words have gone needs no room for them
        if words_on and T[3] * 1.2 / (0.6 if H > W else 0.55) * W / H > plate["w"] * 1.12:
            # too tall to sit above the words at a readable size: the words leave before the camera gets there
            wend[0] = min(wend[0], t0 - 1.3)
            words_on = False
        # never closer than ~60% of a desktop page (85% of a phone page): the page keeps its context, and the
        # camera never has to zoom 2.5x in a second to get there
        floor = max(wmin, plate["w"] * (0.84 if vertical else 0.6))
        cam = fit(T, plate, (W, H), words_on, floor, pad=1.06 if wide else 1.2)
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
            end_len = 3.4 if pace >= 0.9 else 3.0
            out_beats.append({"job": "end", "start": round(t, 3), "end": round(t + end_len, 3)})
            cues += [{"t": round(t, 3), "kind": "swell"}, {"t": round(t + 0.05, 3), "kind": "hit"}]
            t += end_len
            break
        f = flows[b["flow"]]
        fid = b["flow"]
        # the flow's first state, the first time it is shown
        if fid not in shown:
            shown.add(fid)
            p, r = at(fid, f.get("_start", 0))
            fresh = not any(L["plate"] == plates.index(p) for L in layers)
            layer(fid, f.get("_start", 0), t, "base" if not layers else ("plate-in" if fresh else "fade"), 0.0 if not layers else 0.6)
            if layers[-1]["kind"] == "plate-in":
                cues.append({"t": round(t, 3), "kind": "whoosh"})
                t += 1.0          # the camera's travel to a new page takes its time (never paced down: smooth first)
        steps = [f["real"][i] for i in b.get("steps", [])]
        panel = f.get("_open_panel")
        if job in ("hook", "reveal"):
            p, vr = view_rect(fid, 0)
            dur = max(1.8, 1.0 + 0.3 * len((text or "").split()), b.get("dur", 3.0) * pace)
            # wide on the whole page, pushing in to where the next beat acts
            top = [vr[0] + vr[2] * 0.06, vr[1] + vr[3] * 0.03, vr[2] * 0.88, vr[3] * 0.5]
            if f.get("headline"):      # the page's own headline, whole: the hook never crops it
                hl = f["headline"]
                top = [vr[0] + hl[0], vr[1] + hl[1], hl[2], hl[3]]
            w0 = p["w"] * (1.06 if vertical else 1.12)
            if f.get("headline"):
                c0 = fit(top, p, (W, H), bool(text), wmin, pad=1.15)
                c0[2] = max(c0[2], min(w0, c0[2] * 1.15))
            keys.append({"t": round(t, 3), "cam": c0 if f.get("headline") else [vr[0] + vr[2] / 2, top[1] + top[3] / 2 + w0 * H / W * 0.17 if text else vr[1] + vr[3] / 2, w0],
                         "focus": top, "words": bool(text), "wide": True, "wmax": p["w"] * (1.06 if vertical else 1.3)})
            nxt = next((bb for bb in beats[bi + 1:] if bb.get("steps")), None)
            if nxt and nxt["flow"] == fid:
                s0 = f["steps"][f["real"][nxt["steps"][0]]]
                T = union(s0.get("rect") and [vr[0] + s0["rect"][0], vr[1] + s0["rect"][1], s0["rect"][2], s0["rect"][3]], [vr[0] + vr[2] * 0.02, vr[1], vr[2] * 0.96, vr[3] * 0.4])
                key(t + dur, T, p, bool(text))
            t += dur
        # ---- the steps this beat performs (an action with words lets them land first: words, then the hand)
        if job == "action" and text and steps:
            t += 0.8 * max(0.6, pace)
        for si in steps:
            s = f["steps"][si]
            # auto scrolls (a target scrolled into view) just before this step
            for ai in range(si - 1, -1, -1):
                if not f["steps"][ai].get("auto"):
                    break
                a = f["steps"][ai]
                if a["to"] == f.get("_start"):
                    break                 # the flow already starts here
                layer(fid, a["to"], t, "fade", 0.35)
                t += 0.4
            kind = s["kind"]
            p, vr = view_rect(fid, s["from"])
            if kind == "write" and s.get("caret"):
                # typed into what already has focus (after a shortcut or a button): no hand, the text appears
                c = s["caret"]
                lines = max(x[1] for x in c["pos"]) + 1
                T = union([p["x"] + s["rect"][0], p["y"] + s["rect"][1], s["rect"][2], s["rect"][3]],
                          [p["x"] + c["left"], p["y"] + c["top"], max(x[0] for x in c["pos"]) + 12, lines * c["lh"]])
                if panel:
                    T = union(T, panel)
                key(t + 0.5, T, p, bool(text))
                layer(fid, s["empty"], t + 0.3, "fade", 0.18)
                t0 = t + 0.6
                n = len(s["text"])
                layer(fid, s["to"], t0, "type", n / CPS, caret={**c, "top": c["top"] + p["y"]}, cps=CPS, n=n)
                cues += [{"t": round(t0 + j / CPS, 3), "kind": "tick"} for j in range(0, n, 2)]
                s["_focus"] = T
                t = t0 + n / CPS + 0.45
                continue
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
                t_click = t + max(1.25 * max(0.75, pace), mv + 0.5 * max(0.6, pace))      # the camera settles, then the hand clicks
                # the camera frames what the hand acts on; the hand fades in once it is wholly in frame (gate_cursor)
                key(t_click - 0.45 * max(0.6, pace), T, p, bool(text), focus=T)
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
                dur = min(3.0, max(1.4, abs(s["dy"]) / 800))     # a reading pace down the page, never paced down
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
            t += max(b.get("dur", 2.4) * pace, 1.4, 1.2 + 0.3 * len((text or "").split()) if text else 0)   # a result is held long enough to read
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
            dur = max(2.0, b.get("dur", 3.2) * pace)
            keys.append({"t": round(t + dur, 3), "cam": [p["x"] + p["w"] / 2, fr[1] + fr[3] / 2, min(p["w"] * 1.1, max(wmin, p["w"] * (1.06 if vertical else 1.1)))],
                         "focus": fr, "words": bool(text), "wide": True, "wmax": p["w"] * (1.06 if vertical else 1.3)})
            t += dur
        elif job == "action":
            t += 0.35 * pace
        if text:
            # the words open the beat and leave before the hand is busy: the UI carries the rest
            if wend[0] - start > 1.2:
                words.append({"text": text, "start": round(start + 0.15, 3), "end": round(min(t, wend[0]), 3)})
        out_beats.append({"job": job, "start": round(start, 3), "end": round(t, 3), "text": text, "flow": fid})
    total = t
    who = d / "flows" / "whoami.json"
    toks = [x.lower() for x in json.loads(who.read_text()).get("tokens", []) if len(x) >= 4] if who.exists() else []
    from PIL import Image
    for L in layers:
        L["src"] = redact(d, L["src"], toks)
        with Image.open(d / L["src"]) as im:
            L["res"] = round(im.size[0] / L["w"], 3)      # picture px per page px: the most it can be magnified
    n = int(round(total * fps))
    fill_guard(d, keys, layers, plates, W, H, wmin)
    fcache = {}

    def fill_at(k, cam):
        F = k["focus"]
        pi = next((i for i, p in enumerate(plates) if p["x"] <= F[0] + F[2] / 2 <= p["x"] + p["w"] and p["y"] <= F[1] + F[3] / 2 <= p["y"] + p["h"]), None)
        return 1.0 if pi is None else fill_of(fill_cells(d, layers, pi, plates[pi], k["t"], fcache), plates[pi], cam, W, H)
    text_guard(keys, layers, W, H, wmin, fill=fill_at)
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

FILL_AIM = 0.5     # a held framing whose estimated product fill is under this is re-framed tighter (check FAILs under 0.35)
BLOCK = 24         # page px a fill cell covers (content_fill's 24 px blocks at about 1 frame px per page px)


def fill_cells(d, layers, pi, plate, t, cache):
    """The plate as it looks at time t, as cells of BLOCK page px: 1 where there is UI detail (edges), 0 on flat
    ground of any colour, grown by a cell, the same way content_fill reads a rendered frame. Returns its integral."""
    import cv2
    import numpy as np
    from PIL import Image
    shown = [L for L in layers if L["plate"] == pi and L["t"] <= t and L["kind"] in ("base", "fade", "plate-in", "type", "sweep", "pop", "modal")]
    key = (pi, tuple(L["src"] for L in shown))
    if key in cache:
        return cache[key]
    gw, gh = int(math.ceil(plate["w"] / BLOCK)), int(math.ceil(plate["h"] / BLOCK))
    cells = np.zeros((gh, gw), np.float32)
    for L in shown:
        with Image.open(Path(d) / L["src"]) as im:
            g = np.asarray(im.convert("L").resize((max(1, int(L["w"] / 2)), max(1, int(L["h"] / 2))), Image.BILINEAR))
        e = cv2.Canny(g, 30, 90) > 0
        bs = BLOCK // 2
        hh, ww = (e.shape[0] // bs) * bs, (e.shape[1] // bs) * bs
        blk = (e[:hh, :ww].reshape(hh // bs, bs, ww // bs, bs).mean(axis=(1, 3)) > 0.015).astype(np.float32)
        x0, y0 = int(round((L["x"] - plate["x"]) / BLOCK)), int(round((L["y"] - plate["y"]) / BLOCK))
        bh, bw = min(blk.shape[0], gh - y0), min(blk.shape[1], gw - x0)
        if bh > 0 and bw > 0 and x0 >= 0 and y0 >= 0:
            cells[y0:y0 + bh, x0:x0 + bw] = blk[:bh, :bw]    # a later full state replaces what was there
    cells = (cv2.dilate(cells, np.ones((3, 3), np.uint8)) > 0).astype(np.float64)
    ii = np.pad(cells.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    cache[key] = ii
    return ii


def fill_of(ii, plate, cam, W, H):
    """Estimated share of the frame that is UI detail for camera (cx, cy, w); off the plate counts as empty."""
    cx, cy, w = cam
    h = w * H / W
    gh, gw = ii.shape[0] - 1, ii.shape[1] - 1
    x0, x1 = (cx - w / 2 - plate["x"]) / BLOCK, (cx + w / 2 - plate["x"]) / BLOCK
    y0, y1 = (cy - h / 2 - plate["y"]) / BLOCK, (cy + h / 2 - plate["y"]) / BLOCK
    a, b = int(max(0, min(gw, round(x0)))), int(max(0, min(gw, round(x1))))
    c, e = int(max(0, min(gh, round(y0)))), int(max(0, min(gh, round(y1))))
    if b <= a or e <= c:
        return 0.0
    return float(ii[e, b] - ii[c, b] - ii[e, a] + ii[c, a]) / max(1.0, (x1 - x0) * (y1 - y0))


def fill_guard(d, keys, layers, plates, W, H, wmin):
    """Sparse pages (a dark site's big headline on empty ground): every framing whose estimated product fill is
    under FILL_AIM is re-framed on the detected content, tighter (never past 1:1 on the capture) and slid toward
    the busy part, keeping its focus whole inside the safe frame and above the words. Records "fill" on each key."""
    import numpy as np
    cache = {}
    for k in keys:
        cx, cy, w = k["cam"]
        F = k["focus"]
        pi = next((i for i, p in enumerate(plates) if p["x"] <= F[0] + F[2] / 2 <= p["x"] + p["w"] and p["y"] <= F[1] + F[3] / 2 <= p["y"] + p["h"]), None)
        if pi is None:
            continue
        plate = plates[pi]
        ii = fill_cells(d, layers, pi, plate, k["t"], cache)
        f0 = fill_of(ii, plate, k["cam"], W, H)
        k["fill"] = round(f0, 2)
        if f0 >= FILL_AIM:
            continue
        best, score0 = None, f0
        lo = max(wmin * 1.02, F[2] * 1.12, F[3] * 1.12 * W / H / (0.55 if k.get("words") else 0.88))
        for w2 in np.geomspace(w, max(lo, w * 0.45), 9) if lo < w else [w]:
            h2 = w2 * H / W
            m = SAFE * min(W, H) * w2 / W * 1.4
            band = 0.55 if k.get("words") else 1.0       # the focus sits in the top part when words are on
            xs = (F[0] + F[2] + m - w2 / 2, F[0] - m + w2 / 2)
            ys = (F[1] + F[3] + m + h2 / 2 - h2 * band, F[1] - m + h2 / 2)
            if xs[0] > xs[1] or ys[0] > ys[1]:
                continue
            for x in np.linspace(*xs, 9):
                for y in np.linspace(*ys, 9):
                    f = fill_of(ii, plate, (x, y, w2), W, H)
                    sc = f - 0.08 * abs(math.log(w2 / w)) - 0.05 * math.hypot(x - cx, y - cy) / w
                    if sc > score0 + 0.06:
                        best, score0 = ((float(x), float(y), float(w2)), f), sc
        if best:
            k["cam"], k["fill"] = [round(float(v), 2) for v in best[0]], round(float(best[1]), 2)


# ---------------------------------------------------------------- text whole or out

TEXT_M = 6          # frame px: a line kept in frame sits at least this far inside the edge
FADE_MAX = 0.12     # the edge fade, at most this share of the short side: a short fade, never a vignette


def shown_lines(layers, t, cache):
    """The text lines on the canvas at time t, as an (n, 5) array x0, y0, x1, y1, plate: each layer's lines, less
    an earlier layer's lines on the same plate under its region (a new state replaces what it covers)."""
    import numpy as np
    idx = tuple(i for i, L in enumerate(layers) if L["t"] <= t)
    if idx in cache:
        return cache[idx]
    vis = np.zeros((0, 5))
    for i in idx:
        L = layers[i]
        if L["kind"] == "type":
            continue
        R = (L.get("weak") or L.get("rect")) if L["kind"] in ("pop", "sweep", "modal") else [L["x"], L["y"], L["w"], L["h"]]
        if R and len(vis):
            cx, cy = (vis[:, 0] + vis[:, 2]) / 2, (vis[:, 1] + vis[:, 3]) / 2
            vis = vis[~((vis[:, 4] == L["plate"]) & (cx >= R[0]) & (cx <= R[0] + R[2]) & (cy >= R[1]) & (cy <= R[1] + R[3]))]
        ln = L.get("lines") or []
        if ln:
            a = np.array(ln, float)
            vis = np.vstack([vis, np.column_stack([a[:, 0], a[:, 1], a[:, 0] + a[:, 2], a[:, 1] + a[:, 3], np.full(len(a), L["plate"])])])
    cache[idx] = vis
    return vis


def cut_by(lines, cam, W, H):
    """Which lines (shown_lines rows) the frame of camera (cx, cy, w) cuts: in it but not wholly inside, TEXT_M
    in from the edge. A line overlapping the frame by under 2 frame px is out."""
    cx, cy, w = cam
    h, k = w * H / W, W / w
    fx0, fy0, fx1, fy1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    m, e = TEXT_M / k, 2 / k
    x0, y0, x1, y1 = lines[:, 0], lines[:, 1], lines[:, 2], lines[:, 3]
    inter = (x0 < fx1 - e) & (x1 > fx0 + e) & (y0 < fy1 - e) & (y1 > fy0 + e)
    inside = (x0 >= fx0 + m) & (x1 <= fx1 - m) & (y0 >= fy0 + m) & (y1 <= fy1 - m)
    return inter & ~inside


def on_focus(lines, F):
    """Lines that are part of the focus: a quarter or more of the line inside it."""
    ox = (lines[:, 2].clip(None, F[0] + F[2]) - lines[:, 0].clip(F[0])).clip(0)
    oy = (lines[:, 3].clip(None, F[1] + F[3]) - lines[:, 1].clip(F[1])).clip(0)
    return ox * oy >= 0.25 * (lines[:, 2] - lines[:, 0]) * (lines[:, 3] - lines[:, 1])


def focus_ok(F, cam, W, H, words):
    """The focus wholly inside the safe frame, and clear of the words when they are up (framing's own test)."""
    cx, cy, w = cam
    k = W / w
    m = SAFE * min(W, H)
    x0, y0 = (F[0] - cx) * k + W / 2, (F[1] - cy) * k + H / 2
    x1, y1 = x0 + F[2] * k, y0 + F[3] * k
    if x0 < m - 1 or y0 < m - 1 or x1 > W - m + 1 or y1 > H - m + 1:
        return False
    if words:
        wb = words_rect(W, H)
        ov = max(0, min(x1, wb[0] + wb[2]) - max(x0, wb[0])) * max(0, min(y1, wb[1] + wb[3]) - max(y0, wb[1]))
        return ov <= 0.04 * max(1, (x1 - x0) * (y1 - y0))
    return True


def text_guard(keys, layers, W, H, wmin, only=None, fill=None):
    """Every held framing shows each line of text whole or not at all. The focus first grows to the whole of
    the lines it holds part of (when that still fits), then the camera shifts (up to a quarter of the frame) or
    widens (up to the key's wmax, never past 1:1 on the capture) to the nearest framing that cuts the fewest
    lines, the focus kept whole in the safe frame and, given fill(key, cam), the product filling as much of the
    frame as before (dropping a line by framing empty ground beside it is no fix). Checked at the hold's start and at the end of its push-in.
    Lines it cannot clear are faded at the edge (edge_fades), never the focus's. Returns the lines still cut."""
    import numpy as np
    cache = {}
    left = 0
    ks = sorted(range(len(keys)), key=lambda i: keys[i]["t"])
    for n, j in enumerate(ks):
        if only is not None and j not in only:
            continue
        k = keys[j]
        nxt = keys[ks[n + 1]] if n + 1 < len(ks) else None
        t1 = max(k["t"], nxt["t"] - nxt.get("D", 1.0)) if nxt else k["t"] + 2.0
        lines = np.vstack([shown_lines(layers, t, cache) for t in (k["t"] + 0.05, t1)])
        if not len(lines):
            continue
        push = math.exp(-HOLD_PUSH * min(t1 - k["t"], 4) / 3)
        wmax = k.get("wmax", k["cam"][2] * 1.3)
        cx, cy, w = k["cam"]
        F = k["focus"]
        hit = on_focus(lines, F)
        if hit.any():
            g = lines[hit]
            F2 = union(F, [float(g[:, 0].min()), float(g[:, 1].min()), float(g[:, 2].max() - g[:, 0].min()), float(g[:, 3].max() - g[:, 1].min())])
        else:
            F2 = F

        def cost(cam, foc):
            c = 0.0
            for ww in (cam[2], cam[2] * push):
                cut = cut_by(lines, (cam[0], cam[1], ww), W, H)
                c += 100 * float((cut & foc).sum()) + float((cut & ~foc).sum())
            return c

        f0 = min(FILL_AIM, fill(k, k["cam"])) if fill else 0
        lost = (lambda cam: 8 * max(0.0, f0 - fill(k, cam))) if fill else (lambda cam: 0.0)
        base = cost(k["cam"], on_focus(lines, F))
        if base == 0 and F2 == F:
            continue
        best = None
        for F_ in ([F2, F] if F2 != F else [F]):
            foc = on_focus(lines, F_)
            for w2 in sorted({w, *np.geomspace(max(wmin, w * 0.88), max(w, wmax), 14)}):
                h2 = w2 * H / W
                for dx in np.linspace(-0.25, 0.25, 21) * w2:
                    for dy in np.linspace(-0.25, 0.25, 21) * h2:
                        cam = (cx + dx, cy + dy, w2)
                        if not focus_ok(F_, (cam[0], cam[1], w2 * push), W, H, k.get("words")) or not focus_ok(F_, cam, W, H, k.get("words")):
                            continue
                        c = cost(cam, foc)
                        sc = c + 3 * math.hypot(dx, dy) / w + 2 * abs(math.log(w2 / w)) + lost(cam)
                        if best is None or sc < best[0]:
                            best = (sc, c, cam, F_)
            if best and best[1] < 100:
                break           # the grown focus fits whole: keep it
        if best and best[1] < base:
            k["cam"] = [round(float(v), 2) for v in best[2]]
            k["focus"] = [round(float(v), 1) for v in best[3]]
            base = best[1]
        k["text_cut"] = int(base)
        left += int(base > 0)
    return left


def holding(cam, i, fps):
    """The camera is holding at frame i: moving under a fifth of the frame a second (check_render's test)."""
    a, b = cam[max(0, min(len(cam) - 2, i))], cam[max(1, min(len(cam) - 1, i + 1))]
    return (math.hypot(b[0] - a[0], b[1] - a[1]) / a[2] + abs(math.log(b[2] / a[2]))) * fps <= 0.2


def held_key(keys, t):
    """The key being held at t (after its arrival, before the next move starts), or None."""
    j = max((n for n, kk in enumerate(keys) if kk["t"] <= t), default=None)
    if j is not None and (j + 1 >= len(keys) or t < keys[j + 1]["t"] - keys[j + 1].get("D", 1.5) - 2 * SMOOTH_S) and t - keys[j]["t"] > 0.25:
        return j
    return None


def edge_fades(plan):
    """Per frame [left, top, right, bottom] frame px: where a held frame still cuts a line that is not part of
    the focus, that edge fades out over a short band (the line's visible part plus 10 px, at most about a word
    of its type at the side edges and FADE_MAX of the short side), eased in and out over 0.25 s. Journey.tsx
    masks the canvas with it: clear for the outer 40% of the band (the cut glyphs), then a ramp."""
    import numpy as np
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    cam, keys, layers = plan["cam"], plan["keys"], plan["canvas"]["layers"]
    n = len(cam)
    out = np.zeros((n, 4))
    cap = FADE_MAX * min(W, H)
    cache = {}
    for i in range(n):
        t = i / fps
        if t >= plan.get("end", 1e9) - 0.15 or not holding(cam, i, fps):
            continue
        lines = shown_lines(layers, t, cache)
        if not len(lines):
            continue
        cut = cut_by(lines, cam[i], W, H)
        j = held_key(keys, t)
        if j is not None:
            cut &= ~on_focus(lines, keys[j]["focus"])
        if not cut.any():
            continue
        cx, cy, w = cam[i]
        h, k = w * H / W, W / w
        fx0, fy0, fx1, fy1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        m = TEXT_M / k
        for x0, y0, x1, y1, _ in lines[cut]:
            word = max(40, 3 * (y1 - y0) * k)          # about a word of this line's type: the cut word goes
            if x0 < fx0 + m:
                out[i, 0] = max(out[i, 0], min(cap, word, (min(x1, fx1) - fx0) * k + 10))
            if x1 > fx1 - m:
                out[i, 2] = max(out[i, 2], min(cap, word, (fx1 - max(x0, fx0)) * k + 10))
            if y0 < fy0 + m:
                out[i, 1] = max(out[i, 1], min(cap, (min(y1, fy1) - fy0) * k + 10))
            if y1 > fy1 - m:
                out[i, 3] = max(out[i, 3], min(cap, (fy1 - max(y0, fy0)) * k + 10))
    # held for 0.25 s either side, then eased: the fade never pops
    r = max(1, int(0.25 * fps))
    for c in range(4):
        col = out[:, c]
        mx = np.array([col[max(0, i - r):i + r + 1].max() for i in range(n)])
        out[:, c] = np.convolve(np.pad(mx, r, mode="edge"), np.ones(2 * r + 1) / (2 * r + 1), mode="valid")
    return [[round(float(v), 1) for v in row] for row in out]


def text_cuts(plan):
    """[(t, problem, key j)] for every held frame where the frame edge cuts a line of text: on the focus it is a
    framing failure; elsewhere it must sit under an edge fade (plan["edge"]) at least as deep as the cut."""
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    keys, layers, cam = plan["keys"], plan["canvas"]["layers"], plan["cam"]
    edge = plan.get("edge")
    out, cache = [], {}
    for i in range(len(cam)):
        t = i / fps
        if t >= plan.get("end", 1e9) - 0.15:
            break
        j = held_key(keys, t)
        if j is None:
            continue
        lines = shown_lines(layers, t, cache)
        if not len(lines):
            continue
        cut = cut_by(lines, cam[i], W, H)
        foc = cut & on_focus(lines, keys[j]["focus"])
        if foc.any():
            out.append((t, f"{int(foc.sum())} line(s) of text on the focus cut by the frame edge", j))
        elif cut.any() and not (edge and any(v > 0 for v in edge[i])):
            out.append((t, f"{int(cut.sum())} line(s) of text cut by the frame edge, not faded", j))
    return out


def framing(plan, words_box=None):
    """Every frame, from the plan's own camera: the held focus inside the safe frame, never under the words,
    the cursor wholly in frame or not shown, no capture shown bigger than it was taken. [(t, problem, key i)]"""
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    m = SAFE * min(W, H)
    keys = plan["keys"]
    out = []
    S = min(W, H) / 1080 * 1.25
    words = plan.get("words", [])
    layers = plan.get("canvas", {}).get("layers", [])
    wb = words_box or words_rect(W, H)
    for i, (cx, cy, w) in enumerate(plan["cam"]):
        t = i / fps
        if t >= plan.get("end", 1e9) - 0.15:
            break          # the canvas is fading into the logo card
        k = W / w
        tf = lambda x, y: ((x - cx) * k + W / 2, (y - cy) * k + H / 2)
        # no picture shown bigger than it was taken: frame px per page px against each visible state's own px
        lim = min((L.get("res", plan.get("dsf", 3)) for L in layers if L["t"] <= t and L["x"] < cx + w / 2 and L["x"] + L["w"] > cx - w / 2
                   and L["y"] < cy + w * H / W / 2 and L["y"] + L["h"] > cy - w * H / W / 2), default=plan.get("dsf", 3))
        if k > lim * 1.02:
            out.append((t, f"a capture shown past 1:1 ({k:.2f} frame px per page px, the picture has {lim:.2f})", None))
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
    if plan.get("canvas", {}).get("layers") and any(L.get("lines") for L in layers):
        out += [p for p in text_cuts(plan) if "on the focus" in p[1]]
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
            break
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
        text_guard(plan["keys"], plan.get("canvas", {}).get("layers", []), W, H, plan.get("wmin", 0), only=set(idx))
        cam, _ = camera(plan["keys"], plan["durationInFrames"], fps, W, H, plan.get("wmin", 0))
        plan["cam"] = [[round(x, 2) for x in c] for c in cam]
        if plan.get("cursor_raw"):
            plan["cursor"] = [list(c) for c in plan["cursor_raw"]]
            gate_cursor(plan["cursor"], plan["cam"], W, H, fps, plan.get("touch"))
    if plan.get("canvas", {}).get("layers"):
        plan["edge"] = edge_fades(plan)
    return framing(plan)


def crop_layers(d, plan, margin=120):
    """Each state cut down to what the camera ever shows of it from its first frame on (plus a margin, for the
    motion blur's look-ahead), so a 3x capture of a tall page is never decoded whole. Writes the cut picture
    beside the state once; the layer keeps its page geometry and gains "crop", the canvas rect the picture
    covers (Journey.tsx Pic). Returns (pixels before, pixels after)."""
    import numpy as np
    from PIL import Image
    d = Path(d)
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    cam = np.array(plan["cam"])
    end = min(len(cam), int((plan.get("end", 1e9) + 0.6) * fps) + 1)
    before = after = 0
    layers = plan["canvas"]["layers"]
    for i, L in enumerate(layers):
        # shown until a later whole-page state on the same plate has finished arriving over it (Journey.tsx Canvas)
        gone = min([M["t"] + M["dur"] for M in layers[i + 1:] if M["plate"] == L["plate"] and M["kind"] in ("base", "fade", "plate-in")
                    and M["x"] <= L["x"] and M["y"] <= L["y"] and M["x"] + M["w"] >= L["x"] + L["w"] and M["y"] + M["h"] >= L["y"] + L["h"]],
                   default=1e9)
        c = cam[max(0, int(L["t"] * fps) - 1):min(end, int(gone * fps) + 2)]
        if not len(c):
            continue
        hw, hh = c[:, 2] / 2 + margin, c[:, 2] * H / W / 2 + margin
        x0, y0 = max(L["x"], float((c[:, 0] - hw).min())), max(L["y"], float((c[:, 1] - hh).min()))
        x1, y1 = min(L["x"] + L["w"], float((c[:, 0] + hw).max())), min(L["y"] + L["h"], float((c[:, 1] + hh).max()))
        with Image.open(d / L["src"]) as im:
            sc = im.size[0] / L["w"]
            before += im.size[0] * im.size[1]
            if x1 <= x0 or y1 <= y0 or (x1 - x0) * (y1 - y0) > 0.85 * L["w"] * L["h"]:
                after += im.size[0] * im.size[1]
                continue
            box = [int((x0 - L["x"]) * sc), int((y0 - L["y"]) * sc), int(math.ceil((x1 - L["x"]) * sc)), int(math.ceil((y1 - L["y"]) * sc))]
            box = [max(0, box[0]), max(0, box[1]), min(im.size[0], box[2]), min(im.size[1], box[3])]
            out = str(Path(L["src"]).with_suffix("")) + f".crop-{box[0]}-{box[1]}-{box[2]}-{box[3]}.jpg"
            if not (d / out).exists():
                im.convert("RGB").crop(box).save(d / out, quality=92)
        after += (box[2] - box[0]) * (box[3] - box[1])
        L["src"] = out
        L["crop"] = [round(L["x"] + box[0] / sc, 2), round(L["y"] + box[1] / sc, 2), round((box[2] - box[0]) / sc, 2), round((box[3] - box[1]) / sc, 2)]
    return before, after


def plan_speed(plan):
    """How busy the camera is, from the plan: (p95, median) of its speed in frame diagonals a second (pan and
    zoom together; the diagonal, so a tall frame and a wide one compare). v4 of the reference project, which
    measured inside the Linear bar, planned at p95 1.28 (16:9) and 0.94 (9:16), medians 0.03-0.07."""
    import numpy as np
    c = np.array(plan["cam"])
    diag = c[:-1, 2] * (1 + (plan["height"] / plan["width"]) ** 2) ** 0.5
    v = (np.hypot(np.diff(c[:, 0]), np.diff(c[:, 1])) / diag + np.abs(np.diff(np.log(c[:, 2])))) * plan["fps"]
    return float(np.percentile(v, 95)), float(np.median(v))


SPEED_BAR = (1.3, 0.22)


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
        box_of = lambda L: L.get("crop") or [L["x"], L["y"], L["w"], L["h"]]
        L = next((L for L in reversed(layers) if L["t"] + L["dur"] <= t and box_of(L)[0] <= F[0] and box_of(L)[1] <= F[1]
                  and box_of(L)[0] + box_of(L)[2] >= F[0] + F[2] and box_of(L)[1] + box_of(L)[3] >= F[1] + F[3]), None)
        if not L or F[2] < 20 or F[3] < 12:
            continue
        fi = min(len(plan["cam"]) - 1, round(t * fps))
        cx, cy, cw = plan["cam"][fi]
        kk = W / cw / 2                          # half-size frames
        from PIL import Image
        with Image.open(d / L["src"]) as im:
            C = box_of(L)
            sc = im.size[0] / C[2]
            box = [(F[0] - C[0]) * sc, (F[1] - C[1]) * sc, (F[0] - C[0] + F[2]) * sc, (F[1] - C[1] + F[3]) * sc]
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
    # text cut by the frame edge, read off the render: OCR at 2 fps, full size, on held frames
    read = ocr_boxes()
    if not read:
        out.append(("WARN", "no OCR engine (ocrmac or rapidocr): the cut-text check did not run", "setup installs one"))
    else:
        from PIL import Image
        hits = []
        proc = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=2,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                stdout=subprocess.PIPE)
        i = -1
        while True:
            buf = proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            i += 1
            t = i / 2
            fi = min(len(plan["cam"]) - 1, round(t * fps))
            if t < 0.5 or t > end - 0.3 or not holding(plan["cam"], fi, fps):
                continue
            img = Image.frombytes("RGB", (W, H), buf)
            boxes = [[x * W, y * H, w * W, h * H] for _, (x, y, w, h) in read(img)]
            j = held_key(keys, t)
            fr = None
            if j is not None:
                F, (cx, cy, cw) = keys[j]["focus"], plan["cam"][fi]
                k = W / cw
                fr = [(F[0] - cx) * k + W / 2, (F[1] - cy) * k + H / 2, F[2] * k, F[3] * k]
            hits += [(t, lvl) for lvl, _ in edge_text(boxes, W, H, fr, grey=np.asarray(img.convert("L")))]
        proc.wait()
        for lvl in ("FAIL", "WARN"):
            for a, b in runs([t for t, l in hits if l == lvl], 0.6):
                out.append((lvl, f"{a:.1f}-{b:.1f} s: a line of text runs into the frame edge" + (" on the focus" if lvl == "FAIL" else ""),
                            "product.py plan again (journey.text_guard re-frames it, edge_fades fades it)"))
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


def edge_text(boxes, W, H, focus=None, touch=3, grey=None):
    """[(level, box)] for OCR text boxes (frame px) that touch the frame edge with ink on the edge itself (grey:
    the frame, 0-255; an OCR box's own padding touching it is not a cut), so their words are cut: FAIL when the
    box overlaps the focus (frame px), WARN elsewhere."""
    import numpy as np
    out = []
    for b in boxes:
        x0, y0, x1, y1 = b[0], b[1], b[0] + b[2], b[1] + b[3]
        if x0 > touch and y0 > touch and x1 < W - touch and y1 < H - touch:
            continue
        if grey is not None:
            ya, yb, xa, xb = int(max(0, y0)), int(min(H, y1 + 1)), int(max(0, x0)), int(min(W, x1 + 1))
            strips = ([grey[ya:yb, :3]] if x0 <= touch else []) + ([grey[ya:yb, -3:]] if x1 >= W - touch else []) + \
                     ([grey[:3, xa:xb]] if y0 <= touch else []) + ([grey[-3:, xa:xb]] if y1 >= H - touch else [])
            if not any(st.size and float(st.max()) - float(np.median(st)) > 40 for st in strips):
                continue
        on = focus is not None and x0 < focus[0] + focus[2] and x1 > focus[0] and y0 < focus[1] + focus[3] and y1 > focus[1]
        out.append(("FAIL" if on else "WARN", b))
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
    # the cursor wholly in frame or not shown: one on the frame's right edge fails, gate_cursor hides it
    plan["cursor"] = [[x + w / 2 - 2, y, 1.0, 0, 0] for x, y, w in plan["cam"]]
    assert any("cursor is cut" in m for _, m, _ in framing(plan))
    gate_cursor(plan["cursor"], plan["cam"], 1920, 1080, 60, False)
    assert not any("cursor" in m for _, m, _ in framing(plan)), framing(plan)[:3]
    # no picture past 1:1: a state taken at 2x fails a frame that shows it at 2.5 frame px per page px
    plan2 = {**plan, "keys": [], "words": [], "cursor": [[0, 0, 0, 0, 0]], "cam": [[720, 450, 1920 / 2.5]],
             "canvas": {"layers": [{"t": 0, "x": 0, "y": 0, "w": 1440, "h": 900, "res": 2.0}]}}
    assert any("past 1:1" in m for _, m, _ in framing(plan2))
    plan2["canvas"]["layers"][0]["res"] = 3.0
    assert not framing(plan2)
    # the fill estimate: busy cells count, empty ones do not; a sparse framing is re-framed onto the busy part
    import numpy as np
    cells = np.zeros((40, 60))
    cells[25:38, 35:58] = 1                                  # the product sits low right on a 1440 x 960 plate
    ii = np.pad(cells.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    pl = {"x": 0, "y": 0, "w": 1440, "h": 960}
    assert fill_of(ii, pl, [720, 480, 1440], 1920, 1080) < 0.3 and fill_of(ii, pl, [1110, 760, 520], 1920, 1080) > 0.9
    # the frame filled by product: an empty ground (any colour) counts as none of it, UI detail as all of it
    busy = (np.random.default_rng(0).random((540, 960, 3)) * 255).astype(np.uint8)
    assert content_fill(np.full((540, 960, 3), 40, np.uint8)) == 0 and content_fill(busy) > 0.9
    # text whole or out: a framing that cuts a line at the frame edge fails; text_guard re-frames it
    lay = [{"plate": 0, "t": 0, "kind": "base", "x": 0, "y": 0, "w": 1440, "h": 900, "dur": 0,
            "lines": [[100, 100, 600, 40], [900, 400, 500, 30], [200, 600, 400, 30]]}]

    def text_plan(cam, focus):
        ks = [{"t": 0.0, "cam": list(cam), "focus": list(focus), "words": False, "wmax": 1872}]
        return {"width": 1920, "height": 1080, "fps": 30, "keys": ks, "canvas": {"layers": lay}, "end": 9,
                "cam": camera(ks, 90, 30, 1920, 1080, 400)[0]}
    tp = text_plan([500, 300, 1000], [100, 100, 400, 40])                     # the right edge cuts the second line
    assert any("not faded" in m for _, m, _ in text_cuts(tp)), text_cuts(tp)[:2]
    assert text_guard(tp["keys"], lay, 1920, 1080, 400) == 0, tp["keys"]
    tp["cam"] = camera(tp["keys"], 90, 30, 1920, 1080, 400)[0]
    assert not text_cuts(tp), text_cuts(tp)[:2]
    tp = text_plan([300, 300, 640], [100, 100, 400, 40])                      # the focus's own line cut: a framing failure
    assert any("on the focus" in m for _, m, _ in framing({**tp, "cursor": [[0, 0, 0, 0, 0]] * 90, "words": []}))
    assert text_guard(tp["keys"], lay, 1920, 1080, 400) == 0 and tp["keys"][0]["focus"][2] >= 600, tp["keys"]
    tp["cam"] = camera(tp["keys"], 90, 30, 1920, 1080, 400)[0]
    assert not text_cuts(tp), text_cuts(tp)[:2]
    # a line no framing can clear (wider than the page) is faded at both edges, never left hard-cut
    lay[0]["lines"].append([-600, 300, 3000, 30])
    tp = text_plan([500, 300, 1000], [100, 100, 400, 40])
    text_guard(tp["keys"], lay, 1920, 1080, 400)
    tp["cam"] = camera(tp["keys"], 90, 30, 1920, 1080, 400)[0]
    assert text_cuts(tp)
    tp["edge"] = edge_fades(tp)
    assert tp["edge"][45][0] > 0 and tp["edge"][45][2] > 0 and not text_cuts(tp), (tp["edge"][45], text_cuts(tp)[:2])
    # the render check: an OCR box touching the frame edge is a cut word; on the focus it fails
    bx = [[1800, 500, 120, 30], [0, 900, 80, 30], [500, 500, 300, 30]]
    assert [lv for lv, _ in edge_text(bx, 1920, 1080, [1700, 480, 220, 80])] == ["FAIL", "WARN"]
    g = np.zeros((1080, 1920), np.uint8)
    g[505:525, 1910:1920:3] = 230                   # glyph strokes run into the right edge; the left box's edge is bare
    assert [lv for lv, _ in edge_text(bx, 1920, 1080, [1700, 480, 220, 80], grey=g)] == ["FAIL"]
    print("demo ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
