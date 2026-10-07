#!/usr/bin/env python3
"""Pull a creator's videos + word-level transcripts, via yt-dlp and Whisper or Scribe.

Commands:

  doctor      checks the tools, and prints the exact fix for anything missing.
              Run it first.

  setkey      optional. Saves an ElevenLabs key once, for every folder. Paste it
              when asked (it stays hidden), or pipe it in: pbpaste | ... setkey
              `setkey --gemini` saves a Gemini key the same way (the look pass).

  list        yt-dlp --flat-playlist over a profile -> videos.json + a ranked
              table on stdout. No downloads, no API key, no cost.

  transcribe  transcribes the picked videos through transcribe.py next to this
              file: the N most-viewed plus the 2 videos closest to the median as
              a control group. Whisper (free, local) by default; Scribe v2 when
              an ElevenLabs key exists. Uses video/<id>.mp4 when visual.py
              downloaded it, else downloads the audio (needs ffmpeg).

  demo        self-check of the ranking and control-group logic.

Whisper is free and drops some fillers. Scribe keeps every filler and false
start, which makes the voice profile better. --engine picks one.

Usage:
  python3 scripts/fetch.py doctor
  python3 scripts/fetch.py setkey [--gemini]
  python3 scripts/fetch.py list <handle> [--platform tiktok] [--limit 40]
  python3 scripts/fetch.py transcribe <handle> [--top 8] [--control 2] [--ids ID,ID]
                                                [--engine whisper|scribe]

Output lands in ./creator-teardowns/<handle>/, under the folder you run it from.

Cost: list and Whisper are free. Scribe is ~0.37c per minute of audio ($0.22/hour).

Exit codes: 0 ok - 1 error, or doctor found something to fix - 2 usage
"""
import argparse
import datetime
import glob
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

from transcribe import KEY_FILE, VENV_PY, find_key

OUT_ROOT = Path.cwd() / "creator-teardowns"
SELF = Path(__file__).resolve()
TRANSCRIBE = SELF.with_name("transcribe.py")
LOCK = SELF.parents[1] / "requirements.lock"   # ai-editor's pins for what this skill uses (check_plugins.py keeps it in sync)
OS = platform.system()  # Darwin, Windows, Linux
PY = "py" if OS == "Windows" else "python3"

PROFILE_URL = {
    "tiktok": "https://www.tiktok.com/@{h}",
    "youtube": "https://www.youtube.com/@{h}/shorts",
    "instagram": "https://www.instagram.com/{h}/reels/",
}

# Fields we keep off the flat-playlist dump. Anything else is noise.
KEEP = ("id", "title", "description", "duration", "view_count", "like_count",
        "comment_count", "repost_count", "save_count", "timestamp", "webpage_url")


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def ytdlp():
    """The pinned yt-dlp in the tool venv (the version CI checks weekly), else one on PATH."""
    if VENV_PY.exists() and run([str(VENV_PY), "-m", "yt_dlp", "--version"]).returncode == 0:
        return [str(VENV_PY), "-m", "yt_dlp"]
    if shutil.which("yt-dlp"):
        return [shutil.which("yt-dlp")]
    return None


def ai_editor_setup():
    """ai-editor's setup.py when that plugin is installed (this repo's copy, or the plugin cache), else None."""
    cands = [SELF.parents[4] / "ai-editor" / "skills" / "setup" / "scripts" / "setup.py"]
    cands += [Path(p) for p in sorted(glob.glob(str(Path.home() / ".claude" / "plugins" / "**" / "skills" / "setup"
                                                    / "scripts" / "setup.py"), recursive=True), reverse=True)]
    return next((p for p in cands if p.is_file() and (p.parents[3] / "lib" / "ai_editor").is_dir()), None)


