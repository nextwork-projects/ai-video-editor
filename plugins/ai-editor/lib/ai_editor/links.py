#!/usr/bin/env python3
"""Pasted links -> the skill that handles them. Stdlib only.

    python3 links.py route "<the user's message>" [--own]   classify every link, probe video
                                                            lengths with yt-dlp, print the plan
    python3 links.py classify <url>... [--own]              offline: kind, normalised url, action
    python3 links.py fetch <url> <edit dir> [--cookies-from-browser chrome] [--max-gb 4] [--max-height 2160]
    python3 links.py demo                                   self-check on 40+ real URL shapes
    python3 links.py live                                   network check: a /channel/ link and a Spotify show

Kinds: own (the user's footage: cut + style-edit), creator (creator-teardown), long (clips),
product (product-video), music (the music question with rights), video (a single video whose
kind depends on its length and whose it is: `decide`), ask (one question in the question box),
unsupported (a sentence to say to the user).

classify() and decide() are pure: no network. `route` runs yt-dlp --dump-json --skip-download
on single videos to read their length, resolves a YouTube /channel/ link to its @handle (yt-dlp, no
videos read) and a Spotify episode or show to the same episode's audio in the show's own RSS feed
(Spotify's embed page for the names, the free iTunes Search API for the feed); `fetch` downloads. Neither uses cookies unless the user
said yes in the question box (--cookies-from-browser).

fetch exit codes: 0 ok (prints the file path) - 1 error (a sentence for the user) - 3 the site
wants a login: ask the cookie question, then re-run with --cookies-from-browser.
"""
import base64
import json
import xml.etree.ElementTree as ET
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

LONG_S = 8 * 60          # a video at least this long goes to clips
CLIPS_MIN_S = 3 * 60     # shorter than this, "make clips" is not offered
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mts", ".3gp")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".opus")
TEARDOWN_PLATFORMS = ("tiktok", "youtube", "instagram")  # what creator-teardown's fetch.py lists
ORDER = ("ask", "creator", "own", "video", "long", "product", "music", "unsupported")
ACTION = {
    "own": "fetch into the edit folder, then cut + style-edit",
    "creator": "creator-teardown (quick mode), then blend the style",
    "long": "clips",
    "product": "product-video",
    "music": "the music question with rights (style-edit or product-video)",
    "video": "read its length (route does), then decide",
    "ask": "one question in the question box, recommended option first",
    "unsupported": "say the note to the user",
}
LABEL = {"own": "Edit it as my video", "creator": "Copy this creator's style",
         "long": "Make short clips from it", "music": "Use it as music"}
_EXT = "|".join(e[1:] for e in VIDEO_EXT + AUDIO_EXT)
TOKEN_RE = re.compile(
    r"https?://[^\s<>\"')\]]+"                                   # a full link
    r"|(?<![\w./@])@[A-Za-z0-9._]{2,30}"                          # an @handle
    r"|\"[^\"]+\.(?:" + _EXT + r")\"|'[^']+\.(?:" + _EXT + r")'"   # a quoted path with spaces
    r"|(?:~|\.{1,2}|[A-Za-z]:)?[\\/][^\s\"']+\.(?:" + _EXT + r")\b"  # a path
    r"|(?<![\w./@\\])[\w-]+\.(?:" + _EXT + r")\b"                # a bare file name
    r"|(?<![\w./@-])[\w-]+(?:\.[\w-]+)*\.(?:com|ai|io|app|co|fm|ms|be|org|net|dev|so|xyz)\b(?:/[^\s<>\"')\]]*)?",
    re.I)


def _item(kind, url, **kw):
    d = {"kind": kind, "url": url, "action": ACTION[kind]}
    d.update({k: v for k, v in kw.items() if v is not None})
    return d


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "video"


def _ask(url, options, **kw):
    """options: kinds, recommended first."""
    return _item("ask", url, options=[{"kind": k, "label": LABEL[k]} for k in options], **kw)


