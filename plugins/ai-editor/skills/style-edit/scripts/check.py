#!/usr/bin/env python3
"""Check an edit mechanically before anyone looks at it.

    python3 check.py plan   edits/NAME [--plan plan.json] [--style style.json]   instant, stdlib only
    ~/.ai-video-editor/venv/bin/python check.py render edits/NAME [--plan plan.json] [--style style.json]   reads render.mp4
    python3 check.py demo   self-check, synthetic data, no video

plan: every card inside the app's safe zones, vertical cards centred, no card on the head while
it is up (face.json, moved by the zooms or the split window), captions inside the safe zone and
never held long past their words, no stretch with nothing changing on screen, not more text cards
than picture cards, text cards' text at least 34 px.
render: on the rendered mp4 (4 samples a second), where the card's drawn pixels are: on the face
(YuNet, face.py), off centre, or not moving. On cut.mp4's audio: silences inside the speech, and
kept spans too short to read as anything but a glitch. Caption words that differ from what the
cut's own transcript heard are listed for a person to look at. Then quality.py: every frame
(freezes, one-frame pops, jitter, a first-frame flash, when each card lands against its word,
static stretches, cuts and cards a minute against style.json), each settled card (text running
into its edge, contrast, the AI-default look), captions (contrast, the frame's edge), loudness, true
peak and each sound cue against the voice, and a render older than what it was made from.

Prints FAIL / WARN / LOOK lines with the time and the fix, writes edits/NAME/check.json
(check-XYZ.json for plan-XYZ.json, one key per mode). Exit 1 on any FAIL.
"""
import argparse
import difflib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
from plan import GAP_S, QUIET_HOLD_S, card_gaps, INK_MIN_W, OVERLAY_EDGE, OVERLAY_TOP, RAIL_TOP, READ_XH, SAFE, capture_xh, explain_ink, clean, cut_lines, cut_points, head_during, overlay_led, small_lines, sticker_crop  # noqa: E402

CENTRE_PLAN = 1.5      # % of the width a vertical card's box centre may sit off 50
CENTRE_INK = 2.0       # % of the width a card's drawn content may sit off centre
WORD_S = 1.2           # a caption up longer than this per word is a misheard word held on screen
TAIL_S = 0.3           # a caption held longer than this past its last word
STATIC_S = 6.0         # nothing changes on screen for longer than this (no style pace given)
TEXT_ANIMS = ("counter", "steps", "versus", "keyword")
LABEL_MIN = 34         # px, remotion/src/Anims.tsx LABEL_MIN
SILENCE_S = 0.3        # a silence inside the speech longer than this
SLIVER_S = 0.2         # a kept span shorter than this between two splices
HOOK_TOL_S = 0.5       # a first graphic this much later than the creator's winners' median is a miss
HOOK_S = 3.0           # the hook: a capture up in this opening shows what is said (a `find` mark), not the page's headline
STILL_S = 1.5          # a card region unchanged for longer than this
FPS = 4                # render samples a second
ZOOM_ORIGIN = (50, 30)  # remotion/src/StyleEdit.tsx ZOOM_ORIGIN


# Where an explaining card's size and place come from: the plan, never the renderer's source.
PLAN_FIX = ("plan again (plan.py makes a vertical flow a full-frame scene and centres a logo_cluster's logos); "
            "drop a \"layout\": \"box\", a \"box\" or a \"band\" set on that beat in visuals.json; "
            "a flow of one node or a cluster of one logo is a logo card instead")


def spread(c):
    """A card laid round the head over the whole frame (logo_cluster): its content is placed by the head,
    not centred, so the off-centre checks skip it."""
    return (c.get("anim") or {}).get("type") == "logo_cluster" or c.get("box") == [0, 0, 100, 100] and c.get("layout") != "scene"


def finding(level, t, what, fix):
    return {"level": level, "t": None if t is None else round(t, 2), "what": what, "fix": fix}


def aspect_of(plan):
    return "9:16" if plan["height"] > plan["width"] else "16:9"


PUNCH_S, PUSH_MIN_S = 0.16, 0.8   # StyleEdit.tsx


