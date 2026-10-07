#!/usr/bin/env python3
"""The look pass, measured from pixels: captions, face, graphics and motion.

  measure <handle>   per video: OCR 3 frames a second, find the caption lines (the
                     ones that match the spoken words), then measure them: place,
                     size, words, case, fill / stroke / box / highlight colours, weight,
                     how they enter. Plus the face framing, the share of runtime with
                     graphics on screen, cards a minute, how long they hold, how fast
                     they land, and the graphics palette. Writes video/<id>.look.json,
                     merges captions, face, graphics and motion into style.json, and
                     writes look.md: the summary Claude reads instead of frame images.
  summary <handle>   rewrite look.md from style.json and print it.
  demo               self-check on a synthetic clip with drawn captions. No network.

OCR: Apple Vision through ocrmac on a Mac, RapidOCR (onnxruntime) elsewhere. Without
either, captions are left to the fallback sheet pass and everything else still runs.
Faces: OpenCV YuNet, the model ai-editor's face.py uses (one 230 KB download, cached).
Every number here comes from code. gemini.py adds the words (font class, graphics style).
LOOK_OCR=rapid forces RapidOCR on a Mac (to test the Windows / Linux path).

Usage (the tool venv python: numpy, pillow, opencv, ocrmac or rapidocr):
  ~/.ai-video-editor/venv/bin/python scripts/look.py measure <handle> [--fps 3]
  ~/.ai-video-editor/venv/bin/python scripts/look.py demo

Exit codes: 0 ok - 1 error - 2 usage
"""
import argparse
import difflib
import importlib
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, slug  # noqa: E402

WORK_W = 720          # analysis width, px (most TikTok and Shorts are 720 or 1080 wide)
SAMPLE_FPS = 3
# OCR box height / font size (em), per engine, measured in the demo on drawn text.
# Only used when the caption colours cannot be read; the x-height measure is better.
EM_PER_BOX = {"vision": 1.17, "rapid": 1.36, "fake": 1.0}
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor")) / "models" / "yunet.onnx"
# Glyph stem / em -> CSS weight. Stems of real fonts: Inter 400 ~0.09 em, 700 ~0.15, 900 ~0.2.
STEM_CAL = 1.23          # measured in the demo: Pillow's default font (400) reads 0.073 raw
X_H, CAP_H = 0.53, 0.70   # x-height and cap height in em, typical of caption fonts
WEIGHTS = [(0.07, 300), (0.09, 400), (0.115, 500), (0.13, 600), (0.15, 700), (0.175, 800), (0.2, 900)]


# ---------- decoding ----------

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), float(d["format"]["duration"])


def decode(path, w, h, fps=None, t0=None, dur=None, gray=False):
    """Yields frames as arrays, scaled to w x h, at `fps` (source rate when None)."""
    cmd = ["ffmpeg", "-v", "error"]
    if t0 is not None:
        cmd += ["-ss", f"{max(0.0, t0):.3f}"]
    cmd += ["-i", str(path)]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    vf = (f"fps={fps}," if fps else "") + f"scale={w}:{h}"
    c = 1 if gray else 3
    p = subprocess.Popen(cmd + ["-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"],
                         stdout=subprocess.PIPE)
    n = w * h * c
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        a = np.frombuffer(buf, np.uint8).reshape(h, w, c)
        yield a[:, :, 0] if gray else a
    p.stdout.close()
    p.wait()


# ---------- engines ----------

def ocr_engine():
    """(name, fn(rgb, t) -> [(text, [x, y, w, h])] in fractions, top-left origin), or (None, None)."""
    if sys.platform == "darwin" and os.environ.get("LOOK_OCR") != "rapid":
        try:
            from ocrmac import ocrmac
            from PIL import Image

            def vision(im, t=None):
                out = ocrmac.OCR(Image.fromarray(im), recognition_level="accurate",
                                 language_preference=["en-US"]).recognize()
                # Vision's origin is bottom-left.
                return [(t, [x, 1 - y - h, w, h]) for t, conf, (x, y, w, h) in out if conf >= 0.3]
            return "vision", vision
        except ImportError:
            pass
    for mod in ("rapidocr_onnxruntime", "rapidocr"):
        try:
            eng = importlib.import_module(mod).RapidOCR()
        except ImportError:
            continue

        def rapid(im, t=None, eng=eng, old=mod == "rapidocr_onnxruntime"):
            H, W = im.shape[:2]
            r = eng(np.ascontiguousarray(im[:, :, ::-1]))
            items = [(b, t) for b, t, _ in (r[0] or [])] if old else \
                list(zip(r.boxes if r.boxes is not None else [], r.txts or []))
            out = []
            for b, t in items:
                b = np.asarray(b, float)
                (x0, y0), (x1, y1) = b.min(0), b.max(0)
                out.append((t, [float(x0 / W), float(y0 / H), float((x1 - x0) / W), float((y1 - y0) / H)]))
            return out
        return "rapid", rapid
    return None, None


def face_detector():
    """fn(rgb) -> face box [x, y, w, h] in fractions or None. None when OpenCV or the
    model is missing and cannot be fetched."""
    try:
        import cv2
        if not YUNET.exists():
            YUNET.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(YUNET_URL, YUNET)
    except Exception as e:  # offline, or no OpenCV: the rest still runs
        print(f"  no face detection ({e})", file=sys.stderr)
        return None
    det = {}

    def find(im):
        h, w = im.shape[:2]
        sw, sh = 360, round(360 * h / w)
        small = cv2.resize(im[:, :, ::-1], (sw, sh))
        if (sw, sh) not in det:
            det[(sw, sh)] = cv2.FaceDetectorYN.create(str(YUNET), "", (sw, sh), 0.6)
        _, faces = det[(sw, sh)].detect(small)
        if faces is None or not len(faces):
            return None
        x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])[:4]
        return [float(x / sw), float(y / sh), float(fw / sw), float(fh / sh)]
    return find


