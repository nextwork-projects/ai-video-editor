#!/usr/bin/env python3
"""The visual pass: measure how a creator edits, from their real videos.

  download <handle>   yt-dlp the picked videos to creator-teardowns/<handle>/video/.
                      Same pick as fetch.py transcribe: --top most-viewed plus
                      --control closest to the median, or --ids.
  measure <handle>    per video: cut times, shot lengths, zoom events and one contact
                      sheet. Writes video/<id>.visual.json and sheets/<id>.jpg,
                      then merges `pace` and `zoom` into style.json.
  demo                self-check on a synthetic video (hard cut, zoom step, push).

Cuts. ffmpeg scene detection misses jump cuts on a locked-off camera: the
framing never changes, so the scene score stays low. Instead every frame is
differenced against the next, and a frame that spikes well above its neighbours
is a candidate. A candidate counts as a cut when most of the frame changed
(median block difference) or the brightness histogram jumped. A candidate whose
"after" frame is just a scaled copy of the "before" frame is a zoom punch, not
a cut.

Zooms. For each candidate and for frames 0.5 s apart inside each shot, a centre
crop of one frame is searched over scales and offsets for the best match with
the other. A scale step at one frame is a punch; a run of small steps is a push.

Usage (run with the tool venv python: numpy + pillow + ffmpeg):
  ~/.ai-video-editor/venv/bin/python scripts/visual.py download <handle> [--top 8] [--control 2]
  ~/.ai-video-editor/venv/bin/python scripts/visual.py measure <handle>
  ~/.ai-video-editor/venv/bin/python scripts/visual.py demo

Exit codes: 0 ok - 1 error - 2 usage
"""
import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from parallel import pmap

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, count_line, pick, slug, ytdlp  # noqa: E402

SMALL = 108          # short side of the analysis frames, px
BLOCK = 8            # block size for the median block difference
SPIKE = 2.5          # a candidate is this many times its neighbours' median
WIN = 7              # neighbours on each side, frames
SHOT_R = 10.0        # median block difference (0-255) that means a new picture
SHOT_H = 0.30        # histogram jump (L1, 0-2) that means a new picture
ZOOM_H = 0.15        # below this histogram jump, a scaled match is a pure zoom
PUNCH_SCALES = [1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6, 1.8, 2.0]
PUSH_SCALES = [1.02, 1.04, 1.06, 1.08, 1.1, 1.15]
PUSH_STEP_S = 0.5


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json",
                        str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), float(d["format"]["duration"])


def gray_frames(path, w, h, fps=None):
    vf = (f"fps={fps}," if fps else "") + f"scale={w}:{h},format=gray"
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", vf,
                          "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, np.uint8)
    n = a.size // (w * h)
    return a[:n * w * h].reshape(n, h, w).astype(np.float32)


def block_median(a, b):
    """Median over 8x8 blocks of |a - b|. Robust to a person moving or a card
    popping on: most blocks are background, so only a new picture moves it."""
    h, w = (a.shape[0] // BLOCK) * BLOCK, (a.shape[1] // BLOCK) * BLOCK
    r = np.abs(a[:h, :w] - b[:h, :w]).reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK)
    return float(np.median(r.mean(axis=(1, 3))))


def hist_jump(a, b):
    ha = np.histogram(a, 32, (0, 256))[0] / a.size
    hb = np.histogram(b, 32, (0, 256))[0] / b.size
    return float(np.abs(ha - hb).sum())


def best_scale(a, b, scales):
    """(scale, residual): b looks like a zoomed by `scale` (>1 in, <1 out).
    Searches a 5x5 grid of crop offsets per scale, both directions."""
    h, w = a.shape
    best = (1.0, block_median(a, b))
    for src, dst, sign in ((a, b, 1), (b, a, -1)):
        im = Image.fromarray(src.astype(np.uint8))
        for s in scales:
            cw, ch = w / s, h / s
            for dx in np.linspace(-(w - cw) / 2, (w - cw) / 2, 5):
                for dy in np.linspace(-(h - ch) / 2, (h - ch) / 2, 5):
                    x0, y0 = (w - cw) / 2 + dx, (h - ch) / 2 + dy
                    z = np.asarray(im.resize((w, h), Image.BILINEAR,
                                             box=(x0, y0, x0 + cw, y0 + ch)), np.float32)
                    r = block_median(z, dst)
                    if r < best[1]:
                        best = (s ** sign, r)
    return best