def install_fixes(setup, os_name=None):
    """The fix lines for the tool venv, all from pinned, hash-checked versions.
    With ai-editor: its bootstrap (first install) and repair (drift). Without: this skill's lock."""
    if setup:
        return {"venv": f'{PY} "{setup}" bootstrap',
                "update": f'claude plugin update ai-editor@nextwork, then {PY} "{setup}" repair',
                "ocr": f'{PY} "{setup}" repair'}
    o = os_name or OS
    if o == "Windows":
        venv, pip = "py -m venv %USERPROFILE%\\.ai-video-editor\\venv", "%USERPROFILE%\\.ai-video-editor\\venv\\Scripts\\pip"
    else:
        venv, pip = "python3 -m venv ~/.ai-video-editor/venv", "~/.ai-video-editor/venv/bin/pip"
    pin = f'{pip} install --no-deps --require-hashes -r "{LOCK}"'
    tail = "   (needs: sudo apt install -y python3-venv)" if o == "Linux" else ""
    return {"venv": f"{venv} && {pin}{tail}",
            "update": f"claude plugin update creator-teardown@nextwork, then {pin}",
            "ocr": pin}


def tool_python():
    """The venv python when it exists: faster-whisper, numpy and pillow live there."""
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def slug(handle):
    return re.sub(r"[^a-z0-9._-]", "", handle.lstrip("@").lower())


def fix(mac, win, linux):
    return {"Darwin": mac, "Windows": win}.get(OS, linux)


def reach(v):
    """Views, or likes where the platform hides views (single Instagram reels via yt-dlp)."""
    return v.get("view_count") or v.get("like_count") or 0


def platform_of(urls):
    hosts = {("instagram" if "instagram.com" in u else "youtube" if "youtu" in u else "tiktok") for u in urls}
    return hosts.pop() if len(hosts) == 1 else "mixed"


def count_line(top, control):
    """The first line download and transcribe print: --top N takes N plus the control group."""
    return (f"{len(top)} most-viewed + {len(control)} control (closest to the median) = "
            f"{len(top) + len(control)} videos")


def pick(videos, median, top, control):
    """The `top` most-viewed, plus the `control` videos closest to the median.

    The control group is what separates a creator's habits from the reason a
    video won: a move in the winner AND the median videos is a habit.
    """
    ranked = sorted(videos, key=reach, reverse=True)
    rest = [v for v in ranked[top:] if reach(v)]
    rest.sort(key=lambda v: abs(reach(v) - median))
    return ranked[:top], rest[:control]


