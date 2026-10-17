#!/usr/bin/env python3
"""A b-roll reel: a reference reel's cuts, on-screen text and sound, rebuilt over the user's own b-roll.

    python3 run.py reel.py read  <edit> <reel.mp4>   measure the reel -> <edit>/reel.json, reel/audio.m4a, reel/shots.jpg
    python3 run.py reel.py build <edit>              picks.json + reel.json -> <edit>/base.mp4 + <edit>/plan.json
    python3 run.py reel.py demo                      self-check (ffmpeg, the venv: numpy, pillow; OCR is stubbed)

reel.json: {"source", "duration", "width", "height",      (+ reel/ocr.json: every text read; reel/shot-NN.jpg: each shot)
            "shots": [{"n", "start", "end"}],                       cut times from creator-teardown visual.py
            "texts": [{"text", "start", "end", "box": [x, y, w, h] % of the frame, "size_pct", "color", "box_color"}]}
  OCR (look.py's engine: Apple Vision on a Mac, RapidOCR elsewhere) at 3 frames a second; lines that sit together are
  one block, a block held over consecutive samples is one text, its start and end snapped to a cut 0.35 s away.
  Only the reel's captions stay in texts (big, held, centred: caption()); words in the footage stay in ocr.json.
  OCR slips ("Al" for "AI") and a caption read late or merged with a line from the footage: read the shot frames and fix.
  `color` is the text's fill, `box_color` the solid box behind it when there is one (else null: plain text, drawn
  with a dark stroke). Edit texts here before build to change the words (Additional instructions, review notes).
picks.json (Claude writes it from the contact sheets, broll.py sheet): {"shots": [{"clip": "<path>", "from": 0.0}]},
  one per reel shot, in order. A clip shorter than its shot loops.
build: each pick cut to its shot, filled to 1080x1920, joined, the reel's sound under it -> base.mp4; plan.json for
  style-edit's renderer (StyleEdit: base.mp4, no captions, the texts as "onscreen" items). Then
  `edit.py render <edit>` and `review.py <edit> round --video render.mp4 --stage edit --plan plan.json`.
"""
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[3]                       # plugins/ai-editor
TEARDOWN = PLUGIN.parent / "creator-teardown" / "skills" / "creator-teardown" / "scripts"
W, H, FPS = 1080, 1920, 30
OCR_FPS = 3
SNAP_S = 0.35            # a text that starts or ends this close to a cut moves onto it
SAME_TEXT = 0.75         # difflib ratio: OCR reads the same line a little differently frame to frame
NOISE = re.compile(r"tiktok|^@\w|capcut", re.I)   # ponytail: platform watermarks by name; a new app's mark gets through
# The reel's own captions, not words inside its footage (a keyboard, a screen): big, held, centred. Measured on a POV reel
# where every caption passed and no keyboard key, menu or UI label did.
MIN_SIZE, MIN_HOLD, MAX_OFF_CENTRE = 1.8, 0.6, 15   # size_pct, seconds, % of the width from the centre


def ff(*a):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, a)], check=True)


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                        "-of", "json", str(p)], capture_output=True, text=True, check=True)
    j = json.loads(r.stdout)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


