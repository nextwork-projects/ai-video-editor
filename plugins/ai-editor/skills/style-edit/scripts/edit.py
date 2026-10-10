#!/usr/bin/env python3
"""Stills, estimates and renders for a plan.json. Stdlib only.

    python3 edit.py stills   edits/NAME [--plan plan.json] [--no-check]   runs check.py plan, then PNGs into edits/NAME/stills/
    python3 edit.py estimate edits/NAME [--plan plan.json]   Laptop, Modal, then GitHub Actions and Lambda: time + cost
    python3 edit.py render   edits/NAME [--plan plan.json] [--modal | --lambda]   -> edits/NAME/render.mp4
    python3 edit.py render   edits/NAME [--plan plan.json] --draft   laptop, 2/3 size -> edits/NAME/render-draft.mp4
    python3 edit.py stills   edits/NAME --at 15.4 --at 13-15.5   only those moments -> stills-at/sheet.png
    python3 edit.py patch    edits/NAME [--range 13-15.5]   re-renders only what changed since render.mp4 (render.plan.json)
    python3 edit.py render   edits/NAME [--plan plan.json] --github   -> edits/NAME/github-render/ + github-render-media.zip
    python3 edit.py github-push  edits/NAME --repo NAME [--plan plan.json]   private repo + media release, starts a render
    python3 edit.py github-fetch edits/NAME --repo NAME [--plan plan.json]   waits, then -> edits/NAME/render-github.mp4
    python3 edit.py demo     self-check

A plan named plan-XYZ.json writes stills-XYZ/ and render-XYZ.mp4, so two aspects can sit side by side.
The renderer lives in ~/.ai-video-editor/remotion (the setup skill installs it; this script
refreshes its source from the plugin on every run).
"""
import argparse
import filecmp
import inspect
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
REMOTION = HOME / "remotion"
PLUGIN = Path(__file__).resolve().parents[3]            # plugins/ai-editor
SRC = PLUGIN / "remotion"
SETUP = PLUGIN / "skills" / "setup" / "scripts" / "setup.py"


def sync_renderer():
    """Install on first use; afterwards copy the source over so plugin updates take effect."""
    lock = "package-lock.json"     # the pinned set: a changed lock means npm ci again
    same_deps = (REMOTION / lock).exists() and (REMOTION / lock).read_bytes() == (SRC / lock).read_bytes()
    if not (REMOTION / "node_modules" / "remotion").exists() or not same_deps:
        subprocess.run([sys.executable, str(SETUP), "remotion"], check=True)
    mirror(SRC / "src", REMOTION / "src")
    for f in ("render.mjs", "tsconfig.json"):
        copy_changed(SRC / f, REMOTION / f)


def mirror(src, dst):
    """Make dst an exact copy of src: changed files copied, files gone from src removed from dst."""
    shutil.copytree(src, dst, dirs_exist_ok=True, copy_function=copy_changed)
    for p in sorted(dst.rglob("*"), reverse=True):     # children before their folder
        if not (src / p.relative_to(dst)).exists():    # missing_ok: parallel stills may race to the same file
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() and not p.is_symlink() else p.unlink(missing_ok=True)


def copy_changed(src, dst):
    """Copy only a changed file, through a temp name: several clips' stills run at once, and an
    unchanged file rewritten in place is briefly empty while another run bundles it."""
    if not (os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False)):
        tmp = f"{dst}.{os.getpid()}.tmp"
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    return dst


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
    # Card images, plus every image an anim's or a capture card's props name (a logo card, a diagram's logos, props.logo_src).
    rels = [c["src"] for c in plan["cards"] if c.get("src")]
    rels += re.findall(r'"(images/[^"]+)"', json.dumps([[c.get("anim"), c.get("props")] for c in plan["cards"]]))
    rels += [c["src"] for c in plan.get("sfx", [])]   # sound cues, from sfx.py
    rels += [plan["music"]["src"]] if plan.get("music") else []   # the music bed, from sfx.py music
    rels += [plan["cover"]["src"]] if plan.get("cover") else []   # an audio clip's cover, from clips.py trim
    for c in plan.get("cutouts", []):   # the speaker cut out for behind cards: a folder of PNGs from matte.py
        if not (edit / c["src"]).is_dir():
            sys.exit(f"ERROR: {edit / c['src']} missing (run matte.py)")
        shutil.copytree(edit / c["src"], pub / c["src"], dirs_exist_ok=True, copy_function=lambda a, b: None if (
            os.path.exists(b) and os.path.getmtime(b) >= os.path.getmtime(a)) else shutil.copy2(a, b))   # only new frames
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
        for line in f.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() and v.strip():
                env.setdefault(k.strip(), v.strip())
    return env


def node(*args):
    try:
        return subprocess.run(["node", str(REMOTION / "render.mjs"), *map(str, args)], cwd=REMOTION,
                              check=True, capture_output=args[0] in ("bench", "lambda-estimate", "bundle"), text=True,
                              env=aws_env())
    except subprocess.CalledProcessError as e:     # a short message, never a traceback (render.md "If a render stops")
        last = [x for x in (e.stderr or "").splitlines() if x.strip() and not x.lstrip().startswith("at ")][-1:]
        sys.exit(f"ERROR: render.mjs {args[0]} failed (exit {e.returncode})" + (f": {last[0].strip()}" if last else
                 " (its output is above)") + ". Run the same command again once; if it stops the same way, see "
                 "style-edit references/render.md \"If a render stops\".")


# The stall watchdog. A laptop render once sat at 0% CPU for 25 min after Remotion restarted a crashed
# browser ("Made new browser"), printing nothing. No new "Rendered N/M" line for this long = stalled:
# Remotion's own per-frame deadline (render.mjs TIMEOUT_MS, 120 s) plus a margin, or 200 frames' time
# on a slow machine. Before the first frame: bundling and Chrome's start, STALL_START_S more.
STALL_MIN_S, STALL_FRAMES, STALL_START_S = 180, 200, 120
CHUNK_FRAMES = 200        # the fallback: pieces this long, each its own Chrome (the path that finished the
                          # stalled render in the real-footage test)
STALLED = "stalled"


def stall_s(s_per_frame):
    return max(STALL_MIN_S, STALL_FRAMES * s_per_frame)


def watch(cmd, log, stall, start=STALL_START_S, cwd=None, env=None, echo=True):
    """Run cmd with its output into log (and its progress and errors onto stdout). Returns its exit code,
    or STALLED after killing it (and Chrome under it) when no new "Rendered N/M" came for `stall` seconds."""
    import threading
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    seen = {"t": time.time() + start, "n": None}
    with open(log, "a", encoding="utf-8") as f:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=cwd, env=env,
                             start_new_session=os.name != "nt")

        def read():
            for line in p.stdout:
                f.write(line)
                f.flush()
                m = re.match(r"Rendered (\d+)/", line)
                if m and m.group(1) != seen["n"]:
                    seen.update(t=time.time(), n=m.group(1))
                if echo and not line.lstrip().startswith("at "):
                    print(line, end="", flush=True)
        th = threading.Thread(target=read, daemon=True)
        th.start()
        while p.poll() is None:
            if time.time() - seen["t"] > stall:
                if os.name != "nt":
                    os.killpg(p.pid, 9)
                else:
                    p.kill()
                p.wait()
                th.join(5)
                f.write(f"\n[edit.py: no new frame for {stall:.0f} s, stopped]\n")
                return STALLED
            time.sleep(0.5)
        th.join(5)
        return p.returncode


def render_failed(code, log, edit):
    """A failed render: one short message with the log and the next step, never a traceback."""
    lines = [x.strip() for x in Path(log).read_text(errors="replace", encoding="utf-8").splitlines()
             if x.strip() and not x.lstrip().startswith("at ")] if Path(log).exists() else []
    sys.exit(f"ERROR: the laptop render failed (exit {code}). The renderer's log: {log}"
             + (f"\n  its last line: {lines[-1][:200]}" if lines else "")
             + f"\nNext: render again once (edit.py render {edit}); if it fails the same way, offer --draft or --modal.")


# Laptop speed: benchmarked once (2 s of the first video), then replaced by every full laptop render.
LAPTOP_JSON = HOME / "laptop.json"


