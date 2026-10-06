#!/usr/bin/env python3
"""Export an edit to another editor, so the user can keep working on it by hand.

    python3 export_nle.py edits/NAME --to fcpxml|premiere|resolve|capcut|edl|srt|all [--plan plan.json]
                          [--source RAW.MOV] [--no-render]
    python3 export_nle.py demo        self-check, offline

--to takes one or a comma list. Writes edits/NAME/export/:
  NAME.srt        the captions (always)
  NAME.fcpxml     FCPXML 1.10: Final Cut Pro 10.6+ and DaVinci Resolve 18+ (File > Import > Timeline)
  NAME.xml        FCP7 XML (xmeml 4): Premiere Pro (File > Import); Resolve reads it too
  NAME.edl        CMX3600, the cut only (one video track, no cards, no captions)
  CAPCUT.md       CapCut has no timeline import: the steps, every card's time and place
  media/          card-NN.png (a plain capture fitted to its box), card-NN.mov (a card that moves:
                  rendered by the plugin's Remotion on a transparent ground, cropped to its box,
                  ProRes 4444 with alpha), sfx-NN.wav (sound cues, level baked in)

What the timelines hold, all on cut.mp4's clock:
  - the jump cut as trims of the ORIGINAL raw take (report.json "source", or --source), so every
    cut can be re-opened in the editor. Source timecode is honoured when the take has one.
  - captions: titles in FCPXML (font, size, colour, place from plan.json), the .srt everywhere
  - each card on its own track at its time and place, drawn at 100% (the file is already box-sized)
  - sound cues on their own audio track
  - a marker per beat (beats.json sentences; the cards' trigger words when there is no beats.json)
Not exported: zooms, the split layout's sliding window and ground, a plain capture's entrance
(the .png is static). A card whose anim type the renderer no longer draws is left out, with a note.

Positions: FCPXML adjust-transform position is in % of the frame height, y up (Apple's convention,
the DTD only names the attribute). xmeml Basic Motion center is the offset as a fraction of the
frame, y down. Neither was import-tested on a machine with the app (see the skill's render.md).
Needs ffmpeg/ffprobe (card media and probing). Exit codes: 0 ok, 1 error, 2 usage
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

FORMATS = ("fcpxml", "premiere", "resolve", "capcut", "edl", "srt")
TITLE_UID = ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
LEAD_S, TAIL_S = 0.3, 0.4   # an animated card is rendered from a little before to a little after its slot


# ---------- timing ----------

def frame_rate(fps):
    """(num, den) frames per second: 29.97 -> (30000, 1001), 30 -> (30, 1)."""
    n = round(fps)
    if abs(fps - n * 1000 / 1001) < 0.005 and abs(fps - n) > 0.005:
        return n * 1000, 1001
    return Fraction(fps).limit_denominator(1001).numerator, Fraction(fps).limit_denominator(1001).denominator


def rt(frames, rate):
    """FCPXML rational time for a frame count."""
    num, den = rate
    return f"{frames * den}/{num}s" if frames else "0s"


def tc(frames, timebase):
    s, f = divmod(int(frames), timebase)
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


def segments(spans_f):
    """[(timeline_start, source_start, length)] in frames, from kept [start, end) source frames."""
    out, t = [], 0
    for s, e in spans_f:
        out.append((t, s, e - s))
        t += e - s
    return out


def seg_at(segs, f):
    """Index of the segment holding timeline frame f (the last one past the end)."""
    for i, (t, _, n) in enumerate(segs):
        if f < t + n:
            return i
    return len(segs) - 1


def lanes(items):
    """Greedy lane per item (1-based) so items in one lane never overlap. Items need start_f, len_f."""
    ends = []
    for it in sorted(items, key=lambda x: x["start_f"]):
        k = next((i for i, e in enumerate(ends) if e <= it["start_f"]), None)
        if k is None:
            ends.append(0)
            k = len(ends) - 1
        ends[k] = it["start_f"] + it["len_f"]
        it["lane"] = k + 1
    return len(ends)


def box_px(box, w, h):
    x, y, bw, bh = box
    return [round(x / 100 * w), round(y / 100 * h), round(bw / 100 * w), round(bh / 100 * h)]


def fit(size, rect):
    """An image of size [iw, ih] contained in rect [x, y, w, h], centred: its rect in px, even sides."""
    iw, ih = size
    x, y, w, h = rect
    s = min(w / iw, h / ih)
    fw, fh = max(2, round(iw * s / 2) * 2), max(2, round(ih * s / 2) * 2)
    return [round(x + (w - fw) / 2), round(y + (h - fh) / 2), fw, fh]


# ---------- reading the edit ----------

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:format_tags=timecode:stream=codec_type,width,height,r_frame_rate,"
                        "sample_rate,channels:stream_tags=timecode", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ERROR: ffprobe could not read {path}: {r.stderr.strip()}")
    j = json.loads(r.stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), {})
    tcode = (j["format"].get("tags") or {}).get("timecode") or next(
        ((s.get("tags") or {}).get("timecode") for s in j["streams"] if (s.get("tags") or {}).get("timecode")), None)
    return {"duration": float(j["format"].get("duration", 0)), "width": v.get("width"), "height": v.get("height"),
            "fps": float(Fraction(v["r_frame_rate"])) if v.get("r_frame_rate") else None,
            "channels": a.get("channels"), "rate": int(a["sample_rate"]) if a.get("sample_rate") else None,
            "timecode": tcode}


def tc_frames(tcode, timebase):
    if not tcode:
        return 0
    h, m, s, f = map(int, re.split(r"[:;.]", tcode))
    return ((h * 60 + m) * 60 + s) * timebase + f   # ponytail: drop-frame timecode read as non-drop


def load_edit(edit, plan_name, source):
    report = edit / "report.json"
    if not report.exists():
        sys.exit(f"ERROR: no {report}. Run the cut skill first: the export trims the raw take with its spans.")
    rep = json.loads(report.read_text())
    plan_path = edit / plan_name
    if not plan_path.exists():
        sys.exit(f"ERROR: no {plan_path}. Run plan.py first.")
    plan = json.loads(plan_path.read_text())
    src = Path(source or rep["source"]).expanduser()
    if not src.exists():
        sys.exit(f"ERROR: the raw take {src} is gone. Pass --source <the same file> (it must be the take the cut was made from).")
    meta = probe(src)
    if abs(meta["duration"] - rep["duration"]) > 0.1:
        sys.exit(f"ERROR: {src} is {meta['duration']:.2f} s, the cut was made from a {rep['duration']:.2f} s take. Wrong file?")
    beats = edit / "beats.json"
    return {"name": edit.name, "edit": edit.resolve(), "plan": plan, "plan_path": plan_path, "fps": rep["fps"], "frames": rep["frames"],
            "source": src.resolve(), "meta": meta, "beats": json.loads(beats.read_text()) if beats.exists() else None}


def ctx_timing(ctx):
    rate = frame_rate(ctx["fps"])
    tb = round(ctx["fps"])
    ctx.update(rate=rate, timebase=tb, ntsc=rate[1] == 1001, tc0=tc_frames(ctx["meta"].get("timecode"), tb),
               segs=segments(ctx["frames"]))
    ctx["total_f"] = sum(n for _, _, n in ctx["segs"])
    ctx["f"] = lambda t: max(0, min(ctx["total_f"], round(t * ctx["fps"])))
    return ctx


def markers(ctx):
    if ctx["beats"]:
        return [{"start_f": ctx["f"](b["start"]), "text": b["text"]} for b in ctx["beats"]]
    return [{"start_f": ctx["f"](c["start"]), "text": c.get("trigger_word", "card")} for c in ctx["plan"]["cards"]]


def captions(ctx):
    return [{"start_f": ctx["f"](c["start"]), "len_f": max(1, ctx["f"](c["end"]) - ctx["f"](c["start"])), "text": c["text"]}
            for c in ctx["plan"]["captions"]["chunks"]]


# ---------- media ----------

def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *map(str, args)], check=True)


def render_cards(ctx, todo, media):
    """Moving cards through the plugin's renderer, on a transparent ground: the Preview composition
    draws one card, render.mjs stills writes every frame as a PNG with alpha, ffmpeg crops them to the
    card's box into a ProRes 4444 .mov (alpha kept). One bundle for all cards."""
    sys.path.insert(0, str(Path(__file__).parent))
    import edit as E   # the renderer helpers style-edit already uses
    E.sync_renderer()
    pub = E.prepare_public(ctx["edit"], ctx["plan"], "-export")
    bundle = ctx["edit"] / ".render-export-bundle"
    E.node("bundle", pub, bundle)
    plan, fps = ctx["plan"], ctx["plan"]["fps"]
    try:
        for it in todo:
            c, out = it["card"], media / f"card-{it['i']:02d}.mov"
            t0 = it["start_f"] / fps   # the clip starts here; the card's own times shift with it
            props = {"composition": "Preview", "width": plan["width"], "height": plan["height"],
                     "dur": it["len_f"] / fps, "bg": "transparent", "light": bool(plan.get("layout")),
                     "look": plan.get("look"), "motion": plan.get("motion"),
                     "card": {**c, "start": round(c["start"] - t0, 4), "end": round(c["end"] - t0, 4)}}
            frames = media / f".card-{it['i']:02d}"
            shutil.rmtree(frames, ignore_errors=True)
            pp = media / f".card-{it['i']:02d}.json"
            pp.write_text(json.dumps(props))
            E.node("stills", bundle, pp, frames, *(f"f{k:05d}={k}" for k in range(it["len_f"])))
            x, y, w, h = it["rect"]
            ffmpeg("-framerate", fps, "-i", frames / "f%05d.png", "-vf", f"crop={w}:{h}:{x}:{y}",
                   "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", out)
            shutil.rmtree(frames)
            pp.unlink()
            it["path"] = out
            if empty(out):
                it["kind"], it["why"] = "missing", "draws nothing in this version of the renderer"
    finally:
        shutil.rmtree(bundle, ignore_errors=True)


