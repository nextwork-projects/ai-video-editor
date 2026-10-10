#!/usr/bin/env python3
"""The speaker cut out of cut.mp4, so cards with "layer": "behind" sit behind the head and shoulders.

    ~/.ai-video-editor/venv/bin/python matte.py edits/NAME [--plan plan.json] [--modal] [--estimate]
    ~/.ai-video-editor/venv/bin/python matte.py fetch      download the model (setup.py matte calls it)
    ~/.ai-video-editor/venv/bin/python matte.py demo       self-check, no video needed

Only the time ranges where a behind card is up (plus HANDLE_S each side) are cut, as RGBA PNG frames
named by their frame of the cut (000105.png is frame 105) in one folder per cut and output size,
edits/NAME/cutout/WxH-KEY/ (KEY: cut.mp4's size and time, so a new cut never reuses an old matte).
Their ranges go into the plan as "cutouts"; the renderer draws the cutout over the cards only while
one is up and the raw camera everywhere else. A frame already cut is never cut again: a re-plan that
moves a card cuts only the frames it adds, and plan.py writes "cutouts" itself whenever every frame
a range needs is already there. --estimate prints the frames to cut and the time, then stops.

Per frame:
  1. Robust Video Matting (mobilenetv3, onnxruntime): a recurrent person matte that keeps hair, hands
     and motion blur. Each range starts WARM_S early so the recurrent state has settled on its first
     frame.
  2. Stabilise: alpha is the median of frames t-2..t+2 wherever the camera pixel is still, so edges
     stop flickering; where the speaker moves the frame's own alpha is kept, so motion never lags.
  3. Edge refine: soft edge pixels are part wall. The wall behind them is estimated from the nearby
     background and subtracted (unmix, F = (C - (1-a)B) / a), and the colour of the nearest solid
     foreground fills in where that is unreliable, so strands stay hair-coloured over any card.
     Alpha is firmed on dark hair (no grey fringe) and kept soft on skin (blurred hands stay solid).

Why PNG frames and not ProRes 4444: through Remotion's transparent OffthreadVideo, ProRes 4444 came
back about 3 levels darker in the shadows than the same pixels in the h264 footage (measured with
BT.601 and BT.709, limited and full range), so the speaker visibly changed when the cutout switched
on. A .mov of PNG frames matched the footage exactly but lost its alpha in the compositor, and VP9
alpha seeks poorly. Plain PNGs drawn with <Img> keep alpha, match the footage exactly and need no
seeking; about 0.5 MB a frame.

Model choice (the sample take, 1080x1920, three frames, hair at 2x crop): RVM mobilenetv3 and RVM resnet50
cut the hair alike; BiRefNet-general-lite (MIT) was 20-50x slower on CPU, per frame (no temporal
state, so it flickers) and let the wall's slats through at low alpha. RVM mobilenetv3 is 15 MB
against resnet50's 107 MB. RVM: github.com/PeterL1n/RobustVideoMatting (GPL-3.0); the weights are
downloaded from its release on first use, never shipped with this plugin.

Exit codes: 0 done (read any WARNING it prints), 1 error, 2 usage.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
MODEL = HOME / "models" / "rvm_mobilenetv3_fp32.onnx"
HANDLE_S = 0.5      # cut this much before and after each behind card
WARM_S = 1.0        # RVM runs this long before a range so its recurrent state has settled
RATIO = 0.25        # RVM downsample_ratio: 1920 tall -> 480, its sweet spot for a person in frame
STILL = 6.0         # mean |RGB diff| (0-255) under which a pixel counts as still (stabilise)
RADIUS = 2          # stabilise over t-RADIUS..t+RADIUS
LO, HI, SOFT_LO = 0.25, 0.9, 0.04   # alpha firming: hair cut off at LO, skin keeps down to SOFT_LO
FLAT_LO, FLAT_HI = 18.0, 40.0       # wall plate RMS error (0-255 per pixel): unmix trusted under LO, not over HI
# Modal (modal.com/pricing, 2026-10): per physical core and per GiB of memory, per second.
MODAL_CPU, MODAL_MEM_GB = 8, 8
MODAL_CPU_USD_S, MODAL_MEM_USD_S = 0.0000131, 0.00000222
LAPTOP_S = 0.26     # s a frame on the test laptop (the sample take, 1080x1920, 2026-10-07)


def model(check=False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import models   # pinned URL + sha256
    return str(models.fetch(MODEL.name, check))


def pool(edit, plan):
    """The cutout folder (relative to edit) for this cut at this output size: frames are keyed by it
    and their frame number, so any plan of the same cut reuses them."""
    import hashlib
    st = (Path(edit) / plan["video"]).stat()
    rate = "" if float(plan.get("fps", 30)).is_integer() else f"-{plan['fps']}"   # frame n means another time at 29.97
    key = hashlib.sha1(f"{st.st_size}-{st.st_mtime_ns}{rate}".encode()).hexdigest()[:8]
    return f"cutout/{plan['width']}x{plan['height']}-{key}"


def missing(plan, edit):
    """(cutouts, runs): the plan's behind ranges as cutouts, and the [a, b] runs of frames not cut yet."""
    rel = pool(edit, plan)
    runs = []
    cutouts = [{"src": rel, "from": a, "to": b} for a, b in behind_ranges(plan)]
    for c in cutouts:
        for f in range(c["from"], c["to"] + 1):
            if (Path(edit) / rel / f"{f:06d}.png").exists():
                continue
            if runs and runs[-1][1] == f - 1:
                runs[-1][1] = f
            else:
                runs.append([f, f])
    return cutouts, runs


