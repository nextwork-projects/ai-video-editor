#!/usr/bin/env python3
"""A website in, a product video out: its real UI, its own brand, its own words.

    python3 product.py crawl  URL DIR [--app URL] [--cookies FILE] [--include URLS]   crawl.mjs: site.json, pages, fonts, logo
    python3 product.py pages  DIR                                     pages.md: every crawled page, compact, to find the use cases in
    python3 product.py record DIR [--mobile] [--cookies FILE]         record.mjs: flows.json -> real click-throughs in flows/
    python3 product.py music  DIR --url URL [--start S --end S] --rights own|cc|licensed|unsure [--credit "..."]
    python3 product.py copy   DIR                                     the site's phrases to pick beats from (Jev ranks them with a key)
    python3 product.py plan   DIR --style linear|apple|stripe|arc|raycast --aspect 16:9|9:16|1:1 [--length 30]
                              [--music generated|eleven|none|audio/F] [--sfx subtle|none] [--vo F] [--story F --tag T]
    python3 product.py animatic DIR --plan plan-linear-16x9.json      start/middle/end of every beat, captioned: approve before rendering
    python3 product.py stills DIR --plan plan-apple-16x9.json         settled frames + stills-<tag>/sheet.png
    python3 product.py render DIR --plan plan-apple-16x9.json [--draft | --modal | --lambda]
    python3 product.py check  DIR --plan plan-apple-16x9.json         check-<tag>.json; exit 1 on a FAIL
    python3 product.py share  DIR                                     share.txt: caption + alt text
    python3 product.py tts    DIR --text "..." [--voice ID]           audio/vo.mp3 (ElevenLabs key only)
    python3 product.py meter  VIDEO                                   smoothness: speed, jerk, judder, stops, carry across cuts
    python3 product.py approve DIR --plan plan-linear-16x9.json       after the user chose Approve on the animatic: render needs it
    python3 product.py demo                                           self-check, no network

DIR holds site.json (crawl) and story.json (the beats, written from `copy`; references/story.md).
Renders go through style-edit's edit.py (same renderer, same laptop / Modal / Lambda paths).
"""
import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[2]
STYLE = PLUGIN / "skills" / "style-edit" / "scripts"
sys.dont_write_bytecode = True
sys.path[:0] = [str(STYLE), str(PLUGIN / "lib")]
import gates  # noqa: E402  (the steps a film cannot skip: brief, approval, licence, story order)

SIZES = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
FPS = 30
END_S = {"apple": 3.2, "linear": 3.6, "stripe": 2.6, "arc": 2.2, "raycast": 4.0}
STYLES = list(END_S)
STYLE_TILT = {"linear": True}
STYLE_CUT = {"linear": "blur", "raycast": "blur"}
PACE = {"arc": 0.7, "raycast": 1.2}    # measured shot medians against Linear's (references/style.md)
WEIGHT = {"page": 1.0, "lift": 1.15, "media": 1.3, "flow": 1.6, "keys": 1.4, "macro": 1.0, "stack": 1.0, "push": 0.8,
          "split": 1.4, "orbit": 1.0, "whip": 0.7, "grid": 1.0, "type": 0.6}
ZOOM_S = 1.15          # a push-in or pull-out on a recording takes 0.9-1.4 s, eased both ends (owner, 2026-10-06)
MAX_WORDS = 5          # owner rule: about five words a card
READ_S = 0.3           # seconds per word once settled, plus the entrance (brag's reading floor)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[‘’]", "'", s or "")).strip().lower()


def load(d, name):
    return json.loads((Path(d) / name).read_text())


def tag_of(variant, aspect):
    return f"{variant}-{aspect.replace(':', 'x')}"


# ---------------------------------------------------------------- copy: the only words allowed on screen

def site_text(site):
    """Every phrase the site says: home page, app page, and the inner pages crawl.mjs read."""
    return [c["text"] for c in site["copy"]] + [site.get("title") or "", site.get("description") or ""] + \
        [c["text"] for c in (site.get("app") or {}).get("copy", [])] + \
        [x for p in site.get("pages", []) for x in [p.get("title") or "", p.get("description") or ""]
         + [ln["text"] for ln in p.get("lines", [])] + [c["text"] for c in p.get("controls", [])]]


def flow_text(d):
    """Words the recordings saw on the live site: each step's target text and what was on screen at the end."""
    out = []
    for f in sorted((Path(d) / "flows").glob("*.json")) if d else []:
        if f.name == "whoami.json":
            continue
        m = json.loads(f.read_text())
        out += [x["label"][5:] for x in m.get("steps", []) if (x.get("label") or "").startswith("text=")] + m.get("copy", [])
    return out


def is_site_phrase(text, site, d=None):
    """On-screen words must be a run of the site's own copy (case and spacing aside): its pages, or what its
    recordings showed."""
    t = norm(text).rstrip(".")
    return bool(t) and any(t in norm(s) for s in site_text(site) + flow_text(d))


def candidates(site):
    """Phrases worth a beat: headings, short lines and button labels, not navigation."""
    out, seen = [], set()
    for c in site["copy"]:
        t, n = c["text"], len(c["text"].split())
        if not 1 < n <= 14 or len(t) > 110 or norm(t) in seen or c["rect"][1] < 90:
            continue
        seen.add(norm(t))
        out.append({"text": t, "tag": c["tag"], "y": c["rect"][1],
                    "el": next((e["id"] for e in site["elements"] if inside(c["rect"], e["rect"])), None)})
    return out


def inside(r, box, slack=8):
    return r[0] >= box[0] - slack and r[1] >= box[1] - slack and r[0] + r[2] <= box[0] + box[2] + slack and \
        r[1] + r[3] <= box[1] + box[3] + slack


def cmd_copy(d):
    site = load(d, "site.json")
    cands = candidates(site)
    from ai_editor import jev, keys
    key, _ = keys.get("typesafe")
    if key and cands:
        qs = {f"c{i}": jev.noul("Is this phrase a concrete statement of what the product does or why someone would want it, "
                                "strong enough to sit on screen in a launch video?", phrase=c["text"], product=site.get("title", ""))
              for i, c in enumerate(cands)}
        ans = jev.ask(f"Landing page copy of {site['domain']}.", qs, key=key, log_dir=d)
        for i, c in enumerate(cands):
            c["jev"] = round(jev.yes(ans[f"c{i}"]), 3)
        cands.sort(key=lambda c: -c["jev"])
        print(f"ranked by Jev (${jev.ask.last_usage['cost_usd']:.4f})")
    else:
        print("no TypeSafe key: pick the beats yourself from this list")
    for i, c in enumerate(cands[:60]):
        print(f"{i:2}  {c.get('jev', ''):5}  {c['tag']:6} y={c['y']:<5} {c['el'] or '':6} {c['text']}")
    print("\nelements (focus / lift / click targets):")
    for e in site["elements"]:
        print(f"  {e['id']:6} {e['kind']:8} {str(e['rect']):26} {(e.get('text') or '')[:60]}")
    for m in site.get("media", []):
        print(f"  media  {m['src']}  (the page's own video)")


# ---------------------------------------------------------------- use cases: what the site says it is for

def cmd_pages(d):
    """pages.md: a compact read of every crawled page (never raw HTML) to find the use cases in. With a
    TypeSafe key Jev also ranks the headings by how plainly each names a job a user does with the product."""
    d = Path(d)
    site = load(d, "site.json")
    pages = [{"id": "home", "url": site["url"], "kind": "home", "title": site.get("title"), "description": site.get("description"),
              "lines": [{"tag": c["tag"], "text": c["text"]} for c in site["copy"] if c["tag"] in ("h1", "h2", "h3", "p")],
              "controls": [], "media": site.get("media", [])}] + site.get("pages", [])
    jobs = []
    from ai_editor import jev, keys
    key, _ = keys.get("typesafe")
    heads = list(dict.fromkeys((h["text"], p["url"]) for p in pages for h in p["lines"] if h["tag"] in ("h1", "h2", "h3")
                               and 2 <= len(h["text"].split()) <= 14))[:120]
    if key and heads:
        qs = {f"h{i}": jev.noul("Does this line name a concrete job a user does with the product (a flow, not a slogan)?",
                                line=t, product=site.get("title", "")) for i, (t, _) in enumerate(heads)}
        ans = jev.ask(f"Website of {site['domain']}.", qs, key=key, log_dir=d)
        jobs = sorted(((round(jev.yes(ans[f"h{i}"]), 3), t, u) for i, (t, u) in enumerate(heads)), reverse=True)[:25]
    brief = json.loads((d / "brief.json").read_text()) if (d / "brief.json").exists() else {}
    out = [f"# {site['domain']}: {len(pages)} pages read", ""]
    if brief:
        out += ["## The brief (the user's answers; use-cases.md marks these [brief])", ""] + \
            [f"- {k}: {v}" for k, v in brief.items()] + [""]
    if jobs:
        out += ["## Lines Jev reads as jobs (yes-probability)", ""] + [f"- {p}  {t}  ({u})" for p, t, u in jobs] + [""]
    for p in pages:
        out += [f"## {p['id']} [{p['kind']}] {p['url']}", f"title: {p.get('title') or ''}", f"description: {p.get('description') or ''}"]
        if p.get("shot"):
            out.append(f"screenshot: {p['shot']}")
        out += [f"  {ln['tag']}: {ln['text'][:200]}" for ln in p["lines"][:28]]
        ctl = [c for c in p.get("controls", []) if c["kind"] in ("button", "tab", "input", "summary", "a")][:24]
        if ctl:
            out.append("  controls: " + " | ".join(f"{c['kind']}:{c['text'][:40]}" for c in ctl))
        if p.get("media"):
            out.append("  media: " + " ".join(m.get("src") or m.get("from", "") for m in p["media"]))
        out.append("")
    (d / "pages.md").write_text("\n".join(out))
    print(f"{d / 'pages.md'}: {len(pages)} pages" + (f", {len(jobs)} lines ranked by Jev" if jobs else ", no TypeSafe key: read it and rank the use cases yourself"))