def classify(raw, own=False):
    """One pasted thing -> {kind, url, action, ...}. Pure. `own`: the user said it is their video."""
    s = raw.strip().strip("<>").rstrip(".,;")
    if re.fullmatch(r"@[A-Za-z0-9._]{2,30}", s):
        return _item("creator", s, handle=s[1:].lower(), platform=None,
                     note="ask which platform the handle is on (TikTok first)")
    if not re.match(r"https?://", s, re.I):
        first = re.split(r"[\\/]", s)[0]
        if re.match(r"(~|\.{1,2}[\\/]|[\\/]|[A-Za-z]:[\\/])", s) or (
                s.lower().endswith(VIDEO_EXT + AUDIO_EXT) and (first == s or "." not in first)):
            p = os.path.abspath(os.path.expanduser(s))
            if p.lower().endswith(AUDIO_EXT):
                return _ask(p, ["long", "music"], name=_slug(Path(p).stem), local=True)
            return _item("own", p, name=_slug(Path(p).stem), local=True)
        s = "https://" + s
    u = urlparse(s)
    host = u.netloc.lower().split(":")[0]
    host = host[4:] if host.startswith("www.") else host
    host = host[2:] if host.startswith("m.") else host
    path = u.path or "/"
    q = parse_qs(u.query)
    parts = [p for p in path.split("/") if p]
    low = path.lower()

    # music first: music.youtube.com would otherwise read as a YouTube video
    if (host in ("music.youtube.com", "music.apple.com", "soundcloud.com", "tidal.com", "deezer.com")
            or host.endswith(".bandcamp.com")
            or (host == "open.spotify.com" and parts[:1] and parts[0] in ("track", "album", "playlist", "artist"))):
        return _item("music", s)

    # podcasts -> clips
    if host == "open.spotify.com" and parts[:1] and parts[0] in ("episode", "show"):
        return _item("long", s, platform="spotify", name=_slug("spotify-" + parts[-1]),
                     note="Spotify keeps most episodes locked. If the download fails, paste the same "
                          "episode from Apple Podcasts, YouTube or the show's RSS feed.")
    if host == "podcasts.apple.com":
        return _item("long", s, platform="apple-podcasts", name=_slug("podcast-" + (q.get("i") or parts[-1:])[0]),
                     note=None if "i" in q else "a show page: paste one episode's link")
    if (host in ("overcast.fm", "pca.st", "castbox.fm", "podcasts.google.com", "pocketcasts.com", "anchor.fm",
                 "podcasters.spotify.com", "podbean.com", "buzzsprout.com", "simplecast.com", "transistor.fm",
                 "rss.com", "podcastaddict.com")
            or any(host.endswith("." + h) for h in ("libsyn.com", "podbean.com", "buzzsprout.com", "simplecast.com",
                                                     "transistor.fm", "captivate.fm", "megaphone.fm"))
            or low.endswith((".rss", "/rss", "/feed", "/feed/")) or "/podcast" in low):
        return _item("long", s, name=_slug(host + "-" + (parts[-1] if parts else "")))

    # app stores and extension stores -> product
    if host in ("apps.apple.com", "chromewebstore.google.com", "microsoft.com", "apps.microsoft.com") and (
            host != "microsoft.com" or "/store/" in low) or (host == "play.google.com" and low.startswith("/store/apps")) or (
            host == "chrome.google.com" and low.startswith("/webstore")):
        return _item("product", s, note="an app store page: product-video records the app's own website "
                                       "when it has one; ask for it if the store page is all there is")

    # Google Drive
    if host in ("drive.google.com", "docs.google.com", "drive.usercontent.google.com"):
        if "folders" in parts:
            return _item("unsupported", s, note="That is a Drive folder. Open it, right-click the video, "
                         "Share > Copy link, and paste that link (Anyone with the link can view).")
        fid = (q.get("id") or [None])[0]
        if "d" in parts and parts.index("d") + 1 < len(parts):
            fid = parts[parts.index("d") + 1]
        if fid:
            return _item("own", f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t",
                         source=s, name=_slug("drive-" + fid[:10]),
                         note="In Drive, Share > General access > 'Anyone with the link', then paste the link again.")
        return _item("unsupported", s, note="That Google link is not a file. Share the video itself and paste that link.")

    # Dropbox
    if host in ("dropbox.com", "dl.dropboxusercontent.com", "dl.dropbox.com"):
        if host == "dropbox.com" and (parts[:2] == ["scl", "fo"] or parts[:1] == ["sh"]):
            return _item("unsupported", s, note="That is a Dropbox folder. Open the video in it and copy that file's link.")
        qs = {k: v[0] for k, v in q.items()}
        qs["dl"] = "1"
        name = Path(parts[-1]).stem if parts else "dropbox"
        return _item("own", urlunparse(u._replace(query=urlencode(qs))), source=s, name=_slug(name))

    # OneDrive / SharePoint: a share link -> the shares API (personal) or download=1 (SharePoint)
    if host in ("1drv.ms", "onedrive.live.com") or host.endswith(".sharepoint.com"):
        if host.endswith(".sharepoint.com"):
            qs = {k: v[0] for k, v in q.items()}
            qs["download"] = "1"
            dl = urlunparse(u._replace(query=urlencode(qs)))
        else:
            b64 = base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")
            dl = f"https://api.onedrive.com/v1.0/shares/u!{b64}/root/content"
        return _item("own", dl, source=s, name="onedrive-video",
                     note="OneDrive only lets this through for 'Anyone with the link' shares. If it fails, "
                          "download the file in the browser and give me its path.")

    # iCloud: a web page, never the file
    if host in ("icloud.com", "share.icloud.com"):
        return _item("unsupported", s, note="iCloud links open a web page, not the file, so I can't download it. "
                     "Open the link, press Download (or AirDrop it to this computer), and give me the file's path.")

    # YouTube
    if host in ("youtube.com", "youtu.be", "youtube-nocookie.com"):
        vid = None
        if host == "youtu.be" and parts:
            vid = parts[0]
        elif parts[:1] == ["watch"] and "v" in q:
            vid = q["v"][0]
        elif parts[:1] and parts[0] in ("shorts", "live", "embed", "v") and len(parts) > 1:
            vid = parts[1]
        if vid:
            canon = f"https://www.youtube.com/{'shorts/' if parts[:1] == ['shorts'] else 'watch?v='}{vid}"
            return _item("video", canon, platform="youtube", name=_slug("yt-" + vid), short=parts[:1] == ["shorts"])
        if parts[:1] == ["playlist"] or "list" in q:
            return _ask(s, ["creator", "long"], platform="youtube",
                        note="a playlist: copy the style of the creator behind it, or clip its videos one at a time")
        if parts and parts[0].startswith("@"):
            return _item("creator", f"https://www.youtube.com/{parts[0].lower()}", platform="youtube", handle=parts[0][1:].lower())
        if parts[:1] and parts[0] in ("channel", "c", "user") and len(parts) > 1:
            return _item("creator", f"https://www.youtube.com/{parts[0]}/{parts[1]}", platform="youtube",
                         handle=None if parts[0] == "channel" else parts[1].lower(),
                         note="creator-teardown lists by @handle: open the channel and use the @name under its title"
                         if parts[0] == "channel" else None)

    # TikTok
    if host.endswith("tiktok.com"):
        if host in ("vm.tiktok.com", "vt.tiktok.com") or parts[:1] == ["t"]:
            return _item("video", s, platform="tiktok", name=_slug("tiktok-" + parts[-1]), short=True)
        if parts and parts[0].startswith("@"):
            h = parts[0][1:].lower()
            if len(parts) >= 3 and parts[1] in ("video", "photo"):
                if parts[1] == "photo":
                    return _item("creator", f"https://www.tiktok.com/@{h}", platform="tiktok", handle=h,
                                 note="a photo post, not a video: the teardown reads this creator's videos")
                return _item("video", f"https://www.tiktok.com/@{h}/video/{parts[2]}", platform="tiktok",
                             handle=h, name=_slug(f"tiktok-{parts[2]}"), short=True)
            return _item("creator", f"https://www.tiktok.com/@{h}", platform="tiktok", handle=h)

    # Instagram
    if host in ("instagram.com", "instagr.am"):
        for i, p in enumerate(parts):
            if p in ("reel", "reels", "p", "tv") and i + 1 < len(parts):
                h = parts[0].lower() if i == 1 else None
                return _item("video", f"https://www.instagram.com/reel/{parts[i + 1]}/", platform="instagram",
                             handle=h, name=_slug("ig-" + parts[i + 1]), short=True)
        if parts[:1] == ["stories"]:
            return _item("unsupported", s, note="Instagram stories need a login and vanish in a day. "
                         "Save it from the app and give me the file's path.")
        if parts and parts[0] not in ("explore", "accounts", "direct"):
            h = parts[0].lower()
            return _item("creator", f"https://www.instagram.com/{h}/", platform="instagram", handle=h,
                         note="Instagram hides profiles from yt-dlp: paste 3-10 of their reel links, "
                              "or their TikTok or YouTube handle")

    # X / Twitter
    if host in ("x.com", "twitter.com", "mobile.twitter.com", "fxtwitter.com", "vxtwitter.com"):
        if len(parts) >= 3 and parts[1] == "status":
            return _item("video", f"https://x.com/{parts[0]}/status/{parts[2]}", platform="x",
                         handle=parts[0].lower(), name=_slug("x-" + parts[2]))
        if parts:
            return _item("unsupported", s, platform="x", note="creator-teardown reads TikTok, YouTube and Instagram. "
                         "Give me this creator's handle on one of those.")

    # other video hosts yt-dlp reads
    if host in ("vimeo.com", "player.vimeo.com", "loom.com", "fb.watch", "facebook.com", "twitch.tv",
                "clips.twitch.tv", "rumble.com", "dailymotion.com", "streamable.com", "linkedin.com") and (
            host not in ("facebook.com", "linkedin.com") or re.search(r"/(watch|videos?|reel|posts|feed/update)", low)):
        return _item("video", s, platform=host.split(".")[0], name=_slug(host.split(".")[0] + "-" + (parts[-1] if parts else "")))

    # a direct media file anywhere
    if low.endswith(VIDEO_EXT):
        return _item("own", s, name=_slug(Path(path).stem))
    if low.endswith(AUDIO_EXT):
        return _ask(s, ["long", "music"], name=_slug(Path(path).stem))

    return _item("product", s, name=_slug(host.split(".")[0] if host.count(".") <= 1 else host.split(".")[-2]))