# ---------- captions ----------

def norm(s):
    return re.sub(r"[^a-z0-9']", "", s.lower())


def spoken(text, t, words):
    """True when most of the line's words are said within a few seconds of t."""
    toks = [x for x in (norm(w) for w in text.split()) if x]
    if not toks or not words:
        return False
    near = {w for w, s in words if t - 2.5 <= s <= t + 1.5}
    hit = sum(1 for x in toks if x in near or difflib.get_close_matches(x, near, 1, 0.7))
    return hit / len(toks) >= 0.6


def find_captions(samples, words):
    """Marks samples[i]["lines"][j]["cap"]. Captions match the transcript (or, with no
    transcript, are short centred lines), never stay up longer than 4 s, and sit in one band."""
    for s in samples:
        for ln in s["lines"]:
            x, y, w, h = ln["box"]
            n = len(ln["text"].split())
            if words:
                ln["cap"] = spoken(ln["text"], s["t"], words)
            else:
                ln["cap"] = n <= 7 and abs(x + w / 2 - 0.5) < 0.15 and h > 0.012
    # Titles and screen text that happen to be spoken stay up; captions do not.
    run, prev = Counter(), {}
    for s in samples:
        cur = {norm(ln["text"]) for ln in s["lines"]}
        for k in cur:
            run[k] = prev.get(k, 0) + 1
        prev = {k: run[k] for k in cur}
        for ln in s["lines"]:
            ln["run"] = run[norm(ln["text"])]
    long_runs = {norm(ln["text"]) for s in samples for ln in s["lines"] if ln["run"] > 4 * SAMPLE_FPS}
    ys = []
    for s in samples:
        for ln in s["lines"]:
            # ...nor are they small print: a box under 2.2% of the height is a card's text.
            if ln["cap"] and (norm(ln["text"]) in long_runs or ln["box"][3] < 0.022):
                ln["cap"] = False
            if ln["cap"]:
                ys.append(ln["box"][1] + ln["box"][3] / 2)
    if ys:
        band = statistics.median(ys)
        for s in samples:
            for ln in s["lines"]:
                if ln["cap"] and abs(ln["box"][1] + ln["box"][3] / 2 - band) > 0.12:
                    ln["cap"] = False


def block(s):
    """The caption block of one sample: its lines, top to bottom."""
    return sorted((ln for ln in s["lines"] if ln.get("cap")), key=lambda ln: ln["box"][1])


def kmeans(px, k):
    import cv2
    cv2.setRNGSeed(0)  # the same video always gives the same colours
    px = np.float32(px)
    k = max(1, min(k, len(px)))
    _, lab, cen = cv2.kmeans(px, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1.0),
                             3, cv2.KMEANS_PP_CENTERS)
    return lab.ravel(), cen


def nearest(img, cen):
    d = ((img[..., None, :].astype(np.float32) - cen[None, None]) ** 2).sum(-1)
    return d.argmin(-1)


def hexc(c):
    c = [int(round(v)) for v in c]
    if min(c) >= 232:
        c = [255, 255, 255]
    elif max(c) <= 28:
        c = [0, 0, 0]
    return "#{:02X}{:02X}{:02X}".format(*c)


def regions(crop_shape, core):
    """Masks inside a crop: the OCR box (core), a thin ring round it (near) and a ring
    a line-height out (far)."""
    H, W = crop_shape[:2]
    x0, y0, x1, y1 = core
    h = y1 - y0
    yy, xx = np.mgrid[0:H, 0:W]

    def rect(m):
        return (xx >= x0 - m) & (xx < x1 + m) & (yy >= y0 - m) & (yy < y1 + m)
    c = rect(0)
    near = rect(round(0.3 * h)) & ~c
    far = rect(round(1.0 * h)) & ~rect(round(0.6 * h))
    return c, near, far


def enclosure(labs, cores, a, b, h_px):
    """Share of the ring just outside cluster a's pixels that is cluster b."""
    import cv2
    hit = tot = 0
    for lab, core, h in zip(labs, cores, h_px):
        m = ((lab == a) & core).astype(np.uint8)
        if m.sum() < 10:
            continue
        r = max(1, round(0.05 * h))
        ring = (cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=r) > 0) & (m == 0) & core
        hit += int((lab[ring] == b).sum())
        tot += int(ring.sum())
    return hit / tot if tot else 0.0


def stem_ratio(mask, em_px):
    """Glyph stroke thickness / em: 2 x area / perimeter over the glyph contours."""
    import cv2
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cs)
    # x STEM_CAL: a pixel contour runs longer than the true outline, so the raw figure reads thin.
    return STEM_CAL * 2 * mask.sum() / per / em_px if per and em_px else None


def weight_of(ratio):
    if ratio is None:
        return None
    for (r0, w0), (r1, w1) in zip(WEIGHTS, WEIGHTS[1:]):
        if ratio <= r1:
            return int(round((w0 + (w1 - w0) * max(0.0, (ratio - r0) / (r1 - r0))) / 100) * 100)
    return 900