# ---------------------------------------------------------------- music: the beat grid, for cuts on the beat

def beats(path):
    """Beat times (s) of a track: spectral-flux onsets, tempo by autocorrelation (70-180 BPM), best phase.
    [] without numpy or on a track with no clear pulse."""
    try:
        import numpy as np
    except ImportError:
        return []
    sr, hop = 22050, 512
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < sr * 4:
        return []
    n = (len(x) - 2048) // hop
    frames = np.stack([x[i * hop:i * hop + 2048] * np.hanning(2048) for i in range(n)])
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)))
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(1)
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    fr = sr / hop
    lags = np.arange(int(fr * 60 / 180), int(fr * 60 / 70))
    ac = np.array([np.dot(flux[:-l], flux[l:]) for l in lags])
    lag = int(lags[ac.argmax()])
    phase = max(range(lag), key=lambda p: flux[p::lag].sum())
    return [round((phase + k * lag) / fr, 3) for k in range(int((len(flux) - phase) / lag))]


def snap(t, grid, tol=0.35):
    near = min(grid, key=lambda b: abs(b - t)) if grid else t
    return near if abs(near - t) <= tol else t


# ---------------------------------------------------------------- plan

def brand_of(site):
    b = site["brand"]
    d = b["display"]
    px = re.match(r"(-?[\d.]+)px", str(d.get("letter_spacing", "")))
    track = float(px.group(1)) / d["size_px"] if px and d.get("size_px") else 0.0
    muted = b["body_ink"] if norm(b["body_ink"]) != norm(b["ink"]) else mix(b["ink"], b["ground"], 0.45)
    return {"ground": b["ground"], "ink": b["ink"], "muted": muted, "accent": b["accent"], "dark": b["dark"],
            "radius_px": b["radius_px"], "display": {"family": d["family"], "weight": int(d.get("weight") or 600),
                                                       "tracking_em": round(max(-0.05, min(0.02, track)), 3)},
            "body": {"family": b["body"]["family"], "weight": int(b["body"].get("weight") or 400)}, "fonts": b["fonts"]}


def mix(a, b, p):
    ca, cb = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * p):02X}" for x, y in zip(ca, cb))


def logo_of(site, d):
    lg = site.get("logo") or {}
    out = {"word": lg.get("word") or None}
    src = lg.get("src")
    if src and (Path(d) / src).exists():
        out["src"] = src
        if src.endswith(".svg"):
            t = (Path(d) / src).read_text(errors="ignore")
            vb = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', t)
            out["aspect"] = round(float(vb.group(1)) / float(vb.group(2)), 3) if vb else 1
        else:
            w, h = lg.get("png_size") or [1, 1]
            out["aspect"] = round(w / h, 3)
    if not out.get("src") and not out["word"]:
        out["word"] = site.get("title", "").split("|")[0].split(" - ")[0].strip() or site["domain"]
    return out


def page_extent(site):
    t = site["tiles"][-1]
    return t["y"] + site["viewport"][1]


def rect_of(focus, site):
    vw, vh = site["viewport"]
    if focus in (None, "hero"):
        return [0, 0, vw, vh]
    if isinstance(focus, list):
        return focus
    el = next((e for e in site["elements"] if e["id"] == focus), None)
    if not el:
        sys.exit(f"ERROR: story names {focus!r}, which is not in site.json elements (product.py copy lists them)")
    return el["crop"] if "crop" in el else el["rect"]


def scroll_for(r, site):
    vh = site["viewport"][1]
    return max(0, min(page_extent(site) - vh, r[1] + r[3] / 2 - vh * 0.48))


def grow(r, k, site=None):
    cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
    return [cx - r[2] * k / 2, cy - r[3] * k / 2, r[2] * k, r[3] * k]


def overview(scroll, site):
    vw, vh = site["viewport"]
    return [0, scroll, vw, vh]


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    j = json.loads(out or "{}")
    s = (j.get("streams") or [{}])[0]
    return s.get("width"), s.get("height"), float(j.get("format", {}).get("duration") or 0)


def seekable(d, src):
    """The page's video as H.264 with a keyframe every 15 frames: webm and long-GOP files stall the
    renderer's frame extraction (ENOBUFS, then a failed render)."""
    if src.endswith(".seek.mp4"):
        return src
    out = str(Path(src).with_suffix("")) + ".seek.mp4"
    if not (Path(d) / out).exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(Path(d) / src), "-an", "-c:v", "libx264", "-crf", "18",
                        "-preset", "veryfast", "-g", "15", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                        str(Path(d) / out)], check=True)
    return out


def fixed_len(s):
    """A flow plays at its own speed: its shot is as long as the stretch of recording it shows."""
    if s["kind"] in ("flow", "keys"):
        return s.get("dur") or max(1.5, s["to"] - s.get("from", 0)) if "to" in s else s.get("dur")
    return s.get("dur")


def durations(story, length, variant):
    """Seconds per shot: the end card fixed, flows at their own length, the rest shared by weight, each at
    least its reading time."""
    shots = story["shots"]
    body = [s for s in shots if s["kind"] != "end"]
    end = END_S.get(variant, 3.4) if any(s["kind"] == "end" for s in shots) else 0
    pace = PACE.get(variant, 1.0)
    floor = [max(1.6 if variant == "arc" else 2.2, 1.0 + READ_S * len((s.get("text") or "").split())
                 + (1.2 if s.get("click") or s["kind"] == "lift" else 0)) for s in body]
    fixed = [fixed_len(s) for s in body]
    free = (length - end - sum(f for f in fixed if f)) / max(1e-6, sum(WEIGHT[s["kind"]] for s, f in zip(body, fixed) if not f))
    out = [f if f else max(fl, free * WEIGHT[s["kind"]] * pace) for s, f, fl in zip(body, fixed, floor)]
    rest = [d for d, f in zip(out, fixed) if not f]
    if rest:
        k = (length - end - sum(f for f in fixed if f)) / sum(rest)
        out = [d if f else max(fl, d * k) for d, f, fl in zip(out, fixed, floor)]
    return out, end


def screen(ref, d):
    """A full screen for stack, push and whip: tile-N, page-N, flow:<id>@<s> (a frame of a recording), or a path."""
    d = Path(d)
    if ref.startswith("tile-"):
        rel = f"images/{ref}.jpg"
    elif ref.startswith("page-"):
        rel = f"pages/{ref}.jpg"
    elif ref.startswith("flow:"):
        fid, at = ref[5:].split("@")
        rel = f"images/frame-{fid}-{float(at):.2f}.jpg"
        if not (d / rel).exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", at, "-i", str(d / "flows" / f"{fid}.mp4"), "-frames:v", "1",
                            "-q:v", "2", str(d / rel)], check=True)
    else:
        rel = ref
    w, h, _ = probe(d / rel)
    return {"src": rel, "size": [w or 16, h or 10]}


def el_of(site, ref):
    el = next((e for e in site["elements"] if e["id"] == ref), None)
    if not el:
        sys.exit(f"ERROR: story names {ref!r}, which is not in site.json elements (product.py copy lists them)")
    return {k: el[k] for k in ("src", "size", "crop", "hover_src") if k in el}


