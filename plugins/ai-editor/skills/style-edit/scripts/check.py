#!/usr/bin/env python3
"""Check an edit mechanically before anyone looks at it.

    python3 check.py plan   edits/NAME [--plan plan.json] [--style style.json]   instant, stdlib only
    ~/.ai-video-editor/venv/bin/python check.py render edits/NAME [--plan plan.json]   reads render.mp4
    python3 check.py demo   self-check, synthetic data, no video

plan: every card inside the app's safe zones, vertical cards centred, no card on the head while
it is up (face.json, moved by the zooms or the split window), captions inside the safe zone and
never held long past their words, no stretch with nothing changing on screen, not more text cards
than picture cards, text cards' text at least 34 px.
render: on the rendered mp4 (4 samples a second), where the card's drawn pixels are: on the face
(YuNet, face.py), off centre, or not moving. On cut.mp4's audio: silences inside the speech, and
kept spans too short to read as anything but a glitch. Caption words that differ from what the
cut's own transcript heard are listed for a person to look at.

Prints FAIL / WARN / LOOK lines with the time and the fix, writes edits/NAME/check.json
(check-XYZ.json for plan-XYZ.json, one key per mode). Exit 1 on any FAIL.
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from plan import SAFE, clean, cut_points, head_during  # noqa: E402

CENTRE_PLAN = 1.5      # % of the width a vertical card's box centre may sit off 50
CENTRE_INK = 2.0       # % of the width a card's drawn content may sit off centre
WORD_S = 1.2           # a caption up longer than this per word is a misheard word held on screen
TAIL_S = 0.3           # a caption held longer than this past its last word
STATIC_S = 6.0         # nothing changes on screen for longer than this (no style pace given)
TEXT_ANIMS = ("counter", "steps", "versus", "keyword")
LABEL_MIN = 34         # px, remotion/src/Anims.tsx LABEL_MIN
SILENCE_S = 0.3        # a silence inside the speech longer than this
SLIVER_S = 0.2         # a kept span shorter than this between two splices
STILL_S = 1.5          # a card region unchanged for longer than this
FPS = 4                # render samples a second
ZOOM_ORIGIN = (50, 30)  # remotion/src/StyleEdit.tsx ZOOM_ORIGIN


def finding(level, t, what, fix):
    return {"level": level, "t": None if t is None else round(t, 2), "what": what, "fix": fix}


def aspect_of(plan):
    return "9:16" if plan["height"] > plan["width"] else "16:9"


def zoom_at(t, zooms):
    """StyleEdit.tsx zoomScale."""
    z = next((z for z in zooms if z["start"] <= t < z["end"]), None)
    if not z:
        return 1.0
    if z["kind"] == "punch" or z.get("ease_s", 0) <= 0:
        return z["scale"]
    e = min(z["ease_s"], (z["end"] - z["start"]) / 2)
    cub = lambda p: 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2
    if t < z["start"] + e:
        p = (t - z["start"]) / e
    elif t > z["end"] - e:
        p = (z["end"] - t) / e
    else:
        p = 1
    return 1 + (z["scale"] - 1) * cub(max(0, min(1, p)))


def on_screen(box, t, plan):
    """A head box on cut.mp4 (percent) -> where it is drawn on the output while a card is up:
    grown by the zoom, and in split moved into the speaker's window under the seam."""
    x, y, w, h = box
    s = zoom_at(t, plan["zooms"])
    lay = plan.get("layout")
    if not lay:
        ox, oy = ZOOM_ORIGIN
        return [ox + (x - ox) * s, oy + (y - oy) * s, w * s, h * s]
    sp = lay["speaker"]
    k = sp["scale"]
    ox, oy = k * sp["origin"][0], k * sp["origin"][1]
    x0, y0 = ox + (k * x - ox) * s - sp["x"], lay["seam"] + oy + (k * y - oy) * s - sp["y"]
    x1, y1 = x0 + k * w * s, y0 + k * h * s
    y0 = max(y0, lay["seam"])          # the window clips the video at the seam
    return [x0, y0, x1 - x0, max(0, y1 - y0)]