def laptop_speed(plan_path, pub):
    try:
        return json.loads(LAPTOP_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        b = json.loads(node("bench", pub, plan_path).stdout.strip().splitlines()[-1])
        m = {"s_per_frame": b["s_per_frame"], "bundle_s": b["bundle_s"], "start_s": b.get("start_s", 0), "source": "benchmark"}
        LAPTOP_JSON.write_text(json.dumps(m), encoding="utf-8")
        return m


def laptop_s(lap, frames):
    """A laptop render's seconds: bundling, Chrome's start-up once (a benchmark times it apart; a full
    render's speed already holds it), then every frame."""
    return lap["bundle_s"] + lap.get("start_s", 0) + lap["s_per_frame"] * frames


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# Modal (modal.com): one container per chunk, all at once. Rates from modal.com/pricing, read
# 2026-10-06: CPU $0.0000131 per physical core per second, memory $0.00000222 per GiB per second,
# billed on the higher of what is requested and what is used. modal_render.py does the render.
MODAL_CPU = 4                  # physical cores requested per container
MODAL_MEM_MB = 8192
MODAL_CPU_USD_S = 0.0000131
MODAL_MEM_USD_S = 0.00000222
# Measured on the bill, 2026-10-07 (the 205.6 s sample take, 9 and 19 containers): Chrome uses about
# 4.6 cores of the 4 requested, and each container is billed about 23 s past its render (boot, image).
# ponytail: one take on one day; re-measure when the bill and the printed cost drift apart.
MODAL_CORES_BILLED = 4.6
MODAL_BOOT_S = 23
MODAL_MAX_CONTAINERS = 40
# Containers: as many as keep the billed boot under MODAL_OVERHEAD of each container's bill (23 s of
# boot over about 115 s of work). Starting one takes seconds (measured below), so more containers are
# faster, only dearer. Each container gets MODAL_PIECES pieces from a shared queue: one that runs fast
# takes the next piece, so a slow container (some ran 3x slower on the same frames) holds up less.
MODAL_OVERHEAD = 0.2
MODAL_PIECES = 3
MODAL_MIN_PIECE = 100          # frames; each piece starts Node and Chrome again
MODAL_JSON = HOME / "modal.json"   # the last Modal render's measured speed
# Until this computer's first Modal render, the sample take's (6,167 frames, 2026-10-07, 16 containers
# x 3 pieces, 184 s in all; the upload speed from the render before it, 200 MB in 21.5 s):
#   s_per_frame  container seconds per 1080p frame, Node and Chrome start included (piece times / frames)
#   start_s      submit to the last container starting (4-18 s over four renders)
#   straggle     the render phase past start_s over the ideal, container seconds / containers
#   tail_s       the last piece done to the joined file: the rest of the download and the join
#   up_bytes_s   upload speed, which is the uplink of the computer that measured it
# Each Modal render saves its own to MODAL_JSON and the next estimate uses those.
MODAL_MEASURED = {"s_per_frame": 0.331, "start_s": 7, "straggle": 1.26, "tail_s": 12, "up_bytes_s": 9.3e6}


def modal_plan(frames, s_per_frame):
    """(containers, pieces): pieces are inclusive [from, to] frame ranges, MODAL_PIECES per container."""
    n = max(1, min(MODAL_MAX_CONTAINERS, int(frames * s_per_frame * MODAL_OVERHEAD / MODAL_BOOT_S)))
    k = max(1, min(n * MODAL_PIECES, frames // MODAL_MIN_PIECE))
    step = math.ceil(frames / k)
    pieces = [[a, min(frames, a + step) - 1] for a in range(0, frames, step)]
    return min(n, len(pieces)), pieces


def modal_cost(container_s, containers):
    """USD for container_s seconds of rendering on `containers` containers: each is also billed
    MODAL_BOOT_S, at the cores Chrome really uses (more than the request, which Modal bills) and the
    memory requested."""
    s = container_s + containers * MODAL_BOOT_S
    return s * (max(MODAL_CPU, MODAL_CORES_BILLED) * MODAL_CPU_USD_S + MODAL_MEM_MB / 1024 * MODAL_MEM_USD_S)


def modal_speed():
    """(speeds, measured?): the last Modal render's measurements over the sample take's."""
    try:
        m = json.loads(MODAL_JSON.read_text(encoding="utf-8"))
        return {**MODAL_MEASURED, **{k: m[k] for k in MODAL_MEASURED if k in m}}, "straggle" in m
    except (OSError, ValueError):
        return dict(MODAL_MEASURED), False


def modal_estimate(frames, media_bytes, m=None):
    """(wall s, usd, containers, measured?): upload + start + the render on n containers, slowed by the
    straggle factor + the tail. media_bytes is what goes up: modal_upload_bytes leaves out footage Modal
    already holds."""
    m, measured = (m, True) if m else modal_speed()
    work = frames * m["s_per_frame"]
    n, _ = modal_plan(frames, m["s_per_frame"])
    wall = media_bytes / m["up_bytes_s"] + m["start_s"] + work / n * m["straggle"] + m["tail_s"]
    return wall, modal_cost(work, n), n, measured


def modal_upload_bytes(pub, media, run=subprocess.run, ready=None):
    """Footage bytes a Modal render will upload. Modal skips a file it already holds by its hash (a
    re-render's upload takes 3-4 s); modal_render.py held asks by hash and sends nothing. Modal not set
    up, or no answer in 30 s: all of it."""
    if not (ready or modal_ready)():
        return media
    try:
        r = run([venv_python(), str(Path(__file__).parent / "modal_render.py"), "held", str(pub)],
                capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout.strip().splitlines()[-1])["to_upload"]
    except Exception:
        return media


def venv_python():
    vpy = HOME / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return str(vpy) if vpy.exists() else sys.executable


def modal_ready():
    """modal installed in the venv and a token saved (no network call)."""
    has_pkg = subprocess.run([venv_python(), "-c", "import modal"], capture_output=True).returncode == 0
    has_token = (Path.home() / ".modal.toml").exists() or bool(os.environ.get("MODAL_TOKEN_ID"))
    return has_pkg and has_token


def gh_ready():
    """gh installed and logged in (`gh auth status` reads the saved login)."""
    return bool(shutil.which("gh")) and subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0


def aws_ready(env=None, home=None):
    """AWS keys in the environment or saved by `setup.py awskey`, or a profile in ~/.aws (no network call)."""
    env = aws_env() if env is None else env
    return (any(env.get(k) for k in ("AWS_ACCESS_KEY_ID", "REMOTION_AWS_ACCESS_KEY_ID", "AWS_PROFILE"))
            or (Path(home or Path.home()) / ".aws" / "credentials").exists())


def not_set_up(ready, step):
    return "" if ready else f" Not set up yet: the setup skill's {step} runs first."


def render_modal(edit, plan_path, pub, out):
    bundle_dir = edit / ".modal-bundle"
    node("bundle", pub, bundle_dir)
    r = subprocess.run([venv_python(), str(Path(__file__).parent / "modal_render.py"), "render",
                        str(bundle_dir), str(plan_path), str(out)], stdout=subprocess.PIPE, text=True)
    shutil.rmtree(bundle_dir, ignore_errors=True)
    print(r.stdout, end="")
    if r.returncode:
        sys.exit("ERROR: the Modal render failed (above). Nothing was written to " + str(out))
    m = json.loads(r.stdout.strip().splitlines()[-1])
    save_json(MODAL_JSON, {**modal_speed()[0], **m})    # an upload Modal skipped keeps the last uplink speed


def render_chunks(edit, plan_path, pub, out, draft, log, stall, run=None, bundle_to=None):
    """The fallback after a stall: bundle once, render CHUNK_FRAMES-frame pieces (each its own Chrome, each
    retried once if it stalls), then the GitHub workflow's JOIN puts them together."""
    run = run or watch
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    tmp = edit / f".render-chunks{out.stem[len('render'):]}"
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "chunks").mkdir(parents=True)
    bundle = tmp / "bundle"
    (bundle_to or (lambda a, b: node("bundle", a, b)))(pub, bundle)
    frames = plan["durationInFrames"]
    pieces = [{"i": f"{i:03d}", "from": a, "to": min(frames, a + CHUNK_FRAMES) - 1}
              for i, a in enumerate(range(0, frames, CHUNK_FRAMES))]
    for c in pieces:
        cmd = ["node", str(REMOTION / "render.mjs"), "chunk", str(bundle), str(plan_path),
               str(tmp / "chunks" / f"chunk-{c['i']}.mkv"), str(c["from"]), str(c["to"]), *(["--draft"] if draft else [])]
        r = run(cmd, log, stall, cwd=REMOTION, env=aws_env())
        if r == STALLED:
            print(f"frames {c['from']}-{c['to']} stalled too; once more")
            r = run(cmd, log, stall, cwd=REMOTION, env=aws_env())
        if r:
            render_failed("stalled" if r == STALLED else r, log, edit)
    j = subprocess.run([sys.executable, "-c", JOIN], cwd=tmp, capture_output=True, text=True,
                       env={**os.environ, "FPS": str(plan["fps"]), "CHUNKS": json.dumps(pieces)})
    if j.returncode:
        Path(log).open("a").write(j.stderr)
        render_failed(j.returncode, log, edit)
    shutil.move(str(tmp / "out" / "render.mp4"), out)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"rendered {out} in {len(pieces)} pieces")


def render_laptop(edit, plan_path, pub, out, draft, run=None, chunks=None):
    t0 = time.time()
    frames = json.loads(plan_path.read_text(encoding="utf-8"))["durationInFrames"]
    try:
        spf = json.loads(LAPTOP_JSON.read_text(encoding="utf-8"))["s_per_frame"]
    except (OSError, ValueError, KeyError):
        spf = 0.3
    stall, log = stall_s(spf), out.parent / f"{out.stem}.renderer.log"
    log.unlink(missing_ok=True)
    r = (run or watch)(["node", str(REMOTION / "render.mjs"), "local", str(pub), str(plan_path), str(out),
                        *(["--draft"] if draft else [])], log, stall, cwd=REMOTION, env=aws_env())
    if r == STALLED:
        print(f"\nthe render stalled: no new frame for {stall:.0f} s. Stopped it; rendering again in "
              f"{CHUNK_FRAMES}-frame pieces (log: {log})", flush=True)
        (chunks or render_chunks)(edit, plan_path, pub, out, draft, log, stall)
        return
    if r:
        render_failed(r, log, edit)
    # The next estimate uses this video's real speed. ponytail: a clip under 10 s is mostly Chrome
    # starting up, so it would overstate the speed of a long video; those are skipped.
    if not draft and frames >= 300:
        try:
            bundle_s = json.loads(LAPTOP_JSON.read_text(encoding="utf-8"))["bundle_s"]
        except (OSError, ValueError, KeyError):
            bundle_s = 3.0
        save_json(LAPTOP_JSON, {"s_per_frame": max(0.001, (time.time() - t0 - bundle_s) / frames),
                                "bundle_s": bundle_s, "source": f"render of {edit.name}"})


# GitHub Actions, measured 2026-09-30 (a private test repo): ubuntu-latest rendered
# the sample take, 44.2 s of 1080x1920 (1326 frames), in 409 s, plus about 25 s of npm ci, browser and media download.
GH_S_PER_FRAME = 0.31
GH_INSTALL_S = 25
GH_CHUNK_S = 120          # about 2 min of video per runner
GH_MAX_CHUNKS = 20        # free accounts run 20 jobs at once
GH_ASSET_MAX = 1_900_000_000   # release files are capped at 2 GiB; bigger media goes up in parts


def chunk_ranges(frames, fps):
    """Frame ranges [from, to] (inclusive), one per runner. The workflow's plan job runs this function."""
    k = max(1, min(GH_MAX_CHUNKS, math.ceil(frames / (fps * GH_CHUNK_S))))
    step = math.ceil(frames / k)
    return [[a, min(frames, a + step) - 1] for a in range(0, frames, step)]


def github_estimate(frames, fps, media_bytes):
    chunks = chunk_ranges(frames, fps)
    longest = max(b - a + 1 for a, b in chunks)
    wall = GH_INSTALL_S + longest * GH_S_PER_FRAME
    # Actions bills each job rounded up to the minute: the plan job, every chunk, the join.
    minutes = 2 + sum(math.ceil((GH_INSTALL_S + (b - a + 1) * GH_S_PER_FRAME) / 60) for a, b in chunks)
    parts = math.ceil(media_bytes / GH_ASSET_MAX)
    media = (f"media {media_bytes / 1e6:.0f} MB, " +
             ("fits one release file" if parts <= 1 else f"uploaded in {parts} parts (one release file holds 2 GB)"))
    return (f"GitHub Actions: about {wall / 60:.1f} min on {len(chunks)} runner{'s' * (len(chunks) > 1)}, "
            f"uses about {minutes} of the 2,000 free private-repo minutes a month; {media}. Free.")


def minutes(s):
    return f"{s:.0f} s" if s < 90 else f"{s / 60:.1f} min"


def speed_note(lap, name):
    """Where the laptop speed comes from, and how far to trust it."""
    src = lap.get("source", "")
    if src == "benchmark":
        return "speed from a 2 s benchmark: a rough guess"
    if src == f"render of {name}":
        return "speed from this video's last render"
    other = src[len("render of "):] if src.startswith("render of ") else src
    return f"speed from the last render of another video ({other}): a rough guess, cards and length change it"


def estimate(plan_path, pub):
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    frames = plan["durationInFrames"]
    media = sum(f.stat().st_size for f in pub.rglob("*") if f.is_file())
    lap = laptop_speed(plan_path, pub)
    print(f"Laptop: about {minutes(laptop_s(lap, frames))} ({frames} frames, {speed_note(lap, plan_path.parent.name)}). Free.")
    wall, usd, n, measured = modal_estimate(frames, modal_upload_bytes(pub, media))
    print(f"Modal: about {minutes(wall)} on {n} machine{'s' * (n > 1)}, about ${usd:.2f} "
          f"({'speed measured on the last Modal render' if measured else 'a guess until the first Modal render'}; "
          f"the Starter plan includes $30 of free credit a month)." +
          not_set_up(modal_ready(), "Modal step"))
    lam = json.loads(node("lambda-estimate", plan_path).stdout.strip().splitlines()[-1])
    print("Other: " + github_estimate(frames, plan["fps"], media) + not_set_up(gh_ready(), "GitHub CLI section"))
    print(f"Other: Lambda: about {lam['wall_s']} s on {lam['lambdas']} Lambdas in {lam['region']}, "
          f"about ${lam['usd']:.3f}. A guess until a real render is measured; the render prints the real cost."
          + not_set_up(aws_ready(), "Lambda section"))


# The render in parallel: `plan` splits the frames (chunk_ranges, pasted in below), one `render` job per
# chunk, `join` concatenates the chunks in order into the `render` artifact that github-fetch downloads.
WORKFLOW = """name: render
on: workflow_dispatch
permissions:
  contents: read
  actions: write
jobs:
  plan:
    runs-on: ubuntu-latest
    outputs:
      chunks: ${{ steps.split.outputs.chunks }}
      fps: ${{ steps.split.outputs.fps }}
    steps:
      - uses: actions/checkout@v4
      - id: split
        run: |
          python3 - <<'EOF' >> "$GITHUB_OUTPUT"
          import json, math
__CHUNK_PY__
          p = json.load(open("plan.json"))
          r = chunk_ranges(p["durationInFrames"], p["fps"])
          print("chunks=" + json.dumps([{"i": f"{i:02d}", "from": a, "to": b} for i, (a, b) in enumerate(r)]))
          print(f"fps={p['fps']}")
          EOF
  render:
    needs: plan
    runs-on: ubuntu-latest
    timeout-minutes: 360
    strategy:
      matrix:
        chunk: ${{ fromJSON(needs.plan.outputs.chunks) }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: if [ -f package-lock.json ]; then npm ci; else npm install; fi
      - run: npx remotion browser ensure
      - run: |
          gh release download media -R "$GITHUB_REPOSITORY" -p '__ZIP__*'
          if ls __ZIP__.part-* >/dev/null 2>&1; then cat __ZIP__.part-* > __ZIP__ && rm __ZIP__.part-*; fi
          unzip -q __ZIP__ -d public && rm __ZIP__
        env:
          GH_TOKEN: ${{ github.token }}
      - run: node render.mjs chunk public plan.json out/chunk-${{ matrix.chunk.i }}.mkv ${{ matrix.chunk.from }} ${{ matrix.chunk.to }}
      - uses: actions/upload-artifact@v4
        with:
          name: chunk-${{ matrix.chunk.i }}
          path: out/chunk-${{ matrix.chunk.i }}.mkv
          retention-days: 1
  join:
    needs: [plan, render]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: chunk-*
          path: chunks
          merge-multiple: true
      - run: command -v ffmpeg || (sudo apt-get update -q && sudo apt-get install -y -q ffmpeg)
      - run: |
          python3 - <<'EOF'
__JOIN__
          EOF
        env:
          CHUNKS: ${{ needs.plan.outputs.chunks }}
          FPS: ${{ needs.plan.outputs.fps }}
      - uses: actions/upload-artifact@v4
        with:
          name: render
          path: out/render.mp4
          retention-days: 1
      - run: |
          gh api "repos/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID/artifacts" --paginate \\
            -q '.artifacts[] | select(.name | startswith("chunk-")) | .id' |
            xargs -I{} gh api -X DELETE "repos/$GITHUB_REPOSITORY/actions/artifacts/{}"
        env:
          GH_TOKEN: ${{ github.token }}
"""
# Chunks carry PCM audio that runs a few samples past the last frame (16 at 30 fps). Each chunk's audio
# is cut to exactly its frames, the pieces laid end to end and encoded to AAC once; the video is copied.
# Measured on the sample take (3 chunks): no gap or step at the joins, sync held to the sample.
JOIN = """import json, os, subprocess
fps, sr = float(os.environ["FPS"]), 48000
chunks = json.loads(os.environ["CHUNKS"])
os.makedirs("out", exist_ok=True)
with open("list.txt", "w") as lst, open("audio.raw", "wb") as pcm:
    for c in chunks:
        f = os.path.abspath(f"chunks/chunk-{c['i']}.mkv")
        lst.write(f"file '{f}'\\n")
        n = 4 * (round((c["to"] + 1) * sr / fps) - round(c["from"] * sr / fps))
        a = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-map", "0:a", "-f", "s16le", "-ac", "2",
                            "-ar", str(sr), "-"], capture_output=True, check=True).stdout
        pcm.write(a[:n].ljust(n, b"\\0"))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", "list.txt",
                "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", "audio.raw", "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", "out/render.mp4"], check=True)
"""


def workflow(zip_name):
    py = "\n".join(f"GH_CHUNK_S = {GH_CHUNK_S}\nGH_MAX_CHUNKS = {GH_MAX_CHUNKS}\n{inspect.getsource(chunk_ranges)}".splitlines())
    ind = lambda t: "\n".join(" " * 10 + l if l.strip() else "" for l in t.splitlines())
    return (WORKFLOW.replace("__CHUNK_PY__", ind(py)).replace("__JOIN__", ind(JOIN))
            .replace("__ZIP__", zip_name))


README = """# {name}: render on GitHub Actions

Made by the AI video editor (`edit.py render --github`). Keep this repo private: the footage is in
it, as the `{zip}` asset of the `media` release.

Actions > render > Run workflow renders `plan.json` with Remotion, about 2 minutes of video per
runner in parallel, then joins the pieces. The video is the `render` artifact on the finished run
(kept 1 day). `edit.py github-fetch` downloads it, then deletes the footage (the `media` release) and
the run's artifacts unless the profile says `"cloud_cleanup": false`.
"""


def gh_paths(edit, tag):
    """(git folder, media zip) for one plan."""
    return edit / f"github-render{tag}", edit / f"github-render{tag}-media.zip"


def media_files(zip_path):
    """What goes up to the release: the zip, or its parts when it was too big for one file."""
    return sorted(zip_path.parent.glob(zip_path.name + ".part-*")) or [zip_path]


def split_file(path, size):
    """path -> path.part-00, -01, ... of at most size bytes; the workflow cats them back together."""
    with open(path, "rb") as f:
        for i in range(math.ceil(path.stat().st_size / size)):
            with open(f"{path}.part-{i:02d}", "wb") as out:
                left = size
                while left and (buf := f.read(min(left, 1 << 24))):
                    out.write(buf)
                    left -= len(buf)
    path.unlink()


def package_github(edit, plan_path, pub, tag):
    """The renderer source + plan in a git folder (no media), the media zipped beside it."""
    repo, zip_path = gh_paths(edit, tag)
    shutil.rmtree(repo / "src", ignore_errors=True)
    shutil.copytree(SRC / "src", repo / "src")
    for f in ("package.json", "render.mjs", "tsconfig.json"):
        shutil.copy2(SRC / f, repo / f)
    lock = REMOTION / "package-lock.json"          # npm ci on the runner then matches this laptop
    if lock.exists():
        shutil.copy2(lock, repo / "package-lock.json")
    shutil.copy2(plan_path, repo / "plan.json")
    (repo / ".gitignore").write_text("node_modules/\nout/\npublic/\n*.mp4\n*.zip\n", encoding="utf-8")
    (repo / "README.md").write_text(README.format(name=edit.name, zip=zip_path.name), encoding="utf-8")
    wf = repo / ".github" / "workflows" / "render.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(workflow(zip_path.name), encoding="utf-8")
    for f in media_files(zip_path):
        f.unlink(missing_ok=True)
    shutil.make_archive(str(zip_path.with_suffix("")), "zip", pub)
    if zip_path.stat().st_size > GH_ASSET_MAX:
        split_file(zip_path, GH_ASSET_MAX)
    mb = lambda p: sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and ".git" not in f.parts) / 1e6
    print(f"{repo} ({mb(repo):.1f} MB)")
    for f in media_files(zip_path):
        print(f"{f} ({f.stat().st_size / 1e6:.1f} MB)")
    return repo, zip_path