def kept(plan, edit):
    """plan.py: the cutouts every one of whose frames is already cut (a re-plan keeps them)."""
    if not (Path(edit) / plan["video"]).exists():
        return []
    cutouts, runs = missing(plan, edit)
    return [c for c in cutouts if not any(a <= c["to"] and b >= c["from"] for a, b in runs)]


def behind_ranges(plan):
    """Inclusive frame ranges [a, b] that need the cutout: every behind card plus HANDLE_S, merged."""
    fps, last = plan["fps"], plan["durationInFrames"] - 1
    spans = sorted((max(0, round((c["start"] - HANDLE_S) * fps)), min(last, round((c["end"] + HANDLE_S) * fps)))
                   for c in plan["cards"] if c.get("layer") == "behind")
    out = []
    for a, b in spans:
        if out and a <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


# ---------- the per-frame work (numpy + OpenCV; also runs inside a Modal container) ----------
def _fill(img, mask, cv2, np):
    """Each masked-out pixel takes the colour of the masked pixels near it: normalised blur at
    widening radii, at quarter size (the result is smooth, so this costs nothing in detail)."""
    h, w = mask.shape
    s_img = cv2.resize(img * mask[..., None], (w // 4, h // 4), interpolation=cv2.INTER_AREA).reshape(h // 4, w // 4, -1)
    s_m = cv2.resize(mask, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    out = np.zeros_like(s_img)
    done = np.zeros(s_m.shape, bool)
    for k in (2, 6, 15):
        num, den = cv2.GaussianBlur(s_img, (0, 0), k).reshape(s_img.shape), cv2.GaussianBlur(s_m, (0, 0), k)
        sel = (den > 1e-3) & ~done
        out[sel] = num[sel] / den[sel][:, None]
        done |= sel
    return cv2.resize(out, (w, h), interpolation=cv2.INTER_LINEAR).reshape(h, w, -1)


def refine(cam, al, cv2, np):
    """cam (H,W,3) uint8, al (H,W) float 0..1 -> (rgb float, alpha float): unmixed edge colour, firm alpha."""
    c = cam.astype(np.float32)
    k3, k5 = np.ones((3, 3), np.uint8), np.ones((5, 5), np.uint8)
    solid = cv2.erode((al >= 0.95).astype(np.float32), k5)
    ext = _fill(c, solid, cv2, np)                         # the nearest solid foreground colour
    bg = cv2.erode((al < 0.02).astype(np.float32), k5)
    B = _fill(c, bg, cv2, np)                              # the wall behind each edge pixel
    # How well that plate predicts the wall near here: a flat wall a few levels, slats or plants tens.
    # The unmix is only trusted on a flat wall; on a textured one the solid colour fills in.
    sd = np.sqrt(np.maximum(_fill(((c - B) ** 2).sum(2, keepdims=True), bg, cv2, np)[..., 0], 0))
    flat = 1 - np.clip((sd - FLAT_LO) / (FLAT_HI - FLAT_LO), 0, 1)
    A = np.maximum(al, 0.15)[..., None]
    F = np.clip((c - (1 - A) * B) / A, 0, 255)
    wt = (np.clip((al - 0.15) / 0.35, 0, 1) * flat)[..., None]   # trust the unmix once alpha means something
    keep = np.clip((al - 0.9) / 0.1, 0, 1)[..., None]      # the camera's own colour where solid
    rgb = c * keep + (F * wt + ext * (1 - wt)) * (1 - keep)
    ae = cv2.erode(al, k3)
    hard = np.clip((ae - LO) / (HI - LO), 0, 1)
    hard = hard * hard * (3 - 2 * hard)
    soft = np.clip((ae - SOFT_LO) / (HI - SOFT_LO), 0, 1)
    skin = np.clip((ext @ np.array([0.299, 0.587, 0.114], np.float32) - 60) / 50, 0, 1)   # 0 dark hair, 1 skin
    return rgb, hard * (1 - skin) + np.maximum(hard, soft) * skin


def stabilise(cams, alphas, i, cv2, np):
    """alpha of frame i: the median over the window where every frame agrees the pixel is still.
    Only edge pixels (soft in some frame of the window) can differ, so only they are computed."""
    st = np.stack(alphas)
    edge = ((st > 0.01) & (st < 0.99)).any(0)
    edge = cv2.dilate(edge.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    ys, xs = np.nonzero(edge)
    c0 = cams[i][ys, xs].astype(np.int16)
    still = np.ones(len(ys), bool)
    for j, c in enumerate(cams):
        if j != i:
            still &= np.abs(c[ys, xs].astype(np.int16) - c0).mean(1) < STILL
    # stay clear of moving edges: a pixel next to a moving one keeps its own alpha too
    moving = np.zeros(edge.shape, np.uint8)
    moving[ys[~still], xs[~still]] = 1
    still &= ~cv2.dilate(moving, np.ones((5, 5), np.uint8)).astype(bool)[ys, xs]
    out = alphas[i].copy()
    out[ys, xs] = np.where(still, np.median(st[:, ys, xs], 0), out[ys, xs])
    return out


def cut_range(video, fps, w, h, vf, a, b, out, model_path, providers=("CPUExecutionProvider",)):
    """Frames a..b (inclusive) of video (already w x h; vf an ffmpeg filter, "null" for none), RGBA at
    out/<frame>.png.
    Returns timings in seconds: decode+matte, refine, total."""
    import cv2
    import numpy as np
    import onnxruntime as ort
    warm = min(a, round(WARM_S * fps))
    n = b - a + 1 + warm
    # Decoded the way the renderer decodes the footage (ffmpeg's default conversion of the same
    # file), and stored as RGBA PNGs, so the cutout's pixels ARE the footage's.
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{(a - warm) / fps:.6f}", "-i", str(video), "-frames:v", str(n),
                            "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sess = ort.InferenceSession(model_path, providers=list(providers))
    rec = [np.zeros([1, 1, 1, 1], np.float32)] * 4
    ratio = np.array([RATIO], np.float32)
    win_c, win_a = [], []
    t0, t_ref, got, wrote = time.time(), 0.0, 0, 0

    def emit(i):
        nonlocal t_ref, wrote
        t1 = time.time()
        al = stabilise(win_c, win_a, i, cv2, np)
        rgb, al = refine(win_c[i], al, cv2, np)
        t_ref += time.time() - t1
        rgba = np.concatenate([np.clip(rgb, 0, 255), al[..., None] * 255], 2).round().astype(np.uint8)
        rgba[rgba[..., 3] == 0] = 0     # nothing behind a clear pixel: smaller files
        tmp = out / f"{a + wrote:06d}.tmp.png"     # named by its frame of the cut; whole or not there
        cv2.imwrite(str(tmp), cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA), [cv2.IMWRITE_PNG_COMPRESSION, 3])
        os.replace(tmp, out / f"{a + wrote:06d}.png")
        wrote += 1

    size = w * h * 3
    while True:
        buf = dec.stdout.read(size)
        if len(buf) < size:
            break
        cam = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        _, pha, *rec = sess.run(None, {"src": (cam.astype(np.float32) / 255).transpose(2, 0, 1)[None], "r1i": rec[0],
                                       "r2i": rec[1], "r3i": rec[2], "r4i": rec[3], "downsample_ratio": ratio})
        got += 1
        if got <= warm - RADIUS:
            continue        # warm-up only: the recurrent state settles, nothing is written
        win_c.append(cam)
        win_a.append(pha[0, 0])
        if got == warm + 1:   # the first written frame: pad the window's head with it
            while len(win_c) < RADIUS + 1:
                win_c.insert(0, cam)
                win_a.insert(0, pha[0, 0])
        if len(win_c) == 2 * RADIUS + 1:
            emit(RADIUS)
            win_c.pop(0)
            win_a.pop(0)
    while win_c and wrote < b - a + 1:      # the tail: pad with the last frame
        win_c.append(win_c[-1])
        win_a.append(win_a[-1])
        emit(RADIUS)
        win_c.pop(0)
        win_a.pop(0)
    dec.wait()
    if wrote != b - a + 1:
        raise RuntimeError(f"frames {a}-{b}: wrote {wrote} of {b - a + 1}")
    total = time.time() - t0
    return {"frames": wrote, "matte_s": round(total - t_ref, 1), "refine_s": round(t_ref, 1), "wall_s": round(total, 1)}


# ---------- checks on the finished cutout ----------
def read_alpha(path, frame, w, h):
    import cv2
    return cv2.imread(str(Path(path) / f"{frame:06d}.png"), cv2.IMREAD_UNCHANGED)[..., 3] / 255.0


def move_hint(c):
    """The field that moves or shrinks a behind card: its beat's "box" (images.json for the user's picture)."""
    word = c.get("trigger_word") or f"{c['start']:.1f} s"
    where = "images.json" if str(c.get("src") or "").startswith("images/") and not c.get("format") else "visuals.json"
    return (f"move or shrink it: give the '{word}' beat a smaller \"box\": [x, y, w, h] (% of the frame) in {where}, "
            "beside the head or higher, or plan with --behind off")


def verify(plan, edit, w, h):
    """Per behind card: how much of its key region (plan.py's "key") the person covers, and that the
    face is solid (a hole in the matte would let the card show through the face)."""
    face = json.loads((edit / "face.json").read_text()) if (edit / "face.json").exists() else None
    bad = 0
    for c in plan["cards"]:
        if c.get("layer") != "behind":
            continue
        t = (c["start"] + c["end"]) / 2
        f = round(t * plan["fps"])
        cut = next((x for x in plan["cutouts"] if x["from"] <= f <= x["to"]), None)
        al = read_alpha(edit / cut["src"], f, w, h)
        msg = []
        if c.get("key"):
            x, y, kw, kh = c["key"]
            reg = al[round(y / 100 * h):round((y + kh) / 100 * h), round(x / 100 * w):round((x + kw) / 100 * w)]
            cov = float((reg > 0.5).mean()) if reg.size else 0.0
            msg.append(f"key region {100 * cov:.0f}% behind the speaker")
            if cov > 0.05:
                bad += 1
                msg[-1] += f" (WARNING: over 5%; {move_hint(c)})"
        hd = face and min(face["heads"], key=lambda x: abs(x["t"] - t))["box"]
        if hd:   # the face itself: the middle of the head box
            x, y, hw, hh = hd
            reg = al[round((y + hh * 0.35) / 100 * h):round((y + hh * 0.8) / 100 * h), round((x + hw * 0.25) / 100 * w):round((x + hw * 0.75) / 100 * w)]
            solid = float((reg > 0.98).mean())
            msg.append(f"face {100 * solid:.0f}% solid")
            if solid < 0.97:
                bad += 1
                msg[-1] += f" (WARNING: the card would show through the face; {move_hint(c)})"
        print(f"  {c.get('trigger_word') or c['start']}: " + ", ".join(msg))
    return bad


# ---------- Modal ----------
def matte_image(modal, model_path, req=HOME / "modal-matte.lock"):
    """The container: numpy, opencv and onnxruntime at requirements.lock's pins, hash-checked, the
    lock's lines for them and what they pull in (lib/ai_editor/lock.py)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import lock
    req.parent.mkdir(parents=True, exist_ok=True)
    text = lock.subset(lock.MATTE_ROOTS)
    if not req.exists() or req.read_text(encoding="utf-8") != text:   # unchanged file: Modal reuses the image
        req.write_text(text, encoding="utf-8")
    return (modal.Image.debian_slim(python_version="3.12").apt_install("ffmpeg")
            .pip_install_from_requirements(str(req), extra_options="--no-deps --require-hashes")
            .add_local_file(model_path, "/m/rvm.onnx", copy=True)
            .add_local_file(str(Path(__file__).resolve()), "/m/matte.py"))


def run_modal(video, jobs, model_path):
    """Each range on its own Modal container (CPU: RVM mobilenet is small, and the refine and the
    PNG encode are CPU work that a GPU would not speed up). The cut goes up once."""
    import modal
    image = matte_image(modal, model_path)
    vol = modal.Volume.from_name("ai-video-editor-renders", create_if_missing=True)
    app = modal.App("ai-video-editor-matte")
    job = f"matte-{os.getpid()}-{int(time.time())}"

    @app.function(image=image, volumes={"/vol": vol}, cpu=MODAL_CPU, memory=MODAL_MEM_GB * 1024, timeout=3600, serialized=True)
    def one(job, name, args):
        import sys as s
        s.path.insert(0, "/m")
        import matte
        out = f"/vol/{job}/{args['a']}-{args['b']}"
        r = matte.cut_range(f"/vol/{job}/{name}", args["fps"], args["w"], args["h"], args["vf"], args["a"], args["b"], out, "/m/rvm.onnx")
        import shutil
        shutil.make_archive(out, "tar", out)     # one file down instead of hundreds
        shutil.rmtree(out)
        vol.commit()
        return r

    t0 = time.time()
    with modal.enable_output(), app.run():
        with vol.batch_upload(force=True) as up:
            up.put_file(str(video), f"/{job}/{Path(video).name}")
        try:
            res = list(one.starmap([(job, Path(video).name, j) for j in jobs]))
            import shutil
            for j in jobs:
                tar = f"{j['out']}-{j['a']}.tar"
                with open(tar, "wb") as f:
                    vol.read_file_into_fileobj(f"/{job}/{j['a']}-{j['b']}.tar", f)
                shutil.unpack_archive(tar, j["out"])
                os.remove(tar)
        finally:
            vol.remove_file(f"/{job}", recursive=True)
    wall = time.time() - t0
    usd = sum(r["wall_s"] for r in res) * (MODAL_CPU * MODAL_CPU_USD_S + MODAL_MEM_GB * MODAL_MEM_USD_S)
    return res, wall, usd


def main():
    args = sys.argv[1:]
    if args == ["demo"]:
        return demo()
    if args == ["fetch"]:
        print(model(check=True))
        return
    if not args or args[0].startswith("-"):
        sys.exit(__doc__)
    edit = Path(args[0]).resolve()
    plan_name = args[args.index("--plan") + 1] if "--plan" in args else "plan.json"
    plan_path = edit / plan_name
    plan = json.loads(plan_path.read_text())
    if not behind_ranges(plan):
        plan.pop("cutouts", None)
        plan_path.write_text(json.dumps(plan, indent=1))
        print("no behind cards: nothing to cut out")
        return
    w, h, fps = plan["width"], plan["height"], plan["fps"]
    cutouts, runs = missing(plan, edit)
    rel = cutouts[0]["src"]
    frames = sum(b - a + 1 for a, b in runs)
    need = sum(c["to"] - c["from"] + 1 for c in cutouts)
    print(f"{len(cutouts)} range{'s' * (len(cutouts) > 1)} behind cards, {frames} frames to cut "
          f"({need - frames} reused); about {frames * LAPTOP_S:.0f} s on a laptop, free"
          + (f", or about ${frames * LAPTOP_S * (MODAL_CPU * MODAL_CPU_USD_S + MODAL_MEM_GB * MODAL_MEM_USD_S):.3f} on "
             "Modal" if frames else ""), flush=True)
    if "--estimate" in args:
        return
    vf = "null"
    if runs:
        for old in (edit / "cutout").glob(f"*{w}x{h}-*"):    # an older cut's frames (or the pre-pool range folders)
            if old.name != Path(rel).name:
                shutil.rmtree(old)
        sys.path.insert(0, str(Path(__file__).parent))
        from edit import prepare_public
        # The footage exactly as the renderer draws it: edit.py's output-size copy of the cut
        video = prepare_public(edit, {**plan, "cutouts": []}, plan_path.stem[len("plan"):]) / plan["video"]
    jobs = [{"fps": fps, "w": w, "h": h, "vf": vf, "a": a, "b": b, "out": str(edit / rel)} for a, b in runs]
    t0 = time.time()
    if jobs and "--modal" in args:
        res, wall, usd = run_modal(video, jobs, model())
        print(f"Modal: {frames} frames in {wall:.0f} s on {len(jobs)} containers, about ${usd:.4f} at Modal's CPU rates")
    elif jobs:
        res = []
        for j in jobs:
            r = cut_range(video, fps, w, h, vf, j["a"], j["b"], j["out"], model())
            res.append(r)
            print(f"  frames {j['a']}-{j['b']}: {r['wall_s']} s ({r['wall_s'] / r['frames']:.2f} s/frame; "
                  f"matte {r['matte_s']} s, edge refine {r['refine_s']} s)", flush=True)
        wall = time.time() - t0
        print(f"laptop: {frames} frames in {wall:.0f} s ({wall / max(1, frames):.2f} s/frame), free")
    plan["cutouts"] = cutouts
    plan_path.write_text(json.dumps(plan, indent=1))
    print(f"{plan_path}: {len(cutouts)} cutouts")
    if verify(plan, edit, w, h):
        print("Read every WARNING above: change that beat's \"box\" as it says, then plan.py and matte.py again.")


def demo():
    import numpy as np
    import cv2
    plan = {"fps": 30, "durationInFrames": 300, "cards": [
        {"layer": "behind", "start": 1.0, "end": 2.0}, {"layer": "behind", "start": 2.5, "end": 3.0},
        {"start": 4.0, "end": 5.0}, {"layer": "behind", "start": 9.8, "end": 10.0}]}
    assert behind_ranges(plan) == [[15, 105], [279, 299]], behind_ranges(plan)   # merged; clamped at the end
    # A re-plan keeps the cutout: frames are keyed by the cut and their frame number, so a card that moves
    # (the sample take: frames 8-115 -> 105-212) needs only the frames it adds, and a plan whose ranges are
    # all cut gets its cutouts back from plan.py with nothing to run.
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        e = Path(t)
        (e / "cut.mp4").write_bytes(b"x")
        p1 = {"video": "cut.mp4", "width": 1080, "height": 1920, "fps": 30, "durationInFrames": 300,
              "cards": [{"layer": "behind", "start": 0.77, "end": 3.33}]}
        cuts, runs = missing(p1, e)
        assert runs == [[8, 115]] and kept(p1, e) == [], runs
        (e / cuts[0]["src"]).mkdir(parents=True)
        for f in range(8, 116):
            (e / cuts[0]["src"] / f"{f:06d}.png").write_bytes(b"")
        assert kept(p1, e) == cuts and missing(p1, e)[1] == []
        p2 = {**p1, "cards": [{"layer": "behind", "start": 4.0, "end": 6.57}]}
        assert missing(p2, e) == ([{"src": cuts[0]["src"], "from": 105, "to": 212}], [[116, 212]]), missing(p2, e)
        assert kept(p2, e) == []          # not every frame is there yet: check.py plan says to run matte.py
        (e / "cut.mp4").write_bytes(b"a new cut")   # a new cut never reuses the old matte
        assert pool(e, p1) != cuts[0]["src"] and missing(p1, e)[1] == [[8, 115]]
        assert pool(e, {**p1, "fps": 29.97003}) != pool(e, p1)   # a plan at the source's 29.97: its own frames
    # refine: a flat grey wall, an orange disc with a soft edge. The edge's colour must come out orange
    # (no grey bleed), and alpha must be firm inside and zero on the open wall.
    h, w = 200, 200
    yy, xx = np.mgrid[:h, :w]
    d = np.hypot(yy - 100, xx - 100)
    al = np.clip((60 - d) / 6, 0, 1).astype(np.float32)
    fg, wall = np.array([230, 120, 40], np.float32), np.array([128, 128, 128], np.float32)
    cam = (al[..., None] * fg + (1 - al[..., None]) * wall).astype(np.uint8)
    rgb, a2 = refine(cam, al, cv2, np)
    ring = (al > 0.3) & (al < 0.7)
    assert np.abs(rgb[ring] - fg).max(1).mean() < 12, np.abs(rgb[ring] - fg).max(1).mean()
    assert a2[100, 100] > 0.99 and a2[0, 0] == 0
    # stabilise: a still pixel takes the median, a moving one keeps its own
    cams = [np.zeros((10, 10, 3), np.uint8) for _ in range(5)]
    alphas = [np.full((10, 10), v, np.float32) for v in (0.2, 0.9, 0.1, 0.8, 0.85)]
    assert abs(stabilise(cams, alphas, 2, cv2, np)[5, 5] - 0.8) < 1e-6
    cams[0] = np.full((10, 10, 3), 200, np.uint8)
    assert abs(stabilise(cams, alphas, 2, cv2, np)[5, 5] - 0.1) < 1e-6
    # a WARNING names the field that moves the card (the real-footage test's warning named none)
    with tempfile.TemporaryDirectory() as t:
        e = Path(t)
        a = np.full((192, 108, 4), 255, np.uint8)
        a[60:70, 50:58, 3] = 0                                     # a hole in the face
        (e / "cut").mkdir()
        cv2.imwrite(str(e / "cut" / "000045.png"), a)
        (e / "face.json").write_text(json.dumps({"heads": [{"t": 1.5, "box": [30, 25, 40, 20]}]}))
        pl = {"fps": 30, "cutouts": [{"src": "cut", "from": 0, "to": 90}],
              "cards": [{"layer": "behind", "start": 1.0, "end": 2.0, "trigger_word": "repo", "src": "images/capture-x.png",
                         "format": "shot"}]}
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert verify(pl, e, 108, 192) == 1
        assert "through the face" in buf.getvalue() and "'repo' beat" in buf.getvalue() and '"box"' in buf.getvalue() \
            and "visuals.json" in buf.getvalue(), buf.getvalue()
        assert "images.json" in move_hint({"start": 1, "src": "images/dashboard.png"})
    # The Modal image installs the lock's pins (hashes and all), never an unpinned package.
    import re
    import tempfile
    calls = []

    class Rec:
        def __getattr__(self, name):
            return lambda *a, **k: (calls.append((name, a, k)), self)[1]
    with tempfile.TemporaryDirectory() as t:
        matte_image(type("M", (), {"Image": Rec()}), "rvm.onnx", Path(t) / "req.lock")
        names = [c[0] for c in calls]
        assert "pip_install" not in names and "pip_install_from_requirements" in names, names
        c = calls[names.index("pip_install_from_requirements")]
        assert "--require-hashes" in c[2]["extra_options"] and "--no-deps" in c[2]["extra_options"]
        req = Path(c[1][0]).read_text(encoding="utf-8")
    lock = (Path(__file__).resolve().parents[3] / "requirements" / "requirements.lock").read_text(encoding="utf-8")
    pin = lambda txt, n: set(re.findall(rf"^{re.escape(n)}==(\S+)", txt, re.M))
    for n in ("numpy", "opencv-python-headless", "onnxruntime"):
        assert pin(req, n) and pin(req, n) == pin(lock, n), (n, pin(req, n), pin(lock, n))
    print("demo ok")


if __name__ == "__main__":
    main()