def fit(text, w, mx):
    """Anims.tsx fit: font px so text fits w on one line."""
    return min(mx, w / (0.52 * max(1, len(str(text)))))


def text_sizes(anim, w, h):
    """(what, px it would be drawn at before the renderer's 34 px floor) for a text card."""
    p, t = anim.get("props") or {}, anim["type"]
    out = []
    if t == "counter":
        dec = int(p.get("decimals", 0))
        full = f"{p.get('prefix', '')}{float(p.get('to', 0)):.{dec}f}{p.get('suffix', '')}"
        out.append(("number", fit(full, w * 0.86, h * 0.5)))
        if p.get("label"):
            out.append(("label", fit(p["label"], w * 0.86, h * 0.13)))
    elif t == "keyword":
        out.append(("text", fit(p.get("text", ""), w * 0.86, h * 0.34)))
        if p.get("sub"):
            out.append(("sub", fit(p["sub"], w * 0.86, h * 0.13)))
    elif t == "versus":
        out.append(("sides", min(fit(p.get("a", ""), w * 0.42, h * 0.3), fit(p.get("b", ""), w * 0.42, h * 0.3))))
    elif t == "steps":
        items = p.get("items") or [""]
        out.append(("items", min(h / (len(items) * 1.6 + 0.2), fit(max(items, key=len), w * 0.8, h))))
    return out


def check_plan(plan, face=None, cuts=(), static_s=STATIC_S):
    out = []
    aspect = aspect_of(plan)
    l, top, r, bottom = SAFE[aspect]
    if aspect == "9:16":
        l = r = max(l, r)
    W, H = plan["width"], plan["height"]
    cards = plan["cards"]
    step = (face or {}).get("step_s", 0.5)
    heads = [{"t": hd["t"], "box": on_screen(hd["box"], hd["t"], plan) if hd["box"] else None}
             for hd in (face or {}).get("heads", [])]
    for c in cards:
        name = f"'{c['trigger_word']}' {c.get('src') or c['anim']['type']}"
        x, y, w, h = c["box"]
        if x < l - 0.05 or y < top - 0.05 or x + w > 100 - r + 0.05 or y + h > 100 - bottom + 0.05:
            out.append(finding("FAIL", c["start"], f"{name} card {[round(v, 1) for v in c['box']]} reaches under the app's UI "
                               f"(safe: {l}% sides, {top}% top, {bottom}% bottom)",
                               "drop its box in visuals.json/images.json (plan.py fits it), then plan again"))
        if aspect == "9:16" and c.get("lane") != "logo" and abs(x + w / 2 - 50) > CENTRE_PLAN:
            out.append(finding("FAIL", c["start"], f"{name} card centre at {x + w / 2:.1f}% of the width, not 50",
                               "drop its box x in visuals.json/images.json so plan.py centres it"))
        if heads:
            hd = head_during(heads, step, c["start"], c["end"])
            if hd and x < hd[2] and x + w > hd[0] and y < hd[3] and y + h > hd[1]:
                out.append(finding("FAIL", c["start"], f"{name} card covers the head "
                                   f"(head {hd[1]:.0f}-{hd[3]:.0f}% down, card {y:.0f}-{y + h:.0f}%)",
                                   "run face.py, then plan again; or give the card a smaller box above the head"))
    cap = plan["captions"]["style"]
    ys = [("captions", cap.get("y_pct"))] + ([("full-frame captions", plan["layout"]["caption_full_y"])]
                                              if plan.get("layout") else [])
    for what, v in ys:
        if v is not None and not top <= v <= 100 - bottom:
            out.append(finding("FAIL", None, f"{what} at {v}% down, under the app's UI ({top}-{100 - bottom}% is clear)",
                               "set captions.y_pct in style.json inside that band, then plan again"))
    for ch in plan["captions"]["chunks"]:
        ws = ch["words"] or [{"end": ch["end"]}]
        dur, tail = ch["end"] - ch["start"], ch["end"] - ws[-1]["end"]
        if dur > WORD_S * len(ws) + 0.01:
            out.append(finding("FAIL", ch["start"], f"caption '{ch['text']}' up {dur:.1f} s for {len(ws)} word(s)",
                               "check that word in captions.json against the audio: a misheard or stretched word; fix or delete it"))
        elif tail > TAIL_S + 0.01:
            out.append(finding("FAIL", ch["start"], f"caption '{ch['text']}' held {tail:.2f} s past its last word",
                               "plan again with the current plan.py (it caps the tail at 0.3 s)"))
    # Stretches with nothing changing: no card up, no zoom starting or ending, no jump cut.
    dur = plan["durationInFrames"] / plan["fps"]
    marks = sorted([0.0, dur] + [z[k] for z in plan["zooms"] for k in ("start", "end")] + list(cuts)
                   + [c[k] for c in cards for k in ("start", "end")])
    for a, b in zip(marks, marks[1:]):
        if b - a > static_s and not any(c["start"] <= a and c["end"] >= b for c in cards):
            out.append(finding("WARN", a, f"static for {b - a:.1f} s ({a:.1f}-{b:.1f} s): no card, zoom or cut",
                               "add a visual beat or a zoom in that stretch"))
    main = [c for c in cards if c.get("lane") != "logo"]
    text = [c for c in main if (c.get("anim") or {}).get("type") in TEXT_ANIMS]
    if len(text) > len(main) - len(text):
        for c in text:
            out.append(finding("WARN", c["start"], f"'{c['trigger_word']}' {c['anim']['type']} is only text; "
                               f"{len(text)} text cards vs {len(main) - len(text)} picture cards",
                               "make it a scene (flow, race, pile) or a capture"))
    for c in text:
        w, h = c["box"][2] / 100 * W, c["box"][3] / 100 * H
        for part, px in text_sizes(c["anim"], w, h):
            label = part in ("label", "sub", "items")   # the renderer floors these at 34 px
            if px < LABEL_MIN:
                out.append(finding("WARN" if label else "FAIL", c["start"],
                                   f"'{c['trigger_word']}' {c['anim']['type']} {part} fits at {px:.0f} px"
                                   + (f"; floored to {LABEL_MIN} px it runs wider than the card" if label else ""),
                                   "shorten the text in visuals.json or give the card a bigger box"))
    return out