def zoom_state(t, zooms):
    """StyleEdit.tsx zoomAt: (scale, (origin x, y) % of the frame). Punches ease over PUNCH_S on power2.out,
    pushes at least PUSH_MIN_S each way on sine.inOut (a fitted ease is read as sine.inOut here); log space."""
    zs = sorted(zooms, key=lambda z: z["start"])
    out2 = lambda p: 1 - (1 - p) ** 2  # noqa: E731
    sine = lambda p: (1 - math.cos(math.pi * p)) / 2  # noqa: E731
    for i, z in enumerate(zs):
        nxt = zs[i + 1]["start"] if i + 1 < len(zs) else float("inf")
        push = z.get("kind") == "push" and z.get("ease_s", 0) > 0
        tail = 0 if push else min(PUNCH_S, max(0, nxt - z["end"]))
        if not z["start"] <= t < z["end"] + tail:
            continue
        if push:
            e = min(max(PUSH_MIN_S, z["ease_s"]), (z["end"] - z["start"]) / 2)
            p = sine((t - z["start"]) / e) if t < z["start"] + e else sine((z["end"] - t) / e) if t > z["end"] - e else 1
        else:
            p = out2(min(1, (t - z["start"]) / PUNCH_S)) if t < z["end"] else 1 - out2(min(1, (t - z["end"]) / PUNCH_S))
        return z["scale"] ** max(0.0, min(1.0, p)), tuple(z.get("origin") or ZOOM_ORIGIN)
    return 1.0, ZOOM_ORIGIN


def zoom_at(t, zooms):
    """The zoom for the head check: held at its peak from its start (a punch's 0.16 s ramp errs large)."""
    z = next((z for z in zooms if z["start"] <= t < z["end"] and z.get("kind") != "push"), None)
    return z["scale"] if z else zoom_state(t, zooms)[0]


def pan_at(t, pans):
    """StyleEdit.tsx panAt: (offset % of the width, cover scale)."""
    x = 0.0
    for p in pans or []:
        if t >= p["start"]:
            q = min(1.0, (t - p["start"]) / max(1e-3, p["end"] - p["start"]))
            x = p["from"] + (p["to"] - p["from"]) * (1 - math.cos(math.pi * q)) / 2
    return x, 1 + 2 * abs(x) / 100


def footage_affine(t, plan, W, H):
    """Where StyleEdit.tsx draws the cut at t (overlay layout): 2x3 matrix, frame px. Scale about the zoom's
    origin (the zoom x the pan's cover), then the pan's shift."""
    k, (ox, oy) = zoom_state(t, plan["zooms"])
    px, pk = pan_at(t, plan.get("pans"))
    s, ox, oy = k * pk, ox / 100 * W, oy / 100 * H
    return [[s, 0, ox * (1 - s) + px / 100 * W], [0, s, oy * (1 - s)]]


def on_screen(box, t, plan):
    """A head box on cut.mp4 (percent) -> where it is drawn on the output while a card is up:
    grown by the zoom (and moved by a pan), and in split moved into the speaker's window under the seam."""
    x, y, w, h = box
    s = zoom_at(t, plan["zooms"])
    lay = plan.get("layout")
    if not lay:
        ox, oy = zoom_state(t, plan["zooms"])[1]
        px, pk = pan_at(t, plan.get("pans"))
        s *= pk
        return [ox + (x - ox) * s + px, oy + (y - oy) * s, w * s, h * s]
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


