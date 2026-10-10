#!/usr/bin/env python3
"""The home page: first run in the browser. Setup checks, optional keys, pick a creator, watch their
videos get studied, see the style and the skill it became, drop a video. Stdlib only.

Claude stays the brain. The page only queues jobs; Claude takes each one with `wait`, runs the skill
for it, and reports back with `status`:

    python3 home.py serve [--root DIR] [--no-open]   serve the page and open it (run in the background)
    python3 home.py wait                         block until the page queues a job, print it as one line,
                                                 exit (run in the background, again after each job):
        JOB teardown @handle platform=tiktok take=captions,pace root=DIR
        JOB teardown @name urls=DIR/creator-teardowns/name/picks.txt take= root=DIR
        JOB skill @handle take=captions,pace,graphics root=DIR
        JOB video /path/take.mov as=@handle aspect=9:16 root=DIR      (as=defaults: no creator)
        JOB modal                                 the user pressed "Log in with your browser"
        JOB cancel teardown                       the user pressed Cancel
        ALREADY ...                               another wait is running: nothing to do
    python3 home.py status <job> [--step "..."] [--detail "video 6 of 10"] [--progress 0.6]
                                 [--result '<json>' | --result @file.json] [--done] [--failed "..."]
                                 <job> is teardown, skill, video or setup: its latest job
    python3 home.py demo                         self-check (no network, no keys)

State: $AI_EDITOR_HOME/home/state.json (default ~/.ai-video-editor). Keys typed on the page go
straight to keys.py (prefix check, one free verify request, then saved 0600); a key value is never
written to state.json, printed, logged or sent back to the page.

Numbers on the page come from the teardown's own style.json and videos.json, read by this server.
Claude's `--result` adds words only (the skill, prompts, what not to copy). Nothing is made up: a part
not measured yet shows as empty.

The server listens on 127.0.0.1 only and every request needs the random token in the URL it prints
(then a SameSite cookie), as review.py does.
"""
import argparse
import glob
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keys  # noqa: E402
import links  # noqa: E402
from review import load, now, save  # noqa: E402  (atomic write; review.py's server owns the rest)

HTML = Path(__file__).with_name("home.html")
SETUP = Path(__file__).resolve().parents[2] / "skills" / "setup" / "scripts" / "setup.py"
BEAT_S = 6
JOBS = ("teardown", "skill", "video", "modal", "setup")
TAKE = ("captions", "pace", "graphics", "sound")          # the page's parts; editplan.py --take names
KEY_NAMES = tuple(keys.VARS)
TOOLS = {"python": ("Python", "runs the editor"), "ffmpeg": ("ffmpeg", "cuts and joins video"),
         "node": ("Node", "draws captions and zooms"), "git": ("git", "for the installers"),
         "python packages": ("Python packages", "pinned versions"),
         "transcription model": ("Transcription model", "500 MB, runs offline"),
         "renderer": ("The renderer", "700 MB"), "free disk": ("Free disk", "3 GB or more")}
TOP, CONTROL = 5, 2       # creator-teardown quick mode: 5 most viewed + 2 closest to the median


def home():
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "home"


def state_path():
    return home() / "state.json"


def read():
    try:
        return load(state_path())
    except (OSError, ValueError):
        return {"root": str(Path.cwd()), "jobs": []}


