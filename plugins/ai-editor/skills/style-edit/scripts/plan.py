#!/usr/bin/env python3
"""Turn a creator's style.json + a cut's words.json into plan.json for the Remotion render.

    python3 plan.py <style.json> <edits/NAME/words.json> [--images images.json (default: next to words.json)]
                    [--aspect auto|9:16|16:9] [--layout overlay|split] [--out edits/NAME/plan.json]
    python3 plan.py demo      self-check

cut.mp4 is read from the words.json folder (ffprobe gives its size, fps and length).
images.json, optional: [{"src": "images/a.png", "word": "notion"}, ...]. src is relative
to the edit folder. Optional per image: "nth" (which time the word is said, default the
next one after the previous card), "box" [x, y, w, h] in percent, "entrance", "hold_s".
visuals.json next to words.json, optional: its "anim" beats become animated cards
(its "capture" beats arrive through images.json once capture.mjs has run).
--layout split (vertical only): the visual sits in a top panel, the speaker in a window under it,
framed from face.json; with no visual up the speaker has the whole frame. Default overlay: cards
float over the full-frame speaker. style.json "layout": {"mode": "split", "ground": "#F4F4F2"}
sets it too (the flag wins).
Shapes: docs/CONTRACTS.md. Stdlib only, deterministic.
"""
import argparse
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080)}
PAUSE_S = 0.3          # a gap this long starts a new caption chunk
MAX_WORD_S = 0.8       # longest a single spoken word is believed to last
HOLD_TAIL_S = 0.3      # a caption stays up this long after its last word
CARD_LEAD_S = 0.1      # a card lands this long before its word
ENTRANCES = ("pop", "slide", "fade", "scale")
# Above the head in a vertical frame, the right side in a wide one.
DEFAULT_BOX = {"9:16": [10, 15, 74, 20], "16:9": [54, 10, 40, 48]}
# Where the app's own UI sits, in percent: left, top, right, bottom. Vertical: the
# TikTok/Reels/Shorts top bar, the like/comment/share rail on the right and the
# caption/username block at the bottom. Wide: YouTube's progress bar.
SAFE = {"9:16": (6, 14, 14, 22), "16:9": (3, 5, 3, 10)}
LOGO_S = 1.2           # a logo stays up this long
LOGO_BOX_H = 11        # logo tile height, % of the frame
TOP_CARD_MAX_H = {"9:16": 22, "16:9": 80}   # a top card taller than this reaches the head
SCENES = ("flow", "race", "pile")   # picture scenes: parts land on their own words
ANIMS = ("counter", "steps", "versus", "logo", "keyword") + SCENES   # remotion/src/Anims.tsx
MIN_CARD_S = 0.5       # a card cut shorter than this by the next one is dropped


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
        # A transcriber can stretch one word over a pause or a misheard run; never hold past
        # a plausible spoken length plus a short tail.
        last = c[-1]
        end = min(last["end"], last["start"] + MAX_WORD_S) + HOLD_TAIL_S
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


def safe_box(box, aspect):
    """Move then shrink a card box so none of it sits under the app's UI."""
    l, t, r, b = SAFE[aspect]
    x, y, w, h = box
    # ponytail: fixed height cap, not a head measurement; measure the head if framings vary a lot
    w, h = min(w, 100 - l - r), min(h, 100 - t - b, TOP_CARD_MAX_H[aspect] if y < 50 else 100)
    x = min(max(x, l), 100 - r - w)
    y = min(max(y, t), 100 - b - h)
    return [x, y, w, h]


def logo_items(visuals, edit_dir, cap_y, aspect):
    """logo beats -> small logo cards just above the captions. They run in their own lane,
    so a logo can land while a bigger card is up. capture.mjs fetches the files."""
    out = []
    for v in visuals:
        if v.get("kind") != "logo":
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (v.get("brand") or v["word"]).lower()).strip("-")
        src = next((f"images/logo-{slug}.{e}" for e in ("svg", "png")
                    if edit_dir and (edit_dir / f"images/logo-{slug}.{e}").exists()), None)
        if not src:
            print(f"warning: no logo file for '{slug}', run capture.mjs first; skipped", file=sys.stderr)
            continue
        w = LOGO_BOX_H * (16 / 9 if aspect == "9:16" else 9 / 16)   # a square tile
        item = {k: v[k] for k in ("word", "nth", "entrance") if k in v}
        item.update({"anim": {"type": "logo", "props": {"src": src}}, "hold_s": v.get("hold_s", LOGO_S),
                     "box": v.get("box") or [50 - w / 2, cap_y - LOGO_BOX_H - 5, w, LOGO_BOX_H], "lane": "logo"})
        out.append(item)
    return out


