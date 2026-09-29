#!/usr/bin/env python3
"""Turn a creator's style.json + a cut's words.json into plan.json for the Remotion render.

    python3 plan.py <style.json> <edits/NAME/words.json> [--images images.json]
                    [--aspect auto|9:16|16:9] [--out edits/NAME/plan.json]
    python3 plan.py demo      self-check

cut.mp4 is read from the words.json folder (ffprobe gives its size, fps and length).
images.json, optional: [{"src": "images/a.png", "word": "notion"}, ...]. src is relative
to the edit folder. Optional per image: "nth" (which time the word is said, default the
next one after the previous card), "box" [x, y, w, h] in percent, "entrance", "hold_s".
Shapes: docs/CONTRACTS.md. Stdlib only, deterministic.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
PAUSE_S = 0.3          # a gap this long starts a new caption chunk
CARD_LEAD_S = 0.1      # a card lands this long before its word
ENTRANCES = ("pop", "slide", "fade", "scale")
# Above the head in a vertical frame, the right side in a wide one.
DEFAULT_BOX = {"9:16": [12, 4, 76, 22], "16:9": [54, 10, 40, 48]}


def clean(text):
    return re.sub(r"[^\w'’-]+", "", text)


def cased(text, mode):
    text = clean(text)
    return text.lower() if mode == "lower" else text.upper() if mode == "upper" else text


def ends_sentence(text):
    return text.rstrip().endswith((".", "?", "!"))


def ends_clause(text):
    return text.rstrip().endswith((".", "?", "!", ",", ";", ":"))


def chunk_captions(words, n, mode):
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or len(cur) >= n or ends_clause(w["text"]) or nxt["start"] - w["end"] > PAUSE_S:
            chunks.append(cur)
            cur = []
    out = []
    for i, c in enumerate(chunks):
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else None
        end = c[-1]["end"] + 0.4
        if nxt is not None:
            end = min(end, nxt)
        ws = [{"text": cased(w["text"], mode), "start": w["start"], "end": w["end"]} for w in c]
        ws = [w for w in ws if w["text"]]
        if ws:
            out.append({"text": " ".join(w["text"] for w in ws), "start": c[0]["start"],
                        "end": round(end, 3), "words": ws})
    return out


def zoom_times(words, on, cuts):
    """Candidate moments for a zoom, in seconds."""
    if on == "every_cut" and cuts:
        return cuts
    starts = [w["start"] for i, w in enumerate(words)
              if i == 0 or ends_sentence(words[i - 1]["text"]) or w["start"] - words[i - 1]["end"] > 0.5]
    if on != "emphasis":
        return starts
    # Emphasis: the longest-held word of each phrase (people stretch the word they stress).
    out, phrase = [], []
    for i, w in enumerate(words):
        phrase.append(w)
        if i + 1 == len(words) or words[i + 1]["start"] - w["end"] > 0.2:
            out.append(max(phrase, key=lambda x: x["end"] - x["start"])["start"])
            phrase = []
    return out


def place_zooms(zoom, words, duration, cuts):
    per_min = zoom.get("per_min") or 0
    if not per_min or not words:
        return []
    gap = 60 / per_min * 0.8
    picked = []
    for t in zoom_times(words, zoom.get("on", "sentence_start"), cuts):
        if not picked or t - picked[-1] >= gap:
            picked.append(t)
    kind = zoom.get("kind", "punch")
    ease = 0.0 if kind == "punch" else (zoom.get("duration_s") or 0.4)
    # Alternate in / out so the frame never creeps tighter: every other change goes back to 1x.
    ends = picked[1:] + [duration]
    return [{"start": round(s, 3), "end": round(e, 3), "scale": zoom.get("scale", 1.15),
             "kind": kind, "ease_s": ease}
            for i, (s, e) in enumerate(zip(picked, ends)) if i % 2 == 0 and e > s]


def card_defaults(style):
    cats = style.get("cats") or (style["events"] if isinstance(style.get("events"), dict) else {})
    top = next(iter(cats.values()), {}) if cats else {}
    ent = next((e[0] for e in top.get("entrance") or [] if e[0] in ENTRANCES), "pop")
    return top.get("hold_s") or 2.5, ent, top.get("box")


def place_cards(images, words, duration, style, aspect):
    hold, ent, box = card_defaults(style)
    cards, after = [], -1.0
    for im in images:
        target = clean(im["word"]).lower()
        hits = [w for w in words if clean(w["text"]).lower() == target]
        if im.get("nth"):
            hits = hits[im["nth"] - 1:im["nth"]]
        else:
            hits = [w for w in hits if w["start"] > after]
        if not hits:
            print(f"warning: '{im['word']}' is never said after the previous card, skipped {im['src']}",
                  file=sys.stderr)
            continue
        start = round(max(0.0, hits[0]["start"] - CARD_LEAD_S), 3)
        cards.append({"src": im["src"], "start": start,
                      "end": round(min(duration, start + (im.get("hold_s") or hold)), 3),
                      "trigger_word": im["word"], "entrance": im.get("entrance", ent),
                      "box": im.get("box") or box or DEFAULT_BOX[aspect]})
        after = start
    cards.sort(key=lambda c: c["start"])
    for a, b in zip(cards, cards[1:]):     # never two cards at once
        a["end"] = min(a["end"], b["start"])
    return cards


def build(style, words, meta, images=(), aspect="auto", cuts=()):
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    if aspect == "auto":
        aspect = "9:16" if meta["height"] > meta["width"] else "16:9"
    width, height = SIZES[aspect]
    fps = round(meta["fps"]) or 30
    duration = meta["duration"]
    cap = dict(style.get("captions") or {})
    chunks = chunk_captions(words, cap.get("words_per_caption") or 3, cap.get("case", "sentence")) \
        if cap.get("present", True) else []
    return {"video": meta["video"], "width": width, "height": height, "fps": fps,
            "durationInFrames": int(duration * fps),
            "captions": {"style": cap, "chunks": chunks},
            "zooms": place_zooms(style.get("zoom") or {}, words, duration, list(cuts)),
            "cards": place_cards(list(images), words, duration, style, aspect)}


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration",
                          "-of", "json", str(video)], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"ERROR: ffprobe could not read {video}")
    d = json.loads(out.stdout)
    s = d["streams"][0]
    w, h = s["width"], s["height"]
    if any(abs(sd.get("rotation", 0)) == 90 for sd in s.get("side_data_list", [])):
        w, h = h, w
    num, den = s["r_frame_rate"].split("/")
    return {"video": Path(video).name, "width": w, "height": h,
            "fps": int(num) / int(den or 1), "duration": float(d["format"]["duration"])}


def cut_points(edit_dir):
    """Where the jump cuts fall on cut.mp4, from the cut skill's decisions.json."""
    p = edit_dir / "decisions.json"
    if not p.exists():
        return []
    t, out = 0.0, []
    for span in json.loads(p.read_text())[:-1]:
        t += span["end"] - span["start"]
        out.append(round(t, 3))
    return out


