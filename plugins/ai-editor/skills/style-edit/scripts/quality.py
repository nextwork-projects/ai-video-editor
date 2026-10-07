#!/usr/bin/env python3
"""The render checks that need every frame, the audio, or the pixels of a settled card.
check.py render runs them after its own 4-a-second pass; they print in its FAIL / WARN / LOOK style.

    ~/.ai-video-editor/venv/bin/python quality.py demo     self-check, synthetic data, no video
    python3 quality.py normalize <video>   opt-in only: <video stem>-normalized.mp4, one gain to -14 LUFS
                                           (never past a -1 dBTP peak), video copied, no compression or denoise

Every frame of the render (half size) is compared with the cut behind it, as check.py does:
  freeze      the render repeats a frame while the footage behind it moves (a dropped frame)
  spike       a card's region changes in one isolated frame (a part popping in with no entrance)
  reversal    a card's outline turns back at speed (jitter), not easing into the turn
  flash       a card shows its finished state on its first frame, then animates in
  lands       when the card is half drawn, against its word (plan start + plan.CARD_LEAD_S;
              a scene: its trigger word in captions.json, half its transition = 0.31 s x the motion k)
  static      the longest stretch where no card moves and nothing is cut
  rhythm      cuts and card entrances a minute against the creator's style.json
On the frame each card has settled (the same moment as its still):
  overflow    a text card's content reaching the card's own edge
  contrast    WCAG ratio, at the worst spot: caption fill against what is drawn right around it
              (its stroke, else the footage; full size), a text card's text against its ground
  generic     the AI-default look: near-black panel + one neon accent, a blue-purple gradient,
              emoji, or a card that is mostly stock icons
On each zoom move (frames round its start and end, the face band, ORB + a similarity fit frame to frame):
  zoom snap   one frame carries most of the change (an instant step, not a move)
  zoom jerk   the zoom's speed reverses or surges again mid-move (a smooth move rises and falls once)
On the audio: integrated loudness and true peak (ffmpeg ebur128), and every sound cue's level
against the voice (render minus cut, sample-aligned). On the files: a render older than its inputs.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))

# ---- thresholds. Each one says where it comes from.
FREEZE_D = 0.08        # whole-frame mean grey change (0-255, 64x36) under this = a repeated frame. An
                       # encoded duplicate measures 0.00-0.05; a live camera never drops under ~0.15.
FOOTAGE_MOVING = 0.4   # ...while the cut behind it changed this much at the same frame
FREEZE_RUN = 3         # 3 repeated frames = 0.1 s, the point where a held frame reads as a stutter
SPIKE_X = 3.0          # an isolated jump: this many times every neighbour within 2 frames
SPIKE_ABS = 2.0        # and a mean grey change over the card's box of at least this
REV_RATIO = 0.35       # a turn where speed going in AND coming out are both over this share of peak:
                       # an ease decelerates into a turn, so one side of a smooth turn is near zero
REV_MIN_PX = 3         # px at half size (6 px on the output): smaller travel is not visible
JUMP_SHARE = 0.25      # an outline that moves over this share of the box in one frame: something
                       # entered or left, not one thing moving; the series restarts there
LAND_SHARE = 0.5       # a card has landed when it carries half the ink it has 0.6 s in
LAND_TOL = 0.15        # s. ITU-R BT.1359: picture after sound is noticed from ~0.1 s and objected to
                       # from ~0.185 s; picture before sound is tolerated longer. Late = FAIL, early = WARN
FLASH_SHARE = 0.5      # first-frame ink over this share of the landed ink, then dropping: a flash
WHOLE_SHARE = 0.8      # first-frame ink over this share and staying: no entrance at all
MOVE_D = 0.3           # a card region changing more than this a frame is moving (encoded stills: < 0.1)
EDGE_IN = (0.008, 0.025)   # strip inside a card's edge (share of its width/height) where its content
                       # should never be: every template pads text by 7% (Anims.tsx fit at 86%)
EDGE_ROWS = 0.06       # content in more than this share of the strip's length = runs into the edge
CORNER = 0.12          # strip ends skipped: rounded corners show the footage
CAP_EDGE = 0.015       # captions this close to the frame's side are cut off by it
from plan import CONTRAST_MIN as CONTRAST_FAIL, CONTRAST_TARGET   # noqa: E402  WCAG 1.4.3 for large text; one line for plan and check
CONTRAST_WARN = 4.5    # WCAG AA for body text: the margin moving footage needs
ZOOM_MIN_LOG = 0.03    # a zoom changing log-scale less than this (3%) is too small to judge
SNAP_SHARE = 0.6       # one frame carrying this share of a zoom's change is a snap. A 0.16 s power2.out punch
                       # puts 39% in its first frame at 30 fps; an instant punch puts 100%
JERK_SHARE = 0.3       # a second speed peak (or a reversal) over this share of the first: the move surges
DARK_V, DARK_SHARE = 0.2, 0.45          # near-black panel: value under 0.2, low colour, 45%+ of the card
NEON_S, NEON_V, NEON_SHARE = 0.4, 0.75, 0.003   # bright saturated pixels, 0.3%+ of the card
NEON_HUES = (90, 330)  # degrees: green-cyan-blue-violet-magenta, the glow hues; not print reds/yellows
ONE_HUE = 0.4          # the accent: the 30-degree hue slice holding the most saturated pixels, 40%+ of
                       # them (a logo on the card brings its own colours, so not all of them)
GRAD_HUES, GRAD_SHARE = (220, 300), 0.3  # blue to purple over 30%+ of the card
ICONS_PER_CARD = 3     # a 4th stock icon in one card is the icon-grid template
LUFS_LOW, LUFS_HIGH = -23.0, -9.0  # platforms play at about -14 LUFS; they turn loud down but rarely
                       # turn quiet up. 9 dB under (EBU R128 broadcast level) plays clearly quieter
TP_WARN, TP_FAIL = -1.0, 0.0       # dBTP. -1 is the streaming recommendation (AES TD1004); over 0 clips
SFX_HOT, SFX_LOST = 0.0, -20.0     # dB against the speech level (sfx.py's: mean power of the 50 ms
                       # windows with speech). Over it masks the word; 20 dB under, speech masks it
RATE_BAND = (0.5, 2.0) # rhythm against the creator: a 45 s video holds ~5-15 events, sd ~sqrt(n), so
                       # inside half to double is noise; outside it is a different pace
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]")


def F(level, t, what, fix):
    from check import finding
    return finding(level, t, what, fix)


# ---------------------------------------------------------------- pure measurements (demo-tested)

def rel_lum(rgb):
    """WCAG relative luminance of an array ending in 3 (RGB, 0-255)."""
    import numpy as np
    c = np.asarray(rgb, float) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return c[..., 0] * 0.2126 + c[..., 1] * 0.7152 + c[..., 2] * 0.0722


def ratio(a, b):
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def worst_contrast(rgb, text, ring_px):
    """Text pixels (mask) against the ring around them, at the ring's worst: its 90th percentile
    toward the text's own luminance. One bright patch under one word is what stops it reading."""
    import cv2
    import numpy as np
    if text.sum() < 20:
        return None
    # a round kernel: a square one reaches 1.4x as far on every curve and diagonal, past a stroke
    grow = lambda r: cv2.dilate(text.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
    ring = grow(ring_px + 1) & ~grow(1)       # skip the 1 px anti-aliased edge of the glyphs
    if ring.sum() < 20:
        return None
    L = rel_lum(rgb[..., ::-1])               # BGR in
    lt, lr = float(np.median(L[text])), L[ring]
    worst = float(np.percentile(lr, 90 if lt > np.median(lr) else 10))
    return round(ratio(lt, worst), 2)


def freezes(d_render, d_behind, hidden=()):
    """Runs of repeated render frames while the footage moved: [(first, length)]. Frames in `hidden` (a
    full-frame scene covers the footage) never count."""
    out, run = [], None
    for i, (r, b) in enumerate(zip(d_render, d_behind)):
        if r < FREEZE_D and b > FOOTAGE_MOVING and i not in hidden:
            run = run or [i, 0]
            run[1] += 1
        else:
            if run:
                out.append(tuple(run))
            run = None
    if run:
        out.append(tuple(run))
    return out


def spikes(d, skip=()):
    """Isolated one-frame jumps in a card region's change series."""
    out = []
    for i in range(1, len(d)):
        if i in skip or d[i] < SPIKE_ABS:
            continue
        nb = list(d[max(0, i - 2):i]) + list(d[i + 1:i + 3])
        if nb and d[i] >= SPIKE_X * max(max(nb), 0.1):
            out.append(i)
    return out


def jitter(series):
    """Turns in a position series taken at speed on both sides: [(index, min(in, out) / peak)]."""
    import numpy as np
    d = np.diff(np.asarray(series, float))
    peak = float(np.abs(d).max()) if len(d) else 0.0
    if peak < REV_MIN_PX:
        return []
    out, last = [], None          # last = (sign, speed) of the last non-zero step
    for i, v in enumerate(d):
        if v == 0:
            continue
        if last and np.sign(v) != last[0]:
            r = min(last[1], abs(v)) / peak
            if r >= REV_RATIO and min(last[1], abs(v)) >= 1:
                out.append((i, round(r, 2)))
        last = (np.sign(v), abs(v))
    return out


def scene_land(c, words, k, lead=None):
    """(word time, landed time) of a scene card. The word is the trigger word's first time at or after
    the card's own word (plan starts a scene SCENE_LEAD_S x k early, an overlay card OVERLAY_LEAD_S x k
    early: pass that as `lead`, so start + CARD_LEAD_S is not it).
    A scene counts as landed when its transition is half done: start + 0.31 s x k (Scene.tsx runs 0.62 s x k)."""
    from plan import CARD_LEAD_S, SCENE_LEAD_S, clean
    lead = SCENE_LEAD_S if lead is None else lead
    t, floor = clean(c["trigger_word"]).lower(), c["start"] + CARD_LEAD_S - 0.05
    hit = next((w["start"] for w in words if clean(w["text"]).lower() == t and w["start"] >= floor), None)
    word = hit if hit is not None else c["start"] + CARD_LEAD_S + lead * k
    return word, c["start"] + 0.31 * k


def landing(area, f0, fps):
    """(frame it landed, first-frame verdict) from a card's ink area per frame, area[0] = frame f0-3.
    verdict: None, 'flash' (whole then gone) or 'whole' (no entrance)."""
    import numpy as np
    a = np.asarray(area, float)
    pre, i0 = a[2], 3                       # the frame before the card exists, and its first frame
    ref = a[i0:i0 + int(0.6 * fps) + 1].max() - pre
    if ref <= 0 or pre > 0.25 * a.max():    # something else was in the box: not this card's entrance
        return None, None
    rise = a - pre
    hit = np.nonzero(rise[i0 - 2:] >= LAND_SHARE * ref)[0]
    land = f0 - 2 + int(hit[0]) if len(hit) else None
    first, after = rise[i0], rise[i0 + 1:i0 + 4]
    verdict = None
    if first >= FLASH_SHARE * ref and len(after) and after.min() < 0.5 * first:
        verdict = "flash"
    elif first >= WHOLE_SHARE * ref:
        verdict = "whole"
    return land, verdict


def edit_events(f):
    """measure_edit's counter on 64x36 grey frames: hard cuts, jump cuts, moves (frame indices)."""
    import numpy as np
    d = np.concatenate([[0.0], np.abs(np.diff(f, axis=0)).mean(axis=(1, 2))])
    n, cuts, jumps, moves = len(d), [], [], []
    for i in range(1, n):
        nb = np.concatenate([d[max(1, i - 3):i], d[i + 1:i + 4]])
        peak = nb.max() if len(nb) else 0.0
        if d[i] >= 12 and d[i] >= 3 * peak:
            cuts.append(i)
        elif 4 <= d[i] < 12 and d[i] >= 5 * max(peak, 0.2):
            jumps.append(i)
    i = 1
    while i < n:
        if d[i] >= 5:
            j = i
            while j + 1 < n and d[j + 1] >= 5:
                j += 1
            if j - i + 1 >= 4 and np.abs(f[j] - f[i - 1]).mean() >= 12:
                moves.append((i, j))
            i = j + 1
        else:
            i += 1
    return d, cuts, jumps, moves


def edge_overflow(grey, bg):
    """Share of each inner edge strip of a card crop (grey 0-255) holding content: {side: share}."""
    import numpy as np
    h, w = grey.shape
    content = np.abs(grey.astype(float) - bg) > 50
    a, b = max(1, int(EDGE_IN[0] * w)), max(2, int(EDGE_IN[1] * w))
    av, bv = max(1, int(EDGE_IN[0] * h)), max(2, int(EDGE_IN[1] * h))
    cr, cc = int(CORNER * h), int(CORNER * w)
    strips = {"left": content[cr:h - cr, a:b].any(axis=1), "right": content[cr:h - cr, w - b:w - a].any(axis=1),
              "top": content[av:bv, cc:w - cc].any(axis=0), "bottom": content[h - bv:h - av, cc:w - cc].any(axis=0)}
    return {k: round(float(v.mean()), 3) if v.size else 0.0 for k, v in strips.items()}


def panel_crop(frame, bg, box, ink_diff, split):
    """(crop, panel grey level or None) for a settled card. Overlay: the drawn panel, found as the
    biggest drawn region around the plan box (a panel can hug its text, smaller than the box).
    Split: the plan box on the ground. The level is None when the crop's border is not one flat
    ground, so there is no edge for content to run into."""
    import cv2
    import numpy as np
    x0, y0, x1, y1 = box
    H, W = frame.shape[:2]
    if not split:
        px, py = int(0.03 * W), int(0.02 * H)
        X0, Y0, X1, Y1 = max(0, x0 - px), max(0, y0 - py), min(W, x1 + px), min(H, y1 + py)
        diff = cv2.absdiff(cv2.GaussianBlur(frame[Y0:Y1, X0:X1], (5, 5), 0),
                           cv2.GaussianBlur(bg[Y0:Y1, X0:X1], (5, 5), 0)).max(axis=2)
        ink = cv2.morphologyEx((diff > ink_diff).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(ink)
        if n < 2:
            return None, None
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        bx, by, bw, bh = stats[k, :4]
        x0, y0, x1, y1 = X0 + bx, Y0 + by, X0 + bx + bw, Y0 + by + bh
    if y1 - y0 < 12 or x1 - x0 < 12:
        return None, None
    g = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(float)
    h, w = g.shape
    a, b = max(1, int(0.03 * min(h, w))), max(2, int(0.06 * min(h, w)))
    strips = [g[a:b, w // 4:3 * w // 4], g[h - b:h - a, w // 4:3 * w // 4],
              g[h // 4:3 * h // 4, a:b], g[h // 4:3 * h // 4, w - b:w - a]]
    flat = [float(np.median(st)) for st in strips if np.mean(np.abs(st - np.median(st)) < 12) > 0.8]
    agree = [[v for v in flat if abs(v - u) <= 12] for u in flat]     # a flat shadow strip is not the panel
    best = max(agree, key=len, default=[])
    if len(best) < 2:
        return frame[y0:y1, x0:x1], None
    level = float(np.median(best))
    # A drop shadow is drawn too: trim edge rows and columns that are not the panel's ground
    off = lambda v: np.mean(np.abs(v - level) <= 12) < 0.8
    for _ in range(h // 4):
        if off(g[0, w // 8:-w // 8]): g, y0 = g[1:], y0 + 1
        elif off(g[-1, w // 8:-w // 8]): g, y1 = g[:-1], y1 - 1
        else: break
    for _ in range(w // 4):
        if off(g[g.shape[0] // 8:-g.shape[0] // 8 or None, 0]): g, x0 = g[:, 1:], x0 + 1
        elif off(g[g.shape[0] // 8:-g.shape[0] // 8 or None, -1]): g, x1 = g[:, :-1], x1 - 1
        else: break
    return frame[y0:y1, x0:x1], level


def caption_fill(frame, colours, ys, font_px, text):
    """(rows, fill mask, touches the frame's side) for the caption on a frame, or None. The caption
    is centred on x 50% at one of ys (px); its fill is the caption colour. Rows: the font size
    around the y where the most fill sits inside the span its text would take."""
    import cv2
    import numpy as np
    H, W = frame.shape[:2]
    half = min(W / 2, 0.33 * font_px * max(1, len(text)) * 1.25 + font_px)
    xa, xb = int(W / 2 - half), int(W / 2 + half)
    near = np.zeros((H, W), bool)
    f = frame.astype(np.int16)
    lo, hi = max(0, int(min(ys) - font_px)), min(H, int(max(ys) + font_px))
    if hi <= lo:
        return None
    # footage close to the fill colour (white captions on a bright desk) is not the fill: the
    # tolerance shrinks to under half the distance between the fill and the band's typical colour
    typical = np.median(f[lo:hi, xa:xb].reshape(-1, 3), axis=0)
    for c in colours:
        tol = min(60, max(8, 0.4 * float(np.abs(typical - c).max())))
        near |= np.abs(f - c).max(axis=2) < tol
    per_row = near[lo:hi, xa:xb].sum(axis=1).astype(float)
    k = max(1, int(font_px * 0.7))
    score = np.convolve(per_row, np.ones(k), "same")
    yc = lo + int(np.argmax(score))
    r0, r1 = max(0, int(yc - 0.75 * font_px)), min(H, int(yc + 0.75 * font_px))
    fill = np.zeros((r1 - r0, W), bool)
    fill[:, xa:xb] = near[r0:r1, xa:xb]
    # keep the glyphs: blobs as tall as a letter (specks of light in the footage are not), joined
    # to the run of text through the centre of the span
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fill.astype(np.uint8))
    fill &= np.isin(lab, [i for i in range(1, n) if stats[i, cv2.CC_STAT_HEIGHT] >= 0.3 * font_px])
    merged = cv2.dilate(fill.astype(np.uint8), np.ones((3, max(3, int(0.35 * font_px))), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(merged)
    keep = [i for i in range(1, n) if stats[i, cv2.CC_STAT_LEFT] <= W / 2 + 0.1 * W
            and stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] >= W / 2 - 0.1 * W]
    fill &= np.isin(lab, keep)
    if fill.sum() < 30:
        return None
    xs = np.nonzero(fill.any(axis=0))[0]
    return slice(r0, r1), fill, bool(xs.min() < CAP_EDGE * W or xs.max() > (1 - CAP_EDGE) * W)


def caption_lines(frame, colours, y, font_px):
    """How many lines of caption text sit round row y (the page's centre, Captions.tsx translateY -50%):
    bands of caption-coloured glyphs (blobs a letter tall) within two font sizes of it."""
    import cv2
    import numpy as np
    H, W = frame.shape[:2]
    lo, hi = max(0, int(y - 2 * font_px)), min(H, int(y + 2 * font_px))
    f = frame[lo:hi].astype(np.int16)
    if not len(f):
        return 0
    typical = np.median(f.reshape(-1, 3), axis=0)
    near = np.zeros(f.shape[:2], bool)
    for c in colours:
        near |= np.abs(f - c).max(axis=2) < min(60, max(8, 0.4 * float(np.abs(typical - c).max())))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(near.astype(np.uint8))
    near = np.isin(lab, [i for i in range(1, n) if 0.3 * font_px <= stats[i, cv2.CC_STAT_HEIGHT] <= 1.3 * font_px])
    # a line of words: glyphs joined across their gaps, running through the middle of the frame
    merged = cv2.dilate(near.astype(np.uint8), np.ones((1, max(3, int(0.5 * font_px))), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(merged)
    near &= np.isin(lab, [i for i in range(1, n) if stats[i, cv2.CC_STAT_LEFT] < 0.45 * W
                          and stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] > 0.55 * W])
    return sum(1 for b in text_bands(near) if b[1] - b[0] >= 0.35 * font_px)


def generic_pixels(bgr):
    """Palette tells of the AI-default look on a settled card crop: a list of short reasons."""
    import cv2
    import numpy as np
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(float)
    hue, s, v = hsv[:, 0] * 2, hsv[:, 1] / 255, hsv[:, 2] / 255
    out = []
    dark = float(((v < DARK_V) & (s < 0.35)).mean())
    acc = (s >= NEON_S) & (v >= NEON_V)
    if dark >= DARK_SHARE and acc.any():
        bins = np.bincount((hue[acc] // 30).astype(int), minlength=12)
        top = int(bins.argmax())
        mid = top * 30 + 15
        if bins[top] / acc.sum() >= ONE_HUE and bins[top] >= NEON_SHARE * len(hue) and NEON_HUES[0] <= mid <= NEON_HUES[1]:
            out.append(f"near-black panel ({dark:.0%}) lit by one bright colour (hue {mid} deg)")
    g = (hue >= GRAD_HUES[0]) & (hue <= GRAD_HUES[1]) & (s >= 0.3) & (v >= 0.25)
    if g.mean() >= GRAD_SHARE:
        spread = np.percentile(v[g], 90) - np.percentile(v[g], 10) + (np.percentile(hue[g], 90) - np.percentile(hue[g], 10)) / 60
        if spread >= 0.15:
            out.append(f"blue-purple gradient over {g.mean():.0%} of the card")
    return out


FLAT_SHARE, FLAT_SAT = 0.6, 0.3   # one saturated colour over 60% of the card: the flat-ground AI card
TITLE_H, SUB_H, BAR_H, BAR_FILL, BAR_W, CENTRE_TOL = 0.15, 0.5, 0.2, 0.75, 0.5, 0.06


def text_bands(ink):
    """Horizontal bands of a binary ink mask: [(y0, y1, x0, x1, fill)] top to bottom, gaps under 3 rows merged."""
    import numpy as np
    rows = ink.sum(axis=1) > max(2, 0.005 * ink.shape[1])
    out, y = [], 0
    while y < len(rows):
        if not rows[y]:
            y += 1
            continue
        y0 = y
        while y < len(rows) and (rows[y] or rows[y:y + 3].any()):
            y += 1
        band = ink[y0:y]
        xs = np.nonzero(band.any(axis=0))[0]
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        out.append((y0, y, x0, x1, float(band[:, x0:x1].mean())))
    return out


def ai_title_card(bgr):
    """The AI-made title card, from a settled crop of one card: [reason]. A flat saturated ground over
    FLAT_SHARE of it; or a large centred text block with a small line under it and a short solid bar."""
    import cv2
    import numpy as np
    out = []
    q = (bgr >> 5).reshape(-1, 3)
    keys, counts = np.unique(q[:, 0].astype(np.int32) * 64 + q[:, 1] * 8 + q[:, 2], return_counts=True)
    top = int(keys[counts.argmax()])
    share = counts.max() / len(q)
    col = np.uint8([[[(top // 64) * 32 + 16, ((top // 8) % 8) * 32 + 16, (top % 8) * 32 + 16]]])
    sat = cv2.cvtColor(col, cv2.COLOR_BGR2HSV)[0, 0, 1] / 255
    if share > FLAT_SHARE and sat > FLAT_SAT:
        out.append(f"a flat saturated ground over {share:.0%} of the card")
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.int16)
    bg = int(np.median(grey))
    ink = np.abs(grey - bg) > 50
    H, W = ink.shape
    bands = text_bands(ink)
    if bands:
        big = max(bands, key=lambda b: b[1] - b[0])
        bh = big[1] - big[0]
        centred = abs((big[2] + big[3]) / 2 - W / 2) < CENTRE_TOL * W
        below = [b for b in bands if b[0] >= big[1]]
        sub = any(b[1] - b[0] < SUB_H * bh and b[4] < BAR_FILL for b in below)
        bar = any(b[1] - b[0] <= BAR_H * bh and b[4] >= BAR_FILL and b[3] - b[2] < BAR_W * W for b in bands if b is not big)
        if bh >= TITLE_H * H and centred and sub and bar:
            out.append("a big centred heading with a small line under it and a short accent bar")
    return out


def icon_counts(anim):
    """(stock icons, real logos/images) named in one card's anim props."""
    icons = real = 0
    stack = [anim or {}]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if n.get("icon"):
                icons += 1
            src = n.get("src") if isinstance(n.get("src"), str) else ""
            if not n.get("icon") and (n.get("logo") or (src and "/icon-" not in src)):
                real += 1
            stack += list(n.values())
        elif isinstance(n, list):
            stack += n
    return icons, real


def emoji_in(obj):
    return sorted({m for s in re.findall(r'"((?:[^"\\]|\\.)*)"', json.dumps(obj, ensure_ascii=False))
                   for m in EMOJI.findall(s)})


def stale(render, inputs):
    """Inputs (existing paths) changed after the render: [(name, seconds newer)]."""
    t = render.stat().st_mtime
    return sorted(((p.name, round(p.stat().st_mtime - t)) for p in inputs if p.exists() and p.stat().st_mtime > t + 1),
                  key=lambda x: -x[1])


def rate_check(name, got, want):
    if not want:
        return None
    r = got / want
    if RATE_BAND[0] <= r <= RATE_BAND[1]:
        return None
    return F("WARN", None, f"{name}: {got:.1f} a minute, the creator's style has {want:.1f}",
             "fewer/more visuals or zooms in visuals.json / style.json, then plan again" if "card" in name or "zoom" in name
             else "the cut sets this: compare spans.json with the creator's pace")


# ---------------------------------------------------------------- audio

def loudness(video):
    err = subprocess.run(["ffmpeg", "-nostats", "-v", "info", "-i", str(video), "-map", "0:a:0?", "-af", "ebur128=peak=true",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    summ = err[err.rfind("Summary:"):] if "Summary:" in err else ""
    i = re.search(r"I:\s+(-?[\d.]+|-inf) LUFS", summ)
    p = re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summ)
    num = lambda m: None if not m or "inf" in m.group(1) else float(m.group(1))
    return num(i), num(p)


LUFS_TARGET = -14.0    # where the platforms play speech; normalize never goes past TP_WARN


def gain_db(lufs, tp, target=LUFS_TARGET, ceiling=TP_WARN):
    """The one gain that brings `lufs` to `target` without the true peak passing `ceiling`."""
    return round(min(target - lufs, ceiling - tp), 2)


def normalize(video):
    """Opt-in: the whole audio track moved by one gain (no compressor, limiter or denoise), so the
    voice sounds exactly as recorded, only louder or quieter. Writes <stem>-normalized.mp4 next to
    `video` and leaves `video` as it is. Returns (out, gain, (lufs, tp) after)."""
    video = Path(video)
    lufs, tp = loudness(video)
    if lufs is None or tp is None:
        sys.exit(f"ERROR: no audio to measure in {video}")
    g = gain_db(lufs, tp)
    out = video.with_name(video.stem + "-normalized.mp4")
    if subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-map", "0:v?", "-map", "0:a:0",
                       "-c:v", "copy", "-af", f"volume={g}dB", "-c:a", "aac", "-b:a", "192k",
                       "-movflags", "+faststart", str(out)]).returncode:
        sys.exit("ERROR: ffmpeg could not write " + str(out))
    return out, g, loudness(out)


def grab(video, t, w, h):
    """One frame at t seconds, BGR, w x h."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w, 3) if len(raw) == w * h * 3 else None


def pcm(video, sr=48000):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def cue_levels(r, c, cues, sr=48000, win=0.05):
    """Each cue's loudest 50 ms in (render - gain * cut), in dB against the cut's speech level.
    The two are aligned to the sample first (AAC priming shifts one against the other)."""
    import numpy as np
    n = min(len(r), len(c), sr * 20)
    if n < sr:
        return None, []
    size = 1 << int(np.ceil(np.log2(2 * n)))
    xc = np.fft.irfft(np.fft.rfft(r[:n], size) * np.conj(np.fft.rfft(c[:n], size)), size)
    lag = int(np.argmax(np.concatenate([xc[-int(0.1 * sr):], xc[:int(0.1 * sr)]]))) - int(0.1 * sr)
    c = np.roll(c, lag)[:len(r)] if lag else c[:len(r)]
    r = r[:len(c)]
    g = float(np.dot(r, c) / max(np.dot(c, c), 1e-12))
    res = r - g * c
    w = int(win * sr)
    db = lambda x: 10 * np.log10(max(float(np.mean(x ** 2)), 1e-12))
    # The voice as sfx.py measures it: the mean power of the 50 ms windows over -45 dBFS
    pw = [float(np.mean(c[i:i + w] ** 2)) * g * g for i in range(0, len(c) - w, w)]
    loud = [x for x in pw if x > 10 ** (-4.5)]
    voice = 10 * np.log10(max(np.mean(loud) if loud else 1e-12, 1e-12))
    out = []
    for cue in cues:
        a, b = int(cue["t"] * sr), int((cue["t"] + 0.6) * sr)
        lv = [db(res[i:i + w]) for i in range(max(0, a), max(a + 1, min(len(res), b) - w), w // 2)]
        out.append(round(max(lv) - voice, 1) if lv else None)
    return {"lag_ms": round(1000 * lag / sr, 1), "voice_gain_db": round(20 * np.log10(max(g, 1e-6)), 1)}, out


# ---------------------------------------------------------------- the pass over every frame

def zoom_steps(frames):
    """Log-scale change from each grey frame to the next: ORB matches, a RANSAC similarity fit."""
    import cv2
    import numpy as np
    orb, bf = cv2.ORB_create(600), cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    feats = [orb.detectAndCompute(f, None) for f in frames]
    out = []
    for (ka, da), (kb, db) in zip(feats, feats[1:]):
        m = bf.match(da, db) if da is not None and db is not None else []
        M = None
        if len(m) >= 8:
            M, _ = cv2.estimateAffinePartial2D(np.float32([ka[x.queryIdx].pt for x in m]),
                                               np.float32([kb[x.trainIdx].pt for x in m]), method=cv2.RANSAC)
        out.append(float(np.log(np.hypot(M[0, 0], M[1, 0]))) if M is not None else 0.0)
    return out


def zoom_verdict(steps):
    """None (smooth, or too small to judge), "snap" or "jerk" for one zoom move's per-frame log-scale steps."""
    tot = sum(steps)
    if abs(tot) < ZOOM_MIN_LOG:
        return None
    v = [x if tot > 0 else -x for x in steps]       # speed along the move
    peak = max(v)
    if peak > SNAP_SHARE * abs(tot):
        return "snap"
    if min(v) < -JERK_SHARE * peak:
        return "jerk"
    i = v.index(peak)       # a smooth move: speed rises to one peak and falls; a second surge is jerk
    if any(v[j] - min(v[min(j, i):max(j, i) + 1]) > JERK_SHARE * peak for j in range(len(v)) if j != i):
        return "jerk"
    return None


def zoom_moves(video, plan, w=270, h=480):
    """[(t, kind, steps)] for every zoom move on the render: in at start, back out at end."""
    import numpy as np
    fps = plan["fps"]
    out = []
    for z in plan["zooms"]:
        e = max(0.8, z.get("ease_s") or 0) if z.get("kind") == "push" and z.get("ease_s") else 0.16
        for t in (z["start"], z["end"] - (e if z.get("kind") == "push" and z.get("ease_s") else 0)):
            a, d = max(0.0, t - 0.1), e + 0.25
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{d:.3f}", "-i", str(video), "-vf",
                                  f"fps={fps},scale={w}:{h},format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
            fr = np.frombuffer(raw, np.uint8)[: len(raw) // (w * h) * w * h].reshape(-1, h, w)
            o = (z.get("origin") or [50, 30])[1] / 100
            band = fr[:, int(max(0, o) * h):int(min(1, o + 0.3) * h)]     # the head down from its top (the origin): not cards, not captions
            if len(band) >= 3:
                out.append((round(t, 2), z.get("kind", "punch"), zoom_steps(list(band))))
    return out


def run(edit, plan, video, plan_path, style=None, cuts=(), brand=None):
    """All checks above on one render. Returns (findings, measured)."""
    import cv2
    import numpy as np
    from check import INK_DIFF, footage_affine, stream, TEXT_ANIMS, STATIC_S
    from edit import proxy_filter, still_frames
    from plan import CARD_LEAD_S, ENTRANCES, MOTION_K, OVERLAY_LEAD_S, overlay_led, probe
    cj = edit / "captions.json"
    cwords = json.loads(cj.read_text()) if cj.exists() else []
    out, meas = [], {}
    fps = plan["fps"]
    split = bool(plan.get("layout"))
    W, H = plan["width"] // 2, plan["height"] // 2
    cards = plan["cards"]
    m = probe(edit / plan["video"])
    behind = stream(edit / plan["video"], proxy_filter(m["width"], m["height"], plan["width"], plan["height"]), W, H, fps)
    ground = None
    if split:
        g = plan["layout"]["ground"].lstrip("#")
        ground = np.full((H, W, 3), [int(g[4:6], 16), int(g[2:4], 16), int(g[0:2], 16)], np.uint8)
    cs = plan["captions"]["style"]
    ch = max(4.0, cs.get("size_pct", 6) / 100 * max(W, H))           # Captions.tsx: size_pct of the long side
    cap_ys = sorted({cs.get("y_pct", 70)} | ({plan["layout"]["caption_full_y"]} if split else set()))
    cap_rows = (int(cap_ys[0] / 100 * H - ch), int(cap_ys[-1] / 100 * H + ch))   # centred on y_pct (translateY -50%)

    def box_px(b):
        x0, y0 = int(b[0] / 100 * W), int(b[1] / 100 * H)
        x1, y1 = int((b[0] + b[2]) / 100 * W), int((b[1] + b[3]) / 100 * H)
        return max(0, x0), max(0, y0), min(W, x1), min(H, y1)

    boxes = [box_px(c["box"]) for c in cards]
    first = [round(c["start"] * fps) for c in cards]
    last = [round(c["end"] * fps) for c in cards]
    settle = {f"{4 + i}-card": i for i in range(len(cards))}
    sframes = {v: k for k, v in still_frames(plan).items() if k in settle}
    chunks = plan["captions"]["chunks"]
    step = max(1, len(chunks) // 24)
    cap_frames = {round((ch_["start"] + ch_["end"]) / 2 * fps): ch_ for ch_ in chunks[::step]}
    # every page, once settled: how many lines it is drawn on (Captions.tsx: one unless max_lines says more)
    page_frames = {round((ch_["start"] + ch_["end"]) / 2 * fps): ch_ for ch_ in chunks}
    cap_bgr = [np.array([int(h.lstrip("#")[k:k + 2], 16) for k in (4, 2, 0)], float)
               for h in [cs.get("color") or "#FFFFFF"] + ([cs["highlight_color"]] if cs.get("highlight_color") else [])]
    wrapped = []
    series = {i: {"area": [], "bbox": [], "d": [], "prev": None} for i in range(len(cards))}
    small_r, small_b, kept, caps = [], [], {}, []
    prev_r = prev_b = None
    for n, frame in enumerate(stream(video, "null", W, H, fps)):
        t = n / fps
        cut = next(behind, None)
        if cut is None:
            break
        sr_ = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        sb_ = cv2.resize(cv2.cvtColor(cut, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
        small_r.append(sr_)
        small_b.append(sb_)
        up = [i for i in range(len(cards)) if first[i] - 3 <= n <= last[i]]
        if n in page_frames:
            nl = max(caption_lines(frame, cap_bgr, y / 100 * H, ch) for y in cap_ys)
            if nl > (cs.get("max_lines") or 1):
                wrapped.append((t, page_frames[n]["text"], nl))
        need = up or n in sframes or n in cap_frames
        if not need:
            continue
        if split:
            bg = ground
        else:
            zm = np.float32(footage_affine(t, plan, W, H))
            bg = cv2.warpAffine(cut, zm, (W, H))
            # a behind card: the speaker's cutout over it is the speaker, not the card (and its refined
            # edge differs a little from the raw camera), so his pixels read as footage here
            k = any(cards[i].get("layer") == "behind" for i in up) and \
                next((x for x in plan.get("cutouts") or [] if x["from"] <= n <= x["to"]), None)
            png = k and edit / k["src"] / f"{n - k['from']:06d}.png"
            if png and png.exists():
                al = cv2.resize(cv2.imread(str(png), cv2.IMREAD_UNCHANGED)[..., 3], (W, H), interpolation=cv2.INTER_AREA)
                person = cv2.dilate((cv2.warpAffine(al, zm, (W, H)) > 0).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
                frame = frame.copy()
                frame[person] = bg[person]
        if n in sframes:
            kept[settle[sframes[n]]] = (frame.copy(), bg.copy())
        if n in cap_frames:
            caps.append((t, cap_frames[n]))
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for i in up:
            x0, y0, x1, y1 = boxes[i]
            if x1 <= x0 or y1 <= y0:
                continue
            a, b = frame[y0:y1, x0:x1], bg[y0:y1, x0:x1]
            diff = cv2.absdiff(cv2.GaussianBlur(a, (5, 5), 0), cv2.GaussianBlur(b, (5, 5), 0)).max(axis=2)
            ink = diff > INK_DIFF["split" if split else "overlay"]
            r0, r1 = max(0, cap_rows[0] - y0), max(0, cap_rows[1] - y0)
            ink[r0:r1] = False                      # the caption is not the card
            st = series[i]
            st["area"].append(int(ink.sum()))
            ys, xs = np.nonzero(ink)
            st["bbox"].append([xs.min(), ys.min(), xs.max(), ys.max()] if len(xs) else None)
            region = grey[y0:y1, x0:x1]
            # change on the card's own pixels only (this frame's or the last), so the footage
            # around a panel that is smaller than its box never reads as the card moving
            if st["prev"] is not None and st["prev"][0].shape == region.shape:
                own = ink | st["prev"][1]
                st["d"].append(float(np.abs(region - st["prev"][0])[own].sum()) / region.size)
            else:
                st["d"].append(0.0)
            st["prev"] = (region, ink)
    nfr = len(small_r)
    dur = nfr / fps
    sr_a, sb_a = np.array(small_r), np.array(small_b)
    d_r = np.concatenate([[1.0], np.abs(np.diff(sr_a, axis=0)).mean(axis=(1, 2))])
    d_b = np.concatenate([[1.0], np.abs(np.diff(sb_a, axis=0)).mean(axis=(1, 2))])

    # freeze. Not under a full-frame scene: the footage is hidden there, so a still frame is not a dropped one
    fz = freezes(d_r, d_b, {n for i, c in enumerate(cards) if c.get("layout") == "scene" for n in range(first[i], last[i] + 1)})
    meas["freezes"] = [[round(a / fps, 2), k] for a, k in fz]
    for a, k in fz:
        out.append(F("FAIL" if k >= FREEZE_RUN else "WARN", a / fps,
                     f"the render repeats {k} frame(s) while the footage moves ({a / fps:.2f} s)",
                     "render again; if it stays, re-encode cut.mp4 with a keyframe every 15 frames (edit.py does) and check the source for dropped frames"))

    # rhythm + static stretches
    _, hard, jump, moves = edit_events(sr_a)
    events = sorted(set(hard + jump + [i for a, b in moves for i in range(a, b + 1)]))
    moving = np.zeros(nfr, bool)
    for i in events:
        moving[max(0, i - fps // 4):i + fps // 4] = True
    for i, c in enumerate(cards):
        d = series[i]["d"]
        for k, v in enumerate(d):
            if v > MOVE_D and 0 <= first[i] - 3 + k < nfr:
                moving[first[i] - 3 + k] = True
    for z in plan["zooms"]:
        if z.get("ease_s"):
            for a in (z["start"], z["end"] - z["ease_s"]):
                moving[int(a * fps):int((a + z["ease_s"]) * fps)] = True
    pace = (style or {}).get("pace") or {}
    static_s = round(2.5 * pace["median_shot_s"], 1) if pace.get("median_shot_s") else STATIC_S
    runs, k0 = [], None
    for k in range(nfr + 1):
        if k < nfr and not moving[k]:
            k0 = k if k0 is None else k0
        elif k0 is not None:
            runs.append((k0, k))
            k0 = None
    meas["moving_share"] = round(float(moving.mean()), 2)
    for a, b in runs:
        if (b - a) / fps > static_s:
            out.append(F("WARN", a / fps, f"nothing moves for {(b - a) / fps:.1f} s ({a / fps:.1f}-{b / fps:.1f} s): "
                         "no card in motion, no cut", "a visual beat or a zoom in that stretch, or motion in the card that is up"))
    mins = dur / 60
    landed = []
    meas["zoom_moves"] = []
    for t, kind, st in zoom_moves(video, plan):
        v = zoom_verdict(st)
        meas["zoom_moves"].append({"t": t, "kind": kind, "verdict": v,
                                   "peak_share": round(max(map(abs, st)) / max(1e-6, abs(sum(st))), 2) if st else None})
        if v:
            out.append(F("WARN", t, f"the {kind} zoom at {t:.2f} s {'snaps in one frame' if v == 'snap' else 'surges or reverses mid-move'}",
                         "render with the current StyleEdit.tsx (eased punches, pushes of 0.8 s or more); a zoom on a cut hides in the cut"))
    meas["rhythm"] = {"cuts_per_min": round((len(hard) + len(jump)) / mins, 1),
                      "moves_per_min": round(len(moves) / mins, 1),
                      "zooms_per_min": round(len(plan["zooms"]) / mins, 1)}

    # per card: flash, landing, spikes, jitter
    skip_t = sorted({z[k] for z in plan["zooms"] for k in ("start", "end")} | set(cuts)
                    | {round(n / fps, 3) for n in hard + jump})
    rec = meas.setdefault("cards", {})
    for i, c in enumerate(cards):
        st, name = series[i], f"'{c['trigger_word']}' {c.get('src') or c['anim']['type']}"
        r = rec.setdefault(f"{i}:{c['trigger_word']}", {})
        if len(st["area"]) < 6:
            continue
        others = [j for j, o in enumerate(cards) if j != i and o["start"] - 0.4 < c["start"] < o["end"] + 0.4
                  and not (boxes[j][2] <= boxes[i][0] or boxes[j][0] >= boxes[i][2]
                           or boxes[j][3] <= boxes[i][1] or boxes[j][1] >= boxes[i][3])]
        word = c["start"] + CARD_LEAD_S
        scene = c.get("layout") == "scene"
        k_ = MOTION_K.get(plan.get("motion"), 1.0)
        if scene:
            word, lt = scene_land(c, cwords, k_)
        elif overlay_led(c):     # started OVERLAY_LEAD_S x k before its word (plan.lay_out)
            word = scene_land(c, cwords, k_, OVERLAY_LEAD_S)[0]
        if not others and c.get("entrance", "pop") in ENTRANCES + ("cut",):   # cut: the creator's measured hard cut
            land, verdict = landing(st["area"], first[i], fps)
            if land is not None or scene:
                lt = lt if scene else land / fps
                r["lands_s"], r["word_s"] = round(lt, 2), round(word, 2)
                landed.append(lt)
                if lt - word > LAND_TOL:
                    out.append(F("FAIL", lt, f"{name} lands {lt - word:.2f} s after its word ({word:.2f} s)",
                                 "a quicker entrance, or an earlier start (hold_s / the beat's word in visuals.json)"))
                elif word - lt > LAND_TOL:
                    out.append(F("WARN", lt, f"{name} lands {word - lt:.2f} s before its word ({word:.2f} s)",
                                 "anchor the beat to the word that names it in visuals.json"))
            if verdict == "flash":
                out.append(F("FAIL", c["start"], f"{name} shows its finished state on its first frame, then animates in",
                             "the entrance's from-state must hold on frame 0 (Anims.tsx / StyleEdit.tsx); render again"))
            elif verdict == "whole" and c.get("entrance") != "cut":
                out.append(F("WARN", c["start"], f"{name} appears whole in one frame: no entrance",
                             f"give it an entrance ({', '.join(ENTRANCES)}) in visuals.json"))
        # entrance and exit are judged by landing and flash; a cut or zoom moves everything at once
        L = len(st["d"])
        near = {k for k in range(L) for tt in skip_t if abs(first[i] - 3 + k - tt * fps) <= 3}
        near |= set(range(0, 3 + int(0.5 * fps))) | set(range(max(0, L - int(0.4 * fps)), L))
        sp = spikes(st["d"], near)
        r["spikes"] = [round((first[i] - 3 + k) / fps, 2) for k in sp]
        if sp and c.get("lane") != "logo":
            out.append(F("WARN", (first[i] - 3 + sp[0]) / fps, f"{name} changes in one isolated frame at {len(sp)} point(s)",
                         "something pops in with no entrance: give that part a spring or a fade"))
        # jitter on the outline, in runs where it tracks one thing
        # only while it enters and leaves (inside, scenes rearrange on purpose), and only when
        # the box was empty before it (in split, the panel opening fills the box first)
        L, ent = len(st["bbox"]), 3 + int(0.8 * fps)
        empty = st["area"][2] <= 0.25 * max(st["area"])
        # a cut or a zoom moves everything at once, the card's outline as read here too: the run breaks there
        moved = {k for k in range(L) for tt in skip_t if abs(first[i] - 3 + k - tt * fps) <= 3}
        bb = [b if (k < ent or k >= L - int(0.5 * fps)) and empty and k not in moved else None for k, b in enumerate(st["bbox"])]
        bw, bh = boxes[i][2] - boxes[i][0], boxes[i][3] - boxes[i][1]
        worst = []
        for axis in range(4):
            run_ = []
            for b in bb + [None]:
                v = None if b is None else b[axis]
                lim = JUMP_SHARE * (bw if axis % 2 == 0 else bh)
                if v is None or (run_ and abs(v - run_[-1]) > lim):
                    worst += jitter(run_) if len(run_) > 4 else []
                    run_ = [] if v is None else [v]
                else:
                    run_.append(v)
        if worst and not others:
            r["jitter"] = max(w for _, w in worst)
            out.append(F("WARN", c["start"], f"{name}'s outline turns back at speed {len(worst)} time(s) "
                         f"(worst {r['jitter']:.0%} of its peak speed both sides of the turn)",
                         "jitter: ease into turns (spring damping up, or one axis at a time)"))

    if style:
        for nm, got, want in (("cuts", meas["rhythm"]["cuts_per_min"], (pace.get("cuts_per_10s") or 0) * 6),
                              ("cards", len(landed) / mins if landed else len(cards) / mins, style.get("per_min")),
                              ("zooms", meas["rhythm"]["zooms_per_min"], (style.get("zoom") or {}).get("per_min"))):
            f = rate_check(nm, got, want)
            if f:
                out.append(f)
        meas["rhythm"]["creator"] = {"cuts_per_min": round((pace.get("cuts_per_10s") or 0) * 6, 1) or None,
                                     "cards_per_min": style.get("per_min"),
                                     "zooms_per_min": (style.get("zoom") or {}).get("per_min")}

    # settled frames: overflow, contrast, generic look
    icons_all = real_all = 0
    for i, c in enumerate(cards):
        anim = c.get("anim") or {}
        ic, rl = icon_counts(anim)
        icons_all += ic
        real_all += rl + bool(c.get("src"))
        name = f"'{c['trigger_word']}' {c.get('src') or anim.get('type')}"
        if ic > ICONS_PER_CARD:
            out.append(F("WARN", c["start"], f"{name} is {ic} stock icons: the icon-grid look every AI edit has",
                         "show the real thing: a logo, a capture of the product, or a photo the user gave"))
        if i not in kept or c.get("src") or c.get("lane") == "logo":
            continue
        frame, bg = kept[i]
        crop, bgv = panel_crop(frame, bg, boxes[i], INK_DIFF["split" if split else "overlay"], split)
        if crop is None:
            continue
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        ih, iw = grey.shape
        rr = rec.setdefault(f"{i}:{c['trigger_word']}", {})
        if bgv is None:
            bgv = float(np.median(grey))
            bad = []                           # no uniform panel: nothing to overflow
        else:
            rr["edges"] = ov = edge_overflow(grey, bgv)
            bad = [k for k, v in ov.items() if v > EDGE_ROWS]
        if bad:
            text_card = anim.get("type") in TEXT_ANIMS
            out.append(F("FAIL" if text_card else "WARN", c["start"],
                         f"{name}: content runs into the card's {' and '.join(bad)} edge",
                         "shorten the text or give the card a bigger box in visuals.json, then plan again"))
        # text cards only: a scene's glows and tiles are not text
        text = np.abs(grey.astype(float) - bgv) > 50
        text[:int(0.06 * ih)] = text[int(0.94 * ih):] = False
        text[:, :int(0.03 * iw)] = text[:, int(0.97 * iw):] = False
        cr = worst_contrast(crop, text, 2) if anim.get("type") in TEXT_ANIMS else None
        rr["contrast"] = cr
        if cr is not None and cr < CONTRAST_WARN:
            out.append(F("FAIL" if cr < CONTRAST_FAIL else "WARN", c["start"],
                         f"{name}: its text against the card is {cr}:1 at the worst spot",
                         "a darker or more opaque card ground, or brighter ink (look in style.json)"))
        # the AI-made look on the settled card (ai_tells.check_still runs generic_pixels and ai_title_card)
        from ai_tells import check_still, for_brand
        gen = for_brand(check_still(crop, name), brand)
        rr["generic"] = [f"{g['tell']}: {g['where']}" for g in gen]
        for g in gen:
            out.append(F("FAIL" if g["level"] == "BAN" else "WARN", c["start"], f"{name} AI tell '{g['tell']}': {g['where']}", g["fix"]))
    if icons_all > real_all and icons_all > ICONS_PER_CARD:
        out.append(F("WARN", None, f"{icons_all} stock icons against {real_all} real logos, captures and images",
                     "swap icons for the real products and screenshots the words name"))
    meas["icons"] = {"stock": icons_all, "real": real_all}
    for where, obj in (("visuals.json", (edit / "visuals.json")), ("captions.json", (edit / "captions.json"))):
        if obj.exists():
            em = emoji_in(json.loads(obj.read_text()))
            if em:
                out.append(F("WARN", None, f"emoji in {where}: {' '.join(em)}", "words or a real image, not emoji"))

    # captions: contrast and the frame's edge
    cols = [cs.get("color") or "#FFFFFF"] + ([cs["highlight_color"]] if cs.get("highlight_color") else [])
    rgbs = [np.array([int(h.lstrip("#")[k:k + 2], 16) for k in (4, 2, 0)], float) for h in cols]   # BGR
    worst_cap, edge_hits = [], []
    FW, FH = plan["width"], plan["height"]
    # under a landed scene the captions are the ground's ink, not the caption colour (StyleEdit.tsx sceneCaptions):
    # those pages are skipped. ponytail: the scene's own ink-on-ground pair is not measured here.
    k_cap = MOTION_K.get(plan.get("motion"), 1.0)
    inked = [(c["start"] + 0.31 * k_cap, c["end"] - 0.31 * k_cap) for c in cards if c.get("layout") == "scene"]
    for t, chunk in caps:
        if any(a <= t < b for a, b in inked):
            continue
        text = chunk["text"]
        # full size: the stroke is 0.05 em outside the fill, about one pixel at half size
        frame = grab(video, t, FW, FH)
        if frame is None:
            continue
        got = caption_fill(frame, rgbs, [y / 100 * FH for y in cap_ys], 2 * ch, text)
        if got is None:
            continue
        rows, fill, touches = got
        if touches:
            edge_hits.append(t)
        # the ring is what is drawn right around the glyph: the stroke when there is one
        # (Captions.tsx: 0.1 em, half of it outside the fill; plan.py's contrast "treat" draws one too),
        # else the footage
        stroked = cs.get("stroke") or chunk.get("treat") in ("stroke", "backing")
        cr = worst_contrast(frame[rows], fill, max(2, round((0.08 if stroked else 0.12) * ch)))
        if cr is not None:
            worst_cap.append((cr, t))
    if worst_cap:
        lo = min(worst_cap)
        meas["caption_contrast"] = {"worst": lo[0], "at": round(lo[1], 2), "median": float(np.median([c for c, _ in worst_cap])),
                                    "samples": len(worst_cap)}
        meas["caption_contrast"]["low_at"] = [round(t, 2) for c, t in worst_cap if c < CONTRAST_TARGET]
        bad = [x for x in worst_cap if x[0] < CONTRAST_WARN]
        if bad:
            out.append(F("FAIL" if lo[0] < CONTRAST_FAIL else "WARN", lo[1],
                         f"captions read at {lo[0]}:1 against what is around them ({len(bad)} of {len(worst_cap)} samples under {CONTRAST_WARN}:1)",
                         f"plan again: plan.py reads this check and gives each page under {CONTRAST_TARGET}:1 the next treatment "
                         "(shadow, stroke, backing; contrast.json keeps it); then render"))
    # pages under a landed scene draw in the scene's ink, not the caption colour: not read here
    wrapped = [w for w in wrapped if not any(a <= w[0] < b for a, b in inked)]
    meas["caption_lines"] = {"pages": len(page_frames), "over": [[round(t, 2), txt, nl] for t, txt, nl in wrapped]}
    if wrapped:
        t, txt, nl = wrapped[0]
        out.append(F("FAIL", t, f"caption '{txt}' is drawn on {nl} lines ({len(wrapped)} page(s) over "
                     f"{cs.get('max_lines') or 1}): one page is one line at one size",
                     "render with the current Captions.tsx (one line, never wrapped); or fewer words_per_caption"))
    for t in edge_hits[:1]:
        out.append(F("FAIL", t, f"a caption touches the frame's side ({len(edge_hits)} sample(s)): cut off",
                     "fewer words_per_caption or a smaller size_pct in style.json, then plan again"))

    # audio
    lufs, tp = loudness(video)
    meas["loudness"] = {"lufs": lufs, "true_peak_db": tp}
    if lufs is not None and not LUFS_LOW <= lufs <= LUFS_HIGH:
        out.append(F("WARN", None, f"loudness {lufs} LUFS; platforms play at about -14",
                     "leave it (the default), or opt in: quality.py normalize <render> applies one gain to "
                     "-14 LUFS under a -1 dBTP peak, no compression"))
    if tp is not None and tp > TP_WARN:
        out.append(F("FAIL" if tp > TP_FAIL else "WARN", None, f"true peak {tp} dBTP (keep it under {TP_WARN})",
                     "a quieter cue (sfx.py) or a quieter source; peaks over 0 clip on every phone"))
    cues = plan.get("sfx") or []
    if cues and (edit / plan["video"]).exists():
        info, lv = cue_levels(pcm(video), pcm(edit / plan["video"]), cues)
        if info:
            meas["sfx"] = {**info, "cues_db": lv}
            for cue, x in zip(cues, lv):
                if x is None:
                    continue
                if x > SFX_HOT:
                    out.append(F("FAIL", cue["t"], f"{Path(cue['src']).stem} cue {x:+.1f} dB against the voice: louder than him",
                                 "turn that cue down (sfx.py sets each level against the cut)"))
                elif x < SFX_LOST:
                    out.append(F("WARN", cue["t"], f"{Path(cue['src']).stem} cue {x:+.1f} dB against the voice: not heard",
                                 "turn it up in sfx.py, or drop it"))

    # stale
    ins = [plan_path, edit / plan["video"], edit / "captions.json", edit / "visuals.json", edit / "images.json"]
    ins += [edit / c["src"] for c in cards if c.get("src")] + [edit / s["src"] for s in cues]
    old = stale(video, ins)
    if old:
        out.append(F("FAIL", None, f"{video.name} is older than {', '.join(f'{n} (+{s} s)' for n, s in old[:4])}",
                     "render again: the render does not show these changes"))
    pold = stale(plan_path, [edit / n for n in ("captions.json", "visuals.json", "images.json", "face.json")])
    if pold:
        out.append(F("WARN", None, f"{plan_path.name} is older than {', '.join(n for n, _ in pold)}", "plan again, then render"))
    return out, meas


def demo():
    import numpy as np
    import cv2
    # zoom moves: an instant 1.2x punch snaps; the same punch eased over 0.16 s, or a sine push, does not
    tex = cv2.GaussianBlur(np.random.default_rng(1).integers(0, 255, (200, 270)).astype(np.uint8), (0, 0), 1.2)
    at = lambda k: cv2.warpAffine(tex, cv2.getRotationMatrix2D((135, 100), 0, k), (270, 200))  # noqa: E731
    out2 = lambda f: 1 - (1 - f) ** 2  # noqa: E731
    assert zoom_verdict(zoom_steps([at(1.0)] * 3 + [at(1.2)] * 5)) == "snap"
    assert zoom_verdict(zoom_steps([at(1.2 ** out2(min(1, i / 5))) for i in range(9)])) is None
    assert zoom_verdict(zoom_steps([at(1.2 ** ((1 - np.cos(np.pi * i / 24)) / 2)) for i in range(25)])) is None
    assert zoom_verdict([0.01, 0.03, 0.005, 0.03, 0.01]) == "jerk" and zoom_verdict([0.01] * 2) is None
    # freeze: render flat for 4 frames while footage moves
    dr, db = [1.0] * 10, [1.0] * 10
    dr[3:7] = [0.01] * 4
    assert freezes(dr, db) == [(3, 4)], freezes(dr, db)
    assert freezes([0.01] * 5, [0.0] * 5) == []                 # still footage, still render: fine
    assert freezes(dr, db, set(range(2, 8))) == []                # under a full-frame scene: not a dropped frame
    # spikes: one isolated jump, not a ramp
    d = [0.3] * 20
    d[8] = 9
    assert spikes(d) == [8] and spikes(d, {8}) == []
    ramp = [0.3, 2, 4, 6, 8, 6, 4, 2, 0.3]
    assert spikes(ramp) == []
    # jitter: a kink at speed both sides is caught, a sine turn is not
    assert jitter([0, 5, 10, 15, 20, 15, 10, 5])
    assert not jitter(list(30 * np.sin(np.linspace(0, np.pi, 40))))
    assert not jitter([0, 1, 0, 1, 0])                           # 1 px flicker: under the visible floor
    # landing: pop from nothing at f0=30, lands half-way on frame 32
    area = [0, 0, 0, 0, 200, 600, 900, 1000] + [1000] * 20
    land, v = landing(area, 30, 30)
    assert land == 32 and v is None, (land, v)
    flash = [0, 0, 0, 1000, 50, 200, 500, 900] + [1000] * 20
    assert landing(flash, 30, 30)[1] == "flash"
    assert landing([0, 0, 0] + [1000] * 25, 30, 30)[1] == "whole"
    assert landing([900, 900, 900] + [1000] * 25, 30, 30) == (None, None)
    # scene_land: planned 0.3 x k early (k 1.35), word 5.0, so start 5.0 - 0.1 - 0.405; half done at start + 0.31 k
    k = 1.35
    sc = {"trigger_word": "Notion,", "start": round(5.0 - 0.1 - 0.3 * k, 3)}
    w, lt = scene_land(sc, [{"text": "notion", "start": 2.0}, {"text": "notion", "start": 5.0}], k)
    assert w == 5.0 and abs(lt - (sc["start"] + 0.31 * k)) < 1e-9, (w, lt)
    assert abs(scene_land({"trigger_word": "x", "start": 1.0}, [], 1.0)[0] - 1.4) < 1e-9
    # an overlay card starts OVERLAY_LEAD_S x k early: its word is found the same way, never start + CARD_LEAD_S
    from plan import OVERLAY_LEAD_S, overlay_led
    ov = {"src": "images/a.png", "trigger_word": "jev", "start": round(5.0 - 0.1 - OVERLAY_LEAD_S, 3), "layout": "box"}
    assert overlay_led(ov) and scene_land(ov, [{"text": "Jev", "start": 5.0}], 1.0, OVERLAY_LEAD_S)[0] == 5.0
    assert not overlay_led({**ov, "lane": "logo"}) and not overlay_led({**ov, "layout": "scene"})
    # the AI title card: big centred number, small line under it, a short bar, on a flat green ground
    card = np.full((600, 600, 3), (60, 110, 30), np.uint8)
    cv2.putText(card, "2,026", (95, 260), cv2.FONT_HERSHEY_SIMPLEX, 4.2, (240, 240, 240), 14)
    cv2.rectangle(card, (250, 300), (350, 312), (60, 210, 250), -1)
    cv2.putText(card, "the year it shipped", (150, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (200, 210, 200), 2)
    got = ai_title_card(card)
    assert len(got) == 2, got
    page = np.full((600, 600, 3), 255, np.uint8)
    cv2.putText(page, "Input tokens: $0.042", (20, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (30, 30, 30), 2)
    assert ai_title_card(page) == [], ai_title_card(page)   # a white capture card passes
    # caption_fill: a white word with a black stroke at y 600 on grey footage
    fr = np.full((960, 540, 3), 128, np.uint8)
    glyph = np.zeros((960, 540), np.uint8)
    cv2.putText(glyph, "hello", (200, 615), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 255, 3)
    fr[cv2.dilate(glyph, np.ones((7, 7), np.uint8)) > 0] = 0            # a 3 px black stroke
    fr[glyph > 0] = 255
    fr[590:620, 0:40] = 255                                            # a white patch far left: not the caption
    fr[600:603, 330:333] = 255                                         # a speck of light beside it
    rows, fill, touches = caption_fill(fr, [np.array([255, 255, 255.])], [600], 36, "hello")
    assert not fill[:, 330:333].any()
    assert rows.start < 600 < rows.stop and not touches and not fill[:, :40].any()
    assert worst_contrast(fr[rows], fill, 2) > 10                      # against its stroke
    assert worst_contrast(fr[rows], fill, 6) < CONTRAST_WARN            # reaching past it, into the grey
    # caption_lines: one line at the caption's y reads 1; the same page wrapped to two lines reads 2
    one = np.full((960, 540, 3), 90, np.uint8)
    cv2.putText(one, "down competitor ads", (40, 612), cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 4)
    two = np.full((960, 540, 3), 90, np.uint8)
    cv2.putText(two, "down competitor", (90, 590), cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 4)
    cv2.putText(two, "ads", (230, 650), cv2.FONT_HERSHEY_DUPLEX, 1.4, (255, 255, 255), 4)
    white = [np.array([255, 255, 255.])]
    assert caption_lines(one, white, 600, 40) == 1 and caption_lines(two, white, 600, 40) == 2
    # rhythm counter, measure_edit's synthetic clip
    f = np.full((120, 36, 64), 40, np.float32)
    base = np.random.default_rng(0).uniform(0, 80, (36, 64)).astype(np.float32)
    f[:] = base
    f[30:] = base + 120
    for k in range(10):
        f[60 + k:, :, :6 * (k + 1)] = 250
    f[90:] = f[89] + 6
    _, cuts, jumps, moves = edit_events(f)
    assert cuts == [30] and jumps == [90] and moves[0][0] == 60, (cuts, jumps, moves)
    # contrast: white text on black is 21:1; white on light grey fails
    img = np.zeros((60, 200, 3), np.uint8)
    cv2.putText(img, "hello", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 4)
    m = img.max(axis=2) > 200
    assert worst_contrast(img, m, 3) > 15
    img2 = np.repeat(np.where(m[..., None], 255, 225), 3, axis=2).astype(np.uint8)
    assert worst_contrast(img2, m, 3) < CONTRAST_FAIL
    assert round(ratio(rel_lum(np.array([255, 255, 255])), rel_lum(np.array([0, 0, 0]))), 1) == 21.0
    # overflow: text that runs off the right edge
    card = np.full((100, 400), 20, np.uint8)
    card[40:60, 300:400] = 240
    ov = edge_overflow(card, 20)
    assert ov["right"] > EDGE_ROWS and ov["left"] == 0, ov
    card[:, 300:] = 20
    card[40:60, 100:300] = 240
    assert max(edge_overflow(card, 20).values()) == 0
    # panel_crop: a white panel hugging its text inside a wider plan box, over busy footage
    foot = np.random.default_rng(2).integers(0, 255, (400, 400, 3)).astype(np.uint8)
    fr = foot.copy()
    fr[210:216, 124:284] = 30                                       # its drop shadow
    fr[150:210, 120:280] = 250
    cv2.putText(fr, "go", (170, 195), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)
    crop, level = panel_crop(fr, foot, (40, 140, 360, 220), 40, False)
    assert abs(crop.shape[0] - 60) <= 3 and abs(crop.shape[1] - 160) <= 3 and level == 250, (crop.shape, level)
    assert max(edge_overflow(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), level).values()) == 0
    # generic: near-black panel + mint glow is flagged; a cream card with black text is not
    panel = np.full((100, 300, 3), (18, 16, 16), np.uint8)
    panel[40:60, 40:120] = (176, 242, 124)                         # BGR of #7CF2B0
    assert generic_pixels(panel) and "near-black" in generic_pixels(panel)[0]
    cream = np.full((100, 300, 3), (230, 238, 242), np.uint8)
    cream[40:60, 40:200] = 20
    assert generic_pixels(cream) == []
    grad = np.zeros((100, 300, 3), np.uint8)
    for x in range(300):
        grad[:, x] = cv2.cvtColor(np.uint8([[[110 + x // 10, 200, 120 + x // 3]]]), cv2.COLOR_HSV2BGR)[0, 0]
    assert any("gradient" in g for g in generic_pixels(grad)), generic_pixels(grad)
    assert icon_counts({"type": "flow", "props": {"nodes": [{"icon": "mail", "src": "images/icon-mail.svg"}, {"icon": "x"},
                                                             {"logo": "notion", "src": "images/logo-notion.svg"}]}}) == (2, 1)
    assert icon_counts({"type": "logo", "props": {"src": "images/logo-claude.svg"}}) == (0, 1)
    assert emoji_in([{"text": "fast \U0001F680"}]) == ["\U0001F680"] and emoji_in(["plain"]) == []
    assert rate_check("cuts", 3, 12) and rate_check("cuts", 10, 12) is None and rate_check("cuts", 1, None) is None
    # audio: a cue mixed 6 dB under the voice measures about -6, even with the render 7 samples late
    sr = 48000
    rng = np.random.default_rng(1)
    voice = rng.normal(0, 0.1, sr * 3)
    cue = np.zeros_like(voice)
    cue[sr:sr + 4800] = rng.normal(0, 0.05, 4800)
    render = np.concatenate([np.zeros(7), voice + cue])[:len(voice)]
    info, lv = cue_levels(render, voice, [{"t": 1.0}], sr)
    assert abs(lv[0] + 6) < 1.0 and info["lag_ms"] == round(1000 * 7 / sr, 1), (info, lv)
    # stale
    import tempfile, os, time
    with tempfile.TemporaryDirectory() as tmp:
        r, p = Path(tmp) / "render.mp4", Path(tmp) / "plan.json"
        r.write_text("x")
        p.write_text("{}")
        os.utime(r, (time.time() - 100, time.time() - 100))
        assert stale(r, [p])[0][0] == "plan.json" and stale(p, [r]) == []
        # normalize: the quiet sample take's level comes up to -14 by one gain; a peak caps the gain
        assert gain_db(-24.7, -12.0) == 10.7 and gain_db(-24.7, -4.0) == 3.0 and gain_db(-10.0, -2.0) == -4.0
        q = Path(tmp) / "quiet.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                        "-af", "volume=-30dB", "-c:a", "aac", str(q)], check=True)
        out, g, (lufs, tp) = normalize(q)
        assert out.name == "quiet-normalized.mp4" and q.exists() and abs(lufs - LUFS_TARGET) < 0.5 and tp <= -0.5, (g, lufs, tp)
    print("demo ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["demo"]:
        demo()
    elif len(sys.argv) == 3 and sys.argv[1] == "normalize":
        o, g, (lu, pk) = normalize(sys.argv[2])
        print(f"{o}: {g:+.1f} dB, now {lu} LUFS, true peak {pk} dBTP. The original is untouched.")
    else:
        sys.exit(__doc__)