def anim_items(visuals):
    """The built-animation beats of visuals.json as card items. Capture beats reach the
    plan through images.json (capture.mjs writes them there)."""
    out = []
    for v in visuals:
        if v.get("kind") != "anim":
            continue
        if v.get("type") not in ANIMS:
            print(f"warning: unknown anim type {v.get('type')!r} on '{v.get('word')}', skipped", file=sys.stderr)
            continue
        item = {k: v[k] for k in ("word", "nth", "box", "entrance", "hold_s") if k in v}
        item["anim"] = {"type": v["type"], "props": v.get("props") or {}}
        out.append(item)
    return out


def scene_parts(cards, words, edit_dir):
    """Fill in a scene's props, anywhere they nest: "icon" / "logo" -> "src" (the file capture.mjs
    fetched), "word" / "off_word" -> "at" / "off_at", seconds after the card lands. A word is the
    first time it is said once the card is up ("nth" picks a later time). No word: the scene staggers."""
    slug = lambda s: re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    def walk(node, card):
        if isinstance(node, list):
            for x in node:
                walk(x, card)
            return
        if not isinstance(node, dict):
            return
        if "icon" in node and "src" not in node:
            node["src"] = f"images/icon-{slug(node['icon'])}.svg"
        if "logo" in node and "src" not in node:
            s = slug(node["logo"])
            src = next((f"images/logo-{s}.{e}" for e in ("svg", "png")
                        if edit_dir and (Path(edit_dir) / f"images/logo-{s}.{e}").exists()), None)
            if src:
                node["src"] = src
            else:
                print(f"warning: no logo file for '{s}', run capture.mjs first", file=sys.stderr)
        for key, out in (("word", "at"), ("off_word", "off_at")):
            if key not in node:
                continue
            target = clean(node[key]).lower()
            hits = [w for w in words if clean(w["text"]).lower() == target and w["start"] >= card["start"]]
            n = node.get("nth", 1)
            if len(hits) < n:
                print(f"warning: '{node[key]}' is not said during the '{card['trigger_word']}' scene", file=sys.stderr)
                continue
            node[out] = round(hits[n - 1]["start"] - card["start"], 3)
            if card["start"] + node[out] > card["end"]:
                print(f"warning: '{node[key]}' lands after the '{card['trigger_word']}' scene ends; raise hold_s",
                      file=sys.stderr)
        for v in node.values():
            walk(v, card)

    for c in cards:
        if (c.get("anim") or {}).get("type") in SCENES:
            c["anim"] = json.loads(json.dumps(c["anim"]))   # never write back into visuals
            walk(c["anim"]["props"], c)
    return cards


def place_cards(images, words, duration, style, aspect):
    """images: image items and anim items (anim_items). Each group without "nth" takes the
    next time its word is said after that group's previous card."""
    hold, ent, box = card_defaults(style)
    out = []
    logos = [i for i in images if i.get("lane") == "logo"]
    images = [i for i in images if i.get("lane") != "logo"]
    for lane in ([i for i in images if "anim" not in i] + [i for i in images if "anim" in i], logos):
        cards = []
        for group in ([i for i in lane if "anim" not in i], [i for i in lane if "anim" in i]):
            cards += _place(group, words, duration, hold, ent, box, aspect)
        cards.sort(key=lambda c: c["start"])
        for a, b in zip(cards, cards[1:]):     # never two cards at once in a lane
            a["end"] = min(a["end"], b["start"])
        for c in cards:
            if c["end"] - c["start"] < MIN_CARD_S:
                print(f"warning: '{c['trigger_word']}' card cut to {c['end'] - c['start']:.2f} s by the next one, dropped",
                      file=sys.stderr)
        out += [c for c in cards if c["end"] - c["start"] >= MIN_CARD_S]
    return sorted(out, key=lambda c: c["start"])


