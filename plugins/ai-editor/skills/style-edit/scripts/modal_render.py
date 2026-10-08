#!/usr/bin/env python3
"""Render a plan on Modal (modal.com): the bundle goes up once, chunks of frames render in parallel,
the pieces come back and join on this computer with the GitHub Actions join (edit.py JOIN).

Runs in the editor venv, where `setup.py modal` installs the modal package. edit.py calls it:

    ~/.ai-video-editor/venv/bin/python modal_render.py render <bundleDir> <plan.json> <out.mp4>
    ~/.ai-video-editor/venv/bin/python modal_render.py held <publicDir>   footage bytes Modal does not hold yet
    ~/.ai-video-editor/venv/bin/python modal_render.py hello      one tiny function call: proves the login works
    ~/.ai-video-editor/venv/bin/python modal_render.py demo       self-check, no account needed

`render` prints one JSON line last: wall_s, chunks, cpu_s, usd. edit.py stores it in
~/.ai-video-editor/modal.json, which the next estimate reads.
"""
import contextlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from concurrent import futures
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import modal

BOOT = time.time()      # in a container: when it imported this file, so its start-up is measurable

if modal.is_local():
    # Sizes, rates, chunking and the estimate live in edit.py (stdlib, so `edit.py estimate` works
    # without modal installed).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from edit import (HOME, JOIN, MODAL_CPU as CPU, MODAL_MAX_CONTAINERS, MODAL_MEM_MB as MEM_MB,
                      modal_cost as cost, modal_plan as plan_pieces, modal_speed as speed)
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
VOL_NAME = "ai-video-editor-renders"
vol = modal.Volume.from_name(VOL_NAME, create_if_missing=True)
VOL_DIR, RENDER_MJS = "/vol", "/r/render.mjs"     # where the container sees them (demo points them here)
LOCAL_DIR = tempfile.gettempdir()                 # the container's own disk
HEDGE = 2
# Test only, off by default: "piece:seconds" holds the first copy of that piece in its container, the slow
# container the hedge is for. AI_EDITOR_MODAL_SLOW_PIECE=0:600 edit.py render <edit> --modal
SLOW_PIECE_ENV = "AI_EDITOR_MODAL_SLOW_PIECE"
app = modal.App("ai-video-editor")


@app.function(image=image, volumes={"/vol": vol}, cpu=CPU, memory=MEM_MB, timeout=1800, retries=1,
              max_containers=MODAL_MAX_CONTAINERS, scaledown_window=2)   # Modal's default bills 60 s idle per container
def render_chunk(job, i, a, b, copy=0, delay=0):
    import resource
    t0, ru0 = time.time(), resource.getrusage(resource.RUSAGE_CHILDREN)
    time.sleep(delay)       # a test's slow container (SLOW_PIECE_ENV); 0 otherwise
    bundle = unpack(job)
    out = f"{VOL_DIR}/{job}/chunks/chunk-{i:03d}-{copy}.mkv"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    r = subprocess.run(["node", RENDER_MJS, "chunk", bundle, f"{VOL_DIR}/{job}/plan.json", out,
                        str(a), str(b)], cwd=os.path.dirname(RENDER_MJS),   # render.mjs: one tab per core it sees
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"chunk {i} (frames {a}-{b}) failed:\n{r.stderr[-3000:]}")
    vol.commit()
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)     # a reused container counts from its first input
    cpu = ru.ru_utime + ru.ru_stime - ru0.ru_utime - ru0.ru_stime
    return {"i": i, "frames": b - a + 1, "wall_s": time.time() - t0, "cpu_s": cpu, "boot": BOOT, "t0": t0,
            "copy": copy, "out": out[len(VOL_DIR):]}


def pack(bundle_dir, out):
    """The bundle's code as one tar, byte-identical whenever the code is (no times, owners or source
    maps but the one Remotion opens), so Modal skips it by hash on the next render. One file, not ~3,700: the upload was one
    request per file. The footage goes up beside it on its own, also skipped by hash when unchanged."""
    with tarfile.open(out, "w", format=tarfile.USTAR_FORMAT) as tf:
        for f in sorted(Path(bundle_dir).rglob("*")):
            rel = f.relative_to(bundle_dir)
            if f.is_file() and rel.parts[0] != "public" and (f.suffix != ".map" or f.name == "bundle.js.map"):
                ti = tf.gettarinfo(f, rel.as_posix())
                ti.mtime, ti.uid, ti.gid, ti.uname, ti.gname = 0, 0, 0, "", ""
                with open(f, "rb") as fh:
                    tf.addfile(ti, fh)


