#!/usr/bin/env python3
"""The look pass in words: what code cannot measure, named by a cheap video model.

  look <handle>    Gemini Flash-Lite watches each picked video (no sound, 480 px, 1 frame
                   a second, low media resolution) and fills a fixed JSON schema: font
                   class, weight, case, caption animation, graphics style, motion
                   personality, transitions, b-roll types, and what makes the look not
                   generic. Writes video/<id>.look-ai.json, then runs merge.
  kinds <handle>   names the kind of every graphic graphics.py cropped (12 crops a call, low
                   resolution, about 70 tokens a crop): screenshot, UI recording, logo, text card,
                   photo, meme, chart, b-roll, or part of the set (dropped). Then graphics merge.
  merge <handle>   folds every video/<id>.look-ai.json into style.json "look" (majority
                   per field), sets captions.font_match, rewrites look.md. The fallback
                   (no key) writes the same files from frame sheets, then runs this.
  prompt           prints the prompt and schema, for the fallback's small model.
  demo             self-check. No network.

Numbers never come from here: size, place, colours, timings are look.py's. Only the
categories the model names land in style.json, plus captions.font_match.

Key: GEMINI_API_KEY in the environment, or ~/.config/creator-teardown/.env
($AI_EDITOR_HOME/.env instead when AI_EDITOR_HOME is set)
(`fetch.py setkey --gemini`). Free at https://aistudio.google.com/apikey.
Model: gemini-3.1-flash-lite ($0.25 per 1M input tokens), then gemini-3.5-flash-lite
($0.30) if a key cannot use it; GEMINI_MODEL overrides. A 60 s video at 1 fps, low
resolution, is about 5,600 tokens (measured on 7 TikToks).

Usage:
  ~/.ai-video-editor/venv/bin/python scripts/gemini.py look <handle> [--top 5] [--ids ID,ID]
  ~/.ai-video-editor/venv/bin/python scripts/gemini.py merge <handle>
  ~/.ai-video-editor/venv/bin/python scripts/gemini.py kinds <handle> [--force]

Exit codes: 0 ok - 1 error - 2 usage or no key
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch import OUT_ROOT, slug  # noqa: E402
from transcribe import find_key  # noqa: E402

# Cheapest first. A 404 (retired, or closed to new keys) moves on to the next.
# gemini-2.5-flash-lite ($0.10) is closed to keys made after mid-2026.
MODELS = [os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else \
    ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
MODEL = MODELS[0]
API = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
FONTS = ["Montserrat", "Poppins", "Inter", "Roboto", "TikTok Sans", "Archivo Black", "Anton",
         "Bebas Neue", "Oswald", "Nunito", "Playfair Display", "DM Serif Display", "Caveat",
         "Permanent Marker", "JetBrains Mono"]
WEIGHT = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700, "extra bold": 800, "black": 900}


def enum(*v):
    return {"type": "STRING", "enum": list(v)}


def many(*v):
    return {"type": "ARRAY", "items": enum(*v)}


SCHEMA = {"type": "OBJECT", "properties": {
    "font_class": enum("geometric sans", "grotesk", "serif", "condensed", "handwritten", "mono",
                       "rounded", "no captions"),
    "closest_google_font": enum(*FONTS),
    "weight_class": enum(*WEIGHT),
    "caption_case": enum("lower", "upper", "sentence"),
    "caption_animation": enum("pop", "word_highlight", "slide", "typewriter", "fade", "none"),
    "graphics_style": many("real screenshots", "screen recordings", "logos", "stock footage",
                           "stock photos", "illustrated", "3D", "memes", "text cards", "charts",
                           "none"),
    "motion_personality": enum("snappy", "smooth", "punchy", "calm"),
    "transitions": many("hard cut", "jump cut", "zoom punch", "whip", "slide", "fade", "glitch",
                        "none"),
    "broll_types": many("screen recording", "product UI", "app screenshot", "website", "article",
                        "social post", "stock video", "photo", "meme", "news clip", "green screen",
                        "animation", "none"),
    "not_generic": {"type": "ARRAY", "items": {"type": "STRING"}},
}, "required": ["font_class", "closest_google_font", "weight_class", "caption_case",
                "caption_animation", "graphics_style", "motion_personality", "transitions",
                "broll_types", "not_generic"]}

PROMPT = """You are describing the editing look of a short-form video so another editor can copy it.
Judge only what is on screen. Captions are the words burned in that follow the speech.
- font_class, closest_google_font, weight_class, caption_case, caption_animation: the captions.
  closest_google_font is the nearest free font in the list, by letter shapes.
- graphics_style: every kind of visual laid over or cut in, besides the speaker.
- motion_personality: snappy (fast, instant), smooth (eased, gliding), punchy (hard hits, zooms
  on beats), calm (few cuts, long holds).