def _place(images, words, duration, hold, ent, box, aspect):
    cards, after = [], -1.0
    for im in images:
        target = clean(im["word"]).lower()
        hits = [w for w in words if clean(w["text"]).lower() == target]
        if im.get("nth"):
            hits = hits[im["nth"] - 1:im["nth"]]
        else:
            hits = [w for w in hits if w["start"] > after]
        if not hits:
            print(f"warning: '{im['word']}' is never said after the previous card, "
                  f"skipped {im.get('src') or im['anim']['type']}", file=sys.stderr)
            continue
        start = round(max(0.0, hits[0]["start"] - CARD_LEAD_S), 3)
        card = {"src": im["src"]} if "src" in im else {"anim": im["anim"]}
        if im.get("lane"):
            card["lane"] = im["lane"]
        for k in ("highlight", "size"):
            if im.get(k):
                card[k] = im[k]
        card.update({"start": start, "end": round(min(duration, start + (im.get("hold_s") or hold)), 3),
                     "trigger_word": im["word"], "entrance": im.get("entrance", ent),
                     "box": safe_box(im.get("box") or box or DEFAULT_BOX[aspect], aspect)})
        cards.append(card)
        after = start
    return cards


HEAD_GAP = 2           # % kept between a card and the head (a zoom punch grows the head a little)
MIN_CARD_H = 9         # a card squeezed shorter than this above the head is dropped instead


def head_during(heads, step, start, end):
    """Union of the head boxes sampled while a card is up, as (left, top, right, bottom)."""
    bs = [h["box"] for h in heads if h["box"] and start - step <= h["t"] <= end]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs),
            max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs))


def avoid_heads(cards, face, cap_y, aspect):
    """Keep every card off the speaker's head (face.json from face.py). A top card shrinks to
    the band above the head; a logo drops below the chin or moves beside the head. A card
    that cannot fit is dropped: covering the face is worse than losing the visual."""
    if not face:
        return cards
    l_safe, _, r_safe, _ = SAFE[aspect]
    out = []
    for c in cards:
        hd = head_during(face["heads"], face.get("step_s", 0.5), c["start"], c["end"])
        x, y, w, h = c["box"]
        if hd is None or not (x < hd[2] and x + w > hd[0] and y < hd[3] and y + h > hd[1]):
            out.append(c)
            continue
        left, top, right, bottom = hd
        new = None
        if (c.get("anim") or {}).get("type") == "logo" and h < 20:
            if bottom + HEAD_GAP + h <= cap_y - 1:
                new = [x, bottom + HEAD_GAP, w, h]
            elif 100 - r_safe - (right + HEAD_GAP) >= w:
                new = [right + HEAD_GAP, (top + bottom - h) / 2, w, h]
            elif left - HEAD_GAP - l_safe >= w:
                new = [left - HEAD_GAP - w, (top + bottom - h) / 2, w, h]
        elif top - HEAD_GAP - y >= MIN_CARD_H:
            new = [x, y, w, top - HEAD_GAP - y]
        if new is None:
            print(f"warning: no room off the head for the '{c['trigger_word']}' card, dropped", file=sys.stderr)
            continue
        c["box"] = [round(v, 1) for v in new]
        out.append(c)
    return out


SFX_GAP_S = 0.25       # never two cues closer than this
SFX_EVERY_S = 1.5      # at most one cue per this many seconds, on average
SFX_RANK = ("hit", "whoosh-in", "whoosh-out", "pop", "zoom")   # who keeps its slot when cues crowd