def candidates(F):
    """Frames whose difference to the next spikes above their neighbours."""
    d = np.abs(np.diff(F, axis=0)).mean(axis=(1, 2))
    out = []
    for i in range(len(d)):
        lo, hi = max(0, i - WIN), min(len(d), i + WIN + 1)
        nb = np.concatenate([d[lo:i], d[i + 1:hi]])
        base = float(np.median(nb)) if nb.size else 0.0
        if d[i] == d[lo:hi].max() and d[i] > max(SPIKE * base, SPIKE):
            out.append(i)
    return out


def analyse(F, fps):
    """Cuts and zooms from grey frames at the source frame rate."""
    n = len(F)
    cuts, zooms = [], []
    for i in candidates(F):
        a, b = F[max(0, i - 1)], F[min(n - 1, i + 2)]
        r1, hj = block_median(a, b), hist_jump(F[i], F[i + 1])
        if r1 <= SHOT_R and hj <= SHOT_H:
            continue  # a gesture, or a small graphic
        t = round((i + 1) / fps, 3)
        s, rb = best_scale(a, b, PUNCH_SCALES) if r1 > 2 else (1.0, r1)
        scaled = s != 1.0 and rb < 0.5 * r1
        if scaled:
            zooms.append({"t": t, "kind": "punch", "scale": round(s, 2), "duration_s": 0.0,
                          "on_cut": hj >= ZOOM_H})
        if not (scaled and hj < ZOOM_H):
            cuts.append(t)

    # Pushes: steady scale change inside a shot, sampled every PUSH_STEP_S.
    edges = [0.0] + cuts + [n / fps]
    step = max(1, round(PUSH_STEP_S * fps))
    for s0, s1 in zip(edges, edges[1:]):
        idx = list(range(int(s0 * fps) + 2, int(s1 * fps) - 2, step))
        run = []
        for j, k in zip(idx, idx[1:]):
            s, rb = best_scale(F[j], F[k], PUSH_SCALES)
            moving = s != 1.0 and rb < 0.7 * block_median(F[j], F[k])
            if moving and (not run or (s > 1) == (run[-1][2] > 1)):
                run.append((j, k, s))
                continue
            if len(run) >= 2:
                zooms.append(push(run, fps))
            run = [(j, k, s)] if moving else []
        if len(run) >= 2:
            zooms.append(push(run, fps))
    zooms.sort(key=lambda z: z["t"])
    return cuts, zooms


def sharpness(f):
    """Variance of a 4-neighbour Laplacian: drops when a frame is motion-blurred."""
    lap = -4 * f[1:-1, 1:-1] + f[:-2, 1:-1] + f[2:, 1:-1] + f[1:-1, :-2] + f[1:-1, 2:]
    return float(lap.var())