def caption_colours(crops, long_side, k=6):
    """crops: [(rgb, core box in crop px, text, line height px, sample index)].
    Fill and stroke are the colours that sit inside the OCR box in most captions and
    not a line-height away; the stroke is the one wrapped round the fill; a box colour
    fills the padding but not further out; a highlight is a saturated text colour
    that comes and goes."""
    rng = np.random.default_rng(0)
    pool, labs, regs = [], [], []
    for rgb, core, *_ in crops:
        c, near, far = regions(rgb.shape, core)
        regs.append((c, near, far))
        for m, n in ((c, 300), (far, 150)):
            px = rgb[m]
            if len(px):
                pool.append(px[rng.choice(len(px), min(n, len(px)), replace=False)])
    _, cen = kmeans(np.concatenate(pool), k)
    shares = []
    for (rgb, *_), (c, near, far) in zip(crops, regs):
        lab = nearest(rgb, cen)
        labs.append(lab)
        shares.append([[float(((lab == j) & m).sum()) / max(1, m.sum()) for m in (c, near, far)]
                       for j in range(len(cen))])
    S = np.array(shares)  # crops x clusters x (core, near, far)
    pres = (S[:, :, 0] >= 0.04).mean(0)
    core, near, far = (np.median(S[:, :, i], 0) for i in range(3))

    box = None
    for j in np.argsort(-near):
        if near[j] >= 0.5 and far[j] <= 0.5 * near[j] and pres[j] >= 0.6:
            box = int(j)
            break
    text = [j for j in range(len(cen)) if j != box and pres[j] >= 0.3 and core[j] >= 0.03
            and core[j] >= 1.5 * far[j] and near[j] <= 0.25]  # text stops at its box
    if not text:
        return None
    cores = [r[0] for r in regs]
    hs = [cr[3] for cr in crops]

    def luma(j):
        return float(cen[j] @ np.array([0.299, 0.587, 0.114]))

    def chroma(j):
        return float(cen[j].max() - cen[j].min())

    # Fill: the text colour covering most of the box in most captions. A one-word
    # highlight in a two-word caption covers as much, so a neutral colour wins the tie.
    # ponytail: a saturated fill with a neutral highlight reads backwards; the look pass names it.
    def score(j):
        return pres[j] * core[j] * (1.5 if chroma(j) < 60 else 1.0)
    order = sorted(text, key=lambda j: -score(j))
    fill, stroke = order[0], None
    # Stroke: a contrasting colour wrapped round the fill (the ring just outside the
    # fill is mostly it, while the ring outside it is not mostly fill). The anti-aliased
    # glyph edge also wraps the fill, but sits near its brightness, so it never counts.
    for b in order[1:]:
        # A real stroke covers a good share of what the fill does; the background seen
        # through the holes of o, a and e is a sliver.
        if abs(luma(fill) - luma(b)) < 100 or score(b) < 0.15 * score(fill):
            continue
        out, back = enclosure(labs, cores, fill, b, hs), enclosure(labs, cores, b, fill, hs)
        if back >= 0.3 and back > out + 0.15:   # b sits inside: b is the fill
            fill, stroke = b, fill
            break
        if out >= 0.3 and out > back + 0.15:
            stroke = b
            break

    def dist(a, b):
        return float(np.abs(cen[a] - cen[b]).sum())
    def blend(j):
        """True when j is a mix of the fill and another colour: an anti-aliased edge."""
        f = cen[fill]
        for o in range(len(cen)):
            if o in (j, fill):
                continue
            d = cen[o] - f
            t = float(np.clip((cen[j] - f) @ d / max(1e-6, d @ d), 0, 1))
            if np.linalg.norm(f + t * d - cen[j]) < 35:
                return True
        return False
    # A highlight is a text colour: never in the far ring (a shirt behind the captions
    # is) and not a blend of the fill with what is behind it.
    hi = [j for j in range(len(cen)) if j not in (fill, stroke, box) and chroma(j) >= 60
          and 0.08 <= pres[j] and far[j] < 0.02 and dist(j, fill) > 120 and not blend(j)]
    hi = max(hi, key=lambda j: pres[j]) if hi else None

    # Size from the x-height (or cap height): the band of rows most of the ink sits in.
    # It does not change with ascenders, descenders or the OCR engine, unlike a box.
    # Weight from the glyph stems against that em. A moving highlight from where it sits.
    ratios, ems, cx = [], [], []
    for (rgb, core_box, text_, h, si), lab, (c, _, _) in zip(crops, labs, regs):
        ink = ((lab == fill) | ((lab == hi) if hi is not None else False)) & c
        rows = ink.sum(1)
        if rows.max() < 3:
            continue
        letters = re.sub(r"[^A-Za-z]", "", text_)
        upper = letters.isupper() and len(letters) > 1
        em = int((rows >= 0.5 * rows.max()).sum()) / (CAP_H if upper else X_H)
        ems.append(em)
        r = stem_ratio(ink, em)
        if r:
            ratios.append(r)
        if hi is not None:
            m = (lab == hi) & c
            if m.sum() > 20:
                x0, _, x1, _ = core_box
                cx.append((si, text_, (np.nonzero(m)[1].mean() - x0) / max(1, x1 - x0)))
    moving = sum(1 for (s1, t1, c1), (s2, t2, c2) in zip(cx, cx[1:])
                 if s2 == s1 + 1 and t1 == t2 and len(t1.split()) > 1 and abs(c2 - c1) > 0.15)
    return {
        "color": hexc(cen[fill]),
        "stroke": stroke is not None,
        "stroke_color": hexc(cen[stroke]) if stroke is not None else None,
        "box": box is not None,
        "box_color": hexc(cen[box]) if box is not None else None,
        "highlight_color": hexc(cen[hi]) if hi is not None else None,
        "highlight_moves": moving >= 2,
        "stem_ratio": round(statistics.median(ratios), 3) if ratios else None,
        "size_pct": round(100 * statistics.median(ems) / long_side, 2) if ems else None,
    }


