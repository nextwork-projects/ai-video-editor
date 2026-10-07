#!/usr/bin/env python3
"""Smoothness meter: how a film's camera moves, frame by frame, measured from its pixels.

    python3 meter.py VIDEO [VIDEO ...] [--json out.json] [--from S --to S]
    python3 meter.py demo

Optical flow (OpenCV Farneback) between every pair of frames at 480 px wide, fitted to one camera
move per frame: pan x, pan y (share of the frame width a second) and zoom (log scale a second).
From that:
  speed     the camera's speed each frame (% of the width a second; zoom counted the same way)
  jerk      the change of acceleration (second difference of the velocity), %/s^3; a spike is a snap
  judder    a frame that repeats the last one while the frames around it move (a stutter)
  stops     the camera going from moving to dead still in under 0.15 s
  cuts      frames that change wholesale; carry = does the motion before a cut continue after it
            (cosine of the two velocities times the ratio of their speeds; 1 = carried through)
Every number is also given per 1 s window (the worst window is where to look).
"""
import json
import math
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
import subprocess
import sys

W = 480


def frames(video, t0=None, t1=None):
    import numpy as np
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                          "-of", "json", video], capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    fps = float(num) / float(den)
    h = int(round(s["height"] * W / s["width"] / 2)) * 2
    cut = (["-ss", str(t0)] if t0 else []) + (["-to", str(t1 - (t0 or 0))] if t1 else [])
    raw = subprocess.run(["ffmpeg", "-v", "error", *cut[:2], "-i", video, *cut[2:], "-vf", f"scale={W}:{h}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, W), fps


def camera(a, b):
    """One camera move from a to b: (pan x, pan y) in frame widths and zoom (log scale), plus the share of
    the frame that changed wholesale (a cut)."""
    import cv2
    import numpy as np
    diff = float(np.abs(a.astype(np.int16) - b.astype(np.int16)).mean())
    flow = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 4, 21, 3, 5, 1.1, 0)
    h, w = a.shape
    gy, gx = np.gradient(a.astype(np.float32))
    g = np.hypot(gx, gy)
    tex = g > max(4.0, float(np.percentile(g, 75)))   # only where there is detail to track
    ys, xs = np.nonzero(tex[::4, ::4])
    ys, xs = ys * 4, xs * 4
    if len(xs) < 40:
        return 0.0, 0.0, 0.0, diff, 0.0
    u, v = flow[ys, xs, 0], flow[ys, xs, 1]
    cx, cy = w / 2, h / 2
    # u = tx + k (x - cx), v = ty + k (y - cy): least squares
    A = np.zeros((2 * len(xs), 3))
    A[:len(xs), 0] = 1
    A[len(xs):, 1] = 1
    A[:len(xs), 2] = xs - cx
    A[len(xs):, 2] = ys - cy
    rhs = np.concatenate([u, v])
    (tx, ty, k), *_ = np.linalg.lstsq(A, rhs, rcond=None)
    resid = float(np.sqrt(np.mean((A @ np.array([tx, ty, k]) - rhs) ** 2)))
    return -tx / w, -ty / w, math.log1p(k), diff, resid


def measure(video, t0=None, t1=None):
    import numpy as np
    fr, fps = frames(video, t0, t1)
    rows = [camera(fr[i], fr[i + 1]) for i in range(len(fr) - 1)]
    tx, ty, zm, diff, res = (np.array(c) for c in zip(*rows)) if rows else [np.zeros(0)] * 5
    # a cut: most of the frame changes and no single camera move explains it
    cut = (diff > 18) & (res > 1.5)
    # velocity per second, as % of the frame width (zoom: % scale change)
    vel = np.stack([tx, ty, zm], 1) * fps * 100
    vel[cut] = np.nan
    speed = np.sqrt(np.nansum(vel ** 2, 1))
    speed[cut] = np.nan
    # judder: a frame identical to the last while both neighbours move
    moving = diff > 0.6
    judder = [i for i in range(1, len(diff) - 1) if diff[i] < 0.15 and moving[i - 1] and moving[i + 1] and not cut[i - 1] and not cut[i + 1]]
    # jerk on the velocity smoothed over 0.05 s (flow noise differentiated twice would swamp it, more so at
    # 60 fps), and never across a cut
    sig = max(1.0, 0.05 * fps)
    k = np.exp(-0.5 * (np.arange(-3 * int(sig), 3 * int(sig) + 1) / sig) ** 2)
    k /= k.sum()
    filled = np.where(np.isnan(vel), 0, vel)
    sm = np.stack([np.convolve(filled[:, c], k, mode="same") for c in range(3)], 1)
    near_cut = np.convolve(cut.astype(float), np.ones(2 * len(k) + 1), mode="same") > 0
    acc = np.diff(sm, axis=0) * fps
    jerk = np.linalg.norm(np.diff(acc, axis=0) * fps, axis=1)
    jerk[near_cut[1:-1]] = np.nan
    j = jerk[~np.isnan(jerk)]
    # dead stops: moving (>2 %/s) to still (<0.2 %/s) within 0.15 s
    win = max(1, int(round(0.15 * fps)))
    stops = [i for i in range(len(speed) - win) if speed[i] > 2 and np.nanmax(speed[i + 1:i + win + 1]) < 0.2]
    # carry across each cut: the camera's velocity over 4 frames each side
    carry = []
    for i in np.nonzero(cut)[0]:
        a, b = vel[max(0, i - 4):i], vel[i + 1:i + 5]
        a, b = np.nanmean(a, 0) if len(a) else None, np.nanmean(b, 0) if len(b) else None
        if a is None or b is None or np.isnan(a).any() or np.isnan(b).any():
            continue
        sa, sb = np.linalg.norm(a), np.linalg.norm(b)
        if max(sa, sb) < 0.5:
            carry.append(None)        # still into still: nothing to carry
            continue
        cos = float(a @ b / (sa * sb)) if sa > 0 and sb > 0 else 0.0
        carry.append(max(0.0, cos) * min(sa, sb) / max(sa, sb))
    moving_cuts = [c for c in carry if c is not None]
    # 1 s windows
    n = int(fps)
    wins = []
    for s in range(0, len(speed) - n + 1, n):
        sp, jk = speed[s:s + n], jerk[s:s + n - 2] if s + n - 2 <= len(jerk) else jerk[s:]
        wins.append({"t": round(s / fps, 1), "speed": round(float(np.nanmean(sp)), 2) if np.isfinite(sp).any() else 0,
                     "jerk_max": round(float(np.nanmax(jk)), 0) if len(jk) and np.isfinite(jk).any() else 0,
                     "judder": sum(1 for x in judder if s <= x < s + n)})
    worst = max(wins, key=lambda w: w["jerk_max"]) if wins else None
    dur = len(fr) / fps
    return {"video": video, "fps": round(fps, 2), "seconds": round(dur, 1),
            "speed_median": round(float(np.nanmedian(speed)), 2) if len(speed) else 0,
            "still_share": round(float(np.nanmean(speed < 0.3)), 2) if len(speed) else 0,
            "jerk_p50": round(float(np.percentile(j, 50)), 0) if len(j) else 0,
            "jerk_p95": round(float(np.percentile(j, 95)), 0) if len(j) else 0,
            "judder_per_10s": round(len(judder) / dur * 10, 2),
            "stops_per_10s": round(len(stops) / dur * 10, 2),
            "cuts_per_10s": round(float(cut.sum()) / dur * 10, 2),
            "carry_moving_cuts": round(float(np.mean(moving_cuts)), 2) if moving_cuts else None,
            "moving_cuts": len(moving_cuts), "still_cuts": carry.count(None),
            "worst_window": worst, "judder_at": [round(x / fps, 2) for x in judder][:40], "windows": wins}


SHOW = ["fps", "seconds", "speed_median", "still_share", "jerk_p50", "jerk_p95", "judder_per_10s", "stops_per_10s",
        "cuts_per_10s", "carry_moving_cuts"]


def demo():
    """A synthetic pan: smooth is smooth, a held frame is judder, a snap is a jerk spike."""
    import numpy as np
    import tempfile
    import os
    rng = np.random.default_rng(1)
    tex = (rng.random((400, 1400)) * 255).astype(np.uint8)
    import cv2
    tex = cv2.GaussianBlur(tex, (0, 0), 2)
    with tempfile.TemporaryDirectory() as d:
        def write(name, xs):
            p = os.path.join(d, name)
            pr = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", "480x270", "-r", "30", "-i", "-",
                                   "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "12", p], stdin=subprocess.PIPE)
            for x in xs:   # sub-pixel shifts, so the source itself never repeats a frame
                M = np.float32([[1, 0, -x], [0, 1, -60]])
                pr.stdin.write(np.ascontiguousarray(cv2.warpAffine(tex, M, (480, 270), flags=cv2.INTER_CUBIC)).tobytes())
            pr.stdin.close()
            pr.wait()
            return p
        smooth = [300 * (1 - math.cos(math.pi * (i + 6) / 71)) / 2 for i in range(60)]   # mid-move: never at rest
        held = list(smooth)
        held[30] = held[29]
        a, b = measure(write("a.mp4", smooth)), measure(write("b.mp4", held))
        assert a["judder_per_10s"] == 0 and b["judder_per_10s"] > 0, (a["judder_per_10s"], b["judder_per_10s"])
        assert b["jerk_p95"] > a["jerk_p95"], (a["jerk_p95"], b["jerk_p95"])
    print("demo ok")


def main():
    args = sys.argv[1:]
    if args == ["demo"]:
        return demo()
    out = None
    t0 = t1 = None
    if "--json" in args:
        i = args.index("--json")
        out = args[i + 1]
        del args[i:i + 2]
    for k in ("--from", "--to"):
        if k in args:
            i = args.index(k)
            v = float(args[i + 1])
            del args[i:i + 2]
            t0, t1 = (v, t1) if k == "--from" else (t0, v)
    res = [measure(v, t0, t1) for v in args]
    print(f"{'film':40} " + " ".join(f"{k:>10}" for k in SHOW))
    for r in res:
        print(f"{r['video'][-40:]:40} " + " ".join(f"{str(r[k]):>10}" for k in SHOW))
        if r["worst_window"]:
            print(f"{'':40} worst 1 s window at {r['worst_window']['t']} s: jerk {r['worst_window']['jerk_max']}, judder {r['worst_window']['judder']}")
    if out:
        with open(out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
