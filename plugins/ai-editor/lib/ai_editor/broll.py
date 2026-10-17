#!/usr/bin/env python3
"""B-roll libraries: a named folder of the user's own clips per type of video, for Claude to pick from.

    python3 broll.py list                    every library in the profile: name, folder, clip count
    python3 broll.py sheet <name>            index the library's clips and draw numbered contact sheets
    python3 broll.py add <name> <folder>     save a library in the profile
    python3 broll.py drives                  the Google Drive folders the Drive app mounts here
    python3 broll.py demo                    self-check (needs ffmpeg)

The profile holds the libraries (profile.py set 'broll.travel="/path/to/folder"'):

  "broll": {"travel": "~/Library/CloudStorage/GoogleDrive-me@x.com/My Drive/B-roll/Travel",
            "desk":   "/Users/me/Movies/desk clips"}

A Google Drive folder is read through the Google Drive desktop app, which mounts Drive as a local folder
(~/Library/CloudStorage/GoogleDrive-<email>/ on a Mac, a G: drive on Windows). Online-only files download
when ffmpeg first reads them.

`sheet` writes $AI_EDITOR_HOME/broll/<name>/: index.json ({"clips": [{"n", "path", "duration"}]}) and
sheet-01.jpg ... (12 clips each, left to right, top to bottom, numbered n = 1, 2, ... in index order; the
frame is the middle of the clip). It prints the sheet paths. Look at every sheet, pick the clips that fit
the lines, copy them into EDIT/images/ and use each as a `video_card` (or the full frame). Re-runs reuse
the sheets while the folder's files are unchanged. Needs ffmpeg and ffprobe. Stdlib only.

The editor's New video page (home.py) lists the libraries (listing), browses Drive (drives, browse), adds one
(add) and sends the ones the user ticked with the job: brief() writes EDIT/broll.json
({"auto", "libraries": [{"name", "folder"}]}: the ticked ones, or with "Claude decides" every library and
auto true, so Claude picks the ones that fit) and EDIT/instructions.md ("Additional instructions
for Claude"). The job line carries both paths (broll=, instructions=).
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
PER_SHEET, COLS, BOX = 12, 4, 320
MAX_CLIPS = 240   # ponytail: one frame per clip, 240 clips = 20 sheets; split a bigger folder into libraries
NOTE_MAX = 4000   # characters of "Additional instructions for Claude"


def _profile_path():
    """profile.py's file, found from the environment on every call (a self-check sets AI_EDITOR_HOME late)."""
    return Path(os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor") / "profile.json"


def _raw():
    """Only what the user answered, never profile.py's DEFAULTS (so missing() still asks the rest)."""
    try:
        return json.loads(_profile_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def libraries():
    return {k: str(Path(os.path.expanduser(v))) for k, v in (_raw().get("broll") or {}).items()}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "library"


def videos_in(folder):
    """Video files directly in folder (not below): cheap enough to count per row of the Drive browser."""
    try:
        return sum(1 for p in Path(folder).iterdir() if p.suffix.lower() in EXTS and not p.name.startswith("."))
    except OSError:
        return 0


def listing():
    """Every library for the page: name, folder, clip count (to MAX_CLIPS), its first clip for the picture."""
    out = []
    for name, folder in libraries().items():
        found = clips(folder) if Path(folder).is_dir() else []
        out.append({"name": name, "folder": folder, "clips": len(found), "missing": not Path(folder).is_dir(),
                    "first": str(found[0]) if found else ""})
    return out


def drives(home=None):
    """The Drive app's mounts: ~/Library/CloudStorage/GoogleDrive-<email>/My Drive on a Mac, X:\\My Drive on Windows."""
    home = Path(home or Path.home())
    found = [{"label": d.name.split("-", 1)[1].split(" (")[0], "path": str(d / "My Drive")}
             for d in sorted((home / "Library" / "CloudStorage").glob("GoogleDrive-*")) if (d / "My Drive").is_dir()]
    if os.name == "nt":
        found += [{"label": f"{c}: drive", "path": f"{c}:\\My Drive"} for c in "DEFGHIJKLMNOPQRSTUVWXYZ"
                  if Path(f"{c}:\\My Drive").is_dir()]
    return found


def browse(folder):
    """One level of a folder for the Drive browser: its subfolders, each with the videos directly in it."""
    f = Path(folder)
    subs = sorted((d for d in f.iterdir() if d.is_dir() and not d.name.startswith(".")), key=lambda d: d.name.lower())
    return {"path": str(f), "videos": videos_in(f),
            "folders": [{"name": d.name, "path": str(d), "videos": videos_in(d)} for d in subs]}


def add(name, folder):
    """Save a library in the profile. Returns the error to show, or ""."""
    name, folder = str(name or "").strip(), str(Path(os.path.expanduser(str(folder or "").strip())))
    if not name or len(name) > 40:
        return "Give it a short name."
    if not Path(folder).is_dir():
        return "That folder is not on this computer."
    raw = _raw()
    raw.setdefault("broll", {})[name] = folder
    _profile_path().parent.mkdir(parents=True, exist_ok=True)
    _profile_path().write_text(json.dumps(raw, indent=1), encoding="utf-8")
    return ""


def brief(edit, names, note, auto=False):
    """The job's b-roll picks and instructions, in the edit folder. auto ("Claude decides"): every library, and
    Claude picks which fit. Returns the job-line args written."""
    edit, libs, args = Path(edit), libraries(), {}
    picked = [{"name": n, "folder": f} for n, f in libs.items()] if auto else \
        [{"name": n, "folder": libs[n]} for n in dict.fromkeys(names or []) if n in libs]
    if picked:
        (edit / "broll.json").write_text(json.dumps({"auto": bool(auto), "libraries": picked}, indent=1), encoding="utf-8")
        args["broll"] = str(edit / "broll.json")
    note = str(note or "").strip()[:NOTE_MAX]
    if note:
        (edit / "instructions.md").write_text(note + "\n", encoding="utf-8")
        args["instructions"] = str(edit / "instructions.md")
    return args


def clips(folder):
    return sorted((p for p in Path(folder).rglob("*") if p.suffix.lower() in EXTS and not p.name.startswith(".")),
                  key=lambda p: str(p).lower())[:MAX_CLIPS]


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return round(float(r.stdout.strip()), 2)
    except ValueError:
        return None   # unreadable: left out of the sheets


def sheet(name, folder, out=None):
    out = Path(out or _profile_path().parent / "broll" / slug(name))
    found = clips(folder)
    if not found:
        raise SystemExit(f"no video files in {folder}")
    key = hashlib.sha1(json.dumps([[str(p), p.stat().st_size, int(p.stat().st_mtime)] for p in found]).encode()).hexdigest()
    idx = out / "index.json"
    if idx.exists() and json.loads(idx.read_text(encoding="utf-8")).get("key") == key:
        return json.loads(idx.read_text(encoding="utf-8"))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rows = []
    # every frame padded to one size here: a size change mid-sequence restarts ffmpeg's tile and drops earlier cells
    pad = f"scale={BOX}:{BOX}:force_original_aspect_ratio=decrease,pad={BOX}:{BOX}:(ow-iw)/2:(oh-ih)/2:color=black"
    with tempfile.TemporaryDirectory() as tmp:
        for p in found:
            d = duration(p)
            if not d:
                continue
            rows.append({"n": len(rows) + 1, "path": str(p), "duration": d})
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(d / 2), "-i", str(p), "-frames:v", "1",
                            "-vf", pad, f"{tmp}/f{len(rows):04d}.png"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{tmp}/f%04d.png", "-vf",
                        f"drawbox=0:0:{BOX}:{BOX}:white@0.5:2,tile={COLS}x{PER_SHEET // COLS}",
                        "-q:v", "3", "-start_number", "1", str(out / "sheet-%02d.jpg")], check=True)
    data = {"name": name, "folder": str(folder), "key": key, "per_sheet": PER_SHEET, "cols": COLS, "clips": rows,
            "sheets": [str(s) for s in sorted(out.glob("sheet-*.jpg"))]}
    idx.write_text(json.dumps(data, indent=1), encoding="utf-8")
    return data