def empty(mov):
    """True when every frame's alpha is 0: the renderer skipped the card (a removed anim type)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mov), "-vf", "alphaextract,signalstats,"
                        "metadata=print:key=lavfi.signalstats.YMAX:file=-", "-f", "null", "-"],
                       capture_output=True, text=True)
    vals = [float(v) for v in re.findall(r"YMAX=([\d.]+)", r.stdout)]
    return bool(vals) and max(vals) == 0


def card_items(ctx, media, render):
    """One overlay per card: {i, kind image|video|missing, path, start_f, len_f, rect [x, y, w, h] px}.
    A plain capture is its PNG fitted to the box. Anything that moves (an anim, a Lottie, a capture
    with marks or a highlight) is rendered."""
    plan, edit = ctx["plan"], ctx["edit"]
    W, H, fps = plan["width"], plan["height"], plan["fps"]
    items, todo = [], []
    for i, c in enumerate(plan["cards"], 1):
        box = box_px(c.get("box") or [0, 0, 100, 100], W, H)
        if c.get("layout") == "scene":
            box = [0, 0, W, H]
        name = c.get("trigger_word") or (c.get("anim") or {}).get("type") or "card"
        still = c.get("src") and not c["src"].endswith(".json") and not c.get("marks") and not c.get("highlight")
        if still:
            src = edit / c["src"]
            size = c.get("size") or [probe(src)["width"], probe(src)["height"]]
            rect = fit(size, box)
            out = media / f"card-{i:02d}.png"
            if src.suffix.lower() == ".svg":
                shutil.copy2(src, out.with_suffix(".svg"))   # ffmpeg reads no SVG; the editor scales it
                out = out.with_suffix(".svg")
            else:
                ffmpeg("-i", src, "-vf", f"scale={rect[2]}:{rect[3]}:flags=lanczos", out)
            f0, f1 = ctx["f"](c["start"]), ctx["f"](c["end"])
            items.append({"i": i, "kind": "image", "path": out, "start_f": f0, "len_f": max(1, f1 - f0),
                          "rect": rect, "name": name})
            continue
        a = max(0, round((c["start"] - LEAD_S) * fps))
        b = min(plan["durationInFrames"], round((c["end"] + TAIL_S) * fps))
        box[2], box[3] = box[2] // 2 * 2, box[3] // 2 * 2
        it = {"i": i, "kind": "video", "card": c, "start_f": a, "len_f": b - a, "rect": box, "name": name}
        items.append(it)
        done = media / f"card-{i:02d}.mov"
        if done.exists() and done.stat().st_mtime > ctx["plan_path"].stat().st_mtime:
            it["path"] = done
            if empty(done):
                it["kind"], it["why"] = "missing", "draws nothing in this version of the renderer"
        elif render:
            todo.append(it)
        else:
            it["kind"], it["why"] = "missing", "not rendered (--no-render)"
    if todo:
        render_cards(ctx, todo, media)
    for it in items:
        it.pop("card", None)
        if it["kind"] == "missing":
            it.pop("path", None)
    return items


def sfx_items(ctx, media):
    out = []
    for i, s in enumerate(ctx["plan"].get("sfx") or [], 1):
        src = ctx["edit"] / s["src"]
        dst = media / f"sfx-{i:02d}{src.suffix}"
        shutil.copy2(src, dst)
        m = probe(dst)
        f0 = ctx["f"](s["t"])
        out.append({"path": dst, "start_f": f0, "len_f": max(1, round(m["duration"] * ctx["fps"])),
                    "channels": m["channels"] or 2, "rate": m["rate"] or 48000})
    return out


# ---------- writers ----------

def srt(caps, fps):
    def ts(f):
        ms = round(f / fps * 1000)
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{n}\n{ts(c['start_f'])} --> {ts(c['start_f'] + c['len_f'])}\n{c['text']}\n"
                     for n, c in enumerate(caps, 1))


def url(p):
    return "file://" + quote(Path(p).resolve().as_posix() if Path(p).is_absolute() or Path(p).exists() else str(p))


def color(hexstr, alpha=1):
    h = (hexstr or "#FFFFFF").lstrip("#")
    r, g, b = (int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))
    return f"{r:.4g} {g:.4g} {b:.4g} {alpha}"


def fcp_pos(rect, W, H):
    """Centre of a px rect as FCPXML position: offset from frame centre in % of frame height, y up."""
    x, y, w, h = rect
    return f"{(x + w / 2 - W / 2) / H * 100:.4f} {(H / 2 - (y + h / 2)) / H * 100:.4f}"


def fcpxml(ctx, cards, sfx, caps, marks):
    plan, meta, rate = ctx["plan"], ctx["meta"], ctx["rate"]
    W, H = plan["width"], plan["height"]
    T = lambda f: rt(f, rate)
    root = ET.Element("fcpxml", version="1.10")
    res = ET.SubElement(root, "resources")
    ET.SubElement(res, "format", id="r1", name=f"FFVideoFormat{W}x{H}p{ctx['timebase']}",
                  frameDuration=T(1), width=str(W), height=str(H))
    ET.SubElement(res, "format", id="r2", frameDuration=T(1), width=str(meta["width"]), height=str(meta["height"]))
    src_len = round(meta["duration"] * ctx["fps"])
    a = ET.SubElement(res, "asset", id="r3", name=ctx["source"].stem, start=T(ctx["tc0"]), duration=T(src_len),
                      hasVideo="1", format="r2", hasAudio="1" if meta["channels"] else "0", videoSources="1",
                      audioSources="1", audioChannels=str(meta["channels"] or 2), audioRate=str(meta["rate"] or 48000))
    ET.SubElement(a, "media-rep", kind="original-media", src=url(ctx["source"]))
    ET.SubElement(res, "effect", id="r4", name="Basic Title", uid=TITLE_UID)
    n = 5
    for it in cards + sfx:
        if not it.get("path"):
            continue
        rid = f"r{n}"
        n += 1
        kw = {"id": rid, "name": Path(it["path"]).stem, "start": "0s"}
        if it in sfx:
            kw.update(duration=T(it["len_f"]), hasAudio="1", audioSources="1", audioChannels=str(it["channels"]),
                      audioRate=str(it["rate"]))
        elif it["kind"] == "image":
            fid = f"r{n}"
            n += 1
            ET.SubElement(res, "format", id=fid, name="FFVideoFormatRateUndefined",
                          width=str(it["rect"][2]), height=str(it["rect"][3]))
            kw.update(duration="0s", hasVideo="1", format=fid, videoSources="1")
        else:
            fid = f"r{n}"
            n += 1
            ET.SubElement(res, "format", id=fid, frameDuration=T(1), width=str(it["rect"][2]), height=str(it["rect"][3]))
            kw.update(duration=T(it["len_f"]), hasVideo="1", format=fid, videoSources="1")
        ET.SubElement(ET.SubElement(res, "asset", **kw), "media-rep", kind="original-media", src=url(it["path"]))
        it["rid"] = rid

    lib = ET.SubElement(root, "library")
    ev = ET.SubElement(lib, "event", name=f"AI editor {ctx['name']}")
    pj = ET.SubElement(ev, "project", name=ctx["name"])
    seq = ET.SubElement(pj, "sequence", format="r1", duration=T(ctx["total_f"]), tcStart="0s", tcFormat="NDF",
                        audioLayout="stereo", audioRate="48k")
    spine = ET.SubElement(seq, "spine")
    clips = []
    for k, (t, s, ln) in enumerate(ctx["segs"]):
        clips.append(ET.SubElement(spine, "asset-clip", ref="r3", name=f"{ctx['source'].stem} {k + 1}", offset=T(t),
                                   start=T(ctx["tc0"] + s), duration=T(ln), format="r2", tcFormat="NDF"))
    anchored = {k: [] for k in range(len(clips))}
    marked = {k: [] for k in range(len(clips))}

    def local(f):
        k = seg_at(ctx["segs"], f)
        t, s, _ = ctx["segs"][k]
        return k, ctx["tc0"] + s + (f - t)

    top = lanes([c for c in cards if c.get("rid")])
    for it in cards:
        if not it.get("rid"):
            continue
        k, off = local(it["start_f"])
        tag = "video" if it["kind"] == "image" else "asset-clip"
        e = ET.Element(tag, ref=it["rid"], lane=str(it["lane"]), offset=T(off), name=it["name"],
                       start="0s", duration=T(it["len_f"]))
        ET.SubElement(e, "adjust-conform", type="none")   # the file is already box-sized: draw it 1:1
        ET.SubElement(e, "adjust-transform", position=fcp_pos(it["rect"], W, H))
        anchored[k].append(e)
    st = plan["captions"].get("style") or {}
    size = round((st.get("size_pct") or 6) / 100 * max(W, H))
    y = (50 - (st.get("y_pct") or 70)) / 100 * 100   # % of frame height, y up
    for j, c in enumerate(caps, 1):
        k, off = local(c["start_f"])
        e = ET.Element("title", ref="r4", lane=str(top + 1), offset=T(off), name=c["text"][:40],
                       start="0s", duration=T(c["len_f"]))
        txt = ET.SubElement(e, "text")
        ET.SubElement(txt, "text-style", ref=f"ts{j}").text = c["text"]
        d = ET.SubElement(e, "text-style-def", id=f"ts{j}")
        ET.SubElement(d, "text-style", font=st.get("font_match") or "Helvetica", fontSize=str(size),
                      fontColor=color(st.get("color")), bold="1" if (st.get("weight") or 700) >= 600 else "0",
                      alignment="center", **({"strokeColor": "0 0 0 1", "strokeWidth": str(round(size / 12))}
                                             if st.get("stroke") else {}))
        ET.SubElement(e, "adjust-transform", position=f"0 {y:.4f}")
        anchored[k].append(e)
    tmp = [dict(s) for s in sfx]   # audio lanes count down from -1
    lanes(tmp)
    for s, t in zip(sfx, tmp):
        k, off = local(s["start_f"])
        anchored[k].append(ET.Element("asset-clip", ref=s["rid"], lane=str(-t["lane"]), offset=T(off),
                                      name=Path(s["path"]).stem, start="0s", duration=T(s["len_f"])))
    for m in marks:
        k, off = local(m["start_f"])
        marked[k].append(ET.Element("marker", start=T(off), duration=T(1), value=m["text"][:120]))
    for k, clip in enumerate(clips):   # DTD order inside a clip: anchored items, then markers
        clip.extend(anchored[k] + marked[k])
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + ET.tostring(root, encoding="unicode") + "\n"


def xmeml(ctx, cards, sfx, marks):
    """FCP7 XML for Premiere: cut on V1/A1, cards on V2.., sound cues on A2.., sequence markers."""
    plan, meta = ctx["plan"], ctx["meta"]
    W, H, tb = plan["width"], plan["height"], ctx["timebase"]
    ntsc = "TRUE" if ctx["ntsc"] else "FALSE"

    def rate(parent):
        r = ET.SubElement(parent, "rate")
        ET.SubElement(r, "timebase").text = str(tb)
        ET.SubElement(r, "ntsc").text = ntsc

    def sub(parent, tag, text):
        ET.SubElement(parent, tag).text = str(text)

    files = {}

    def file_el(parent, path, frames, video=True, audio=0, size=None):
        key = str(path)
        if key in files:
            ET.SubElement(parent, "file", id=files[key])
            return
        files[key] = f"file-{len(files) + 1}"
        f = ET.SubElement(parent, "file", id=files[key])
        sub(f, "name", Path(path).name)
        sub(f, "pathurl", url(path))
        rate(f)
        sub(f, "duration", frames)
        md = ET.SubElement(f, "media")
        if video:
            sc = ET.SubElement(ET.SubElement(md, "video"), "samplecharacteristics")
            sub(sc, "width", size[0])
            sub(sc, "height", size[1])
        if audio:
            au = ET.SubElement(md, "audio")
            sub(au, "channelcount", audio)

    def clip(track, cid, name, start, length, src_in, path, frames, **kw):
        c = ET.SubElement(track, "clipitem", id=cid)
        sub(c, "name", name)
        sub(c, "enabled", "TRUE")
        sub(c, "duration", frames)
        rate(c)
        sub(c, "start", start)
        sub(c, "end", start + length)
        sub(c, "in", src_in)
        sub(c, "out", src_in + length)
        file_el(c, path, frames, **kw)
        return c

    root = ET.Element("xmeml", version="4")
    seq = ET.SubElement(root, "sequence", id="sequence-1")
    sub(seq, "name", ctx["name"])
    sub(seq, "duration", ctx["total_f"])
    rate(seq)
    media = ET.SubElement(seq, "media")
    vid = ET.SubElement(media, "video")
    sc = ET.SubElement(ET.SubElement(vid, "format"), "samplecharacteristics")
    rate(sc)
    sub(sc, "width", W)
    sub(sc, "height", H)
    sub(sc, "pixelaspectratio", "square")
    aud = ET.SubElement(media, "audio")
    src_len = round(meta["duration"] * ctx["fps"])
    v1, a1 = ET.SubElement(vid, "track"), ET.SubElement(aud, "track")
    for k, (t, s, ln) in enumerate(ctx["segs"]):
        v = clip(v1, f"v-{k + 1}", ctx["source"].name, t, ln, s, ctx["source"], src_len,
                 size=(meta["width"], meta["height"]), audio=meta["channels"] or 0)
        a = clip(a1, f"a-{k + 1}", ctx["source"].name, t, ln, s, ctx["source"], src_len,
                 size=(meta["width"], meta["height"]), audio=meta["channels"] or 0)
        ET.SubElement(a, "sourcetrack").extend([_t("mediatype", "audio"), _t("trackindex", "1")])
        for c, mt, ti in ((v, "video", 1), (a, "audio", 1)):
            for other_id, omt in ((f"v-{k + 1}", "video"), (f"a-{k + 1}", "audio")):
                lk = ET.SubElement(c, "link")
                sub(lk, "linkclipref", other_id)
                sub(lk, "mediatype", omt)
                sub(lk, "trackindex", 1)
                sub(lk, "clipindex", k + 1)
    real = [c for c in cards if c.get("path") and Path(c["path"]).suffix != ".svg"]
    tracks = {}
    for it in sorted(real, key=lambda x: x["lane"]):
        if it["lane"] not in tracks:
            tracks[it["lane"]] = ET.SubElement(vid, "track")
        tr = tracks[it["lane"]]
        frames = it["len_f"]
        c = clip(tr, f"card-{it['i']}", it["name"], it["start_f"], frames, 0, it["path"], frames,
                 size=it["rect"][2:])
        x, y, w, h = it["rect"]
        flt = ET.SubElement(ET.SubElement(c, "filter"), "effect")
        for tag, text in (("name", "Basic Motion"), ("effectid", "basic"), ("effectcategory", "motion"),
                          ("effecttype", "motion"), ("mediatype", "video")):
            sub(flt, tag, text)
        p = ET.SubElement(flt, "parameter")
        sub(p, "parameterid", "scale")
        sub(p, "name", "Scale")
        sub(p, "value", 100)
        p = ET.SubElement(flt, "parameter")
        sub(p, "parameterid", "center")
        sub(p, "name", "Center")
        v = ET.SubElement(p, "value")
        sub(v, "horiz", f"{(x + w / 2 - W / 2) / W:.5f}")
        sub(v, "vert", f"{(y + h / 2 - H / 2) / H:.5f}")
    tmp = [dict(s) for s in sfx]
    lanes(tmp)
    atracks = {}
    for s, t in zip(sfx, tmp):
        if t["lane"] not in atracks:
            atracks[t["lane"]] = ET.SubElement(aud, "track")
        tr = atracks[t["lane"]]
        clip(tr, f"sfx-{len(atracks)}-{s['start_f']}", Path(s["path"]).name, s["start_f"], s["len_f"], 0,
             s["path"], s["len_f"], video=False, audio=s["channels"])
    for m in marks:
        mk = ET.SubElement(seq, "marker")
        sub(mk, "name", m["text"][:60])
        sub(mk, "comment", m["text"])
        sub(mk, "in", m["start_f"])
        sub(mk, "out", -1)
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _t(tag, text):
    e = ET.Element(tag)
    e.text = text
    return e


def edl(ctx):
    tb, reel = ctx["timebase"], "AX"
    lines = [f"TITLE: {ctx['name']}", "FCM: NON-DROP FRAME", ""]
    for k, (t, s, ln) in enumerate(ctx["segs"], 1):
        s += ctx["tc0"]
        lines += [f"{k:03d}  {reel:<8} V     C        {tc(s, tb)} {tc(s + ln, tb)} {tc(t, tb)} {tc(t + ln, tb)}",
                  f"* FROM CLIP NAME: {ctx['source'].name}", ""]
    return "\n".join(lines)


def capcut(ctx, cards, sfx):
    W, H = ctx["plan"]["width"], ctx["plan"]["height"]
    secs = lambda f: f"{f / ctx['fps']:.2f}"
    rows = [f"| {c['i']} | {Path(c['path']).name if c.get('path') else '(not rendered)'} | {secs(c['start_f'])} | "
            f"{secs(c['start_f'] + c['len_f'])} | {(c['rect'][0] + c['rect'][2] / 2) / W * 100:.0f}% "
            f"{(c['rect'][1] + c['rect'][3] / 2) / H * 100:.0f}% | {c['rect'][2] / W * 100:.0f}% |" for c in cards]
    srows = [f"| {Path(s['path']).name} | {secs(s['start_f'])} |" for s in sfx]
    return "\n".join([
        f"# {ctx['name']} in CapCut", "",
        "CapCut has no timeline import. Its project files are undocumented and change between versions, "
        "so this export does not write one. Rebuild it by hand in about ten minutes:", "",
        f"1. New project, {W}x{H}. Import `{ctx['edit'] / 'cut.mp4'}` (the jump cut, already trimmed) and the "
        "`media/` folder, and drop the cut on the main track.",
        f"2. Captions > Add captions > pick `{ctx['name']}.srt`. Style them once; CapCut applies it to all.",
        "3. Each card below on its own overlay track at its start time. Set its position (centre, % of the "
        "frame from the top-left) and width in the Video > Basic panel.",
        "4. Each sound cue on an audio track at its time. Their level is already set.", "",
        "| card | file | start s | end s | centre x y | width |", "|---|---|---|---|---|---|", *rows, "",
        "| sound | start s |", "|---|---|", *srows, ""])


def export(ctx, out, todo, render):
    out.mkdir(parents=True, exist_ok=True)
    media = out / "media"
    media.mkdir(exist_ok=True)
    caps, marks = captions(ctx), markers(ctx)
    written = [out / f"{ctx['name']}.srt"]
    written[0].write_text(srt(caps, ctx["fps"]), encoding="utf-8")
    needs_media = bool(todo - {"srt", "edl"})
    cards = card_items(ctx, media, render) if needs_media else []
    sfx = sfx_items(ctx, media) if needs_media else []
    lanes([c for c in cards if c.get("path")])
    if todo & {"fcpxml", "resolve"}:
        written.append(out / f"{ctx['name']}.fcpxml")
        written[-1].write_text(fcpxml(ctx, cards, sfx, caps, marks), encoding="utf-8")
    if todo & {"premiere", "resolve"}:
        written.append(out / f"{ctx['name']}.xml")
        written[-1].write_text(xmeml(ctx, cards, sfx, marks), encoding="utf-8")
    if "edl" in todo:
        written.append(out / f"{ctx['name']}.edl")
        written[-1].write_text(edl(ctx), encoding="utf-8")
    if "capcut" in todo:
        written.append(out / "CAPCUT.md")
        written[-1].write_text(capcut(ctx, cards, sfx), encoding="utf-8")
    missing = [c for c in cards if c["kind"] == "missing"]
    return written, cards, sfx, missing


# ---------- demo ----------

def demo():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "media").mkdir()
        card_png, cue = d / "media" / "card-01.png", d / "media" / "sfx-01.wav"
        card_png.write_bytes(b"png")
        cue.write_bytes(b"wav")
        ctx = ctx_timing({
            "name": "demo", "edit": d, "fps": 30.0, "frames": [[30, 90], [150, 210]],
            "source": Path("/footage/take one.mov"), "beats": [{"start": 0.0, "text": "first beat"}, {"start": 2.5, "text": "second"}],
            "meta": {"duration": 10.0, "width": 1080, "height": 1920, "channels": 1, "rate": 48000, "timecode": "01:00:00:00"},
            "plan": {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 120,
                     "captions": {"style": {"size_pct": 5, "y_pct": 70, "font_match": "Inter", "color": "#FFFFFF", "stroke": True},
                                  "chunks": [{"text": "hello there", "start": 0.0, "end": 1.0}, {"text": "after the cut", "start": 2.2, "end": 3.0}]},
                     "cards": []}})
        assert ctx["segs"] == [(0, 30, 60), (60, 150, 60)] and ctx["total_f"] == 120 and ctx["tc0"] == 108000
        assert frame_rate(29.97) == (30000, 1001) and rt(3, (30000, 1001)) == "3003/30000s" and rt(45, (30, 1)) == "45/30s"
        assert seg_at(ctx["segs"], 59) == 0 and seg_at(ctx["segs"], 60) == 1 and seg_at(ctx["segs"], 999) == 1
        assert fit([200, 100], [0, 0, 100, 100]) == [0, 25, 100, 50]
        cards = [{"i": 1, "kind": "image", "path": card_png, "start_f": 10, "len_f": 80, "rect": [140, 280, 800, 400], "name": "jev"},
                 {"i": 2, "kind": "video", "path": d / "media" / "card-02.mov", "start_f": 70, "len_f": 30,
                  "rect": [0, 0, 1080, 1920], "name": "race"}]
        sfx = [{"path": cue, "start_f": 65, "len_f": 12, "channels": 2, "rate": 48000}]
        caps, marks = captions(ctx), markers(ctx)
        assert lanes(list(cards)) == 2 and cards[1]["lane"] == 2   # they overlap at 70-90
        # SRT on the cut's clock
        s = srt(caps, 30)
        assert "1\n00:00:00,000 --> 00:00:01,000\nhello there" in s and "00:00:02,200 --> 00:00:03,000" in s, s
        # FCPXML: two spine clips trimmed from the RAW take with its timecode, anchored items on the right clip
        x = ET.fromstring(fcpxml(ctx, cards, sfx, caps, marks).split("\n", 2)[2])
        spine = x.find(".//spine")
        clips = spine.findall("asset-clip")
        assert [(c.get("offset"), c.get("start"), c.get("duration")) for c in clips] == \
            [("0s", "108030/30s", "60/30s"), ("60/30s", "108150/30s", "60/30s")], [c.attrib for c in clips]
        src = x.find(".//asset[@id='r3']/media-rep").get("src")
        assert src == "file:///footage/take%20one.mov" and x.find(".//asset[@id='r3']").get("start") == "108000/30s"
        # the race card starts at timeline 70 = inside clip 2, local = tc0 + 150 + 10
        race = clips[1].find("asset-clip[@name='race']")
        assert race.get("offset") == "108160/30s" and race.get("lane") == "2" and race.find("adjust-transform").get("position") == "0.0000 0.0000"
        jev = clips[0].find("video[@name='jev']")
        assert jev.find("adjust-conform").get("type") == "none" and jev.find("adjust-transform").get("position") == "0.0000 25.0000"
        titles = x.findall(".//title")
        assert [t.get("lane") for t in titles] == ["3", "3"] and titles[1].get("offset") == "108156/30s"
        assert titles[0].find("text-style-def/text-style").get("fontSize") == "96" and titles[0].find("adjust-transform").get("position") == "0 -20.0000"
        assert clips[1].find("asset-clip[@lane='-1']") is not None
        kids = [c.tag for c in clips[1]]
        assert kids.index("marker") > max(i for i, t in enumerate(kids) if t != "marker"), kids   # DTD: markers last
        assert clips[1].find("marker").get("start") == "108165/30s"   # "second" at 2.5 s = frame 75
        # xmeml: V1 trims, cards on V2/V3, centre as a fraction of the frame
        m = ET.fromstring(xmeml(ctx, cards, sfx, marks).split("\n", 2)[2])
        tracks = m.findall(".//video/track")
        assert len(tracks) == 3 and [c.findtext("in") for c in tracks[0]] == ["30", "150"]
        assert tracks[1].find(".//parameter[parameterid='center']/value/vert").text == "-0.25000"
        assert len(m.findall(".//audio/track")) == 2 and len(m.findall("sequence/marker")) == 2
        assert m.find(".//file[@id='file-1']/pathurl").text == "file:///footage/take%20one.mov"
        # EDL: source timecode from the take's own, record from 0
        e = edl(ctx)
        assert "001  AX       V     C        01:00:01:00 01:00:03:00 00:00:00:00 00:00:02:00" in e, e
        assert "002  AX       V     C        01:00:05:00 01:00:07:00 00:00:02:00 00:00:04:00" in e, e
        assert "| 1 | card-01.png | 0.33 | 3.00 | 50% 25% | 74% |" in capcut(ctx, cards, sfx)
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("edit")
    ap.add_argument("--to", required=True, help="fcpxml, premiere, resolve, capcut, edl, srt, all; or a comma list")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--source", help="the raw take, when report.json's path moved")
    ap.add_argument("--no-render", action="store_true", help="skip rendering animated cards (they become markers only)")
    a = ap.parse_args()
    todo = set(FORMATS) if a.to == "all" else {t.strip() for t in a.to.split(",")}
    if todo - set(FORMATS):
        ap.error(f"--to: unknown {sorted(todo - set(FORMATS))}; one of {', '.join(FORMATS)} or all")
    edit = Path(a.edit)
    ctx = ctx_timing(load_edit(edit, a.plan, a.source))
    if abs(ctx["total_f"] - ctx["plan"]["durationInFrames"]) > 1:
        sys.exit(f"ERROR: the cut's spans add up to {ctx['total_f']} frames, the plan to "
                 f"{ctx['plan']['durationInFrames']}. Plan again after the last cut.")
    written, cards, sfx, missing = export(ctx, ctx["edit"] / "export", todo, not a.no_render)
    for p in written:
        print(p)
    print(f"{len(ctx['segs'])} cuts from {ctx['source'].name}, {len(cards)} cards, {len(sfx)} sound cues")
    for c in missing:
        print(f"note: card {c['i']} ({c['name']}) left out: {c['why']}", file=sys.stderr)


if __name__ == "__main__":
    main()
