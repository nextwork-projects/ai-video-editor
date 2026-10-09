#!/usr/bin/env python3
"""The review page: the user watches a render and leaves notes at moments on its timeline. Stdlib only.

One page per edit folder, the hand-over after every render (the cut, the styled edit, a clip, a
product video). Notes save with the edit, never in the plugin:

    <folder>/review.json    every round, note, reply and send/approve event
    <folder>/review/        a frame still per note, and any image the user attached

    python3 review.py <folder> start --video cut.mp4 [--stage cut|edit] [--transcript words.json] [--plan plan.json]
                                     [--name NAME] [--note "..."]
    python3 review.py <folder> serve [--no-open]   serve the page and open it (run in the background)
    python3 review.py <folder> wait                block until the user presses send or approve (run in the background)
    python3 review.py <folder> status "rendering" [--log render.log] [--done]   what Claude is doing, live on the page
    python3 review.py <folder> resolve <id> fixed|wontfix|open [--reply "..."] [--new-t 12.3]
    python3 review.py <folder> round --video v2.mp4 [--stage cut|edit] [--transcript ..] [--plan ..] [--note ".."]
    python3 review.py <folder> alt <name> --video other.mp4 [--transcript ..]   another video in this round
    python3 review.py demo                         self-check on a generated 6 s clip

`wait` exits when the user presses send or approve, and prints every note of the round: its time,
the text, the words being said, the card on screen (from plan.json) and the frame still's path.
While `wait` runs the page says Claude is listening; without it the notes still save, and the next
`wait` returns at once with them.

The server listens on 127.0.0.1 only, and every request needs the random token in the URL it
prints (then a SameSite cookie), as preview.py does: another page open in the browser cannot read
the notes or press send.
"""
import argparse
import base64
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

HTML = Path(__file__).with_name("review.html")
LOCK = threading.Lock()
BEAT_S = 6          # `wait` touches review/.listening at least this often; older = nobody listening
IMAGE_TYPES = ("png", "jpeg", "gif", "webp")
MAX_IMAGE = 15 << 20


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, d):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1), encoding="utf-8")
    for i in range(20):   # Windows refuses to replace a file another process is reading this instant
        try:
            return os.replace(tmp, path)
        except PermissionError:
            if i == 19:
                raise
            time.sleep(0.05)


# ponytail: a thread lock, not a file lock. The page writes notes; the CLI writes only between rounds and
# `wait` only on a send or approve, when the page has stopped taking notes. A cross-process lock if that changes.
def update(path, fn):
    with LOCK:
        d = load(path)
        out = fn(d)
        save(path, d)
        return out


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def probe(video):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout.strip().split(",")
    return len(r) >= 2 and r[1].isdigit() and int(r[1]) > int(r[0])   # ffprobe can print a trailing comma


def words_of(transcript):
    """A transcript's words: the plugin's list shape, or {"words": [...]} from other tools."""
    if not transcript or not Path(transcript).exists():
        return []
    d = load(transcript)
    ws = d.get("words", []) if isinstance(d, dict) else d
    return [w for w in ws if isinstance(w, dict) and w.get("type", "word") == "word"]


def words_at(transcript, t0, t1):
    got = [w["text"].strip() for w in words_of(transcript) if w["end"] >= t0 - 1.5 and w["start"] <= t1 + 1.5]
    return " ".join(x for x in got if x)


def card_at(plan, t):
    """The plan.json card on screen at t, so a note maps to the card it is about."""
    if not plan or not Path(plan).exists():
        return None
    for i, c in enumerate(load(plan).get("cards", [])):
        if c.get("start", 0) <= t < c.get("end", 0):
            kind = (c.get("anim") or {}).get("type") or c.get("lane") or "image"
            return {"i": i, "kind": kind, "trigger_word": c.get("trigger_word"), "src": c.get("src"),
                    "start": c["start"], "end": c["end"]}
    return None