def check_plan(plan, face=None, cuts=(), static_s=STATIC_S, visuals=None, brand=None, named=()):
    """named: [(t, name)] the profile's things said (route.py beats.json)."""
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
        if c.get("format") == "sticker" and c.get("lines") and c.get("size"):
            cut = cut_lines(sticker_crop(c), c["lines"])
            if cut:
                out.append(finding("FAIL", c["start"], f"{name} sticker's crop cuts {len(cut)} line(s) of text at its edge",
                                   "plan again (plan.py whole_lines grows the crop to whole lines), or drop props.crop"))
        tiny = aspect == "9:16" and small_lines(c, aspect)
        if tiny:
            out.append(finding("FAIL", c["start"], f"{name} sticker shows {len(tiny)} line(s) of text under {READ_XH} px x-height "
                               "beside its evidence (a kicker or footnote): unreadable on a phone",
                               "plan again (plan.py leaves those lines out of the crop), or set a \"crop\" round the evidence lines"))
        marks = c.get("marks") or ((c.get("anim") or {}).get("props") or {}).get("marks") or []
        if (c.get("src") or "").startswith("images/capture-") and c["start"] < HOOK_S \
                and not any(mk.get("find") for mk in marks) and not c.get("highlight"):
            out.append(finding("FAIL", c["start"], f"{name} capture on the hook has no `find` mark: it shows the page's own "
                               "headline, not what is said", "give the beat a mark whose \"find\" is the page's words for what "
                               "the speaker says (visuals.json), capture again; or move the card past the hook"))
        xh = aspect == "9:16" and c.get("src") and c.get("layout") != "scene" and capture_xh(c, aspect)
        if xh and xh < READ_XH:
            out.append(finding("FAIL", c["start"], f"{name} capture text renders at {xh:.0f} px x-height, under {READ_XH}: "
                               "unreadable on a phone", "plan again (plan.py cuts it to the evidence as a sticker), or give "
                               "the beat a \"crop\" round the evidence lines, or \"layout\": \"scene\""))
        if c.get("layer") == "behind":
            # behind the speaker: the cutout covers the card where it meets him, so it may reach the head,
            # but only once matte.py has cut him out for this card's time
            fps = plan["fps"]
            if not any(k["from"] <= c["start"] * fps and c["end"] * fps <= k["to"] + 1 for k in plan.get("cutouts") or []):
                out.append(finding("FAIL", c["start"], f"{name} card sits behind the speaker but there is no cutout for it",
                                   "run matte.py edits/<name> (it cuts the speaker out where behind cards are up)"))
            continue
        ink = aspect == "9:16" and explain_ink(c, W, H)
        if ink and (ink[1] - ink[0] < INK_MIN_W or abs((ink[0] + ink[1]) / 2 - 50) > CENTRE_INK):
            out.append(finding("FAIL", c["start"], f"{name} draws {ink[0]:.0f}-{ink[1]:.0f}% of the width "
                               f"(under {INK_MIN_W}% wide or off centre): small and lopsided on a phone", PLAN_FIX))
        if c.get("layout") == "scene" or spread(c):
            continue    # a full-frame cut-away, or logos laid round the head: the renderer keeps them clear
        cl, ct, cr = l, top, r
        if aspect == "9:16" and overlay_led(c):     # plan.free_regions' allowances
            cl, ct = OVERLAY_EDGE, OVERLAY_TOP
            if y + h <= RAIL_TOP:
                cr = OVERLAY_EDGE
        if x < cl - 0.05 or y < ct - 0.05 or x + w > 100 - cr + 0.05 or y + h > 100 - bottom + 0.05:
            out.append(finding("FAIL", c["start"], f"{name} card {[round(v, 1) for v in c['box']]} reaches under the app's UI "
                               f"(safe: {l}% sides, {top}% top, {bottom}% bottom)",
                               "drop its box in visuals.json/images.json (plan.py fits it), then plan again"))
        if aspect == "9:16" and c.get("lane") != "logo" and not spread(c) and abs(x + w / 2 - 50) > CENTRE_PLAN:
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
    # pacing (SKILL.md step 3): a stretch with no card longer than the plan's card_gap_s is fine only when nothing
    # in it is named and the frame still changes (a zoom or a cut) at least every QUIET_HOLD_S
    gap_s = plan.get("card_gap_s") or GAP_S
    moves = sorted([z[k] for z in plan["zooms"] for k in ("start", "end")] + list(cuts))
    for a, b in card_gaps(cards, dur):
        if b - a <= gap_s + 0.01:
            continue
        said = [f"'{n}' at {t:.1f} s" for t, n in named if a <= t < b]
        pts = [a] + [x for x in moves if a < x < b] + [b]
        still = max(y - x for x, y in zip(pts, pts[1:]))
        if said or still > QUIET_HOLD_S + 0.01:
            out.append(finding("WARN", a, f"no card for {b - a:.1f} s ({a:.1f}-{b:.1f} s; the rule is {gap_s:.0f} s)"
                               + (f": {', '.join(said)} is named there" if said else f" and the frame holds still for {still:.1f} s"),
                               "show the named thing (a capture, post or logo in visuals.json)" if said else
                               f"plan again (plan.py adds a zoom change every {QUIET_HOLD_S:.0f} s there); never a made-up visual"))
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
    # the creator's hook (plan "targets", from style.json hook.winner): her winners show a graphic by then
    want = (plan.get("targets") or {}).get("first_graphic_s")
    if want is not None:
        first = min((c["start"] + ((c.get("anim") or {}).get("props") or c.get("props") or {}).get("word_at", 0.1)
                     for c in cards), default=None)
        if first is None or first > want + HOOK_TOL_S:
            ctl = plan["targets"].get("control_first_graphic_s")
            out.append(finding("WARN", first, ("no graphic at all" if first is None else f"first graphic lands at {first:.1f} s")
                               + f"; the creator's winners show one by {want:.1f} s" + (f" (her other videos: {ctl:.1f} s)" if ctl is not None else ""),
                               "anchor a visual to a word in the first sentence (visuals.json)"))
    for c, n in unsaid_numbers(plan):
        out.append(finding("FAIL", c["start"], f"'{c['trigger_word']}' {c['anim']['type']} shows {n}, a number nobody says",
                           "show the page that published it (a capture), or only the words the speaker says"))
    # the AI-made look (references/ai-tells.md): BAN -> FAIL, WARN -> WARN
    from ai_tells import check_plan as ai_tells, for_brand
    for f in for_brand(ai_tells(plan, visuals), brand):
        out.append(finding("FAIL" if f["level"] == "BAN" else "WARN", None, f"AI tell '{f['tell']}': {f['where']}", f["fix"]))
    return out


