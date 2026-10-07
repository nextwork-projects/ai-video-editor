#!/usr/bin/env python3
"""Render a plan on Modal (modal.com): the bundle goes up once, chunks of frames render in parallel,
the pieces come back and join on this computer with the GitHub Actions join (edit.py JOIN).

Runs in the editor venv, where `setup.py modal` installs the modal package. edit.py calls it:

    ~/.ai-video-editor/venv/bin/python modal_render.py render <bundleDir> <plan.json> <out.mp4>
    ~/.ai-video-editor/venv/bin/python modal_render.py hello      one tiny function call: proves the login works
    ~/.ai-video-editor/venv/bin/python modal_render.py demo       self-check, no account needed

`render` prints one JSON line last: wall_s, chunks, cpu_s, usd. edit.py stores it in
~/.ai-video-editor/modal.json, which the next estimate reads.
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import modal

if modal.is_local():
    # Sizes, rates, chunking and the estimate live in edit.py (stdlib, so `edit.py estimate` works
    # without modal installed).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from edit import (HOME, JOIN, MODAL_CPU as CPU, MODAL_MAX_CONTAINERS, MODAL_MEM_MB as MEM_MB,
                      modal_cost as cost, modal_ranges as ranges, modal_speed as speed)
    REMOTION = HOME / "remotion"
else:   # inside a container only render_chunk runs, and it needs none of that
    CPU = MEM_MB = MODAL_MAX_CONTAINERS = None
    REMOTION = Path("/r")

# Remotion's Debian list (remotion.dev/docs/miscellaneous/linux-dependencies) for Chrome Headless Shell.
CHROME_DEPS = ["libnss3", "libdbus-1-3", "libatk1.0-0", "libasound2", "libxrandr2", "libxkbcommon-dev",
               "libxfixes3", "libxcomposite1", "libxdamage1", "libgbm-dev", "libcups2", "libcairo2",
               "libpango-1.0-0", "libatk-bridge2.0-0"]

# Built once in the user's Modal account and cached: Node 22, the renderer's npm packages at the
# laptop's exact versions (package-lock.json), Chrome Headless Shell. A plugin update that changes
# package.json rebuilds it.
image = (modal.Image.debian_slim(python_version="3.12")
         .apt_install("ca-certificates", "curl", "gnupg", *CHROME_DEPS)
         .run_commands(  # NodeSource's signed apt source, not its setup script piped to a root shell
             "mkdir -p /etc/apt/keyrings && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key"
             " | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg",
             'echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main"'
             " > /etc/apt/sources.list.d/nodesource.list",
             "apt-get update && apt-get install -y nodejs")
         .add_local_file(REMOTION / "package.json", "/r/package.json", copy=True)
         .add_local_file(REMOTION / "package-lock.json", "/r/package-lock.json", copy=True)
         .run_commands("cd /r && npm ci --no-audit --no-fund && npx remotion browser ensure")
         .add_local_file(REMOTION / "render.mjs", "/r/render.mjs"))
vol = modal.Volume.from_name("ai-video-editor-renders", create_if_missing=True)
VOL_DIR, RENDER_MJS = "/vol", "/r/render.mjs"     # where the container sees them (demo points them here)
app = modal.App("ai-video-editor")


@app.function(image=image, volumes={"/vol": vol}, cpu=CPU, memory=MEM_MB, timeout=1800, retries=1,
              max_containers=MODAL_MAX_CONTAINERS)
def render_chunk(job, i, a, b, concurrency):
    import resource
    t0, ru0 = time.time(), resource.getrusage(resource.RUSAGE_CHILDREN)
    out = f"{VOL_DIR}/{job}/chunks/chunk-{i:02d}.mkv"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run(["node", RENDER_MJS, "chunk", f"{VOL_DIR}/{job}/bundle", f"{VOL_DIR}/{job}/plan.json", out,
                        str(a), str(b), f"--concurrency={concurrency}"], cwd=os.path.dirname(RENDER_MJS),
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"chunk {i} (frames {a}-{b}) failed:\n{r.stderr[-3000:]}")
    vol.commit()
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)     # a reused container counts from its first input
    cpu = ru.ru_utime + ru.ru_stime - ru0.ru_utime - ru0.ru_stime
    return {"i": i, "frames": b - a + 1, "wall_s": time.time() - t0, "cpu_s": cpu}


@app.function(image=modal.Image.debian_slim(), timeout=120)
def hello():
    return "modal ok"


def join(chunk_dir, chunks, fps, out):
    """edit.py's GitHub Actions join, run here on the downloaded pieces."""
    work = Path(chunk_dir).parent
    env = dict(os.environ, FPS=str(fps), CHUNKS=json.dumps(chunks))
    subprocess.run([sys.executable, "-c", JOIN], cwd=work, env=env, check=True)
    os.replace(work / "out" / "render.mp4", out)