def unpack(job):
    """In the container: the code onto local disk once (later pieces on the container reuse it), the
    footage left on the volume and linked in."""
    local = os.path.join(LOCAL_DIR, f"ave-{job}")
    if not os.path.exists(local):
        tmp = f"{local}.{os.getpid()}"
        with tarfile.open(f"{VOL_DIR}/{job}/code.tar") as tf:
            tf.extractall(tmp, filter="data")
        os.symlink(f"{VOL_DIR}/{job}/public", os.path.join(tmp, "public"))
        try:
            os.replace(tmp, local)
        except OSError:     # another piece on this container unpacked it first
            shutil.rmtree(tmp)
    return local


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
    n, r = plan_pieces(frames, speed()[0]["s_per_frame"])
    job = uuid.uuid4().hex[:12]
    slow, slow_s = map(int, os.environ[SLOW_PIECE_ENV].split(":")) if os.environ.get(SLOW_PIECE_ENV) else (-1, 0)
    media = sum(f.stat().st_size for f in Path(bundle_dir, "public").rglob("*") if f.is_file())
    done = []
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as t:
            cdir, code = Path(t) / "chunks", Path(t) / "code.tar"
            cdir.mkdir()
            pack(bundle_dir, code)
            up_bytes = code.stat().st_size + media
            with modal.enable_output(), app.run(), ThreadPoolExecutor(8) as pool:
                print(f"uploading {up_bytes / 1e6:.0f} MB (skipped when Modal already holds it)", flush=True)
                with vol.batch_upload(force=True) as up:
                    up.put_file(str(code), f"/{job}/code.tar")
                    up.put_directory(str(Path(bundle_dir, "public")), f"/{job}/public")
                    up.put_file(str(plan_path), f"/{job}/plan.json")
                t_up = time.time() - t0
                render_chunk.update_autoscaler(max_containers=n)
                print(f"rendering {frames} frames in {len(r)} pieces on {n} container{'s' * (n > 1)}", flush=True)
                t_sub, gets = time.time(), []
                # each piece downloads as soon as it is done, while the others render
                for c in run_pieces(lambda i, a, b, copy: render_chunk.spawn(
                        job, i, a, b, copy, slow_s if (i, copy) == (slow, 0) else 0), r, n):
                    done.append(c)
                    gets.append(pool.submit(fetch, c, cdir))
                t_ren = time.time()
                for g in gets:
                    g.result()
            join(cdir, [{"i": f"{i:03d}", "from": a, "to": b} for i, (a, b) in enumerate(r)], fps, out)
    finally:
        # Only after app.run() has stopped every container: one still running when another chunk
        # failed (or its retry) writes its folder back onto the volume when it exits.
        try:
            vol.remove_file(f"/{job}", recursive=True)
        except Exception as e:      # nothing uploaded yet; never hide the error that got us here
            print(f"could not delete /{job} from the ai-video-editor-renders volume: {e}", file=sys.stderr)
    res = measure(done, frames, t0, t_up, t_sub, t_ren, time.time(), up_bytes)
    print(f"rendered {out} in {res['wall_s']:.1f} s on {res['containers']} containers; about ${res['usd']:.3f} at Modal's "
          f"rates (the Modal dashboard has the exact bill)")
    print(json.dumps(res))


def to_upload(pub):
    """Bytes of the footage Modal does not hold yet. Each file's sha256 is asked of Modal, nothing is
    sent: the upload skips a held file by the same hash. Uses Modal's internal API (modal is pinned in
    setup.py), so a volume of another version, or any error, counts every byte."""
    import asyncio
    import hashlib
    from modal.volume import _Volume
    from modal_proto import api_pb2

    async def ask():
        v = _Volume.from_name(VOL_NAME)
        await v.hydrate()
        if v._metadata.version not in (api_pb2.VOLUME_FS_VERSION_UNSPECIFIED, api_pb2.VOLUME_FS_VERSION_V1):
            raise RuntimeError("not a v1 volume")
        n = 0
        for f in (f for f in Path(pub).rglob("*") if f.is_file()):
            with open(f, "rb") as fh:
                sha = hashlib.file_digest(fh, "sha256").hexdigest()
            r = await v._client._stub.MountPutFile(api_pb2.MountPutFileRequest(sha256_hex=sha))
            n += 0 if r.exists else f.stat().st_size
        return n
    try:
        return asyncio.run(ask())
    except Exception:
        return sum(f.stat().st_size for f in Path(pub).rglob("*") if f.is_file())


def fetch(c, cdir):
    with open(cdir / f"chunk-{c['i']:03d}.mkv", "wb") as f:
        vol.read_file_into_fileobj(c["out"], f)


