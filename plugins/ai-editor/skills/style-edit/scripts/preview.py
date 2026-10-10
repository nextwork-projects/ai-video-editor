#!/usr/bin/env python3
"""Live preview of an edit in the browser, before the render. Stdlib only (plus the installed renderer).

    python3 preview.py edits/NAME [--plan plan.json] [--port 0] [--no-open]   serve the page, wait for Render
    python3 preview.py apply edits/NAME [--plan plan.json]                    write overrides.json into the plan
    python3 preview.py demo                                                   self-check

The page plays the real StyleEdit composition (remotion/src) with @remotion/player and the plan's own
props. Every change on the page is a small diff in edits/NAME/overrides.json, logged to
corrections.jsonl (what, from, to) for the taste skill. Render writes preview-done.json and stops the
server. plan.py applies overrides.json after planning (apply_overrides below), so a re-plan keeps them.

overrides.json:
  {"plan": "plan.json",
   "cards": {"<trigger_word>@<planned start>": {"start": s, "end": s, "box": [x, y, w, h],
             "src": "images/x.png", "size": [w, h], "deleted": true}},
   "words": {"<word start>": "fixed text"},          ("" deletes the word)
   "sfx":   {"<cue event time>": gain_db}}
"""
import argparse
import array
import datetime
import hmac
import json
import mimetypes
import re
import secrets
import shutil
import subprocess
import sys
import threading
import wave
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[2]                       # plugins/ai-editor
PAGE = PLUGIN / "preview"
MATCH_S = 0.75        # a re-planned card still matches its override when its start moved less than this
CUE_WINDOW = (-0.05, 0.45)   # a card's own sound cue lands this close after its start (plan.py CARD_LEAD_S 0.1)
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif")


def card_key(c):
    return c.get("override") or f"{c.get('trigger_word', '')}@{c['start']:.3f}"


def gained(edit_dir, src, db):
    """The cue file at db dB, written next to it once (16-bit PCM, as sfx.py writes the kit)."""
    base = re.sub(r"\.g[+-][\d.]+(?=\.wav$)", "", src)
    if not db:
        return base
    out = re.sub(r"\.wav$", f".g{db:+g}.wav", base)
    dst, srcf = Path(edit_dir) / out, Path(edit_dir) / base
    if not dst.exists() and srcf.exists():
        with wave.open(str(srcf)) as w:
            p, frames = w.getparams(), w.readframes(w.getnframes())
        if p.sampwidth != 2:
            print(f"warning: {base} is not 16-bit PCM, level left as is", file=sys.stderr)
            return base
        a, k = array.array("h", frames), 10 ** (db / 20)
        if sys.byteorder == "big":
            a.byteswap()
        a = array.array("h", (max(-32768, min(32767, int(v * k))) for v in a))
        if sys.byteorder == "big":
            a.byteswap()
        with wave.open(str(dst), "wb") as w:
            w.setparams(p)
            w.writeframes(a.tobytes())
    return out