def render(bundle_dir, plan_path, out):
    plan = json.loads(Path(plan_path).read_text())
    frames, fps = plan["durationInFrames"], plan["fps"]
    r = ranges(frames, speed()[0])
    job = uuid.uuid4().hex[:12]
    t0 = time.time()
    with modal.enable_output(), app.run():
        print(f"uploading {bundle_dir} ({sum(f.stat().st_size for f in Path(bundle_dir).rglob('*') if f.is_file()) / 1e6:.0f} MB)", flush=True)
        with vol.batch_upload(force=True) as up:
            up.put_directory(str(bundle_dir), f"/{job}/bundle")
            up.put_file(str(plan_path), f"/{job}/plan.json")
        t_up = time.time() - t0
        print(f"rendering {frames} frames on {len(r)} container{'s' * (len(r) > 1)}", flush=True)
        try:
            done = list(render_chunk.starmap([(job, i, a, b, CPU * 2) for i, (a, b) in enumerate(r)]))
            with tempfile.TemporaryDirectory() as t:
                cdir = Path(t) / "chunks"
                cdir.mkdir()
                for c in done:
                    with open(cdir / f"chunk-{c['i']:02d}.mkv", "wb") as f:
                        vol.read_file_into_fileobj(f"/{job}/chunks/chunk-{c['i']:02d}.mkv", f)
                join(cdir, [{"i": f"{i:02d}", "from": a, "to": b} for i, (a, b) in enumerate(r)], fps, out)
        finally:
            vol.remove_file(f"/{job}", recursive=True)
    wall = time.time() - t0
    usd = cost(done)
    # Container seconds per frame (Chrome launch included), and everything else past the upload and
    # the longest container: boot, download, join.
    spf_m = sum(c["wall_s"] for c in done) / frames
    longest = max(done, key=lambda c: c["wall_s"])
    res = {"wall_s": round(wall, 1), "upload_s": round(t_up, 1), "chunks": len(done), "frames": frames,
           "cpu_s": round(sum(c["cpu_s"] for c in done), 1), "usd": round(usd, 4),
           "s_per_frame": round(spf_m, 4),
           "startup_s": round(max(0.0, wall - t_up - longest["wall_s"]), 1)}
    print(f"rendered {out} in {wall:.1f} s on {len(done)} containers; about ${usd:.3f} at Modal's rates "
          f"(the Modal dashboard has the exact bill)")
    print(json.dumps(res))


def demo():
    """No account needed. Always: the app, image and functions are defined. With a bundle, plan and
    output path: render() end to end with Modal faked, so the real upload calls, the real container
    body (render_chunk run here with .local) and the real join all run, in three pieces."""
    assert render_chunk and hello and image
    if len(sys.argv) > 2:
        mocked_render(*sys.argv[2:5])
    print("demo ok")


class FakeVolume:
    """The Volume calls render() and render_chunk make, on a local folder."""
    def __init__(self, root):
        self.root = Path(root)

    def _p(self, p):
        return self.root / p.lstrip("/")

    def batch_upload(self, force=False):
        import contextlib
        return contextlib.nullcontext(self)

    def put_directory(self, src, dst):
        import shutil
        shutil.copytree(src, self._p(dst))

    def put_file(self, src, dst):
        self._p(dst).parent.mkdir(parents=True, exist_ok=True)
        self._p(dst).write_bytes(Path(src).read_bytes())

    def read_file_into_fileobj(self, p, f):
        return f.write(self._p(p).read_bytes())

    def remove_file(self, p, recursive=False):
        import shutil
        shutil.rmtree(self._p(p))

    def commit(self):
        pass


def mocked_render(bundle_dir, plan_path, out):
    import contextlib
    g = globals()
    body = render_chunk.local
    third = lambda n, spf: [[a, min(n, a + math.ceil(n / 3)) - 1] for a in range(0, n, math.ceil(n / 3))]
    with tempfile.TemporaryDirectory() as t:
        saved = {k: g[k] for k in ("vol", "VOL_DIR", "RENDER_MJS", "app", "render_chunk", "ranges")}
        saved_out = modal.enable_output
        try:
            g.update(vol=FakeVolume(t), VOL_DIR=t, RENDER_MJS=str(REMOTION / "render.mjs"), ranges=third,
                     app=type("A", (), {"run": lambda self: contextlib.nullcontext()})(),
                     render_chunk=type("F", (), {"starmap": lambda self, xs: [body(*x) for x in xs]})())
            modal.enable_output = contextlib.nullcontext
            render(bundle_dir, plan_path, out)
            assert not any(Path(t).iterdir()), "the render's folder was left on the volume"
        finally:
            g.update(saved)
            modal.enable_output = saved_out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "render" and len(sys.argv) == 5:
        render(*sys.argv[2:5])
    elif cmd == "hello":
        with app.run():
            print(hello.remote())
    elif cmd == "demo":
        demo()
    else:
        sys.exit(__doc__)