def flow_ref(d, s, dur, tight=False):
    """A recording in a shot: the camera follows the cursor, Screen Studio style. Wide until the hand is about
    to act, then a push onto what it acts on (0.45 s early), out again when nothing happens for a while."""
    meta = json.loads((Path(d) / "flows" / f"{s['flow']}.json").read_text())
    vw, vh = meta["viewport"]
    t0 = s.get("from", 0.0)
    # "wide": the framing between actions (a share of the viewport, centred on "wide_at" [x, y]); a sparse
    # dark site wants it tighter than the whole page
    ww = vw * s.get("wide", 1.0)
    cx, cy = s.get("wide_at", [vw / 2, vh / 2])
    wide = [max(0, min(vw - ww, cx - ww / 2)), max(0, min(vh - ww * vh / vw, cy - ww * vh / vw / 2)), ww, ww * vh / vw]
    keys = [{"t": 0, "scroll": 0, "rect": wide}]
    acts = [x for x in meta["steps"] if x.get("rect") and x["kind"] in ("click", "type", "hover", "move") and t0 <= x["t"] - 0.2 < t0 + dur]
    for i, x in enumerate(acts):
        cx, cy = x["rect"][0] + x["rect"][2] / 2, x["rect"][1] + x["rect"][3] / 2
        w = max(x["rect"][2] * 1.6, vw * 0.8) if vh > vw else max(x["rect"][2] * 2.2, vw * s.get("zoom", 0.42 if tight else 0.56))
        h = w * vh / vw
        r = [max(0, min(vw - w, cx - w / 2)), max(0, min(vh - h, cy - h / 2)), w, h]
        at = max(keys[-1]["t"] + ZOOM_S, x["t"] - t0 - 0.45)
        keys += [{"t": round(at - ZOOM_S, 3), "scroll": 0, "rect": keys[-1]["rect"]}, {"t": round(at, 3), "scroll": 0, "rect": r}]
        later = [y for y in meta["steps"] if y["t"] > x["t"] + 0.05]
        nxt = later[0]["t"] - t0 if later else dur
        if later and later[0]["kind"] == "key":
            # a key answers what was typed: hold on it through the press, then out to see the result land
            keys += [{"t": round(nxt + 0.25, 3), "scroll": 0, "rect": r}, {"t": round(nxt + 0.25 + ZOOM_S, 3), "scroll": 0, "rect": wide}]
        elif nxt - (x["t"] - t0) > 2.6:
            keys += [{"t": round(x["t"] - t0 + 1.2, 3), "scroll": 0, "rect": r}, {"t": round(x["t"] - t0 + 1.2 + ZOOM_S, 3), "scroll": 0, "rect": wide}]
    keys = [k for k in keys if k["t"] >= 0]
    keys.append({"t": round(dur, 3), "scroll": 0, "rect": keys[-1]["rect"]})
    keys = sorted({k["t"]: k for k in keys}.values(), key=lambda k: k["t"])
    caps = [{"t": round(x["t"] - t0 + 0.05, 3), "label": x["label"]} for x in meta["steps"] if x["kind"] == "key" and t0 <= x["t"] < t0 + dur]
    out = {"src": meta["src"], "size": meta["size"], "viewport": meta["viewport"], "from": t0,
           "keys": [{**k, "rect": [round(v, 1) for v in k["rect"]]} for k in keys]}
    if caps and (tight or s.get("keycaps", True)):
        out["keycaps"] = caps
    return out, meta