def gh(*args, check=True, cwd=None):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, cwd=cwd)
    if check and r.returncode:
        sys.exit(f"ERROR: gh {' '.join(args)}\n{r.stderr.strip()}")
    return r


def need_gh():
    if not shutil.which("gh"):
        sys.exit("ERROR: the GitHub CLI (gh) is missing. The setup skill's doctor prints the install command.")
    if subprocess.run(["gh", "auth", "status"], capture_output=True).returncode:
        print("Not logged in to GitHub. In your own terminal, run:\n  gh auth login --web")
        sys.exit(1)


# The render repo's own .git/config: an empty helper clears the user's global ones for this repo only, then
# gh supplies the login. `gh auth setup-git` would rewrite the user's global git config instead.
GIT_CREDENTIAL = [["config", "--local", "--replace-all", "credential.helper", ""],
                  ["config", "--local", "--add", "credential.helper", "!gh auth git-credential"]]


def cloud_cleanup():
    """The profile's answer to "Delete the uploaded footage from <service> after rendering?". Unanswered: yes."""
    sys.path.insert(0, str(PLUGIN / "lib"))
    from ai_editor import profile
    return profile.load().get("cloud_cleanup", True) is not False


def github_cleanup(repo_name, run_id, gh=gh):
    """After the render is downloaded: delete the footage from GitHub. The `media` release (and its tag) and every
    artifact of the run. The repo stays (renderer source and plan, no footage) for the next push."""
    gh("release", "delete", "media", "-y", "--cleanup-tag", "-R", repo_name, check=False)
    arts = gh("api", f"repos/{repo_name}/actions/runs/{run_id}/artifacts", check=False).stdout
    for a in (json.loads(arts).get("artifacts", []) if arts.strip() else []):
        gh("api", "-X", "DELETE", f"repos/{repo_name}/actions/artifacts/{a['id']}", check=False)
    print(f"deleted the footage from {repo_name}: the media release and the run's artifacts")


