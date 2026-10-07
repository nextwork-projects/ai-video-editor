#!/usr/bin/env python3
"""The graphics teardown: every on-screen graphic, where it sits, how it moves.

  measure <handle>   per video: find each graphic laid over the footage, crop a clean
                     sample, record its box, how it enters and exits (the box tracked frame
                     by frame at the source rate, the curve fitted to a GSAP ease), how long
                     it holds and whether it moves while up. Writes video/<id>.graphics.json,
                     graphics/<id>_<n>.jpg, graphics/heatmap.png, and merges
                     graphics.kinds / layout / entrances / exits / secondary_motion into style.json.
  merge <handle>     rebuild the style.json block from the per-video files (gemini.py kinds runs it).
  demo               self-check on a synthetic clip. No network.

How a graphic is found. The camera is locked off for most short-form talking heads, so
every framing (the base shot, a punched-in shot) has a clean plate: the per-pixel median
of all the frames shot that way. A graphic is a region that differs from its plate, is
not the speaker (a mask grown from the face box down to the frame bottom), is not the
caption band, and stays put for 0.6 s or more. Boxes are linked across samples by overlap.

How it moves. Around each entrance, every source frame is compared with the plate inside
a window round the graphic's final box: the box's centre, size and how much of the
final picture is already there. The channel that changed most (slide, scale, fade, mask)
gives the progress curve, and a grid search fits start, duration and ease family.
The ease names are the motion engine's (GSAP): power1-4.out, expo.out, sine.inOut,
power2/3.inOut, back.out(s), none. Exits are the same fit on the reversed clip (.in eases).

Kinds start as a code guess (moving inside: b-roll or a UI recording; text lines inside:
screenshot or text card) and are replaced by gemini.py kinds when a Gemini key exists.

Usage (the tool venv python: numpy, pillow, opencv):
  ~/.ai-video-editor/venv/bin/python scripts/graphics.py measure <handle> [--force]
  ~/.ai-video-editor/venv/bin/python scripts/graphics.py demo

Exit codes: 0 ok - 1 error - 2 usage
"""
import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
import warnings
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, slug  # noqa: E402
from look import decode, probe  # noqa: E402

AW = 180              # analysis width, px
SFPS = 5              # sample rate for finding graphics
DIFF = 38             # colour distance from the plate that counts as changed (0-441)
MIN_AREA = 0.006      # smallest graphic, share of the frame
MIN_HOLD = 0.6        # shortest graphic, s
PLATE_FIT = 8         # block median above this: the sample fits no plate (mid-push, b-roll)
KINDS = ["real screenshot", "UI recording", "logo", "text card", "photo", "meme", "chart", "b-roll"]
GRID = (16, 9)        # heatmap rows x cols (portrait); swapped for landscape


# ---------- eases (GSAP names) ----------

def _back(s):
    return lambda t: 1 + (s + 1) * (t - 1) ** 3 + s * (t - 1) ** 2


EASES = {
    "none": lambda t: t,
    "power1.out": lambda t: 1 - (1 - t) ** 2,
    "power2.out": lambda t: 1 - (1 - t) ** 3,
    "power3.out": lambda t: 1 - (1 - t) ** 4,
    "power4.out": lambda t: 1 - (1 - t) ** 5,
    "expo.out": lambda t: 1 - np.power(2.0, -10 * t),
    "sine.inOut": lambda t: -(np.cos(np.pi * t) - 1) / 2,
    "power2.inOut": lambda t: np.where(t < 0.5, 4 * t ** 3, 1 - (-2 * t + 2) ** 3 / 2),
    "power3.inOut": lambda t: np.where(t < 0.5, 8 * t ** 4, 1 - (-2 * t + 2) ** 4 / 2),
}
for _s in (0.8, 1.2, 1.7, 2.5, 3.5):
    EASES[f"back.out({_s})"] = _back(_s)


def ease_value(name, t):
    t = np.clip(np.asarray(t, float), 0, 1)
    if name.endswith(".in") or ".in(" in name:     # an exit: the .out curve reversed
        out = name.replace(".in", ".out")
        return 1 - EASES[out](1 - t)
    return EASES[name](t)


def fit_ease(ts, p, fps):
    """ts, p: progress samples (0 before, 1 settled). Grid search over start, duration and
    family. Returns {"ease", "duration_s", "overshoot", "t0", "err"} or None."""
    ts, p = np.asarray(ts, float), np.asarray(p, float)
    if len(ts) < 4 or np.ptp(p) < 0.3:
        return None
    a = ts[np.argmax(p > 0.08)] if (p > 0.08).any() else ts[0]
    best = None
    t0s = a + np.arange(-1.5, 0.51, 0.25) / fps
    ds = np.arange(0.5, max(1.0, 1.5 * fps) + 0.01, 0.5) / fps
    for name, f in EASES.items():
        pen = 0.004 if name.startswith("back") else 0.0   # prefer no overshoot on a tie
        for t0 in t0s:
            u = (ts[None, :] - t0) / ds[:, None]
            pred = np.where(u <= 0, 0.0, np.where(u >= 1, 1.0, f(np.clip(u, 0, 1))))
            err = ((pred - p[None, :]) ** 2).sum(1) + pen
            k = int(err.argmin())
            if best is None or err[k] < best[0]:
                best = (float(err[k]), name, float(t0), float(ds[k]))
    err, name, t0, d = best
    if d <= 1.0 / fps + 1e-6:
        name, d = "none", 0.0      # landed within a frame: a cut
    return {"ease": name, "duration_s": round(d, 3), "overshoot": round(max(0.0, float(p.max()) - 1), 3),
            "t0": round(t0, 3), "err": round(err / len(p), 4)}


# ---------- plates and masks ----------