def entrance(path, src_fps, W, H, t0, t1, core, fill_rgb):
    """How one caption arrives: (kind, frames to settle). core: [x0, y0, x1, y1] px at W x H.
    Masks the fill colour at the source frame rate between two samples."""
    x0, y0, x1, y1 = core
    h = y1 - y0
    X0, Y0 = max(0, int(x0 - 0.6 * h)), max(0, int(y0 - 1.0 * h))
    X1, Y1 = min(W, int(x1 + 0.6 * h)), min(H, int(y1 + 1.0 * h))
    fill = np.array(fill_rgb, np.float32)
    ms = [np.abs(f[Y0:Y1, X0:X1].astype(np.float32) - fill).sum(-1) < 90
          for f in decode(path, W, H, None, t0, t1 - t0 + 0.25)]
    if len(ms) < 3:
        return None

    def iou(a, b):
        u = (a | b).sum()
        return (a & b).sum() / u if u else 1.0
    last, first = ms[-1], ms[0]
    area = last.sum()
    if area < 20:
        return None
    a = next((k for k, m in enumerate(ms) if m.sum() > 0.3 * area and iou(m, last) > iou(m, first)), None)
    if a is None or a == 0:
        return None
    s = next((k for k in range(a, len(ms)) if iou(ms[k], last) >= 0.85), len(ms) - 1)
    if s - a <= 2:  # settled within 2 frames: a cut, not an animation
        return "none", s - a
    ya = np.nonzero(ms[a])[0]
    yl = np.nonzero(last)[0]
    shift = abs(ya.mean() - yl.mean()) / h if len(ya) and len(yl) else 0
    return ("slide" if shift > 0.25 else "pop"), s - a


def ease_in(path, W, H, t0, t1, skip_rows):
    """Seconds a graphic takes to land: frames from first change to settled, source rate."""
    w, h = 160, round(160 * H / W / 2) * 2
    F = [f.astype(np.float32) for f in decode(path, w, h, None, t0, t1 - t0 + 0.6, gray=True)]
    if len(F) < 4:
        return None
    keep = np.ones(h, bool)
    if skip_rows:
        keep[int(skip_rows[0] * h):int(skip_rows[1] * h) + 1] = False
    # Only the pixels the graphic changed: a talking head moving around it would
    # otherwise read as a slow ease.
    m = (np.abs(F[0] - F[-1]) > 25) & keep[:, None]
    if m.mean() < 0.01:
        return None
    d = [float(np.abs(f - F[-1])[m].mean()) for f in F]
    a = next((k for k, v in enumerate(d) if v < 0.85 * d[0]), None)
    s = next((k for k, v in enumerate(d) if v <= 0.2 * d[0]), None)
    if a is None or s is None:
        return None
    return s - a + 1


# ---------- one video ----------

def load_words(tdir, vid):
    p = tdir / f"{vid}.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text())
    return [(norm(w["text"]), w["start"]) for w in d.get("words", []) if w.get("type") == "word"]


