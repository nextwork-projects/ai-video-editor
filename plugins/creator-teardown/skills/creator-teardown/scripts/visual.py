#!/usr/bin/env python3
"""The visual pass: measure how a creator edits, from their real videos.

  download <handle>   yt-dlp the picked videos to creator-teardowns/<handle>/video/.
                      Same pick as fetch.py transcribe: --top most-viewed plus
                      --control closest to the median, or --ids.
  measure <handle>    per video: cut times, shot lengths, zoom events and contact
                      sheets. Writes video/<id>.visual.json and sheets/<id>-NN.jpg,
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
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, pick, slug, ytdlp  # noqa: E402

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


def push(run, fps):
    total = float(np.prod([s for _, _, s in run]))
    return {"t": round(run[0][0] / fps, 3), "kind": "push", "scale": round(total, 2),
            "duration_s": round((run[-1][1] - run[0][0]) / fps, 2), "on_cut": False}


def sheets(path, out_dir, vid, w, h, per=20, cols=5):
    """Frames at 2 fps, 20 to a sheet (10 s), timestamp burned top-left."""
    tw = 240
    th = round(tw * h / w / 2) * 2
    F = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf",
                        f"fps=2,scale={tw}:{th}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, check=True).stdout
    n = len(F) // (tw * th * 3)
    frames = np.frombuffer(F, np.uint8)[:n * tw * th * 3].reshape(n, th, tw, 3)
    try:
        font = ImageFont.load_default(size=18)
    except TypeError:  # pillow < 10.1
        font = ImageFont.load_default()
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k in range(0, n, per):
        chunk = frames[k:k + per]
        rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cols * tw, rows * th), "black")
        draw = ImageDraw.Draw(sheet)
        for j, f in enumerate(chunk):
            x, y = (j % cols) * tw, (j // cols) * th
            sheet.paste(Image.fromarray(f), (x, y))
            label = f"{(k + j) / 2:.1f}s"
            draw.rectangle([x, y, x + 62, y + 24], fill="black")
            draw.text((x + 4, y + 2), label, fill="yellow", font=font)
        p = out_dir / f"{vid}-{k // per + 1:02}.jpg"
        sheet.save(p, quality=85)
        paths.append(p)
    return paths


def measure_video(path, sheet_dir):
    w, h, fps, dur = probe(path)
    sw, sh = (SMALL, round(SMALL * h / w / 2) * 2) if w <= h else (round(SMALL * w / h / 2) * 2, SMALL)
    F = gray_frames(path, sw, sh)
    cuts, zooms = analyse(F, fps)
    edges = [0.0] + cuts + [dur]
    shots = [round(b - a, 3) for a, b in zip(edges, edges[1:])]
    return {
        "id": path.stem, "duration_s": round(dur, 2), "fps": round(fps, 3),
        "width": w, "height": h,
        "cuts": cuts, "shots_s": shots,
        "cuts_per_10s": round(len(cuts) / dur * 10, 2) if dur else 0,
        "median_shot_s": round(statistics.median(shots), 2),
        "zooms": zooms,
        "zooms_per_min": round(len(zooms) / dur * 60, 1) if dur else 0,
        "sheets": [str(p) for p in sheets(path, sheet_dir, path.stem, w, h)],
    }


def speech(tdir, vid):
    """(wpm, pause_s, sentence starts) off a transcript, or None."""
    p = tdir / f"{vid}.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
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
    meta = json.loads((outdir / "videos.json").read_text())
    if a.ids:
        by_id = {v["id"]: v for v in meta["videos"]}
        todo = [by_id[i] for i in a.ids.split(",")]
    else:
        top, control = pick(meta["videos"], meta.get("median_views") or 0, a.top, a.control)
        todo = top + control
    yt = ytdlp()
    if not yt:
        sys.exit("yt-dlp not found. Run fetch.py doctor.")
    vdir = outdir / "video"
    vdir.mkdir(parents=True, exist_ok=True)
    for v in todo:
        if (vdir / f"{v['id']}.mp4").exists():
            print(f"{v['id']} cached")
            continue
        print(f"{v['id']} downloading")
        r = subprocess.run(yt + ["-f", "bv*+ba/b", "-S", "vcodec:h264,res:1080",
                                 "--merge-output-format", "mp4", "--no-warnings",
                                 "-o", str(vdir / "%(id)s.%(ext)s"), v["webpage_url"]],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  failed: {r.stderr.strip()[-300:]}", file=sys.stderr)
    print(f"-> {vdir}")


def cmd_measure(a):
    handle = slug(a.handle)
    outdir = OUT_ROOT / handle
    vids = sorted((outdir / "video").glob("*.mp4"))
    if not vids:
        sys.exit(f"no videos in {outdir / 'video'}. Run `download {handle}` first.")
    tdir = outdir / "transcripts"
    rows = []
    for p in vids:
        print(f"{p.stem} measuring", file=sys.stderr)
        r = measure_video(p, outdir / "sheets")
        p.with_suffix(".visual.json").write_text(json.dumps(r, indent=2))
        rows.append(r)
        print(f"  {len(r['cuts'])} cuts ({r['cuts_per_10s']}/10s), median shot "
              f"{r['median_shot_s']} s, {len(r['zooms'])} zooms, {len(r['sheets'])} sheets")

    sp = [s for s in (speech(tdir, r["id"]) for r in rows) if s]
    first = rows[0]
    style_path = outdir / "style.json"
    style = json.loads(style_path.read_text()) if style_path.exists() else {}
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
    })
    style_path.write_text(json.dumps(style, indent=2))
    print(json.dumps({k: style[k] for k in ("pace", "zoom")}, indent=2))
    if not sp:
        print("no transcripts yet: wpm and max_pause_s are empty. Transcribe, then rerun.",
              file=sys.stderr)
    print(f"-> {style_path}\n-> {outdir / 'sheets'}")


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
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("download")
    p.add_argument("handle")
    p.add_argument("--top", type=int, default=8)
    p.add_argument("--control", type=int, default=2)
    p.add_argument("--ids", default=None)
    p.set_defaults(fn=cmd_download)
    p = sub.add_parser("measure")
    p.add_argument("handle")
    p.set_defaults(fn=cmd_measure)
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