def place_sfx(plan, words, kit):
    """Sound cues for the plan's visual events: a card lands (whoosh-in, a counter or a scene's tag
    gets the soft hit, a logo tile a pop), a card leaves while a sentence is still going (whoosh-out),
    a scene part lands on its word (pop), a zoom starts (zoom). A cue starts its attack early so its
    hit is heard on the event. kit: sfx.py's kit.json."""
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    ev = []

    def parts(node, key, start):
        if isinstance(node, list):
            for x in node:
                parts(x, key, start)
        elif isinstance(node, dict):
            if "at" in node and key != "label":   # a label swapping its text stays quiet
                ev.append((start + node["at"], "hit" if key == "tag" else "pop"))
            for k, v in node.items():
                parts(v, k, start)

    def mid_sentence(t):
        before = [w for w in words if w["end"] <= t + 0.05]
        return bool(before) and t - before[-1]["end"] < PAUSE_S and not ends_sentence(before[-1]["text"]) \
            and any(0 <= w["start"] - t < PAUSE_S for w in words)

    for c in plan["cards"]:
        kind = (c.get("anim") or {}).get("type")
        lands = c["start"] + CARD_LEAD_S
        ev.append((lands, "pop" if kind == "logo" else "hit" if kind == "counter" else "whoosh-in"))
        if kind != "logo" and mid_sentence(c["end"] - 0.15):   # the card fades out over its last 0.15 s
            ev.append((c["end"] - 0.15, "whoosh-out"))
        parts((c.get("anim") or {}).get("props"), None, c["start"])
    ev += [(z["start"], "zoom") for z in plan["zooms"]]

    duration = plan["durationInFrames"] / plan["fps"]
    budget = max(1, int(duration / SFX_EVERY_S))
    kept = []
    # ponytail: rank-then-time greedy, so a crowded video loses its LATER low-rank cues first;
    # spread the budget over time if that ever reads lopsided.
    for t, name in sorted(ev, key=lambda e: (SFX_RANK.index(e[1]), e[0])):
        if name in kit["cues"] and len(kept) < budget and 0 <= t < duration \
                and all(abs(t - k) >= SFX_GAP_S for k, _ in kept):
            kept.append((t, name))
    return [{"t": round(max(0.0, t - kit["cues"][n]["attack_s"]), 3), "src": f".sfx/{n}.wav", "event": round(t, 3)}
            for t, n in sorted(kept)]


def with_sfx(build):
    """Adds plan["sfx"] (place_sfx) to build()'s plan. Off when style.json has "sfx": false or
    there is no edit folder (sfx.py level-matches the kit to the folder's cut.mp4)."""
    sig = inspect.signature(build)

    def wrap(*a, **k):
        plan = build(*a, **k)
        v = sig.bind(*a, **k)
        v.apply_defaults()
        style, edit_dir = v.arguments["style"], v.arguments["edit_dir"]
        if style.get("sfx", True) is False or not edit_dir:
            plan["sfx"] = []
            return plan
        import sfx
        plan["sfx"] = place_sfx(plan, v.arguments["words"], sfx.kit(edit_dir))
        return plan
    return wrap


# Split layout: the visual owns a top panel, the speaker a window under the seam. In percent of the frame.
SPLIT = {"seam": 50, "ground": "#F4F4F2"}
SPLIT_GAP = 2          # art stops this far above the seam
SPLIT_CAP_BELOW = 4.5  # captions sit this far under the seam, over the top of the speaker's window
HEAD_ROOM = 4          # the top of the head (hair included) sits this far into the window
MIN_HEAD = 22          # a head shorter than this is scaled up to it, so a face is never tiny
MAX_SPEAKER_SCALE = 1.6
PANEL_T = 0.3          # the panel opens this long before a card lands (StyleEdit.tsx PANEL_T)
SPLIT_LOGO_S = 1.5     # a logo alone in the panel stays at least this long


def split_art_box(seam):
    """The part of the top panel clear of the app's UI and the seam: every split card fills it."""
    l, t, r, _ = SAFE["9:16"]
    return [l, t, 100 - l - r, seam - SPLIT_GAP - t]