def demo():
    with tempfile.TemporaryDirectory() as t:
        src = Path(t, "lib")
        (src / "sub").mkdir(parents=True)
        for i, p in enumerate([src / "a.mp4", src / "sub" / "b.MOV", *(src / f"c{k}.mp4" for k in range(12))]):
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=d=1:s={'160x284' if i % 2 else '284x160'}:r=10",
                            "-vf", f"hue=h={i * 25}", str(p)], check=True)
        (src / "notes.txt").write_text("x", encoding="utf-8")
        d = sheet("t", src, Path(t, "out"))
        assert len(d["clips"]) == 14 and d["clips"][0]["path"].endswith("a.mp4"), d["clips"][:2]
        assert [Path(s).name for s in d["sheets"]] == ["sheet-01.jpg", "sheet-02.jpg"], d["sheets"]
        stamp = Path(d["sheets"][0]).stat().st_mtime_ns
        assert sheet("t", src, Path(t, "out"))["key"] == d["key"]
        assert Path(d["sheets"][0]).stat().st_mtime_ns == stamp   # unchanged folder: cached
        # profile, Drive mounts, browse, brief: on a throwaway AI_EDITOR_HOME
        old = os.environ.get("AI_EDITOR_HOME")
        os.environ["AI_EDITOR_HOME"] = str(Path(t, "home"))
        try:
            Path(t, "home").mkdir()
            _profile_path().write_text(json.dumps({"platform": "tiktok"}), encoding="utf-8")
            assert add("Desk", src) == "" and add("", src) and add("Gone", Path(t, "nope"))
            raw = _raw()
            assert raw["broll"] == {"Desk": str(src)} and "creators" not in raw, raw   # DEFAULTS never written in
            row = listing()[0]
            assert row["name"] == "Desk" and row["clips"] == 14 and row["first"].endswith("a.mp4"), row
            b = browse(src)
            assert b["videos"] == 13 and [x["name"] for x in b["folders"]] == ["sub"] and b["folders"][0]["videos"] == 1, b
            mnt = Path(t, "fakehome", "Library", "CloudStorage", "GoogleDrive-me@x.com (1-1-2026)", "My Drive")
            mnt.mkdir(parents=True)
            assert drives(Path(t, "fakehome")) == [{"label": "me@x.com", "path": str(mnt)}]
            e = Path(t, "edit")
            e.mkdir()
            assert brief(e, [], " ") == {}
            got = brief(e, ["Desk", "Desk", "Unknown"], "Desk for the intro.")
            assert json.loads((e / "broll.json").read_text(encoding="utf-8")) == {"auto": False, "libraries": [{"name": "Desk", "folder": str(src)}]}
            add("Screen", src / "sub")
            brief(e, [], "", auto=True)
            assert [x["name"] for x in json.loads((e / "broll.json").read_text(encoding="utf-8"))["libraries"]] == ["Desk", "Screen"]
            assert (e / "instructions.md").read_text(encoding="utf-8") == "Desk for the intro.\n" and set(got) == {"broll", "instructions"}
            assert slug("Me on camera") == "me-on-camera"
        finally:
            if old is None:
                os.environ.pop("AI_EDITOR_HOME")
            else:
                os.environ["AI_EDITOR_HOME"] = old
    print("broll demo ok")


def main():
    a = sys.argv[1:]
    if a[:1] == ["list"]:
        for k, v in libraries().items():
            n = len(clips(v)) if Path(v).is_dir() else "folder not found"
            print(f"{k}\t{v}\t{n}")
        if not libraries():
            print("no b-roll libraries: profile.py set 'broll.<name>=\"<folder>\"'")
    elif a[:1] == ["sheet"] and len(a) == 2:
        libs = libraries()
        if a[1] not in libs:
            raise SystemExit(f"no library {a[1]!r}; have: {', '.join(libs) or 'none'}")
        d = sheet(a[1], libs[a[1]])
        print(f"{len(d['clips'])} clips, index {Path(d['sheets'][0]).parent / 'index.json'}")
        print("\n".join(d["sheets"]))
    elif a[:1] == ["add"] and len(a) == 3:
        err = add(a[1], a[2])
        print(err or f"saved {a[1]} -> {a[2]}")
        sys.exit(1 if err else 0)
    elif a[:1] == ["drives"]:
        print(json.dumps(drives(), indent=1))
    elif a[:1] == ["demo"]:
        demo()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