def github_push(edit, repo_name, tag):
    need_gh()
    repo, zip_path = gh_paths(edit, tag)
    media = media_files(zip_path)
    if not (repo / ".github").exists() or not media[0].exists():
        sys.exit(f"ERROR: {repo} missing: run edit.py render {edit} --github first")
    view = gh("repo", "view", repo_name, "--json", "isPrivate,nameWithOwner,url", check=False)
    info = json.loads(view.stdout) if view.returncode == 0 else None
    if info and not info["isPrivate"]:
        sys.exit(f"ERROR: {info['nameWithOwner']} is public. The footage goes in this repo: use a private one.")
    git = lambda *a, **kw: subprocess.run(["git", *a], cwd=repo, check=True, **kw)
    if not (repo / ".git").exists():
        git("init", "-q", "-b", "main")
    for c in GIT_CREDENTIAL:                       # git pushes with the gh login, in this repo only
        git(*c)
    git("add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode:
        who = subprocess.run(["git", "config", "user.email"], cwd=repo, capture_output=True, text=True).stdout.strip()
        ident = [] if who else ["-c", "user.name=ai-video-editor", "-c", "user.email=ai-video-editor@users.noreply.github.com"]
        subprocess.run(["git", *ident, "commit", "-q", "-m", "Render plan"], cwd=repo, check=True)
    if info is None:
        print(f"creating private repo {repo_name}")
        gh("repo", "create", repo_name, "--private", "--source", ".", "--push", cwd=repo)
        info = json.loads(gh("repo", "view", repo_name, "--json", "isPrivate,nameWithOwner,url").stdout)
    else:
        if subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo, capture_output=True).returncode:
            git("remote", "add", "origin", info["url"] + ".git")
        git("push", "-q", "-u", "origin", "HEAD:main")
    full = info["nameWithOwner"]
    print(f"uploading {', '.join(f.name for f in media)} ({sum(f.stat().st_size for f in media) / 1e6:.0f} MB)", flush=True)
    rel = gh("release", "view", "media", "-R", full, "--json", "assets", "-q", ".assets[].name", check=False)
    if rel.returncode == 0:
        # A zip left from an earlier push would be downloaded with (or cat over) the new media.
        for old in set(rel.stdout.split()) - {f.name for f in media}:
            gh("release", "delete-asset", "media", old, "-y", "-R", full)
        gh("release", "upload", "media", *map(str, media), "--clobber", "-R", full)
    else:
        gh("release", "create", "media", *map(str, media), "--title", "media", "-R", full,
           "--notes", "Footage for the render workflow. Keep this repo private.")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 5))
    for attempt in range(10):                      # a just-pushed workflow takes a few seconds to register
        if gh("workflow", "run", "render.yml", "-R", full, check=attempt == 9).returncode == 0:
            break
        time.sleep(3)
    # github-fetch downloads the run started here, never an older one.
    (edit / f"github{tag}.json").write_text(json.dumps({"repo": full, "started": started}), encoding="utf-8")
    print(f"render started: {info['url']}/actions/workflows/render.yml")