def grab(video, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=960:-2", "-q:v", "3", str(out)], check=False)


def listening(folder):
    try:
        return time.time() - (folder / "review" / ".listening").stat().st_mtime < BEAT_S
    except OSError:
        return False


def log_pct(path):
    """The last "N/M" in a render log (Remotion prints "Rendered 812/3255"), as a percent."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            tail = f.read().decode(errors="ignore")
    except OSError:
        return None
    m = re.findall(r"(\d+)/(\d+)", tail)
    return round(100 * int(m[-1][0]) / int(m[-1][1])) if m and int(m[-1][1]) else None


def log_round(d):
    """Every round's video is kept, so the page has a tab per round."""
    rs = [r for r in d.setdefault("rounds", []) if (r["stage"], r["round"]) != (d["stage"], d["round"])]
    d["rounds"] = rs + [{k: d.get(k) for k in ("stage", "round", "video", "note", "label", "alts")}]


def alt_of(d, name, rnd=None):
    """A version's video and transcript. No name = the round's main video."""
    r = rnd or d
    a = next((a for a in r.get("alts") or [] if a["name"] == name), None)
    return a or {"video": r["video"], "transcript": d.get("transcript")}


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def stage_name(s):
    return {"cut": "the cut", "edit": "the edit"}.get(s, s)


# ---------------------------------------------------------------- server
def make_handler(folder, token):
    rj = folder / "review.json"

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def cookie_name(self):
            return f"ave-review-{self.server.server_address[1]}"   # cookies ignore ports: one per server

        def authorized(self):
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

        def file(self, p, ctype):
            # Range requests: without 206 the browser cannot seek a long mp4
            size = p.stat().st_size
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if m and (m[1] or m[2]):
                start, end = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (size - int(m[2]), size - 1)
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            try:
                with open(p, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        b = f.read(min(1 << 20, left))
                        if not b:
                            break
                        self.wfile.write(b)
                        left -= len(b)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.authorized():
                return self.send(403, {"error": "open the page with the URL review.py printed"})
            path = urlsplit(self.path).path
            q = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
            if path == "/":
                return self.send(200, HTML.read_bytes(), "text/html; charset=utf-8", cookie=True)
            if path == "/state":
                d = load(rj)
                d["listening"] = listening(folder)
                d["cutcheck"] = (folder / "cut-check.html").exists()
                for x in d.get("activity", [])[-1:]:
                    if x.get("log") and not x.get("done"):
                        x["pct"] = log_pct(x["log"])
                return self.send(200, d)
            if path == "/video":
                d = load(rj)
                r = next((r for r in d.get("rounds", []) if f"{r['stage']}-{r['round']}" == q.get("k")), d)
                p = Path(alt_of(d, q.get("alt", ""), r)["video"])
                return self.file(p, "video/mp4") if p.exists() else self.send(404, {})
            if path.startswith("/frames/"):
                p = folder / "review" / Path(unquote(path)).name
                ct = {".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}.get(p.suffix, "image/jpeg")
                return self.file(p, ct) if p.is_file() else self.send(404, {})
            # the cut skill's transcript page, with its video beside it
            if path in ("/cut-check.html", "/cut.mp4") and (folder / path[1:]).exists():
                return self.file(folder / path[1:], "text/html; charset=utf-8" if path.endswith("html") else "video/mp4")
            self.send(404, {})

        def do_POST(self):
            if not self.authorized():
                return self.send(403, {"error": "open the page with the URL review.py printed"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                return self.send(400, {"error": "not json"})
            path = urlsplit(self.path).path
            if path == "/comment":
                return self.comment(body)
            if path == "/scope":   # a saved note: all versions ("*") or one version (a name, None = main)
                def sc(d):
                    for c in d["comments"]:
                        if c["id"] == body.get("id") and c["round"] == d["round"] and not d.get("sent"):
                            c["alt"] = body.get("alt") or None
                update(rj, sc)
                return self.send(200, {})
            if path == "/delete":
                def rm(d):
                    d["comments"] = [c for c in d["comments"] if not (
                        c["id"] == body.get("id") and c["round"] == d["round"] and not d.get("sent"))]
                update(rj, rm)
                return self.send(200, {})
            if path == "/check":   # "got it" on one of Claude's answers
                ids = set(body.get("ids", []))
                def ck(d):
                    for c in d["comments"]:
                        if c["id"] in ids:
                            c["checked"] = True
                update(rj, ck)
                return self.send(200, {})
            if path == "/event":
                if body.get("type") not in ("send", "approve"):
                    return self.send(400, {})
                def ev(d):
                    d["events"].append({"type": body["type"], "stage": d["stage"], "round": d["round"],
                                        "at": now(), "handled": False})
                    d["sent"] = True
                update(rj, ev)
                return self.send(200, {})
            self.send(404, {})

        def comment(self, body):
            text = str(body.get("text", "")).strip()
            imgs = body.get("images") or []
            if not text and not imgs:
                return self.send(400, {"error": "empty"})
            try:
                t = float(body["t"])
                te = float(body["t_end"]) if body.get("t_end") is not None else None
            except (KeyError, TypeError, ValueError):
                return self.send(400, {"error": "no time"})
            d = load(rj)
            if d.get("sent"):
                return self.send(409, {"error": "this round is with Claude"})
            alt = body.get("alt") or None
            src = alt_of(d, alt if alt != "*" else None)
            cid = max([c["id"] for c in d["comments"]] + [0]) + 1
            frame = f"r{d['stage']}{d['round']}-c{cid}.jpg"
            grab(src["video"], t, folder / "review" / frame)
            images = []   # pasted or dropped pictures: only these types, under 15 MB each, at most 6
            for i, im in enumerate(imgs[:6]):
                m = re.match(r"data:image/(png|jpeg|gif|webp);base64,(.+)", im if isinstance(im, str) else "", re.S)
                if not m:
                    continue
                try:
                    raw = base64.b64decode(m[2])
                except ValueError:
                    continue
                if len(raw) > MAX_IMAGE:
                    continue
                name = f"r{d['stage']}{d['round']}-c{cid}-img{i + 1}.{'jpg' if m[1] == 'jpeg' else m[1]}"
                (folder / "review" / name).write_bytes(raw)
                images.append(name)
            c = {"id": cid, "round": d["round"], "stage": d["stage"], "t": round(t, 2), "alt": alt,
                 "t_end": round(te, 2) if te is not None else None, "text": text,
                 "words": words_at(src.get("transcript"), t, te if te is not None else t),
                 "card": card_at(d.get("plan"), t) if d["stage"] == "edit" else None,
                 "frame": frame, "images": images, "status": "open", "reply": None, "new_t": None, "at": now()}
            update(rj, lambda d: d["comments"].append(c))
            return self.send(200, c)
    return H


def running(folder):
    """The URL of this folder's server if one answers, else None."""
    f = folder / "review" / ".server"
    try:
        url = f.read_text(encoding="utf-8").strip()
        s = json.loads(urllib.request.urlopen(url.replace("/?t=", "/state?t="), timeout=2).read())
        return url if s.get("folder") == str(folder) else None
    except (OSError, ValueError):
        return None


def serve(folder, port=0, open_browser=True):
    """(server, url). An already running server for this folder is reused: (None, its url)."""
    url = running(folder)
    if url:
        if open_browser:
            webbrowser.open(url)
        return None, url
    token = secrets.token_urlsafe(32)
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(folder, token))
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={token}"
    (folder / "review" / ".server").write_text(url, encoding="utf-8")
    if open_browser:
        webbrowser.open(url)
    return srv, url


# ---------------------------------------------------------------- cli
def cmd_start(a, folder):
    (folder / "review").mkdir(parents=True, exist_ok=True)
    rj = folder / "review.json"
    d = load(rj) if rj.exists() else {"folder": str(folder), "name": folder.name, "comments": [], "events": []}
    d.update(folder=str(folder), stage=a.stage, round=d.get("round", 0) + 1 if d.get("stage") == a.stage else 1,
             video=str(Path(a.video).resolve()), note=a.note or "", sent=False, alts=[],
             transcript=str(Path(a.transcript).resolve()) if a.transcript else None,
             plan=str(Path(a.plan).resolve()) if a.plan else None, vertical=probe(a.video), label=a.name)
    log_round(d)
    save(rj, d)
    print(f"{rj}: {stage_name(d['stage'])}, round {d['round']}")


def cmd_round(a, folder):
    def f(d):
        if a.stage and a.stage != d["stage"]:
            d["stage"], d["round"] = a.stage, 1
        else:
            d["round"] += 1
        d["video"] = str(Path(a.video).resolve())
        d["vertical"] = probe(a.video)
        if a.transcript:
            d["transcript"] = str(Path(a.transcript).resolve())
        if a.plan:
            d["plan"] = str(Path(a.plan).resolve())
        d["note"], d["sent"], d["alts"] = a.note or "", False, []   # versions belong to a round: add them again
        d["label"] = a.name or d.get("label")
        for x in d.get("activity", []):
            x["done"] = True
        log_round(d)
        return d
    d = update(folder / "review.json", f)
    still = [str(c["id"]) for c in d["comments"]
             if c["status"] == "open" and c["stage"] == d["stage"] and c["round"] < d["round"]]
    print(f"{stage_name(d['stage'])}, round {d['round']}" + (f"; still open: {', '.join(still)}" if still else ""))
    if not running(folder):
        print("the page is not running: start it with `serve`")


def cmd_resolve(a, folder):
    def f(d):
        for c in d["comments"]:
            if c["id"] == a.id:
                c["status"] = a.status
                if a.reply is not None:
                    c["reply"] = a.reply
                if a.new_t is not None:
                    c["new_t"] = a.new_t
                return c
        sys.exit(f"no note {a.id}")
    c = update(folder / "review.json", f)
    print(f"#{c['id']} {c['status']}")


def cmd_status(a, folder):
    """One step of what Claude is doing for the next round. Each new step closes the one before."""
    def f(d):
        act = d.setdefault("activity", [])
        for x in act:
            x["done"] = True
        if not a.done:
            act.append({"text": a.text, "at": now(), "round": d["round"], "done": False,
                        "log": str(Path(a.log).resolve()) if a.log else None})
        d["activity"] = act[-30:]
    update(folder / "review.json", f)
    print("done" if a.done else f"status: {a.text}")


def cmd_alt(a, folder):
    """Add (or replace) another video in this round: the other aspect, another clip."""
    def f(d):
        d["alts"] = [x for x in d.get("alts") or [] if x["name"] != a.name] + [
            {"name": a.name, "video": str(Path(a.video).resolve()),
             "transcript": str(Path(a.transcript).resolve()) if a.transcript else None}]
        log_round(d)
        return d
    d = update(folder / "review.json", f)
    print(f"round {d['round']}: {1 + len(d['alts'])} videos "
          f"({', '.join([d.get('label') or 'main'] + [x['name'] for x in d['alts']])})")


def cmd_wait(folder, poll=1.0):
    rj = folder / "review.json"
    beat = folder / "review" / ".listening"
    try:
        while True:
            beat.touch()
            # read only: a write here could drop a note the page saves in the same instant
            if any(not e["handled"] for e in load(rj)["events"]):
                break
            time.sleep(poll)
    finally:
        beat.unlink(missing_ok=True)

    def take(d):
        ev = [e for e in d["events"] if not e["handled"]]
        for e in ev:
            e["handled"] = True
        return ev, d
    ev, d = update(rj, take)
    e = ev[-1]
    r = next((r for r in d.get("rounds", []) if (r["stage"], r["round"]) == (e["stage"], e["round"])), d)
    cs = sorted((c for c in d["comments"] if c["stage"] == e["stage"] and c["round"] == e["round"]), key=lambda c: c["t"])
    print(f"{e['type'].upper()}: {d['name']} {stage_name(e['stage'])}, round {e['round']}, "
          f"{len(cs)} note{'' if len(cs) == 1 else 's'}. video {r['video']}")
    for x in r.get("alts") or []:
        print(f"  also {x['name']}: {x['video']}")
    for c in cs:
        span = fmt(c["t"]) + (f"-{fmt(c['t_end'])}" if c["t_end"] is not None else "")
        ver = " [all videos]" if c.get("alt") == "*" else f" [{c['alt']}]" if c.get("alt") else (
            f" [{r.get('label') or 'main'}]" if r.get("alts") else "")
        k = c.get("card")
        card = f" [card {k['i']} {k['kind']} '{k['trigger_word'] or ''}']" if k else ""
        print(f"#{c['id']} {span} ({c['t']}s){ver}{card}: {c['text']}\n    said: \"{c['words']}\""
              f"\n    frame: {folder / 'review' / c['frame']}"
              + "".join(f"\n    image: {folder / 'review' / x}" for x in c.get("images") or []))
    return e["type"]


def demo():
    import contextlib
    import io
    import shutil
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="review_demo_"))
    vid = tmp / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=6",
                    "-f", "lavfi", "-i", "sine=duration=6", "-shortest", "-pix_fmt", "yuv420p", str(vid)], check=True)
    tr = tmp / "words.json"
    tr.write_text(json.dumps([{"text": "hello", "start": 1.0, "end": 1.4, "type": "word"},
                              {"text": " ", "start": 1.4, "end": 1.5, "type": "spacing"},
                              {"text": "world", "start": 1.5, "end": 2.0, "type": "word"},
                              {"text": "later", "start": 5.0, "end": 5.5, "type": "word"}]))
    pl = tmp / "plan.json"
    pl.write_text(json.dumps({"cards": [{"src": "images/a.png", "start": 3.5, "end": 5.5, "trigger_word": "later"}]}))
    folder = tmp / "edits" / "demo"
    ns = argparse.Namespace
    cmd_start(ns(video=str(vid), stage="cut", transcript=str(tr), plan=None, note=None, name=None), folder)
    assert load(folder / "review.json")["vertical"] is False
    srv, url = serve(folder, 0, open_browser=False)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base, tok = url.split("/?t=")

    def get(p, **h):
        return urllib.request.urlopen(urllib.request.Request(base + p + ("&" if "?" in p else "?") + "t=" + tok, headers=h))

    def post(p, b):
        return json.loads(urllib.request.urlopen(urllib.request.Request(
            base + p + "?t=" + tok, json.dumps(b).encode(), method="POST")).read())

    def waited():
        o = io.StringIO()
        with contextlib.redirect_stdout(o):
            cmd_wait(folder, poll=0.01)
        return o.getvalue()

    # no token: nothing reads or writes
    for p, data in (("/", None), ("/state", None), ("/video", None), ("/event", b'{"type":"send"}')):
        try:
            urllib.request.urlopen(urllib.request.Request(base + p, data, method="POST" if data else "GET"))
            raise AssertionError(f"{p} answered without the token")
        except urllib.error.HTTPError as e:
            assert e.code == 403, (p, e.code)
    assert not load(folder / "review.json")["events"]
    assert running(folder) == url and serve(folder, 0, open_browser=False) == (None, url)
    r = get("/")
    assert b"review" in r.read() and "HttpOnly" in r.headers["Set-Cookie"]
    r = get("/video?k=cut-1", Range="bytes=10-19")
    assert r.status == 206 and len(r.read()) == 10 and r.headers["Content-Range"].endswith(f"/{vid.stat().st_size}")
    # a note: its words, its frame still; an attached image (a non-image is dropped); delete
    c = post("/comment", {"t": 1.2, "t_end": None, "text": "cut the hello"})
    assert c["words"] == "hello world" and c["card"] is None and (folder / "review" / c["frame"]).stat().st_size > 0
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJ"
           "RU5ErkJggg==")
    ci = post("/comment", {"t": 1.5, "text": "", "images": [png, "data:text/html;base64,PGI+"]})
    assert ci["images"] == [f"rcut1-c{ci['id']}-img1.png"]
    assert get("/frames/" + ci["images"][0]).headers["Content-Type"] == "image/png"
    post("/delete", {"id": ci["id"]})
    assert [x["id"] for x in load(folder / "review.json")["comments"]] == [c["id"]]
    assert not json.loads(get("/state").read())["listening"]
    # send: wait prints the note and its still; the page says the round is with Claude
    post("/event", {"type": "send"})
    out = waited()
    assert out.startswith("SEND: demo the cut, round 1, 1 note.") and "#1 0:01.2" in out and 'said: "hello world"' in out, out
    assert str(folder / "review" / c["frame"]) in out and not (folder / "review" / ".listening").exists()
    try:
        post("/comment", {"t": 2, "text": "too late"})
        raise AssertionError("a note after send")
    except urllib.error.HTTPError as e:
        assert e.code == 409
    # round 2 on the styled edit: the card under a note comes with it, Claude's answer shows
    cmd_round(ns(video=str(vid), stage="edit", transcript=None, plan=str(pl), note=None, name=None), folder)
    cmd_resolve(ns(id=1, status="fixed", reply="cut it", new_t=0.9), folder)
    c2 = post("/comment", {"t": 4.0, "t_end": 5.0, "text": "card smaller"})
    assert c2["card"]["trigger_word"] == "later" and c2["stage"] == "edit" and c2["round"] == 1, c2
    s = json.loads(get("/state").read())
    assert s["comments"][0]["status"] == "fixed" and not s["sent"] and [r["stage"] for r in s["rounds"]] == ["cut", "edit"]
    # another video in the round: its own notes, notes on every video, scope switched and back
    cmd_alt(ns(name="wide", video=str(vid), transcript=str(tr)), folder)
    assert get("/video?k=edit-1&alt=wide").status == 200
    c3 = post("/comment", {"t": 5.1, "text": "louder here", "alt": "wide"})
    assert c3["alt"] == "wide" and c3["words"] == "later"
    c4 = post("/comment", {"t": 1.0, "text": "on all of them", "alt": "*"})
    post("/scope", {"id": c3["id"], "alt": "*"})
    assert next(x for x in load(folder / "review.json")["comments"] if x["id"] == c3["id"])["alt"] == "*"
    post("/scope", {"id": c3["id"], "alt": "wide"})
    # live progress from a render log
    lg = tmp / "r.log"
    lg.write_text("Rendered 10/40\nRendered 30/40\n")
    cmd_status(ns(text="rendering", log=str(lg), done=False), folder)
    st = json.loads(get("/state").read())["activity"][-1]
    assert st["text"] == "rendering" and st["pct"] == 75 and not st["done"], st
    post("/event", {"type": "approve"})
    out = waited()
    assert out.startswith("APPROVE: demo the edit, round 1, 3 notes.") and f"also wide: {vid.resolve()}" in out, out
    assert f"#{c4['id']} 0:01.0 (1.0s) [all videos]: on all of them" in out, out
    assert f"#{c3['id']} 0:05.1 (5.1s) [wide] [card 0 image 'later']: louder here" in out, out
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(tmp, ignore_errors=True)
    print("review demo ok")