def apply_overrides(plan, edit_dir, plan_name=None):
    """plan with edits/NAME/overrides.json applied. Idempotent: applying to an already applied plan
    changes nothing, so it is safe after plan.py and again on the preview server."""
    f = Path(edit_dir) / "overrides.json"
    if not f.exists():
        return plan
    ov = json.loads(f.read_text(encoding="utf-8"))
    if plan_name and ov.get("plan") and ov["plan"] != plan_name:
        print(f"warning: overrides.json is for {ov['plan']}, not {plan_name}: not applied", file=sys.stderr)
        return plan
    cues = plan.get("sfx") or []
    for key, db in (ov.get("sfx") or {}).items():
        for c in cues:
            if c.get("override") == key or (not c.get("override") and abs(c.get("event", c["t"]) - float(key)) < 0.05):
                c.update(override=key, gain_db=db, src=gained(edit_dir, c["src"], db))
    for key, o in (ov.get("cards") or {}).items():
        word, at = key.rsplit("@", 1)
        tagged = [c for c in plan["cards"] if c.get("override") == key]
        near = sorted((c for c in plan["cards"] if not c.get("override") and c.get("trigger_word", "") == word
                       and abs(c["start"] - float(at)) < MATCH_S), key=lambda c: abs(c["start"] - float(at)))
        c = (tagged or near or [None])[0]
        if c is None:
            continue
        own = [q for q in cues if CUE_WINDOW[0] <= q.get("event", q["t"]) - c["start"] <= CUE_WINDOW[1]]
        if o.get("deleted"):
            plan["cards"].remove(c)
            cues[:] = [q for q in cues if q not in own]
            continue
        d = o.get("start", c["start"]) - c["start"]
        for q in own:
            q["t"], q["event"] = round(max(0.0, q["t"] + d), 3), round(q.get("event", q["t"]) + d, 3)
        for k, v in o.items():
            if v is None:
                c.pop(k, None)
            else:
                c[k] = v
        c["override"] = key
    words = ov.get("words") or {}
    if words:
        for ch in plan["captions"]["chunks"]:
            for w in ch["words"]:
                k = f"{w['start']:.3f}"
                if k in words:
                    w["text"] = words[k]
            ch["words"] = [w for w in ch["words"] if w["text"].strip()]
            ch["text"] = " ".join(w["text"] for w in ch["words"])
        plan["captions"]["chunks"] = [ch for ch in plan["captions"]["chunks"] if ch["words"]]
    return plan


def regions(plan, edit_dir):
    """Per card: where it may be dragged to (plan.py free_regions round the head while it is up) and the head."""
    sys.path.insert(0, str(HERE))
    from plan import SAFE, free_regions, head_during
    aspect = "9:16" if plan["height"] > plan["width"] else "16:9"
    fj = Path(edit_dir) / "face.json"
    face = json.loads(fj.read_text(encoding="utf-8")) if fj.exists() else None
    l, t, r, b = SAFE[aspect]
    cap_y = plan["captions"]["style"].get("y_pct", 74)
    for c in plan["cards"]:
        hd = face and head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        c["_key"] = card_key(c)
        c["_head"] = [hd[0], hd[1], hd[2] - hd[0], hd[3] - hd[1]] if hd else None
        c["_regions"] = free_regions(hd, cap_y, aspect) if hd else [[l, t, 100 - l - r, 100 - t - b]]
    return face