def github_fetch(edit, repo_name, tag):
    need_gh()
    meta = edit / f"github{tag}.json"
    since = json.loads(meta.read_text(encoding="utf-8"))["started"] if meta.exists() else ""
    runs = []
    for _ in range(20):                            # the run triggered by github-push can take a moment to appear
        runs = [r for r in json.loads(gh("run", "list", "-R", repo_name, "--workflow", "render.yml", "-L", "5",
                                         "--json", "databaseId,url,createdAt").stdout) if r["createdAt"] >= since]
        if runs:
            break
        time.sleep(3)
    if not runs:
        sys.exit("ERROR: no render run since the last push: run edit.py github-push first")
    run_id = str(runs[0]["databaseId"])
    print(f"waiting for {runs[0]['url']}", flush=True)
    if subprocess.run(["gh", "run", "watch", run_id, "-R", repo_name, "--exit-status"]).returncode:
        sys.exit(f"ERROR: the render failed. Open {runs[0]['url']} for the log.")
    tmp = edit / f".github-download{tag}"
    shutil.rmtree(tmp, ignore_errors=True)
    gh("run", "download", run_id, "-R", repo_name, "-n", "render", "-D", str(tmp))
    out = edit / f"render-github{tag}.mp4"
    shutil.move(str(tmp / "render.mp4"), out)
    shutil.rmtree(tmp, ignore_errors=True)
    if cloud_cleanup():
        github_cleanup(repo_name, run_id)
    else:
        print(f"kept on GitHub (profile cloud_cleanup false): the footage is the media release of {repo_name}")
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(out)], capture_output=True, text=True).stdout.strip()
    print(f"{out} ({float(dur):.1f} s)")


def contact_sheet(edit, plan_name, folder=None):
    """sheet.py in the venv (it needs Pillow): one labelled sheet of every still, printed as THE review image."""
    r = subprocess.run([venv_python(), str(Path(__file__).parent / "sheet.py"), str(edit), "--plan", plan_name,
                        *(["--dir", folder] if folder else [])],
                       capture_output=True, text=True)
    if r.returncode:
        print(f"note: no contact sheet ({(r.stderr.strip().splitlines() or ['sheet.py failed'])[-1]}); review the stills one by one")
        return
    s = json.loads(r.stdout.strip().splitlines()[-1])
    print(f"REVIEW THIS: {s['sheet']}\n  {s['stills']} stills on one sheet, {s['size'][0]}x{s['size'][1]}, about "
          f"{s['tokens_sheet']} image tokens (the stills one by one: about {s['tokens_stills']}). "
          f"Open a single still from {Path(s['sheet']).parent} only to zoom in on a tile.")


def secs(x):
    """'15.4', '15.4s', '0:15' or '1:02.5' -> seconds."""
    m, _, sec = str(x).strip().rstrip("s").rpartition(":")
    return round((int(m) * 60 if m else 0) + float(sec), 3)


def card_at(plan, t):
    """(index, card) of the plan card up at t seconds (its own lane first), else (None, None)."""
    up = [(i, c) for i, c in enumerate(plan["cards"]) if c["start"] <= t < c["end"]]
    up.sort(key=lambda ic: ic[1].get("lane") == "logo")
    return up[0] if up else (None, None)


def frames_at(plan, specs):
    """--at specs -> {still name: frame}. '15.4' is one still; '13-15.5' is five across the range
    (entrance, landing, middle, late, exit), the frames a moving card is judged on."""
    fps, last, out = plan["fps"], plan["durationInFrames"] - 1, {}
    for spec in specs:
        a, _, b = spec.partition("-")
        ts = [secs(a)] if not b else [secs(a) + (secs(b) - secs(a)) * k for k in (0.04, 0.25, 0.5, 0.75, 0.96)]
        for t in ts:
            out[f"t{t:07.2f}"] = min(last, max(0, round(t * fps)))
    return out


def at_labels(plan, frames):
    """still name -> 'card 1 logo 'Duolingo'  15.40s' (card N = plan.cards[N], the review page's index)."""
    sys.path.insert(0, str(Path(__file__).parent))
    from sheet import kind
    out = {}
    for name, f in sorted(frames.items(), key=lambda kv: kv[1]):
        t = f / plan["fps"]
        i, c = card_at(plan, t)
        out[name] = f"{t:.2f}s" + (f"  card {i} {kind(c)} '{c.get('trigger_word', '')}'" if c else "")
    return out


# A patch render re-renders only where the plan changed and splices those frames into the last render.
PATCH_PAD_S = 0.5        # each changed span grows this much both ways: an exit or a cue tail
PATCH_MAX_SHARE = 0.6    # more of the video than this changed: a full render is as quick
SFX_TAIL_S = 1.5         # ponytail: the longest cue in the sfx.py kit; read each cue's length if the kit grows
RANGED = ("cards", "zooms", "sfx", "cutouts")