def run_pieces(spawn, r, n, poll=5.0):
    """Yield each piece's result as it finishes, every piece once. Once no piece is left waiting for a
    container, one still running HEDGE x the median piece time later gets a second copy on another
    container and the first copy to finish counts: one slow container (a 115-frame piece took 368 s
    where the other 53 took 16-61 s) no longer holds up the render. The other copy is cancelled."""
    stop, futs, done, hedged, t_dry = threading.Event(), {}, {}, set(), None
    pool = ThreadPoolExecutor(len(r) + n)

    def go(i, copy):
        fc = spawn(i, *r[i], copy)
        futs[pool.submit(wait_for, fc, stop)] = (i, fc)
    try:
        for f in [pool.submit(go, i, 0) for i in range(len(r))]:    # one request each: send them at once
            f.result()
        while len(done) < len(r):
            fin, _ = futures.wait(list(futs), timeout=poll, return_when=futures.FIRST_COMPLETED)
            for f in fin:
                i, _ = futs.pop(f)
                if f.exception() and any(j == i for j, _ in futs.values()):
                    continue        # the other copy can still finish it
                if i not in done:
                    done[i] = f.result()
                    yield done[i]
            left = [i for i in range(len(r)) if i not in done]
            if t_dry is None and len(left) <= n:
                t_dry = time.time()
            if t_dry and done and time.time() - t_dry > HEDGE * statistics.median(c["wall_s"] for c in done.values()):
                for i in set(left) - hedged:
                    hedged.add(i)
                    print(f"piece {i} still running at {HEDGE}x the median piece: a second copy started", flush=True)
                    go(i, 1)
    finally:
        stop.set()
        for _, fc in futs.values():
            with contextlib.suppress(Exception):
                fc.cancel()
        pool.shutdown(wait=False)


def wait_for(fc, stop):
    """A spawned piece's result, checking every few seconds whether it is still wanted."""
    while not stop.is_set():
        try:
            return fc.get(timeout=3)
        except TimeoutError:    # Python's: no result yet (a piece that timed out raises Modal's own)
            pass


def measure(done, frames, t0, t_up, t_sub, t_ren, t_end, up_bytes):
    """What the next estimate reads (edit.py MODAL_MEASURED says what each is)."""
    boots = {c["boot"] for c in done}           # one per container
    n, work = len(boots), sum(c["wall_s"] for c in done)
    # a second copy's container boots late on purpose: start-up is the first copies' containers
    start = max(0.0, max(c["boot"] for c in done if not c.get("copy")) - t_sub)
    res = {"wall_s": round(t_end - t0, 1), "upload_s": round(t_up, 1), "pieces": len(done), "containers": n,
           "frames": frames, "cpu_s": round(sum(c["cpu_s"] for c in done), 1), "usd": round(cost(work, n), 4),
           "s_per_frame": round(work / frames, 4), "start_s": round(start, 1),
           "straggle": round(max(1.0, (t_ren - t_sub - start) / (work / n)), 2), "tail_s": round(t_end - t_ren, 1)}
    # ponytail: footage Modal already held goes up in a second; that time says nothing about the uplink
    if t_up > 10:
        res["up_bytes_s"] = round(up_bytes / t_up)
    return res


def demo():
    """No account needed. Always: the app, image and functions are defined. With a bundle, plan and
    output path: render() end to end with Modal faked, so the real upload calls, the real container
    body (render_chunk run here with .local) and the real join all run, in three pieces."""
    assert render_chunk and hello and image
    with tempfile.TemporaryDirectory() as t:
        # the code goes up as one tar, the same bytes when the code is the same (Modal then skips it)
        b = Path(t, "b")
        (b / "public").mkdir(parents=True)
        for f, x in (("bundle.js", "js"), ("1.bundle.js", "font"), ("bundle.js.map", "map"), ("1.bundle.js.map", "map"), ("public/cut.mp4", "mp4")):
            Path(b, f).write_text(x)
        pack(b, Path(t, "1.tar"))
        os.utime(b / "bundle.js", (1, 1))
        pack(b, Path(t, "2.tar"))
        assert Path(t, "1.tar").read_bytes() == Path(t, "2.tar").read_bytes(), "a new file time changed the tar"
        assert tarfile.open(Path(t, "1.tar")).getnames() == ["1.bundle.js", "bundle.js", "bundle.js.map"]
    # what the next estimate reads: 2 containers, the slow one takes one piece while the fast one takes three
    pcs = [{"boot": 105, "t0": 110, "wall_s": w, "cpu_s": 0} for w in (30, 30, 30)] + \
          [{"boot": 108, "t0": 110, "wall_s": 80, "cpu_s": 0}]
    m = measure(pcs, 1000, 0, 40, 100, 200, 230, 152e6)
    assert m["containers"] == 2 and m["start_s"] == 8 and m["s_per_frame"] == 0.17 and m["tail_s"] == 30, m
    assert m["straggle"] == round((100 - 8) / 85, 2) and m["up_bytes_s"] == 3.8e6, m
    late = measure(pcs + [{"boot": 220, "t0": 220, "wall_s": 30, "cpu_s": 0, "copy": 1}], 1000, 0, 40, 100, 260, 290, 152e6)
    assert late["start_s"] == 8 and late["containers"] == 3, "a second copy's late container counted as start-up"
    assert "up_bytes_s" not in measure(pcs, 1000, 0, 2, 100, 200, 230, 152e6), "a skipped upload is not a speed"
    # a piece stuck on a slow container gets a second copy once the queue is empty; the first to finish counts
    calls = []

    def spawn(i, a, b, copy):
        calls.append(Done({"i": i, "copy": copy, "wall_s": 0.01}, hang=(i, copy) == (2, 0)))
        return calls[-1]
    t = time.time()
    got = list(run_pieces(spawn, [[0, 9], [10, 19], [20, 29], [30, 39]], 2, poll=0.01))
    assert sorted((c["i"], c["copy"]) for c in got) == [(0, 0), (1, 0), (2, 1), (3, 0)], got
    assert [c.cancelled for c in calls if c.hang] == [True] and time.time() - t < 5, time.time() - t
    if len(sys.argv) > 2:
        mocked_render(*sys.argv[2:5])
    print("demo ok")


