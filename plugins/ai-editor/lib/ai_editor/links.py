#!/usr/bin/env python3
"""Pasted links -> the skill that handles them. Stdlib only.

    python3 links.py route "<the user's message>" [--own]   classify every link, probe video
                                                            lengths with yt-dlp, print the plan
    python3 links.py classify <url>... [--own]              offline: kind, normalised url, action
    python3 links.py fetch <url> <edit dir> [--cookies-from-browser chrome] [--max-gb 4] [--max-height 2160] [--direct]
                                                            [--cover <image url>]  (audio: the artwork as cover.<ext>)
    python3 links.py demo                                   self-check on 40+ real URL shapes
    python3 links.py live                                   network check: a /channel/ link and a Spotify show

Kinds: own (the user's footage: cut + style-edit), takes (several own files joined into one video, then cut),
creator (creator-teardown), long (clips),
product (product-video), music (the music question with rights), video (a single video whose
kind depends on its length and whose it is: `decide`), ask (one question in the question box),
unsupported (a sentence to say to the user).

classify() and decide() are pure: no network. `route` runs yt-dlp --dump-json --skip-download
on single videos to read their length, resolves a YouTube /channel/ link to its @handle (yt-dlp, no
videos read) and a Spotify episode or show to the same episode's audio in the show's own RSS feed
(Spotify's embed page for the names, the free iTunes Search API for the feed), and a podcast feed (RSS,
Atom, or an Apple Podcasts show page via the iTunes lookup API) to an `ask` with its newest episodes as
options; `fetch --direct <episode url>` downloads only the chosen file, no yt-dlp. Every yt-dlp call takes
one item at most and has a hard timeout. Neither uses cookies unless the user
said yes in the question box (--cookies-from-browser).

fetch exit codes: 0 ok (prints the file path) - 1 error (a sentence for the user) - 3 the site
wants a login: ask the cookie question, then re-run with --cookies-from-browser.
"""
import base64
import email.utils
import json
from datetime import datetime
import xml.etree.ElementTree as ET
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse, urlunparse

LONG_S = 8 * 60          # a video at least this long goes to clips
CLIPS_MIN_S = 3 * 60     # shorter than this, "make clips" is not offered
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mts", ".3gp")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".opus")
EPISODES = 10            # newest episodes a feed lists; the question box offers the first 3
FEED_CAP = 32 << 20      # a 442-episode feed with show notes is a few MB
PROBE_S, FETCH_S = 60, 30 * 60   # yt-dlp hard timeouts: reading a length, a whole download
SLOW = ("yt-dlp did not finish in {} minutes on that link. Paste one video's own page link (not a playlist, "
        "channel or podcast feed), or download the file in the browser and give me its path.")
LOOKUP = "https://itunes.apple.com/lookup?id="
TEARDOWN_PLATFORMS = ("tiktok", "youtube", "instagram")  # what creator-teardown's fetch.py lists
ORDER = ("ask", "creator", "takes", "own", "video", "long", "product", "music", "unsupported")
ACTION = {
    "own": "fetch into the edit folder, then cut + style-edit",
    "takes": "join the files in order into edits/<name>/joined.mp4 (cut/references/takes.md), then cut + style-edit",
    "creator": "creator-teardown (quick mode), then blend the style",
    "long": "clips",
    "product": "product-video",
    "music": "the music question with rights (style-edit or product-video)",
    "video": "read its length (route does), then decide",
    "ask": "one question in the question box, recommended option first",
    "unsupported": "say the note to the user",
}
LABEL = {"own": "Edit it as my video", "takes": "One video: join them in this order", "separate": "Separate videos", "creator": "Copy this creator's style",
         "long": "Make short clips from it", "music": "Use it as music"}