def demo():
    words = []
    t = 0.0
    for i, text in enumerate("so this is how I edit. every video gets zooms and captions now. try notion today."
                             .split()):
        words.append({"text": text, "start": round(t, 2), "end": round(t + 0.3, 2), "type": "word"})
        t += 0.35 + (0.6 if text.endswith(".") else 0)
    style = {"zoom": {"per_min": 60, "kind": "punch", "scale": 1.2, "on": "sentence_start"},
             "captions": {"words_per_caption": 3, "case": "upper"},
             "cats": {"logo": {"hold_s": 2.0, "entrance": [["slide", 0.7]], "box": None}}}
    meta = {"video": "cut.mp4", "width": 3840, "height": 2160, "fps": 29.97, "duration": t}
    imgs = [{"src": "images/n.png", "word": "Notion"}]
    p = build(style, words, meta, imgs)
    assert (p["width"], p["height"], p["fps"]) == (1920, 1080, 30), p
    chunks = p["captions"]["chunks"]
    assert all(len(c["words"]) <= 3 for c in chunks)
    assert chunks[0]["text"] == "SO THIS IS" and chunks[1]["text"] == "HOW I EDIT", chunks[:2]
    assert all(a["end"] <= b["start"] for a, b in zip(chunks, chunks[1:]))
    z = p["zooms"]
    assert z and all(x["ease_s"] == 0 and x["scale"] == 1.2 for x in z)
    assert all(a["end"] <= b["start"] for a, b in zip(z, z[1:])), "zooms overlap"
    assert z[0]["end"] < z[1]["start"], "zoom-out gap missing: the frame would creep"
    c = p["cards"][0]
    notion = next(w for w in words if w["text"] == "notion")
    assert abs(c["start"] - (notion["start"] - 0.1)) < 1e-6 and c["entrance"] == "slide", c
    assert c["box"] == DEFAULT_BOX["16:9"]
    v = build(style, words, meta, aspect="9:16")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert build(style, words, meta, imgs) == p, "not deterministic"
    push = place_zooms({"per_min": 30, "kind": "push", "duration_s": 0.5, "on": "emphasis"},
                       [w for w in words], t, [])
    assert push and push[0]["ease_s"] == 0.5
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("style")
    ap.add_argument("words")
    ap.add_argument("--images")
    ap.add_argument("--aspect", choices=["auto", "9:16", "16:9"], default="auto")
    ap.add_argument("--out")
    a = ap.parse_args()
    edit_dir = Path(a.words).resolve().parent
    video = edit_dir / "cut.mp4"
    if not video.exists():
        sys.exit(f"ERROR: no cut.mp4 in {edit_dir}. Run the cut skill first.")
    images = json.loads(Path(a.images).read_text()) if a.images else []
    plan = build(json.loads(Path(a.style).read_text()), json.loads(Path(a.words).read_text()),
                 probe(video), images, a.aspect, cut_points(edit_dir))
    out = Path(a.out) if a.out else edit_dir / "plan.json"
    out.write_text(json.dumps(plan, indent=1))
    print(f"{out}: {plan['width']}x{plan['height']}, {plan['durationInFrames'] / plan['fps']:.1f} s, "
          f"{len(plan['captions']['chunks'])} captions, {len(plan['zooms'])} zooms, {len(plan['cards'])} cards")


if __name__ == "__main__":
    main()
