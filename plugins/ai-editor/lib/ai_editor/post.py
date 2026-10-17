#!/usr/bin/env python3
"""Post a finished video to the user's own social accounts through Zernio. Stdlib only.

    python3 post.py accounts                    every connected account, as JSON (id, platform, username)
    python3 post.py connect <platform>          a sign-in link that adds one more account (run again for another)
    python3 post.py send <video> --to <id,id> --caption "..." [--title "..."] [--at 2026-10-20T09:00 --tz America/Chicago] [--trial]
    python3 post.py status <post id> [--wait]   each account's state and live link
    python3 post.py demo                        self-check (no network)

The key is ZERNIO_API_KEY in the editor's key file (keys.py; Settings, Auto-post your videos). Each user connects their
own accounts to their own Zernio, any number per platform: every one is its own id, and `send --to`
takes the ids, so two TikToks are two ids. Exit 2: no key. Exit 1: Zernio refused, with its message.
"""
import argparse
import hashlib
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import keys  # noqa: E402
import net  # noqa: E402

API = "https://zernio.com/api/v1"
SIGNUP = "https://zernio.link/maximus-soares"
# Settings shows a Connect button for each; Zernio connects more (zernio.com/docs), `connect` takes any of them
PLATFORMS = ("instagram", "tiktok", "youtube", "facebook", "linkedin", "twitter", "threads")
# TikTok's required settings: the post skill shows the post and asks before it sends (the consent is the user's)
TIKTOK = {"privacy_level": "PUBLIC_TO_EVERYONE", "allow_comment": True, "allow_duet": True, "allow_stitch": True,
          "content_preview_confirmed": True, "express_consent_given": True}


class NoKey(Exception):
    pass


class Refused(Exception):
    pass


def _key():
    k = keys.get("zernio")[0]
    if not k:
        raise NoKey(f"No Zernio key. Make a Zernio account at {SIGNUP}, then paste the key in Settings, Auto-post your videos.")
    return k