def decide(item, duration=None, own=False):
    """A `video` item plus its length (seconds, None when unknown) -> own, long or ask. Pure."""
    if item["kind"] != "video":
        return item
    d = dict(item, duration=duration)
    is_long = duration is not None and duration >= LONG_S
    if is_long:
        return _ask(d["url"], ["long", "own"], **_rest(d)) if own else dict(d, kind="long", action=ACTION["long"])
    if own:
        return dict(d, kind="own", action=ACTION["own"])
    opts = ["own"]
    if d.get("platform") in TEARDOWN_PLATFORMS:
        opts.append("creator")
    if not d.get("short") and (duration is None or duration >= CLIPS_MIN_S):
        opts.append("long")
    return _ask(d["url"], opts, **_rest(d)) if len(opts) > 1 else dict(d, kind="own", action=ACTION["own"])


def _rest(d):
    return {k: v for k, v in d.items() if k not in ("kind", "url", "action")}


def extract(text):
    """Every link, @handle and media path in a message, in order, deduplicated."""
    found = []
    for m in TOKEN_RE.finditer(text):
        t = m.group(0).strip("\"'").rstrip(".,;:!?)]")
        if t and t not in found:
            found.append(t)
    return found


def group(items):
    """Several video links from one creator (not the user's own) become one creator teardown. Pure."""
    by = {}
    for it in items:
        if it["kind"] in ("video", "ask") and it.get("handle") and it.get("platform") in TEARDOWN_PLATFORMS:
            by.setdefault((it["platform"], it["handle"]), []).append(it)
    out, done = [], set()
    for it in items:
        key = (it.get("platform"), it.get("handle"))
        if key in by and len(by[key]) >= 2:
            if key not in done:
                done.add(key)
                out.append(_item("creator", f"{len(by[key])} videos", platform=key[0], handle=key[1],
                                 urls=[v["url"] for v in by[key]],
                                 note="write the urls one a line to picks.txt; fetch.py list <handle> --urls picks.txt"))
            continue
        out.append(it)
    return out