def cmd_doctor(args):
    required_missing = 0
    print(f"creator-teardown doctor ({ {'Darwin': 'macOS'}.get(OS, OS) })\n")

    def row(state, what, how=None):
        print(f"  {state:<9} {what}")
        if how:
            print(f"  {'':<9} fix: {how}")

    v = sys.version_info
    if v >= (3, 9):
        row("ok", f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        required_missing += 1
        row("FIX", f"Python {v.major}.{v.minor} is too old (need 3.9+)",
            fix("brew install python", "winget install -e --id Python.Python.3.13",
                "sudo apt install -y python3"))

    fixes = install_fixes(ai_editor_setup())
    venv_fix = fixes["venv"]
    if not VENV_PY.exists():
        required_missing += 1
        row("FIX", f"no tool venv at {VENV_PY.parent.parent} (it holds faster-whisper, numpy, pillow)",
            venv_fix)
    else:
        mods = {m: run([str(VENV_PY), "-c", f"import {m}"]).returncode == 0
                for m in ("faster_whisper", "numpy", "PIL")}
        if all(mods.values()):
            row("ok", f"venv {VENV_PY.parent.parent}: faster-whisper, numpy, pillow")
        else:
            required_missing += 1
            gone = ", ".join(m for m, ok in mods.items() if not ok)
            row("FIX", f"the venv is missing {gone}", venv_fix)

    yt = ytdlp()
    if yt:
        ver = run(yt + ["--version"]).stdout.strip()
        row("ok", f"yt-dlp {ver}")
        try:
            age = (datetime.date.today() - datetime.date(*map(int, ver.split(".")[:3]))).days
            if age > 90:
                row("update", f"yt-dlp is {age} days old. TikTok changes often.", fixes["update"])
        except ValueError:
            pass
    else:
        required_missing += 1
        row("FIX", "yt-dlp is not installed (it lists the videos)", venv_fix)

    if shutil.which("ffmpeg"):
        row("ok", "ffmpeg")
    else:
        required_missing += 1
        row("FIX", "ffmpeg is not installed (it reads the audio and the frames)",
            fix("brew install ffmpeg", "winget install -e --id Gyan.FFmpeg",
                "sudo apt install -y ffmpeg"))

    key, where = find_key()
    if key:
        row("ok", f"ElevenLabs key, from {where}. Transcripts use Scribe v2.")
    else:
        row("optional", "no ElevenLabs key. Transcripts use Whisper (free). A key gives "
            "Scribe v2, which keeps every filler.",
            f"{PY} \"{SELF}\" setkey   (run it in a terminal window, not in the Claude chat)")

    # The look pass: OCR reads the captions, Gemini names the font and graphics style.
    if VENV_PY.exists():
        ocr = "ocrmac" if OS == "Darwin" else "rapidocr_onnxruntime"
        alt = "" if OS == "Darwin" else " or rapidocr"
        has = run([str(VENV_PY), "-c", f"import {ocr}"]).returncode == 0 or (
            OS != "Darwin" and run([str(VENV_PY), "-c", "import rapidocr"]).returncode == 0)
        if has:
            row("ok", f"{ocr}{alt}: captions are measured, not read off images")
        else:
            row("optional", f"no {ocr}{alt}. Without it captions fall back to frame sheets.",
                fixes["ocr"])
    gkey, gwhere = find_key("GEMINI_API_KEY")
    if gkey:
        row("ok", f"Gemini key, from {gwhere}. The look pass runs on Gemini Flash-Lite.")
    else:
        row("optional", "no Gemini key. The look pass falls back to one frame sheet per "
            "video. A free key: aistudio.google.com/apikey",
            f"{PY} \"{SELF}\" setkey --gemini   (in a terminal window, not in the Claude chat)")

    print()
    if required_missing:
        print(f"Not ready: {required_missing} thing{'s' if required_missing > 1 else ''} to fix.")
        sys.exit(1)
    print("Ready.")


def save_key(var, key, path=None):
    """Writes var=key into the key file, keeping the other keys in it."""
    path = path or KEY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = [ln for ln in (path.read_text().splitlines() if path.exists() else [])
            if ln.strip() and not ln.startswith(f"{var}=")]
    path.write_text("\n".join(keep + [f"{var}={key}"]) + "\n")


def cmd_setkey(args):
    import getpass
    name, var, where = (("Gemini", "GEMINI_API_KEY", "aistudio.google.com/apikey") if args.gemini
                        else ("ElevenLabs", "ELEVENLABS_API_KEY",
                              "Developers > API Keys on elevenlabs.io"))
    if sys.stdin.isatty():
        key = getpass.getpass(f"Paste your {name} API key and press Enter (it stays hidden): ")
    else:
        key = sys.stdin.readline()
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{20,}", key):
        sys.exit(f"That doesn't look like a {name} key. Copy it again from {where}.")
    save_key(var, key)
    try:
        KEY_FILE.chmod(0o600)  # readable by you only
    except OSError:
        pass
    print(f"Saved to {KEY_FILE}. It works from any folder now.")
    print(f"Check everything with: {PY} \"{SELF}\" doctor")


def cmd_list(args):
    handle = slug(args.handle)
    outdir = OUT_ROOT / handle
    outdir.mkdir(parents=True, exist_ok=True)

    if args.urls:
        # Hand-picked mode: a file of one URL per line. This is how the existing
        # teardowns were actually built -- specific videos, not whole profiles.
        targets = [u.strip() for u in Path(args.urls).read_text().splitlines()
                   if u.strip() and not u.strip().startswith("#")]
        if not targets:
            sys.exit(f"no urls in {args.urls}")
        url = f"{len(targets)} hand-picked urls"
        print(f"pulling {url} ...", file=sys.stderr)
        # -i: one private or removed post must not stop the rest.
        r = run(ytdlp() + ["--dump-json", "--no-warnings", "-i", *targets])
        args.platform = platform_of(targets)
        bad = [ln for ln in r.stderr.splitlines() if ln.startswith("ERROR")]
        if bad:
            print(f"{len(bad)} link(s) failed (private, removed, or login-walled):", file=sys.stderr)
            for ln in bad[:10]:
                print("  " + ln[:200], file=sys.stderr)
    else:
        url = PROFILE_URL[args.platform].format(h=handle)
        print(f"pulling {args.limit} from {url} ...", file=sys.stderr)
        r = run(ytdlp() + ["--flat-playlist", "--dump-json", "--no-warnings",
                 "--playlist-end", str(args.limit), url])

    if not r.stdout.strip():
        hint = ("\n\nUpdate yt-dlp and try again, or pass links to single videos "
                "with --urls. Run doctor for the update command.")
        if args.platform == "instagram":
            hint = ("\n\nInstagram profiles are login-walled for yt-dlp. Single reel links "
                    "work: paste them one per line into a file and run `list <name> --urls "
                    "file`. Or use the creator's TikTok or YouTube handle.")
        sys.exit(f"yt-dlp returned nothing.\n{r.stderr.strip()[:800]}{hint}")

    vids = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        v = {k: d.get(k) for k in KEEP}
        if not v.get("webpage_url"):
            v["webpage_url"] = d.get("url")
        vids.append(v)

    if not vids:
        sys.exit(f"parsed 0 videos.\n{r.stderr.strip()[:800]}")

    by = "views" if any(v.get("view_count") for v in vids) else "likes"
    views = [reach(v) for v in vids if reach(v)]
    median = statistics.median(views) if views else 0
    for v in vids:
        vc = reach(v)
        v["vs_median"] = round(vc / median, 2) if median else None
        v["outlier"] = bool(median and vc >= 3 * median)

    vids.sort(key=reach, reverse=True)
    payload = {"handle": handle, "platform": args.platform, "profile_url": url,
               "count": len(vids), "median_views": median, "ranked_by": by, "videos": vids}
    if by == "likes":
        print("No view counts on these links (Instagram hides them from yt-dlp): ranked by likes.",
              file=sys.stderr)
    (outdir / "videos.json").write_text(json.dumps(payload, indent=2))

    print(f"\n{len(vids)} videos - median {median:,.0f} {by}\n")
    print(f"{by:>10}  {'xmed':>5}  {'sec':>4}  id")
    for v in vids[:25]:
        flag = " *" if v["outlier"] else "  "
        print(f"{reach(v):>10,}  {str(v['vs_median'] or '-'):>5}"
              f"  {str(v.get('duration') or '-'):>4}  {v['id']}{flag}")
    print(f"\n-> {outdir / 'videos.json'}   (* = >=3x median)")


def download_audio(v, audio_dir):
    """Fallback for links Scribe can't fetch. yt-dlp -x needs ffmpeg."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    existing = list(audio_dir.glob(f"{v['id']}.*"))
    if existing:
        return existing[0]
    if not shutil.which("ffmpeg"):
        print("  downloading needs ffmpeg, which isn't installed (doctor has the fix)",
              file=sys.stderr)
        return None
    # -x forces an ffmpeg audio extraction, so a video-only stream fails loudly
    # here instead of producing a silent file. TikTok serves HEVC variants with
    # no audio track under a plain "ba/b" selector.
    r = run(ytdlp() + ["-f", "ba/b", "-x", "--audio-format", "mp3", "--no-warnings",
             "-o", str(audio_dir / "%(id)s.%(ext)s"), v["webpage_url"]])
    existing = list(audio_dir.glob(f"{v['id']}.*"))
    if not existing:
        print(f"  download failed: {r.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return existing[0]


def cmd_transcribe(args):
    handle = slug(args.handle)
    outdir = OUT_ROOT / handle
    meta_path = outdir / "videos.json"
    if not meta_path.exists():
        sys.exit(f"no {meta_path}. Run `list {handle}` first.")
    if not TRANSCRIBE.exists():
        sys.exit(f"missing {TRANSCRIBE}")

    meta = json.loads(meta_path.read_text())
    by_id = {v["id"]: v for v in meta["videos"]}
    median = meta.get("median_views") or 0

    if args.ids:
        ids = args.ids.split(",")
        missing = [i for i in ids if i not in by_id]
        if missing:
            sys.exit(f"unknown ids: {', '.join(missing)}")
        todo = [(by_id[i], "picked") for i in ids]
    else:
        top, control = pick(meta["videos"], median, args.top, args.control)
        todo = [(v, "top") for v in top] + [(v, "control") for v in control]
        print(count_line(top, control) + f", median {median:,.0f} views")
    if not todo:
        sys.exit("nothing to transcribe")

    tdir = outdir / "transcripts"
    tdir.mkdir(exist_ok=True)
    engine = args.engine or ("scribe" if find_key()[0] else "whisper")
    total_sec = sum(v.get("duration") or 0 for v, _ in todo)
    cost = f"~{total_sec/60*0.37:.1f}c" if engine == "scribe" else "free"
    print(f"{len(todo)} videos, ~{total_sec}s audio, {engine}, {cost}\n", file=sys.stderr)

    done, failed = [], []
    for i, (v, role) in enumerate(todo, 1):
        vid = v["id"]
        tag = f"[{i}/{len(todo)}] {vid} ({role}, {v.get('view_count') or 0:,} views)"
        tj = tdir / f"{vid}.json"
        if tj.exists() and not args.force:
            print(f"{tag} cached", file=sys.stderr)
            done.append(vid)
            continue

        print(f"{tag} transcribing", file=sys.stderr)
        eng = ["--engine", engine]
        local = sorted((outdir / "video").glob(f"{vid}.mp4"))
        if engine == "whisper":
            media = local[0] if local else download_audio(v, outdir / "audio")
            if not media:
                failed.append(vid)
                continue
            r = run([tool_python(), str(TRANSCRIBE), str(media), str(tj)] + eng)
            if r.returncode != 0 or not tj.exists():
                print(f"  {r.stderr.strip()[-300:]}", file=sys.stderr)
                failed.append(vid)
                continue
        else:
            # Scribe fetches TikTok and YouTube links itself: no download, no ffmpeg.
            r = run([sys.executable, str(TRANSCRIBE), v["webpage_url"], str(tj)] + eng)
        if r.returncode != 0 or not tj.exists():
            err = r.stderr.strip()
            if r.returncode == 2 or "HTTP 401" in err or "HTTP 403" in err:
                # A key problem fails every video the same way, so stop here.
                sys.exit(f"{err[:400]}\n\nFix the key, then rerun. "
                         f"Check it with: {PY} \"{SELF}\" doctor")
            print("  ElevenLabs couldn't fetch the link, downloading the audio instead",
                  file=sys.stderr)
            audio = download_audio(v, outdir / "audio")
            if not audio:
                failed.append(vid)
                continue
            r = run([sys.executable, str(TRANSCRIBE), str(audio), str(tj)] + eng)
            if r.returncode != 0 or not tj.exists():
                print(f"  {r.stderr.strip()[:300]}", file=sys.stderr)
                failed.append(vid)
                continue

        # Flat text + words-per-minute, the two things the analysis reads.
        data = json.loads(tj.read_text())
        text = data.get("text") or " ".join(
            w.get("text", "") for w in data.get("words", []))
        text = re.sub(r"\s+", " ", text).strip()
        dur = v.get("duration") or 0
        wpm = round(len(text.split()) / dur * 60) if dur else 0
        (tdir / f"{vid}.txt").write_text(
            f"# {vid} - {role} - {v.get('view_count') or 0:,} views - {dur}s - {wpm} wpm\n"
            f"# {v['webpage_url']}\n\n{text}\n")
        done.append(vid)

    print(f"\n{len(done)} ok, {len(failed)} failed -> {tdir}")
    if failed:
        print(f"failed: {','.join(failed)}  (retry: --ids {','.join(failed)})")


def demo():
    """Self-check: the things that silently corrupt a teardown."""
    # Ranking must survive missing view counts rather than crashing.
    vids = [{"id": "a", "view_count": 900}, {"id": "b", "view_count": None},
            {"id": "c", "view_count": 100}]
    vids.sort(key=lambda v: v.get("view_count") or 0, reverse=True)
    assert [v["id"] for v in vids] == ["a", "c", "b"], vids

    # Outlier flag is relative to THIS creator's median, not an absolute.
    views = [100, 100, 100, 900]
    med = statistics.median(views)
    assert med == 100 and (900 >= 3 * med) and not (100 >= 3 * med)

    # Control group: the videos closest to the median, never a top pick again.
    vids = [{"id": str(i), "view_count": n}
            for i, n in enumerate([9000, 5000, 4800, 4700, 1000, 300])]
    top, control = pick(vids, 4750, 1, 2)
    assert [v["id"] for v in top] == ["0"], top
    assert [v["id"] for v in control] == ["2", "3"], control
    assert count_line(top, control).startswith("1 most-viewed + 2 control") and "= 3 videos" in count_line(top, control)

    assert slug("@Some.Creator") == "some.creator"

    # Instagram links carry likes, not views: rank and pick on likes.
    ig = [{"id": "a", "like_count": 900}, {"id": "b", "like_count": 100}, {"id": "c", "like_count": 120}]
    top, control = pick(ig, 120, 1, 1)
    assert [v["id"] for v in top] == ["a"] and [v["id"] for v in control] == ["c"], (top, control)
    assert platform_of(["https://www.instagram.com/reel/X/", "https://instagram.com/p/Y"]) == "instagram"
    assert platform_of(["https://www.tiktok.com/@a/video/1", "https://youtu.be/x"]) == "mixed"

    # Every install line is pinned: ai-editor's bootstrap / repair when it is there, else this
    # skill's hash-checked lock, which holds ai-editor's exact pins for everything it lists.
    for setup in (None, Path("/x/ai-editor/skills/setup/scripts/setup.py")):
        for o in ("Darwin", "Windows", "Linux"):
            for k, line in install_fixes(setup, o).items():
                assert "brew" not in line and "pipx" not in line and "winget" not in line, line
                assert "pip install" not in line or "--require-hashes" in line, line
                assert (("bootstrap" if k == "venv" else "repair") in line) == bool(setup), (k, line)
    pins = {m[1]: m[2] for m in re.finditer(r"^([a-z0-9._-]+)==(\S+)", LOCK.read_text(encoding="utf-8"), re.M)}
    assert {"yt-dlp", "faster-whisper", "numpy", "pillow", "opencv-python-headless"} <= set(pins), pins
    assert LOCK.read_text(encoding="utf-8").count("--hash=sha256:") > len(pins)

    # Saving one key keeps the other.
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / ".env"
        save_key("ELEVENLABS_API_KEY", "a" * 24, f)
        save_key("GEMINI_API_KEY", "b" * 24, f)
        save_key("GEMINI_API_KEY", "c" * 24, f)
        assert f.read_text() == f"ELEVENLABS_API_KEY={'a' * 24}\nGEMINI_API_KEY={'c' * 24}\n"
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    p = sub.add_parser("setkey")
    p.add_argument("--gemini", action="store_true", help="save a Gemini key instead")
    p.set_defaults(fn=cmd_setkey)

    p = sub.add_parser("list")
    p.add_argument("handle", help="used to name the output folder")
    p.add_argument("--platform", default="tiktok", choices=sorted(PROFILE_URL))
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--urls", default=None,
                   help="file of hand-picked video URLs, one per line "
                        "(ignores --platform/--limit)")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("transcribe")
    p.add_argument("handle")
    p.add_argument("--top", type=int, default=8, help="most-viewed videos to take; --control more are added (default 2)")
    p.add_argument("--control", type=int, default=2,
                   help="videos closest to the median, as a control group")
    p.add_argument("--ids", default=None,
                   help="comma-separated video ids (replaces --top/--control)")
    p.add_argument("--engine", choices=["whisper", "scribe"], default=None,
                   help="default: scribe if an ElevenLabs key exists, else whisper")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_transcribe)

    sub.add_parser("demo").set_defaults(fn=lambda a: demo())

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