def speaker_frame(face, seam):
    """How the cut sits in the window under the seam: scaled so the head is at least MIN_HEAD tall,
    moved so the hair sits HEAD_ROOM below the window's top and the head is centred left to right.
    x, y: how far the scaled video's top-left is pulled left and up, in % of the frame. origin: the
    head's centre on the video, for zooms."""
    win = 100 - seam
    bs = sorted((h["box"] for h in (face or {}).get("heads", []) if h["box"]), key=lambda b: b[1])
    if not bs:
        return {"scale": 1, "x": 0, "y": round(seam / 2, 1), "origin": [50, 40]}
    q = lambda xs, f: sorted(xs)[min(len(xs) - 1, int(f * len(xs)))]
    top = q([b[1] for b in bs], 0.1)                  # the highest the head goes, near enough
    bottom = q([b[1] + b[3] for b in bs], 0.9)
    cx = q([b[0] + b[2] / 2 for b in bs], 0.5)
    k = min(max(1, MIN_HEAD / max(1, bottom - top)), MAX_SPEAKER_SCALE)
    y = min(max(0, k * top - HEAD_ROOM), k * 100 - win)
    x = min(max(0, k * cx - 50), k * 100 - 100)
    if k * bottom - y > win:
        print("warning: the head is taller than the split window; the chin is cut off", file=sys.stderr)
    return {"scale": round(k, 3), "x": round(x, 1), "y": round(y, 1), "origin": [round(cx, 1), round((top + bottom) / 2, 1)]}


def split_cards(cards, art):
    """Every card fills the top panel's art box. A logo tile gets the panel to itself for a moment,
    unless a bigger card is up then (the panel is already showing the visual): that logo is dropped."""
    main = [c for c in cards if c.get("lane") != "logo"]
    out = []
    for c in cards:
        if c.get("lane") == "logo":
            if any(m["start"] - 2 * PANEL_T < c["end"] and c["start"] < m["end"] + 2 * PANEL_T for m in main):
                continue
            c = {k: v for k, v in c.items() if k != "lane"}
            nxt = min((m["start"] for m in main if m["start"] > c["start"]), default=c["end"] + 9)
            c["end"] = round(max(c["end"], min(c["start"] + SPLIT_LOGO_S, nxt - 2 * PANEL_T)), 3)
        out.append({**c, "box": list(art)})
    return sorted(out, key=lambda c: c["start"])