def plan(items):
    """Order: questions first, then creators (their style feeds the edit), the user's footage,
    long videos, product sites, music last."""
    return sorted(items, key=lambda it: ORDER.index(it["kind"]))


# ---- network: yt-dlp length probe and the downloader ----

def ytdlp():
    if shutil.which("yt-dlp"):
        return [shutil.which("yt-dlp")]
    home = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
    py = home / "venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    return [str(py), "-m", "yt_dlp"] if py.exists() else None


def probe(url, cookies=None):
    """(duration seconds, uploader handle) via yt-dlp, or (None, None)."""
    if not ytdlp():
        return None, None
    cmd = ytdlp() + ["--dump-json", "--skip-download", "--no-warnings", "--no-playlist", url]
    if cookies:
        cmd[-1:-1] = ["--cookies-from-browser", cookies]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout.splitlines()[0])
    except (subprocess.TimeoutExpired, IndexError, ValueError):
        return None, None
    h = (d.get("uploader_id") or d.get("channel_id") or "").lstrip("@").lower() or None
    return d.get("duration"), h


def channel_handle(url):
    """A YouTube /channel/UC..., /c/ or /user/ link -> its @handle (lowercase, no @), or None.
    One yt-dlp call that reads the channel's page and no videos."""
    if not ytdlp():
        return None
    try:
        r = subprocess.run(ytdlp() + ["--dump-single-json", "--flat-playlist", "--playlist-items", "0",
                                      "--no-warnings", url], capture_output=True, text=True, timeout=60)
        return handle_of(json.loads(r.stdout))
    except (subprocess.TimeoutExpired, ValueError):
        return None


def handle_of(d):
    """yt-dlp's channel JSON -> the @handle, or None. Pure."""
    for k in ("uploader_id", "uploader_url", "channel_url"):
        m = re.search(r"(?:^|/)@([\w.-]+)", str(d.get(k) or ""))
        if m:
            return m.group(1).lower()
    return None


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ai-video-editor"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def spotify_audio(url, get=_get):
    """A Spotify episode or show link -> {audio, feed, title, show} from the show's own RSS feed, or None.
    Spotify's embed page names the episode and its show (a show link: its latest episode; Spotify's oEmbed
    carries the episode title only); the iTunes Search API (free, no key) finds the show's feed; the
    feed's item with the same title has the audio file."""
    parts = [p for p in urlparse(url).path.split("/") if p]
    if len(parts) < 2 or parts[-2] not in ("episode", "show"):
        return None
    try:
        page = get(f"https://open.spotify.com/embed/{parts[-2]}/{parts[-1]}").decode("utf-8", "replace")
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
        e = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
        title, show = e.get("title") or e.get("name"), e.get("subtitle")
        found = json.loads(get("https://itunes.apple.com/search?media=podcast&entity=podcast&limit=10&term="
                               + quote(show)))["results"]
        feed = next(r["feedUrl"] for r in found if r.get("feedUrl") and _norm(r.get("collectionName")) == _norm(show))
        root = ET.fromstring(get(feed))
    except (AttributeError, KeyError, TypeError, ValueError, StopIteration, ET.ParseError, OSError):
        return None
    for item in root.iter("item"):
        enc = item.find("enclosure")
        if enc is not None and enc.get("url") and _norm(item.findtext("title")) == _norm(title):
            return {"audio": enc.get("url"), "feed": feed, "title": title, "show": show, "latest": parts[-2] == "show"}
    return None