class Session:
    def __init__(self, edit, plan_name):
        self.edit, self.plan_name = edit, plan_name
        self.tag = Path(plan_name).stem[len("plan"):]
        self.lock = threading.Lock()
        self.changes = []

    def ov_path(self):
        return self.edit / "overrides.json"

    def overrides(self):
        p = self.ov_path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"plan": self.plan_name, "cards": {}, "words": {}, "sfx": {}}

    def state(self):
        plan = json.loads((self.edit / self.plan_name).read_text(encoding="utf-8"))
        plan = apply_overrides(plan, self.edit, self.plan_name)
        face = regions(plan, self.edit)
        imgs = sorted(f"images/{p.name}" for p in (self.edit / "images").glob("*") if p.suffix.lower() in IMAGE_EXT)
        ov = self.overrides()
        n = sum(len(ov.get(k) or {}) for k in ("cards", "words", "sfx"))
        return {"name": self.edit.name, "planName": self.plan_name, "plan": plan, "images": imgs,
                "face": face, "overrides": ov, "overrideCount": n, "sessionChanges": len(self.changes)}

    def change(self, ch):
        """ch: {kind: card|word|sfx, key, set (card) | to (word, sfx), from, action (move, trim, ...), text}"""
        with self.lock:
            ov = self.overrides()
            ov["plan"] = self.plan_name
            kind, key = ch["kind"], str(ch["key"])
            if kind == "card":
                ov.setdefault("cards", {}).setdefault(key, {}).update(ch["set"])
                to = ch["set"]
            elif kind in ("word", "sfx"):
                ov.setdefault(kind + "s" if kind == "word" else kind, {})[key] = ch["to"]
                to = ch["to"]
            else:
                raise ValueError(kind)
            self.ov_path().write_text(json.dumps(ov, indent=1), encoding="utf-8")
            row = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "source": "preview", "plan": self.plan_name,
                   "change": f"{kind}.{ch.get('action', 'set')}", "target": key, "from": ch.get("from"), "to": to,
                   "what": ch.get("text", "")}
            with open(self.edit / "corrections.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            self.changes.append(row)

    def done(self):
        summary = {"plan": self.plan_name, "overrides": "overrides.json", "changes": len(self.changes),
                   "by_kind": {}, "lines": [c["what"] or f"{c['change']} {c['target']}" for c in self.changes],
                   "at": datetime.datetime.now().isoformat(timespec="seconds")}
        for c in self.changes:
            summary["by_kind"][c["change"]] = summary["by_kind"].get(c["change"], 0) + 1
        (self.edit / "preview-done.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
        return summary

    def media(self, rel):
        """A file the plan names, inside the edit folder. The video comes from edit.py's render copy
        (output size, a keyframe every 15 frames, so seeking is quick) when there is one."""
        target = (self.edit / rel).resolve()
        if not target.is_relative_to(self.edit) or not target.is_file():
            return None
        plan_video = json.loads((self.edit / self.plan_name).read_text(encoding="utf-8"))["video"]
        proxy = self.edit / f".render{self.tag}" / rel
        if rel == plan_video and proxy.exists() and proxy.stat().st_mtime >= target.stat().st_mtime:
            return proxy
        return target


def handler(sess, bundle, stop, token):
    """Every request needs the token: ?t=<token> on the page's URL, then an HttpOnly, SameSite=Strict cookie the
    page's own requests carry. Another site open in the browser (or a DNS-rebound name) has neither: 403."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def cookie_name(self):
            return f"ave-preview-{self.server.server_address[1]}"   # cookies ignore ports: one per server

        def authorized(self):
            from urllib.parse import parse_qs, urlsplit
            from http.cookies import SimpleCookie
            q = parse_qs(urlsplit(self.path).query).get("t", [""])[0]
            c = SimpleCookie()
            try:
                c.load(self.headers.get("Cookie") or "")
            except Exception:
                pass
            got = c[self.cookie_name()].value if self.cookie_name() in c else ""
            return any(hmac.compare_digest(v.encode(), token.encode()) for v in (q, got) if v)

        def body(self, data, ctype="application/json", cookie=False):
            raw = data if isinstance(data, bytes) else json.dumps(data).encode()
            self.send_response(200)
            if cookie:
                self.send_header("Set-Cookie", f"{self.cookie_name()}={token}; Path=/; HttpOnly; SameSite=Strict")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def file(self, path):
            size = path.stat().st_size
            start, end = 0, size - 1
            m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
            if m and (m[1] or m[2]):
                start, end = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (size - int(m[2]), size - 1)
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(end - start + 1))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                with open(path, "rb") as f:
                    f.seek(start)
                    left = end - start + 1
                    while left > 0:
                        chunk = f.read(min(left, 1 << 20))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if not self.authorized():
                return self.send_error(403, "open the preview with the URL preview.py printed")
            p = self.path.split("?")[0]
            if p == "/":
                return self.body((PAGE / "index.html").read_bytes(), "text/html; charset=utf-8", cookie=True)
            if p == "/app.js":
                return self.body(bundle.read_bytes(), "text/javascript")
            if p == "/api/state":
                return self.body(sess.state())
            if p.startswith("/media/"):
                from urllib.parse import unquote
                f = sess.media(unquote(p[len("/media/"):]))
                if f:
                    return self.file(f)
            self.send_error(404)

        def do_POST(self):
            if not self.authorized():
                return self.send_error(403, "open the preview with the URL preview.py printed")
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if self.path == "/api/change":
                try:
                    sess.change(data)
                except (KeyError, ValueError) as e:
                    return self.send_error(400, str(e))
                return self.body(sess.state())
            if self.path == "/api/done":
                out = sess.done()
                self.body(out)
                threading.Timer(0.5, stop).start()
                return
            self.send_error(404)
    return H


def build_bundle():
    """Bundle preview/app.tsx with the renderer's own esbuild and node_modules (~/.ai-video-editor/remotion),
    against the same src/ the render uses."""
    sys.path.insert(0, str(HERE))
    from edit import REMOTION, sync_renderer
    sync_renderer()
    if not (REMOTION / "node_modules" / "@remotion" / "player").exists():
        sys.exit(f"ERROR: @remotion/player missing in {REMOTION}/node_modules. Run the setup skill's remotion step again.")
    dst = REMOTION / "preview"
    dst.mkdir(exist_ok=True)
    for f in ("app.tsx", "Sfx.tsx", "build.mjs"):
        shutil.copy2(PAGE / f, dst / f)
    subprocess.run(["node", str(dst / "build.mjs")], cwd=REMOTION, check=True)
    return dst / "dist" / "app.js"


def make_server(sess, bundle, port):
    """(server, url, token): this computer only (127.0.0.1), a fresh random token in the URL."""
    token = secrets.token_urlsafe(32)
    srv = ThreadingHTTPServer(("127.0.0.1", port), None)
    srv.RequestHandlerClass = handler(sess, bundle, srv.shutdown, token)
    srv.sess = sess
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/?t={token}", token


def serve(edit, plan_name, port, open_page):
    if not (edit / plan_name).exists():
        sys.exit(f"ERROR: no {plan_name} in {edit}. Run plan.py first.")
    srv, url, _ = make_server(Session(edit, plan_name), build_bundle(), port)
    sess = srv.sess
    print(f"preview: {url}  (Ctrl+C to stop; the page's Render button stops it too)", flush=True)
    if open_page:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    done = edit / "preview-done.json"
    if sess.changes or done.exists():
        print(f"{len(sess.changes)} change(s) this session in {edit / 'overrides.json'}")
        for c in sess.changes:
            print(f"  {c['what'] or c['change']}")


def apply_cmd(edit, plan_name):
    p = edit / plan_name
    plan = apply_overrides(json.loads(p.read_text(encoding="utf-8")), edit, plan_name)
    p.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    print(f"{p}: overrides applied, {len(plan['cards'])} cards, {len(plan.get('sfx') or [])} cues")


def demo():
    import tempfile
    d = Path(tempfile.mkdtemp())
    (d / ".sfx").mkdir()
    with wave.open(str(d / ".sfx" / "pop.wav"), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(48000)
        w.writeframes(array.array("h", [1000, -1000, 20000]).tobytes())

    def base():
        return {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 300, "video": "cut.mp4",
                "captions": {"style": {"y_pct": 74}, "chunks": [
                    {"text": "jev is", "start": 0, "end": 1, "words": [{"text": "jev", "start": 0.0, "end": 0.4},
                                                                        {"text": "is", "start": 0.4, "end": 1.0}]},
                    {"text": "um", "start": 1, "end": 1.2, "words": [{"text": "um", "start": 1.0, "end": 1.2}]}]},
                "cards": [{"src": "images/a.png", "trigger_word": "jev", "start": 0.5, "end": 3.0, "box": [4, 10, 92, 20]},
                          {"src": "images/b.png", "trigger_word": "cheap", "start": 5.0, "end": 7.0, "box": [4, 10, 92, 20]}],
                "sfx": [{"t": 0.405, "src": ".sfx/pop.wav", "event": 0.6}, {"t": 5.0, "src": ".sfx/pop.wav", "event": 5.1}]}
    plan = base()
    assert apply_overrides(plan, d) is plan                                  # no overrides.json: untouched
    (d / "overrides.json").write_text(json.dumps({
        "plan": "plan.json",
        "cards": {"jev@0.500": {"start": 1.5, "end": 4.0, "box": [3, 40, 30, 20], "marks": None},
                  "cheap@5.000": {"deleted": True}},
        "words": {"0.000": "Jev", "1.000": ""},
        "sfx": {"0.600": -6}}), encoding="utf-8")
    got = apply_overrides(base(), d, "plan.json")
    c = got["cards"]
    assert len(c) == 1 and c[0]["start"] == 1.5 and c[0]["box"] == [3, 40, 30, 20] and c[0]["override"] == "jev@0.500", c
    assert [q["event"] for q in got["sfx"]] == [1.6], got["sfx"]               # its cue moved with it, the deleted card's went
    assert got["sfx"][0]["src"] == ".sfx/pop.g-6.wav" and (d / ".sfx" / "pop.g-6.wav").exists()
    with wave.open(str(d / ".sfx" / "pop.g-6.wav")) as w:
        assert array.array("h", w.readframes(3))[2] == int(20000 * 10 ** (-6 / 20))
    assert [ch["text"] for ch in got["captions"]["chunks"]] == ["Jev is"]      # "" deletes the word, then the empty chunk
    again = apply_overrides(json.loads(json.dumps(got)), d, "plan.json")
    assert again == got, "apply_overrides must be idempotent"
    assert apply_overrides(base(), d, "plan-split.json")["cards"][0]["start"] == 0.5   # another plan's overrides stay out
    s = Session(d, "plan.json")
    (d / "plan.json").write_text(json.dumps(base()), encoding="utf-8")
    s.change({"kind": "word", "key": "0.400", "from": "is", "to": "was", "action": "fix", "text": "caption 'is' -> 'was'"})
    assert json.loads((d / "overrides.json").read_text(encoding="utf-8"))["words"]["0.400"] == "was"
    row = json.loads((d / "corrections.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert row["change"] == "word.fix" and row["from"] == "is" and row["to"] == "was"
    st = s.state()
    assert st["plan"]["cards"][0]["_regions"] and st["overrideCount"] == 6, st["overrideCount"]
    assert s.done()["changes"] == 1 and (d / "preview-done.json").exists()
    assert s.media("../../etc/passwd") is None
    # the server: 127.0.0.1 only, and every request (page, state, media, writes) needs the URL's token
    import urllib.request, urllib.error
    (d / "app.js").write_text("// bundle", encoding="utf-8")
    srv, url, token = make_server(s, d / "app.js", 0)
    assert srv.server_address[0] == "127.0.0.1" and f"?t={token}" in url and len(token) >= 32, url
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = url.split("?")[0]

    def hit(path, data=None, headers=None):
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path.lstrip("/"), data=data, headers=headers or {})) as r:
                return r.status, r.headers.get("Set-Cookie") or ""
        except urllib.error.HTTPError as e:
            return e.code, ""
    before = (d / "overrides.json").read_text(encoding="utf-8")
    for path, data in (("/", None), ("/app.js", None), ("/api/state", None), ("/api/state?t=wrong", None),
                       ("/api/change", b'{"kind": "word", "key": "0.000", "to": "x"}'), ("/api/done", b"{}")):
        assert hit(path, data)[0] == 403, path
    assert (d / "overrides.json").read_text(encoding="utf-8") == before, "a request without the token wrote"
    code, cookie = hit(f"/?t={token}")
    assert code == 200 and "HttpOnly" in cookie and "SameSite=Strict" in cookie, cookie
    jar = {"Cookie": cookie.split(";")[0]}
    assert hit("/api/state", headers=jar)[0] == 200 and hit("/app.js", headers=jar)[0] == 200
    assert hit("/api/change", b'{"kind": "word", "key": "0.000", "from": "jev", "to": "Jev"}', jar)[0] == 200
    srv.shutdown()
    srv.server_close()
    shutil.rmtree(d)
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    args = sys.argv[1:]
    cmd = args.pop(0) if args and args[0] == "apply" else "serve"
    ap = argparse.ArgumentParser()
    ap.add_argument("edit")
    ap.add_argument("--plan", help="default: the plan overrides.json names, else plan.json")
    ap.add_argument("--port", type=int, default=0, help="default: any free port")
    ap.add_argument("--no-open", action="store_true", help="print the URL, do not open the browser")
    a = ap.parse_args(args)
    edit = Path(a.edit).resolve()
    ov = edit / "overrides.json"
    plan_name = a.plan or (json.loads(ov.read_text(encoding="utf-8")).get("plan") if ov.exists() else None) or "plan.json"
    if cmd == "apply":
        return apply_cmd(edit, plan_name)
    serve(edit, plan_name, a.port, not a.no_open)


if __name__ == "__main__":
    main()