def blocks(lines):
    """OCR lines of one frame -> text blocks: lines stacked within 1.2 line heights that overlap sideways."""
    out = []
    for ln in sorted(lines, key=lambda l: l["box"][1]):
        x, y, w, h = ln["box"]
        for b in out:
            bx, by, bw, bh = b["box"]
            if y - (by + bh) < 1.2 * h and min(x + w, bx + bw) > max(x, bx):
                b["lines"].append(ln)
                nx, ny = min(x, bx), min(y, by)
                b["box"] = [nx, ny, max(x + w, bx + bw) - nx, max(y + h, by + bh) - ny]
                break
        else:
            out.append({"lines": [ln], "box": [x, y, w, h]})
    return [{"text": "\n".join(l["text"] for l in b["lines"]), "box": b["box"],
             "line_h": sorted(l["box"][3] for l in b["lines"])[len(b["lines"]) // 2]} for b in out]


def colours(rgb, box):
    """(fill, box colour or None) of one text block on one frame: the text is the minority of the two brightness
    groups inside the box; a solid box is the majority when the ring just outside matches it."""
    import numpy as np
    h, w = rgb.shape[:2]
    x0, y0 = min(w - 2, max(0, int(box[0] * w))), min(h - 2, max(0, int(box[1] * h)))   # OCR boxes can run off the frame
    x1, y1 = min(w, max(x0 + 2, int((box[0] + box[2]) * w))), min(h, max(y0 + 2, int((box[1] + box[3]) * h)))
    px = rgb[y0:y1, x0:x1].reshape(-1, 3).astype(float)
    lum = px @ [0.299, 0.587, 0.114]
    hi = lum > (lum.min() + lum.max()) / 2
    a, b = px[hi], px[~hi]
    text, back = (a, b) if len(a) < len(b) else (b, a)
    hexc = lambda c: "#%02X%02X%02X" % tuple(int(v) for v in np.median(c, 0))   # noqa: E731
    pad = max(2, int((y1 - y0) * 0.15))
    ring = rgb[max(0, y0 - pad):y0, x0:x1].reshape(-1, 3).astype(float)
    solid = len(ring) and len(back) and np.abs(np.median(ring, 0) - np.median(back, 0)).max() < 28 and ring.std(0).max() < 22
    return hexc(text if len(text) else px), (hexc(back) if solid else None)


def track(samples, frames, cuts, dur):
    """Per-frame blocks -> timed texts."""
    live, done = [], []
    for s in samples:
        seen = set()
        for b in s["blocks"]:
            if NOISE.search(b["text"]):
                continue
            m = next((x for x in live if id(x) not in seen
                      and difflib.SequenceMatcher(None, x["text"].lower(), b["text"].lower()).ratio() >= SAME_TEXT
                      and abs(x["box"][1] - b["box"][1]) < 0.08), None)
            if m is None:
                m = {"text": b["text"], "start": s["t"], "box": b["box"], "line_h": b["line_h"], "frame": s["i"]}
                live.append(m)
            elif len(b["text"]) > len(m["text"]):
                m.update(text=b["text"], box=b["box"])   # the fullest read wins (a line typed on reads short first)
            m["end"] = round(s["t"] + 1 / OCR_FPS, 3)
            seen.add(id(m))
        for x in [x for x in live if id(x) not in seen]:
            live.remove(x)
            done.append(x)
    done += live
    edges = [0.0] + cuts + [dur]
    snap = lambda t: min(edges, key=lambda e: abs(e - t)) if min(abs(e - t) for e in edges) <= SNAP_S else t   # noqa: E731
    out = []
    for x in sorted(done, key=lambda x: x["start"]):
        fill, back = colours(frames[x["frame"]], x["box"])
        out.append({"text": x["text"], "start": round(snap(x["start"]), 3), "end": round(min(dur, snap(x["end"])), 3),
                    "box": [round(v * 100, 2) for v in x["box"]], "size_pct": round(x["line_h"] * 100 / 1.15, 2),
                    "color": fill, "box_color": back})
    return [x for x in out if x["end"] - x["start"] >= 0.2]


def caption(x):
    return x["size_pct"] >= MIN_SIZE and x["end"] - x["start"] >= MIN_HOLD and abs(x["box"][0] + x["box"][2] / 2 - 50) <= MAX_OFF_CENTRE


def read(edit, src, ocr=None, cuts=None):
    edit, src = Path(edit), Path(src)
    out = edit / "reel"
    out.mkdir(parents=True, exist_ok=True)
    w, h, dur = probe(src)
    ff("-i", src, "-vn", "-c:a", "aac", "-b:a", "192k", out / "audio.m4a")
    sys.path.insert(0, str(TEARDOWN))
    import look   # noqa: E402  (venv: numpy, pillow, ocrmac / rapidocr)
    if cuts is None:
        import visual   # noqa: E402
        cuts = visual.measure_video(src, out)["cuts"]
    if ocr is None:
        engine, ocr = look.ocr_engine()
        if not ocr:
            raise SystemExit("No OCR engine: run the setup skill (it installs ocrmac on a Mac, rapidocr elsewhere).")
    aw = min(look.WORK_W, w) // 2 * 2
    ah = round(aw * h / w / 2) * 2
    samples, frames = [], []
    for i, f in enumerate(look.decode(src, aw, ah, OCR_FPS)):
        lines = [{"text": t, "box": b} for t, b in ocr(f, i / OCR_FPS) if t.strip()]
        samples.append({"i": i, "t": round(i / OCR_FPS, 3), "blocks": blocks(lines)})
        frames.append(f)
    edges = [0.0] + list(cuts) + [dur]
    shots = [{"n": i + 1, "start": round(a, 3), "end": round(b, 3)} for i, (a, b) in enumerate(zip(edges, edges[1:])) if b - a > 0.05]
    found = track(samples, frames, list(cuts), dur)
    (out / "ocr.json").write_text(json.dumps(found, indent=1), encoding="utf-8")   # everything read, for a caption it missed
    data = {"source": str(src), "duration": round(dur, 3), "width": w, "height": h, "shots": shots,
            "texts": [x for x in found if caption(x)]}
    (edit / "reel.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    for s in shots:   # each shot full size: Claude reads the real words here and fixes OCR slips in reel.json
        ff("-ss", (s["start"] + s["end"]) / 2, "-i", src, "-frames:v", "1", "-vf", "scale=540:-2", out / f"shot-{s['n']:02d}.jpg")
    # one frame from the middle of each shot, numbered left to right: what Claude matches b-roll against
    with tempfile.TemporaryDirectory() as tmp:
        for s in shots:
            ff("-ss", (s["start"] + s["end"]) / 2, "-i", src, "-frames:v", "1", "-vf",
               "scale=240:426:force_original_aspect_ratio=decrease,pad=240:426:(ow-iw)/2:(oh-ih)/2", f"{tmp}/s{s['n']:03d}.png")
        cols = min(6, len(shots))
        ff("-i", f"{tmp}/s%03d.png", "-vf", f"tile={cols}x{-(-len(shots) // cols)}", "-frames:v", "1", out / "shots.jpg")
    return data


def build(edit):
    edit = Path(edit)
    reel = json.loads((edit / "reel.json").read_text(encoding="utf-8"))
    picks = json.loads((edit / "picks.json").read_text(encoding="utf-8"))["shots"]
    if len(picks) != len(reel["shots"]):
        raise SystemExit(f"picks.json has {len(picks)} shots, the reel has {len(reel['shots'])}: one pick per shot.")
    gone = [p["clip"] for p in picks if not Path(p["clip"]).is_file()]
    if gone:   # an online-only Drive file is a file here; one moved or deleted is not
        raise SystemExit("These picks are not on this computer: " + ", ".join(gone))
    fill = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for s, p in zip(reel["shots"], picks):
            d = round(s["end"] - s["start"], 3)
            part = Path(tmp, f"p{s['n']:03d}.mp4")
            ff("-stream_loop", "-1", "-ss", p.get("from", 0), "-i", p["clip"], "-t", d, "-vf", fill, "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p", part)
            parts.append(part)
        lst = Path(tmp, "list.txt")
        lst.write_text("".join(f"file '{x}'\n" for x in parts), encoding="utf-8")
        ff("-f", "concat", "-safe", "0", "-i", lst, "-i", edit / "reel" / "audio.m4a", "-map", "0:v", "-map", "1:a",
           "-c:v", "copy", "-c:a", "aac", "-t", reel["duration"], edit / "base.mp4")
    texts = [{"kind": "onscreen", "text": t["text"], "start": t["start"], "end": t["end"], "box": t["box"],
              "size_pct": t["size_pct"], "color": t["color"], "box_color": t.get("box_color")} for t in reel["texts"]]
    plan = {"video": "base.mp4", "width": W, "height": H, "fps": FPS, "durationInFrames": round(reel["duration"] * FPS),
            "captions": {"style": {"on": False}, "chunks": []}, "zooms": [], "cards": [], "texts": texts, "sfx": []}
    (edit / "plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    return plan


def demo():
    import numpy as np
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        # a 3 s "reel": two shots (red, then blue at 1.5 s) with a tone, and two clips of b-roll
        box = "enable='between(t,0.4,2.6)'"   # white words on a black box in the top third, 0.4-2.6 s
        ff("-f", "lavfi", "-i", "color=red:s=360x640:d=1.5:r=30", "-f", "lavfi", "-i", "color=blue:s=360x640:d=1.5:r=30",
           "-f", "lavfi", "-i", "sine=f=440:d=3", "-filter_complex",
           f"[0:v][1:v]concat=n=2:v=1,drawbox=x=30:y=180:w=300:h=62:c=black:t=fill:{box},"
           f"drawbox=x=60:y=198:w=200:h=8:c=white:t=fill:{box},drawbox=x=120:y=220:w=120:h=8:c=white:t=fill:{box}[v]",
           "-map", "[v]", "-map", "2:a",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", t / "reel.mp4")
        for c in ("green", "yellow"):
            ff("-f", "lavfi", "-i", f"testsrc=s=640x360:d=1:r=30,hue=s=0,drawbox=c={c}:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p", t / f"{c}.mp4")

        def fake_ocr(im, ts):   # the two lines while the box is up; a watermark throughout
            out = [("TikTok @someone", [0.05, 0.9, 0.4, 0.03])]
            if 0.4 <= ts < 2.6:
                out += [("this is the hook", [0.15, 0.30, 0.6, 0.025]), ("line two", [0.32, 0.335, 0.36, 0.025]),
                        ("Q", [0.1, 0.8, 0.02, 0.01])]   # a keyboard key in the footage: small, kept out
            return out
        d = read(t / "e", t / "reel.mp4", ocr=fake_ocr, cuts=[1.5])
        assert [(s["start"], s["end"]) for s in d["shots"]] == [(0.0, 1.5), (1.5, 3.0)], d["shots"]
        assert len(d["texts"]) == 1, d["texts"]
        x = d["texts"][0]
        assert x["text"] == "this is the hook\nline two" and x["start"] == 0.667 and x["end"] == 3.0, x   # its end snapped onto the reel's end
        assert x["color"].startswith("#F") and x["box_color"] == "#000000", x
        assert (t / "e" / "reel" / "audio.m4a").is_file() and (t / "e" / "reel" / "shots.jpg").is_file()
        assert (t / "e" / "reel" / "shot-02.jpg").is_file() and any(o["text"] == "Q" for o in json.loads((t / "e" / "reel" / "ocr.json").read_text(encoding="utf-8")))
        (t / "e" / "picks.json").write_text(json.dumps({"shots": [{"clip": str(t / "green.mp4")}, {"clip": str(t / "yellow.mp4"), "from": 0.2}]}), encoding="utf-8")
        plan = build(t / "e")
        bw, bh, bd = probe(t / "e" / "base.mp4")
        assert (bw, bh) == (W, H) and abs(bd - 3.0) < 0.1, (bw, bh, bd)
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                            str(t / "e" / "base.mp4")], capture_output=True, text=True)
        assert r.stdout.strip() == "aac", "the reel's sound is on base.mp4"
        assert plan["durationInFrames"] == 90 and plan["texts"][0]["kind"] == "onscreen" and plan["captions"]["chunks"] == []
        (t / "e" / "picks.json").write_text(json.dumps({"shots": [{"clip": str(t / "green.mp4")}]}), encoding="utf-8")
        try:
            build(t / "e")
            raise AssertionError("a short picks.json was built")
        except SystemExit as e:
            assert "one pick per shot" in str(e)
        assert np  # the venv is there
    print("reel demo ok")


def main():
    a = sys.argv[1:]
    if a[:1] == ["read"] and len(a) == 3:
        d = read(a[1], a[2])
        print(f"{len(d['shots'])} shots, {len(d['texts'])} texts, {d['duration']} s -> {Path(a[1]) / 'reel.json'}")
        print(f"shots sheet: {Path(a[1]) / 'reel' / 'shots.jpg'}")
    elif a[:1] == ["build"] and len(a) == 2:
        p = build(a[1])
        print(f"base.mp4 + plan.json ({len(p['texts'])} texts, {p['durationInFrames']} frames)")
    elif a[:1] == ["demo"]:
        demo()
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