class _Lock:
    """Cross-process: the server, `wait` and `status` all write state.json. A lock file made with O_EXCL."""
    def __enter__(self):
        self.p = home() / ".lock"
        self.p.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(400):
            try:
                os.close(os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
                return self
            except FileExistsError:
                try:   # a writer that died holding it: older than 10 s is stale
                    if time.time() - self.p.stat().st_mtime > 10:
                        self.p.unlink(missing_ok=True)
                except OSError:
                    pass
                time.sleep(0.025)
        raise TimeoutError(f"{self.p} is held; delete it if no home.py is running")

    def __exit__(self, *a):
        self.p.unlink(missing_ok=True)


def update(fn):
    with _Lock():
        d = read()
        out = fn(d)
        save(state_path(), d)
        return out


def latest(d, kind):
    return next((j for j in reversed(d["jobs"]) if j["type"] == kind), None)


def listening():
    try:
        return time.time() - (home() / ".listening").stat().st_mtime < BEAT_S
    except OSError:
        return False


# ---------------------------------------------------------------- creator: listing and measured numbers
def fetch_py():
    """creator-teardown's fetch.py: beside this plugin in the repo, or in the plugin cache."""
    env = os.environ.get("AI_EDITOR_FETCH_PY")
    here = Path(__file__).resolve()
    cands = ([env] if env else []) + [str(here.parents[3] / "creator-teardown" / "skills" / "creator-teardown" / "scripts" / "fetch.py")] \
        + sorted(glob.glob(str(here.parents[4] / "creator-teardown" / "*" / "skills" / "creator-teardown" / "scripts" / "fetch.py")))
    return next((Path(c) for c in cands if c and Path(c).is_file()), None)


def reach(v):
    return v.get("view_count") or v.get("like_count") or 0


def picks(vids, median):
    """What quick mode studies, as fetch.py pick: the TOP most viewed, then the CONTROL closest to the median."""
    ranked = sorted(vids, key=reach, reverse=True)
    rest = sorted((v for v in ranked[TOP:] if reach(v)), key=lambda v: abs(reach(v) - median))
    return [dict(v, role=f"Top {i + 1}") for i, v in enumerate(ranked[:TOP])] + \
        [dict(v, role="Control, median") for v in rest[:CONTROL]]


def listing(root, handle):
    """videos.json (written by fetch.py list) -> what H2 and H3 show. None when not listed."""
    try:
        d = json.loads((Path(root) / "creator-teardowns" / handle / "videos.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    keep = ("id", "title", "duration", "view_count", "like_count", "vs_median", "thumbnail", "webpage_url")
    return {"handle": d.get("handle"), "platform": d.get("platform"), "count": d.get("count"),
            "median": d.get("median_views"), "ranked_by": d.get("ranked_by"),
            "videos": [{k: v.get(k) for k in keep + ("role",)} for v in picks(d.get("videos") or [], d.get("median_views") or 0)]}


def run_listing(root, handle, platform):
    """fetch.py list in the background (yt-dlp --flat-playlist: no downloads, no key, a few seconds)."""
    f = fetch_py()
    if not f:
        return update(lambda d: d.__setitem__("lookup", {**d.get("lookup", {}), "status": "nofetch"}))
    try:
        r = subprocess.run([sys.executable, str(f), "list", handle, "--platform", platform, "--limit", "40"],
                           cwd=root, capture_output=True, text=True, timeout=120)
        ok = r.returncode == 0
        msg = "" if ok else (r.stderr.strip().splitlines() or ["yt-dlp returned nothing"])[-1][:200]
    except (OSError, subprocess.TimeoutExpired) as e:
        ok, msg = False, f"listing stopped: {e}"[:200]

    def put(d):
        if (d.get("lookup") or {}).get("handle") == handle:
            d["lookup"].update(status="ok" if ok else "failed", msg=msg)
    update(put)


def num(x, unit=""):
    return None if x is None else f"{x:g}{unit}" if isinstance(x, (int, float)) else str(x)


def measured(root, handle):
    """Plain lines from creator-teardowns/<handle>/style.json. Each part is there only once a script
    measured it, so the page fills in as the teardown runs. No number here comes from anywhere else."""
    try:
        s = json.loads((Path(root) / "creator-teardowns" / handle / "style.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"tiles": [], "rows": {}, "videos": None}
    p, z, c, g = (s.get(k) or {} for k in ("pace", "zoom", "captions", "graphics"))
    snd, hook, win = s.get("sound") or {}, (s.get("hook") or {}).get("winner") or {}, s.get("winners") or {}
    tiles, rows = [], {}
    if p.get("median_shot_s") is not None:
        tiles.append({"big": num(p["median_shot_s"], " s"), "label": "between cuts"})
    if z.get("kind") and z.get("per_min"):
        tiles.append({"big": num(z.get("scale"), "x"), "label": f"{z['kind']} zoom, {num(z['per_min'])} a minute"})
    if hook.get("first_word_s") is not None:
        tiles.append({"big": num(hook["first_word_s"], " s"), "label": "to the first word"})
    if p.get("wpm"):
        tiles.append({"big": num(p["wpm"]), "label": "words a minute"})
    if p:
        rows["pace"] = " ".join(x for x in (
            p.get("median_shot_s") is not None and f"A cut every {num(p['median_shot_s'])} s.",
            p.get("max_pause_s") is not None and f"Pauses top out at {num(p['max_pause_s'])} s.",
            p.get("wpm") and f"{num(p['wpm'])} words a minute.") if x)
    if z:
        rows["zooms"] = ("No zooms." if not z.get("kind") else
                         f"{z['kind'].capitalize()} zooms, {num(z.get('per_min'))} a minute, to {num(z.get('scale'))}x"
                         + (f", {z['ease']}" if z.get("ease") else "") + ".")
    if c:
        if c.get("present") is False:
            rows["captions"] = "No captions."
        elif c.get("words_per_caption") is not None:
            wpc = c["words_per_caption"]
            rows["captions"] = " ".join(x for x in (
                f"{num(wpc)} word{'' if wpc == 1 else 's'} at a time"
                + (f", {num(round(c['y_pct']))}% down the frame." if c.get("y_pct") is not None else "."),
                c.get("case") and f"{c['case'].capitalize()} case" + (f", weight {c['weight']}" if c.get("weight") else "") + ".",
                c.get("color") and f"{c['color']}" + (f" on a {c['box_color']} box" if c.get("box") else "") + ".",
                c.get("entrance") and f"Enters: {c['entrance']}.") if x)
    gpm, gsh = (g.get(k + "_measured", g.get(k)) for k in ("per_min", "share_pct"))   # graphics.py's count wins, as in look.md
    if gpm is not None or gsh is not None:
        rows["graphics"] = " ".join(x for x in (
            gpm is not None and f"{num(gpm)} graphics a minute.",
            gsh is not None and f"On screen {num(gsh)}% of the time.") if x)
    if snd:
        m = (snd.get("music") or {}).get("present_pct")
        rows["sound"] = " ".join(x for x in (
            snd.get("sfx_per_min") is not None and f"{num(snd['sfx_per_min'])} sound effects a minute.",
            m is not None and f"Music in {num(m)}% of videos.") if x)
    if hook:
        rows["hook"] = " ".join(x for x in (
            hook.get("first_word_s") is not None and f"First word at {num(hook['first_word_s'])} s.",
            hook.get("first_caption_s") is not None and f"Caption at {num(hook['first_caption_s'])} s.",
            hook.get("first_cut_s") is not None and f"First cut at {num(hook['first_cut_s'])} s.") if x)
    if win.get("differs"):
        rows["winners"] = " ".join(win["differs"][:2]) + \
            f" ({win.get('n_winners')} top against {win.get('n_control')} median: a lead, not proof.)"
    rows = {k: v for k, v in rows.items() if v}
    return {"tiles": tiles, "rows": rows, "videos": s.get("videos"),
            "report": (Path(root) / "creator-teardowns" / handle / "teardown.html").exists()}


# ---------------------------------------------------------------- setup checks
def doctor_rows(text):
    """setup.py doctor's lines -> [{id, ok, name, what, detail}] for the tools only (keys are their own rows)."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^(ok |FIX|--)\s+(.+?)\s{2,}(.*)$", line)
        if m and m[2].strip() in TOOLS:
            name, what = TOOLS[m[2].strip()]
            v = re.search(r"(?:version )?v?(\d+\.\d+)", m[3]) if m[2].strip() in ("python", "ffmpeg", "node") else None
            out.append({"id": m[2].strip(), "ok": m[1] == "ok ", "name": f"{name} {v[1]}" if v else name, "what": what})
    return out


def run_doctor():
    try:
        r = subprocess.run([sys.executable, str(SETUP), "doctor"], capture_output=True, text=True, timeout=180)
        rows = doctor_rows(r.stdout)
    except (OSError, subprocess.TimeoutExpired):
        rows = []
    update(lambda d: d.__setitem__("doctor", {"rows": rows, "at": now()}))


def key_rows():
    out = {}
    for n in KEY_NAMES:
        k, where = keys.get(n)
        out[n] = {"set": bool(k), "env": bool(k) and not str(where).endswith(".env")}
    return out


# ---------------------------------------------------------------- queueing jobs
def queue(d, kind, args):
    j = {"id": f"{kind}-{sum(x['type'] == kind for x in d['jobs']) + 1}", "type": kind, "args": args,
         "state": "queued", "at": now(), "steps": [], "result": {}}
    d["jobs"].append(j)
    d["jobs"] = d["jobs"][-40:]
    return j


def job_line(j, root):
    a = j["args"]
    if j["type"] == "teardown":
        src = f"urls={a['urls']}" if a.get("urls") else f"platform={a['platform']}"
        return f"JOB teardown @{a['handle']} {src} take={','.join(a.get('take') or [])} root={root}"
    if j["type"] == "skill":
        return f"JOB skill @{a['handle']} take={','.join(a.get('take') or [])} root={root}"
    if j["type"] == "video":
        return f"JOB video {a['path']} as={a['as']} aspect={a['aspect']} root={root}"
    return f"JOB {j['type']}"


def cmd_wait(poll=1.0):
    beat = home() / ".listening"
    beat.parent.mkdir(parents=True, exist_ok=True)
    if listening():   # one waiter at a time, so each job reaches exactly one background task
        print("ALREADY: another `home.py wait` is running; the next job comes out of that one.", flush=True)
        return "ALREADY"
    try:
        while True:
            beat.touch()
            d = read()
            if any(j["state"] == "queued" or (j.get("cancel") and not j.get("cancel_sent")) for j in d["jobs"]):
                break
            time.sleep(poll)
    finally:
        beat.unlink(missing_ok=True)

    def take(d):
        for j in d["jobs"]:
            if j.get("cancel") and not j.get("cancel_sent"):
                j["cancel_sent"] = True
                return f"JOB cancel {j['type']}"
        j = next(j for j in d["jobs"] if j["state"] == "queued")
        j["state"] = "taken"
        return job_line(j, d["root"])
    line = update(take)
    print(line, flush=True)
    return line


def cmd_status(a):
    def f(d):
        j = latest(d, a.job)
        if not j or (a.job == "setup" and j["state"] in ("done", "failed")):
            j = queue(d, a.job, {})
            j["state"] = "taken"
        t = time.time()
        if a.step:
            for s in j["steps"]:
                if not s.get("done"):
                    s["done"], s["secs"] = True, round(t - s["t"])
            j["steps"].append({"text": a.step, "detail": a.detail, "progress": a.progress, "t": t, "done": False})
        elif j["steps"] and (a.detail is not None or a.progress is not None):
            j["steps"][-1].update({k: v for k, v in (("detail", a.detail), ("progress", a.progress)) if v is not None})
        if a.result:
            r = json.loads(Path(a.result[1:]).read_text(encoding="utf-8") if a.result.startswith("@") else a.result)
            j["result"].update(r)
        if a.done or a.failed:
            for s in j["steps"]:
                if not s.get("done"):
                    s["done"], s["secs"] = True, round(t - s["t"])
            j["state"] = "failed" if a.failed else "done"
            j["error"] = a.failed
            j["finished"] = t
        j.setdefault("started", t)
        return j
    j = update(f)
    print(f"{j['id']}: {j['state']}" + (f", {a.step}" if a.step else ""))


# ---------------------------------------------------------------- server
def make_handler(token):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):   # never log a request: a key travels in one
            pass

        def cookie_name(self):
            return f"ave-home-{self.server.server_address[1]}"

        def authorized(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):   # DNS rebinding: another name pointing here
                return False
            q = parse_qs(urlsplit(self.path).query).get("t", [""])[0]
            c = SimpleCookie()
            try:
                c.load(self.headers.get("Cookie") or "")
            except Exception:
                pass
            got = c[self.cookie_name()].value if self.cookie_name() in c else ""
            return any(hmac.compare_digest(v.encode(), token.encode()) for v in (q, got) if v)

        def send(self, code, body, ctype="application/json", cookie=False):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            if cookie:
                self.send_header("Set-Cookie", f"{self.cookie_name()}={token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.authorized():
                return self.send(403, {"error": "open the page with the URL home.py printed"})
            path = unquote(urlsplit(self.path).path)
            if path == "/":
                return self.send(200, HTML.read_bytes(), "text/html; charset=utf-8", cookie=True)
            if path == "/state":
                d = read()
                d["listening"], d["keys"] = listening(), key_rows()
                d["key_file"] = str(keys.key_file()).replace(str(Path.home()), "~")
                lk = d.get("lookup") or {}
                if lk.get("handle"):
                    lk["listing"] = listing(d["root"], lk["handle"])
                td = latest(d, "teardown")
                if td:
                    td["measured"] = measured(d["root"], td["args"]["handle"])
                    td["listing"] = listing(d["root"], td["args"]["handle"])
                return self.send(200, d)
            m = re.match(r"^/td/([a-z0-9._-]+)/(.+)$", path)   # the teardown page and its own files
            if m:
                base = (Path(read()["root"]) / "creator-teardowns" / m[1]).resolve()
                p = (base / m[2]).resolve()
                if base in p.parents and p.is_file():
                    ct = {".html": "text/html; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
                          ".json": "application/json", ".mp4": "video/mp4", ".gif": "image/gif"}.get(p.suffix, "application/octet-stream")
                    return self.send(200, p.read_bytes(), ct)
            self.send(404, {})

        def do_POST(self):
            if not self.authorized():
                return self.send(403, {"error": "open the page with the URL home.py printed"})
            path = urlsplit(self.path).path
            if path == "/upload":
                return self.upload()
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length") or 0), 1 << 20)) or b"{}")
            except ValueError:
                return self.send(400, {"error": "not json"})
            if path == "/key":
                name, val = body.get("name"), str(body.get("value") or "").strip()
                if name not in KEY_NAMES or not val or len(val) > 400 or re.search(r"\s", val):
                    return self.send(400, {"ok": False, "msg": "Paste only the key: one line, no spaces."})
                ok, msg = keys.verify(name, val)
                if ok:
                    keys.save(name, val)
                return self.send(200, {"ok": ok, "msg": "Verified. The key works." if ok else f"Not saved. {msg[0].upper()}{msg[1:]}"})
            if path == "/later":
                for n in body.get("names") or []:
                    if n in KEY_NAMES + ("modal",):
                        subprocess.run([sys.executable, str(SETUP), "later", n], capture_output=True, timeout=30)
                update(lambda d: d.__setitem__("setup_skipped", True))
                return self.send(200, {})
            if path == "/recheck":
                threading.Thread(target=run_doctor, daemon=True).start()
                return self.send(200, {})
            if path == "/lookup":
                return self.lookup(str(body.get("text") or "").strip(), body.get("platform"))
            if path == "/probe":
                return self.send(200, probe(body.get("path") or ""))
            if path == "/job":
                return self.job(body)
            if path == "/cancel":
                def c(d):
                    j = latest(d, body.get("type") or "teardown")
                    if j and j["state"] in ("queued", "taken"):
                        j["cancel"], j["state"] = True, "cancelled"
                update(c)
                return self.send(200, {})
            self.send(404, {})

        def lookup(self, text, platform=None):
            parts = text.split()
            if not parts:
                return self.send(200, {"kind": "empty"})
            if len(parts) == 1 and not re.search(r"[./]", parts[0]):
                parts = ["@" + parts[0].lstrip("@")]           # a bare name is a handle, never a website
            items = [links.classify(p) for p in parts]
            reels = [i for i in items if i["kind"] in ("video", "own", "long") and "instagram.com" in i["url"]]
            if len(items) > 1 and len(reels) == len(items):    # pasted reel links: an Instagram teardown
                return self.send(200, {"kind": "creator", "platform": "instagram", "urls": [i["url"] for i in reels],
                                       "handle": None, "note": f"{len(reels)} reel links. Instagram ranks by likes, not views."})
            it = items[0]
            if it["kind"] != "creator":
                return self.send(200, {"kind": it["kind"], "note": "Paste a creator's handle or profile link, like "
                                                                   "@name or tiktok.com/@name."})
            handle, plat = re.sub(r"[^a-z0-9._-]", "", it["handle"].lower()), it.get("platform") or platform or "tiktok"
            out = {"kind": "creator", "handle": handle, "platform": plat, "note": it.get("note") if plat == "instagram" else None,
                   "ask_platform": not it.get("platform")}
            if plat in ("tiktok", "youtube"):
                d = read()
                if (d.get("lookup") or {}).get("handle") != handle or (d.get("lookup") or {}).get("platform") != plat \
                        or d["lookup"].get("status") == "failed":
                    update(lambda d: d.__setitem__("lookup", {"handle": handle, "platform": plat, "status": "listing"}))
                    threading.Thread(target=run_listing, args=(d["root"], handle, plat), daemon=True).start()
            return self.send(200, out)

        def job(self, b):
            kind = b.get("type")
            take = [t for t in b.get("take") or [] if t in TAKE]
            d = read()
            if kind == "teardown":
                handle = re.sub(r"[^a-z0-9._-]", "", str(b.get("handle") or "").lower())
                urls = [u for u in b.get("urls") or [] if links.classify(u)["kind"] != "unsupported"][:40]
                if urls and not handle:
                    handle = "instagram-" + time.strftime("%m%d%H%M")
                if not handle:
                    return self.send(400, {"error": "no creator"})
                args = {"handle": handle, "platform": b.get("platform") if b.get("platform") in ("tiktok", "youtube") else "tiktok",
                        "take": take}
                if urls:
                    f = Path(d["root"]) / "creator-teardowns" / handle / "picks.txt"
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("\n".join(urls) + "\n", encoding="utf-8")
                    args.update(urls=str(f), platform="instagram")
            elif kind == "skill":
                td = latest(d, "teardown")
                if not td or td["state"] != "done":
                    return self.send(409, {"error": "the study is not finished"})
                args = {"handle": td["args"]["handle"], "take": take}
            elif kind == "video":
                p = probe(b.get("path") or "")
                if not p.get("ok"):
                    return self.send(400, p)
                td = latest(d, "teardown")
                use = b.get("as") != "defaults" and td and td["state"] == "done"
                args = {"path": p["path"], "as": f"@{td['args']['handle']}" if use else "defaults",
                        "aspect": "16:9" if b.get("aspect") == "16:9" else "9:16"}
            elif kind == "modal":
                args = {}
            else:
                return self.send(400, {"error": "unknown job"})
            j = update(lambda d: queue(d, kind, args))
            return self.send(200, {"id": j["id"]})

        def upload(self):
            """A dropped video: streamed to <root>/videos/<name>, never held in memory."""
            name = Path(unquote(parse_qs(urlsplit(self.path).query).get("name", [""])[0])).name
            n = int(self.headers.get("Content-Length") or 0)
            if not name.lower().endswith(links.VIDEO_EXT) or n <= 0:
                return self.send(400, {"ok": False, "msg": "Drop a .mov, .mp4 or .mkv video."})
            out = Path(read()["root"]) / "videos" / name
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(out.suffix + ".part")
            with open(tmp, "wb") as f:
                left = n
                while left > 0:
                    b = self.rfile.read(min(1 << 20, left))
                    if not b:
                        break
                    f.write(b)
                    left -= len(b)
            if left:
                tmp.unlink(missing_ok=True)
                return self.send(400, {"ok": False, "msg": "The upload stopped part way. Drop it again."})
            os.replace(tmp, out)
            return self.send(200, probe(str(out)))
    return H


def probe(path):
    """{ok, path, name, duration, size, vertical, label} for a video file on this computer."""
    p = Path(os.path.expanduser(str(path).strip().strip('"').strip("'")))
    if not p.is_file():
        return {"ok": False, "msg": "No video at that path."}
    if not p.name.lower().endswith(links.VIDEO_EXT):
        return {"ok": False, "msg": "That is not a video file (.mov, .mp4, .mkv)."}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:stream_tags=rotate:format=duration", "-of", "json", str(p)],
                           capture_output=True, text=True, timeout=30)
        j = json.loads(r.stdout or "{}")
        s = (j.get("streams") or [{}])[0]
        w, h, dur = s.get("width"), s.get("height"), float((j.get("format") or {}).get("duration") or 0)
        if str((s.get("tags") or {}).get("rotate", "0")) in ("90", "-90", "270"):
            w, h = h, w
    except (OSError, ValueError, subprocess.TimeoutExpired):
        w = h = None
        dur = 0
    if not w:
        return {"ok": False, "msg": "That file has no video in it that ffprobe can read."}
    size = p.stat().st_size
    gb = f"{size / 1e9:.1f} GB" if size >= 1e9 else f"{size / 1e6:.0f} MB"
    res = "4K" if max(w, h) >= 3840 else "1080p" if max(w, h) >= 1920 else f"{min(w, h)}p"
    return {"ok": True, "path": str(p.resolve()), "name": p.name, "duration": round(dur, 1),
            "vertical": h > w, "label": f"{int(dur // 60)}:{int(dur % 60):02d} · {'vertical' if h > w else 'wide'} {res} · {gb}"}


def running():
    try:
        url = (home() / ".server").read_text(encoding="utf-8").strip()
        urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=2).read()
        return url
    except (OSError, ValueError):
        return None


def serve(root, port=0, open_browser=True):
    """(server, url). A server already running is reused: (None, its url), with the root moved to this one."""
    update(lambda d: d.__setitem__("root", str(Path(root).resolve())))
    url = running()
    if url:
        if open_browser:
            webbrowser.open(url)
        return None, url
    token = secrets.token_urlsafe(32)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(token))
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={token}"
    (home() / ".server").write_text(url, encoding="utf-8")
    threading.Thread(target=run_doctor, daemon=True).start()
    if open_browser:
        webbrowser.open(url)
    return srv, url


# ---------------------------------------------------------------- demo
def demo():
    import contextlib
    import io
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="home_demo_"))
    os.environ["AI_EDITOR_HOME"] = str(tmp / "home")
    for v in keys.VARS.values():
        os.environ.pop(v, None)
    root = tmp / "work"
    td = root / "creator-teardowns" / "sample.creator"
    td.mkdir(parents=True)
    vids = [{"id": str(i), "title": f"v{i}", "view_count": v, "duration": 30, "thumbnail": f"https://x/{i}.jpg"}
            for i, v in enumerate([1600000, 820000, 410000, 302000, 188000, 151000, 97000, 76000, 49000, 47000, 1000])]
    (td / "videos.json").write_text(json.dumps({"handle": "sample.creator", "platform": "tiktok", "count": 11,
                                                "median_views": 151000, "ranked_by": "views", "videos": vids}))
    calls = []
    globals()["run_doctor"] = lambda: update(lambda d: d.__setitem__("doctor", {"rows": doctor_rows(
        "ok   python               3.12.1 (need 3.10+)\nFIX  renderer             missing\n     run: x\n"
        "--   gemini key           Recommended"), "at": now()}))
    globals()["run_listing"] = lambda *a: calls.append(a)
    srv, url = serve(root, 0, open_browser=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base, tok = url.split("/?t=")

    def get(p):
        return json.loads(urllib.request.urlopen(base + p + "?t=" + tok).read())

    def post(p, b):
        return json.loads(urllib.request.urlopen(urllib.request.Request(
            base + p + "?t=" + tok, json.dumps(b).encode(), method="POST")).read())

    def out(fn, *a):
        o = io.StringIO()
        with contextlib.redirect_stdout(o):
            fn(*a)
        return o.getvalue().strip()

    # no token, or another Host name pointing here: nothing reads or writes
    for p, data, hdr in (("/state", None, {}), ("/key", b'{"name":"gemini","value":"AIzaX"}', {}),
                         ("/state?t=" + tok, None, {"Host": "evil.example"})):
        try:
            urllib.request.urlopen(urllib.request.Request(base + p, data, hdr, method="POST" if data else "GET"))
            raise AssertionError(f"{p} answered without the token")
        except urllib.error.HTTPError as e:
            assert e.code == 403, (p, e.code)
    r = urllib.request.urlopen(base + "/?t=" + tok)
    assert b"ai editor" in r.read() and "SameSite=Strict" in r.headers["Set-Cookie"]
    for _ in range(50):
        if read().get("doctor"):
            break
        time.sleep(0.02)
    st = get("/state")
    assert [(x["name"], x["ok"]) for x in st["doctor"]["rows"]] == [("Python 3.12", True), ("The renderer", False)], st["doctor"]
    assert st["keys"]["gemini"] == {"set": False, "env": False} and not st["listening"]
    # keys: a wrong prefix is refused before any request; a good one is verified once, saved, never echoed
    sent = []
    real = keys._get
    keys._get = lambda *a: sent.append(a) or (200, "")
    try:
        r = post("/key", {"name": "gemini", "value": "not-a-key-123"})
        assert not r["ok"] and "AIza" in r["msg"] and "Nothing was sent" in r["msg"] and not sent, r
        secret = "AIza" + "s" * 35
        r = post("/key", {"name": "gemini", "value": secret})
        assert r["ok"] and len(sent) == 1 and secret not in json.dumps(r), r
        keys._get = lambda *a: (401, "bad")
        r = post("/key", {"name": "typesafe", "value": "ts-" + "x" * 30})
        assert not r["ok"] and r["msg"].startswith("Not saved. The service rejected"), r
    finally:
        keys._get = real
    st = get("/state")
    assert st["keys"]["gemini"]["set"] and not st["keys"]["typesafe"]["set"]
    assert secret not in state_path().read_text() and secret not in json.dumps(st), "a key reached state.json"
    assert keys.get("gemini")[0] == secret
    # the paste: a profile link names the platform; a bare name is a handle; a website is not a creator
    r = post("/lookup", {"text": "https://www.tiktok.com/@sample.creator"})
    assert r["kind"] == "creator" and r["handle"] == "sample.creator" and r["platform"] == "tiktok" and calls, r
    assert post("/lookup", {"text": "someone"})["ask_platform"] is True
    assert post("/lookup", {"text": "https://example.com/pricing"})["kind"] != "creator"
    ig = post("/lookup", {"text": "https://www.instagram.com/someone/"})
    assert ig["platform"] == "instagram" and "reel" in ig["note"], ig
    post("/lookup", {"text": "@sample.creator"})
    lk = get("/state")["lookup"]["listing"]
    assert [v["role"] for v in lk["videos"]] == ["Top 1", "Top 2", "Top 3", "Top 4", "Top 5", "Control, median", "Control, median"]
    assert lk["videos"][5]["view_count"] == 151000 and lk["videos"][0]["thumbnail"] == "https://x/0.jpg", lk
    # Start: a teardown job; `wait` prints it as one line and marks it taken
    try:   # Build my skill before the study is done: refused
        post("/job", {"type": "skill"})
        raise AssertionError("skill job before the teardown")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    post("/job", {"type": "teardown", "handle": "sample.creator", "platform": "tiktok", "take": ["captions", "pace", "evil"]})
    assert out(cmd_wait, 0.01) == f"JOB teardown @sample.creator platform=tiktok take=captions,pace root={root.resolve()}"
    assert latest(read(), "teardown")["state"] == "taken"
    # Claude reports steps; the page reads measured numbers from style.json only, as they appear
    ns = argparse.Namespace
    st = lambda **k: out(cmd_status, ns(**{"job": "teardown", "step": None, "detail": None, "progress": None,
                                           "result": None, "done": False, "failed": None, **k}))
    st(step="Listed 40 videos, ranked by views")
    st(step="Reading captions and faces", detail="video 3 of 7", progress=0.4)
    t = get("/state")["jobs"][-1]
    assert t["measured"]["tiles"] == [] and [s["done"] for s in t["steps"]] == [True, False]
    (td / "style.json").write_text(json.dumps({"videos": 7, "pace": {"wpm": 186, "median_shot_s": 1.9, "max_pause_s": 0.3},
                                               "zoom": {"kind": "punch", "per_min": 6.0, "scale": 1.12},
                                               "captions": {"present": True, "words_per_caption": 2, "y_pct": 62.4,
                                                            "case": "upper", "color": "#FFFFFF", "box": True,
                                                            "box_color": "#000000", "entrance": "pop"}}))
    m = get("/state")["jobs"][-1]["measured"]
    assert [x["big"] for x in m["tiles"]] == ["1.9 s", "1.12x", "186"], m["tiles"]
    assert m["rows"]["captions"].startswith("2 words at a time, 62% down") and "graphics" not in m["rows"], m["rows"]
    st(result=json.dumps({"reject": ["The follow-for-part-2 close."]}), done=True)
    t = get("/state")["jobs"][-1]
    assert t["state"] == "done" and t["result"]["reject"] and all(s["done"] for s in t["steps"])
    # the teardown page and its files only, never outside the creator's folder
    (td / "teardown.html").write_text("<h1>t</h1>")
    assert urllib.request.urlopen(base + "/td/sample.creator/teardown.html?t=" + tok).read() == b"<h1>t</h1>"
    for bad in ("/td/sample.creator/../videos.json", "/td/sample.creator/%2e%2e/%2e%2e/x"):
        try:
            urllib.request.urlopen(base + bad + "?t=" + tok)
            raise AssertionError(bad)
        except urllib.error.HTTPError as e:
            assert e.code == 404
    # Build my skill, then a video: the path is probed, the job names the creator
    post("/job", {"type": "skill", "take": ["captions", "graphics"]})
    assert out(cmd_wait, 0.01) == f"JOB skill @sample.creator take=captions,graphics root={root.resolve()}"
    vid = tmp / "take.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=360x640:rate=30:duration=2",
                    "-pix_fmt", "yuv420p", str(vid)], check=True)
    p = post("/probe", {"path": str(vid)})
    assert p["ok"] and p["vertical"] and p["label"].startswith("0:02 · vertical"), p
    assert not post("/probe", {"path": str(tmp / "nope.mp4")})["ok"]
    r = urllib.request.urlopen(urllib.request.Request(base + "/upload?name=drop.mp4&t=" + tok, vid.read_bytes(), method="POST"))
    assert json.loads(r.read())["ok"] and (root / "videos" / "drop.mp4").stat().st_size == vid.stat().st_size
    post("/job", {"type": "video", "path": str(vid), "aspect": "9:16"})
    assert out(cmd_wait, 0.01) == f"JOB video {vid.resolve()} as=@sample.creator aspect=9:16 root={root.resolve()}"
    (home() / ".listening").touch()
    assert out(cmd_wait, 0.01).startswith("ALREADY")
    (home() / ".listening").unlink()
    # cancel reaches `wait` as its own line
    post("/job", {"type": "teardown", "handle": "other", "platform": "youtube"})
    out(cmd_wait, 0.01)
    post("/cancel", {"type": "teardown"})
    assert out(cmd_wait, 0.01) == "JOB cancel teardown" and latest(read(), "teardown")["state"] == "cancelled"
    assert running() == url and serve(root, 0, open_browser=False) == (None, url)
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("home demo ok")


def main():
    if sys.argv[1:2] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("serve")
    s.add_argument("--root", default=".", help="the folder creator-teardowns/ and edits/ live in (default: here)")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--no-open", action="store_true")
    sp.add_parser("wait")
    s = sp.add_parser("status")
    s.add_argument("job", choices=JOBS)
    s.add_argument("--step")
    s.add_argument("--detail")
    s.add_argument("--progress", type=float)
    s.add_argument("--result", help="JSON, or @file.json")
    s.add_argument("--done", action="store_true")
    s.add_argument("--failed", help="a plain sentence for the page")
    a = ap.parse_args()
    if a.cmd == "serve":
        srv, url = serve(a.root, a.port, open_browser=not a.no_open)
        print(url, flush=True)
        if srv:
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
        else:
            print("already serving" + ("" if a.no_open else "; opened it"))
    elif a.cmd == "wait":
        cmd_wait()
    elif a.cmd == "status":
        cmd_status(a)


if __name__ == "__main__":
    main()
