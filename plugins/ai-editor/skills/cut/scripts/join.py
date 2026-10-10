#!/usr/bin/env python3
"""Join several takes of one video into a single source for the cut, with audio sync checked.

    python3 join.py edits/NAME/joined.mp4 take1.mov take2.mov ...   join in the order given
    python3 join.py edits/NAME/joined.mp4 --sort name|created a.mov b.mov
    python3 join.py demo                                               self-check (needs ffmpeg)

Each clip is normalised to the first clip's picture size (as displayed, rotation applied), its frame
rate snapped to a standard one, and 48 kHz stereo audio. Other sizes and rotations are fitted with
black bars, never stretched. Variable frame rate phone clips come out constant. A clip with no
audio gets silence. Each part is rendered alone with its audio left as PCM, then the parts are
joined with no video re-encode and the audio encoded once. Joining AAC parts as a stream copy left
the audio 21 ms late: each part's encoder delay was no longer trimmed.
Writes <out>.parts.json: where each clip starts in the joined file, its video and audio length, and
its full path.

Exit 1 when any part or the joined file has audio and video lengths more than 0.1 s apart, or one
stream starting more than half a frame after the other. One filter
graph trimming and joining several phone clips at once once shipped a 69 s video with 54 s of
audio, while each clip was fine alone.
ponytail: HDR (HLG/PQ) phone clips are squashed to 8-bit SDR with no tone map, so colours can look
flat. Add a zscale tone map if that matters.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction as F

TOL = 0.1
RATES = [F(24000, 1001), F(24), F(25), F(30000, 1001), F(30), F(50), F(60000, 1001), F(60)]


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"no such file or not a video: {path}")
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if not v:
        sys.exit(f"no video stream: {path}")
    rot = next((sd.get("rotation", 0) for sd in v.get("side_data_list", []) if "rotation" in sd), 0)
    w, h = (v["height"], v["width"]) if abs(int(rot)) % 180 == 90 else (v["width"], v["height"])
    fps = F(v.get("avg_frame_rate", "0/0")) if v.get("avg_frame_rate", "0/0") != "0/0" else F(30)
    return {"w": w, "h": h, "fps": fps, "audio": any(s["codec_type"] == "audio" for s in d["streams"]),
            "created": d["format"].get("tags", {}).get("creation_time") or "",
            "mtime": os.path.getmtime(path)}


def durs(path):
    """{"video": s, "audio": s, "video_start": s, "audio_start": s, "fps": f} as far as known."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,duration,start_time,r_frame_rate", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    d = {}
    for st in json.loads(out)["streams"]:
        kind, val = st.get("codec_type"), st.get("duration")
        if kind in ("video", "audio") and kind not in d and val not in (None, "N/A"):
            d[kind] = float(val)
            if st.get("start_time") not in (None, "N/A"):
                d[kind + "_start"] = float(st["start_time"])
            if kind == "video" and st.get("r_frame_rate", "0/0") != "0/0":
                d["fps"] = float(F(st["r_frame_rate"]))
    return d


def check(path, want=None, tol_want=TOL):
    """The file's durs() when audio and video match in length and start; else exit 1."""
    d = durs(path)
    msg = f"{os.path.basename(path)}: video {d.get('video', 0):.2f}s audio {d.get('audio', 0):.2f}s"
    if "audio" not in d or abs(d["video"] - d["audio"]) > TOL or (
            want is not None and abs(d["video"] - want) > tol_want):
        sys.exit(f"FAIL {msg}" + (f" (wanted {want:.2f}s)" if want is not None else "")
                 + ": audio and video lengths differ. Do not cut this file.")
    off = d.get("audio_start", 0.0) - d.get("video_start", 0.0)
    if abs(off) > 0.5 / d.get("fps", 30):
        sys.exit(f"FAIL {msg}: audio and video start {abs(off) * 1000:.1f} ms apart, over half a frame. "
                 "Do not cut this file.")
    print(f"ok   {msg}")
    return d


def order(clips, sort):
    if sort == "name":
        return sorted(clips, key=lambda c: os.path.basename(c).lower())
    if sort == "created":   # the camera's own timestamp, else the file's modified time
        info = {c: probe(c) for c in clips}
        return sorted(clips, key=lambda c: (info[c]["created"] or "~", info[c]["mtime"]))
    return list(clips)