_EXT = "|".join(e[1:] for e in VIDEO_EXT + AUDIO_EXT)
TOKEN_RE = re.compile(
    r"https?://[^\s<>\"')\]]+"                                   # a full link
    r"|(?<![\w./@])@[A-Za-z0-9._]{2,30}"                          # an @handle
    r"|\"[^\"]+\.(?:" + _EXT + r")\"|'[^']+\.(?:" + _EXT + r")'"   # a quoted path with spaces
    r"|(?<![\w./@\\])[^\s\"'\\]*(?:\\.[^\s\"'\\]*)+\.(?:" + _EXT + r")\b"  # Terminal drag and drop: My\ Takes/a\ 1.mov
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


QUESTION = {frozenset(("long", "music")): "What should I do with this audio?",
            frozenset(("creator", "long")): "What should I do with this playlist?",
            frozenset(("long", "own")): "Make short clips from this video, or edit the whole thing?",
            frozenset(("creator", "own")): "Copy this creator's style, or is this your own video to edit?",
            frozenset(("creator", "own", "long")): "Copy this creator's style, or is this your own video to edit?"}


def _ask(url, options, **kw):
    """options: kinds, recommended first. The question box's wording rides with them."""
    kw.setdefault("question", QUESTION.get(frozenset(options), "Is this your own video to edit?"))
    return _item("ask", url, options=[{"kind": k, "label": LABEL[k]} for k in options], **kw)


def _feed(url, **kw):
    """A podcast feed before route reads it: an ask with no options yet (pick_episode fills them)."""
    return _item("ask", url, feed=url, options=[], name=_slug(urlparse(url).netloc), **kw,
                 question="Which episode of this podcast?",
                 note="a podcast feed: route lists its newest episodes to pick from")


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
            if not os.path.exists(p):
                return _item("unsupported", p, note=f"No file at {p}. Check the path (or drag the file in again).")
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

    # podcasts -> clips; a feed or a show page -> pick an episode first
    if host == "open.spotify.com" and parts[:1] and parts[0] in ("episode", "show"):
        return _item("long", s, platform="spotify", name=_slug("spotify-" + parts[-1]),
                     note="Spotify keeps most episodes locked. If the download fails, paste the same "
                          "episode from Apple Podcasts, YouTube or the show's RSS feed.")
    if host == "podcasts.apple.com" and "i" not in q:
        sid = re.search(r"/id(\d+)", path)
        return _feed(s, platform="apple-podcasts", show_id=sid and sid.group(1))
    if low.endswith((".rss", "/rss", "/rss/", "/feed", "/feed/", ".xml")) or re.match(r"(rss|\w*feeds?)\.", host):
        return _feed(s)
    if host == "podcasts.apple.com":
        return _item("long", s, platform="apple-podcasts", name=_slug("podcast-" + (q.get("i") or parts[-1:])[0]),
                     note=None)
    if (host in ("overcast.fm", "pca.st", "castbox.fm", "podcasts.google.com", "pocketcasts.com", "anchor.fm",
                 "podcasters.spotify.com", "podbean.com", "buzzsprout.com", "simplecast.com", "transistor.fm",
                 "rss.com", "podcastaddict.com")
            or any(host.endswith("." + h) for h in ("libsyn.com", "podbean.com", "buzzsprout.com", "simplecast.com",
                                                     "transistor.fm", "captivate.fm", "megaphone.fm"))
            or "/podcast" in low):
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
                         source=s, name=_slug("drive-" + fid[:10]),   # route swaps in the file's own name
                         if_fails="In Drive, Share > General access > 'Anyone with the link', then paste the link again.")
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
    # Not said to be theirs: a public creator's video is for the teardown first, editing it second.
    opts = ["creator", "own"] if d.get("platform") in TEARDOWN_PLATFORMS else ["own"]
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
        if "\\" in t and not re.match(r"https?://|[A-Za-z]:\\", t):
            t = re.sub(r"\\(\W)", r"\1", t)   # a shell escape (\ , \(, \'), never a Windows separator
        if t and t not in found:
            found.append(t)
    return found


def group(items):
    """Several video links from one creator (not the user's own) become one creator teardown. Pure."""
    by = {}
    for it in items:
        if it["kind"] in ("video", "ask") and it.get("handle") and it.get("platform") in TEARDOWN_PLATFORMS:
            by.setdefault((it["platform"], it["handle"]), []).append(it)
    takes = [it for it in items if it["kind"] == "own" and it.get("local")]   # in the order the user gave them
    if len(takes) >= 2:   # several of the user's own files: one video in parts, or separate videos?
        names = ", ".join(Path(t["url"]).name for t in takes)
        merged = _item("ask", f"{len(takes)} files", name=takes[0]["name"], files=[t["url"] for t in takes],
                       question=f"Are these {len(takes)} files one video ({names}, in the order you gave them) "
                                "or separate videos?",
                       options=[{"kind": "takes", "label": LABEL["takes"]},
                                {"kind": "separate", "label": LABEL["separate"]}],
                       action="one question in the question box. takes: " + ACTION["takes"]
                              + ". separate: each file is an `own` item with its own edit folder")
        items = [merged] + [it for it in items if not any(it is t for t in takes)]
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
    """The venv's pinned yt-dlp (the version CI checks weekly), else one on PATH, else None."""
    home = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
    py = home / "venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    if py.exists():
        return [str(py), "-m", "yt_dlp"]
    return [shutil.which("yt-dlp")] if shutil.which("yt-dlp") else None