def slivers(spans, fps):
    """spans: kept frame ranges on the source (report.json frames). Interior spans shorter than
    SLIVER_S, at their time on the cut."""
    out, t = [], 0.0
    for i, (a, b) in enumerate(spans):
        d = (b - a) / fps
        if 0 < i < len(spans) - 1 and d < SLIVER_S:
            out.append(finding("FAIL", t, f"a {d:.2f} s kept span between two splices (source {a / fps:.2f} s)",
                               "cut: widen it to a whole word or remove it in spans.json, then rebuild the cut"))
        t += d
    return out


def caption_looks(heard, shown, known):
    """Words in captions.json that differ from what cut.transcript.json heard, minus names
    the edit uses on purpose (visuals.json)."""
    norm = lambda w: re.sub(r"[^\w']+", "", w["text"].replace("’", "'")).lower()
    tok = lambda ws: [w for w in ws if w.get("type", "word") == "word" and norm(w)]
    a, b = tok(heard), tok(shown)
    out = []
    sm = difflib.SequenceMatcher(a=[norm(w) for w in a], b=[norm(w) for w in b], autojunk=False)
    for op, i0, i1, j0, j1 in sm.get_opcodes():
        if op in ("replace", "insert"):
            new = " ".join(w["text"] for w in b[j0:j1])
            if all(norm(w) in known for w in b[j0:j1]):
                continue
            was = " ".join(w["text"] for w in a[i0:i1]) or "(nothing)"
            out.append(finding("LOOK", b[j0]["start"], f"caption shows '{new}', the cut's transcript heard '{was}'",
                               "listen: keep it if it is a correction, else put back what was said"))
    return out