def changed_ranges(old, new):
    """([[a, b], ...] seconds where new differs from old, why). ranges is None when the change is not
    local (size, look, motion, caption style, music...): that needs a full render."""
    for k in sorted(set(old) | set(new)):
        if k not in RANGED + ("captions",) and old.get(k) != new.get(k):
            return None, k
    oc, nc = old.get("captions") or {}, new.get("captions") or {}
    if {k: v for k, v in oc.items() if k != "chunks"} != {k: v for k, v in nc.items() if k != "chunks"}:
        return None, "captions style"
    fps, dur = new["fps"], new["durationInFrames"] / new["fps"]

    def span(x):
        if "start" in x:
            return x["start"], x["end"]
        if "from" in x:
            return x["from"] / fps, (x["to"] + 1) / fps
        return x["t"], x["t"] + SFX_TAIL_S
    spans = []
    for a, b in [(old.get(k) or [], new.get(k) or []) for k in RANGED] + [(oc.get("chunks") or [], nc.get("chunks") or [])]:
        ka, kb = ({json.dumps(x, sort_keys=True) for x in xs} for xs in (a, b))
        spans += [span(x) for x in a + b if json.dumps(x, sort_keys=True) not in ka & kb]
    out = []
    for s, e in sorted((max(0.0, s - PATCH_PAD_S), min(dur, e + PATCH_PAD_S)) for s, e in spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [[round(s, 3), round(e, 3)] for s, e in out], None


def splice(old, pieces, out, fps, frames):
    """The last render with each piece (from_frame, to_frame inclusive, file) laid in. The picture is one
    encode; the sound is cut as raw 48 kHz samples, as JOIN does, so the voice never moves by a sample
    (check.py's cue check subtracts the cut from the render, sample by sample). Frame times are whole
    milliseconds, as Remotion writes them, so a check that seeks to a time lands on the same frame."""
    from fractions import Fraction
    sr, rate = 48000, Fraction(fps).limit_denominator(1001)
    segs, cur, inputs = [], 0, ["-i", str(old)]
    for i, (a, b, f) in enumerate(pieces, 1):
        inputs += ["-i", str(f)]
        if a > cur:
            segs.append((0, cur, a))
        segs.append((i, a, b + 1))
        cur = b + 1
    if cur < frames:
        segs.append((0, cur, frames))
    smp = lambda fr: round(fr * sr / fps)
    raw = lambda f: subprocess.run(["ffmpeg", "-v", "error", "-i", str(f), "-map", "0:a", "-f", "s16le", "-ac", "2",
                                    "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    srcs = [raw(old)] + [raw(f) for _, _, f in pieces]
    pcm = Path(out).with_suffix(".pcm")
    with open(pcm, "wb") as w:
        for i, a, b in segs:
            n = 4 * (smp(b) - smp(a))
            w.write((srcs[0][4 * smp(a):4 * smp(b)] if i == 0 else srcs[i][:n]).ljust(n, b"\0"))
    fl = [f"[0:v]trim=start_frame={a}:end_frame={b},setpts=PTS-STARTPTS[v{n}]" if i == 0 else
          f"[{i}:v]trim=end_frame={b - a},setpts=PTS-STARTPTS[v{n}]" for n, (i, a, b) in enumerate(segs)]
    fl.append("".join(f"[v{n}]" for n in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=0[v]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-f", "s16le", "-ar", str(sr), "-ac", "2", "-i", str(pcm),
                    "-filter_complex", ";".join(fl), "-map", "[v]", "-map", f"{len(pieces) + 1}:a", "-r", str(rate),
                    "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                    "-video_track_timescale", "1000", "-movflags", "+faststart", str(out)], check=True)
    pcm.unlink()


def probe_render(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,nb_frames",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    return s["width"], s["height"], int(s.get("nb_frames") or 0)


def patch(edit, plan_path, plan, pub, tag, ranges=None, run=None, bundle_to=None):
    """Re-render only the moments that changed since the last render, then splice them in."""
    out = edit / f"render{tag}.mp4"
    snap = out.with_suffix(".plan.json")
    if not out.exists():
        sys.exit(f"ERROR: {out} missing: render in full first (edit.py render {edit})")
    if ranges:
        spans = [[secs(a), secs(b)] for a, _, b in (r.partition("-") for r in ranges)]
    elif snap.exists():
        spans, why = changed_ranges(json.loads(snap.read_text(encoding="utf-8")), plan)
        if spans is None:
            sys.exit(f"the change is not local ({why} changed): render in full (edit.py render {edit})")
        if not spans:
            print(f"nothing changed since {out.name} was rendered")
            return
    else:
        sys.exit(f"ERROR: no {snap.name} (the plan {out.name} was made from): pass --range A-B or render in full")
    w, h, n = probe_render(out)
    fps, frames = plan["fps"], plan["durationInFrames"]
    if (w, h) != (plan["width"], plan["height"]) or abs(n - frames) > 1:
        sys.exit(f"the plan is {plan['width']}x{plan['height']}, {frames} frames; {out.name} is {w}x{h}, {n}: render in full")
    pieces = [(max(0, math.floor(a * fps)), min(frames - 1, math.ceil(b * fps))) for a, b in spans]
    todo = sum(b - a + 1 for a, b in pieces)
    print("patching " + ", ".join(f"{a / fps:.2f}-{(b + 1) / fps:.2f} s" for a, b in pieces)
          + f": {todo} of {frames} frames", flush=True)
    if todo > PATCH_MAX_SHARE * frames:
        print("most of the video changed: rendering in full instead", flush=True)
        render_laptop(edit, plan_path, pub, out, False, run=run)
        shutil.copy2(plan_path, snap)
        return
    t0, tmp = time.time(), edit / f".patch{tag}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    bundle = tmp / "bundle"
    (bundle_to or (lambda a, b: node("bundle", a, b)))(pub, bundle)
    log, stall = out.parent / f"{out.stem}.renderer.log", stall_s(0.3)
    files = []
    for k, (a, b) in enumerate(pieces):
        f = tmp / f"piece-{k}.mkv"
        r = (run or watch)(["node", str(REMOTION / "render.mjs"), "chunk", str(bundle), str(plan_path), str(f), str(a), str(b)],
                           log, stall, cwd=REMOTION, env=aws_env())
        if r:
            render_failed("stalled" if r == STALLED else r, log, edit)
        files.append((a, b, f))
    splice(out, files, tmp / "render.mp4", fps, frames)
    os.replace(tmp / "render.mp4", out)
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copy2(plan_path, snap)
    print(f"patched {out} in {time.time() - t0:.0f} s ({len(pieces)} piece{'s' * (len(pieces) > 1)})")


def demo_patch():
    """stills --at and patch: the moments asked for, the spans that changed, the splice, end to end."""
    import tempfile
    assert secs("15.4") == 15.4 and secs("0:15") == 15 and secs("1:02.5s") == 62.5
    plan = {"fps": 30, "durationInFrames": 300, "width": 64, "height": 36, "look": {}, "captions": {"style": {}, "chunks": []},
            "zooms": [], "sfx": [], "cards": [{"start": 2, "end": 4, "lane": "logo", "trigger_word": "duo", "anim": {"type": "logo"}},
                                               {"start": 3, "end": 6, "src": "images/capture-a.png", "trigger_word": "repo"}]}
    f = frames_at(plan, ["0:03", "4-6"])
    assert f == {"t0003.00": 90, "t0004.08": 122, "t0004.50": 135, "t0005.00": 150, "t0005.50": 165, "t0005.92": 178}, f
    lab = at_labels(plan, f)
    assert lab["t0003.00"] == "3.00s  card 1 capture 'repo'" and lab["t0004.08"] == "4.07s  card 1 capture 'repo'", lab
    assert card_at(plan, 2.5)[0] == 0 and card_at(plan, 7) == (None, None)
    # what changed: a moved card is its old and new spans, padded and merged; a new look is a full render
    new = json.loads(json.dumps(plan))
    new["cards"][0]["box"] = [40, 17, 20, 11]
    assert changed_ranges(plan, new) == ([[1.5, 4.5]], None)
    assert changed_ranges(plan, plan) == ([], None)
    new["sfx"] = [{"t": 8.0, "src": ".sfx/pop.wav"}]
    new["zooms"] = [{"start": 9.0, "end": 9.4}]
    assert changed_ranges(plan, new)[0] == [[1.5, 4.5], [7.5, 10.0]], changed_ranges(plan, new)
    assert changed_ranges(plan, {**new, "look": {"preset": "mono"}}) == (None, "look")
    assert changed_ranges(plan, {**new, "captions": {"style": {"size_pct": 7}, "chunks": []}}) == (None, "captions style")
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        mk = lambda out, color, n, ext: subprocess.run(   # n frames at 29.97, a 440 Hz tone under them
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=64x36:r=30000/1001:d={n / 29 + 1}", "-f", "lavfi",
             "-i", f"sine=f=440:d={n * 1001 / 30000}:r=48000", "-frames:v", str(n), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac" if ext == "mp4" else "pcm_s16le", str(out)], check=True)
        mk(t / "render.mp4", "red", 300, "mp4")
        plan["fps"] = 30000 / 1001
        (t / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        # no record of the rendered plan: patch asks for a range
        try:
            patch(t, t / "plan.json", plan, t, "")
            raise AssertionError("no exit")
        except SystemExit as e:
            assert "--range" in str(e.code), e.code
        (t / "render.plan.json").write_text(json.dumps(plan), encoding="utf-8")
        moved = json.loads(json.dumps(plan))
        moved["cards"][0]["box"] = [40, 17, 20, 11]
        (t / "plan.json").write_text(json.dumps(moved), encoding="utf-8")
        asked = []

        def fake(cmd, log, stall, **k):
            a, b = int(cmd[-2]), int(cmd[-1])
            asked.append((a, b))
            mk(Path(cmd[-3]), "blue", b - a + 1, "mkv")
            return 0
        patch(t, t / "plan.json", moved, t, "", run=fake, bundle_to=lambda a, b: None)
        assert asked == [(44, 135)], asked          # 1.5-4.5 s at 29.97 fps
        assert json.loads((t / "render.plan.json").read_text(encoding="utf-8")) == moved
        n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(t / "render.mp4")], capture_output=True, text=True).stdout
        assert int(n) == 300, n
        px = lambda fr: subprocess.run(["ffmpeg", "-v", "error", "-i", str(t / "render.mp4"), "-vf", f"select=eq(n\\,{fr})",
                                        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout[:3]
        assert px(20)[0] > 200 and px(90)[2] > 200 and px(200)[0] > 200, (px(20), px(90), px(200))
        d = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration",
                                  "-of", "csv=p=0", str(t / "render.mp4")], capture_output=True, text=True).stdout)
        assert abs(d - 300 * 1001 / 30000) < 0.03, d
        patch(t, t / "plan.json", moved, t, "", run=fake, bundle_to=lambda a, b: None)   # nothing changed: nothing rendered
        assert len(asked) == 1


def demo():
    import tempfile
    demo_patch()
    # the laptop estimate: Chrome's start-up once, then every frame; every cloud line says when it is not set up
    assert laptop_s({"s_per_frame": 0.05, "bundle_s": 3.0, "start_s": 2.0}, 1000) == 55.0
    assert laptop_s({"s_per_frame": 0.05, "bundle_s": 3.0}, 1000) == 53.0
    with tempfile.TemporaryDirectory() as d:
        assert not aws_ready({}, d) and aws_ready({"AWS_PROFILE": "x"}, d)
        (Path(d) / ".aws").mkdir()
        (Path(d) / ".aws" / "credentials").write_text("", encoding="utf-8")
        assert aws_ready({}, d)
    assert not_set_up(True, "x") == "" and "Lambda section" in not_set_up(False, "Lambda section")
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
    import tempfile, zipfile
    with tempfile.TemporaryDirectory() as t:
        edit, pub = Path(t) / "fake", Path(t) / "fake" / ".render"
        (pub / "images").mkdir(parents=True)
        (pub / "cut.mp4").write_bytes(b"x" * 100)
        (pub / "images" / "a.png").write_bytes(b"png")
        (edit / "plan.json").write_text('{"video": "cut.mp4"}', encoding="utf-8")
        repo, z = package_github(edit, edit / "plan.json", pub, "")
        for f in (".github/workflows/render.yml", "plan.json", "package.json", "render.mjs", "src/index.ts"):
            assert (repo / f).exists(), f
        assert not list(repo.rglob("*.mp4")), "footage leaked into the git folder"
        assert set(zipfile.ZipFile(z).namelist()) >= {"cut.mp4", "images/a.png"}, zipfile.ZipFile(z).namelist()
        # an unchanged renderer file is never rewritten (parallel stills bundle it); a changed one is
        a, b = Path(t) / "a.ts", Path(t) / "b.ts"
        a.write_text("same", encoding="utf-8"), b.write_text("same", encoding="utf-8")
        ino = b.stat().st_ino
        copy_changed(a, b)
        assert b.stat().st_ino == ino, "an unchanged file was rewritten"
        a.write_text("new", encoding="utf-8")
        copy_changed(a, b)
        assert b.read_text(encoding="utf-8") == "new" and not list(Path(t).glob("b.ts.*.tmp"))
        # the renderer copy is exact: a component deleted upstream leaves the user's copy too
        up, mine = Path(t) / "up", Path(t) / "mine"
        (up / "keep").mkdir(parents=True), (mine / "old").mkdir(parents=True)
        (up / "keep" / "A.tsx").write_text("a", encoding="utf-8"), (mine / "Gone.tsx").write_text("x", encoding="utf-8"), (mine / "old" / "B.tsx").write_text("b", encoding="utf-8")
        (Path(t) / "outside.txt").write_text("user", encoding="utf-8")
        mirror(up, mine)
        assert sorted(p.relative_to(mine).as_posix() for p in mine.rglob("*")) == ["keep", "keep/A.tsx"], list(mine.rglob("*"))
        assert (Path(t) / "outside.txt").exists()
        wf = (repo / ".github/workflows/render.yml").read_text(encoding="utf-8")
        assert "-p 'github-render-media.zip*'" in wf
        for job in ("  plan:", "  render:", "  join:", "name: render\n", "render.mjs chunk", '"concat"'):
            assert job in wf, job
        # the plan job's own script gives the same chunks as chunk_ranges
        (repo / "plan.json").write_text('{"durationInFrames": 72000, "fps": 30}', encoding="utf-8")
        py = re.search(r"<<'EOF' >> \"\$GITHUB_OUTPUT\"\n(.*?)\n\s*EOF", wf, re.S).group(1)
        out = subprocess.run([sys.executable, "-c", textwrap.dedent(py)], cwd=repo, capture_output=True, text=True, check=True).stdout
        got = json.loads(out.splitlines()[0].partition("=")[2])
        assert out.splitlines()[1] == "fps=30", out
        assert [[c["from"], c["to"]] for c in got] == chunk_ranges(72000, 30) and got[-1]["i"] == "19", got[-1]
        big = Path(t) / "big.zip"
        big.write_bytes(bytes(range(256)) * 10)
        split_file(big, 1000)
        assert [p.name for p in media_files(big)] == ["big.zip.part-00", "big.zip.part-01", "big.zip.part-02"]
        assert b"".join(p.read_bytes() for p in media_files(big)) == bytes(range(256)) * 10
    # git pushes use the gh login in the render repo only: the user's global credential helper is never rewritten
    assert "setup-git" not in inspect.getsource(github_push)
    assert GIT_CREDENTIAL and all(c[:2] == ["config", "--local"] for c in GIT_CREDENTIAL), GIT_CREDENTIAL
    # after a downloaded render the footage leaves GitHub: the media release and the run's artifacts, nothing else
    assert "retention-days: 7" not in WORKFLOW and WORKFLOW.count("retention-days: 1") == 2
    calls = []

    def fake_gh(*args, check=True, cwd=None):
        calls.append(args)
        out = '{"artifacts": [{"id": 11, "name": "render"}, {"id": 12, "name": "chunk-00"}]}' if args[:1] == ("api",) and "-X" not in args else ""
        return subprocess.CompletedProcess(args, 0, out, "")
    github_cleanup("me/video-x", "99", fake_gh)
    assert ("release", "delete", "media", "-y", "--cleanup-tag", "-R", "me/video-x") in calls, calls
    assert {c[-1] for c in calls if "DELETE" in c} == {"repos/me/video-x/actions/artifacts/11", "repos/me/video-x/actions/artifacts/12"}, calls
    assert not any("repo" in c[:1] or "delete" == c[0] for c in calls), "never the repo itself"
    assert chunk_ranges(1326, 30) == [[0, 1325]]
    r = chunk_ranges(40 * 60 * 30, 30)
    assert len(r) == 20 and r[0] == [0, 3599] and r[-1][1] == 71999, r
    assert len(chunk_ranges(3 * 3600 * 30, 30)) == 20                       # capped
    assert all(b - a + 1 > 0 for a, b in chunk_ranges(9, 1))
    assert "1 runner," in github_estimate(1326, 30, 34e6) and "fits one" in github_estimate(1326, 30, 34e6)
    assert "20 runners" in github_estimate(72000, 30, 5e9) and "3 parts" in github_estimate(72000, 30, 5e9)
    # Modal: containers from the work (the billed boot stays under 20% of each one's bill), three
    # pieces each from a shared queue, every frame once and in order, capped
    assert modal_plan(6167, 0.345) == (18, modal_plan(6167, 0.345)[1]) and len(modal_plan(6167, 0.345)[1]) == 54
    assert modal_plan(1326, 0.345)[0] == 3 and len(modal_plan(1326, 0.345)[1]) == 9
    assert modal_plan(100, 0.345) == (1, [[0, 99]])
    assert modal_plan(3 * 3600 * 30, 0.345)[0] == MODAL_MAX_CONTAINERS
    assert [f for a, b in modal_plan(9999, 0.05)[1] for f in range(a, b + 1)] == list(range(9999))
    # the bill for the sample take on 19 containers (1865 container-seconds of render) was $0.181
    assert abs(modal_cost(1865, 19) - 0.181) < 0.01, modal_cost(1865, 19)
    # the estimate is upload + start + the work on n containers times the straggle factor + the tail
    m = {"s_per_frame": 0.3, "start_s": 10, "straggle": 1.5, "tail_s": 20, "up_bytes_s": 4e6}
    wall, usd, n, _ = modal_estimate(6000, 140e6, m)
    assert n == 15 and abs(wall - (35 + 10 + 1800 / 15 * 1.5 + 20)) < 1e-6 and abs(usd - modal_cost(1800, 15)) < 1e-9, (wall, n)
    # footage Modal already holds (asked by hash, nothing sent) is not counted as upload time
    said = lambda out: lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out)
    assert modal_upload_bytes("pub", 140e6, run=said('{"to_upload": 0}\n'), ready=lambda: True) == 0
    assert modal_upload_bytes("pub", 140e6, run=said('{"to_upload": 5}\n'), ready=lambda: True) == 5
    assert modal_upload_bytes("pub", 140e6, run=said(""), ready=lambda: True) == 140e6, "no answer: all of it"
    assert modal_upload_bytes("pub", 140e6, run=None, ready=lambda: False) == 140e6, "Modal not set up"
    # the estimate says when its speed is another video's (the real-footage test read "speed from the last
    # render of pod-clip1" as if it were this video's)
    assert "another video (pod-clip1)" in speed_note({"source": "render of pod-clip1"}, "raw-take")
    assert speed_note({"source": "render of raw-take"}, "raw-take") == "speed from this video's last render"
    assert "rough guess" in speed_note({"source": "benchmark"}, "x")
    # the stall watchdog: a renderer that prints one frame and then hangs (the 25 min hang at 0% CPU) is
    # stopped after `stall` seconds with no new frame; one that keeps printing frames is left alone
    with tempfile.TemporaryDirectory() as t:
        log = Path(t) / "r.log"
        hang = [sys.executable, "-c", "import time; print('Rendered 1/10', flush=True); time.sleep(60)"]
        t0 = time.time()
        assert watch(hang, log, 1.0, start=0, echo=False) == STALLED and time.time() - t0 < 10
        assert "Rendered 1/10" in log.read_text(encoding="utf-8") and "stopped" in log.read_text(encoding="utf-8")
        steady = [sys.executable, "-c", "import time\nfor i in range(6): print(f'Rendered {i}/6', flush=True); time.sleep(0.4)"]
        assert watch(steady, log, 1.0, start=0, echo=False) == 0
        assert watch([sys.executable, "-c", "import sys; sys.exit(3)"], log, 5, echo=False) == 3
        assert stall_s(0.03) == STALL_MIN_S and stall_s(2.0) == 400
        # a stall goes to the 200-frame pieces; a failure is one short message naming the log, not a traceback
        (Path(t) / "plan.json").write_text('{"durationInFrames": 450, "fps": 30}', encoding="utf-8")
        went = []
        render_laptop(Path(t), Path(t) / "plan.json", Path(t), Path(t) / "render.mp4", False,
                      run=lambda *a, **k: STALLED, chunks=lambda *a: went.append(a))
        assert went and went[0][-1] >= STALL_MIN_S, went
        Path(t, "render.renderer.log").write_text("Rendered 3/450\nError: Request closed\n    at x (y.js:1)\n", encoding="utf-8")
        try:
            render_failed(1, Path(t) / "render.renderer.log", Path(t))
            raise AssertionError("no exit")
        except SystemExit as e:
            msg = str(e.code)
        assert "render.renderer.log" in msg and "Error: Request closed" in msg and "Next:" in msg and "at x" not in msg, msg
        # the fallback, end to end with a fake renderer: 450 frames in pieces 0-199, 200-399, 400-449 (each
        # piece's first try stalls, its retry works), joined by JOIN into one file of every frame
        tries = []

        def fake(cmd, log, stall, **k):
            a, b = int(cmd[-2]), int(cmd[-1])
            tries.append((a, b))
            if tries.count((a, b)) == 1:
                return STALLED
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=s=64x36:r=30:d={(b - a + 1) / 30}",
                            "-f", "lavfi", "-i", f"sine=d={(b - a + 1) / 30 + 0.01}:r=48000", "-c:v", "libx264",
                            "-c:a", "pcm_s16le", "-shortest", cmd[5]], check=True)
            return 0
        out = Path(t) / "render.mp4"
        render_chunks(Path(t), Path(t) / "plan.json", Path(t), out, False, Path(t) / "c.log", 1, run=fake,
                      bundle_to=lambda a, b: None)
        assert sorted(set(tries)) == [(0, 199), (200, 399), (400, 449)] and len(tries) == 6, tries
        n = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                            "stream=nb_read_frames", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
        assert int(n) == 450 and not (Path(t) / ".render-chunks").exists(), n
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["stills", "estimate", "render", "patch", "github-push", "github-fetch"])
    ap.add_argument("edit")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--lambda", dest="use_lambda", action="store_true")
    ap.add_argument("--modal", action="store_true", help="render on Modal (modal.com)")
    ap.add_argument("--draft", action="store_true", help="laptop render at 2/3 size, to render-draft.mp4")
    ap.add_argument("--github", action="store_true", help="package for GitHub Actions instead of rendering here")
    ap.add_argument("--repo", help="GitHub repo name (github-push, github-fetch)")
    ap.add_argument("--no-check", action="store_true", help="stills even when check.py plan finds a FAIL")
    ap.add_argument("--at", action="append", help="stills: only this moment (15.4 or 0:15) or range (13-15.5, five stills)")
    ap.add_argument("--range", action="append", help="patch: re-render this span (13-15.5) instead of what changed")
    a = ap.parse_args()
    edit = Path(a.edit).resolve()
    plan_path = edit / a.plan
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    tag = plan_path.stem[len("plan"):]
    if a.cmd.startswith("github-"):
        if not a.repo:
            sys.exit("ERROR: --repo NAME is required")
        return (github_push if a.cmd == "github-push" else github_fetch)(edit, a.repo, tag)
    sync_renderer()
    pub = prepare_public(edit, plan, tag)
    if a.cmd == "stills":
        # check.py plan first: prints what it finds, stops the stills only on a FAIL
        chk = subprocess.run([sys.executable, str(Path(__file__).parent / "check.py"), "plan", str(edit), "--plan", a.plan])
        if chk.returncode and not a.no_check:
            sys.exit("check.py plan found a FAIL: fix it and plan again (edit.py stills --no-check to look anyway)")
        if a.at:   # just these moments, into stills-at/ (the full sheet stays as it was)
            frames, folder = frames_at(plan, a.at), edit / f"stills{tag}-at"
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir()
            (folder / "labels.json").write_text(json.dumps(at_labels(plan, frames)), encoding="utf-8")
        else:
            frames, folder = still_frames(plan), edit / f"stills{tag}"
        node("stills", pub, plan_path, folder, *[f"{k}={v}" for k, v in frames.items()])
        contact_sheet(edit, a.plan, folder.name if a.at else None)
    elif a.cmd == "estimate":
        estimate(plan_path, pub)
    elif a.cmd == "patch":
        patch(edit, plan_path, plan, pub, tag, a.range)
    elif a.github:
        package_github(edit, plan_path, pub, tag)
    elif a.use_lambda:
        node("lambda", pub, plan_path, edit / f"render{tag}.mp4", re.sub(r"[^a-z0-9-]+", "-", f"ai-editor-{edit.name}{tag}".lower()),
             *(["--cleanup"] if cloud_cleanup() else []))
    elif a.modal:
        if not modal_ready():
            sys.exit("Modal is not set up on this computer: run the setup skill's Modal step first.")
        render_modal(edit, plan_path, pub, edit / f"render{tag}.mp4")
    else:
        render_laptop(edit, plan_path, pub, edit / f"render{tag}{'-draft' if a.draft else ''}.mp4", a.draft)
    if a.cmd == "render" and not (a.draft or a.github):   # the plan this render was made from: patch diffs against it
        shutil.copy2(plan_path, edit / f"render{tag}.plan.json")


if __name__ == "__main__":
    main()