def join(out, clips):
    info = [probe(c) for c in clips]
    w, h = info[0]["w"] // 2 * 2, info[0]["h"] // 2 * 2
    fps = min(RATES, key=lambda r: abs(r - info[0]["fps"]))
    tmp = tempfile.mkdtemp(prefix="join_")
    parts, placed, total = [], [], 0.0
    for i, (src, inf) in enumerate(zip(clips, info)):
        part = os.path.join(tmp, f"{i:02d}.mov")
        silence = [] if inf["audio"] else ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
        vdur = durs(src).get("video")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src, *silence,
             "-map", "0:v:0", "-map", "0:a:0" if inf["audio"] else "1:a:0",
             "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,"
                    f"setsar=1,fps={fps}:start_time=0,format=yuv420p",
             # both streams start at 0 (a dropped first frame is filled with the next one); audio padded
             # with silence or trimmed to the picture's length, so the two always match
             "-af", "aresample=48000:async=1:first_pts=0,apad", *(["-t", f"{vdur:.3f}"] if vdur else ["-shortest"]),
             "-c:v", "libx264", "-crf", "18", "-preset", "fast",
             "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", part], check=True)
        d = check(part)
        placed.append({"clip": os.path.realpath(src), "start": round(total, 3), "dur": round(d["video"], 3),
                       "audio": round(d["audio"], 3)})
        total += d["video"]
        parts.append(part)
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        # concat quoting: a ' in the temp path (a user name like O'Brien) is closed, escaped, reopened
        f.writelines("file '" + p.replace("'", "'\\''") + "'\n" for p in parts)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    # every part has the same video settings, so the video is a stream copy; the audio is encoded
    # once, so its encoder delay is trimmed once, at the start
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out], check=True)
    total = check(out, total, TOL + 0.02 * len(parts))["video"]   # each join can round by up to a frame
    with open(out + ".parts.json", "w", encoding="utf-8") as f:
        json.dump(placed, f, indent=1)
    shutil.rmtree(tmp)   # the parts of a 4K take run to gigabytes
    print(f"joined {len(clips)} clips into {out}: {total:.2f}s, {w}x{h} at {float(fps):.3f} fps")
    return placed


def demo():
    tmp = tempfile.mkdtemp(prefix="join_demo_")
    ff = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, a)], check=True)  # noqa: E731
    a, b, c = (os.path.join(tmp, n) for n in ("a.mp4", "b.mov", "c.mp4"))
    # a: 1280x720 at 25 fps, audio 0.5 s longer than the picture
    ff("-f", "lavfi", "-i", "testsrc=s=1280x720:r=25:d=2", "-f", "lavfi", "-i", "sine=f=440:d=2.5",
       "-c:v", "libx264", "-c:a", "aac", "-ar", "44100", a)
    # b: 640x480 at 29.97 with every third frame dropped (variable frame rate), mono 22 kHz,
    # then tagged as rotated 90 degrees like a phone held upright
    raw = os.path.join(tmp, "raw.mp4")
    ff("-f", "lavfi", "-i", "testsrc=s=640x480:r=30000/1001:d=3", "-f", "lavfi", "-i", "sine=f=660:d=3",
       "-vf", "select='mod(n\\,3)'", "-fps_mode", "vfr", "-c:v", "libx264", "-c:a", "aac", "-ar", "22050",
       "-ac", "1", raw)
    ff("-display_rotation", "90", "-i", raw, "-c", "copy", b)
    # c: no audio at all
    ff("-f", "lavfi", "-i", "testsrc=s=320x240:r=60:d=1", "-c:v", "libx264", c)
    assert probe(b)["w"] == 480 and probe(b)["h"] == 640, probe(b)
    out = os.path.join(tmp, "out", "joined.mp4")
    placed = join(out, [a, b, c])
    d = durs(out)
    assert abs(d["video"] - d["audio"]) <= TOL, d
    assert abs(d.get("audio_start", 0) - d.get("video_start", 0)) <= 0.5 / 25, d    # in sync from the start
    pj = json.load(open(out + ".parts.json", encoding="utf-8"))
    assert [p["clip"] for p in pj] == [os.path.realpath(x) for x in (a, b, c)] and all("audio" in p for p in pj), pj
    assert abs(d["video"] - 6.0) <= 0.15, d
    assert [p["start"] for p in placed][:2] == [0.0, placed[0]["dur"]], placed
    s = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                   "stream=width,height,r_frame_rate", "-of", "json", out],
                                  capture_output=True, text=True, check=True).stdout)["streams"][0]
    assert (s["width"], s["height"], s["r_frame_rate"]) == (1280, 720, "25/1"), s
    assert order([b, a], "name") == [a, b]
    try:   # the house check: clip a's audio outlasts its picture by 0.5 s
        check(a)
        raise AssertionError("check passed a 0.5 s audio/video gap")
    except SystemExit:
        pass
    late = os.path.join(tmp, "late.mp4")   # audio 50 ms behind the picture, lengths equal
    ff("-i", out, "-itsoffset", "0.05", "-i", out, "-map", "0:v", "-map", "1:a", "-c", "copy", late)
    try:
        check(late)
        raise AssertionError("check passed audio starting 50 ms late")
    except SystemExit as e:
        assert "half a frame" in str(e), e
    shutil.rmtree(tmp)
    print("demo ok")


def main(argv):
    if argv == ["demo"]:
        return demo()
    sort = None
    if "--sort" in argv:
        i = argv.index("--sort")
        sort = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) < 3 or sort not in (None, "name", "created"):
        sys.exit(__doc__)
    join(argv[0], order(argv[1:], sort))


if __name__ == "__main__":
    main(sys.argv[1:])