def resolve(it):
    """route's network step for creator and podcast links: a /channel/ link gets its @handle, a
    Spotify link its episode's audio from the show's feed. Returns the item, changed or not."""
    if it["kind"] == "creator" and it.get("platform") == "youtube" and "/@" not in it["url"]:
        h = channel_handle(it["url"])
        if h:
            it = dict(it, url=f"https://www.youtube.com/@{h}", handle=h, source=it["url"])
            it.pop("note", None)
    if it.get("platform") == "spotify":
        a = spotify_audio(it["url"])
        if a:
            it = dict(it, url=a["audio"], source=it["url"], feed=a["feed"], name=_slug(a["title"]),
                      note=f"{a['show']}: {a['title']}, from the show's RSS feed" +
                           (" (a show link: its latest episode; paste an episode's link for another)" if a["latest"] else ""))
    return it


def route(text, own=False):
    items = [classify(t, own) for t in extract(text)]
    out = []
    for it in items:
        it = resolve(it)
        if it["kind"] == "video":
            dur, h = (None, None) if it.get("short") and own else probe(it["url"])
            if h and not it.get("handle") and it.get("platform") in TEARDOWN_PLATFORMS:
                it["handle"] = h
            it = decide(it, dur, own)
        out.append(it)
    return plan(group(out))


LOGIN = re.compile(r"sign in|log ?in|login|private|cookies|not a bot|registered users|members-only|age", re.I)


def video_format(max_height=2160):
    """yt-dlp -f: H.264 mp4 first, no taller than max_height (clips pass 1080: a 1080x1920 clip needs no 4K)."""
    h = int(max_height)
    return f"bv*[vcodec^=avc1][height<={h}]+ba[ext=m4a]/b[ext=mp4][height<={h}]/bv*[height<={h}]+ba/b[height<={h}]/b"


def fetch(url, edit_dir, cookies=None, max_gb=4.0, max_height=2160):
    """Download one own-footage link into edit_dir. Returns (code, message)."""
    it = classify(url, own=True)
    if it["kind"] == "video":
        it = decide(it, None, own=True)
    if it.get("platform") == "spotify":
        it = resolve(it)    # the episode's audio from the show's feed: Spotify's own stream is DRM
    edit = Path(edit_dir)
    if it.get("local"):
        p = Path(it["url"])
        return (0, str(p)) if p.is_file() else (1, f"No file at {p}. Check the path.")
    if it["kind"] == "unsupported":
        return 1, it["note"]
    if it["kind"] not in ("own", "ask", "long"):
        return 1, f"That link is a {it['kind']} link, not a video file ({it['action']})."
    if it.get("platform") and it["platform"] not in ("spotify",) or it["kind"] in ("ask", "long"):
        y = ytdlp()
        if not y:
            return 1, "yt-dlp is not installed. Run the setup skill, then try again."
        cmd = y + ["-f", video_format(max_height), "--merge-output-format", "mp4",
                   "--no-playlist", "--no-warnings", "--max-filesize", f"{int(max_gb * 1024)}M",
                   "-o", str(edit / "source.%(ext)s"), "--print", "after_move:filepath", it["url"]]
        if cookies:
            cmd[-1:-1] = ["--cookies-from-browser", cookies]
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = [ln for ln in r.stdout.splitlines() if ln.strip()]
        if r.returncode == 0 and out and Path(out[-1]).is_file():
            return 0, out[-1]
        err = r.stderr.strip().splitlines()[-1:] or ["no output"]
        if "max-filesize" in r.stderr or "larger than max-filesize" in r.stdout:
            return 1, f"The video is over {max_gb:g} GB. Download a smaller version, or pass --max-gb."
        if LOGIN.search(r.stderr):
            return 3, ("The site wants a login for this video (private, age-gated, or a bot check). "
                       "I can read your browser's login for this one download, if you agree. " + err[0][:200])
        return 1, f"The download failed: {err[0][:300]}"
    return http_get(it["url"], edit, max_gb, it.get("note"))


