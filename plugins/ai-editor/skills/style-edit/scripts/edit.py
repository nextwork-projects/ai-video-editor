#!/usr/bin/env python3
"""Stills, estimates and renders for a plan.json. Stdlib only.

    python3 edit.py stills   edits/NAME [--plan plan.json] [--no-check]   runs check.py plan, then PNGs into edits/NAME/stills/
    python3 edit.py estimate edits/NAME [--plan plan.json]   laptop time (measured) + Lambda cost (guess)
    python3 edit.py render   edits/NAME [--plan plan.json] [--lambda]   -> edits/NAME/render.mp4
    python3 edit.py demo     self-check

A plan named plan-XYZ.json writes stills-XYZ/ and render-XYZ.mp4, so two aspects can sit side by side.
The renderer lives in ~/.ai-video-editor/remotion (the setup skill installs it; this script
refreshes its source from the plugin on every run).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
REMOTION = HOME / "remotion"
PLUGIN = Path(__file__).resolve().parents[3]            # plugins/ai-editor
SRC = PLUGIN / "remotion"
SETUP = PLUGIN / "skills" / "setup" / "scripts" / "setup.py"


def sync_renderer():
    """Install on first use; afterwards copy the source over so plugin updates take effect."""
    same_deps = (REMOTION / "package.json").exists() and \
        (REMOTION / "package.json").read_bytes() == (SRC / "package.json").read_bytes()
    if not (REMOTION / "node_modules" / "remotion").exists() or not same_deps:
        subprocess.run([sys.executable, str(SETUP), "remotion"], check=True)
    shutil.copytree(SRC / "src", REMOTION / "src", dirs_exist_ok=True)
    for f in ("render.mjs", "tsconfig.json"):
        shutil.copy2(SRC / f, REMOTION / f)


def proxy_filter(sw, sh, w, h):
    """Fit the cut to the output: same shape scales, wider source is centre-cropped,
    taller source (vertical into 16:9) sits over a blurred copy of itself."""
    src, dst = sw / sh, w / h
    if abs(src - dst) < 0.02:
        return f"scale={w}:{h},setsar=1"
    if src > dst:
        return f"scale=-2:{h},crop={w}:{h},setsar=1"
    return (f"split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"gblur=sigma=40,eq=brightness=-0.08[bg];[b]scale=-2:{h}[fg];"
            f"[bg][fg]overlay=(W-w)/2:0,setsar=1")


def prepare_public(edit, plan, tag):
    """A folder with only what the render reads: the cut at output size (keyframe every
    15 frames, which keeps frame seeking fast) and the card images."""
    pub = edit / f".render{tag}"
    pub.mkdir(exist_ok=True)
    cut, proxy = edit / plan["video"], pub / plan["video"]
    if not cut.exists():
        sys.exit(f"ERROR: {cut} missing")
    if not proxy.exists() or proxy.stat().st_mtime < cut.stat().st_mtime:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(Path(__file__).parent))
        from plan import probe
        m = probe(cut)
        print(f"preparing {plan['width']}x{plan['height']} copy of {cut.name}", flush=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cut), "-filter_complex",
                        proxy_filter(m["width"], m["height"], plan["width"], plan["height"]),
                        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-g", "15",
                        "-keyint_min", "15", "-sc_threshold", "0", "-pix_fmt", "yuv420p",
                        "-c:a", "copy", str(proxy)], check=True)
    # Card images, plus every image an anim's props name (a logo card, a scene's icons and logos).
    rels = [c["src"] for c in plan["cards"] if c.get("src")]
    rels += re.findall(r'"(images/[^"]+)"', json.dumps([c.get("anim") for c in plan["cards"]]))
    rels += [c["src"] for c in plan.get("sfx", [])]   # sound cues, from sfx.py
    for rel in dict.fromkeys(rels):
        src = edit / rel
        if not src.exists():
            sys.exit(f"ERROR: {src} missing" + (" (run sfx.py build, then plan.py)" if rel.startswith(".sfx/") else ""))
        (pub / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, pub / rel)
    return pub


def still_frames(plan):
    """Frames that show each part of the edit: the opening, a caption, a zoom, then every card
    (4-card, 5-card, ...) once its entrance and animation have settled. Every card but a logo tile
    moves, so it also gets N-card-early and N-card-late; a card that swaps in right after the
    one before it gets N-swap, mid-move."""
    fps, last = plan["fps"], plan["durationInFrames"] - 1
    chunks, zooms, cards = plan["captions"]["chunks"], plan["zooms"], plan["cards"]
    busy = lambda t: any(z["start"] <= t < z["end"] for z in zooms) or any(c["start"] <= t < c["end"] for c in cards)
    mid = lambda a: (a["start"] + a["end"]) / 2
    frames = {"1-opening": 0.5}
    plain = [mid(c) for c in chunks if not busy(mid(c))]
    if chunks:
        frames["2-caption"] = plain[0] if plain else mid(chunks[0])
    if zooms:
        z = zooms[0]
        inside = [mid(c) for c in chunks if z["start"] <= mid(c) < z["end"]]
        frames["3-zoom"] = inside[0] if inside else mid(z)
    for i, c in enumerate(cards):
        frames[f"{4 + i}-card"] = max(c["start"], min(c["start"] + 1.6, c["end"] - 0.25))
        if c.get("lane") != "logo":
            frames[f"{4 + i}-card-early"] = c["start"] + 0.5
            frames[f"{4 + i}-card-late"] = c["end"] - 0.3
            prev = [p for p in cards[:i] if p.get("lane") != "logo"]
            if prev and 0 <= c["start"] - prev[-1]["end"] < 1.2:
                frames[f"{4 + i}-swap"] = c["start"] + 0.12
    return {k: min(last, round(t * fps)) for k, t in frames.items()}


def aws_env():
    """AWS keys saved by `setup.py awskey`, layered over the real environment."""
    env, f = dict(os.environ), HOME / "aws.env"
    if f.exists():
        for line in f.read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() and v.strip():
                env.setdefault(k.strip(), v.strip())
    return env


def node(*args):
    return subprocess.run(["node", str(REMOTION / "render.mjs"), *map(str, args)], cwd=REMOTION,
                          check=True, capture_output=args[0] in ("bench", "lambda-estimate"), text=True,
                          env=aws_env())


def estimate(plan_path, pub):
    b = json.loads(node("bench", pub, plan_path).stdout.strip().splitlines()[-1])
    laptop = b["bundle_s"] + b["s_per_frame"] * b["frames"]
    lam = json.loads(node("lambda-estimate", plan_path).stdout.strip().splitlines()[-1])
    print(f"Laptop: about {laptop / 60:.1f} min (measured {b['bench_s']:.1f} s for "
          f"{b['bench_frames']} frames, {b['frames']} frames in all).")
    print(f"Lambda: about {lam['wall_s']} s on {lam['lambdas']} Lambdas in {lam['region']}, "
          f"about ${lam['usd']:.3f}. A guess until a real render is measured; the render prints the real cost.")


def demo():
    plan = {"fps": 30, "durationInFrames": 900,
            "captions": {"chunks": [{"start": 1, "end": 2}, {"start": 5, "end": 6}]},
            "zooms": [{"start": 0.5, "end": 3}], "cards": [{"start": 20, "end": 23}, {"start": 25, "end": 26}]}
    f = still_frames(plan)
    assert f == {"1-opening": 15, "2-caption": 165, "3-zoom": 45, "4-card": 648, "4-card-early": 615, "4-card-late": 681,
                 "5-card": 772, "5-card-early": 765, "5-card-late": 771}, f
    plan["cards"][1]["start"] = 23.5
    assert still_frames(plan)["5-swap"] == 709
    assert "crop=1080:1920" in proxy_filter(1920, 1080, 1080, 1920)
    assert "gblur" in proxy_filter(1080, 1920, 1920, 1080)
    assert proxy_filter(3840, 2160, 1920, 1080).startswith("scale=1920:1080")
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stills", "estimate", "render"])
    ap.add_argument("edit")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--lambda", dest="use_lambda", action="store_true")
    ap.add_argument("--no-check", action="store_true", help="stills even when check.py plan finds a FAIL")
    a = ap.parse_args()
    edit = Path(a.edit).resolve()
    plan_path = edit / a.plan
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan"):]
    sync_renderer()
    pub = prepare_public(edit, plan, tag)
    if a.cmd == "stills":
        # check.py plan first: prints what it finds, stops the stills only on a FAIL
        chk = subprocess.run([sys.executable, str(Path(__file__).parent / "check.py"), "plan", str(edit), "--plan", a.plan])
        if chk.returncode and not a.no_check:
            sys.exit("check.py plan found a FAIL: fix it and plan again (edit.py stills --no-check to look anyway)")
        pairs = [f"{k}={v}" for k, v in still_frames(plan).items()]
        node("stills", pub, plan_path, edit / f"stills{tag}", *pairs)
    elif a.cmd == "estimate":
        estimate(plan_path, pub)
    elif a.use_lambda:
        node("lambda", pub, plan_path, edit / f"render{tag}.mp4", re.sub(r"[^a-z0-9-]+", "-", f"ai-editor-{edit.name}{tag}".lower()))
    else:
        node("local", pub, plan_path, edit / f"render{tag}.mp4")


if __name__ == "__main__":
    main()