@with_sfx
def build(style, words, meta, images=(), aspect="auto", cuts=(), visuals=(), edit_dir=None, layout=None):
    words = [w for w in words if w.get("type", "word") == "word" and w["text"].strip()]
    if aspect == "auto":
        aspect = "9:16" if meta["height"] > meta["width"] else "16:9"
    width, height = SIZES[aspect]
    fps = round(meta["fps"]) or 30
    duration = meta["duration"]
    cap = dict(style.get("captions") or {})
    _, top, _, bottom = SAFE[aspect]
    cap["y_pct"] = min(max(cap.get("y_pct") or 70, top + 5), 100 - bottom - 4)   # clear of the app's UI
    chunks = chunk_captions(words, cap.get("words_per_caption") or 3, cap.get("case", "sentence")) \
        if cap.get("present", True) else []
    fj = edit_dir and Path(edit_dir) / "face.json"
    face = json.loads(fj.read_text()) if fj and fj.exists() else None
    lay = {**SPLIT, **(style.get("layout") or {}), **(layout or {})}
    if lay.get("mode", "overlay") == "split":
        if aspect != "9:16":
            sys.exit("ERROR: the split layout is vertical only; use --layout overlay for 16:9")
        seam = lay["seam"]
        art = split_art_box(seam)
        full_y = cap["y_pct"]   # where captions sit while the speaker has the whole frame
        cap["y_pct"] = min(seam + SPLIT_CAP_BELOW, 100 - bottom - 4)
        cards = place_cards(list(images) + anim_items(visuals) + logo_items(visuals, edit_dir, cap["y_pct"], aspect),
                            words, duration, style, aspect)
        return {"video": meta["video"], "width": width, "height": height, "fps": fps,
                "durationInFrames": int(duration * fps),
                "layout": {"mode": "split", "ground": lay["ground"], "seam": seam, "art": art,
                           "speaker": speaker_frame(face, seam), "caption_full_y": full_y},
                "captions": {"style": cap, "chunks": chunks},
                "zooms": place_zooms(style.get("zoom") or {}, words, duration, list(cuts)),
                "cards": scene_parts(split_cards(cards, art), words, edit_dir)}
    return {"video": meta["video"], "width": width, "height": height, "fps": fps,
            "durationInFrames": int(duration * fps),
            "captions": {"style": cap, "chunks": chunks},
            "zooms": place_zooms(style.get("zoom") or {}, words, duration, list(cuts)),
            "cards": scene_parts(avoid_heads(place_cards(list(images) + anim_items(visuals)
                                             + logo_items(visuals, edit_dir, cap["y_pct"], aspect),
                                             words, duration, style, aspect),
                                 face, cap["y_pct"], aspect), words, edit_dir)}


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
    face = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 30, 40, 30]}, {"t": 0.5, "box": [30, 31, 40, 30]}]}
    top = {"start": 0.0, "end": 1.0, "box": [10, 15, 74, 22], "trigger_word": "a"}
    logo = {"start": 0.0, "end": 1.0, "box": [42, 50, 16, 9], "trigger_word": "b", "anim": {"type": "logo"}}
    tiny = {"start": 0.0, "end": 1.0, "box": [10, 25, 74, 22], "trigger_word": "c"}
    got = avoid_heads([top, logo, tiny], face, 68, "9:16")
    assert got[0]["box"] == [10, 15, 74, 13], got[0]["box"]           # shrunk to above the head
    lx, _, lw, _ = got[1]["box"]
    assert (lx + lw <= 30 or lx >= 70) and len(got) == 2, got         # logo beside the head; tiny dropped
    assert safe_box([6, 3, 88, 27], "9:16") == [6, 14, 80, 22], safe_box([6, 3, 88, 27], "9:16")
    assert safe_box([50, 90, 20, 10], "9:16")[1] == 68
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
    vis = [{"word": "zooms", "kind": "anim", "type": "keyword", "props": {"text": "zooms"}},
           {"word": "today", "kind": "anim", "type": "nope"},
           {"word": "edit", "kind": "capture", "url": "https://example.com"}]
    a = build(style, words, meta, imgs, visuals=vis)["cards"]
    assert [c.get("src") or c["anim"]["type"] for c in a] == ["keyword", "images/n.png"], a
    zooms_w = next(w for w in words if w["text"] == "zooms")
    assert abs(a[0]["start"] - (zooms_w["start"] - 0.1)) < 1e-6 and "src" not in a[0]
    assert a[0]["anim"] == {"type": "keyword", "props": {"text": "zooms"}}
    assert a[0]["end"] <= a[1]["start"], "two cards at once"
    sc = [{"word": "every", "kind": "anim", "type": "flow", "hold_s": 3,
           "props": {"nodes": [{"icon": "mail", "word": "video"}, {"label": "x", "word": "zooms", "off_word": "captions"}]}}]
    f = next(c for c in build(style, words, meta, visuals=sc)["cards"] if c["anim"]["type"] == "flow")
    every = next(w for w in words if w["text"] == "every")
    n0, n1 = f["anim"]["props"]["nodes"]
    assert n0["src"] == "images/icon-mail.svg" and abs(n0["at"] - (every["start"] + 0.35 - f["start"])) < 1e-6, f
    assert n1["off_at"] > n1["at"] > n0["at"] and "at" not in sc[0]["props"]["nodes"][0], f
    sp_face = {"step_s": 0.5, "heads": [{"t": 0.0, "box": [30, 31, 30, 29]}, {"t": 0.5, "box": None}]}
    fr = speaker_frame(sp_face, 50)
    assert fr["scale"] == 1 and fr["y"] == 27 and 31 - fr["y"] == HEAD_ROOM, fr      # hair HEAD_ROOM into the window
    assert abs(speaker_frame({"heads": [{"t": 0, "box": [45, 40, 10, 15]}]}, 50)["scale"] - MIN_HEAD / 15) < 1e-3   # small head scaled up
    assert speaker_frame(None, 50)["y"] == 25
    lg = {"start": 5.0, "end": 6.2, "box": [1, 1, 1, 1], "trigger_word": "l", "lane": "logo", "anim": {"type": "logo"}}
    big = {"start": 0.0, "end": 4.0, "box": [1, 1, 1, 1], "trigger_word": "b"}
    art = split_art_box(50)
    assert art == [6, 14, 80, 34]
    sc2 = split_cards([big, lg, {**lg, "start": 3.5, "end": 4.7}], art)
    assert [c["box"] for c in sc2] == [art, art] and "lane" not in sc2[1] and sc2[1]["end"] == 6.5, sc2   # overlapping logo dropped
    vs = build(style, words, {**meta, "width": 1080, "height": 1920}, imgs, layout={"mode": "split"})
    assert vs["layout"]["mode"] == "split" and vs["captions"]["style"]["y_pct"] == 50 + SPLIT_CAP_BELOW
    assert all(c["box"] == art for c in vs["cards"]) and "layout" not in p
    kit = {"cues": {n: {"attack_s": 0.2} for n in SFX_RANK}}
    sp = {"fps": 30, "durationInFrames": 300, "zooms": [{"start": 1.25}, {"start": 6.0}],
          "cards": [{"start": 1.0, "end": 3.0, "anim": {"type": "flow", "props": {"nodes": [{"at": 0.5}, {"at": 0.6}],
                                                                                   "tag": {"at": 1.5}}}},
                    {"start": 7.0, "end": 8.0, "src": "images/a.png"}]}
    sw = [{"text": t, "start": s, "end": s + 0.2} for t, s in (("a", 2.6), ("b", 2.9), ("c.", 7.5))]
    cues = place_sfx(sp, sw, kit)
    ev = [(c["event"], c["src"]) for c in cues]
    assert ev == [(1.1, ".sfx/whoosh-in.wav"), (1.5, ".sfx/pop.wav"), (2.5, ".sfx/hit.wav"),
                  (2.85, ".sfx/whoosh-out.wav"), (6.0, ".sfx/zoom.wav"), (7.1, ".sfx/whoosh-in.wav")], ev
    assert all(abs(c["t"] - (c["event"] - 0.2)) < 1e-6 for c in cues)   # started early by the attack
    assert all(b["event"] - a["event"] >= SFX_GAP_S for a, b in zip(cues, cues[1:]))   # 1.25 zoom and 1.6 pop lost
    sp["durationInFrames"] = 90   # 3 s: room for 2 cues, the highest ranked
    assert [c["src"] for c in place_sfx(sp, sw, kit)] == [".sfx/whoosh-in.wav", ".sfx/hit.wav"]
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    ap = argparse.ArgumentParser()
    ap.add_argument("style")
    ap.add_argument("words")
    ap.add_argument("--images")
    ap.add_argument("--aspect", choices=["auto", "9:16", "16:9"], default="auto")
    ap.add_argument("--layout", choices=["overlay", "split"], help="default: style.json layout.mode, else overlay")
    ap.add_argument("--out")
    ap.add_argument("--no-sfx", action="store_true", help="no sound cues (same as \"sfx\": false in style.json)")
    a = ap.parse_args()
    edit_dir = Path(a.words).resolve().parent
    video = edit_dir / "cut.mp4"
    if not video.exists():
        sys.exit(f"ERROR: no cut.mp4 in {edit_dir}. Run the cut skill first.")
    img = Path(a.images) if a.images else edit_dir / "images.json"
    images = json.loads(img.read_text()) if img.exists() else []
    vis = edit_dir / "visuals.json"
    visuals = json.loads(vis.read_text()) if vis.exists() else []
    plan = build(json.loads(Path(a.style).read_text()), json.loads(Path(a.words).read_text()),
                 probe(video), images, a.aspect, cut_points(edit_dir), visuals, edit_dir,
                 {"mode": a.layout} if a.layout else None)
    if a.no_sfx:
        plan["sfx"] = []
    out = Path(a.out) if a.out else edit_dir / "plan.json"
    out.write_text(json.dumps(plan, indent=1))
    print(f"{out}: {plan['width']}x{plan['height']}, {plan['durationInFrames'] / plan['fps']:.1f} s, "
          f"{len(plan['captions']['chunks'])} captions, {len(plan['zooms'])} zooms, {len(plan['cards'])} cards")


if __name__ == "__main__":
    main()