def cut_kind(F, c, fps, punch_here):
    """What kind of cut lands at frame c (the first frame after it):
    zoom-punch  the next shot is the same picture scaled (visual.py's punch on a cut)
    whip        the frames round the cut are motion-blurred (sharpness under 40% of the shots')
    dissolve    over 2+ frames every pixel is a blend of the two shots
    mask        over 2+ frames part of the frame is already the next shot, part still the last
    jump        the set lines up across the cut (a third of the frame or more unchanged)
    match       an instant change to a new picture whose layout of edges lines up with the last
    hard        an instant change to a new picture"""
    n = len(F)
    if punch_here:
        return "zoom-punch"
    pre, post = F[max(0, c - 4)], F[min(n - 1, c + 3)]
    around = [sharpness(F[k]) for k in range(max(0, c - 2), min(n, c + 2))]
    shots = [sharpness(F[k]) for k in list(range(max(0, c - 9), max(0, c - 4))) + list(range(min(n, c + 4), min(n, c + 9)))]
    if shots and around and min(around) < 0.4 * float(np.median(shots)):
        return "whip"
    big = np.abs(post - pre) > 20
    step = float(np.abs(F[c] - F[c - 1])[big].mean() / (np.abs(post - pre)[big].mean() + 1e-6)) if big.any() else 1.0
    if big.mean() > 0.05 and step < 0.6:     # most of the change is not in the one frame: gradual
        mids = []
        for k in range(max(0, c - 3), min(n, c + 3)):
            p = np.clip(np.abs(F[k] - pre)[big] / (np.abs(post - pre)[big] + 1e-6), 0, 1)
            if 0.15 < p.mean() < 0.85:
                mids.append(p)
        if len(mids) >= 2:
            p = np.concatenate(mids)
            return "mask" if ((p < 0.2) | (p > 0.8)).mean() > 0.6 else "dissolve"
    h, w = (F[c].shape[0] // BLOCK) * BLOCK, (F[c].shape[1] // BLOCK) * BLOCK
    blocks = np.abs(F[c - 1][:h, :w] - F[c][:h, :w]).reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).mean(axis=(1, 3))
    if (blocks < 8).mean() >= 0.3:
        return "jump"

    def edges(f):
        gy, gx = np.gradient(f)
        e = np.hypot(gx, gy)
        hh, ww = (e.shape[0] // 12) * 12, (e.shape[1] // 12) * 12
        e = e[:hh, :ww].reshape(hh // 12, 12, ww // 12, 12).mean(axis=(1, 3)).ravel()
        return (e - e.mean()) / (e.std() + 1e-6)
    if float(np.mean(edges(F[c - 1]) * edges(F[c]))) > 0.6:
        return "match"
    return "hard"


def camera(F, fps, cuts, zooms):
    """Pans and shake inside shots, from frame-to-frame shifts (phase correlation).
    pan: the top third (mostly the set) drifts 2% of the width a second or more for 1 s. shake: frame-to-frame
    jitter round the drift over 0.4% of the width. Returns per-minute rates and runtime shares."""
    import cv2
    n = len(F)
    if n < 4:
        return {"pan_per_min": 0.0, "shake_pct": 0, "pans": []}
    W = F.shape[2]
    edges = [0] + [round(c * fps) for c in cuts] + [n]
    pushing = np.zeros(n, bool)
    for z in zooms:
        if z["kind"] == "push":
            pushing[int(z["t"] * fps):int((z["t"] + z["duration_s"]) * fps) + 1] = True
    pans, shaky = [], 0
    top = F.shape[1] // 3
    win = cv2.createHanningWindow((F.shape[2], top), cv2.CV_32F)
    for a, b in zip(edges, edges[1:]):
        if b - a < fps:
            continue
        # The top third: mostly the set, so the speaker's own movement does not read as a pan.
        pc = [cv2.phaseCorrelate(F[k][:top], F[k + 1][:top], win) for k in range(a + 1, b - 2)]
        # A weak peak is a plain wall or a graphic changing, not the camera: no shift.
        d = np.array([sh if r >= 0.3 else (0.0, 0.0) for sh, r in pc])
        if not len(d):
            continue
        d = d * ~pushing[a + 1:b - 2, None]
        k = max(3, int(0.5 * fps))
        smooth = np.stack([np.convolve(d[:, j], np.ones(k) / k, "same") for j in (0, 1)], 1)
        jitter = np.hypot(*(d - smooth).T)
        shaky += int((np.convolve(jitter > 0.004 * W, np.ones(k), "same") >= k / 2).sum())
        speed = np.hypot(*smooth.T) * fps / W            # widths a second
        run = speed > 0.02
        idx = np.nonzero(run)[0]
        if len(idx):
            for r in np.split(idx, np.nonzero(np.diff(idx) > 1)[0] + 1):
                v = d[r].sum(0)
                steady = np.hypot(*v) >= 0.7 * np.hypot(*d[r].T).sum()   # one direction, not to and fro
                if len(r) >= fps and steady and 0.03 <= np.hypot(*v) / W <= 0.6:
                    pans.append({"t": round((a + 1 + r[0]) / fps, 2), "duration_s": round(len(r) / fps, 2),
                                 "dir": ("left" if v[0] > 0 else "right") if abs(v[0]) >= abs(v[1]) else
                                 ("up" if v[1] > 0 else "down"),
                                 "distance_pct": round(100 * float(np.hypot(*v)) / W, 1)})
    mins = n / fps / 60
    return {"pan_per_min": round(len(pans) / mins, 1) if mins else 0.0,
            "shake_pct": round(100 * shaky / n), "pans": pans}


def zoom_ease(F, fps, z):
    """A push's scale frame by frame against its first frame, fitted to an ease (graphics.fit_ease).
    A punch is a cut: ease none."""
    if z["kind"] != "push" or z["duration_s"] <= 0:
        return {"ease": "none", "duration_s": 0.0}
    from graphics import fit_ease
    a = max(0, int(z["t"] * fps) - 3)
    b = min(len(F) - 1, int((z["t"] + z["duration_s"]) * fps) + 6)
    target = z["scale"]
    scales = np.linspace(1.0, max(target, 1 / target) * 1.05, 30)
    h, w = F[a].shape
    ref = Image.fromarray(F[a].astype(np.uint8))
    zoomed = []
    for sc in scales:
        cw, ch = w / sc, h / sc
        zoomed.append(np.asarray(ref.resize((w, h), Image.BILINEAR,
                                            box=((w - cw) / 2, (h - ch) / 2, (w + cw) / 2, (h + ch) / 2)), np.float32))
    prog = []
    for k in range(a, b + 1):
        errs = [block_median(zm, F[k]) for zm in zoomed]
        s_ = scales[int(np.argmin(errs))]
        prog.append((s_ - 1) / (max(target, 1 / target) - 1))
    fit = fit_ease(np.arange(len(prog)) / fps, np.array(prog), fps)
    return {"ease": fit["ease"], "duration_s": fit["duration_s"]} if fit else {"ease": None, "duration_s": z["duration_s"]}


def push(run, fps):
    total = float(np.prod([s for _, _, s in run]))
    return {"t": round(run[0][0] / fps, 3), "kind": "push", "scale": round(total, 2),
            "duration_s": round((run[-1][1] - run[0][0]) / fps, 2), "on_cut": False}


def sheets(path, out_dir, vid, w, h, dur, n=9, cols=3, tw=240):
    """ONE sheet per video: n frames spread over it, 3 x 3, time burned top-left.
    Only read in the fallback look pass (no Gemini key), by a small model."""
    th = round(tw * h / w / 2) * 2
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:  # pillow < 10.1
        font = ImageFont.load_default()
    rows = -(-n // cols)
    sheet = Image.new("RGB", (cols * tw, rows * th), "black")
    draw = ImageDraw.Draw(sheet)
    for j in range(n):
        t = dur * (j + 0.5) / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
                              "-frames:v", "1", "-vf", f"scale={tw}:{th}", "-f", "rawvideo",
                              "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        if len(raw) < tw * th * 3:
            continue
        x, y = (j % cols) * tw, (j // cols) * th
        sheet.paste(Image.fromarray(np.frombuffer(raw[:tw * th * 3], np.uint8).reshape(th, tw, 3)), (x, y))
        draw.rectangle([x, y, x + 56, y + 20], fill="black")
        draw.text((x + 4, y + 2), f"{t:.1f}s", fill="yellow", font=font)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{vid}-*.jpg"):  # the old 20-frame sheets
        old.unlink()
    p = out_dir / f"{vid}.jpg"
    sheet.save(p, quality=80)
    return [p]


def measure_video(path, sheet_dir):
    w, h, fps, dur = probe(path)
    sw, sh = (SMALL, round(SMALL * h / w / 2) * 2) if w <= h else (round(SMALL * w / h / 2) * 2, SMALL)
    F = gray_frames(path, sw, sh)
    cuts, zooms = analyse(F, fps)
    punch_at = {round(z["t"], 3) for z in zooms if z["kind"] == "punch" and z["on_cut"]}
    kinds = [cut_kind(F, round(c * fps), fps, round(c, 3) in punch_at) for c in cuts]
    for z in zooms:
        z.update({"ease": zoom_ease(F, fps, z)["ease"]} if z["kind"] == "push" else {"ease": "none"})
    cam = camera(F, fps, cuts, zooms)
    edges = [0.0] + cuts + [dur]
    shots = [round(b - a, 3) for a, b in zip(edges, edges[1:])]
    return {
        "id": path.stem, "duration_s": round(dur, 2), "fps": round(fps, 3),
        "width": w, "height": h,
        "cuts": cuts, "cut_kinds": kinds, "shots_s": shots, "camera": cam,
        "cuts_per_10s": round(len(cuts) / dur * 10, 2) if dur else 0,
        "median_shot_s": round(statistics.median(shots), 2),
        "zooms": zooms,
        "zooms_per_min": round(len(zooms) / dur * 60, 1) if dur else 0,
        "sheets": [str(p) for p in sheets(path, sheet_dir, path.stem, w, h, dur)],
    }


def speech(tdir, vid):
    """(wpm, pause_s, sentence starts) off a transcript, or None."""
    p = tdir / f"{vid}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    words = [x for x in d.get("words", []) if x.get("type") == "word"]
    dur = d.get("audio_duration_secs") or (words[-1]["end"] if words else 0)
    if len(words) < 2 or not dur:
        return None
    gaps = [b["start"] - a["end"] for a, b in zip(words, words[1:])]
    starts = [words[0]["start"]] + [b["start"] for a, b, g in zip(words, words[1:], gaps)
                                    if g >= 0.25 or a["text"].rstrip()[-1:] in ".?!"]
    real = sorted(g for g in gaps if g > 0.05)
    # The 90th percentile gap: the pause they leave between phrases, not a one-off.
    pause = real[int(0.9 * (len(real) - 1))] if real else 0.0
    return len(words) / dur * 60, pause, starts


def zoom_block(rows, tdir):
    zs = [(r, z) for r in rows for z in r["zooms"]]
    mins = sum(r["duration_s"] for r in rows) / 60
    if not zs:
        return {"per_min": 0.0, "kind": None, "scale": 1.0, "duration_s": 0.0, "on": None}
    kinds = [z["kind"] for _, z in zs]
    kind = max(set(kinds), key=kinds.count)
    mine = [(r, z) for r, z in zs if z["kind"] == kind]
    on_cut = sum(z["on_cut"] for _, z in mine) / len(mine)
    near = 0
    for r, z in mine:
        sp = speech(tdir, r["id"])
        if sp and any(abs(z["t"] - s) <= 0.3 for s in sp[2]):
            near += 1
    on = "every_cut" if on_cut >= 0.7 else "sentence_start" if near / len(mine) >= 0.5 else "emphasis"
    return {"per_min": round(len(zs) / mins, 1),
            "kind": kind,
            "scale": round(statistics.median(max(z["scale"], 1 / z["scale"]) for _, z in mine), 2),
            "duration_s": round(statistics.median(z["duration_s"] for _, z in mine), 2),
            "on": on}


def cmd_download(a):
    handle = slug(a.handle)
    outdir = OUT_ROOT / handle
    meta = json.loads((outdir / "videos.json").read_text(encoding="utf-8"))
    if a.ids:
        by_id = {v["id"]: v for v in meta["videos"]}
        todo = [by_id[i] for i in a.ids.split(",")]
    else:
        top, control = pick(meta["videos"], meta.get("median_views") or 0, a.top, a.control)
        todo = top + control
        print(count_line(top, control))
    yt = ytdlp()
    if not yt:
        sys.exit("yt-dlp not found. Run fetch.py doctor.")
    vdir = outdir / "video"
    vdir.mkdir(parents=True, exist_ok=True)
    failed = [vid for vid, ok in pmap(lambda v: fetch_one(yt, v, vdir), todo, threads=True) if not ok]
    print(f"{len(todo) - len(failed)} of {len(todo)} downloaded -> {vdir}")
    if failed:
        # Every later step measures what is on disk: a gap here is a smaller sample, so say it.
        print(f"failed: {','.join(failed)}  (retry: visual.py download {handle} --ids {','.join(failed)}, "
              f"or pick others with --ids)")
        sys.exit(1)


def fetch_one(yt, v, vdir, tries=2):
    """(id, ok). Two tries: YouTube's 403 on a media URL is often gone on the second request."""
    if (vdir / f"{v['id']}.mp4").exists():
        print(f"{v['id']} cached")
        return v["id"], True
    print(f"{v['id']} downloading")
    for k in range(tries):
        r = subprocess.run(yt + ["-f", "bv*+ba/b", "-S", "vcodec:h264,res:1080",
                                 "--merge-output-format", "mp4", "--no-warnings",
                                 "-o", str(vdir / "%(id)s.%(ext)s"), v["webpage_url"]],
                           capture_output=True, text=True)
        if r.returncode == 0 and (vdir / f"{v['id']}.mp4").exists():
            return v["id"], True
        print(f"  {v['id']} failed{' (retrying)' if k + 1 < tries else ''}: {r.stderr.strip()[-300:]}",
              file=sys.stderr)
    return v["id"], False


def measure_one(job):
    """One video's visual.json (worker process)."""
    p, sheets = job
    r = measure_video(p, sheets)
    p.with_suffix(".visual.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    print(f"{p.stem}: {len(r['cuts'])} cuts ({r['cuts_per_10s']}/10s), median shot "
          f"{r['median_shot_s']} s, {len(r['zooms'])} zooms, {len(r['sheets'])} sheets", file=sys.stderr)
    return r


def cmd_measure(a):
    handle = slug(a.handle)
    outdir = OUT_ROOT / handle
    vids = sorted((outdir / "video").glob("*.mp4"))
    if not vids:
        sys.exit(f"no videos in {outdir / 'video'}. Run `download {handle}` first.")
    tdir = outdir / "transcripts"
    print(f"measuring {len(vids)} videos", file=sys.stderr)
    rows = pmap(measure_one, [(p, outdir / "sheets") for p in vids])

    sp = [s for s in (speech(tdir, r["id"]) for r in rows) if s]
    first = rows[0]
    style_path = outdir / "style.json"
    style = json.loads(style_path.read_text(encoding="utf-8")) if style_path.exists() else {}
    style.update({
        "handle": handle,
        "videos": len(rows),
        "aspect": "9:16" if first["height"] > first["width"] else "16:9",
        "pace": {
            "wpm": round(statistics.median(s[0] for s in sp)) if sp else None,
            "max_pause_s": round(statistics.median(s[1] for s in sp), 2) if sp else None,
            "cuts_per_10s": round(statistics.median(r["cuts_per_10s"] for r in rows), 2),
            "median_shot_s": round(statistics.median(r["median_shot_s"] for r in rows), 2),
        },
        "zoom": zoom_block(rows, tdir),
        "camera": {
            "pan_per_min": round(statistics.median(r["camera"]["pan_per_min"] for r in rows), 1),
            "shake_pct": round(statistics.median(r["camera"]["shake_pct"] for r in rows)),
            "push_per_min": round(statistics.median(sum(z["kind"] == "push" for z in r["zooms"]) / r["duration_s"] * 60
                                                    for r in rows), 1),
        },
    })
    ck = Counter(k for r in rows for k in r.get("cut_kinds", []))
    style["pace"]["cut_kinds"] = {k: round(100 * v / sum(ck.values())) for k, v in ck.most_common()} if ck else {}
    tr = transitions_of(style["pace"]["cut_kinds"])
    if tr is None:
        style.pop("transitions", None)
    else:
        style["transitions"] = tr     # [] = they only cut: style-edit cuts its scenes hard
    eases = Counter(z.get("ease") for r in rows for z in r["zooms"] if z["kind"] == style["zoom"].get("kind"))
    style["zoom"]["ease"] = eases.most_common(1)[0][0] if eases else None
    style_path.write_text(json.dumps(style, indent=2), encoding="utf-8")
    if a.json:
        print(json.dumps({k: style[k] for k in ("pace", "zoom", "camera")}, indent=2))
    print(summary_line(style, style_path))
    if not sp:
        print("no transcripts yet: wpm and max_pause_s are empty. Transcribe, then rerun.",
              file=sys.stderr)


# A cut kind -> style-edit's scene transition (Scene.tsx). Hard, jump and zoom-punch cuts have none.
TRANSITION = {"whip": "push", "match": "match", "mask": "wipe", "dissolve": "fade"}


def transitions_of(cut_kinds):
    """style.json "transitions", the list style-edit cycles through its scene cards: the creator's
    own transition cuts (5% of cuts or more), most used first. Empty: they only cut. None: no cuts measured."""
    if not cut_kinds:
        return None
    return [TRANSITION[k] for k, v in sorted((cut_kinds or {}).items(), key=lambda kv: -kv[1])
            if k in TRANSITION and v >= 5]


def summary_line(style, path):
    """One line for Claude's context: the full blocks are in style.json, --json prints them."""
    p, z, c = style["pace"], style["zoom"], style["camera"]
    return (f"visual: {p['wpm']} wpm, {p['cuts_per_10s']} cuts/10s, shot {p['median_shot_s']} s, "
            f"zoom {z.get('kind')} {z.get('per_min')}/min, pans {c['pan_per_min']}/min -> {path} (\"pace\", \"zoom\", \"camera\")")


def demo():
    """A synthetic clip: picture A, hard cut to B at 2 s, punch in on B at 4 s,
    hard cut back to A at 6 s, then a slow push over 6-8 s. Every step must be
    found, and nothing else."""
    rng = np.random.default_rng(0)
    W, H, FPS = 360, 640, 30

    def texture():
        x = rng.random((H // 16, W // 16)) * 255
        return np.asarray(Image.fromarray(x.astype(np.uint8)).resize((W, H), Image.BICUBIC))

    def zoom(img, s):
        cw, ch = W / s, H / s
        box = ((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2)
        return np.asarray(Image.fromarray(img).resize((W, H), Image.BILINEAR, box=box))

    A, B = texture(), texture()
    frames = ([A] * 60 + [B] * 60 + [zoom(B, 1.25)] * 60
              + [zoom(A, 1 + 0.2 * k / 59) for k in range(60)] + [zoom(A, 1.2)] * 30)
    with tempfile.TemporaryDirectory() as d:
        mp4 = Path(d) / "demo.mp4"
        raw = b"".join(np.clip(f + rng.normal(0, 2, f.shape), 0, 255).astype(np.uint8).tobytes()
                       for f in frames)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
                        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-pix_fmt", "yuv420p",
                        "-c:v", "libx264", "-crf", "18", str(mp4)], input=raw, check=True)
        r = measure_video(mp4, Path(d) / "sheets")
        assert r["cuts"] == [2.0, 6.0], r["cuts"]
        punches = [z for z in r["zooms"] if z["kind"] == "punch"]
        pushes = [z for z in r["zooms"] if z["kind"] == "push"]
        assert len(punches) == 1 and abs(punches[0]["t"] - 4.0) < 0.05, r["zooms"]
        assert abs(punches[0]["scale"] - 1.25) <= 0.05 and not punches[0]["on_cut"], punches
        assert len(pushes) == 1 and 5.9 <= pushes[0]["t"] <= 6.6, r["zooms"]
        assert 1.1 <= pushes[0]["scale"] <= 1.3 and pushes[0]["duration_s"] >= 1.0, pushes
        assert len(r["sheets"]) == 1 and Path(r["sheets"][0]).exists()
        assert r["cut_kinds"] == ["hard", "hard"], r["cut_kinds"]
        assert [z["ease"] for z in r["zooms"]][:1] == ["none"], r["zooms"]

    # Cut kinds and camera moves, on frames built in memory.
    C, D = texture(), texture()

    def shift(img, dx, dy):
        return np.asarray(Image.fromarray(img).transform((W, H), Image.AFFINE, (1, 0, dx, 0, 1, dy),
                                                         Image.BILINEAR), np.float32)
    f = [A.astype(np.float32)] * 20
    body = A.astype(np.float32).copy()
    body[200:460, 100:260] = 255 - body[200:460, 100:260]          # the speaker moved: a jump cut
    f += [body] * 20 + [B.astype(np.float32)] * 20                  # 20: jump, 40: hard
    f += [(1 - a) * B + a * C for a in np.linspace(0, 1, 8)[1:-1]] + [C.astype(np.float32)] * 20   # 60: dissolve
    blur = np.asarray(Image.fromarray(C).resize((W // 60, H)).resize((W, H)), np.float32)
    f += [blur, np.asarray(Image.fromarray(D).resize((W // 60, H)).resize((W, H)), np.float32)]    # 86: whip
    f += [D.astype(np.float32)] * 20
    f += [shift(D, -1.5 * k, 0) for k in range(45)]                 # 108-153: a pan
    f += [shift(D, rng.normal(0, 3), rng.normal(0, 3)) for _ in range(40)]   # shake
    G = np.stack(f).astype(np.float32)
    small = np.stack([np.asarray(Image.fromarray(g.astype(np.uint8)).resize((108, 192)), np.float32) for g in G])
    got = {c: cut_kind(small, c, FPS, False) for c in (20, 40, 61, 87)}
    assert got == {20: "jump", 40: "hard", 61: "dissolve", 87: "whip"}, got
    assert cut_kind(small, 40, FPS, True) == "zoom-punch"
    cam = camera(small, FPS, [20 / FPS, 40 / FPS, 61 / FPS, 87 / FPS, 108 / FPS, 153 / FPS], [])
    assert len(cam["pans"]) == 1 and cam["pans"][0]["dir"] in ("left", "right"), cam
    assert cam["shake_pct"] >= 10, cam
    line = summary_line({"pace": {"wpm": 180, "cuts_per_10s": 2.1, "median_shot_s": 3.4},
                         "zoom": {"kind": "punch", "per_min": 6.0}, "camera": {"pan_per_min": 0.5}}, "style.json")
    assert "\n" not in line and "{" not in line and "punch 6.0/min" in line, line   # measure prints one line
    # style-edit's scene transitions, from the cut kinds the creator uses (a hard cut has none)
    assert transitions_of({"hard": 60, "whip": 25, "dissolve": 10, "mask": 3, "jump": 2}) == ["push", "fade"]
    assert transitions_of({"hard": 90, "match": 10}) == ["match"] and transitions_of({"hard": 100}) == []
    assert transitions_of({}) is None    # no cuts measured: no "transitions", style-edit's default, not hard cuts
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("download")
    p.add_argument("handle")
    p.add_argument("--top", type=int, default=8, help="most-viewed videos; --control more are added (default 2)")
    p.add_argument("--control", type=int, default=2)
    p.add_argument("--ids", default=None)
    p.set_defaults(fn=cmd_download)
    p = sub.add_parser("measure")
    p.add_argument("handle")
    p.add_argument("--json", action="store_true", help="print pace, zoom and camera in full")
    p.set_defaults(fn=cmd_measure)
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