ONE = ["--no-playlist", "--playlist-items", "1"]   # a playlist or feed link reads one item, never the whole list


def probe(url, cookies=None):
    """(duration seconds, uploader handle, note) via yt-dlp; (None, None, None) when unknown, the note on a timeout."""
    if not ytdlp():
        return None, None, None
    cmd = ytdlp() + ["--dump-json", "--skip-download", "--no-warnings", *ONE, url]
    if cookies:
        cmd[-1:-1] = ["--cookies-from-browser", cookies]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=PROBE_S)
        d = json.loads(r.stdout.splitlines()[0])
    except subprocess.TimeoutExpired:
        return None, None, SLOW.format(PROBE_S // 60)
    except (IndexError, ValueError):
        err = (r.stderr.strip().splitlines() or ["no answer"])[-1]
        return None, None, f"yt-dlp could not open this video to read its length: {err[:200]}"
    h = (d.get("uploader_id") or d.get("channel_id") or "").lstrip("@").lower() or None
    return d.get("duration"), h, None


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


def _get(url, timeout=30, cap=FEED_CAP):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ai-video-editor"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(cap + 1)
    if len(data) > cap:
        raise ValueError(f"{url} is over {cap >> 20} MB")
    return data


# Podcast analytics prefixes: each wraps the host's own file URL (with or without its https://), so stripping
# them downloads the host's file instead of a redirect chain.
TRACKERS = re.compile(r"^https?://(?:dts\.podtrac\.com/redirect\.\w+|(?:www\.)?podtrac\.com/pts/redirect\.\w+|"
                      r"chrt\.fm/track/[^/]+|chtbl\.com/track/[^/]+|pdst\.fm/e|op3\.dev/e(?:,[^/]*)?|pfx\.vpixl\.com/[^/]+|"
                      r"arttrk\.com/p/[^/]+|mgln\.ai/e/[^/]+|prfx\.byspotify\.com/e|verifi\.podscribe\.com/rss/p|"
                      r"claritaspod\.com/measure|tracking\.swap\.fm/track/[^/]+)/", re.I)


def untrack(url):
    """An episode's enclosure with every analytics redirect prefix removed. Pure."""
    while True:
        m = TRACKERS.match(url)
        if not m:
            return url
        rest = url[m.end():]
        url = rest if re.match(r"https?://", rest, re.I) else "https://" + rest


def file_name(url, timeout=15):
    """The file name a download link serves (Content-Disposition), or None. One ranged GET, no body read."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ai-video-editor", "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            cd = r.headers.get("Content-Disposition", "")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)|filename=\"?([^\";]+)", cd, re.I)
    return unquote(m.group(1) or m.group(2)).strip() if m else None


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
        eps = episodes(get(feed), limit=None)[1]
    except (AttributeError, KeyError, TypeError, ValueError, StopIteration, ET.ParseError, OSError):
        return None
    for e in eps:
        if _norm(e["title"]) == _norm(title):
            return {"audio": untrack(e["url"]), "feed": feed, "title": title, "show": show, "latest": parts[-2] == "show",
                    "image": e["image"]}
    return None


def _when(text):
    """An RSS (RFC 2822) or Atom (ISO 8601) date -> datetime, or None."""
    for parse in (email.utils.parsedate_to_datetime, lambda t: datetime.fromisoformat(t.replace("Z", "+00:00"))):
        try:
            return parse((text or "").strip())
        except (TypeError, ValueError, IndexError):
            pass
    return None


def _secs(text):
    """itunes:duration ("3723", "62:03", "1:02:03") -> seconds, or None."""
    try:
        return sum(int(float(p)) * 60 ** i for i, p in enumerate(reversed((text or "").strip().split(":")))) or None
    except ValueError:
        return None


def episodes(data, limit=EPISODES):
    """RSS or Atom bytes -> (show title, [{title, date, duration, url, image}] newest first, only items with
    audio). image: the episode's itunes:image, else the show's (itunes:image or <image><url>), else None. Pure."""
    def tag(e):
        return e.tag.rsplit("}", 1)[-1] if isinstance(e.tag, str) else ""

    def image(el):
        for c in el:
            if tag(c) == "image":
                u = c.get("href") or next((x.text for x in c if tag(x) == "url"), None)
                if u and u.strip():
                    return u.strip()
        return None
    root = ET.fromstring(data)
    top = root if root.find("channel") is None else root.find("channel")
    show = next((c.text or "" for c in top if tag(c) == "title"), "").strip()
    cover = image(top)
    out = []
    for el in root.iter():
        if tag(el) not in ("item", "entry"):
            continue
        f, url = {}, None
        for c in el:
            t = tag(c)
            if t == "enclosure" or (t == "link" and c.get("rel") == "enclosure"):
                url = url or c.get("url") or c.get("href")
            elif t not in f:
                f[t] = (c.text or "").strip()
        if not url:
            continue
        d = _when(f.get("pubDate") or f.get("published") or f.get("updated"))
        out.append({"title": f.get("title") or "untitled", "date": d.date().isoformat() if d else None,
                    "duration": _secs(f.get("duration")), "url": untrack(url), "image": image(el) or cover, "_t": d.timestamp() if d else float("-inf")})
    out.sort(key=lambda e: e.pop("_t"), reverse=True)    # stable: undated items keep the feed's order, last
    return show, out[:limit]


def _long(s):
    return f"{s // 3600} h {s % 3600 // 60} min" if s >= 3600 else f"{s // 60} min" if s else ""


def pick_episode(it, get=None):
    """A feed (or an Apple show page, via the iTunes lookup API) -> an ask whose options are its newest
    episodes, recommended newest first; `episodes` holds the newest 10. A podcast-host link that is not a
    feed comes back unchanged. One capped, timed GET per URL, no yt-dlp."""
    get = get or (lambda u: _get(u, timeout=15))
    feed = it.get("feed") or it["url"]
    try:
        if it.get("show_id"):
            feed = json.loads(get(LOOKUP + it["show_id"]))["results"][0]["feedUrl"]
        show, eps = episodes(get(feed))
    except (KeyError, IndexError, TypeError, ValueError, ET.ParseError, OSError):
        show, eps = "", []
    if not eps:
        return dict(it, note="Could not read that podcast feed. Paste one episode's link, or its audio file's link.") \
            if it.get("feed") else it
    for e in eps:
        e["name"] = _slug(e["title"])
    opts = [{"kind": "long", "label": e["title"][:60], "url": e["url"], "name": e["name"], "image": e["image"],
             "description": ", ".join(x for x in (e["date"], _long(e["duration"] or 0)) if x)} for e in eps[:3]]
    out = dict(it, kind="ask", action=ACTION["ask"], url=feed, feed=feed, episodes=eps, options=opts,
               question=f"Which episode of {show or 'this podcast'}?",
               note=f"{len(eps)} newest episodes in `episodes`; fetch the picked one's url with --direct "
                    "--cover <its image>")
    if feed != it["url"]:
        out["source"] = it["url"]
    return out


def resolve(it):
    """route's network step for creator and podcast links: a /channel/ link gets its @handle, a
    Spotify link its episode's audio from the show's feed. Returns the item, changed or not."""
    if it["kind"] == "creator" and it.get("platform") == "youtube" and "/@" not in it["url"]:
        h = channel_handle(it["url"])
        if h:
            it = dict(it, url=f"https://www.youtube.com/@{h}", handle=h, source=it["url"])
            it.pop("note", None)
    if it.get("feed") or (it["kind"] == "long" and not it.get("platform")
                          and not urlparse(it["url"]).path.lower().endswith(VIDEO_EXT + AUDIO_EXT)):
        it = pick_episode(it)
    if it["kind"] == "own" and urlparse(it["url"]).netloc == "drive.usercontent.google.com":
        n = file_name(it["url"])     # the edit folder after the file, not after Drive's id
        if n:
            it = dict(it, name=_slug(Path(n).stem))
    if it.get("platform") == "spotify":
        a = spotify_audio(it["url"])
        if a:
            it = dict(it, url=a["audio"], source=it["url"], feed=a["feed"], name=_slug(a["title"]), image=a.get("image"),
                      note=f"{a['show']}: {a['title']}, from the show's RSS feed" +
                           (" (a show link: its latest episode; paste an episode's link for another)" if a["latest"] else ""))
    return it


def route(text, own=False):
    items = [classify(t, own) for t in extract(text)]
    out = []
    for it in items:
        it = resolve(it)
        if it["kind"] == "video":
            dur, h, slow = (None, None, None) if it.get("short") and own else probe(it["url"])
            if slow:
                it["note"] = slow
            if h and not it.get("handle") and it.get("platform") in TEARDOWN_PLATFORMS:
                it["handle"] = h
            it = decide(it, dur, own)
        out.append(it)
    return plan(group(out))


# Whole words only: a bare "age" matched "webpage", "image" and "storage", and an ordinary 404 asked for the browser login.
LOGIN = re.compile(r"\b(?:sign(?:ed)? ?in|log ?in|login|private|cookies|not a bot|registered users|members[- ]only|"
                   r"age[- ](?:restricted|gated|verification)|confirm your age|inappropriate for some users)\b", re.I)


def video_format(max_height=2160):
    """yt-dlp -f: H.264 mp4 first, no taller than max_height (clips pass 1080: a 1080x1920 clip needs no 4K)."""
    h = int(max_height)
    return f"bv*[vcodec^=avc1][height<={h}]+ba[ext=m4a]/b[ext=mp4][height<={h}]/bv*[height<={h}]+ba/b[height<={h}]/b"


def save_cover(url, edit, get=_get):
    """The podcast's own artwork next to the source, as cover.<ext>: the ground an audio-only clip renders
    on (clips.py trim). Best effort: None when there is none or it fails to download."""
    if not url:
        return None
    ext = next((e for e in (".jpg", ".jpeg", ".png", ".webp") if urlparse(url).path.lower().endswith(e)), ".jpg")
    try:
        data = get(url, timeout=30, cap=20 << 20)
    except (ValueError, OSError):
        return None
    Path(edit).mkdir(parents=True, exist_ok=True)
    out = Path(edit) / f"cover{ext}"
    out.write_bytes(data)
    return out


def fetch(url, edit_dir, cookies=None, max_gb=4.0, max_height=2160, direct=False, cover=None):
    """Download one own-footage link into edit_dir. Returns (code, message). `direct`: a file URL (a podcast
    episode's enclosure), downloaded as it is, no yt-dlp. `cover`: the episode's image, saved as cover.<ext>."""
    found = {}
    code, msg = _fetch(url, edit_dir, cookies, max_gb, max_height, direct, found)
    if code == 0 and Path(msg).suffix.lower() in AUDIO_EXT:
        save_cover(cover or found.get("image"), edit_dir)
    return code, msg


def _fetch(url, edit_dir, cookies, max_gb, max_height, direct, found):
    if direct:
        return http_get(url, Path(edit_dir), max_gb)
    it = classify(url, own=True)
    if it.get("feed"):
        return 1, ("That is a podcast feed, not one episode. Run links.py route on it, pick an episode, "
                   "then fetch that episode's url with --direct.")
    if it["kind"] == "video":
        it = decide(it, None, own=True)
    if it.get("platform") == "spotify":
        it = resolve(it)    # the episode's audio from the show's feed: Spotify's own stream is DRM
        found["image"] = it.get("image")
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
                   *ONE, "--no-warnings", "--max-filesize", f"{int(max_gb * 1024)}M",
                   "-o", str(edit / "source.%(ext)s"), "--print", "after_move:filepath", it["url"]]
        if cookies:
            cmd[-1:-1] = ["--cookies-from-browser", cookies]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=FETCH_S)
        except subprocess.TimeoutExpired:
            return 1, SLOW.format(FETCH_S // 60)
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
    return http_get(it["url"], edit, max_gb, it.get("if_fails") or it.get("note"))


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
    ("C:\\Users\\me\\Videos\\take.mp4", False, "unsupported", None),   # a local path, but no such file
    ("https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk", False, "long", None),
    ("https://podcasts.apple.com/us/podcast/some-show/id123456789?i=1000600000000", False, "long", None),
    ("https://feeds.example.com/show/rss", False, "ask", None),
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
    """In a temp home and working folder holding the files the local-path cases name: a path that does
    not exist is reported as not found."""
    old = os.getcwd(), {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
    with tempfile.TemporaryDirectory() as d:
        for f in ("Movies/take.mov", "take.mp4", "take.MOV", "a.mp3", "a.mov", "b.mov", "A.mov", "take.mov",
                  "My Takes/IMG 0001.MOV", "My Takes/IMG 0002.MOV"):
            Path(d, f).parent.mkdir(parents=True, exist_ok=True)
            Path(d, f).touch()
        os.chdir(d)
        os.environ.update(HOME=d, USERPROFILE=d)
        try:
            _demo(os.path.realpath(d))
        finally:
            os.chdir(old[0])
            for k, v in old[1].items():
                os.environ.pop(k, None) if v is None else os.environ.update({k: v})


def _demo(home):
    assert "[height<=1080]" in video_format(1080) and "2160" not in video_format(1080)
    assert video_format(1080).count("[height<=1080]") == 4, video_format(1080)   # every fallback that knows its height
    for raw, own, kind, url in CASES:
        it = classify(raw, own)
        assert it["kind"] == kind, (raw, it)
        if url:
            assert it["url"] == url, (raw, it["url"], url)
    assert len(CASES) >= 40, len(CASES)
    # a Drive link: the share how-to is said only when the download fails; the folder is named after the file
    dr = classify("https://drive.google.com/file/d/1l5rk28jrAbCdEf/view?usp=sharing")
    assert "note" not in dr and "Anyone with the link" in dr["if_fails"], dr
    saved_fn = globals()["file_name"]
    try:
        globals()["file_name"] = lambda u: "My Take 3.MOV"
        assert resolve(dr)["name"] == "my-take-3", resolve(dr)
        globals()["file_name"] = lambda u: None
        assert resolve(dr)["name"] == "drive-1l5rk28jra"
    finally:
        globals()["file_name"] = saved_fn
    # podcast analytics redirects stripped down to the host's own file
    for raw in ("https://dts.podtrac.com/redirect.mp3/chrt.fm/track/AB12/traffic.megaphone.fm/XYZ123.mp3?updated=1",
                "https://op3.dev/e/https://traffic.megaphone.fm/XYZ123.mp3?updated=1",
                "https://pdst.fm/e/chtbl.com/track/9/traffic.megaphone.fm/XYZ123.mp3?updated=1"):
        assert untrack(raw) == "https://traffic.megaphone.fm/XYZ123.mp3?updated=1", (raw, untrack(raw))
    assert untrack("https://cdn.example.com/12.mp3") == "https://cdn.example.com/12.mp3"
    # length and ownership decide a single video
    yt = classify("https://youtu.be/dQw4w9WgXcQ")
    assert decide(yt, 1500)["kind"] == "long"                       # a 25 min video -> clips
    assert decide(yt, 1500, own=True)["options"][0]["kind"] == "long"  # own and long: clips first, then whole edit
    short = decide(yt, 200)
    assert [o["kind"] for o in short["options"]] == ["creator", "own", "long"], short
    assert [o["kind"] for o in decide(yt, 60)["options"]] == ["creator", "own"]  # too short to clip
    assert decide(yt, 200, own=True)["kind"] == "own"
    tt = classify("https://www.tiktok.com/@a/video/1")
    assert [o["kind"] for o in decide(tt, 136)["options"]] == ["creator", "own"]   # someone else's TikTok: style first
    sh = classify("https://www.youtube.com/shorts/abcDEF12345")
    assert [o["kind"] for o in decide(sh, 39)["options"]] == ["creator", "own"], decide(sh, 39)
    assert [o["kind"] for o in decide(classify("https://vimeo.com/76979871"), 300)["options"]] == ["own", "long"]
    for it in [decide(tt, 136), decide(yt, 1500, own=True), decide(yt, 200)] + [classify(u) for u in (
            "https://www.youtube.com/playlist?list=PL123", "https://example.com/episode.mp3", "~/a.mp3",
            "https://feeds.example.com/show/rss")]:
        assert it["kind"] == "ask" and it["question"].endswith("?"), it   # every question box has its wording
    assert decide(classify("https://x.com/a/status/1"), 30)["kind"] == "own"  # no teardown for X, no clips under 3 min
    assert classify("https://www.tiktok.com/@a/video/1", own=True)["kind"] == "video"  # classify stays pure
    # several videos from one creator -> one teardown; questions, creators, own footage, product, music
    items = [decide(classify(u)) for u in ("https://www.tiktok.com/@a/video/1", "https://www.tiktok.com/@a/video/2")]
    g = group(items)
    assert len(g) == 1 and g[0]["kind"] == "creator" and g[0]["handle"] == "a" and len(g[0]["urls"]) == 2, g
    # several own files: one question (one video joined, or separate), in the order the user gave them
    g = group([classify(u) for u in ("~/b.mov", "https://example.com", "~/A.mov")])
    assert g[0]["kind"] == "ask" and [o["kind"] for o in g[0]["options"]] == ["takes", "separate"], g
    assert [Path(f).name for f in g[0]["files"]] == ["b.mov", "A.mov"] and g[0]["name"] == "b", g
    assert "b.mov, A.mov, in the order you gave them" in g[0]["question"] and [i["kind"] for i in g[1:]] == ["product"], g
    # macOS Terminal drag and drop escapes spaces; a path that is not there is said, not guessed at
    msg = "join My\\ Takes/IMG\\ 0002.MOV and " + home + "/My\\ Takes/IMG\\ 0001.MOV please"
    assert extract(msg) == ["My Takes/IMG 0002.MOV", home + "/My Takes/IMG 0001.MOV"], extract(msg)
    g = group([classify(t) for t in extract(msg)])
    assert [Path(f).name for f in g[0]["files"]] == ["IMG 0002.MOV", "IMG 0001.MOV"], g
    assert os.path.realpath(g[0]["files"][0]) == os.path.join(home, "My Takes", "IMG 0002.MOV"), g
    nf = classify("~/My Takes/IMG 0003.MOV")
    assert nf["kind"] == "unsupported" and nf["note"].startswith("No file at"), nf
    assert [i["kind"] for i in group([classify("~/a.mov")])] == ["own"]   # one file: no question
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
    # "age" inside an ordinary word is not an age gate: these are plain failures (exit 1), never a cookie question
    for line in ("ERROR: Unable to download webpage: HTTP Error 404: Not Found", "ERROR: no image found",
                 "ERROR: not enough storage", "ERROR: [generic] x: Unable to extract page data", "ERROR: message too long"):
        assert not LOGIN.search(line), line
    for line in ("ERROR: [youtube] x: This video is age-restricted", "ERROR: [instagram] x: Requested content is not available, "
                 "rate-limit reached or login required", "ERROR: [tiktok] x: This post may not be comfortable for some audiences. "
                 "Log in for access", "ERROR: [youtube] x: Join this channel to get access to members-only content",
                 "Use --cookies-from-browser or --cookies for the authentication"):
        assert LOGIN.search(line), line
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
    # a podcast feed is never clips straight away: pick an episode, newest first, then download only it
    rss = b"""<?xml version="1.0"?><rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>
        <title>Some Show</title><itunes:image href="https://cdn.example.com/show.jpg"/>""" + b"".join(
        f"""<item><title>Ep {n}: Talk number {n}</title>{'<itunes:image href="https://cdn.example.com/ep13.png"/>' if n == 13 else ''}<pubDate>{d:02d} Sep 2026 08:00:00 +0000</pubDate>
            <itunes:duration>{'1:02:03' if n == 13 else 3000 + n}</itunes:duration>
            <enclosure url="https://cdn.example.com/{n}.mp3?x=1" type="audio/mpeg"/></item>""".encode()
        for n, d in ((12, 1), (13, 8), *((k, 1) for k in range(1, 12)))) + b"</channel></rss>"
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Show</title>
        <entry><title>Old</title><published>2026-01-01T00:00:00Z</published>
          <link rel="enclosure" href="https://cdn.example.com/old.m4a"/></entry>
        <entry><title>New</title><published>2026-02-01T00:00:00Z</published>
          <link rel="alternate" href="https://example.com/new"/><link rel="enclosure" href="https://cdn.example.com/new.m4a"/></entry>
        <entry><title>No audio</title><published>2026-03-01T00:00:00Z</published></entry></feed>"""
    show, eps = episodes(rss, limit=None)
    assert show == "Some Show" and len(eps) == 13 and len(episodes(rss)[1]) == EPISODES and eps[0]["title"] == "Ep 13: Talk number 13", eps[:2]
    assert eps[0]["date"] == "2026-09-08" and eps[0]["duration"] == 3723 and eps[0]["url"] == "https://cdn.example.com/13.mp3?x=1"
    assert episodes(atom)[1] and [e["title"] for e in episodes(atom)[1]] == ["New", "Old"], episodes(atom)
    assert episodes(atom)[1][0]["url"] == "https://cdn.example.com/new.m4a" and episodes(atom)[1][0]["image"] is None
    assert eps[0]["image"] == "https://cdn.example.com/ep13.png" and eps[1]["image"] == "https://cdn.example.com/show.jpg", eps[:2]
    with tempfile.TemporaryDirectory() as td:   # the artwork lands next to the source; a dead link is no error
        got = save_cover("https://cdn.example.com/ep13.png?w=3000", td, get=lambda u, **k: b"png")
        assert got.name == "cover.png" and got.read_bytes() == b"png", got
        assert save_cover("https://cdn.example.com/x.jpg", td, get=lambda u, **k: offline(u)) is None and save_cover(None, td) is None
    for raw in ("https://feeds.example.com/show/rss", "https://feeds.megaphone.fm/ABC123", "https://anchor.fm/s/abc/podcast/rss",
                "https://example.com/show.xml", "https://podcasts.apple.com/us/podcast/some-show/id123456789"):
        it = classify(raw)
        assert it["kind"] == "ask" and it.get("feed") and not it["options"], (raw, it)   # never "long" with no episode
    assert classify("https://podcasts.apple.com/us/podcast/some-show/id123456789")["show_id"] == "123456789"
    web = {"https://feeds.example.com/show/rss": rss,
           "https://itunes.apple.com/lookup?id=123456789": json.dumps({"results": [{"feedUrl": "https://feeds.example.com/show/rss"}]}).encode()}
    for raw in ("https://feeds.example.com/show/rss", "https://podcasts.apple.com/us/podcast/some-show/id123456789"):
        it = pick_episode(classify(raw), get=lambda u, **k: web[u])
        assert it["kind"] == "ask" and it["url"] == "https://feeds.example.com/show/rss" and len(it["episodes"]) == EPISODES, it
        o = it["options"]
        assert len(o) == 3 and o[0]["kind"] == "long" and o[0]["url"] == "https://cdn.example.com/13.mp3?x=1", o
        assert o[0]["image"] == "https://cdn.example.com/ep13.png" and o[0]["name"] == "ep-13-talk-number-13" and "2026-09-08" in o[0]["description"] and "1 h 2 min" in o[0]["description"], o[0]
        assert "Some Show" in it["question"], it
    dead = pick_episode(classify("https://feeds.example.com/show/rss"), get=offline)
    assert dead["kind"] == "ask" and not dead["options"] and "episode" in dead["note"], dead
    assert pick_episode(classify("https://somepodcast.libsyn.com/episode-12"), get=lambda u, **k: b"<html>")["kind"] == "long"
    big = []
    try:
        _get("data:application/octet-stream;base64," + base64.b64encode(b"x" * 100).decode(), cap=10)
    except ValueError as e:
        big.append(str(e))
    assert big and "over" in big[0], big   # the size cap holds
    code, msg = fetch("https://feeds.example.com/show/rss", "/nonexistent-dir-never-made")
    assert code == 1 and "episode" in msg, msg     # a feed never reaches yt-dlp
    # yt-dlp on a link that can be a playlist: one item at most, a hard timeout, a plain sentence on timeout
    cmds = []
    def slow(cmd, **kw):
        cmds.append((cmd, kw))
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
    saved = g["ytdlp"], subprocess.run
    try:
        g["ytdlp"], subprocess.run = (lambda: ["yt-dlp"]), slow
        assert probe("https://www.youtube.com/watch?v=dQw4w9WgXcQ")[:2] == (None, None)
        code, msg = fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "/nonexistent-dir-never-made")
    finally:
        g["ytdlp"], subprocess.run = saved
    assert code == 1 and "paste" in msg.lower() and "minutes" in msg, msg
    # a probe yt-dlp cannot open (an Instagram reel it is refused) says why, so the ask carries a note
    saved = g["ytdlp"], subprocess.run
    try:
        g["ytdlp"] = lambda: ["yt-dlp"]
        subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "ERROR: [Instagram] x: Requested content is not available")
        dur, _, note = probe("https://www.instagram.com/reel/C1a2B3c4D5e/")
        assert dur is None and "Requested content is not available" in note, note
        it = route("https://www.instagram.com/reel/C1a2B3c4D5e/")[0]
        assert it["kind"] == "ask" and "could not open" in it["note"], it
    finally:
        g["ytdlp"], subprocess.run = saved
    for cmd, kw in cmds:
        assert kw.get("timeout") and "--no-playlist" in cmd and cmd[cmd.index("--playlist-items") + 1] == "1", cmd
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
        cover = a[a.index("--cover") + 1] if "--cover" in a else None
        code, msg = fetch(a[1], a[2], cookies, max_gb, height, "--direct" in a, cover)
        print(msg, file=sys.stdout if code == 0 else sys.stderr)
        return code
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