UNITS = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
BIG = {"hundred": 100, "thousand": 1000, "million": 10 ** 6, "billion": 10 ** 9}
REAL_ANIMS = ("social_post", "video_card", "terminal")   # a real post or clip (fetched), a command line: not a statistic


def nums(text):
    """The numbers written in a text, normalised ("1,200" -> "1200", "40%" -> "40")."""
    return {str(float(n.replace(",", ""))).removesuffix(".0") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def said_numbers(text):
    """The numbers spoken in a transcript, written as digits or words ("forty two" -> 42, "ten" -> 10)."""
    out, ws = nums(text), re.findall(r"[a-z]+", text.lower())
    for i, w in enumerate(ws):
        v = UNITS.index(w) if w in UNITS else TENS.get(w, BIG.get(w))
        if v is None:
            continue
        if w in TENS and i + 1 < len(ws) and ws[i + 1] in UNITS[1:10]:
            out.add(str(v + UNITS.index(ws[i + 1])))
        out.add(str(v))
    return out


def unsaid_numbers(plan):
    """[(card, number)]: a number on a built card that the speaker never says. A capture or a real post is the
    source itself and is exempt. Without captions there is nothing to check against."""
    from ai_tells import strings
    spoken = " ".join(ch.get("text", "") for ch in (plan.get("captions") or {}).get("chunks", []))
    if not spoken.strip():
        return []
    said = said_numbers(spoken)
    out = []
    for c in plan["cards"]:
        a = c.get("anim") or {}
        if a.get("type") in REAL_ANIMS:
            continue
        for n in sorted({n for _, t in strings(a.get("props") or {}) for n in nums(t)} - said):
            out.append((c, n))
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
    the edit uses on purpose (visuals.json) and the cut's own spelling (words.json, fixes.json)."""
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


def stream(video, vf, w, h, fps=FPS):
    import numpy as np
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-filter_complex", f"[0:v]{vf},fps={fps},scale={w}:{h}",
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
            zm = np.float32(footage_affine(t, plan, W, H))
            bg = cv2.warpAffine(cut, zm, (W, H))
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
        # a behind card may sit inside the head box (beside the hair, behind it): only ink ON the speaker
        # (the cutout's solid pixels, on the same zoom) counts as covering him
        person = None
        if not split and any(cards[i].get("layer") == "behind" for i in up):
            k = next((x for x in plan.get("cutouts") or [] if x["from"] <= n <= x["to"]), None)
            png = k and edit / k["src"] / f"{n - k['from']:06d}.png"
            if png and png.exists():
                al = cv2.resize(cv2.imread(str(png), cv2.IMREAD_UNCHANGED)[..., 3], (W, H), interpolation=cv2.INTER_AREA)
                person = cv2.warpAffine(al, zm, (W, H)) > 230
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
                on = mask[hy0:hy1, hx0:hx1]
                if c.get("layer") == "behind" and person is not None:
                    on = on * person[hy0:hy1, hx0:hx1]
                st["cover"].append((t, float(on.sum()) / area))
            region = grey[y0:y1, x0:x1]
            if st["prev"] is not None:
                st["diffs"].append((t, float(np.abs(region - st["prev"]).mean())))
            st["prev"] = region
            # Measured once the card has settled (every scene part landed), just before it leaves:
            # a scene that builds left to right is off centre mid-build by design.
            if st["mid"] is None and t >= max((c["start"] + c["end"]) / 2, c["end"] - 0.6):
                ys, xs = np.nonzero(mask)
                st["mid"] = (t, None if not len(xs) else [100 * xs.min() / W, 100 * ys.min() / H,
                                                          100 * (xs.max() + 1) / W, 100 * (ys.max() + 1) / H])
    for i, c in enumerate(cards):
        st, name = per[i], f"'{c['trigger_word']}' {c.get('src') or c['anim']['type']}"
        rec = measured.setdefault(f"{i}:{c['trigger_word']}", {})
        bad = [(t, f) for t, f in st["cover"] if f > FACE_COVER and c.get("layout") != "scene"]   # a cut-away hides him on purpose
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
            explain = (c.get("anim") or {}).get("type") in ("flow", "logo_cluster")
            if aspect_of(plan) == "9:16" and c.get("lane") != "logo" and (explain or not spread(c)) \
                    and (abs(cx - 50) > CENTRE_INK or explain and x1 - x0 < INK_MIN_W):
                out.append(finding("FAIL", st["mid"][0], f"{name} card is drawn {cx - 50:+.1f}% of the width off centre "
                                   f"(its content spans {x0:.0f}-{x1:.0f}%)" if abs(cx - 50) > CENTRE_INK else
                                   f"{name} card is drawn {x1 - x0:.0f}% of the width wide, under {INK_MIN_W}% "
                                   f"(its content spans {x0:.0f}-{x1:.0f}%)",
                                   PLAN_FIX + "; then render again" if explain else
                                   "plan again: drop the beat's \"box\" in visuals.json/images.json so plan.py centres it, "
                                   "or give a capture a \"crop\" round the evidence; then render again"))
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


def style_note(path, style):
    """The line printed when the render's rhythm is not compared with a creator (None when it is)."""
    if not path:
        return "note: no --style, so the rhythm is measured but not compared with the creator"
    if not style:
        return f"note: {Path(path).name} is the default style (no creator), so the rhythm is measured, not compared"
    return None


def demo():
    assert "no --style" in style_note(None, None) and style_note("s.json", {"pace": {}}) is None
    assert "no --style" not in style_note("edits/x/style.json", {}), style_note("edits/x/style.json", {})
    face = {"step_s": 0.5, "heads": [{"t": t / 2, "box": [30, 32, 40, 24]} for t in range(20)]}
    words = [{"text": "a", "start": 0.0, "end": 0.3, "type": "word"}]
    plan = {"width": 1080, "height": 1920, "fps": 30, "durationInFrames": 600, "zooms": [],
            "captions": {"style": {"y_pct": 68}, "chunks": [
                {"text": "ok", "start": 0.0, "end": 0.5, "words": [{"text": "ok", "start": 0.0, "end": 0.3}]},
                {"text": "cloud", "start": 1.0, "end": 4.0, "words": [{"text": "cloud", "start": 1.0, "end": 3.9}]}]},
            "cards": [{"src": "images/a.png", "start": 0.5, "end": 3.0, "trigger_word": "a", "box": [14, 14, 72, 16]},
                      {"src": "images/b.png", "start": 3.0, "end": 5.0, "trigger_word": "b", "box": [2, 14, 72, 16]},
                      {"src": "images/c.png", "start": 5.0, "end": 7.0, "trigger_word": "c", "box": [14, 20, 72, 20]},
                      {"anim": {"type": "keyword", "props": {"text": "a very long keyword line that will not fit"}},
                       "start": 7.0, "end": 9.0, "trigger_word": "d", "box": [14, 14, 72, 10]},
                      {"anim": {"type": "counter", "props": {"to": 10}}, "start": 9.0, "end": 9.8, "trigger_word": "e",
                       "box": [14, 14, 72, 16]},
                      {"anim": {"type": "steps", "props": {"items": ["x"]}}, "start": 9.8, "end": 10.0,
                       "trigger_word": "f", "box": [14, 14, 72, 16]},
                      {"anim": {"type": "keyword", "props": {"text": "go"}}, "start": 10.0, "end": 10.5,
                       "trigger_word": "g", "box": [14, 14, 72, 16]}]}
    scene = {**plan, "cards": [{"anim": {"type": "flow"}, "layout": "scene", "start": 0.5, "end": 3,
                                "trigger_word": "s", "box": [0, 0, 100, 100]}]}
    assert not any(f["level"] == "FAIL" and "'s'" in f["what"] for f in check_plan(scene, face))
    got = check_plan(plan, face)
    has = lambda lvl, word, s: any(f["level"] == lvl and s in f["what"] and f"'{word}'" in f["what"] for f in got)
    assert not any(f"'a'" in f["what"] for f in got if f["level"] == "FAIL"), got   # clean card passes
    assert has("FAIL", "b", "centre at 38") and has("FAIL", "b", "under the app's UI"), got
    assert has("FAIL", "c", "covers the head"), got
    # a behind card may reach the head, but needs its cutout
    bh = {**plan, "cards": [{**plan["cards"][2], "layer": "behind"}]}
    assert any("no cutout" in f["what"] for f in check_plan(bh, face)) and not any("covers the head" in f["what"] for f in check_plan(bh, face))
    bh["cutouts"] = [{"src": "cutout/x.mov", "from": 0, "to": 10 ** 6}]
    assert not any("no cutout" in f["what"] for f in check_plan(bh, face))
    # the sample take's flow and logo_cluster (backlog 2026-10-07): a flow in the 21%-tall band above the head
    # renders small and pushed right (check.py render FAILed it at +5.6%), so the plan check FAILs it too and
    # points at the plan; as plan.py now lays it out, a full-frame scene, it passes
    fp = {"nodes": [{"label": "jev", "src": "images/logo-typesafe.png"}], "tasks": [{"text": "small task"}, {"text": "harder", "heavy": True}],
          "split": [{"label": "haiku", "src": "images/logo-claude.svg"}, {"label": "opus", "src": "images/logo-claude.svg"}]}
    fl = {**plan, "cards": [{"anim": {"type": "flow", "props": fp}, "start": 0.5, "end": 3, "trigger_word": "task",
                             "box": [4, 10, 92, 21.2], "layout": "box"}]}
    bad = [f for f in check_plan(fl, face) if f["level"] == "FAIL" and "'task'" in f["what"]]
    assert bad and "% of the width" in bad[0]["what"] and bad[0]["fix"].startswith("plan again") and ".tsx" not in bad[0]["fix"], bad
    fl["cards"][0].update(box=[0, 0, 100, 100], layout="scene")
    assert not any(f["level"] == "FAIL" and "'task'" in f["what"] for f in check_plan(fl, face)), check_plan(fl, face)
    # logo_cluster: logos laid round the head (no band) FAIL on vertical; plan.py's centred band passes, one logo does not
    lc = {**plan, "cards": [{"anim": {"type": "logo_cluster", "props": {"logos": [{"src": "a"}, {"src": "b"}]}}, "start": 0.5,
                             "end": 2, "trigger_word": "l", "box": [0, 0, 100, 100]}]}
    assert any(f["level"] == "FAIL" and "'l'" in f["what"] for f in check_plan(lc, face))
    lc["cards"][0]["anim"]["props"].update(band=[17, 83], size=20)
    assert not any(f["level"] == "FAIL" and "'l'" in f["what"] for f in check_plan(lc, face)), check_plan(lc, face)
    lc["cards"][0]["anim"]["props"]["logos"] = [{"src": "a"}]
    assert any(f["level"] == "FAIL" and "'l'" in f["what"] for f in check_plan(lc, face))
    # an overlay in the band above the head may span 4-96% and start 10% down (plan.free_regions)
    band = {**plan, "cards": [{"src": "images/a.png", "start": 0.5, "end": 2, "trigger_word": "a", "box": [4, 10, 92, 20], "layout": "box"}]}
    assert not any(f["level"] == "FAIL" and "'a'" in f["what"] for f in check_plan(band, face)), check_plan(band, face)
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
    # the creator's hook target: her winners show a graphic by 0.0 s; the first card lands at 0.6 s here
    hk = {**band, "targets": {"first_graphic_s": 0.0, "control_first_graphic_s": 4.3}}
    assert any("winners show one by 0.0 s" in f["what"] for f in check_plan(hk, face))
    hk["targets"]["first_graphic_s"] = 1.0
    assert not any("winners" in f["what"] for f in check_plan(hk, face))
    # numbers on a built card are the speaker's: "40%" said as "forty" passes, an invented "3x" fails
    talk = {**plan, "captions": {"style": {"y_pct": 68}, "chunks": [{"text": "it grew forty two percent in ten days", "words": []}]},
            "cards": [{"anim": {"type": "arrow_callout", "props": {"text": "42% in 10 days"}}, "trigger_word": "grew", "start": 0},
                      {"anim": {"type": "chat", "props": {"messages": [{"text": "3x faster"}]}}, "trigger_word": "it", "start": 1},
                      {"anim": {"type": "social_post", "props": {"text": "99 likes"}}, "trigger_word": "days", "start": 2}]}
    assert [(c["trigger_word"], n) for c, n in unsaid_numbers(talk)] == [("it", "3")], unsaid_numbers(talk)
    # a sticker's crop never cuts a line of text: the default trim into a tight capture fails, plan.py's fix passes
    import plan as pl
    lines = [[12, 14, 2430, 100], [12, 150, 1500, 100]]
    stk = {**band, "cards": [{"src": "images/s.png", "format": "sticker", "size": [2460, 260], "lines": lines, "start": 0.5,
                              "end": 2, "trigger_word": "s", "box": [4, 10, 92, 20], "layout": "box"}]}
    assert any("cuts 2 line" in f["what"] for f in check_plan(stk, face)), check_plan(stk, face)
    fixed = pl.with_formats([{k: v for k, v in stk["cards"][0].items()}], [])[0]
    stk["cards"][0]["props"] = fixed["props"]
    assert not any("cuts" in f["what"] for f in check_plan(stk, face)), (fixed["props"], check_plan(stk, face))
    # a capture on vertical reads on a phone: the audit's two browser captures, planned as boxes about a fifth
    # of the frame tall, render their text at 27 and 19 px x-height and FAIL; plan.py cuts each to its evidence
    cap1 = {"src": "images/capture-1-jev.png", "size": [2000, 1434], "format": "browser", "props": {"url": "https://a.b"},
            "lines": [[12, 14, 194, 42], [766, 14, 159, 42], [704, 118, 369, 28], [884, 172, 233, 32], [767, 212, 465, 32],
                      [704, 402, 422, 32], [762, 460, 491, 32], [823, 664, 300, 58], [786, 705, 372, 58], [310, 763, 1360, 212],
                      [206, 914, 1568, 212], [310, 1064, 1360, 212], [196, 1215, 1553, 212]],
            "start": 0.5, "end": 2.5, "trigger_word": "jev", "box": [4, 10, 92, 21.5], "layout": "box"}
    cap2 = {"src": "images/capture-2-claude.png", "size": [2000, 1400], "format": "browser", "props": {"url": "https://c.d"},
            "lines": [[1332, 53, 196, 38], [1617, 53, 153, 38], [711, 232, 578, 152], [694, 364, 612, 152], [645, 543, 709, 56],
                      [846, 749, 356, 42], [614, 1030, 772, 30], [695, 1066, 610, 30], [848, 1229, 377, 42]],
            "start": 3.0, "end": 5.0, "trigger_word": "claude", "box": [4, 10, 92, 21.7], "layout": "box"}
    small = {**band, "cards": [json.loads(json.dumps(cap1)), json.loads(json.dumps(cap2))]}
    assert sum("x-height" in f["what"] for f in check_plan(small, face) if f["level"] == "FAIL") == 2, check_plan(small, face)
    hook = [f for f in check_plan(small, face) if "on the hook" in f["what"]]
    assert len(hook) == 1 and "'jev'" in hook[0]["what"], hook          # cap1 is up at 0.5 s with no find; cap2 lands at 3.0 s
    small["cards"] = pl.readable_captures(small["cards"], "9:16")
    # the jev page's kicker (58 px lines over 212 px headline lines) is left out of the sticker, not shrunk into it
    tiny = [json.loads(json.dumps(small["cards"][0]))]
    tiny[0]["props"]["crop"] = [196, 600, 1578, 600]
    assert any("under 28 px x-height beside" in f["what"] for f in check_plan({**band, "cards": tiny}, face))
    assert not pl.small_lines(small["cards"][0], "9:16"), (small["cards"][0]["props"], pl.small_lines(small["cards"][0], "9:16"))
    withfind = {**band, "cards": [{**cap1, "marks": [{"kind": "highlight", "find": "System One", "rect": [310, 763, 900, 212]}]}]}
    assert not any("on the hook" in f["what"] for f in check_plan(withfind, face))
    # plan.py keeps a mark's "find" in the plan (it timed the mark and dropped it before, so this check never saw it)
    planned = pl.scene_parts([{**cap1, "marks": [{"kind": "highlight", "find": "System One", "at_word": "jev"}]}],
                             [{"text": "jev", "start": 0.6, "end": 0.9}], None)
    assert not any("on the hook" in f["what"] for f in check_plan({**band, "cards": planned}, face))
    assert [c["format"] for c in small["cards"]] == ["sticker", "sticker"] and "url" not in small["cards"][0]["props"], small["cards"]
    assert all(pl.capture_xh(c, "9:16") >= READ_XH for c in small["cards"]), [pl.capture_xh(c, "9:16") for c in small["cards"]]
    assert not [f for f in check_plan(small, face) if "x-height" in f["what"] or "cuts" in f["what"]], check_plan(small, face)
    # pacing: the sample's 11.5 s with no card (10.6-22.1 s). Named there ("Jev"): WARN. Nothing named but the
    # frame changing every 3 s: fine. Nothing named and no change for 11 s: WARN
    pc = {**plan, "durationInFrames": 30 * 30, "zooms": [{"start": t, "end": t + 3, "scale": 1.18, "kind": "punch", "ease_s": 0}
                                                         for t in (10.6, 16.6)],
          "cards": [{**plan["cards"][0], "start": 0.5, "end": 10.6}, {**plan["cards"][0], "start": 22.1, "end": 30}]}
    gaps = lambda f: [x for x in f if "no card for" in x["what"]]
    assert gaps(check_plan(pc, face, named=[(14.0, "Jev")])) and "'Jev' at 14.0 s" in gaps(check_plan(pc, face, named=[(14.0, "Jev")]))[0]["what"]
    assert not gaps(check_plan(pc, face)), gaps(check_plan(pc, face))
    assert gaps(check_plan({**pc, "zooms": []}, face))
    print("demo ok")


def brand():
    """The profile's brand kit (a tell the user's own brand names is only a warning)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
        from ai_editor import profile
        return profile.load().get("brand") or {}
    except Exception:
        return {}


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["plan", "render"])
    ap.add_argument("edit")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--style", help="style.json: its pace sets how long a static stretch may run; render compares its rhythm")
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
        named = [(x["start"], n) for x in rd("beats.json") or [] for n in x.get("names") or []]
        found = check_plan(plan, face, cut_points(edit), static_s, rd("visuals.json"), brand(), named)
        extra = {"static_s": static_s}
    else:
        video = edit / f"render{tag}.mp4"
        if not video.exists():
            sys.exit(f"ERROR: {video} missing; render first")
        found, extra["cards"] = check_render(edit, plan, video)
        import quality   # every frame, the settled cards, the audio, the files: quality.py
        style = json.loads(Path(a.style).read_text()) if a.style else None
        if style_note(a.style, style):
            print(style_note(a.style, style))
        more, q = quality.run(edit, plan, video, plan_path, style, cut_points(edit), brand())
        found += more
        for k, v in q.pop("cards", {}).items():
            extra["cards"].setdefault(k, {}).update(v)
        extra.update(q)
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
            # names the edit uses on purpose, and the approved cut text captions take a misheard name from
            known = {s.lower() for s in re.findall(r"[\w']+", json.dumps([rd("visuals.json") or [], rd("words.json") or [],
                                                                        rd("fixes.json") or {}]))}
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