def dark_frame(video, t):
    """Is the recording dark at t (a dark-mode app on a light site)? Mean luminance under 0.35."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=64:36,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    return bool(raw) and sum(raw) / len(raw) / 255 < 0.35


def vertical_shot(s, d):
    """A 9:16 film is filled by the product: a shot's "vertical" fields replace its own, and every recording
    swaps to its phone-layout take (record.mjs --mobile, flows/<id>-m) when there is one."""
    s = {**s, **s.get("vertical", {})}
    s.pop("vertical", None)
    m = lambda fid: fid + "-m" if not fid.endswith("-m") and (Path(d) / "flows" / f"{fid}-m.json").exists() else fid
    if s.get("flow"):
        s["flow"] = m(s["flow"])
    if s.get("flows"):
        s["flows"] = [{**f, "flow": m(f["flow"])} for f in s["flows"]]
    for k in ("screens",):
        if s.get(k):
            s[k] = [f"flow:{m(r[5:].split('@')[0])}@{r.split('@')[1]}" if r.startswith("flow:") else r for r in s[k]]
    if isinstance(s.get("to"), str) and s["to"].startswith("flow:"):
        s["to"] = f"flow:{m(s['to'][5:].split('@')[0])}@{s['to'].split('@')[1]}"
    return s


def rect_any(ref, site):
    return ref if isinstance(ref, list) else rect_of(ref, site)


def build_plan(d, variant, aspect, length=None, music="generated", vo=None, sfx="subtle", own=None, story_name="story.json", tag=None, fps=FPS):
    d = Path(d)
    site, story = load(d, "site.json"), load(d, story_name)
    tag = tag or tag_of(variant, aspect)
    if "beats" in story:
        return build_journey(d, site, story, variant, aspect, music, vo, sfx, own, story_name, tag, max(fps, 60), length)
    length = length or 30
    if aspect == "9:16":
        story = {**story, "shots": [v for v in (vertical_shot(s, d) for s in story["shots"]) if not v.get("skip")]}
    W, H = SIZES[aspect]
    problems = check_story(story, site, length, d)
    if any(p.startswith("FAIL") for p in problems):
        sys.exit("\n".join(problems))
    for p in problems:
        print(p)
    if vo:
        length = max(length, probe(d / vo)[2] + END_S.get(variant, 3.4))
    durs, end_s = durations(story, length, variant)
    import sound
    mood = variant if variant in sound.MOODS else "linear"
    # cuts land on the beat: every shot end snaps to the score's grid (an own track: its detected beats)
    grid = beats(d / own) if own and music == "own" else (sound.beat_grid(mood, length + 8) if music == "generated" else [])
    apple = variant == "apple"
    tilt = STYLE_TILT.get(variant, False)
    shots, t, last, cues = [], 0.0, None, []
    body = [s for s in story["shots"] if s["kind"] != "end"]
    for i, (s, dur) in enumerate(zip(body, durs)):
        beat = (grid[1] - grid[0]) if len(grid) > 1 else 0.5
        start, end = t, snap(t + dur, grid, beat * 0.51) if grid else t + dur
        if fixed_len(s) and end - start > dur + 0.02:      # never past the end of a recording
            end = max(start + beat, end - beat)
        dur = end - start
        out = {"kind": s["kind"], "start": round(start, 3), "end": round(end, 3)}
        if s.get("text"):
            out["text"] = s["text"]
        k = s["kind"]
        if k == "media":
            src = seekable(d, s.get("src") or (site.get("media") or [{}])[0].get("src"))
            mw, mh, _ = probe(d / src)
            out["media"] = {"src": src, "size": [mw or 16, mh or 9]}
            last = None
        elif k in ("flow", "keys"):
            out["flow"], meta = flow_ref(d, s, dur, tight=k == "keys")
            if dark_frame(d / meta["src"], s.get("from", 0) + dur / 2) != site["brand"]["dark"]:
                out["tone"] = "dark" if not site["brand"]["dark"] else "light"   # words and scrim follow the recording, not the site's ground
            if tilt and not meta.get("mobile") and aspect != "9:16":
                out["tilt"] = [0.5, 0.18]
            t0 = s.get("from", 0.0)
            for x in meta["steps"]:
                at = start + x["t"] - t0
                if not start <= at < end:
                    continue
                if x["kind"] == "click":
                    cues.append({"t": round(at + 0.25, 3), "kind": "click"})
                elif x["kind"] == "key":
                    cues.append({"t": round(at + 0.02, 3), "kind": "click"})
                elif x["kind"] in ("type", "write"):
                    for j in range(len(x["label"] or "")):
                        tt = at + (0.6 if x["kind"] == "type" else 0) + j / 9
                        if tt < end:
                            cues.append({"t": round(tt, 3), "kind": "tick"})
            last = None
        elif k == "macro":
            out["macro"] = {"a": rect_any(s["a"], site), "b": rect_any(s["b"], site), "at": round(dur * 0.45, 3)}
        elif k in ("stack", "whip"):
            out["screens"] = [screen(r, d) for r in s["screens"]]
            if k == "whip":
                cues.append({"t": round(start + dur * 0.45, 3), "kind": "whoosh"})
        elif k == "push":
            out["push"] = {"rect": rect_any(s.get("el") or s.get("focus"), site), "to": screen(s["to"], d)}
            cues.append({"t": round(start + dur * 0.92, 3), "kind": "whoosh"})
        elif k == "split":
            pair = []
            for f in s["flows"]:
                ref, _ = flow_ref(d, f, dur)
                ref.pop("keycaps", None)
                pair.append(ref)
            out["pair"] = pair
        elif k == "orbit":
            out["orbit"] = el_of(site, s["el"])
        elif k == "grid":
            out["grid"] = [el_of(site, e) for e in s["els"]]
        elif k == "type":
            for j in range(len(s.get("text", ""))):
                if j % 2 == 0 and start + 0.3 + j / 16 < end:
                    cues.append({"t": round(start + 0.3 + j / 16, 3), "kind": "tick"})
        else:   # page, lift
            target = rect_of(s.get("el") if k == "lift" else s.get("focus"), site)
            sc = scroll_for(target, site) if s.get("focus") not in (None, "hero") or k == "lift" else 0
            focus = target if s.get("focus") not in (None, "hero") or k == "lift" else overview(0, site)
            cont = apple and last is not None and k == "page"
            h1 = next((e for e in site["elements"] if e["kind"] == "heading" and e["rect"][1] < site["viewport"][1]), None)
            if apple:
                k0 = last if cont else {"t": 0, "scroll": sc, "rect": overview(sc, site) if k == "page" else grow(focus, 1.6)}
                k0 = {**k0, "t": 0}
                arrive = dur * (0.55 if k == "page" else 0.3)
                keys = [k0, {"t": round(dur * 0.12 if not cont else 0, 3), "scroll": k0["scroll"], "rect": k0["rect"]},
                        {"t": round(arrive, 3), "scroll": sc, "rect": focus}, {"t": round(dur, 3), "scroll": sc, "rect": grow(focus, 0.93)}]
                if i == 0 and s.get("focus") in (None, "hero"):
                    # the opening shows the whole page, then pushes into the headline (Apple: ~3x over about a second)
                    goal = [h1["rect"][0] - 40, h1["rect"][1] - 60, h1["rect"][2] + 80, h1["rect"][3] + 120] if h1 else grow(overview(0, site), 0.6)
                    hs = scroll_for(goal, site) if goal[1] + goal[3] > site["viewport"][1] else 0
                    keys = [{"t": 0, "scroll": 0, "rect": overview(0, site)}, {"t": round(min(1.0, dur * 0.25), 3), "scroll": 0, "rect": overview(0, site)},
                            {"t": round(min(2.6, dur * 0.65), 3), "scroll": hs, "rect": goal}, {"t": round(dur, 3), "scroll": hs, "rect": grow(goal, 0.94)}]
            else:
                keys = [{"t": 0, "scroll": sc, "rect": grow(focus, 1.25)}, {"t": round(dur, 3), "scroll": sc, "rect": grow(focus, 0.95)}]
                if i == 0 and s.get("focus") in (None, "hero") and h1:
                    goal = [h1["rect"][0] - 40, h1["rect"][1] - 60, h1["rect"][2] + 80, h1["rect"][3] + 120]
                    hs = scroll_for(goal, site) if goal[1] + goal[3] > site["viewport"][1] else 0
                    keys = [{"t": 0, "scroll": 0, "rect": overview(0, site)}, {"t": round(dur, 3), "scroll": hs, "rect": goal}]
                if tilt:
                    out["tilt"] = [1, 0.85] if k == "page" else [1, 1]
            out["keys"] = [{**kk, "rect": [round(v, 1) for v in kk["rect"]], "scroll": round(kk["scroll"], 1)} for kk in keys]
            last = out["keys"][-1] if k == "page" else None
            if cont:
                out["cut_in"] = "continue"
            if k == "lift":
                el = next(e for e in site["elements"] if e["id"] == s["el"])
                out["lift"] = {"src": el["src"], "size": el["size"], "crop": el["crop"], "at": round(dur * (0.32 if apple else 0.2), 3)}
                cues.append({"t": round(start + out["lift"]["at"] + 0.45, 3), "kind": "whoosh"})
            if s.get("click") and apple:
                el = next((e for e in site["elements"] if e["id"] == s["click"]), None)
                if not el:
                    sys.exit(f"ERROR: click target {s['click']!r} not in site.json")
                x, y, w, h = el["rect"]
                to = [x + w / 2, y + h / 2]
                move = round(dur * 0.4, 3)
                out["cursor"] = {"from": [to[0] + 260, to[1] + 200], "to": to, "move_at": move, "click_at": round(move + 0.95, 3),
                                 "el": {kk: el[kk] for kk in ("src", "size", "crop", "hover_src") if kk in el}}
                cues.append({"t": round(start + move + 0.95, 3), "kind": "click"})
        out.setdefault("cut_in", "blur" if STYLE_CUT.get(variant) == "blur" and shots else "cut")
        shots.append(out)
        t = end
    if end_s:
        shots.append({"kind": "end", "start": round(t, 3), "end": round(t + end_s, 3), "cut_in": "blur" if STYLE_CUT.get(variant) == "blur" else "cut"})
        cues += [{"t": round(t, 3), "kind": "swell"}, {"t": round(t + 0.05, 3), "kind": "hit"}]
        t += end_s
    plan = {"composition": "ProductVideo", "width": W, "height": H, "fps": fps, "durationInFrames": round(t * fps),
            "variant": variant, "story": story_name, "brand": brand_of(site), "url": site["domain"], "logo": logo_of(site, d),
            "page": {"vw": site["viewport"][0], "vh": site["viewport"][1], "tiles": site["tiles"], "height": page_extent(site),
                     "domain": site["domain"]}, "shots": shots, "audio": {}}
    if music != "none" or sfx != "none" or vo:
        (d / "audio").mkdir(exist_ok=True)
        rel = f"audio/mix-{tag}.wav"
        rep = sound.score(d / rel, t, mood, music, sfx, cues=cues, cuts=[s["start"] for s in shots[1:]], end_at=end_s and t - end_s or None,
                          vo=d / vo if vo else None, own=d / own if own else None, eleven_key=keys_get("elevenlabs"))
        if rep:
            plan["audio"] = {"mix": rel}
            plan["sound"] = rep
            print(f"sound: {rep['music']} ({rep['mood']}, {rep['bpm']} BPM), {rep['cues']} cues, {rep['lufs']} LUFS, true peak {rep['true_peak']} dBTP, "
                  f"effects {rep['fx_minus_bed_db']} dB against the music")
    return plan


def build_journey(d, site, story, variant, aspect, music, vo, sfx, own, story_name, tag, fps, length=None):
    """The rendered film (journey.py): beats over UI states, one camera, 60 fps. The framing is checked on
    every frame from the camera path and re-planned until it holds; what still fails stops the plan."""
    import journey
    problems = check_story(story, site, None, d)
    if any(p.startswith("FAIL") for p in problems):
        sys.exit("\n".join(problems))
    for p in problems:
        print(p)
    # the length: the story's, else about 8 s a use case (40 s for five). Result, hook, payoff and travel beats
    # are paced down until it fits; the story, the steps and the per-frame checks stay the same.
    cases = sum(1 for b in story["beats"] if b.get("job") == "action")
    target = gates.target_length(story, length)
    pace, best = 1.0, None
    while pace >= 0.45:
        j = journey.build(d, story, aspect, fps, variant, pace)
        left = journey.replan(j, d=d)
        total = j["durationInFrames"] / fps
        p95, med = journey.plan_speed(j)
        if pace < 1.0 and (p95 > journey.SPEED_BAR[0] or med > journey.SPEED_BAR[1]):
            break               # shorter would be busier than the reference films: smooth beats short
        calm = p95 <= journey.SPEED_BAR[0] and med <= journey.SPEED_BAR[1]
        if not left and (best is None or (calm and total < best[0]["durationInFrames"] / fps)):
            best = (j, left, pace)          # the shortest that passes every frame and stays calm
        if total <= target + 1 and not left:
            break
        pace = round(pace - 0.05, 2)
    j, left, pace = best or (j, left, pace)
    p95, med = journey.plan_speed(j)
    print(f"length: {j['durationInFrames'] / fps:.1f} s (target {target:.0f} s for {cases} use cases, pace {pace}); "
          f"camera speed p95 {p95:.2f}, median {med:.2f} frame diagonals/s (bar {journey.SPEED_BAR[0]}, {journey.SPEED_BAR[1]})")
    j.pop("cursor_raw", None)
    px0, px1 = journey.crop_layers(d, j)
    print(f"states: cut to what the camera shows, {px0 / 1e6:.0f} -> {px1 / 1e6:.0f} megapixels to decode")
    total = j["durationInFrames"] / fps
    plan = {"composition": "ProductVideo", **{k: v for k, v in j.items() if k != "cues"}, "variant": variant, "story": story_name,
            "brand": brand_of(site), "url": site["domain"], "logo": logo_of(site, d), "shots": [],
            "page": {"vw": site["viewport"][0], "vh": site["viewport"][1], "tiles": [], "height": site["viewport"][1], "domain": site["domain"]},
            "audio": {}}
    if music != "none" or sfx != "none" or vo:
        import sound
        mood = variant if variant in sound.MOODS else "linear"
        (d / "audio").mkdir(exist_ok=True)
        rel = f"audio/mix-{tag}.wav"
        rep = sound.score(d / rel, total, mood, music, sfx, cues=j["cues"], cuts=[b["start"] for b in j["beats"][1:]], end_at=j["end"],
                          sections=[(b["start"], b["job"]) for b in j["beats"]],
                          vo=d / vo if vo else None, own=d / own if own else None, eleven_key=keys_get("elevenlabs"))
        if rep:
            plan["audio"] = {"mix": rel}
            plan["sound"] = rep
            print(f"sound: {rep['music']} ({rep['mood']}, {rep['bpm']} BPM), {rep['cues']} cues, {rep['lufs']} LUFS, true peak {rep['true_peak']} dBTP")
    if left:
        plan["framing"] = [{"t": round(t, 2), "what": w} for t, w, _ in left[:40]]
        print(f"FAIL framing: {len(left)} frames still fail after re-planning the camera; first: " +
              "; ".join(f"{t:.2f} s {w}" for t, w, _ in left[:5]))
    else:
        print(f"framing: every frame holds (focus in the safe frame, cursor whole or hidden, nothing past 1:1, text whole or faded, no blank frame), {j['durationInFrames']} frames")
    return plan



def keys_get(name):
    from ai_editor import keys
    return keys.get(name)[0]


# The job a shot does decides the shot (references/story.md "Shots follow the job"): never variety for its own sake.
SHOT_JOBS = {
    "hook": {"page", "type", "flow", "media", "macro"},
    "reveal": {"push", "page", "flow", "media", "stack"},
    "action": {"flow", "keys"},
    "result": {"flow", "macro", "lift", "page"},
    "comparison": {"split"},
    "feature-list": {"grid", "stack"},
    "payoff": {"flow", "page", "orbit", "media"},
    "transition": {"whip", "push"},
    "end": {"end"},
}


def jarring(a, b):
    """Two shots in a row that show the same thing the same way: the same recording over the same stretch, the
    same component, or the same screen. A recording carried on from where the last shot stopped is not."""
    if a.get("kind") != b.get("kind") or a.get("kind") == "end":
        return False
    if a.get("flow") and a.get("flow") == b.get("flow"):
        return not (b.get("from", 0) >= a.get("to", 1e9) - 0.05)
    for k in ("el", "focus", "els", "screens", "text"):
        if a.get(k) is not None and a.get(k) == b.get(k):
            return True
    return False


def check_story(story, site, length=None, d=None):
    """Words on screen: the site's own, at most MAX_WORDS, no emoji, no slop. Shots: the kind the beat's job
    allows (SHOT_JOBS), and no jarring repeat. A story of "beats" (the rendered film) is checked the same way."""
    try:
        from ai_tells import check_copy
    except ImportError:
        check_copy = lambda text, where: []
    out = []
    items = story.get("beats") or story.get("shots", [])
    import journey
    if "beats" in story:
        out += gates.story_order(items)
    for i, s in enumerate(items):
        if "beats" in story:
            if s.get("job") not in journey.JOBS:
                out.append(f"FAIL beat {i}: job {s.get('job')!r} is not one of {', '.join(journey.JOBS)}")
            if i and s.get("flow") and s.get("flow") == items[i - 1].get("flow") and s.get("steps") and s.get("steps") == items[i - 1].get("steps"):
                out.append(f"FAIL beat {i}: repeats beat {i - 1} (the same steps of the same flow)")
        else:
            if s.get("kind") not in WEIGHT and s.get("kind") != "end":
                out.append(f"FAIL shot {i}: kind {s.get('kind')!r} is not one of {', '.join(WEIGHT)}, end")
            job = s.get("job")
            if job and job not in SHOT_JOBS:
                out.append(f"FAIL shot {i}: job {job!r} is not one of {', '.join(SHOT_JOBS)}")
            elif job and s.get("kind") not in SHOT_JOBS[job]:
                out.append(f"FAIL shot {i}: a {s.get('kind')} shot cannot do the {job} job; use {' or '.join(sorted(SHOT_JOBS[job]))}")
            if i and jarring(items[i - 1], s):
                out.append(f"FAIL shot {i}: shows what shot {i - 1} just showed, the same way; carry on from where it stopped or show the next thing")
        t = s.get("text")
        if not t:
            continue
        n = len(t.split())
        if not is_site_phrase(t, site, d):
            out.append(f"FAIL shot {i}: {t!r} is not on the site. On-screen words are a run of the site's own copy (product.py copy)")
        if n > MAX_WORDS + 2:
            out.append(f"FAIL shot {i}: {n} words in {t!r}; at most {MAX_WORDS}, cut it to the strongest run")
        elif n > MAX_WORDS:
            out.append(f"WARN shot {i}: {n} words in {t!r}; about {MAX_WORDS} reads at a glance")
        if EMOJI.search(t):
            out.append(f"FAIL shot {i}: emoji in {t!r}")
        out += [f"WARN shot {i}: {f['tell']} {f['where']} (the site's own words, kept)" for f in check_copy(t, f"shot {i}")]
    if "shots" in story and not any(s.get("job") for s in story["shots"]):
        out.append("WARN no shot names its job: write storyboard.md first and give each shot the job it does (references/story.md)")
    texts = sum(1 for s in items if s.get("text"))
    if items and texts == len([s for s in items if s.get("kind", s.get("job")) != "end"]):
        out.append("WARN every shot has words: leave one or two to the UI alone")
    return out


# ---------------------------------------------------------------- render plumbing (style-edit's edit.py)

def public(d, plan, tag):
    """A folder with only what this render reads."""
    pub = Path(d) / f".render-{tag}"
    pub.mkdir(exist_ok=True)
    for rel in dict.fromkeys(re.findall(r'"((?:images|fonts|media|audio|flows|pages|\.sfx)/[^"]+)"', json.dumps(plan))):
        src = Path(d) / rel
        if not src.exists():
            sys.exit(f"ERROR: {src} missing")
        (pub / rel).parent.mkdir(parents=True, exist_ok=True)
        if not (pub / rel).exists() or (pub / rel).stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, pub / rel)
    return pub


def still_frames(plan):
    if plan.get("journey"):
        import journey
        return journey.stills_at(plan)
    out = {}
    for i, s in enumerate(plan["shots"]):
        a, b = s["start"], s["end"]
        times = {"in": a + 0.5, "mid": (a + b) / 2, "late": b - 0.35}
        if s.get("lift"):
            times["lift"] = a + s["lift"]["at"] + 0.5
        if s.get("cursor"):
            times["click"] = a + s["cursor"]["click_at"]
        for k, v in times.items():
            out[f"{i + 1:02d}-{s['kind']}-{k}"] = min(plan["durationInFrames"] - 1, round(v * plan["fps"]))
    return out


def sheet(stills, out):
    from PIL import Image, ImageDraw, ImageFont
    import sheet as sh
    files = sorted(p for p in Path(stills).glob("*.png") if p.name != "sheet.png")
    with Image.open(files[0]) as im:
        tw, th = im.size
    cols, s = sh.grid(len(files), tw, th)
    w, h = int(tw * s), int(th * s)
    lh = max(14, int(sh.LABEL * w))
    rows = math.ceil(len(files) / cols)
    page = Image.new("RGB", (cols * w + (cols + 1) * sh.GAP, rows * (h + lh) + (rows + 1) * sh.GAP), "#202020")
    dr = ImageDraw.Draw(page)
    try:
        font = ImageFont.load_default(size=max(10, int(lh * 0.7)))
    except TypeError:
        font = ImageFont.load_default()
    for i, f in enumerate(files):
        x, y = sh.GAP + (i % cols) * (w + sh.GAP), sh.GAP + (i // cols) * (h + lh + sh.GAP)
        dr.text((x + 3, y + 1), f.stem, fill="#FFFFFF", font=font)
        with Image.open(f) as im:
            page.paste(im.convert("RGB").resize((w, h), Image.LANCZOS), (x, y + lh))
    page.save(out, optimize=True)
    return out


def venv_py():
    from edit import venv_python
    return venv_python()


def cmd_animatic(d, plan_name):
    """The storyboard before the render: start, middle and end of every beat, rendered at full quality as
    stills (seconds, not minutes), on one sheet with each beat's job and words under it. The user approves
    it in the question box; the storyboard-critic agent reviews it first."""
    import edit
    from PIL import Image, ImageDraw, ImageFont
    d = Path(d).resolve()
    plan_path = d / plan_name
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan-"):]
    edit.sync_renderer()
    pub = public(d, plan, tag)
    outdir = d / f"animatic-{tag}"
    shutil.rmtree(outdir, ignore_errors=True)
    edit.node("stills", pub, plan_path, outdir, *[f"{k}={v}" for k, v in still_frames(plan).items()])
    beats = plan.get("beats") or [{"job": s.get("job") or s["kind"], "text": s.get("text"), "start": s["start"], "end": s["end"]} for s in plan["shots"]]
    files = sorted(p for p in outdir.glob("*.png") if p.name != "sheet.png")
    with Image.open(files[0]) as im:
        tw, th = im.size
    w = 360 if th > tw else 480
    h = int(th * w / tw)
    gap, cap = 10, 58
    rows = [[f for f in files if f.name.startswith(f"{i + 1:02d}-")] for i in range(len(beats))]
    page = Image.new("RGB", (gap + 3 * (w + gap) + 300, gap + len(rows) * (h + cap + gap)), "#161616")
    dr = ImageDraw.Draw(page)
    try:
        big, small = ImageFont.load_default(size=22), ImageFont.load_default(size=16)
    except TypeError:
        big = small = ImageFont.load_default()
    for r, (b, fs) in enumerate(zip(beats, rows)):
        y = gap + r * (h + cap + gap)
        for c, f in enumerate(fs[:3]):
            with Image.open(f) as im:
                page.paste(im.convert("RGB").resize((w, h), Image.LANCZOS), (gap + c * (w + gap), y))
        x = gap + 3 * (w + gap)
        dr.text((x, y + 4), f"{r + 1}. {b['job']}", fill="#FFFFFF", font=big)
        dr.text((x, y + 34), f"{b['start']:.1f}-{b['end']:.1f} s", fill="#9A9A9A", font=small)
        if b.get("text"):
            dr.text((x, y + 58), f"\"{b['text']}\"", fill="#E8C872", font=small)
        dr.text((gap, y + h + 6), "start  /  middle  /  end", fill="#7A7A7A", font=small)
    out = outdir / "sheet.png"
    page.save(out, optimize=True)
    print(f"REVIEW THIS: {out}")
    return out


def cmd_stills(d, plan_name):
    import edit
    d = Path(d).resolve()
    plan_path = d / plan_name
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan-"):]
    edit.sync_renderer()
    pub = public(d, plan, tag)
    outdir = d / f"stills-{tag}"
    shutil.rmtree(outdir, ignore_errors=True)
    edit.node("stills", pub, plan_path, outdir, *[f"{k}={v}" for k, v in still_frames(plan).items()])
    r = subprocess.run([venv_py(), str(HERE / "product.py"), "_sheet", str(outdir)], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


def cmd_render(d, plan_name, draft=False, modal=False, use_lambda=False):
    import edit
    d = Path(d).resolve()
    if gates.need_approval(d, plan_name):
        sys.exit(f"ERROR: {gates.need_approval(d, plan_name)}")
    plan_path = d / plan_name
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan-"):]
    edit.sync_renderer()
    pub = public(d, plan, tag)
    out = d / f"render-{tag}{'-draft' if draft else ''}.mp4"
    if use_lambda:
        edit.node("lambda", pub, plan_path, out, re.sub(r"[^a-z0-9-]+", "-", f"ai-editor-{d.name}-{tag}".lower()))
    elif modal:
        if not edit.modal_ready():
            sys.exit("Modal is not set up on this computer: run the setup skill's Modal step first.")
        edit.render_modal(d, plan_path, pub, out)
    else:
        edit.render_laptop(d, plan_path, pub, out, draft)
    print(out)


# ---------------------------------------------------------------- checks on the render

def cmd_check(d, plan_name):
    """FAIL: a stale render, words not on the site, a ban the site's brand does not own, clipping.
    WARN: long static stretches, low contrast of the words, loudness outside -23..-9 LUFS."""
    import numpy as np
    import cv2
    import quality as q
    import ai_tells as at
    d = Path(d).resolve()
    plan_path = d / plan_name
    plan = json.loads(plan_path.read_text())
    tag = plan_path.stem[len("plan-"):]
    video = d / f"render-{tag}.mp4"
    site = load(d, "site.json")
    found = []
    add = lambda lvl, what, fix="": found.append({"level": lvl, "what": what, "fix": fix})
    if not video.exists():
        sys.exit(f"ERROR: {video} missing: render first")
    for name, secs in q.stale(video, [plan_path, d / plan.get("story", "story.json")]):
        add("FAIL", f"{name} changed {secs} s after the render", "render again")
    for s in check_story(load(d, plan.get("story", "story.json")), site, None, d):
        add(s.split()[0], s.split(" ", 1)[1])
    if plan.get("journey"):
        import journey
        for lvl, what, fix in journey.check_render(d, plan, video):
            add(lvl, what, fix)
        (d / f"check-{tag}.json").write_text(json.dumps(found, indent=1))
        for f in found:
            print(f"{f['level']:4}  {f['what']}" + (f"\n      fix: {f['fix']}" if f["fix"] else ""))
        print(f"{sum(f['level'] == 'FAIL' for f in found)} FAIL, {sum(f['level'] == 'WARN' for f in found)} WARN -> check-{tag}.json")
        return 1 if any(f["level"] == "FAIL" for f in found) else 0
    # the site's own brand may carry what is banned elsewhere: its font, its cream ground, its colours
    b = plan["brand"]
    hexrgb = lambda c: tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    own = set()
    if b["display"]["family"].lower().replace(" variable", "") in at.GROTESK or "grotesk" in b["display"]["family"].lower():
        own.add("default-grotesk-display")
    if at.is_cream(b["ground"]):
        own.add("cream-paper-ground")
    if at.is_purple_blue(b["accent"]):
        own |= {"purple-blue", "gradient-ground"}
    if b["dark"]:
        own.add("neon-on-black")
    # a saturated section ground the site paints itself (a pink band, a brand-blue hero) is its brand
    sat = lambda c: (max(c) - min(c)) / max(1, max(c))
    if any(sat(hexrgb(c)) > 0.3 for c in site["brand"].get("section_grounds", []) + [b["accent"]]):
        own.add("flat-saturated-ground")
    # frames: 4 a second at 1/4 size, for motion; one settled frame per shot for the pixel tells
    W, H = plan["width"] // 4, plan["height"] // 4
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps=4,scale={W}:{H}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.int16)
    diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2)) if len(fr) > 1 else np.zeros(0)
    run = best = 0
    for i, v in enumerate(diff):
        run = run + 1 if v < 0.25 else 0
        if run > best:
            best, at_i = run, i
    if best / 4 > 2.5:
        add("WARN", f"nothing moves for {best / 4:.1f} s around {at_i / 4 - best / 8:.1f} s", "a slow push or a shorter shot")
    for i, s in enumerate(plan["shots"]):
        t = s["start"] + min(s["end"] - s["start"] - 0.3, max(1.4, (s["end"] - s["start"]) * 0.6))
        img = q.grab(video, t, plan["width"] // 2, plan["height"] // 2)
        if img is None:
            continue
        cv2.imwrite(str(d / f".check-{tag}-{i + 1:02d}.png"), img)
        for f in at.check_still(img, f"shot {i + 1} ({s['kind']}) at {t:.1f} s"):
            # a recording is the site's own UI, pixel for pixel: a tell in it is theirs, not ours
            real = s["kind"] in ("flow", "keys", "split", "media")
            lvl = "WARN" if f["tell"] in own or real else ("FAIL" if f["level"] == "BAN" else "WARN")
            add(lvl, f"{f['tell']}: {f['where']}" + (" (the site's own brand)" if f["tell"] in own else " (the site's own UI, recorded)" if real else ""), f["fix"])
    for lvl, msg in smoothness(plan):
        add(lvl, msg, "a longer move, sine.inOut, or a cut instead")
    # the product fills the frame: share of each frame that is UI, not plain ground (owner rule, 2026-10-06).
    # A block counts as UI when it has detail in it or is not the ground's colour. Type and the end card are exempt.
    vertical = plan["height"] > plan["width"] * 1.2
    need = 0.75 if vertical else 0.6
    for i, s in enumerate(plan["shots"]):
        if s["kind"] in ("type", "end"):
            continue
        cov = coverage(video, s, b["ground"], plan["width"], plan["height"])
        if cov is not None and cov < need:
            add("FAIL" if cov < need - 0.1 else "WARN", f"shot {i + 1} ({s['kind']}): the product fills {cov:.0%} of the frame, under {need:.0%}",
                "crop to the component, the phone-layout recording (record.mjs --mobile) or a vertical override in story.json")
    # contrast of the words against the ground they sit on
    r = q.ratio(float(q.rel_lum(hexrgb(b["ink"]))), float(q.rel_lum(hexrgb(b["ground"]))))
    if r < 4.5:
        add("FAIL" if r < 3 else "WARN", f"words {b['ink']} on {b['ground']}: contrast {r:.1f}:1", "the site's darker or lighter ink")
    if plan.get("audio", {}).get("music") or plan.get("audio", {}).get("vo") or plan.get("audio", {}).get("sfx"):
        lufs, peak = q.loudness(video)
        if peak is not None and peak > 0:
            add("FAIL", f"true peak {peak:.1f} dBTP clips", "lower the music")
        if lufs is not None and not -23 <= lufs <= -9 and (plan["audio"].get("music") or plan["audio"].get("vo")):
            add("WARN", f"loudness {lufs:.1f} LUFS", "music volume in the plan")
    (d / f"check-{tag}.json").write_text(json.dumps(found, indent=1))
    for f in found:
        print(f"{f['level']:4}  {f['what']}" + (f"\n      fix: {f['fix']}" if f["fix"] else ""))
    print(f"{sum(f['level'] == 'FAIL' for f in found)} FAIL, {sum(f['level'] == 'WARN' for f in found)} WARN -> check-{tag}.json")
    return 1 if any(f["level"] == "FAIL" for f in found) else 0


EASE = {"sine.inOut": lambda p: -(math.cos(math.pi * p) - 1) / 2,
        "power2.inOut": lambda p: 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2,
        "power3.inOut": lambda p: 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2,
        "expo.inOut": lambda p: 0 if p == 0 else 1 if p == 1 else (2 ** (20 * p - 10) / 2 if p < 0.5 else (2 - 2 ** (-20 * p + 10)) / 2)}
MOVE = {"linear": "sine.inOut", "apple": "sine.inOut", "stripe": "sine.inOut", "arc": "expo.inOut", "raycast": "sine.inOut"}


def smoothness(plan):
    """The camera, frame by frame, from the plan (as kit.tsx camAt draws it): zoom speed is the change of
    log scale a frame, pan speed the centre's travel in screen widths a frame. WARN on a frame that
    zooms faster than 7x a second at its peak, a speed that jumps (jerk), or a continued camera that changes speed
    at the join. Returns [(level, message)]."""
    fps, out = plan["fps"], []
    ease = EASE[MOVE.get(plan["variant"], "sine.inOut")]
    prev_end = None
    for i, s in enumerate(plan["shots"]):
        keys = (s.get("flow") or {}).get("keys") or s.get("keys")
        if not keys:
            prev_end = None
            continue
        def at(t):
            if t <= keys[0]["t"]:
                return keys[0]["rect"]
            for a, b in zip(keys, keys[1:]):
                if t <= b["t"]:
                    p = ease(min(1, max(0, (t - a["t"]) / max(1e-3, b["t"] - a["t"]))))
                    w = math.exp(math.log(a["rect"][2]) + (math.log(b["rect"][2]) - math.log(a["rect"][2])) * p)
                    q = (w - a["rect"][2]) / (b["rect"][2] - a["rect"][2]) if abs(b["rect"][2] - a["rect"][2]) > 1 else p
                    cx = a["rect"][0] + a["rect"][2] / 2 + ((b["rect"][0] + b["rect"][2] / 2) - (a["rect"][0] + a["rect"][2] / 2)) * q
                    return [cx - w / 2, 0, w, 0]
            return keys[-1]["rect"]
        n = max(2, round((s["end"] - s["start"]) * fps))
        rs = [at(k / fps) for k in range(n)]
        zv = [abs(math.log(b[2]) - math.log(a[2])) for a, b in zip(rs, rs[1:])]
        pv = [abs((b[0] + b[2] / 2) - (a[0] + a[2] / 2)) / max(a[2], 1) for a, b in zip(rs, rs[1:])]
        fast = max(zv) if zv else 0
        # Apple's measured push: about 3x over about 1 s, eased: a peak of ~1.7 log-units a second
        if fast * fps > 2.0:
            out.append(("WARN", f"shot {i + 1} ({s['kind']}): zooms at {math.exp(fast * fps):.1f}x a second at its peak; give the move more time"))
        for name, v in (("zoom", zv), ("pan", pv)):
            jumps = [k for k in range(1, len(v)) if v[k] > 3 * v[k - 1] + (0.004 if name == "zoom" else 0.01)]
            if jumps:
                out.append(("WARN", f"shot {i + 1} ({s['kind']}): {name} speed jumps at {s['start'] + jumps[0] / fps:.2f} s (a snap, not an ease)"))
        if s.get("cut_in") == "continue" and prev_end is not None and zv and abs(zv[0] - prev_end) > 0.004:
            out.append(("WARN", f"shot {i + 1}: the continued camera changes speed at the join"))
        prev_end = zv[-1] if zv else None
    return out


def coverage(video, shot, ground, W, H, n=5):
    """Median share of the frame covered by product UI across n frames of a shot: 24x24 blocks (at 1/4
    size) that are not flat ground of the site's own colour."""
    import numpy as np
    import quality as q
    g = np.array([int(ground[i:i + 2], 16) for i in (5, 3, 1)], float)   # BGR
    out = []
    for k in range(n):
        t = shot["start"] + (shot["end"] - shot["start"]) * (0.15 + 0.7 * k / max(1, n - 1))
        img = q.grab(video, t, W // 4, H // 4)
        if img is None:
            continue
        bs = 24
        h, w = (img.shape[0] // bs) * bs, (img.shape[1] // bs) * bs
        blk = img[:h, :w].astype(float).reshape(h // bs, bs, w // bs, bs, 3)
        flat = blk.std(axis=(1, 3)).max(-1) < 4
        same = np.abs(blk.mean(axis=(1, 3)) - g).max(-1) < 14
        out.append(1 - float((flat & same).mean()))
    return float(np.median(out)) if out else None


# ---------------------------------------------------------------- share copy, voice

def cmd_share(d):
    """The caption from story.json "share" (site phrases only, checked) and an alt text that says what is shown."""
    d = Path(d)
    site, story = load(d, "site.json"), load(d, "story.json")
    cap = (story.get("share") or {}).get("caption", "")
    bad = [p for p in re.split(r"(?<=[.!?])\s+|\n+", cap) if p.strip() and site["domain"] not in p and not is_site_phrase(p, site)]
    if not cap:
        sys.exit('ERROR: story.json has no "share": {"caption": ...}; write it from the site\'s own phrases')
    if bad:
        sys.exit("ERROR: not the site's words: " + " | ".join(bad))
    shown = [f'"{s["text"]}"' if s.get("text") else s["kind"] for s in story["shots"] if s["kind"] != "end"]
    alt = (f"A product video of the {site['domain']} website, shown in its own colours and type: "
           + ", then ".join(shown) + f". It ends on the {site['domain']} logo and address.")
    music = json.loads((d / "audio" / "music.json").read_text()) if (d / "audio" / "music.json").exists() else {}
    credit = f"\n\nMusic: {music['credit']}" if music.get("credit") else ""
    (d / "share.txt").write_text(f"{cap}{credit}\n\n{site['url']}\n\nALT: {alt}\n")
    print((d / "share.txt").read_text())


RIGHTS = {"own": "It's my own track", "cc": "YouTube Audio Library or Creative Commons (credited)",
          "licensed": "Licensed (Epidemic, Artlist or similar)", "unsure": "Not sure"}


def cmd_music(d, url, start=None, end=None, rights=None, credit=None, cookies=False):
    """A track from a YouTube (or any yt-dlp) link: audio only, cut to a section, its licence recorded in
    audio/MUSIC-LICENSE.md with the user's answer. Never copied anywhere but this project's audio/."""
    import datetime
    d = Path(d)
    (d / "audio").mkdir(exist_ok=True)
    base = ["yt-dlp", "--no-playlist", *(["--cookies-from-browser", "chrome"] if cookies else [])]
    meta = json.loads(subprocess.run(base + ["-j", url], capture_output=True, text=True).stdout or "{}")
    if not meta:
        sys.exit("ERROR: yt-dlp could not read that link. If YouTube asks to sign in, ask the user, then --cookies.")
    raw = d / "audio" / "track-src"
    subprocess.run(base + ["-f", "bestaudio", "-x", "--audio-format", "wav", "-o", f"{raw}.%(ext)s", url], check=True, capture_output=True)
    src = next(d.glob("audio/track-src.wav"))
    out = d / "audio" / "track.wav"
    cut = (["-ss", str(start)] if start else []) + (["-to", str(end)] if end else [])
    subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, "-i", str(src), "-ac", "2", "-ar", "48000", str(out)], check=True)
    src.unlink()
    lic = (meta.get("license") or "").strip()
    chan = meta.get("channel") or meta.get("uploader") or ""
    library = bool(re.search(r"audio library|no ?copyright|ncs|creative commons|cc0|royalty.?free", f"{chan} {meta.get('title', '')} {lic}", re.I))
    info = {"source": meta.get("webpage_url") or url, "title": meta.get("title"), "channel": chan, "license_field": lic or None,
            "looks_like_free_library": library, "rights": rights, "rights_answer": RIGHTS.get(rights), "credit": credit,
            "section": [start, end], "date": datetime.date.today().isoformat(), "file": "audio/track.wav"}
    (d / "audio" / "music.json").write_text(json.dumps(info, indent=1))
    (d / "audio" / "MUSIC-LICENSE.md").write_text(
        f"# Music licence\n\n| field | value |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in info.items()) +
        "\nThe audio stays in this project folder; it is never bundled into any repo.\n")
    print(json.dumps(info, indent=1))
    if rights == "unsure":
        print("WARNING: with the rights unknown, Instagram, TikTok and YouTube may mute the video or claim it. "
              "The generated score or the user's own track avoids that.")
    print(f"next: product.py plan {d} --music audio/track.wav  (cuts snap to its beats)")


def cmd_tts(d, text, voice):
    from ai_editor import keys
    import urllib.request
    key, _ = keys.get("elevenlabs")
    if not key:
        sys.exit("No ElevenLabs key: offer on-screen words or the user's own recording instead.")
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                                 data=json.dumps({"text": text, "model_id": "eleven_multilingual_v2"}).encode(),
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    (Path(d) / "audio").mkdir(exist_ok=True)
    out = Path(d) / "audio" / "vo.mp3"
    with urllib.request.urlopen(req, timeout=120) as r:
        out.write_bytes(r.read())
    print(out)


# ---------------------------------------------------------------- self-check

def demo():
    site = {"domain": "example.com", "viewport": [1440, 900], "title": "Example", "description": "",
            "tiles": [{"src": "images/tile-0.jpg", "y": 0, "size": [2880, 1800]}, {"src": "images/tile-1.jpg", "y": 900, "size": [2880, 1800]}],
            "copy": [{"text": "Ship faster with fewer meetings", "tag": "h1", "rect": [80, 300, 900, 80]},
                     {"text": "Start free", "tag": "a", "rect": [80, 420, 120, 40]}],
            "elements": [{"id": "el-0", "kind": "heading", "rect": [80, 300, 900, 80], "crop": [68, 288, 924, 104], "src": "images/el-0.png", "size": [1848, 208]},
                         {"id": "el-1", "kind": "button", "rect": [80, 420, 120, 40], "crop": [76, 416, 128, 48], "src": "images/el-1.png", "size": [512, 192]}],
            "brand": {"ground": "#FFFFFF", "ink": "#111111", "body_ink": "#555555", "accent": "#0055FF", "dark": False, "radius_px": 8,
                      "display": {"family": "Inter", "weight": 600, "letter_spacing": "-1.2px", "size_px": 60}, "body": {"family": "Inter", "weight": 400}, "fonts": []},
            "logo": {"word": "Example"}, "media": [], "url": "https://example.com"}
    assert is_site_phrase("ship faster", site) and is_site_phrase("Ship  faster with fewer meetings.", site)
    assert not is_site_phrase("ship 10x faster", site)
    story = {"shots": [{"kind": "page", "text": "Ship faster", "click": "el-1"}, {"kind": "lift", "el": "el-0"},
                       {"kind": "page", "focus": "el-1"}, {"kind": "end"}]}
    assert not [p for p in check_story(story, site) if p.startswith("FAIL")], check_story(story, site)
    bad = check_story({"shots": [{"kind": "page", "text": "Unlock seamless growth today"}]}, site)
    assert any("not on the site" in p for p in bad), bad
    twice = check_story({"shots": [{"kind": "grid", "els": ["el-0"]}, {"kind": "grid", "els": ["el-0"]}]}, site)
    assert any("just showed" in p for p in twice), twice
    carried = check_story({"shots": [{"kind": "flow", "flow": "a", "from": 0, "to": 3}, {"kind": "flow", "flow": "a", "from": 3, "to": 6}]}, site)
    assert not any("just showed" in p for p in carried), carried
    wrong = check_story({"shots": [{"kind": "grid", "els": ["el-0"], "job": "action"}]}, site)
    assert any("opens on 'end'" in p for p in check_story({"beats": [{"job": "end"}]}, site))   # gates.story_order runs here
    assert any("cannot do the action job" in p for p in wrong), wrong
    import tempfile as _t
    with _t.TemporaryDirectory() as td:
        (Path(td) / "flows").mkdir()
        (Path(td) / "flows" / "a-m.json").write_text("{}")
        v = vertical_shot({"kind": "flow", "flow": "a", "from": 1, "vertical": {"from": 2}}, td)
        assert v == {"kind": "flow", "flow": "a-m", "from": 2}, v
    snap_plan = {"fps": 30, "variant": "linear", "shots": [{"kind": "page", "start": 0, "end": 1, "keys": [
        {"t": 0, "rect": [0, 0, 1440, 900]}, {"t": 0.2, "rect": [480, 300, 480, 300]}]}]}
    assert any("zooms" in m for _, m in smoothness(snap_plan)), smoothness(snap_plan)
    snap_plan["shots"][0]["keys"][1]["t"] = 1.0
    assert not smoothness(snap_plan), smoothness(snap_plan)
    durs, end = durations(story, 20, "apple")
    assert abs(sum(durs) + end - 20) < 0.05 and min(durs) >= 2.2, durs
    assert snap(4.1, [0, 0.5, 4.0, 4.5]) == 4.0 and snap(7.0, [0, 4.0]) == 7.0
    assert brand_of(site)["display"]["tracking_em"] == -0.02
    assert mix("#000000", "#FFFFFF", 0.5) == "#808080"
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        (Path(t) / "site.json").write_text(json.dumps(site))
        (Path(t) / "story.json").write_text(json.dumps(story))
        for v in ("apple", "linear"):
            p = build_plan(t, v, "9:16", 20, music="none", sfx="none")
            assert p["width"] == 1080 and abs(p["durationInFrames"] - 600) <= 2, p["durationInFrames"]
            assert p["shots"][-1]["kind"] == "end" and all(s["end"] > s["start"] for s in p["shots"])
            assert ("cursor" in p["shots"][0]) == (v == "apple") and p["shots"][1]["lift"]["src"] == "images/el-0.png"
            assert v == "apple" or p["shots"][1]["cut_in"] == "blur"
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    if sys.argv[1:2] == ["_sheet"]:
        out = sheet(sys.argv[2], Path(sys.argv[2]) / "sheet.png")
        return print(f"REVIEW THIS: {out}")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["crawl", "pages", "record", "music", "copy", "plan", "animatic", "stills", "approve", "render", "check", "share", "tts", "meter"])
    ap.add_argument("--file", help="music: the user's own track inside DIR (audio/...), to record its licence")
    ap.add_argument("--url", help="music: a YouTube or other yt-dlp link")
    ap.add_argument("--start"), ap.add_argument("--end")
    ap.add_argument("--rights", choices=list(RIGHTS), help="music: the user's answer to who holds the rights")
    ap.add_argument("--credit", help="music: the credit line a CC-BY track needs (goes into share.txt)")
    ap.add_argument("--yt-cookies", action="store_true", help="music: --cookies-from-browser chrome, only after asking")
    ap.add_argument("a")
    ap.add_argument("b", nargs="?")
    ap.add_argument("--app")
    ap.add_argument("--cookies")
    ap.add_argument("--include", help="crawl: comma-separated pages the brief names, read first")
    ap.add_argument("--mobile", action="store_true", help="record: the phone layout (430x932 @3x) for 9:16")
    ap.add_argument("--variant", "--style", dest="variant", choices=STYLES, default="linear")
    ap.add_argument("--aspect", choices=list(SIZES), default="16:9")
    ap.add_argument("--length", type=float, help="seconds; default 30 for a shot film, about 8 a use case (40 for five) for a story of beats")
    ap.add_argument("--music", default="generated",
                    help="generated (scored here, default) | eleven (ElevenLabs Music, the user's key) | none | audio/<their track>")
    ap.add_argument("--vo", help="a voiceover inside DIR (audio/...)")
    ap.add_argument("--sfx", choices=["subtle", "none"], default="subtle")
    ap.add_argument("--no-sfx", action="store_true", help="same as --sfx none")
    ap.add_argument("--story", default="story.json")
    ap.add_argument("--fps", type=int, choices=[30, 60], default=FPS, help="60 doubles render time; camera moves read smoother (a story of beats always renders at 60)")
    ap.add_argument("--tag", help="names plan-<tag>.json and its renders (default <style>-<aspect>)")
    ap.add_argument("--plan")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--modal", action="store_true")
    ap.add_argument("--lambda", dest="use_lambda", action="store_true")
    ap.add_argument("--text")
    ap.add_argument("--voice", default="JBFqnCBsd6RMkjVDRZzb")
    a = ap.parse_args()
    if a.cmd == "crawl":
        if not a.b:
            sys.exit("usage: product.py crawl URL DIR")
        extra = (["--app", a.app] if a.app else []) + (["--cookies", a.cookies] if a.cookies else []) + (["--include", a.include] if a.include else [])
        sys.exit(subprocess.run(["node", str(HERE / "crawl.mjs"), a.a, a.b, *extra]).returncode)
    if a.cmd == "copy":
        return cmd_copy(a.a)
    if a.cmd == "music":
        if not a.rights:
            sys.exit("ERROR: --rights is required: ask who holds the rights in the question box first")
        if a.file:
            return print(json.dumps(gates.record_file(a.a, a.file, a.rights, a.credit), indent=1))
        return cmd_music(a.a, a.url, a.start, a.end, a.rights, a.credit, a.yt_cookies)
    if a.cmd == "pages":
        return cmd_pages(a.a)
    if a.cmd == "record":
        sys.exit(subprocess.run(["node", str(HERE / "record.mjs"), a.a, *(["--cookies", a.cookies] if a.cookies else []),
                                 *(["--mobile"] if a.mobile else [])]).returncode)
    if a.cmd == "plan":
        own_track = a.music if a.music not in ("generated", "eleven", "none") else None
        for why in (gates.need_brief(a.a), gates.need_licence(a.a, own_track)):
            if why:
                sys.exit(f"ERROR: {why}")
        music, own = (a.music, None) if a.music in ("generated", "eleven", "none") else ("own", a.music)
        if music == "eleven":
            own = "audio/eleven.mp3"
        tag = a.tag or tag_of(a.variant, a.aspect)
        plan = build_plan(a.a, a.variant, a.aspect, a.length, music, a.vo, "none" if a.no_sfx else a.sfx, own, a.story, tag, a.fps)
        out = Path(a.a) / f"plan-{tag}.json"
        out.write_text(json.dumps(plan, indent=1))
        for lvl, msg in smoothness(plan):
            print(f"{lvl} {msg}")
        if plan.get("journey"):
            print(f"{out}: {len(plan['beats'])} beats, {plan['durationInFrames'] / plan['fps']:.1f} s at {plan['fps']} fps, "
                  + " | ".join(f"{b['job']} {b['end'] - b['start']:.1f}s" + (f" '{b['text']}'" if b.get("text") else "") for b in plan["beats"]))
            sys.exit(1 if plan.get("framing") else 0)
        print(f"{out}: {len(plan['shots'])} shots, {plan['durationInFrames'] / plan['fps']:.1f} s, "
              + " | ".join(f"{s['kind']} {s['end'] - s['start']:.1f}s" + (f" '{s['text']}'" if s.get("text") else "") for s in plan["shots"]))
        return
    if a.cmd == "meter":
        sys.exit(subprocess.run([sys.executable, str(HERE / "meter.py"), a.a, *([a.b] if a.b else [])]).returncode)
    if a.cmd in ("animatic", "stills", "approve", "render", "check") and not a.plan:
        sys.exit("--plan plan-<variant>-<aspect>.json is required")
    if a.cmd == "animatic":
        return cmd_animatic(a.a, a.plan)
    if a.cmd == "stills":
        return cmd_stills(a.a, a.plan)
    if a.cmd == "approve":
        return print(gates.approve(a.a, a.plan))
    if a.cmd == "render":
        return cmd_render(a.a, a.plan, a.draft, a.modal, a.use_lambda)
    if a.cmd == "check":
        sys.exit(cmd_check(a.a, a.plan))
    if a.cmd == "share":
        return cmd_share(a.a)
    if a.cmd == "tts":
        return cmd_tts(a.a, a.text, a.voice)


if __name__ == "__main__":
    main()