def http_get(url, edit, max_gb, note=None):
    edit.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ai-video-editor"})
    try:
        r = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as e:
        why = {401: "needs a login", 403: "is private", 404: "does not exist (or is private)"}.get(e.code, f"failed (HTTP {e.code})")
        return 1, f"That link {why}. " + (note or "Share it so anyone with the link can view, then paste it again.")
    except (urllib.error.URLError, OSError) as e:
        return 1, f"Could not reach that link: {e}"
    with r:
        ctype = r.headers.get("Content-Type", "").lower()
        size = int(r.headers.get("Content-Length") or 0)
        if ctype.startswith("text/html"):
            return 1, ("That link opens a web page, not the video file. " +
                       (note or "Share it so anyone with the link can view, or download it and give me the path."))
        if size > max_gb * 2**30:
            return 1, f"The file is {size / 2**30:.1f} GB, over the {max_gb:g} GB limit. Pass --max-gb to allow it."
        ext = next((e for e in VIDEO_EXT + AUDIO_EXT if urlparse(r.url).path.lower().endswith(e)), None)
        if not ext:
            m = re.search(r'filename\*?="?(?:UTF-8\'\')?([^";]+)', r.headers.get("Content-Disposition", ""))
            ext = Path(m.group(1)).suffix.lower() if m else ".mp4"
        dest = edit / f"source{ext or '.mp4'}"
        got = 0
        with open(dest, "wb") as f:
            while chunk := r.read(1 << 20):
                got += len(chunk)
                if got > max_gb * 2**30:
                    f.close()
                    dest.unlink()
                    return 1, f"The file is over the {max_gb:g} GB limit. Pass --max-gb to allow it."
                f.write(chunk)
    if got < 1024:
        dest.unlink()
        return 1, "The link returned an empty file. " + (note or "Check it opens in a private browser window.")
    return 0, str(dest)


# ---- self-check ----

CASES = [  # (pasted, own, kind, expected normalised url or None)
    ("https://www.tiktok.com/@somecreator", False, "creator", "https://www.tiktok.com/@somecreator"),
    ("https://www.tiktok.com/@SomeCreator?lang=en", False, "creator", "https://www.tiktok.com/@somecreator"),
    ("tiktok.com/@somecreator", False, "creator", None),
    ("@somecreator", False, "creator", "@somecreator"),
    ("https://www.tiktok.com/@somecreator/video/7312345678901234567?is_from_webapp=1", False, "video", "https://www.tiktok.com/@somecreator/video/7312345678901234567"),
    ("https://vm.tiktok.com/ZMabc123/", False, "video", None),
    ("https://www.tiktok.com/t/ZTabc123/", False, "video", None),
    ("https://www.tiktok.com/@somecreator/photo/7312345678901234567", False, "creator", None),
    ("https://www.instagram.com/somecreator/", False, "creator", "https://www.instagram.com/somecreator/"),
    ("https://www.instagram.com/somecreator/reels/", False, "creator", None),
    ("https://www.instagram.com/reel/C1a2B3c4D5e/?igsh=abc", False, "video", "https://www.instagram.com/reel/C1a2B3c4D5e/"),
    ("https://www.instagram.com/somecreator/reel/C1a2B3c4D5e/", False, "video", None),
    ("https://www.instagram.com/p/C1a2B3c4D5e/", False, "video", None),
    ("https://www.instagram.com/stories/somecreator/3312345/", False, "unsupported", None),
    ("https://www.youtube.com/@somecreator", False, "creator", "https://www.youtube.com/@somecreator"),
    ("https://www.youtube.com/@SomeCreator/videos", False, "creator", "https://www.youtube.com/@somecreator"),
    ("https://youtube.com/@somecreator/shorts", False, "creator", None),
    ("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv", False, "creator", None),
    ("https://www.youtube.com/c/SomeCreator", False, "creator", None),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s", False, "video", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?si=xyz", False, "video", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", False, "video", None),
    ("https://www.youtube.com/shorts/abcDEF12345", False, "video", "https://www.youtube.com/shorts/abcDEF12345"),
    ("https://www.youtube.com/live/abcDEF12345", False, "video", None),
    ("https://www.youtube.com/playlist?list=PL123", False, "ask", None),
    ("https://music.youtube.com/watch?v=abcDEF12345", False, "music", None),
    ("https://x.com/someone/status/1790000000000000000", False, "video", "https://x.com/someone/status/1790000000000000000"),
    ("https://twitter.com/someone/status/1790000000000000000/video/1", False, "video", "https://x.com/someone/status/1790000000000000000"),
    ("https://x.com/someone", False, "unsupported", None),
    ("https://vimeo.com/76979871", False, "video", None),
    ("https://www.loom.com/share/0123456789abcdef", False, "video", None),
    ("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing", False, "own", "https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOp&export=download&confirm=t"),
    ("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOp", False, "own", "https://drive.usercontent.google.com/download?id=1AbCdEfGhIjKlMnOp&export=download&confirm=t"),
    ("https://drive.google.com/uc?id=1AbCdEfGhIjKlMnOp&export=download", False, "own", None),
    ("https://drive.google.com/drive/folders/1AbCdEf", False, "unsupported", None),
    ("https://www.dropbox.com/s/abc123/my take.mov?dl=0", False, "own", "https://www.dropbox.com/s/abc123/my take.mov?dl=1"),
    ("https://www.dropbox.com/scl/fi/abc123/take.mp4?rlkey=xyz&dl=0", False, "own", "https://www.dropbox.com/scl/fi/abc123/take.mp4?rlkey=xyz&dl=1"),
    ("https://www.dropbox.com/scl/fo/abc123/def?rlkey=xyz&dl=0", False, "unsupported", None),
    ("https://www.icloud.com/iclouddrive/0abcDEF#take", False, "unsupported", None),
    ("https://share.icloud.com/photos/0abcDEF", False, "unsupported", None),
    ("https://1drv.ms/v/s!AbcDef123", False, "own", None),
    ("https://contoso.sharepoint.com/:v:/g/personal/x/Eabc?e=1", False, "own", None),
    ("https://example.com/files/take.MP4", False, "own", None),
    ("https://cdn.example.com/a/b/raw.mov?token=1", False, "own", None),
    ("https://example.com/episode.mp3", False, "ask", None),
    ("~/Movies/take.mov", False, "own", None),
    ("./take.mp4", False, "own", None),
    ("C:\\Users\\me\\Videos\\take.mp4", False, "own", None),
    ("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk", False, "long", None),
    ("https://podcasts.apple.com/us/podcast/some-show/id123456789?i=1000600000000", False, "long", None),
    ("https://feeds.example.com/show/rss", False, "long", None),
    ("https://somepodcast.libsyn.com/episode-12", False, "long", None),
    ("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", False, "music", None),
    ("https://soundcloud.com/artist/track", False, "music", None),
    ("https://artist.bandcamp.com/track/song", False, "music", None),
    ("https://music.apple.com/us/album/x/123?i=456", False, "music", None),
    ("https://apps.apple.com/us/app/some-app/id123456789", False, "product", None),
    ("https://play.google.com/store/apps/details?id=com.example.app", False, "product", None),
    ("https://chromewebstore.google.com/detail/x/abc", False, "product", None),
    ("https://example.com", False, "product", "https://example.com"),
    ("example.ai", False, "product", "https://example.ai"),
    ("https://github.com/someone/somerepo", False, "product", None),
]