def main():
    if sys.argv[1:2] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="the edit folder: edits/<name> (or product/<name>, clips/<name>)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("start")
    s.add_argument("--video", required=True)
    s.add_argument("--stage", choices=["cut", "edit"], default="edit")
    s.add_argument("--transcript", help="words timed to this video (edits/<name>/words.json)")
    s.add_argument("--plan", help="plan.json, so each note names the card on screen")
    s.add_argument("--name", help="what to call this video when the round has others (default main)")
    s.add_argument("--note")
    s = sp.add_parser("serve")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--no-open", action="store_true", help="do not open the browser (tests, headless checks)")
    sp.add_parser("wait")
    s = sp.add_parser("round")
    s.add_argument("--video", required=True)
    s.add_argument("--stage", choices=["cut", "edit"])
    s.add_argument("--transcript")
    s.add_argument("--plan")
    s.add_argument("--note")
    s.add_argument("--name")
    s = sp.add_parser("status")
    s.add_argument("text", nargs="?", default="")
    s.add_argument("--log", help="a render log; the page shows the last N/M in it as progress")
    s.add_argument("--done", action="store_true")
    s = sp.add_parser("alt")
    s.add_argument("name")
    s.add_argument("--video", required=True)
    s.add_argument("--transcript")
    s = sp.add_parser("resolve")
    s.add_argument("id", type=int)
    s.add_argument("status", choices=["fixed", "wontfix", "open"])
    s.add_argument("--reply")
    s.add_argument("--new-t", type=float, help="where the note's moment is in the new render")
    a = ap.parse_args()
    folder = Path(a.folder).resolve()
    if a.cmd != "start" and not (folder / "review.json").exists():
        sys.exit(f"no review in {folder}: run `start` first")
    if a.cmd == "start":
        if not Path(a.video).exists():
            sys.exit(f"no such file: {a.video}")
        cmd_start(a, folder)
    elif a.cmd == "serve":
        srv, url = serve(folder, a.port, open_browser=not a.no_open)
        print(url, flush=True)
        if srv:
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
        else:
            print("already serving this edit" + ("" if a.no_open else "; opened it"))
    elif a.cmd == "wait":
        cmd_wait(folder)
    elif a.cmd == "round":
        cmd_round(a, folder)
    elif a.cmd == "resolve":
        cmd_resolve(a, folder)
    elif a.cmd == "alt":
        cmd_alt(a, folder)
    elif a.cmd == "status":
        cmd_status(a, folder)


if __name__ == "__main__":
    main()