def measure_video(path, words, ocr=None, faces=None, engine="vision", fps=SAMPLE_FPS):
    w0, h0, src_fps, dur = probe(path)
    W = min(WORK_W, w0) // 2 * 2
    H = round(W * h0 / w0 / 2) * 2
    em_k = EM_PER_BOX.get(engine, 1.0)
    samples, thumbs = [], []
    for i, f in enumerate(decode(path, W, H, fps)):
        t = round(i / fps, 3)
        lines = [{"text": tx, "box": [round(v, 4) for v in b]} for tx, b in (ocr(f, t) if ocr else [])]
        samples.append({"t": t, "lines": lines, "face": faces(f) if faces else None})
        thumbs.append(f[::max(1, H // 96), ::max(1, W // 54)].reshape(-1, 3))
    n = len(samples)
    if not n:
        raise SystemExit(f"no frames decoded from {path}")
    find_captions(samples, words)

    # Captions: place, size, words, case.
    caps = [(i, block(s)) for i, s in enumerate(samples) if block(s)]
    cap = {"present": bool(ocr) and len(caps) >= 0.1 * n, "samples": len(caps)}
    if not ocr:
        cap["present"] = None  # unknown: no OCR engine
    long_side = max(W, H)
    if cap["present"]:
        ys = [(b[0]["box"][1] + b[-1]["box"][1] + b[-1]["box"][3]) / 2 for _, b in caps]
        xs = [b[0]["box"][0] + b[0]["box"][2] / 2 for _, b in caps]
        hs = [ln["box"][3] * H / long_side for _, b in caps for ln in b]
        text = " ".join(ln["text"] for _, b in caps for ln in b)
        letters = re.sub(r"[^A-Za-z]", "", re.sub(r"\bI\b", "", text))
        up = sum(ch.isupper() for ch in letters) / max(1, len(letters))
        cap.update({
            "y_pct": round(100 * statistics.median(ys), 1),
            "x_pct": round(100 * statistics.median(xs), 1),
            "size_pct": round(100 * statistics.median(hs) / em_k, 2),
            "words_per_caption": int(round(statistics.median(sum(len(ln["text"].split()) for ln in b)
                                                             for _, b in caps))),
            "lines": int(round(statistics.median(len(b) for _, b in caps))),
            "case": "upper" if up > 0.9 else "lower" if up < 0.03 else "sentence",
        })
        # Second decode: crops of up to 60 caption lines, spread over the video.
        want = {i for i, _ in caps[::max(1, len(caps) // 60)]}
        crops = []
        for i, f in enumerate(decode(path, W, H, fps)):
            if i not in want:
                continue
            for ln in block(samples[i]):
                x, y, bw, bh = ln["box"]
                x0, y0, x1, y1 = int(x * W), int(y * H), int((x + bw) * W), int((y + bh) * H)
                ph = y1 - y0
                X0, Y0 = max(0, x0 - ph), max(0, y0 - ph)
                crop = f[Y0:min(H, y1 + ph), X0:min(W, x1 + ph)]
                crops.append((crop, (x0 - X0, y0 - Y0, x1 - X0, y1 - Y0), ln["text"], ph, i))
        col = caption_colours(crops, long_side) if crops else None
        if col:
            cap.update({k: v for k, v in col.items() if v is not None or k != "size_pct"})
            fill = [int(col["color"][k:k + 2], 16) for k in (1, 3, 5)]
            kinds, frames = [], []
            onsets = [i for (i, b), (_, pb) in zip(caps[1:], caps) if
                      " ".join(ln["text"] for ln in b) != " ".join(ln["text"] for ln in pb)]
            for i in onsets[::max(1, len(onsets) // 8)][:8]:
                ln = block(samples[i])[0]
                x, y, bw, bh = ln["box"]
                r = entrance(path, src_fps, W, H, samples[i - 1]["t"], samples[i]["t"],
                             (x * W, y * H, (x + bw) * W, (y + bh) * H), fill)
                if r:
                    kinds.append(r[0])
                    frames.append(r[1])
            cap["entrance"] = Counter(kinds).most_common(1)[0][0] if kinds else None
            cap["ease_s"] = round(statistics.median(frames) / src_fps, 3) if frames else None

    # Face framing.
    fs = [s["face"] for s in samples if s["face"]]
    face = {"present_pct": round(100 * len(fs) / n)}
    if fs:
        fh = statistics.median(f[3] for f in fs)
        face.update({"x_pct": round(100 * statistics.median(f[0] + f[2] / 2 for f in fs), 1),
                     "y_pct": round(100 * statistics.median(f[1] + f[3] / 2 for f in fs), 1),
                     "height_pct": round(100 * fh, 1),
                     "framing": "close" if fh >= 0.22 else "medium" if fh >= 0.12 else "wide"})

    # Graphics: screen text that is not a caption and not set dressing, or no face
    # in a video that mostly shows one.
    # Text in the caption band is a caption the OCR misread, not a graphic.
    seen = Counter(norm(ln["text"]) for s in samples for ln in s["lines"])
    has_face = len(fs) >= 0.3 * n
    cy = [ln["box"][1] + ln["box"][3] / 2 for s in samples for ln in s["lines"] if ln.get("cap")]
    band_y = statistics.median(cy) if cy else -1
    flags = []
    for s in samples:
        area = sum(ln["box"][2] * ln["box"][3] for ln in s["lines"]
                   if not ln.get("cap") and seen[norm(ln["text"])] < 0.5 * n
                   and abs(ln["box"][1] + ln["box"][3] / 2 - band_y) > 0.04)
        flags.append(area >= 0.004 or (has_face and not s["face"]))
    runs, k = [], 0
    while k < n:
        if flags[k]:
            j = k
            while j + 1 < n and (flags[j + 1] or (j + 2 < n and flags[j + 2])):
                j += 1
            runs.append((k, j))
            k = j + 1
        else:
            k += 1
    band = None
    if cap.get("present"):
        band = ((cap["y_pct"] - 4) / 100, (cap["y_pct"] + 4) / 100)
    # Over half a second is moving footage inside the graphic, not an ease: dropped.
    eases = [e for e in (ease_in(path, W, H, samples[a - 1]["t"], samples[a]["t"], band)
                         for a, _ in runs[:8] if a > 0) if e and e / src_fps <= 0.5]
    gfx = [thumbs[i] for i, f in enumerate(flags) if f]
    palette = []
    if gfx:
        px = np.concatenate(gfx)
        px = px[np.random.default_rng(0).choice(len(px), min(20000, len(px)), replace=False)]
        lab, cen = kmeans(px, 5)
        cnt = np.bincount(lab, minlength=len(cen))
        palette = [{"hex": hexc(cen[j]), "pct": round(100 * cnt[j] / len(lab))} for j in np.argsort(-cnt)]
    graphics = {
        "share_pct": round(100 * sum(flags) / n),
        "per_min": round(len(runs) / dur * 60, 1),
        "hold_s": round(statistics.median((b - a + 1) / fps for a, b in runs), 2) if runs else None,
        "ease_in_s": round(statistics.median(eases) / src_fps, 3) if eases else None,
        "palette": palette,
    }
    return {"id": path.stem, "duration_s": round(dur, 2), "engine": engine if ocr else None,
            "captions": cap, "face": face, "graphics": graphics,
            "samples": [{"t": s["t"], "face": s["face"],
                         "lines": [[ln["text"], ln["box"], bool(ln.get("cap"))] for ln in s["lines"]]}
                        for s in samples]}


# ---------- one creator ----------

def mode(xs):
    xs = [x for x in xs if x is not None]
    return Counter(xs).most_common(1)[0][0] if xs else None


def med(xs, nd=2):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), nd) if xs else None


def personality(cpm, ease, hold, punch_pm):
    """snappy / punchy / smooth / calm from measured numbers, so the motion engine can pick."""
    if ease is not None and ease >= 0.3:
        return "smooth"
    if (punch_pm or 0) >= 5 and (cpm or 0) >= 10:
        return "punchy"
    if (cpm or 0) >= 15:
        return "snappy"
    if (cpm or 0) < 8 and (hold or 0) >= 3:
        return "calm"
    return "snappy" if ease is not None and ease <= 0.1 else "smooth"


def merge(rows, visuals, style):
    """Per-video look.json rows -> the style.json blocks (medians and majorities)."""
    cs = [r["captions"] for r in rows if r["captions"].get("present")]
    measured = [r for r in rows if r["captions"].get("present") is not None]
    cap = dict(style.get("captions") or {})
    if measured:
        cap["present"] = len(cs) >= len(measured) / 2
    if cs:
        cap.update({
            "words_per_caption": int(round(statistics.median(c["words_per_caption"] for c in cs))),
            "lines": int(round(statistics.median(c["lines"] for c in cs))),
            "y_pct": med([c["y_pct"] for c in cs], 1),
            "x_pct": med([c["x_pct"] for c in cs], 1),
            "size_pct": med([c["size_pct"] for c in cs], 2),
            "case": mode(c["case"] for c in cs),
        })
        cc = [c for c in cs if "color" in c]
        if cc:
            weight = weight_of(med([c.get("stem_ratio") for c in cc], 3))
            ent = mode(c.get("entrance") for c in cc)
            moves = sum(c.get("highlight_moves", False) for c in cc) >= len(cc) / 2
            cap.update({
                "color": mode(c["color"] for c in cc),
                "stroke": mode(c["stroke"] for c in cc),
                "stroke_color": mode(c.get("stroke_color") for c in cc),
                "box": mode(c["box"] for c in cc),
                "box_color": mode(c.get("box_color") for c in cc),
                "highlight_color": mode(c.get("highlight_color") for c in cc) if
                sum(1 for c in cc if c.get("highlight_color")) >= len(cc) / 2 else None,
                "entrance": ent,
                "ease_s": med([c.get("ease_s") for c in cc], 3),
                "animation": "word_highlight" if moves else (ent or "none"),
            })
            if weight:
                cap["weight"] = weight
        cap["source"] = {**(cap.get("source") or {}), "numbers": "ocr"}
    fs = [r["face"] for r in rows]
    face = {"present_pct": med([f["present_pct"] for f in fs], 0),
            "x_pct": med([f.get("x_pct") for f in fs], 1), "y_pct": med([f.get("y_pct") for f in fs], 1),
            "height_pct": med([f.get("height_pct") for f in fs], 1),
            "framing": mode(f.get("framing") for f in fs)}
    gs = [r["graphics"] for r in rows]
    pal = Counter()
    for g in gs:
        for p in g["palette"]:
            pal[p["hex"]] += p["pct"]
    tot = sum(pal.values()) or 1
    graphics = {"share_pct": med([g["share_pct"] for g in gs], 0),
                "per_min": med([g["per_min"] for g in gs], 1),
                "hold_s": med([g["hold_s"] for g in gs]),
                "ease_in_s": med([g["ease_in_s"] for g in gs], 3),
                "palette": [{"hex": h, "pct": round(100 * c / tot)} for h, c in pal.most_common(6)]}
    cpm = med([len(v["cuts"]) / v["duration_s"] * 60 for v in visuals if v.get("duration_s")], 1)
    zoom = style.get("zoom") or {}
    punch = zoom.get("per_min") if zoom.get("kind") == "punch" else 0
    motion = {"cuts_per_min": cpm, "ease_in_s": graphics["ease_in_s"], "hold_s": graphics["hold_s"],
              "caption_ease_s": cap.get("ease_s"), "zoom_punch_per_min": punch}
    motion["personality"] = personality(cpm, motion["ease_in_s"], motion["hold_s"], punch)
    return {"captions": cap, "face": face, "graphics": graphics, "motion": motion}


def summary(style, rows_n=None):
    """The <48-line text Claude reads instead of frames."""
    c, f, g, m = (style.get(k) or {} for k in ("captions", "face", "graphics", "motion"))
    # One source for the graphics numbers: graphics.py's per-card measure when it has run (report.py
    # shows the same), else look.py's frame estimate, labelled as such.
    if "share_pct_measured" in g:
        gsrc, gshare, gpm, ghold = (f"{g.get('measured')} cards measured", g["share_pct_measured"],
                                    g.get("per_min_measured"), g.get("hold_s_measured"))
    else:
        gsrc, gshare, gpm, ghold = "frame estimate", g.get("share_pct"), g.get("per_min"), g.get("hold_s")
    p, z, lk = style.get("pace") or {}, style.get("zoom") or {}, style.get("look") or {}
    L = [f"# Look: @{style.get('handle')} ({style.get('videos', rows_n)} videos, measured)", ""]
    if p:
        L.append(f"Pace: {p.get('wpm')} wpm, a cut every {p.get('median_shot_s')} s "
                 f"({m.get('cuts_per_min')} a minute), pauses up to {p.get('max_pause_s')} s.")
    if z:
        L.append(f"Zoom: {z.get('kind')} x{z.get('scale')}, {z.get('per_min')} a minute, on {z.get('on')}.")
    if m:
        L.append(f"Motion: {m.get('personality')}. Graphics land in {m.get('ease_in_s')} s. "
                 f"Captions settle in {m.get('caption_ease_s')} s.")
    L.append("")
    if c.get("present") is False:
        L.append("Captions: none burned in.")
    elif c.get("present"):
        L += [f"Captions: {c.get('words_per_caption')} word(s), {c.get('lines')} line(s), {c.get('case')} case, "
              f"centre at {c.get('y_pct')}% down, {c.get('x_pct')}% across.",
              f"  size {c.get('size_pct')}% of the long side, weight {c.get('weight')}, "
              f"font {c.get('font_match') or 'not named (no look pass: gemini.py look or the sheet fallback names it)'}",
              f"  fill {c.get('color')}, stroke {c.get('stroke_color') if c.get('stroke') else 'none'}, "
              f"box {c.get('box_color') if c.get('box') else 'none'}, highlight {c.get('highlight_color')}",
              f"  enters: {c.get('entrance')}, animation: {c.get('animation')}"]
    else:
        L.append("Captions: not measured (no OCR engine). Run the fallback sheet pass.")
    L.append("")
    if f:
        L.append(f"Face: on screen {f.get('present_pct')}% of the time, {f.get('framing')} "
                 f"(face {f.get('height_pct')}% of the height), centred {f.get('x_pct')}% across, "
                 f"{f.get('y_pct')}% down.")
    if g:
        L.append(f"Graphics ({gsrc}): on screen {gshare}% of the runtime, {gpm} a minute, hold {ghold} s.")
        L.append("  palette (frames with graphics; the AI-tell scan reads this one): " + ", ".join(f"{x['hex']} {x['pct']}%" for x in g.get("palette", [])))
        if g.get("kinds"):
            L.append("  kinds: " + ", ".join(f"{k} {v}%" for k, v in list(g["kinds"].items())[:5]))
        if g.get("entrances"):
            L.append("  enter: " + "; ".join(f"{e['kind']} {e['ease']} {e['duration_s']} s {e['share_pct']}%"
                                             for e in g["entrances"][:3]))
        lay = g.get("layout") or {}
        if lay.get("zones_pct"):
            L.append("  sit: " + ", ".join(f"{k} {v}%" for k, v in lay["zones_pct"].items())
                     + f"; over the face {lay.get('covers_face_pct')}%")
    snd = style.get("sound") or {}
    if snd:
        L.append(f"Sound: {snd.get('sfx_per_min')} effects a minute {snd.get('kinds') or ''}, "
                 f"music in {(snd.get('music') or {}).get('present_pct')}% of videos.")
    cam = style.get("camera") or {}
    if cam:
        L.append(f"Camera: {cam.get('pan_per_min')} pans, {cam.get('push_per_min')} pushes a minute; "
                 f"cuts {(style.get('pace') or {}).get('cut_kinds')}")
    win = style.get("winners") or {}
    for line in (win.get("differs") or [])[:4]:
        L.append("Winners: " + line)
    tells = style.get("ai_tells") or {}
    if tells.get("ran"):
        named = "; ".join(f"{t['level']} {t['tell']} ({t['where']})" for t in (tells.get("found") or [])[:6])
        L.append(f"AI tells in their look: {tells.get('bans')} BAN, {tells.get('warns')} WARN" + (f": {named}" if named else "") + ".")
    cards = style.get("cats")
    if cards:
        L.append(f"Cards (events.json): {style.get('per_min')} a minute, kinds: " + ", ".join(cards))
    if lk:
        L += ["", f"Look ({lk.get('source')}): {lk.get('font_class')} font, {lk.get('weight_class')}, "
              f"{lk.get('caption_animation')} captions, {lk.get('motion_personality')} motion.",
              "  graphics: " + ", ".join(lk.get("graphics_style") or []),
              "  transitions: " + ", ".join(lk.get("transitions") or []),
              "  b-roll: " + ", ".join(lk.get("broll_types") or []),
              "  not generic:"] + [f"  - {x}" for x in (lk.get("not_generic") or [])[:6]]
    return "\n".join(L[:48]) + "\n"


def write_summary(outdir):
    style = json.loads((outdir / "style.json").read_text())
    text = summary(style)
    (outdir / "look.md").write_text(text)
    return text


def cmd_measure(a):
    outdir = OUT_ROOT / slug(a.handle)
    vids = sorted((outdir / "video").glob("*.mp4"))
    if not vids:
        sys.exit(f"no videos in {outdir / 'video'}. Run visual.py download first.")
    engine, ocr = ocr_engine()
    if not ocr:
        print("no OCR engine (ocrmac or rapidocr): captions are left to the sheet pass", file=sys.stderr)
    faces = face_detector()
    rows = []
    for p in vids:
        cache = p.with_suffix(".look.json")
        if cache.exists() and not a.force:
            rows.append(json.loads(cache.read_text()))
            print(f"{p.stem} cached", file=sys.stderr)
            continue
        print(f"{p.stem} measuring", file=sys.stderr)
        r = measure_video(p, load_words(outdir / "transcripts", p.stem), ocr, faces, engine, a.fps)
        cache.write_text(json.dumps(r, default=float))
        rows.append(r)
        c = r["captions"]
        print(f"  captions {c.get('present')} ({c['samples']} samples) y {c.get('y_pct')} "
              f"size {c.get('size_pct')} {c.get('color')}; graphics {r['graphics']['share_pct']}%",
              file=sys.stderr)
    visuals = [json.loads(p.read_text()) for p in sorted((outdir / "video").glob("*.visual.json"))]
    sp = outdir / "style.json"
    style = json.loads(sp.read_text()) if sp.exists() else {"handle": slug(a.handle)}
    style.update(merge(rows, visuals, style))
    sp.write_text(json.dumps(style, indent=2, default=float))
    print(write_summary(outdir))
    print(f"-> {sp}\n-> {outdir / 'look.md'}")


# ---------- self-check ----------

def demo():
    """6 s, 540 x 960, 30 fps. Two-word captions centred at 65% down, 48 px, white with a
    black stroke, a yellow highlight that moves word to word, each caption popping in over
    4 frames. A blue card fades in over 6 frames at 3.0 s and leaves at 4.5 s.
    The OCR is the real engine when one is installed, else a stand-in that knows where the
    text was drawn, so CI checks the measuring without an OCR package."""
    from PIL import Image, ImageDraw, ImageFont
    W, H, FPS, SIZE = 540, 960, 30, 48
    font = ImageFont.load_default(size=SIZE)
    words = ["build", "this", "right", "now", "every", "single", "day", "with", "real", "tools",
             "and", "ship"]
    caps = [(words[k], words[k + 1]) for k in range(0, 12, 2)]  # one caption a second
    rng = np.random.default_rng(1)
    bg = np.asarray(Image.fromarray((rng.random((H // 24, W // 24, 3)) * 160 + 40).astype(np.uint8))
                    .resize((W, H), Image.BICUBIC))
    drawn = {}

    def frame(i):
        t = i / FPS
        im = Image.fromarray(bg.copy())
        d = ImageDraw.Draw(im)
        if 3.0 <= t < 4.5:
            a = min(1.0, (i - 90) / 6)
            card = Image.new("RGB", (W - 120, 300), (51, 102, 255))
            ImageDraw.Draw(card).text((30, 120), "pricing page", fill="white", font=font)
            im.paste(Image.blend(im.crop((60, 120, W - 60, 420)), card, a), (60, 120))
        ci = int(t)
        a, b = caps[ci]
        k = i - ci * FPS
        s = 0.6 + 0.4 * min(1.0, k / 4)
        f = ImageFont.load_default(size=round(SIZE * s))
        full = f"{a} {b}"
        x0, y0, x1, y1 = d.textbbox((0, 0), full, font=f, stroke_width=4)
        X, Y = (W - (x1 - x0)) / 2 - x0, 0.65 * H - (y1 + y0) / 2
        hi = 0 if (t - ci) < 0.5 else 1
        d.text((X, Y), full, font=f, fill="white", stroke_width=4, stroke_fill="black")
        aw = d.textlength(a + " ", font=f)
        word = (a, X) if hi == 0 else (b, X + aw)
        d.text((word[1], Y), word[0], font=f, fill=(255, 225, 60), stroke_width=4, stroke_fill="black")
        bb = d.textbbox((X, Y), full, font=f)
        drawn[i] = [(full, [bb[0] / W, bb[1] / H, (bb[2] - bb[0]) / W, (bb[3] - bb[1]) / H])]
        if 3.0 <= t < 4.5:
            drawn[i].append(("pricing page", [90 / W, 240 / H, 300 / W, 60 / H]))
        return np.asarray(im)

    with tempfile.TemporaryDirectory() as tmp:
        mp4 = Path(tmp) / "demo.mp4"
        raw = b"".join(frame(i).tobytes() for i in range(6 * FPS))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                        f"{W}x{H}", "-r", str(FPS), "-i", "-", "-pix_fmt", "yuv420p", "-c:v", "libx264",
                        "-crf", "16", str(mp4)], input=raw, check=True)
        spoken_words = [(norm(w), k * 0.5 + 0.1) for k, w in enumerate(words)]
        engine, ocr = ocr_engine()
        if not ocr:
            # A stand-in that knows where the text was drawn: its box is one em tall.
            engine, ocr = "fake", lambda f, t: drawn[min(round(t * FPS), 6 * FPS - 1)]
        r = measure_video(mp4, spoken_words, ocr, None, engine, SAMPLE_FPS)
        c, g = r["captions"], r["graphics"]
        print(f"engine {engine}: {json.dumps({k: c.get(k) for k in ('y_pct', 'size_pct', 'words_per_caption', 'color', 'stroke_color', 'highlight_color', 'entrance', 'ease_s', 'stem_ratio')})}")
        print(f"graphics {json.dumps(g)}")
        assert c["present"], c
        assert c["words_per_caption"] == 2 and c["case"] == "lower", c
        assert abs(c["y_pct"] - 65) <= 2.5, c["y_pct"]
        assert abs(c["size_pct"] - 100 * SIZE / H) <= 0.8, c["size_pct"]
        assert c["color"] == "#FFFFFF" and c["stroke"] and c["stroke_color"] == "#000000", c
        hr, hg, hb = (int(c["highlight_color"][k:k + 2], 16) for k in (1, 3, 5))
        assert hr > 200 and hg > 170 and hb < 130, c["highlight_color"]
        assert c["highlight_moves"] and not c["box"], c
        assert 300 <= weight_of(c["stem_ratio"]) <= 500, c["stem_ratio"]  # the font is a 400
        assert c["entrance"] == "pop" and 0.06 <= c["ease_s"] <= 0.2, c
        assert 15 <= g["share_pct"] <= 35 and g["per_min"] == 10.0, g
        assert g["ease_in_s"] and 0.1 <= g["ease_in_s"] <= 0.3, g
        assert any(p["hex"][5:7] > "B0" and p["hex"][1:3] < "60" for p in g["palette"]), g["palette"]
        m = merge([r], [{"cuts": [1, 2, 3], "duration_s": 6.0}], {"zoom": {"kind": "punch", "per_min": 6}})
        assert m["captions"]["animation"] == "word_highlight" and m["motion"]["cuts_per_min"] == 30.0, m
        assert m["motion"]["personality"] == "punchy", m["motion"]
        assert personality(4, 0.05, 4, 0) == "calm" and personality(20, 0.4, 1, 0) == "smooth"
        assert weight_of(0.15) == 700 and weight_of(0.09) == 400 and weight_of(0.5) == 900
        assert len(summary({"handle": "x", **m}).splitlines()) <= 48
        # No Gemini key: no placeholder, one graphics source (graphics.py's), the AI tells named.
        txt = summary({"handle": "x", **m, "captions": {"present": True},
                       "graphics": {"share_pct": 55, "per_min": 5.7, "hold_s": 9.0, "palette": [],
                                    "measured": 6, "share_pct_measured": 3, "per_min_measured": 1.7, "hold_s_measured": 1.2},
                       "ai_tells": {"ran": True, "bans": 1, "warns": 0,
                                    "found": [{"level": "BAN", "tell": "glass-panel", "where": "look 'creator'"}]}})
        assert "[" not in txt and "55%" not in txt and "9.0 s" not in txt, txt
        assert "on screen 3%" in txt and "1.7 a minute" in txt and "BAN glass-panel" in txt, txt
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("measure")
    p.add_argument("handle")
    p.add_argument("--fps", type=float, default=SAMPLE_FPS)
    p.add_argument("--force", action="store_true", help="re-measure cached videos")
    p.set_defaults(fn=cmd_measure)
    p = sub.add_parser("summary")
    p.add_argument("handle")
    p.set_defaults(fn=lambda a: print(write_summary(OUT_ROOT / slug(a.handle))))
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