class Done:
    """A FunctionCall that has finished (or, with `hang`, never will)."""
    def __init__(self, result=None, hang=False):
        self.result, self.hang, self.cancelled = result, hang, False

    def get(self, timeout=None):
        if self.hang:
            time.sleep(timeout)
            raise TimeoutError()
        return self.result

    def cancel(self):
        self.cancelled = True


class FakeVolume:
    """The Volume calls render() and render_chunk make, on a local folder."""
    def __init__(self, root):
        self.root = Path(root)
        self.app_running = False

    @contextlib.contextmanager
    def app_run(self):
        self.app_running = True
        try:
            yield
        finally:
            self.app_running = False

    def _p(self, p):
        return self.root / p.lstrip("/")

    def batch_upload(self, force=False):
        return contextlib.nullcontext(self)

    def put_directory(self, src, dst):
        shutil.copytree(src, self._p(dst))

    def put_file(self, src, dst):
        self._p(dst).parent.mkdir(parents=True, exist_ok=True)
        self._p(dst).write_bytes(Path(src).read_bytes())

    def read_file_into_fileobj(self, p, f):
        return f.write(self._p(p).read_bytes())

    def remove_file(self, p, recursive=False):
        # a container still running (a retry, or a chunk going on after another failed) writes back
        # into the job's folder, so the folder goes only once app.run() has stopped them all
        assert not self.app_running, "the job's folder was deleted while the app could still write to it"
        shutil.rmtree(self._p(p))

    def commit(self):
        pass


def mocked_render(bundle_dir, plan_path, out):
    g = globals()
    body = render_chunk.local
    third = lambda n, spf: (1, [[a, min(n, a + math.ceil(n / 3)) - 1] for a in range(0, n, math.ceil(n / 3))])

    one_at_a_time = threading.Lock()     # run_pieces sends the pieces from several threads

    def chunk_on_container(*x):
        # A Modal container with cpu=4 shows Node more cores than `nproc` (4), and Remotion takes the
        # lower: a fake nproc on PATH gives this computer the same split.
        with one_at_a_time, tempfile.TemporaryDirectory() as bin_dir:
            Path(bin_dir, "nproc").write_text("#!/bin/sh\necho 4\n")
            Path(bin_dir, "nproc").chmod(0o755)
            path = os.environ["PATH"]
            os.environ["PATH"] = bin_dir + os.pathsep + path
            try:
                return body(*x)
            finally:
                os.environ["PATH"] = path

    with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as disk:
        saved = {k: g[k] for k in ("vol", "VOL_DIR", "LOCAL_DIR", "RENDER_MJS", "app", "render_chunk", "plan_pieces")}
        saved_out = modal.enable_output
        fv = FakeVolume(t)
        try:
            g.update(vol=fv, VOL_DIR=t, LOCAL_DIR=disk, RENDER_MJS=str(REMOTION / "render.mjs"), plan_pieces=third,
                     app=type("A", (), {"run": lambda self: fv.app_run()})(),
                     render_chunk=type("F", (), {"update_autoscaler": lambda self, **k: None,
                                                 "spawn": lambda self, *x: Done(chunk_on_container(*x))})())
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
    elif cmd == "held" and len(sys.argv) == 3:
        print(json.dumps({"to_upload": to_upload(sys.argv[2])}))
    elif cmd == "hello":
        with app.run():
            print(hello.remote())
    elif cmd == "demo":
        demo()
    else:
        sys.exit(__doc__)