def demo():
    assert "[height<=1080]" in video_format(1080) and "2160" not in video_format(1080)
    assert video_format(1080).count("[height<=1080]") == 4, video_format(1080)   # every fallback that knows its height
    for raw, own, kind, url in CASES:
        it = classify(raw, own)
        assert it["kind"] == kind, (raw, it)
        if url:
            assert it["url"] == url, (raw, it["url"], url)
    assert len(CASES) >= 40, len(CASES)
    # length and ownership decide a single video
    yt = classify("https://youtu.be/dQw4w9WgXcQ")
    assert decide(yt, 1500)["kind"] == "long"                       # a 25 min video -> clips
    assert decide(yt, 1500, own=True)["options"][0]["kind"] == "long"  # own and long: clips first, then whole edit
    short = decide(yt, 200)
    assert [o["kind"] for o in short["options"]] == ["own", "creator", "long"], short
    assert [o["kind"] for o in decide(yt, 60)["options"]] == ["own", "creator"]  # too short to clip
    assert decide(yt, 200, own=True)["kind"] == "own"
    tt = classify("https://www.tiktok.com/@a/video/1")
    assert [o["kind"] for o in decide(tt)["options"]] == ["own", "creator"]
    assert decide(classify("https://x.com/a/status/1"), 30)["kind"] == "own"  # no teardown for X, no clips under 3 min
    assert classify("https://www.tiktok.com/@a/video/1", own=True)["kind"] == "video"  # classify stays pure
    # several videos from one creator -> one teardown; questions, creators, own footage, product, music
    items = [decide(classify(u)) for u in ("https://www.tiktok.com/@a/video/1", "https://www.tiktok.com/@a/video/2")]
    g = group(items)
    assert len(g) == 1 and g[0]["kind"] == "creator" and g[0]["handle"] == "a" and len(g[0]["urls"]) == 2, g
    p = plan([classify(u) for u in ("https://open.spotify.com/track/x", "https://example.com", "~/take.mov",
                                    "https://www.tiktok.com/@a")])
    assert [i["kind"] for i in p] == ["creator", "own", "product", "music"], p
    # links pulled out of a message, trailing punctuation dropped, emails ignored
    msg = "edit my video ~/Movies/take.mov like https://www.tiktok.com/@somecreator, and see example.com. mail me@site.com"
    assert extract(msg) == ["~/Movies/take.mov", "https://www.tiktok.com/@somecreator", "example.com"], extract(msg)
    assert extract('edit "/Users/me/My Movies/take 2.mov" please') == ["/Users/me/My Movies/take 2.mov"]
    assert extract("cut take.MOV") == ["take.MOV"] and classify("take.MOV")["kind"] == "own"
    assert "@somecreator" in extract("make it look like @somecreator")
    # fetch refuses what it cannot download, with a sentence for the user, no network
    code, msg = fetch("https://www.icloud.com/iclouddrive/0abc#take", "/nonexistent-dir-never-made")
    assert code == 1 and "iCloud" in msg
    code, msg = fetch("https://example.com", "/nonexistent-dir-never-made")
    assert code == 1 and "product" in msg
    for line in ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "ERROR: [instagram] x: login required",
                 "ERROR: [youtube] x: Private video", "Sign in to confirm your age"):
        assert LOGIN.search(line), line
    assert not LOGIN.search("ERROR: [youtube] x: This video is unavailable")
    # a /channel/ link: the @handle out of yt-dlp's channel JSON (canned, as --flat-playlist prints it)
    canned = {"id": "UCabcdefghijklmnopqrstuv", "channel_id": "UCabcdefghijklmnopqrstuv", "uploader_id": "@SomeCreator",
              "uploader_url": "https://www.youtube.com/@SomeCreator", "_type": "playlist"}
    assert handle_of(canned) == "somecreator"
    assert handle_of({"uploader_id": None, "channel_url": "https://www.youtube.com/@Other.One"}) == "other.one"
    assert handle_of({"uploader_id": "UCabc", "channel_url": "https://www.youtube.com/channel/UCabc"}) is None
    g = globals()
    saved = g["channel_handle"]
    try:
        g["channel_handle"] = lambda u: handle_of(canned)
        it = resolve(classify("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv"))
        assert it["url"] == "https://www.youtube.com/@somecreator" and it["handle"] == "somecreator" and "note" not in it, it
        g["channel_handle"] = lambda u: None       # yt-dlp missing or offline: the note stays
        assert "note" in resolve(classify("https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv"))
    finally:
        g["channel_handle"] = saved
    # Spotify: embed page -> show name -> iTunes Search -> RSS feed -> the same episode's audio
    nd = {"props": {"pageProps": {"state": {"data": {"entity": {
        "type": "episode", "title": "#12 \u2013 Sleep, Light & Coffee", "subtitle": "Some Science Show"}}}}}}
    web = {
        "https://open.spotify.com/embed/episode/4rOoJ6Egrf8K2IrywzwOMk":
            f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(nd)}</script></html>'.encode(),
        "https://itunes.apple.com/search?media=podcast&entity=podcast&limit=10&term=Some%20Science%20Show": json.dumps(
            {"results": [{"collectionName": "Some Science Show | Summaries", "feedUrl": "https://wrong.example/rss"},
                         {"collectionName": "Some Science Show", "feedUrl": "https://feeds.example.com/sss"}]}).encode(),
        "https://feeds.example.com/sss": b"""<?xml version="1.0"?><rss><channel><title>Some Science Show</title>
            <item><title>#13 - Next One</title><enclosure url="https://cdn.example.com/13.mp3" type="audio/mpeg"/></item>
            <item><title>#12 - Sleep, Light &amp; Coffee</title><enclosure url="https://cdn.example.com/12.mp3" type="audio/mpeg"/></item>
            </channel></rss>""",
    }
    a = spotify_audio("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk?si=x", get=lambda u: web[u])
    assert a and a["audio"] == "https://cdn.example.com/12.mp3" and a["feed"] == "https://feeds.example.com/sss", a
    assert spotify_audio("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk", get=lambda u: web.get(u, b"")) == a
    assert spotify_audio("https://open.spotify.com/episode/missing", get=lambda u: web.get(u, b"")) is None
    def offline(u):
        raise urllib.error.URLError("offline")
    assert spotify_audio("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk", get=offline) is None
    saved = g["spotify_audio"]
    try:
        g["spotify_audio"] = lambda u: a
        it = resolve(classify("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk"))
        assert it["kind"] == "long" and it["url"] == "https://cdn.example.com/12.mp3" and "RSS" in it["note"], it
    finally:
        g["spotify_audio"] = saved
    print(f"demo ok ({len(CASES)} URL shapes)")