def _req(method, path, body=None, headers=None):
    """One call to Zernio's API: the parsed JSON, or Refused with its message."""
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
                                          "User-Agent": "ai-video-editor", **(headers or {})})
    try:
        with net.urlopen(req, 60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            msg = json.loads(raw).get("error") or json.loads(raw).get("message") or raw
        except ValueError:
            msg = raw
        if e.code in (401, 403):
            msg = "Zernio rejected the key. Paste it again in Settings, Auto-post your videos."
        raise Refused(f"HTTP {e.code}: {str(msg)[:300]}")
    except (urllib.error.URLError, OSError) as e:
        raise Refused(net.friendly(e))


def accounts():
    """Every connected account, active ones first."""
    out = [{"id": a["_id"], "platform": a["platform"], "username": a.get("username") or a.get("displayName") or "",
            "name": a.get("displayName") or "", "picture": a.get("profilePicture") or "",
            "profile": (a.get("profileId") or {}).get("name") if isinstance(a.get("profileId"), dict) else None,
            "active": a.get("isActive", True)} for a in _req("GET", "/accounts").get("accounts") or []]
    return sorted(out, key=lambda a: (not a["active"], PLATFORMS.index(a["platform"]) if a["platform"] in PLATFORMS else 99, a["username"]))


def profile_id():
    """The profile new accounts land in: Zernio's default one, made if the user has none."""
    ps = _req("GET", "/profiles").get("profiles") or []
    p = next((p for p in ps if p.get("isDefault")), ps[0] if ps else None)
    return p["_id"] if p else _req("POST", "/profiles", {"name": "cooked."})["profile"]["_id"]


def connect_url(platform):
    """The sign-in page that adds one account. Zernio shows its own done page; Settings lists it on return."""
    if platform not in PLATFORMS:
        raise Refused(f"{platform}: one of {', '.join(PLATFORMS)}")
    return _req("GET", f"/connect/{platform}?profileId={profile_id()}")["authUrl"]


def upload(video):
    """PUT the file to Zernio's storage (no key on that request); the URL a post uses."""
    video = Path(video)
    ctype = mimetypes.guess_type(video.name)[0] or "video/mp4"
    size = video.stat().st_size
    pre = _req("POST", "/media/presign", {"filename": video.name, "contentType": ctype, "size": size})
    with open(video, "rb") as f:
        req = urllib.request.Request(pre["uploadUrl"], data=f, method="PUT",
                                     headers={"Content-Type": ctype, "Content-Length": str(size)})
        try:
            with net.urlopen(req, 1800):
                pass
        except (urllib.error.URLError, OSError) as e:
            raise Refused(f"upload failed: {net.friendly(e)}")
    return pre["publicUrl"]


def body(media_url, to, caption, title=None, at=None, tz=None, trial=False):
    """The POST /posts body: one platforms entry per account id, so two accounts on one platform both post."""
    by_id = {a["id"]: a for a in accounts()}
    missing = [i for i in to if i not in by_id]
    if missing:
        raise Refused(f"not a connected account: {', '.join(missing)}. `post.py accounts` lists them.")
    plats = []
    for i in to:
        p = {"platform": by_id[i]["platform"], "accountId": i}
        if p["platform"] == "youtube":
            p["platformSpecificData"] = {"title": (title or caption.splitlines()[0])[:100], "visibility": "public", "madeForKids": False}
        if p["platform"] == "instagram" and trial:
            p["platformSpecificData"] = {"trialParams": {"graduationStrategy": "SS_PERFORMANCE"}}
        plats.append(p)
    b = {"content": caption, "mediaItems": [{"type": "video", "url": media_url}], "platforms": plats}
    if any(p["platform"] == "tiktok" for p in plats):
        b["tiktokSettings"] = TIKTOK
    if at:
        b.update(scheduledFor=at, timezone=tz or "UTC")
    else:
        b["publishNow"] = True
    return b


def send(video, to, caption, **kw):
    b = body(upload(video), to, caption, **kw)
    # the same video, accounts and words: a retry returns the first post, never a second one
    idem = hashlib.sha256(json.dumps([str(Path(video).resolve()), to, caption, kw.get("at")]).encode()).hexdigest()[:32]
    return _req("POST", "/posts", b, {"Idempotency-Key": idem})["post"]


def status(pid):
    p = _req("GET", f"/posts/{pid}")
    p = p.get("post") or p
    return {"id": pid, "status": p.get("status"),
            "accounts": [{"platform": x.get("platform"), "status": x.get("status"), "url": x.get("platformPostUrl"),
                          "error": x.get("errorMessage") or x.get("error")} for x in p.get("platforms") or []]}


def wait(pid, every=10, limit=900):
    """Until no account is still pending or publishing (scheduled ones stay scheduled)."""
    for _ in range(int(limit / every)):
        s = status(pid)
        if all(a["status"] in ("published", "failed", "scheduled") for a in s["accounts"]):
            return s
        time.sleep(every)
    return s


def demo():
    import tempfile
    calls, real, real_upload = [], _req, upload
    acc = {"accounts": [
        {"_id": "a1", "platform": "tiktok", "username": "max", "isActive": True},
        {"_id": "a2", "platform": "tiktok", "username": "max.two", "isActive": True},
        {"_id": "a3", "platform": "youtube", "username": "maxyt", "isActive": True, "profileId": {"name": "Default"}},
        {"_id": "a4", "platform": "instagram", "username": "maxig", "isActive": False}]}

    def fake(method, path, b=None, headers=None):
        calls.append((method, path, b, headers))
        if path == "/accounts":
            return acc
        if path == "/profiles":
            return {"profiles": [{"_id": "p0"}, {"_id": "p1", "isDefault": True}]}
        if path.startswith("/connect/"):
            return {"authUrl": "https://example.com/auth"}
        if path == "/posts":
            return {"post": {"_id": "post1"}}
        if path == "/posts/post1":
            return {"post": {"status": "published", "platforms": [{"platform": "tiktok", "status": "published", "platformPostUrl": "u"}]}}
        raise AssertionError(path)
    g = globals()
    g["_req"] = fake
    try:
        a = accounts()
        assert [x["id"] for x in a] == ["a1", "a2", "a3", "a4"], a   # active first, then by platform
        assert a[2]["profile"] == "Default" and a[0]["profile"] is None
        assert connect_url("tiktok") == "https://example.com/auth" and calls[-1][1] == "/connect/tiktok?profileId=p1"
        try:
            connect_url("myspace")
            raise AssertionError("unknown platform accepted")
        except Refused:
            pass
        # two TikToks and a YouTube in one post: three entries, TikTok settings once, a YouTube title
        b = body("https://m/x.mp4", ["a1", "a2", "a3"], "first line\nmore", at="2026-10-20T09:00", tz="America/Chicago")
        assert [p["accountId"] for p in b["platforms"]] == ["a1", "a2", "a3"] and "tiktokSettings" in b
        assert b["platforms"][2]["platformSpecificData"]["title"] == "first line" and "publishNow" not in b
        assert b["scheduledFor"] == "2026-10-20T09:00" and b["timezone"] == "America/Chicago"
        b = body("https://m/x.mp4", ["a3"], "c", title="T")
        assert b["publishNow"] and "tiktokSettings" not in b and b["platforms"][0]["platformSpecificData"]["title"] == "T"
        assert body("u", ["a4"], "c", trial=True)["platforms"][0]["platformSpecificData"]["trialParams"]
        try:
            body("u", ["nope"], "c")
            raise AssertionError("an unknown account id was posted to")
        except Refused:
            pass
        assert status("post1")["accounts"][0]["url"] == "u" and wait("post1", every=0.01)["status"] == "published"
        # send: upload goes to the presigned URL, the post carries an idempotency key that repeats on a retry
        g["upload"] = lambda v: "https://m/x.mp4"
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            assert send(f.name, ["a1"], "c")["_id"] == "post1"
            k1 = calls[-1][3]["Idempotency-Key"]
            send(f.name, ["a1"], "c")
            assert calls[-1][3]["Idempotency-Key"] == k1
            send(f.name, ["a1"], "other")
            assert calls[-1][3]["Idempotency-Key"] != k1
    finally:
        g["_req"], g["upload"] = real, real_upload
    # no key: a clear message, not a request
    import os
    with tempfile.TemporaryDirectory() as d:
        old = os.environ.get("AI_EDITOR_HOME")
        os.environ["AI_EDITOR_HOME"] = d
        os.environ.pop("ZERNIO_API_KEY", None)
        try:
            _req("GET", "/accounts")
            raise AssertionError("no key, yet a request was made")
        except NoKey as e:
            assert SIGNUP in str(e)
        finally:
            os.environ.pop("AI_EDITOR_HOME") if old is None else os.environ.__setitem__("AI_EDITOR_HOME", old)
    print("post ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("accounts")
    c = sub.add_parser("connect")
    c.add_argument("platform", choices=PLATFORMS)
    s = sub.add_parser("send")
    s.add_argument("video")
    s.add_argument("--to", required=True, help="account ids, comma separated (post.py accounts)")
    s.add_argument("--caption", required=True)
    s.add_argument("--title", help="YouTube title (default: the caption's first line)")
    s.add_argument("--at", help="local time to post, 2026-10-20T09:00 (default: now)")
    s.add_argument("--tz", help="time zone for --at, e.g. America/Chicago")
    s.add_argument("--trial", action="store_true", help="Instagram: a Trial Reel")
    st = sub.add_parser("status")
    st.add_argument("id")
    st.add_argument("--wait", action="store_true")
    sub.add_parser("demo")
    a = ap.parse_args()
    if a.cmd == "demo":
        return demo()
    try:
        if a.cmd == "accounts":
            out = accounts()
        elif a.cmd == "connect":
            out = {"url": connect_url(a.platform)}
        elif a.cmd == "send":
            p = send(a.video, [x.strip() for x in a.to.split(",") if x.strip()], a.caption,
                     title=a.title, at=a.at, tz=a.tz, trial=a.trial)
            out = wait(p["_id"]) if not a.at else status(p["_id"])
        else:
            out = wait(a.id) if a.wait else status(a.id)
    except NoKey as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    except Refused as e:
        print(f"Zernio: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