- not_generic: 3 to 5 short, specific things that set this look apart from a default captioned
  talking head (a colour, a placement, a recurring device). Concrete, under 15 words each."""


def video_bytes(path):
    """The video, silent, 480 px tall, 2 fps: a few hundred KB, sent inline."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "small.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-an", "-vf",
                        "fps=2,scale=-2:480", "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
                        str(out)], check=True)
        return out.read_bytes()


def body(data, fps=1.0):
    return {"contents": [{"parts": [
        {"inlineData": {"mimeType": "video/mp4", "data": base64.b64encode(data).decode()},
         "videoMetadata": {"fps": fps}},
        {"text": PROMPT}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": SCHEMA, "mediaResolution": "MEDIA_RESOLUTION_LOW"}}


def parse(resp):
    """(look dict, input tokens) from a generateContent response."""
    text = resp["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text), (resp.get("usageMetadata") or {}).get("promptTokenCount", 0)


def call(key, payload):
    """(response, model). Tries MODELS in order past a 404."""
    for model in MODELS:   # local, not the global: look calls run in threads
        r = post(key, payload, model)
        if r is not None:
            return r, model
    raise SystemExit(f"none of {', '.join(MODELS)} is available to this key")


def post(key, payload, model=None):
    model = model or MODEL
    req = urllib.request.Request(API.format(m=model), json.dumps(payload).encode(),
                                 {"Content-Type": "application/json", "x-goog-api-key": key})
    for wait in (10, 30, 60, None):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            if e.code == 404:
                print(f"  {model} not available to this key, trying the next", file=sys.stderr)
                return None
            if e.code in (429, 500, 503) and wait:
                print(f"  HTTP {e.code}, retrying in {wait} s", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code in (400, 401, 403) and "key" in msg.lower():
                sys.exit(f"Gemini rejected the key (HTTP {e.code}). Make a new one at "
                         f"aistudio.google.com/apikey and save it with: fetch.py setkey --gemini")
            if e.code == 429:
                raise SystemExit("Gemini is rate-limiting this key (HTTP 429, the free tier's per-minute cap). "
                                 "Wait a minute and rerun: finished videos are cached and skipped.")
            raise SystemExit(f"Gemini HTTP {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError) as e:
            if wait:
                print(f"  no answer from Gemini ({e}), retrying in {wait} s", file=sys.stderr)
                time.sleep(wait)
                continue
            raise SystemExit(f"Gemini unreachable ({e}). Check the internet connection and rerun.")


def mode(xs):
    xs = [x for x in xs if x]
    return Counter(xs).most_common(1)[0][0] if xs else None


def merge_rows(rows, source):
    """Majority per field; list fields keep what at least half the videos show."""
    n = len(rows)
    look = {"source": source, "videos": n}
    for k in ("font_class", "closest_google_font", "weight_class", "caption_case",
              "caption_animation", "motion_personality"):
        look[k] = mode(r.get(k) for r in rows)
    for k in ("graphics_style", "transitions", "broll_types"):
        c = Counter(x for r in rows for x in set(r.get(k) or []))
        look[k] = [x for x, m in c.most_common() if m >= n / 2 and x != "none"] or \
                  [x for x, _ in c.most_common(2)]
    seen, ng = set(), []
    for r in rows:
        for x in r.get("not_generic") or []:
            if x.lower() not in seen:
                seen.add(x.lower())
                ng.append(x)
    look["not_generic"] = ng[:6]
    return look


def apply(style, look):
    """Puts the words into style.json. Numbers from look.py are never overwritten."""
    style["look"] = look
    cap = style.setdefault("captions", {})
    if cap.get("present") is not False and look.get("font_class") != "no captions":
        cap["font_match"] = look.get("closest_google_font") or cap.get("font_match")
        cap.setdefault("weight", WEIGHT.get(look.get("weight_class")))
        if cap.get("present") is None:  # no OCR ran: the model's categories stand in
            cap["case"] = cap.get("case") or look.get("caption_case")
            cap["animation"] = cap.get("animation") or look.get("caption_animation")
        cap["source"] = {**(cap.get("source") or {}), "font": look["source"]}
    return style


KIND_SET = "part of the set"
KINDS_SCHEMA = {"type": "OBJECT", "properties": {"items": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {
        "i": {"type": "INTEGER"},
        "kind": enum("real screenshot", "UI recording", "logo", "text card", "photo", "meme", "chart",
                     "b-roll", KIND_SET),
        "what": {"type": "STRING"}},
    "required": ["i", "kind", "what"]}}}, "required": ["items"]}

KINDS_PROMPT = """Each image is a crop a detector flagged as a graphic laid over a short-form video, numbered
in order from 0. Many are false alarms: a patch of the camera shot itself. Name its kind:
- real screenshot: a still capture of a real web page, post, app, document or table
- UI recording: a moving screen recording of an app or site
- logo: a brand or product logo on its own
- text card: words set on a plain ground by the editor (a title, a list, a quote)
- photo: a real photograph
- meme: a reaction image or meme template
- chart: a graph or data chart
- b-roll: a separate video clip inserted by the editor, with its own frame edge or a different scene
  from the main shot (a rare kind: most real-world crops are part of the set)
- part of the set: not a graphic at all, a piece of the main camera shot: the room, ceiling, sky, trees,
  furniture, props, the speaker or other people in the scene, their body or hands. When unsure between
  this and b-roll, pick this.
what: under 8 words, what it shows ("Reddit post about ad copy", "Claude pricing table")."""


def image_part(path):
    from PIL import Image
    import io
    im = Image.open(path).convert("RGB")
    im.thumbnail((384, 384))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}}


def kinds_body(paths):
    parts = []
    for i, p in enumerate(paths):
        parts += [{"text": f"image {i}"}, image_part(p)]
    return {"contents": [{"parts": parts + [{"text": KINDS_PROMPT}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                                 "responseSchema": KINDS_SCHEMA, "mediaResolution": "MEDIA_RESOLUTION_LOW"}}


def cmd_kinds(a):
    """Names the kind of every cropped graphic (graphics.py measure), 12 crops a call."""
    key, _ = find_key("GEMINI_API_KEY")
    if not key:
        print("No Gemini key: the kinds stay the code's guess. See setup.md step 4.", file=sys.stderr)
        sys.exit(2)
    outdir = OUT_ROOT / slug(a.handle)
    files = sorted((outdir / "video").glob("*.graphics.json"))
    if not files:
        sys.exit("no video/*.graphics.json. Run graphics.py measure first.")
    docs = {f: json.loads(f.read_text()) for f in files}
    todo = [(f, g) for f, d in docs.items() for g in d["graphics"]
            if g.get("crop") and (a.force or g.get("kind_source") != "model")]
    total = 0
    for k in range(0, len(todo), 12):
        batch = todo[k:k + 12]
        resp, model = call(key, kinds_body([outdir / g["crop"] for _, g in batch]))
        got, tokens = parse(resp)
        total += tokens
        for it in got.get("items", []):
            if 0 <= it.get("i", -1) < len(batch):
                g = batch[it["i"]][1]
                g.update(kind="set" if it["kind"] == KIND_SET else it["kind"], what=it.get("what", "")[:80],
                         kind_source="model")
        print(f"  {k + len(batch)}/{len(todo)} crops, {tokens} tokens", file=sys.stderr)
    for f, d in docs.items():
        f.write_text(json.dumps(d, indent=1))
    print(f"{total} input tokens, about ${total / 1e6 * 0.30:.4f} at most on the paid tier (free tier: $0)",
          file=sys.stderr)
    from graphics import merge as gmerge
    g = gmerge(outdir)
    print("kinds: " + (", ".join(f"{k} {v}%" for k, v in (g.get("kinds") or {}).items()) or "none") + f" -> {outdir / 'style.json'}")


def cmd_merge(a):
    outdir = OUT_ROOT / slug(a.handle)
    files = sorted((outdir / "video").glob("*.look-ai.json"))
    if not files:
        sys.exit("no video/*.look-ai.json yet. Run `look`, or the fallback sheet pass.")
    rows = [json.loads(f.read_text()) for f in files]
    source = mode(r.get("_source") for r in rows) or MODEL
    sp = outdir / "style.json"
    style = apply(json.loads(sp.read_text()) if sp.exists() else {"handle": slug(a.handle)},
                  merge_rows(rows, source))
    sp.write_text(json.dumps(style, indent=2))
    from look import write_summary
    print(write_summary(outdir))
    print(f"-> {sp}")


def cmd_look(a):
    key, _ = find_key("GEMINI_API_KEY")
    if not key:
        print("No Gemini key. Get one free at https://aistudio.google.com/apikey, then run in a "
              "terminal: fetch.py setkey --gemini. Or use the fallback sheet pass.", file=sys.stderr)
        sys.exit(2)
    outdir = OUT_ROOT / slug(a.handle)
    have = {p.stem: p for p in (outdir / "video").glob("*.mp4")}
    if a.ids:
        ids = a.ids.split(",")
    else:
        views = {}
        vj = outdir / "videos.json"
        if vj.exists():
            views = {v["id"]: v.get("view_count") or v.get("like_count") or 0 for v in json.loads(vj.read_text())["videos"]}
        ids = sorted(have, key=lambda i: -views.get(i, 0))[:a.top]
    def one(vid):
        """Tokens spent on one video (a thread: the work is an HTTP call)."""
        out = outdir / "video" / f"{vid}.look-ai.json"
        if out.exists() and not a.force:
            print(f"{vid} cached", file=sys.stderr)
            return 0
        if vid not in have:
            print(f"{vid} not downloaded, skipped", file=sys.stderr)
            return 0
        data = video_bytes(have[vid])
        if len(data) > 15_000_000:
            print(f"{vid} too big to send inline ({len(data) >> 20} MB), skipped", file=sys.stderr)
            return 0
        resp, model = call(key, body(data, a.fps))
        look, tokens = parse(resp)
        out.write_text(json.dumps({**look, "_source": model, "_tokens": tokens}, indent=2))
        print(f"{vid} {tokens} tokens: {look['font_class']}, {look['caption_animation']}, "
              f"{look['motion_personality']}", file=sys.stderr)
        return tokens
    from parallel import pmap
    total = sum(pmap(one, ids, threads=True))
    print(f"{total} input tokens, about ${total / 1e6 * 0.30:.4f} at most on the paid tier (free tier: $0)",
          file=sys.stderr)
    if a.no_merge:
        print("saved video/*.look-ai.json; style.json is merged by the next `gemini.py merge` (or `look`)",
              file=sys.stderr)
        return
    cmd_merge(a)


def demo_kinds_prompt():
    # a crop of the live shot (a ceiling, a person in the scene) is the set, not b-roll: b-roll must be inserted
    assert "other people in the scene" in KINDS_PROMPT and "ceiling" in KINDS_PROMPT
    assert "pick this" in KINDS_PROMPT.split("part of the set:")[1] and "talking-head" not in KINDS_PROMPT


def demo():
    demo_kinds_prompt()
    with tempfile.TemporaryDirectory() as d:
        clip = Path(d) / "c.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=s=720x1280:d=2:r=30",
                        "-pix_fmt", "yuv420p", str(clip)], check=True)
        data = video_bytes(clip)
        assert 0 < len(data) < 500_000, len(data)
    b = body(b"xyz", 1.0)
    part = b["contents"][0]["parts"][0]
    assert part["inlineData"]["data"] == "eHl6" and part["videoMetadata"]["fps"] == 1.0
    assert b["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_LOW"
    assert set(SCHEMA["required"]) == set(SCHEMA["properties"])

    r1 = {"font_class": "grotesk", "closest_google_font": "TikTok Sans", "weight_class": "bold",
          "caption_case": "lower", "caption_animation": "pop", "graphics_style": ["real screenshots", "logos"],
          "motion_personality": "punchy", "transitions": ["jump cut"], "broll_types": ["screen recording"],
          "not_generic": ["white one-word captions low on the chest"]}
    resp = {"candidates": [{"content": {"parts": [{"text": json.dumps(r1)}]}}],
            "usageMetadata": {"promptTokenCount": 4100}}
    got, tok = parse(resp)
    assert got == r1 and tok == 4100
    r2 = dict(r1, closest_google_font="Inter", graphics_style=["real screenshots"],
              not_generic=["White one-word captions low on the chest", "screenshots slide up"])
    r3 = dict(r1, graphics_style=["memes"])
    look = merge_rows([r1, r2, r3], MODEL)
    assert look["closest_google_font"] == "TikTok Sans" and look["graphics_style"] == ["real screenshots"]
    assert look["not_generic"] == ["white one-word captions low on the chest", "screenshots slide up"]
    style = apply({"captions": {"present": True, "weight": 600, "size_pct": 4.4}}, look)
    c = style["captions"]
    assert c["font_match"] == "TikTok Sans" and c["weight"] == 600 and c["size_pct"] == 4.4, c
    style = apply({"captions": {"present": False}}, look)
    assert "font_match" not in style["captions"]
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.jpg"
        Image.new("RGB", (900, 500), "white").save(p)
        kb = kinds_body([p, p])
        parts = kb["contents"][0]["parts"]
        assert parts[0] == {"text": "image 0"} and parts[1]["inlineData"]["mimeType"] == "image/jpeg"
        assert len(parts) == 5 and KIND_SET in json.dumps(kb["generationConfig"]["responseSchema"])
    print("ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("look")
    p.add_argument("handle")
    p.add_argument("--top", type=int, default=5, help="most-viewed downloaded videos to send")
    p.add_argument("--ids", default=None)
    p.add_argument("--fps", type=float, default=1.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--no-merge", action="store_true",
                   help="only call the model (run beside transcription); `merge` writes style.json later")
    p.set_defaults(fn=cmd_look)
    p = sub.add_parser("merge")
    p.add_argument("handle")
    p.set_defaults(fn=cmd_merge)
    p = sub.add_parser("kinds")
    p.add_argument("handle")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_kinds)
    sub.add_parser("prompt").set_defaults(fn=lambda a: print(
        PROMPT + "\n\nAnswer with JSON only, matching this schema:\n" + json.dumps(SCHEMA, indent=1)))
    sub.add_parser("demo").set_defaults(fn=lambda a: demo())
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