def block_median(a, b, k=6, q=50):
    """The q-th percentile of the 6 x 6 block differences. A low q ignores an overlay
    covering most of the frame; a reframed shot moves every block."""
    h, w = (a.shape[0] // k) * k, (a.shape[1] // k) * k
    d = np.abs(a[:h, :w].astype(np.float32) - b[:h, :w]).mean(-1) if a.ndim == 3 else \
        np.abs(a[:h, :w].astype(np.float32) - b[:h, :w])
    return float(np.percentile(d.reshape(h // k, k, w // k, k).mean(axis=(1, 3)), q))


def similarity(src, dst):
    """2 x 3 matrix mapping grey image src onto dst (scale, shift; ORB + RANSAC), or None when
    the pictures do not share enough corners (a dark plain wall, a different shot)."""
    import cv2
    orb = cv2.ORB_create(1500, edgeThreshold=8, patchSize=15, fastThreshold=5)
    k1, d1 = orb.detectAndCompute(src, None)
    k2, d2 = orb.detectAndCompute(dst, None)
    if d1 is None or d2 is None or len(k1) < 20 or len(k2) < 20:
        return None
    ms = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d1, d2)
    if len(ms) < 20:
        return None
    A, inl = cv2.estimateAffinePartial2D(np.float32([k1[m.queryIdx].pt for m in ms]),
                                         np.float32([k2[m.trainIdx].pt for m in ms]),
                                         method=cv2.RANSAC, ransacReprojThreshold=2)
    if A is None or inl.sum() < 40:
        return None
    scale = math.hypot(A[0, 0], A[1, 0])
    return A if 0.6 <= scale <= 1.6 else None


def consensus(S, fallback, tol=24.0):
    """Per pixel, the value the segments agree on. Each segment median votes for every other
    within tol; the wall looks the same every time it shows, so it is usually the biggest
    cluster. Where no cluster holds 60% of the segments (a spot overlays cover half the time,
    often with look-alike white pages), the top two clusters are both kept and the one closer
    to the wall around it wins: the sure pixels are inpainted across the unsure ones."""
    import cv2
    n = len(S)
    valid = ~np.isnan(S[..., 0])
    V = np.nan_to_num(S)
    nv = np.maximum(valid.sum(0), 1)

    def top(excl):
        votes = np.full(valid.shape, -1, np.int16)
        ok = valid & ~excl
        for i in range(n):
            near = (np.abs(V - V[i]).max(-1) < tol) & ok
            votes[i] = np.where(ok[i], near.sum(0), -1)
        best = votes.argmax(0)
        c = np.take_along_axis(V, best[None, ..., None], 0)[0]
        sup = (np.abs(V - c).max(-1) < tol) & ok
        return sup, votes.max(0)
    supA, vA = top(np.zeros_like(valid))
    supB, vB = top(supA)

    def mean(sup):
        return (V * sup[..., None]).sum(0) / np.maximum(sup.sum(0), 1)[..., None]
    A, B = mean(supA), mean(supB)
    sure = vA >= 0.6 * nv
    guess = cv2.inpaint(np.clip(A, 0, 255).astype(np.uint8), (~sure).astype(np.uint8), 7,
                        cv2.INPAINT_TELEA).astype(np.float32)
    useB = ~sure & (vB > 0) & (np.abs(B - guess).sum(-1) < np.abs(A - guess).sum(-1))
    out = np.where(useB[..., None], B, A)
    return np.where((vA > 0)[..., None], out, fallback).astype(np.float32)


def plates(F, segs):
    """Per sample, the clean plate it is compared with. Every segment (between cuts and
    pushes) is matched to the longest one by its corners: a punch-in, a slightly moved
    camera, a jump cut that nudged the frame. The master plate is the median of every
    sample warped onto the longest segment, so an overlay that is up for one whole segment
    is outvoted by the others; each segment gets the master warped back onto its framing.
    A segment that matches nothing (a plain dark wall) votes unwarped and uses it as is."""
    import cv2
    H, W = F.shape[1:3]
    gray = [cv2.cvtColor(np.median(F[a:b:max(1, (b - a) // 9)], axis=0).astype(np.uint8), cv2.COLOR_RGB2GRAY)
            for a, b in segs]
    ref = max(range(len(segs)), key=lambda i: segs[i][1] - segs[i][0])
    A = [np.float32([[1, 0, 0], [0, 1, 0]]) if i == ref else similarity(g, gray[ref]) for i, g in enumerate(gray)]
    acc = []
    for (a, b), M in zip(segs, A):
        seg = [F[i].astype(np.float32) for i in range(a, b, max(1, (b - a) // 9))]
        if M is not None:
            seg = [cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(np.nan,) * 3) for f in seg]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN where a punch-in shows less
            acc.append(np.nanmedian(np.stack(seg), axis=0))
    # One vote per segment, not per second: an overlay up through one long segment is one
    # voice among many cuts.
    master = consensus(np.stack(acc), np.median(F, axis=0))
    out = [master] * len(F)
    for (a, b), M in zip(segs, A):
        if M is not None:
            pl = cv2.warpAffine(master, cv2.invertAffineTransform(M), (W, H), flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_REPLICATE)
            for i in range(a, b):
                out[i] = pl
    return out


def off_plate(f, pl, body, k=6):
    """True when most of what is not the speaker differs from the plate: the frame is
    mid-push or reframed, so its differences are the camera, not graphics."""
    h, w = (f.shape[0] // k) * k, (f.shape[1] // k) * k
    d = np.abs(f[:h, :w].astype(np.float32) - pl[:h, :w]).mean(-1).reshape(h // k, k, w // k, k).mean(axis=(1, 3))
    keep = ~body[:h, :w].reshape(h // k, k, w // k, k).any(axis=(1, 3))
    return keep.sum() > 4 and float(np.percentile(d[keep], 20)) > PLATE_FIT   # an overlay may cover most of it


def lap(f):
    import cv2
    g = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    return cv2.blur(np.abs(cv2.Laplacian(g, cv2.CV_32F)), (9, 9))


def blur_behind(f, pl, body):
    """True when the footage around the speaker is much softer than the plate: the creator
    blurs the shot while a graphic is up."""
    keep = ~body
    if keep.sum() < 0.1 * keep.size:
        return False
    a, b = lap(f)[keep], lap(pl)[keep]
    return float(np.percentile(a, 50)) < 0.45 * float(np.percentile(b, 50))


def sharp_regions(f, body, band):
    """In a blurred frame: where the picture is still sharp (the graphic on top)."""
    import cv2
    L = lap(f)
    m = (L > max(4.0, 3 * float(np.median(L)))) & ~body
    if band:
        m[int(band[0] * f.shape[0]):int(band[1] * f.shape[0]) + 1] = False
    return cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def real_graphic(f, pl, box, blurred):
    """Drops what only looks changed: a hand (mostly skin), an empty patch (nothing drawn in
    it), and the background nudged a few pixels (it lines up with the plate after a shift)."""
    import cv2
    H, W = f.shape[:2]
    x0, y0 = int(box[0] * W), int(box[1] * H)
    x1, y1 = max(x0 + 3, int((box[0] + box[2]) * W)), max(y0 + 3, int((box[1] + box[3]) * H))
    patch = f[y0:y1, x0:x1]
    ycc = cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2YCrCb)
    # Skin among the pixels that are neither near white nor near black (a white sleeve or a
    # dark wall around a hand does not dilute it).
    mid = (ycc[..., 0] > 45) & (ycc[..., 0] < 215)
    skin = ((ycc[..., 1] >= 135) & (ycc[..., 1] <= 180) & (ycc[..., 2] >= 80) & (ycc[..., 2] <= 130) & mid)
    if mid.mean() > 0.2 and skin.sum() > 0.5 * mid.sum():
        return False
    if float(cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2GRAY).std()) < 6:
        return False
    if blurred:
        return True
    P = f.astype(np.float32)[y0:y1, x0:x1]
    base = float(np.abs(P - pl[y0:y1, x0:x1]).mean())
    best = base
    for dy in range(-6, 7, 2):
        for dx in range(-6, 7, 2):
            ya, xa = y0 + dy, x0 + dx
            if ya < 0 or xa < 0 or ya + (y1 - y0) > H or xa + (x1 - x0) > W:
                continue
            best = min(best, float(np.abs(P - pl[ya:ya + y1 - y0, xa:xa + x1 - x0]).mean()))
    return not (best < 12 and best < 0.5 * base)


def like_plate(f, pl, box):
    """Best normalised correlation of the box's picture with the plate around the same
    place, over a few zooms. Near 1: it is the set. A screenshot or a clip scores low."""
    import cv2
    H, W = f.shape[:2]
    x, y, w, h = box
    x0, y0 = int(x * W), int(y * H)
    x1, y1 = int((x + w) * W), int((y + h) * H)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return 0.0
    g = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    gp = cv2.cvtColor(np.clip(pl, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    patch = g[y0:y1, x0:x1]
    if patch.std() < 4:
        return 0.0
    best = 0.0
    for sc in (0.8, 0.9, 1.0, 1.12, 1.25):
        pw, ph = max(6, int((x1 - x0) / sc)), max(6, int((y1 - y0) / sc))
        t = cv2.resize(patch, (pw, ph), interpolation=cv2.INTER_AREA)
        cx, cy = (x0 + x1) / 2 / sc + W / 2 * (1 - 1 / sc), (y0 + y1) / 2 / sc + H / 2 * (1 - 1 / sc)
        mx, my = int(0.25 * pw) + 4, int(0.25 * ph) + 4
        X0, Y0 = int(max(0, cx - pw / 2 - mx)), int(max(0, cy - ph / 2 - my))
        X1, Y1 = int(min(W, cx + pw / 2 + mx)), int(min(H, cy + ph / 2 + my))
        region = gp[Y0:Y1, X0:X1]
        if region.shape[0] < ph or region.shape[1] < pw:
            continue
        best = max(best, float(cv2.matchTemplate(region, t, cv2.TM_CCOEFF_NORMED).max()))
    return best


def body_mask(face, H, W):
    """The speaker: the face box widened from just above the head to the shoulders, then
    the full width below (arms and knees reach the frame edges).
    ponytail: a graphic beside the speaker's lap is lost; a person segmenter would keep it."""
    m = np.zeros((H, W), bool)
    if face:
        x, y, w, h = face
        x0, x1 = int((x - 1.0 * w) * W), int((x + 2.0 * w) * W)
        m[max(0, int((y - 0.9 * h) * H)):, max(0, x0):min(W, x1)] = True   # hair, and a lean forward
        m[min(H, int((y + 1.6 * h) * H)):, :] = True
    return m


def changed(f, plate, body, band):
    import cv2
    d = np.sqrt(((f.astype(np.float32) - plate) ** 2).sum(-1))
    d = cv2.GaussianBlur(d, (3, 3), 0)
    m = (d > DIFF) & ~body
    if band:
        m[int(band[0] * f.shape[0]):int(band[1] * f.shape[0]) + 1] = False
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    return m


def boxes(mask):
    """Connected regions as [x, y, w, h] fractions with their fill, biggest first."""
    import cv2
    H, W = mask.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a >= MIN_AREA * H * W:
            out.append({"box": [x / W, y / H, w / W, h / H], "fill": a / (w * h)})
    return sorted(out, key=lambda b: -b["box"][2] * b["box"][3])


def iou(a, b):
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw, ih = max(0, min(ax1, bx1) - max(a[0], b[0])), max(0, min(ay1, by1) - max(a[1], b[1]))
    u = a[2] * a[3] + b[2] * b[3] - iw * ih
    return iw * ih / u if u else 0.0


def overlay_dets(F, band):
    """Graphics on moving footage: per sample, the regions that hold still for +-0.4 s while most of
    the frame changes (a cut or a moving camera under them), rectangular enough and not flat (a
    sky that happens to hold still is not a graphic). A sample whose footage is still gives none."""
    import cv2
    n, H, W = F.shape[:3]
    G = F.astype(np.float32)
    k5 = np.ones((5, 5), np.uint8)
    out = []
    for i in range(n):
        js = [j for j in range(max(0, i - 2), min(n, i + 3)) if j != i]
        d = np.max([np.abs(G[j] - G[i]).mean(-1) for j in js], axis=0) if js else None
        if d is None or (d >= 25).mean() < 0.4:
            out.append([])
            continue
        m = (d < 12).astype(np.uint8)
        if band:
            m[int(band[0] * H):int(band[1] * H) + 1] = 0
        m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_OPEN, k5), cv2.MORPH_CLOSE, k5)
        keep = []
        for b in boxes(m):
            x, y, w, h = b["box"]
            if b["fill"] < 0.6 or w * h > 0.6:
                continue
            patch = G[i][int(y * H):int((y + h) * H), int(x * W):int((x + w) * W)]
            if cv2.cvtColor(patch.astype(np.uint8), cv2.COLOR_RGB2GRAY).std() >= 8:
                keep.append(b)
        out.append(keep)
    return out


def grow_track(tr, F):
    """The track's run of samples widened to every neighbouring sample showing the same picture in
    its box: the footage under it stood still there, so the moving-footage test could not see it."""
    box = tr["boxes"][len(tr["boxes"]) // 2]
    ref = own_crop(F[tr["idx"][len(tr["idx"]) // 2]], box)
    same = [float(np.abs(own_crop(F[i], box) - ref).mean()) < 14 for i in range(len(F))]
    a, b = tr["idx"][0], tr["idx"][-1]
    while a > 0 and same[a - 1]:
        a -= 1
    while b + 1 < len(F) and same[b + 1]:
        b += 1
    return {**tr, "idx": list(range(a, b + 1)), "boxes": [box] * (b - a + 1), "last": b}


# ---------- motion of one graphic ----------

def component(m, roi, fb):
    """The changed region inside roi (x0, y0, x1, y1 px) that is this graphic: the component
    overlapping its final box fb most, else the one nearest it. (x0, y0, x1, y1) px or None."""
    import cv2
    X0, Y0, X1, Y1 = roi
    sub = np.ascontiguousarray(m[Y0:Y1, X0:X1])
    n, _, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    best, key = None, None
    fcx, fcy = (fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if a < 6:
            continue
        bx = (x + X0, y + Y0, x + X0 + w, y + Y0 + h)
        ov = max(0, min(bx[2], fb[2]) - max(bx[0], fb[0])) * max(0, min(bx[3], fb[3]) - max(bx[1], fb[1]))
        k = (ov, -math.hypot((bx[0] + bx[2]) / 2 - fcx, (bx[1] + bx[3]) / 2 - fcy))
        if key is None or k > key:
            best, key = bx, k
    return best


def motion(frames, plate, body, box, fps, t_first, blurred=False):
    """How one graphic arrives. frames: source-rate RGB from before it is there to after it
    settles. box: its settled box, fractions. Returns the entrance dict or None.
    Slides are read in two strips through the box (one per axis) off the leading edge, so a
    card that starts off-frame still measures; scale and masks off the box; fades off how
    strong the picture is against the plate inside its own box."""
    H, W = plate.shape[:2]
    bx, by, bw, bh = box[0] * W, box[1] * H, box[2] * W, box[3] * H
    fb = (bx, by, bx + bw, by + bh)
    rois = {"v": (int(max(0, bx - 0.15 * bw)), 0, int(min(W, bx + 1.15 * bw)), H),
            "h": (0, int(max(0, by - 0.15 * bh)), W, int(min(H, by + 1.15 * bh))),
            "r": (int(max(0, bx - 0.6 * bw)), int(max(0, by - 0.6 * bh)),
                  int(min(W, bx + 1.6 * bw)), int(min(H, by + 1.6 * bh)))}
    geo, strength = {k: [] for k in rois}, []
    for f in frames:
        d = np.sqrt(((f.astype(np.float32) - plate) ** 2).sum(-1))
        m = sharp_regions(f, body, None) if blurred and blur_behind(f, plate, body) else changed(f, plate, body, None)
        for k, roi in rois.items():
            geo[k].append(component(m, roi, fb))
        g = geo["r"][-1]
        strength.append(float(d[int(g[1]):int(g[3]), int(g[0]):int(g[2])].mean()) if g else 0.0)
    if not geo["r"][-1]:
        return None
    E = geo["r"][-1]
    ew, eh = E[2] - E[0], E[3] - E[1]
    # The first frame of the move: from here to the end the graphic shows in a strip.
    first = None
    for k in range(len(frames) - 1, -1, -1):
        if geo["v"][k] or geo["h"][k]:
            first = k
        else:
            break
    if first is None or first >= len(frames) - 2:
        return None
    ts = t_first + np.arange(len(frames)) / fps
    s_end = strength[-1] or 1.0

    def cen(g):
        return ((g[0] + g[2]) / 2, (g[1] + g[3]) / 2) if g else None
    gv, gh = geo["v"][first], geo["h"][first]
    dy = (cen(gv)[1] - cen(E)[1]) / max(eh, 1) if gv else 0.0
    dx = (cen(gh)[0] - cen(E)[0]) / max(ew, 1) if gh else 0.0
    gr = geo["r"][first]
    size = math.sqrt((gr[2] - gr[0]) * (gr[3] - gr[1]) / max(1, ew * eh)) if gr else 0.0
    out = {"kind": "cut", "from": None, "distance_pct": 0.0, "scale_from": 1.0, "fade": False, "mask": None}
    move = [k for k in range(first, len(frames))]
    if max(abs(dx), abs(dy)) > 0.15:
        out["kind"] = "slide"
        if abs(dy) >= abs(dx):
            side, axis, lead = ("top" if dy < 0 else "bottom"), "v", (3 if dy < 0 else 1)
        else:
            side, axis, lead = ("left" if dx < 0 else "right"), "h", (2 if dx < 0 else 0)
        out["from"] = side
        e0, e1 = geo[axis][first][lead], E[lead]
        out["distance_pct"] = round(100 * float(abs(e1 - e0)) / (H if axis == "v" else W), 1)
        curve = [0.0] * first + [(g[lead] - e0) / (e1 - e0) if g and e1 != e0 else 1.0 for g in
                                 (geo[axis][k] for k in move)]
    elif gr and (size < 0.85 or size > 1.15) and abs(cen(gr)[0] - cen(E)[0]) < 0.15 * ew:
        out["kind"] = "scale"
        out["scale_from"] = round(float(size), 2)
        curve = [0.0] * first + [(math.sqrt((g[2] - g[0]) * (g[3] - g[1]) / (ew * eh)) - size) / (1 - size)
                                 if g else 0.0 for g in (geo["r"][k] for k in move)]
    elif gr and ((gr[2] - gr[0]) < 0.8 * ew or (gr[3] - gr[1]) < 0.8 * eh):
        out["kind"] = "mask"
        out["mask"] = "horizontal" if (gr[2] - gr[0]) < 0.8 * ew else "vertical"
        curve = [0.0] * first + [((g[2] - g[0]) * (g[3] - g[1])) / (ew * eh) if g else 0.0
                                 for g in (geo["r"][k] for k in move)]
    else:
        curve = [0.0] * first + [strength[k] / s_end for k in move]
    # Fade: during the move the picture is weaker against the plate than once it has landed.
    mid = [strength[k] / s_end for k in move if 0.15 < curve[k] < 0.9]
    if out["kind"] in ("cut", "slide", "scale") and mid and statistics.median(mid) < 0.75:
        out["fade"] = True
        if out["kind"] == "cut":
            out["kind"] = "fade"
    fit = fit_ease(ts, np.clip(np.array(curve), -0.5, 1.6), fps)
    if not fit:
        fit = {"ease": "none", "duration_s": 0.0, "overshoot": 0.0, "t0": round(float(ts[first]), 3), "err": 0.0}
    if fit["duration_s"] == 0.0:
        out.update(kind="cut", fade=False, distance_pct=0.0, scale_from=1.0, mask=None)
        out["from"] = None
    out.update(fit)
    if out["overshoot"] < 0.02 and out["ease"].startswith("back"):
        out["ease"] = "power3.out"
    return out


def reverse_ease(e):
    if not e:
        return e
    e = dict(e)
    e["ease"] = e["ease"].replace(".out", ".in") if e["ease"].endswith(".out") or ".out(" in e["ease"] else e["ease"]
    e.pop("t0", None)
    e["to"] = e.pop("from", None)
    e["scale_to"] = e.pop("scale_from", 1.0)
    return e


# ---------- one video ----------

def own_crop(f, b, size=32):
    """The box's picture at a fixed size, so a moving box compares like for like."""
    import cv2
    H, W = f.shape[:2]
    x0, y0 = int(b[0] * W), int(b[1] * H)
    x1, y1 = max(x0 + 2, int((b[0] + b[2]) * W)), max(y0 + 2, int((b[1] + b[3]) * H))
    return cv2.resize(f[y0:y1, x0:x1], (size, size), interpolation=cv2.INTER_AREA).astype(np.float32)


def faces_at(look):
    """t -> face box from look.py's samples (3 a second)."""
    if not look:
        return lambda t: None
    ss = look.get("samples") or []
    ts = np.array([s["t"] for s in ss]) if ss else np.array([0.0])
    fs = [s["face"] for s in ss if s["face"]]
    usual = [float(np.median([f[j] for f in fs])) for j in range(4)] if fs else None

    def at(t):
        if not ss:
            return None
        f = ss[int(np.abs(ts - t).argmin())]["face"]
        # The largest face can be someone in a clip laid over the speaker: the speaker is
        # still in the usual place, so mask that.
        if f and usual and (abs(f[0] + f[2] / 2 - usual[0] - usual[2] / 2) > 0.12
                            or abs(f[1] + f[3] / 2 - usual[1] - usual[3] / 2) > 0.12):
            return usual
        return f
    return at


def colour_count(img):
    """Colours (8 levels a channel) that cover 90% of a picture: an icon or a text card has a
    handful, a photo hundreds."""
    q = (np.asarray(img).reshape(-1, 3) // 32).astype(np.int32)
    n = np.sort(np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]))[::-1]
    return int(np.searchsorted(np.cumsum(n), 0.9 * len(q)) + 1)


def guess_kind(g, look):
    """Code's guess at the kind. gemini.py kinds replaces it."""
    if g["moving"] >= 6:
        return "UI recording" if g["text_lines"] >= 2 else "b-roll"
    # an app or brand icon: small, near-square on screen, a few flat colours, a name at most, and no
    # line of text running out of it (then it is a piece of a wider card)
    if (g.get("colours") or 99) <= 8 and 0.75 <= (g.get("aspect") or 0) <= 1.33 and g.get("area_pct", 100) <= 8 \
            and g["text_lines"] <= 1 and not g.get("text_crossing"):
        return "logo"
    if g["text_lines"] >= 4:
        return "real screenshot"
    if g["text_lines"] >= 1 and g["flat"]:
        return "text card"
    return "photo"


def text_lines_in(box, t0, t1, look):
    """OCR lines from look.json that sit inside the box while it is up (median per sample)."""
    if not look:
        return 0
    x, y, w, h = box
    counts = []
    for s in look.get("samples") or []:
        if t0 <= s["t"] <= t1:
            counts.append(sum(1 for tx, b, cap in s["lines"] if not cap
                              and x - 0.02 <= b[0] + b[2] / 2 <= x + w + 0.02
                              and y - 0.02 <= b[1] + b[3] / 2 <= y + h + 0.02))
    return int(statistics.median(counts)) if counts else 0


def text_crossing(box, t0, t1, look):
    """OCR lines (not captions) that run across the box's edge while it is up: the box is part of a
    wider text item."""
    if not look:
        return 0
    x, y, w, h = box
    n = 0
    for s in look.get("samples") or []:
        if t0 <= s["t"] <= t1:
            for tx, b, cap in s["lines"]:
                inside = x - 0.02 <= b[0] + b[2] / 2 <= x + w + 0.02 and y - 0.02 <= b[1] + b[3] / 2 <= y + h + 0.02
                ov = max(0.0, min(x + w, b[0] + b[2]) - max(x, b[0])) * max(0.0, min(y + h, b[1] + b[3]) - max(y, b[1]))
                n += not cap and not inside and ov > 0
    return n


def measure_video(path, look=None, visual=None, band=None, crop_dir=None):
    w0, h0, src_fps, dur = probe(path)
    W = AW
    H = round(AW * h0 / w0 / 2) * 2
    F = np.stack(list(decode(path, W, H, SFPS)))
    n = len(F)
    face = faces_at(look)
    cuts = [c for c in (visual or {}).get("cuts", []) if 0 < c < dur]
    pushes = [(z["t"], z["t"] + z["duration_s"]) for z in (visual or {}).get("zooms", []) if z["kind"] == "push"]
    edges = sorted(set([0] + [round(c * SFPS) for c in cuts] + [round(a * SFPS) for a, b in pushes]
                       + [round(b * SFPS) for a, b in pushes] + [n]))
    segs = [(a, b) for a, b in zip(edges, edges[1:]) if b - a >= 2]
    plate_of = plates(F, segs or [(0, n)])
    # No speaker most of the time and no clean plate (a vlog, a walk, b-roll): the plate method would
    # call the moving footage a graphic. Find what holds still while the footage moves instead.
    fit_share = float(np.mean([block_median(F[i], plate_of[i]) <= PLATE_FIT for i in range(n)]))
    face_share = sum(1 for i in range(n) if face(i / SFPS)) / n
    overlay = fit_share < 0.5 and face_share < 0.5

    # Per sample: changed regions that are not the speaker or the captions.
    dets, blurred = [], np.zeros(n, bool)
    for i in range(n) if not overlay else ():
        t = i / SFPS
        f, pl = F[i], plate_of[i]
        fc = face(t)
        body = body_mask(fc, H, W)
        if fc and blur_behind(f, pl, body):
            # The footage is blurred behind a graphic: the graphic is the sharp part.
            blurred[i] = True
            m = sharp_regions(f, body, band)
        elif fc and off_plate(f, pl, body):
            dets.append([])         # mid-push or a framing with no plate
            continue
        else:
            m = changed(f, pl, body, band)
        dets.append([b for b in boxes(m) if b["fill"] >= 0.35 and real_graphic(f, pl, b["box"], blurred[i])])
    if overlay:
        dets = overlay_dets(F, band)

    # Link boxes across samples into tracks; a gap of up to 0.6 s (a skipped push frame, a
    # cut under the graphic) is bridged.
    tracks = []
    for i, ds in enumerate(dets):
        for d in ds:
            best = max((tr for tr in tracks if i - tr["last"] <= 4), key=lambda tr: iou(tr["boxes"][-1], d["box"]),
                       default=None)
            if best and iou(best["boxes"][-1], d["box"]) >= 0.4:
                best["boxes"].append(d["box"])
                best["idx"].append(i)
                best["last"] = i
                best["fill"] = max(best["fill"], d["fill"])
            else:
                tracks.append({"boxes": [d["box"]], "idx": [i], "last": i, "fill": d["fill"]})
    def jitter(tr):
        """How irregularly its edges move: a laid-over graphic holds still or drifts on a line,
        a hand jumps about. The median distance of each edge from a straight-line fit."""
        b = np.array(tr["boxes"])
        e = np.c_[b[:, 0], b[:, 1], b[:, 0] + b[:, 2], b[:, 1] + b[:, 3]]
        if len(e) < 3:
            return 0.0
        x = np.array(tr["idx"], float)
        fit = np.stack([np.polyval(np.polyfit(x, e[:, j], 1), x) for j in range(4)], 1)
        return float(np.median(np.abs(e - fit), 0).max())
    def abrupt(tr):
        """A laid-on graphic arrives: its box changes a lot within 0.6 s. Footage drifting
        out of line with the plate (focus breathing, a handheld nudge) creeps in instead."""
        i0 = tr["idx"][0]
        if i0 < 2:
            return True
        x, y, w, h = tr["boxes"][0]
        ys, xs = slice(int(y * H), max(int(y * H) + 2, int((y + h) * H))), slice(int(x * W), max(int(x * W) + 2, int((x + w) * W)))
        after = F[min(n - 1, i0 + 1)][ys, xs].astype(np.float32)
        return float(np.abs(after - F[i0 - 2][ys, xs]).mean()) >= 25

    def background(tr):
        """The box shows the set, reframed: it matches the plate near the same place at some
        zoom (a picture frame after a punch-in, a cushion after a handheld nudge)."""
        mid = tr["idx"][len(tr["idx"]) // 2]
        c = like_plate(F[mid], plate_of[mid], tr["boxes"][len(tr["idx"]) // 2])
        return c > 0.65 or (c > 0.5 and not abrupt(tr))
    if overlay:
        # Grown over the samples where the footage stood still, then kept when it is a laid-on graphic:
        # text in it or a hard rectangular edge, and not up for most of the video (a watermark, a frame).
        tracks = [grow_track(tr, F) for tr in tracks]
        tracks = [tr for tr in tracks if MIN_HOLD <= (tr["idx"][-1] - tr["idx"][0] + 1) / SFPS <= 0.6 * dur
                  and jitter(tr) <= 0.015 and (tr["fill"] >= 0.85 or text_lines_in(
                      tr["boxes"][0], tr["idx"][0] / SFPS, (tr["idx"][-1] + 1) / SFPS, look) >= 1)]
        tracks = [tr for k, tr in enumerate(tracks)   # two tracks grown into one graphic: keep the first
                  if not any(iou(tr["boxes"][0], o["boxes"][0]) >= 0.5 and set(tr["idx"]) & set(o["idx"]) for o in tracks[:k])]
    else:
        tracks = [tr for tr in tracks if (tr["idx"][-1] - tr["idx"][0] + 1) / SFPS >= MIN_HOLD
                  and len(tr["idx"]) >= 0.5 * (tr["idx"][-1] - tr["idx"][0] + 1) and jitter(tr) <= 0.015
                  and not background(tr)]

    out = []
    for k, tr in enumerate(sorted(tracks, key=lambda tr: tr["idx"][0])):
        i0, i1 = tr["idx"][0], tr["idx"][-1]
        box = [float(np.median([b[j] for b in tr["boxes"]])) for j in range(4)]
        t_in, t_out = i0 / SFPS, (i1 + 1) / SFPS
        # Moving while up: the box drifting, growing, or the picture inside changing.
        mid = tr["idx"][len(tr["idx"]) // 4: max(len(tr["idx"]) // 4 + 2, 3 * len(tr["idx"]) // 4)]
        cxs = [tr["boxes"][tr["idx"].index(i)][0] + tr["boxes"][tr["idx"].index(i)][2] / 2 for i in mid]
        cys = [tr["boxes"][tr["idx"].index(i)][1] + tr["boxes"][tr["idx"].index(i)][3] / 2 for i in mid]
        ars = [tr["boxes"][tr["idx"].index(i)][2] * tr["boxes"][tr["idx"].index(i)][3] for i in mid]
        span_s = max(1e-6, (mid[-1] - mid[0]) / SFPS)
        drift = 100 * math.hypot(cxs[-1] - cxs[0], cys[-1] - cys[0]) / span_s if len(mid) > 1 else 0.0
        grow = 100 * (math.sqrt(ars[-1] / max(ars[0], 1e-6)) - 1) if len(mid) > 1 else 0.0
        inner = [own_crop(F[i], tr["boxes"][tr["idx"].index(i)]) for i in mid]   # follows the box: drift is not "video"
        moving = float(np.median([np.abs(a - b).mean() for a, b in zip(inner, inner[1:])])) if len(inner) > 1 else 0.0
        flat = bool(inner and np.median(np.abs(inner[0] - np.median(inner[0], axis=(0, 1)))) < 12)
        sec = "video" if moving >= 6 else "push" if abs(grow) / span_s >= 2 else "drift" if drift >= 1.5 else "still"

        # Entrance and exit at the source frame rate, against the same plate.
        pl = plate_of[i0]
        fc = face(t_in)
        body = body_mask(fc, H, W)
        blur = bool(blurred[i0:i1 + 1].mean() >= 0.5)
        # ponytail: no entrance or exit fit in overlay mode (it needs a plate); fit against the
        # shot before the graphic lands if overlay creators need their motion.
        win = list(decode(path, W, H, None, max(0.0, t_in - 0.6), 1.4)) if not overlay else []
        ent = motion(win, pl, body, box, src_fps, max(0.0, t_in - 0.6), blur) if len(win) > 6 else None
        ext = None
        if t_out < dur - 0.3 and not overlay:
            win = list(decode(path, W, H, None, max(0.0, t_out - 0.9), 1.4))
            if len(win) > 6:
                ext = reverse_ease(motion(win[::-1], plate_of[min(i1, n - 1)], body_mask(face(t_out), H, W),
                                          box, src_fps, 0.0, blur))
        rec = {"n": k, "t_in": round(t_in, 2), "t_out": round(t_out, 2), "hold_s": round(t_out - t_in, 2),
               "blur_behind": blur,
               "box": [round(v, 4) for v in box], "area_pct": round(100 * box[2] * box[3], 1),
               "entrance": ent, "exit": ext, "secondary": sec, "drift_pct_s": round(drift, 2),
               "grow_pct": round(grow, 1), "moving": round(moving, 1), "flat": flat,
               "colours": colour_count(own_crop(F[tr["idx"][len(tr["idx"]) // 2]], tr["boxes"][len(tr["idx"]) // 2])),
               "aspect": round(box[2] * w0 / max(1e-6, box[3] * h0), 2),
               "text_lines": text_lines_in(box, t_in, t_out, look),
               "text_crossing": text_crossing(box, t_in, t_out, look)}
        if rec["box"][3] < 0.05 and rec["box"][2] > 4 * rec["box"][3] and not rec["text_lines"] and look:
            continue      # a thin strip with no text in it: a shelf edge or the ceiling line
        rec["kind"] = guess_kind(rec, look)
        rec["kind_source"] = "code"
        if crop_dir is not None:
            rec["crop"] = save_crop(path, (t_in + min(t_out, t_in + 2.0)) / 2 + 0.3, box, crop_dir,
                                    f"{path.stem}_{k}.jpg")
        out.append(rec)
    return {"id": path.stem, "duration_s": round(dur, 2), "width": w0, "height": h0,
            "mode": "overlay" if overlay else "plate", "graphics": out}


def save_crop(path, t, box, crop_dir, name):
    from PIL import Image
    w0, h0, _, _ = probe(path)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    if len(raw) < w0 * h0 * 3:
        return None
    im = Image.fromarray(np.frombuffer(raw[:w0 * h0 * 3], np.uint8).reshape(h0, w0, 3))
    x, y, w, h = box
    pad = 0.03   # the box is measured at 180 px: keep the letters at its edge
    im = im.crop((int(max(0, x - pad) * w0), int(max(0, y - pad) * h0),
                  int(min(1, x + w + pad) * w0), int(min(1, y + h + pad) * h0)))
    im.thumbnail((480, 480))
    crop_dir.mkdir(parents=True, exist_ok=True)
    im.save(crop_dir / name, quality=82)
    return f"graphics/{name}"


# ---------- one creator ----------

def heatmap(rows, portrait=True):
    """Seconds of graphic cover per grid cell, normalised to the busiest cell (0-100)."""
    gh, gw = GRID if portrait else GRID[::-1]
    acc = np.zeros((gh, gw))
    for r in rows:
        for g in kept(r):
            x, y, w, h = g["box"]
            acc[int(y * gh):max(int(y * gh) + 1, math.ceil((y + h) * gh)),
                int(x * gw):max(int(x * gw) + 1, math.ceil((x + w) * gw))] += g["hold_s"]
    return (100 * acc / acc.max()).round().astype(int).tolist() if acc.max() else acc.astype(int).tolist()


def zone(box):
    x, y, w, h = box
    if w * h >= 0.6:
        return "full"
    cy = y + h / 2
    return "top" if cy < 0.38 else "bottom" if cy > 0.62 else "middle"


def kept(r):
    """A video's graphics without the ones the kinds pass called part of the set."""
    return [g for g in r["graphics"] if g.get("kind") != "set"]


def summarise(rows, face=None):
    """Per-video graphics -> the style.json additions."""
    gs = [g for r in rows for g in kept(r)]
    mins = sum(r["duration_s"] for r in rows) / 60 or 1
    if not gs:
        return {"kinds": {}, "layout": None, "entrances": [], "exits": [], "secondary_motion": {}, "measured": 0,
                "share_pct_measured": 0}
    tot = sum(g["hold_s"] for g in gs)
    kinds = Counter()
    for g in gs:
        kinds[g["kind"]] += g["hold_s"]
    zones = Counter()
    for g in gs:
        zones[zone(g["box"])] += g["hold_s"]
    fy = (face or {}).get("y_pct")

    def covers_face(b):
        return fy is not None and b[1] * 100 <= fy <= (b[1] + b[3]) * 100 and b[0] <= 0.5 <= b[0] + b[2]
    layout = {
        "zones_pct": {z: round(100 * zones[z] / tot) for z in ("top", "middle", "bottom", "full")},
        "median_box": [round(statistics.median(g["box"][j] for g in gs) * 100, 1) for j in range(4)],
        "area_pct": round(statistics.median(g["area_pct"] for g in gs), 1),
        "covers_face_pct": round(100 * sum(g["hold_s"] for g in gs if covers_face(g["box"])) / tot),
        "heatmap": "graphics/heatmap.png",
    }

    def group(key):
        """Entrances (or exits) grouped by kind + ease: the motion engine's menu, most used first."""
        es = [(g[key], g) for g in gs if g.get(key)]
        def key_of(e):
            return (e["kind"], e["ease"], (e.get("from") or e.get("to")) if e["kind"] == "slide" else None)
        c = Counter(key_of(e) for e, _ in es)
        out = []
        for (kind, ease, side), m in c.most_common(5):
            sel = [e for e, _ in es if key_of(e) == (kind, ease, side)]
            d = {"kind": kind, "ease": ease, "share_pct": round(100 * m / len(es)), "n": m,
                 "duration_s": round(statistics.median(e["duration_s"] for e in sel), 3),
                 "overshoot": round(statistics.median(e["overshoot"] for e in sel), 3),
                 "fade": sum(e["fade"] for e in sel) >= m / 2}
            if side:
                d["from" if key == "entrance" else "to"] = side
                d["distance_pct"] = round(statistics.median(e.get("distance_pct", 0) for e in sel), 1)
            if kind == "scale":
                d["scale_from" if key == "entrance" else "scale_to"] = round(statistics.median(
                    e.get("scale_from", e.get("scale_to", 1.0)) for e in sel), 2)
            out.append(d)
        return out
    sec = Counter(g["secondary"] for g in gs)
    return {
        "kinds": {k: round(100 * v / tot) for k, v in kinds.most_common()},
        "kinds_source": Counter(g.get("kind_source", "code") for g in gs).most_common(1)[0][0],
        "measured": len(gs),
        "per_min_measured": round(len(gs) / mins, 1),
        # the same sum report.py shows per video: graphic hold over runtime, one source for look.md
        "share_pct_measured": round(100 * sum(min(r["duration_s"], sum(g["hold_s"] for g in kept(r))) for r in rows)
                                    / (mins * 60)),
        "hold_s_measured": round(statistics.median(g["hold_s"] for g in gs), 2),
        "layout": layout,
        "entrances": group("entrance"),
        "exits": group("exit"),
        "secondary_motion": {k: round(100 * v / len(gs)) for k, v in sec.most_common()},
        "blur_behind_pct": round(100 * sum(g.get("blur_behind", False) for g in gs) / len(gs)),
    }


def save_heatmap(grid, path, still=None):
    """The grid over a dimmed frame of the creator, warm where graphics sit most."""
    from PIL import Image
    g = np.array(grid, float) / 100
    gh, gw = g.shape
    W, H = (360, round(360 * gh / gw)) if gh >= gw else (round(360 * gw / gh), 360)
    W, H = (360, 640) if gh > gw else (640, 360)
    base = np.asarray(Image.open(still).convert("RGB").resize((W, H)), np.float32) * 0.45 if still \
        else np.full((H, W, 3), 30, np.float32)
    heat = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 255
    col = np.stack([255 * np.clip(heat * 1.6, 0, 1), 200 * np.clip(heat * 1.2 - 0.2, 0, 1),
                    40 * np.ones_like(heat)], -1)
    a = np.clip(heat * 0.85, 0, 0.85)[..., None]
    Image.fromarray((base * (1 - a) + col * a).astype(np.uint8)).save(path, quality=85)


def merge(outdir):
    rows = [json.loads(p.read_text()) for p in sorted((outdir / "video").glob("*.graphics.json"))]
    sp = outdir / "style.json"
    style = json.loads(sp.read_text()) if sp.exists() else {"handle": outdir.name}
    portrait = not rows or rows[0]["height"] >= rows[0]["width"]
    grid = heatmap(rows, portrait)
    s = summarise(rows, style.get("face"))
    gfx = dict(style.get("graphics") or {})
    gfx.update(s)
    if s["layout"]:
        gfx["layout"]["grid"] = grid
        still = next((outdir / "video").glob("*.mp4"), None)
        frame = None
        if still:
            frame = outdir / "graphics" / "_still.jpg"
            frame.parent.mkdir(exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", str(still), "-frames:v", "1",
                            str(frame)], check=False)
        save_heatmap(grid, outdir / "graphics" / "heatmap.png", frame if frame and frame.exists() else None)
    gfx["crop_palette"] = crop_palette(outdir, rows)
    style["graphics"] = gfx
    split = split_layout(s["layout"], style.get("face"), portrait)
    if split:
        style["layout"] = split
    elif (style.get("layout") or {}).get("source") == "graphics.py":
        style.pop("layout")
    sp.write_text(json.dumps(style, indent=2))
    return gfx


def split_layout(layout, face, portrait):
    """style.json "layout" for style-edit's split screen (vertical only): the graphics sit in the
    top panel 60%+ of their time, end above 55% of the height, keep off the face, and the face
    is in the lower half. seam: just under the usual graphic. None for an overlay creator."""
    if not portrait or not layout or not (face or {}).get("y_pct"):
        return None
    x, y, w, h = layout["median_box"]
    if layout["zones_pct"].get("top", 0) < 60 or y + h > 55 or layout.get("covers_face_pct", 0) > 10 or face["y_pct"] < 50:
        return None
    return {"mode": "split", "seam": int(min(60, max(35, round(y + h + 2)))), "source": "graphics.py"}


def crop_palette(outdir, rows, k=6):
    """The colours of the graphics themselves (their crops), not the whole frame: what an
    edit copying this creator would put on screen. Share of crop pixels, biggest first."""
    from PIL import Image
    from look import hexc, kmeans
    px = []
    for r in rows:
        for g in kept(r):
            p = outdir / (g.get("crop") or "")
            if g.get("crop") and p.exists():
                im = Image.open(p).convert("RGB")
                im.thumbnail((48, 48))
                px.append(np.asarray(im).reshape(-1, 3))
    if not px:
        return []
    lab, cen = kmeans(np.concatenate(px), k)
    cnt = np.bincount(lab, minlength=len(cen))
    return [{"hex": hexc(cen[j]), "pct": round(100 * cnt[j] / len(lab))} for j in np.argsort(-cnt)]


def measure_one(job):
    """One video's graphics.json (worker process)."""
    p, crop_dir = job
    look_p, vis_p = p.with_suffix(".look.json"), p.with_suffix(".visual.json")
    look = json.loads(look_p.read_text()) if look_p.exists() else None
    vis = json.loads(vis_p.read_text()) if vis_p.exists() else None
    if not look:
        print(f"  {p.stem}: no look.json (run look.py measure first): no speaker mask", file=sys.stderr)
    cap = (look or {}).get("captions") or {}
    band = ((cap["y_pct"] - 4) / 100, (cap["y_pct"] + 4) / 100) if cap.get("y_pct") else None
    print(f"{p.stem} measuring", file=sys.stderr)
    r = measure_video(p, look, vis, band, crop_dir)
    p.with_suffix(".graphics.json").write_text(json.dumps(r, indent=1))
    print(f"  {p.stem}: {len(r['graphics'])} graphics: " + ", ".join(
        f"{g['t_in']}s {g['kind']} {(g['entrance'] or {}).get('kind')}/{(g['entrance'] or {}).get('ease')}"
        for g in r["graphics"][:6]), file=sys.stderr)


def cmd_measure(a):
    outdir = OUT_ROOT / slug(a.handle)
    vids = sorted((outdir / "video").glob("*.mp4"))
    if a.ids:
        vids = [p for p in vids if p.stem in a.ids.split(",")]
    if not vids:
        sys.exit(f"no videos in {outdir / 'video'}. Run visual.py download first.")
    todo = [p for p in vids if a.force or not p.with_suffix(".graphics.json").exists()]
    for p in vids:
        if p not in todo:
            print(f"{p.stem} cached", file=sys.stderr)
    from parallel import pmap
    pmap(measure_one, [(p, outdir / "graphics") for p in todo])
    g = merge(outdir)
    if a.json:
        print(json.dumps({k: g.get(k) for k in ("kinds", "layout", "entrances", "secondary_motion")}, indent=1))
    print(summary_line(g, outdir / "style.json"))


def summary_line(g, path):
    """One line for Claude's context: the full measure is in style.json ("graphics"), --json prints it."""
    top = lambda d, n=3: ", ".join(f"{k} {v}%" for k, v in list((d or {}).items())[:n]) or "none"
    e = (g.get("entrances") or [{}])[0]
    ent = f"{e['kind']}/{e['ease']} {e['share_pct']}%" if e else "none"
    return (f"graphics: {g.get('measured', 0)} measured, {g.get('per_min_measured', 0)}/min, kinds {top(g.get('kinds'))}; "
            f"entrance {ent}; zones {top(((g.get('layout') or {}).get('zones_pct')), 4)} -> {path} (\"graphics\")")


# ---------- self-check ----------

def moving_clip(mp4, W=360, H=640, FPS=30):
    """An 8 s vlog-style fixture, no speaker: the camera pans the whole time over three shots (cuts at
    2.5 s and 5.5 s), with a flat sky band in the second shot and a bright ball moving through
    the third. Hand-labelled truth, (t_in, t_out, box as fractions):
      a product card (border, text bars) 1.0-4.0 s across the first cut,
      an app tile 4.5-7.0 s across the second cut,
      a screenshot 6.2-7.8 s over the panning third shot."""
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(5)

    def shot(seed, sky=False):
        r = np.random.default_rng(seed)
        big = np.asarray(Image.fromarray((r.random((H // 16, (W + 400) // 16, 3)) * 170 + 40).astype(np.uint8))
                         .resize((W + 400, H), Image.BICUBIC)).astype(np.float32)
        if sky:
            big[:150] = (150, 190, 235)
        return big
    shots = [shot(11), shot(12, sky=True), shot(13)]
    card = Image.new("RGB", (280, 160), "white")
    d = ImageDraw.Draw(card)
    d.rectangle((0, 0, 279, 159), outline=(30, 30, 30), width=4)
    for k in range(4):
        d.rectangle((20, 24 + 30 * k, 20 + 220 - 40 * (k % 2), 36 + 30 * k), fill=(40, 40, 40))
    tile = Image.new("RGB", (90, 90), (255, 92, 40))
    ImageDraw.Draw(tile).ellipse((25, 25, 65, 65), fill="white")
    page = Image.new("RGB", (200, 140), (245, 246, 248))
    d = ImageDraw.Draw(page)
    d.rectangle((0, 0, 199, 22), fill=(60, 64, 72))
    for k in range(5):
        d.rectangle((14, 34 + 20 * k, 180 - 25 * (k % 3), 42 + 20 * k), fill=(120, 124, 130))
    over = [(np.asarray(card, np.float32), 40, 60, 1.0, 4.0), (np.asarray(tile, np.float32), 240, 420, 4.5, 7.0),
            (np.asarray(page, np.float32), 20, 470, 6.2, 7.8)]
    truth = [(t0, t1, [x / W, y / H, im.shape[1] / W, im.shape[0] / H]) for im, x, y, t0, t1 in over]
    frames = []
    for i in range(8 * FPS):
        t = i / FPS
        k = 0 if t < 2.5 else 1 if t < 5.5 else 2
        off = int(40 + 45 * t) % 400
        img = shots[k][:, off:off + W].copy()
        if k == 2:   # a bright ball rolling through the shot
            cx, cy = int(60 + 60 * (t - 5.5)), 300
            img[cy - 25:cy + 25, max(0, cx - 25):cx + 25] = 250
        for im, x, y, t0, t1 in over:
            if t0 <= t < t1:
                img[y:y + im.shape[0], x:x + im.shape[1]] = im
        frames.append(np.clip(img + rng.normal(0, 2, img.shape), 0, 255).astype(np.uint8))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                    "-i", "-", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", str(mp4)],
                   input=b"".join(f.tobytes() for f in frames), check=True)
    return truth


def precision_recall(found, truth):
    """A found graphic is right when its box overlaps a true one (IoU 0.5) while that one is up."""
    def hit(g, tr):
        return iou(g["box"], tr[2]) >= 0.5 and min(g["t_out"], tr[1]) - max(g["t_in"], tr[0]) > 0.3
    right = sum(any(hit(g, tr) for tr in truth) for g in found)
    seen = sum(any(hit(g, tr) for g in found) for tr in truth)
    return (right / len(found) if found else 0.0), seen / len(truth)


def demo_moving():
    """No speaker, a moving camera: the overlay mode finds the three graphics and nothing else."""
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = Path(tmp) / "m.mp4"
        truth = moving_clip(mp4)
        r = measure_video(mp4, None, {"cuts": [2.5, 5.5], "zooms": []}, None, None)
        p, rc = precision_recall(r["graphics"], truth)
        print(f"  moving footage ({r.get('mode')} mode): precision {p:.2f}, recall {rc:.2f}, "
              + "; ".join(f"{g['t_in']}-{g['t_out']} {[round(v, 2) for v in g['box']]} {g['kind']}" for g in r["graphics"]))
        assert r.get("mode") == "overlay" and p >= 0.75 and rc == 1.0, (p, rc, r["graphics"])
        tile = next(g for g in r["graphics"] if iou(g["box"], truth[1][2]) >= 0.5)
        assert tile["kind"] == "logo", tile


def demo_kinds():
    """An app icon with its name under it is a logo, not a text card; a text card stays one."""
    from PIL import Image, ImageDraw, ImageFont
    icon = Image.new("RGB", (64, 64), (70, 110, 60))            # a crop round it: the wall shows at the corners
    d = ImageDraw.Draw(icon)
    d.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(255, 92, 40))
    d.ellipse((18, 18, 46, 46), fill="white")
    card = Image.new("RGB", (600, 300), "white")
    d = ImageDraw.Draw(card)
    for k, line in enumerate(["3 things nobody", "tells you about", "pricing pages"]):
        d.text((30, 30 + 80 * k), line, fill=(20, 20, 20), font=ImageFont.load_default(size=56))
    photo = Image.fromarray((np.random.default_rng(1).random((64, 64, 3)) * 255).astype(np.uint8))
    ic, cc, pc = (colour_count(np.asarray(im)) for im in (icon, card, photo))
    print(f"  colours: icon {ic}, text card {cc}, photo {pc}")
    g = {"moving": 0.5, "flat": True, "secondary": "still"}
    assert guess_kind({**g, "text_lines": 1, "colours": ic, "aspect": 1.0, "area_pct": 2.2}, None) == "logo"
    assert guess_kind({**g, "text_lines": 3, "colours": cc, "aspect": 2.0, "area_pct": 14}, None) == "text card"
    assert guess_kind({**g, "flat": False, "text_lines": 0, "colours": pc, "aspect": 1.0, "area_pct": 3}, None) == "photo"
    # the corner of a wide red title banner (measured case): its title line runs out of the box
    corner = {**g, "text_lines": 0, "colours": 7, "aspect": 0.83, "area_pct": 1.3}
    look = {"samples": [{"t": 4.0, "lines": [["BUSINESS OR KIDS?", [0.1, 0.2, 0.8, 0.05], False]]}]}
    assert text_crossing([0.07, 0.18, 0.14, 0.09], 3.8, 4.8, look) == 1
    assert guess_kind({**corner, "text_crossing": 1}, None) != "logo"


def demo():
    """6 s, 360 x 640, 30 fps, a still textured room. A white card with grey lines slides up
    into the top third over 0.3 s (power3.out) at 1.0 s and fades out over 0.2 s at 3.0 s.
    A blue card scales in from 0.6 with an overshoot (back.out) at 3.5 s, drifts right while
    up, and is cut away at 5.5 s. Both must be found with the right motion, nothing else."""
    from PIL import Image, ImageDraw
    W, H, FPS = 360, 640, 30
    rng = np.random.default_rng(3)
    room = np.asarray(Image.fromarray((rng.random((H // 20, W // 20, 3)) * 120 + 60).astype(np.uint8))
                      .resize((W, H), Image.BICUBIC)).astype(np.float32)
    card = Image.new("RGB", (300, 160), "white")
    d = ImageDraw.Draw(card)
    for k in range(6):
        d.rectangle([16, 16 + 22 * k, 16 + 260 - 30 * (k % 3), 26 + 22 * k], fill=(90, 90, 90))
    card = np.asarray(card, np.float32)
    blue = np.zeros((140, 140, 3), np.float32)
    blue[:] = (40, 90, 230)
    blue[30:110, 30:110] = (250, 250, 250)

    def paste(img, c, cx, cy, s=1.0, a=1.0):
        h, w = c.shape[:2]
        if s != 1.0:
            c = np.asarray(Image.fromarray(c.astype(np.uint8)).resize((max(2, round(w * s)), max(2, round(h * s)))),
                           np.float32)
            h, w = c.shape[:2]
        x0, y0 = round(cx - w / 2), round(cy - h / 2)
        xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
        if xb > xa and yb > ya:
            img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - a) + c[ya - y0:yb - y0, xa - x0:xb - x0] * a

    frames = []
    for i in range(6 * FPS):
        t = i / FPS
        img = room.copy()
        if 1.0 <= t < 3.2:
            u = min(1.0, (t - 1.0) / 0.3)
            y = 170 + (1 - EASES["power3.out"](u)) * 420
            a = 1.0 if t < 3.0 else 1 - (t - 3.0) / 0.2
            paste(img, card, 180, y, a=a)
        if 3.5 <= t < 5.5:
            u = min(1.0, (t - 3.5) / 0.4)
            s = 0.6 + 0.4 * float(EASES["back.out(1.7)"](u))
            paste(img, blue, 110 + 20 * (t - 3.5), 400, s=s)
        frames.append(np.clip(img + rng.normal(0, 2, img.shape), 0, 255).astype(np.uint8))
    with tempfile.TemporaryDirectory() as tmp:
        mp4 = Path(tmp) / "g.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                        "-r", str(FPS), "-i", "-", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", str(mp4)],
                       input=b"".join(f.tobytes() for f in frames), check=True)
        r = measure_video(mp4, None, {"cuts": [], "zooms": []}, None, Path(tmp) / "graphics")
        gs = r["graphics"]
        for g in gs:
            print(g["t_in"], g["t_out"], g["box"], g["secondary"], g["entrance"], g["exit"])
        assert len(gs) == 2, gs
        a, b = gs
        assert 0.8 <= a["t_in"] <= 1.4 and 2.9 <= a["t_out"] <= 3.4, a
        assert zone(a["box"]) == "top" and abs(a["box"][1] + a["box"][3] / 2 - 170 / H) < 0.04, a["box"]
        e = a["entrance"]
        assert e["kind"] == "slide" and e["from"] == "bottom", e
        assert e["ease"] in ("power2.out", "power3.out", "power4.out", "expo.out"), e
        assert 0.2 <= e["duration_s"] <= 0.42, e
        assert a["exit"] and a["exit"]["fade"] and 0.1 <= a["exit"]["duration_s"] <= 0.35, a["exit"]
        e = b["entrance"]
        assert e["kind"] == "scale" and e["scale_from"] < 0.85 and e["overshoot"] >= 0.03, e
        assert e["ease"].startswith("back.out"), e
        assert b["secondary"] == "drift" and a["secondary"] == "still", (a["secondary"], b["secondary"])
        assert Path(tmp, a["crop"]).exists()
        s = summarise([r])
        assert s["layout"]["zones_pct"]["top"] > 0 and s["entrances"][0]["n"] == 1, s
        assert ease_value("power3.in", 0.5) < 0.5 < float(EASES["power3.out"](0.5))
        grid = heatmap([r])
        assert max(map(max, grid)) == 100 and len(grid) == GRID[0]
        line = summary_line(s, "style.json")   # measure prints one line, not the JSON block
        assert "\n" not in line and "{" not in line and len(line) < 300 and "slide/" in line, line
    demo_kinds()
    demo_moving()
    # style-edit's split layout when the graphics own the top panel and the speaker sits below it
    top = {"zones_pct": {"top": 82, "middle": 10, "bottom": 0, "full": 8}, "median_box": [8, 9, 84, 33], "covers_face_pct": 0}
    assert split_layout(top, {"y_pct": 71}, True) == {"mode": "split", "seam": 44, "source": "graphics.py"}
    assert split_layout(top, {"y_pct": 38}, True) is None and split_layout(top, {"y_pct": 71}, False) is None
    assert split_layout({**top, "zones_pct": {"top": 30, "middle": 60, "bottom": 10, "full": 0}}, {"y_pct": 71}, True) is None
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure")
    p.add_argument("handle")
    p.add_argument("--force", action="store_true")
    p.add_argument("--ids", default=None, help="only these video ids")
    p.add_argument("--json", action="store_true", help="print the measured block in full")
    p.set_defaults(fn=cmd_measure)
    p = sub.add_parser("merge")
    p.add_argument("handle")
    p.add_argument("--json", action="store_true", help="print the merged block in full")
    p.set_defaults(fn=lambda a: (lambda g: print(json.dumps(g, indent=1) if a.json else
                                                 summary_line(g, OUT_ROOT / slug(a.handle) / "style.json")))(
        merge(OUT_ROOT / slug(a.handle))))
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