def live():
    """Network: one /channel/ link and one well-known podcast on Spotify, end to end."""
    h = channel_handle("https://www.youtube.com/channel/UCBR8-60-B28hp2BmDPdntcQ")
    assert h == "youtube", h
    a = spotify_audio("https://open.spotify.com/show/2MAi0BvDc6GTFvKFPXnkCL")   # a long-running public interview podcast
    assert a and a["audio"].startswith("http") and a["feed"], a
    print(f"live ok: @{h}; {a['show']}: {a['title']} -> {a['audio']}")


def main():
    a = sys.argv[1:]
    if a[:1] == ["demo"]:
        return demo()
    if a[:1] == ["live"]:
        return live()
    if a[:1] in (["classify"], ["route"]) and len(a) > 1:
        own = "--own" in a
        args = [x for x in a[1:] if x != "--own"]
        out = [classify(x, own) for x in args] if a[0] == "classify" else route(" ".join(args), own)
        print(json.dumps(out, indent=2))
        return 0
    if a[:1] == ["fetch"] and len(a) >= 3:
        cookies = a[a.index("--cookies-from-browser") + 1] if "--cookies-from-browser" in a else None
        max_gb = float(a[a.index("--max-gb") + 1]) if "--max-gb" in a else 4.0
        height = int(a[a.index("--max-height") + 1]) if "--max-height" in a else 2160
        code, msg = fetch(a[1], a[2], cookies, max_gb, height)
        print(msg, file=sys.stdout if code == 0 else sys.stderr)
        return code
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