def still_runs(diffs, thr):
    """diffs: [(t, mean abs change since the last sample)] over one card's life. Runs under thr
    longer than STILL_S, as (start, end)."""
    out, run = [], None
    for t, d in diffs:
        if d < thr:
            run = run or [t, t]
            run[1] = t
        else:
            if run and run[1] - run[0] + 1 / FPS > STILL_S:
                out.append(tuple(run))
            run = None
    if run and run[1] - run[0] + 1 / FPS > STILL_S:
        out.append(tuple(run))
    return out


# ---------------------------------------------------------------- render (numpy, cv2)

INK_DIFF = {"overlay": 40, "split": 8}   # a pixel is the card's when it differs this much from what is behind
STILL_DIFF = 0.4                          # mean abs grey change per sample under this = not moving
FACE_COVER = 0.02                         # card pixels on more than this share of the head = covering it


def stream(video, vf, w, h):
    import numpy as np
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-filter_complex", f"[0:v]{vf},fps={FPS},scale={w}:{h}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


def check_render(edit, plan, video):
    import cv2
    import numpy as np
    import face as facemod
    from edit import proxy_filter
    from plan import probe
    out, measured = [], {}
    split = bool(plan.get("layout"))
    mode = "split" if split else "overlay"
    W, H = plan["width"] // 2, plan["height"] // 2
    cards = plan["cards"]
    m = probe(edit / plan["video"])
    behind = stream(edit / plan["video"], proxy_filter(m["width"], m["height"], plan["width"], plan["height"]), W, H)
    ground = None
    if split:
        g = plan["layout"]["ground"].lstrip("#")
        ground = np.full((H, W, 3), [int(g[4:6], 16), int(g[2:4], 16), int(g[0:2], 16)], np.uint8)
    det = None
    pix = lambda b, pad=0: (max(0, int((b[0] - pad) / 100 * W)), max(0, int((b[1] - pad) / 100 * H)),
                            min(W, int((b[0] + b[2] + pad) / 100 * W)), min(H, int((b[1] + b[3] + pad) / 100 * H)))
    per = {i: {"diffs": [], "cover": [], "prev": None, "mid": None} for i in range(len(cards))}
    for n, frame in enumerate(stream(video, "null", W, H)):
        t = n / FPS
        cut = next(behind, None)
        up = [i for i, c in enumerate(cards) if c["start"] + 0.35 <= t <= c["end"] - 0.2]
        if not up:
            continue
        if split:
            bg = ground
        else:
            s = zoom_at(t, plan["zooms"])
            ox, oy = ZOOM_ORIGIN[0] / 100 * W, ZOOM_ORIGIN[1] / 100 * H
            bg = cv2.warpAffine(cut, np.float32([[s, 0, ox * (1 - s)], [0, s, oy * (1 - s)]]), (W, H))
        diff = cv2.absdiff(cv2.GaussianBlur(frame, (5, 5), 0), cv2.GaussianBlur(bg, (5, 5), 0)).max(axis=2)
        ink = cv2.morphologyEx((diff > INK_DIFF[mode]).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        heads = []
        if n % 2 == 0:      # the head every 0.5 s. Overlay: from the cut itself, so a card on the face can't hide it
            src = frame if split else bg
            sw = facemod.SCAN_W
            sh = round(sw * H / W)
            if det is None:
                det = cv2.FaceDetectorYN.create(facemod.model(), "", (sw, sh), 0.6)
            _, faces = det.detect(cv2.resize(src, (sw, sh)))
            for f in faces if faces is not None else []:
                b = facemod.head_box(f[:4].tolist(), sw, sh)
                if not split or b[1] + b[3] / 2 > plan["layout"]["seam"]:   # split: the speaker is in the window
                    heads.append(b)
            heads = sorted(heads, key=lambda b: -b[2] * b[3])[:1]
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        for i in up:
            c, st = cards[i], per[i]
            x0, y0, x1, y1 = pix(c["box"], 2)
            if split:   # below the art box is the speaker's window and its shadow, never the card
                y1 = min(y1, int((c["box"][1] + c["box"][3]) / 100 * H))
            mask = np.zeros_like(ink)
            mask[y0:y1, x0:x1] = ink[y0:y1, x0:x1]
            for hb in heads:
                hx0, hy0, hx1, hy1 = pix(hb)
                area = max(1, (hx1 - hx0) * (hy1 - hy0))
                st["cover"].append((t, float(mask[hy0:hy1, hx0:hx1].sum()) / area))
            region = grey[y0:y1, x0:x1]
            if st["prev"] is not None:
                st["diffs"].append((t, float(np.abs(region - st["prev"]).mean())))
            st["prev"] = region
            if st["mid"] is None and t >= (c["start"] + c["end"]) / 2:
                ys, xs = np.nonzero(mask)
                st["mid"] = (t, None if not len(xs) else [100 * xs.min() / W, 100 * ys.min() / H,
                                                          100 * (xs.max() + 1) / W, 100 * (ys.max() + 1) / H])
    for i, c in enumerate(cards):
        st, name = per[i], f"'{c['trigger_word']}' {c.get('src') or c['anim']['type']}"
        rec = measured.setdefault(f"{i}:{c['trigger_word']}", {})
        bad = [(t, f) for t, f in st["cover"] if f > FACE_COVER]
        rec["face_cover_max"] = round(max([f for _, f in st["cover"]], default=0), 3)
        if bad:
            out.append(finding("FAIL", bad[0][0], f"{name} card is drawn over the face at {len(bad)} sample(s), "
                               f"up to {100 * max(f for _, f in bad):.0f}% of the head",
                               "run face.py, plan again (plan.py moves it off the head); check the box in visuals.json"))
        if st["mid"] and st["mid"][1]:
            x0, y0, x1, y1 = st["mid"][1]
            cx = (x0 + x1) / 2
            rec["ink"] = [round(v, 1) for v in st["mid"][1]]
            rec["ink_centre_x"] = round(cx, 1)
            if aspect_of(plan) == "9:16" and c.get("lane") != "logo" and abs(cx - 50) > CENTRE_INK:
                out.append(finding("FAIL", st["mid"][0], f"{name} card is drawn {cx - 50:+.1f}% of the width off centre "
                                   f"(its content spans {x0:.0f}-{x1:.0f}%)",
                                   "centre the content inside the card (Anims.tsx / the capture's clip), then render again"))
        elif c["end"] - c["start"] > 0.8:
            rec["ink"] = None
            out.append(finding("WARN", (c["start"] + c["end"]) / 2, f"{name} card: nothing drawn found in its box",
                               "look at that frame: the card may be missing from the render"))
        rec["still"] = still_runs(st["diffs"], STILL_DIFF) if c.get("lane") != "logo" else []
        for a, b in rec["still"]:
            out.append(finding("WARN", a, f"{name} card holds still for {b - a + 1 / FPS:.1f} s ({a:.1f}-{b + 1 / FPS:.1f} s)",
                               "give it motion: a highlight or a taller clip for a capture, words for a scene's parts"))
    return out, measured


def check_audio(edit, words):
    """Silences inside the speech on cut.mp4, at the cut skill's threshold derived from this take."""
    sys.path.insert(0, str(HERE.parents[1] / "cut" / "scripts"))
    from build_timeline import SPEECH_OFFSET_DB, derive_noise_db, detect_silence, window_rms_db
    src = Path((json.loads((edit / "report.json").read_text()) if (edit / "report.json").exists() else {}).get("source", ""))
    noise, how = None, ""
    for f, label in ((src, "derived from the source, as the cut did"), (edit / "cut.mp4", "derived from the cut")):
        if noise is None and f.is_file():
            lvl = window_rms_db(f)
            noise, diag = derive_noise_db(lvl)
            how = label
    if noise is None:   # a tight cut can leave no floor to measure: speech level minus the cut skill's offset
        noise = sorted(lvl)[int(0.99 * (len(lvl) - 1))] - SPEECH_OFFSET_DB
        how = f"speech - {SPEECH_OFFSET_DB:.0f} dB ({diag.get('reason')})"
    ws = [w for w in words if w.get("type", "word") == "word"]
    a, b = ws[0]["start"], ws[-1]["end"]
    out = []
    for s, e in detect_silence(edit / "cut.mp4", round(noise, 1), SILENCE_S):
        s, e = max(s, a), min(e, b)
        if e - s > SILENCE_S:
            out.append(finding("FAIL", s, f"{e - s:.2f} s of silence inside the speech ({s:.2f}-{e:.2f} s)",
                               "cut: tighten that splice or pause (spans.json / --max-pause), then rebuild the cut"))
    return out, {"noise_db": round(noise, 1), "threshold": how}


def report(found, mode):
    order = {"FAIL": 0, "WARN": 1, "LOOK": 2}
    found.sort(key=lambda f: (order[f["level"]], f["t"] if f["t"] is not None else -1))
    for f in found:
        t = f"{f['t']:6.2f}s" if f["t"] is not None else "       "
        print(f"{f['level']:4} {t}  {f['what']}\n                -> {f['fix']}")
    n = {k: sum(f["level"] == k for f in found) for k in order}
    print(f"check {mode}: {n['FAIL']} FAIL, {n['WARN']} WARN, {n['LOOK']} LOOK")
    return n


def demo():
    face = {"step_s": 0.5, "heads": [{"t": t / 2, "box": [30, 32, 40, 24]} for t in range(20)]}
    words = [{"text": "a", "start": 0.0, "end": 0.3, "type": "word"}]
    plan = {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 600, "zooms": [],
            "captions": {"style": {"y_pct": 68}, "chunks": [
                {"text": "ok", "start": 0.0, "end": 0.5, "words": [{"text": "ok", "start": 0.0, "end": 0.3}]},
                {"text": "cloud", "start": 1.0, "end": 4.0, "words": [{"text": "cloud", "start": 1.0, "end": 3.9}]}]},
            "cards": [{"src": "images/a.png", "start": 0.5, "end": 3.0, "trigger_word": "a", "box": [14, 14, 72, 16]},
                      {"src": "images/b.png", "start": 3.0, "end": 5.0, "trigger_word": "b", "box": [6, 14, 72, 16]},
                      {"src": "images/c.png", "start": 5.0, "end": 7.0, "trigger_word": "c", "box": [14, 20, 72, 20]},
                      {"anim": {"type": "keyword", "props": {"text": "a very long keyword line that will not fit"}},
                       "start": 7.0, "end": 9.0, "trigger_word": "d", "box": [14, 14, 72, 10]},
                      {"anim": {"type": "counter", "props": {"to": 10}}, "start": 9.0, "end": 9.8, "trigger_word": "e",
                       "box": [14, 14, 72, 16]},
                      {"anim": {"type": "steps", "props": {"items": ["x"]}}, "start": 9.8, "end": 10.0,
                       "trigger_word": "f", "box": [14, 14, 72, 16]},
                      {"anim": {"type": "keyword", "props": {"text": "go"}}, "start": 10.0, "end": 10.5,
                       "trigger_word": "g", "box": [14, 14, 72, 16]}]}
    got = check_plan(plan, face)
    has = lambda lvl, word, s: any(f["level"] == lvl and s in f["what"] and f"'{word}'" in f["what"] for f in got)
    assert not any(f"'a'" in f["what"] for f in got if f["level"] == "FAIL"), got   # clean card passes
    assert has("FAIL", "b", "centre at 42") and has("FAIL", "b", "under the app's UI"), got
    assert has("FAIL", "c", "covers the head"), got
    assert any(f["level"] == "FAIL" and "'cloud' up 3.0 s" in f["what"] for f in got), got
    assert has("FAIL", "d", "text fits at") and has("WARN", "d", "only text"), got
    assert any(f["level"] == "WARN" and "static for 9.5 s" in f["what"] for f in got), got
    # A punch zoom grows the head into a logo beside it.
    near = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 40, 40, 20]}]}
    one = {**plan, "cards": [{**plan["cards"][0], "start": 0, "end": 1, "box": [72, 40, 14, 10], "lane": "logo"}]}
    assert not any("covers" in f["what"] for f in check_plan(one, near))
    one["zooms"] = [{"start": 0, "end": 1, "scale": 1.3, "kind": "punch", "ease_s": 0}]
    assert any("covers" in f["what"] for f in check_plan(one, near))
    # Split: the window clips the head at the seam, so a card in the art box never covers it.
    sp = {**one, "zooms": [], "layout": {"seam": 50, "caption_full_y": 68,
                                         "speaker": {"scale": 1, "x": 0, "y": 40, "origin": [50, 50]}}}
    sp["cards"] = [{**one["cards"][0], "box": [14, 14, 72, 34]}]
    assert on_screen([30, 20, 40, 30], 0, sp)[1] == 50 and not any("covers" in f["what"] for f in check_plan(sp, near))
    assert [f["t"] for f in slivers([[0, 90], [100, 104], [110, 200]], 30)] == [3.0]
    heard = [{"text": t, "start": i, "end": i + 0.5} for i, t in enumerate("I use cloud and jev daily".split())]
    shown = [{**w, "text": {"cloud": "Claude", "daily": "dally"}.get(w["text"], w["text"])} for w in heard]
    looks = caption_looks(heard, shown, {"claude"})
    assert [f["t"] for f in looks] == [5] and "dally" in looks[0]["what"], looks
    assert still_runs([(0.25 * i, 0.1 if 2 <= i <= 10 else 3) for i in range(14)], 0.4) == [(0.5, 2.5)]
    assert zoom_at(1, [{"start": 0, "end": 2, "scale": 1.2, "kind": "push", "ease_s": 0.5}]) == 1.2
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["plan", "render"])
    ap.add_argument("edit")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--style", help="style.json: its pace sets how long a static stretch may run")
    a = ap.parse_args()
    edit = Path(a.edit).resolve()
    plan_path = edit / a.plan
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan"):]
    rd = lambda n: json.loads((edit / n).read_text()) if (edit / n).exists() else None
    face = rd("face.json")
    extra = {}
    if a.mode == "plan":
        pace = (json.loads(Path(a.style).read_text()).get("pace") or {}) if a.style else {}
        static_s = round(2.5 * pace["median_shot_s"], 1) if pace.get("median_shot_s") else STATIC_S
        if not face:
            print("note: no face.json, the head check is skipped (run face.py)")
        found = check_plan(plan, face, cut_points(edit), static_s)
        extra = {"static_s": static_s}
    else:
        video = edit / f"render{tag}.mp4"
        if not video.exists():
            sys.exit(f"ERROR: {video} missing; render first")
        found, extra["cards"] = check_render(edit, plan, video)
        rep = rd("report.json")
        if rep and rep.get("frames"):
            found += slivers(rep["frames"], rep.get("fps") or 30)
        elif rd("decisions.json"):
            found += slivers([[s["start"] * 1000, s["end"] * 1000] for s in rd("decisions.json")], 1000)
        heard, shown = rd("cut.transcript.json"), rd("captions.json")
        if heard:
            f, extra["audio"] = check_audio(edit, shown or heard)
            found += f
        if heard and shown:
            known = {s.lower() for s in re.findall(r"[\w']+", json.dumps(rd("visuals.json") or []))}
            found += caption_looks(heard, shown, known)
    n = report(found, a.mode)
    out = edit / f"check{tag}.json"
    doc = json.loads(out.read_text()) if out.exists() else {}
    doc[a.mode] = {"plan": a.plan, "counts": n, "findings": found, **extra}
    out.write_text(json.dumps(doc, indent=1))
    print(out)
    sys.exit(1 if n["FAIL"] else 0)


if __name__ == "__main__":
    main()
