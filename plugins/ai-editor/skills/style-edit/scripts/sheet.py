#!/usr/bin/env python3
"""The stills as one numbered contact sheet: the one image to review.

    python sheet.py edits/NAME [--plan plan.json]   stills/ -> stills/sheet.png (stills-XYZ/ for plan-XYZ.json)
    python sheet.py demo                            self-check

Tiles run in time order, numbered 1..n. Each is labelled with its number, what it shows (opening,
caption, zoom, card N = plan.cards[N-1], early / late / swap), its time in the edit and the card's
kind (capture, image, logo, or the anim type). The sheet's long edge is LONG_EDGE px, so it is read
at full size and costs about the same as ONE full still. The full-size stills stay on disk beside it
for a zoom-in on any tile that needs a closer look. Needs Pillow (the venv has it).
"""
import json
import math
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from edit import still_frames  # noqa: E402

LONG_EDGE = 1568        # Claude reads images up to 1568 px on the long edge without shrinking them
TOKENS_CAP = 1600       # ...and about 1.15 MP, which is about 1,600 tokens: the most one image costs
LABEL = 0.075           # label strip height, as a share of the tile width
GAP = 6


def tokens(w, h):
    """Image tokens Claude spends on a w x h image: shrunk to LONG_EDGE, then w*h/750, capped."""
    s = min(1.0, LONG_EDGE / max(w, h))
    return min(TOKENS_CAP, round(w * s * h * s / 750))


def grid(n, tw, th, long_edge=LONG_EDGE):
    """(cols, scale) that makes the tiles biggest inside a long_edge x long_edge bound."""
    best = (1, 0.0)
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        s = min((long_edge - (cols + 1) * GAP) / (cols * tw),
                (long_edge - (rows + 1) * GAP) / (rows * (th + LABEL * tw)))
        if s > best[1]:
            best = (cols, s)
    return best


def kind(card):
    if card.get("lane") == "logo":
        return "logo"
    if card.get("src"):
        return "capture" if "capture" in Path(card["src"]).name else "image"
    return (card.get("anim") or {}).get("type", "card")


def labels(plan):
    """still name -> 'role  12.34s  kind' ("card 2 early" is plan.cards[1]), in time order."""
    out = {}
    frames = still_frames(plan)
    for name in sorted(frames, key=lambda n: (frames[n], n)):
        m = re.match(r"(\d+)-(card|swap)(.*)", name)
        if m:
            role = f"{m.group(2)} {int(m.group(1)) - 3}{m.group(3).replace('-', ' ')}"
            k = kind(plan["cards"][int(m.group(1)) - 4])
        else:
            role, k = name.split("-", 1)[1], ""
        out[name] = f"{role}  {frames[name] / plan['fps']:.2f}s  {k}".rstrip()
    return out


def build(stills, plan, out):
    from PIL import Image, ImageDraw, ImageFont
    lab = stills / "labels.json"     # edit.py stills --at writes its own labels: the moments asked for
    names = json.loads(lab.read_text()) if lab.exists() else labels(plan)
    files = [(n, stills / f"{n}.png") for n in names if (stills / f"{n}.png").exists()]
    if not files:
        sys.exit(f"ERROR: no stills in {stills}")
    def load(f):                       # closed straight away: Windows cannot delete an open file
        with Image.open(f) as im:
            im.load()
            return im.convert("RGB")
    tw, th = load(files[0][1]).size
    cols, s = grid(len(files), tw, th)
    s = min(s, 1.0)                    # never blow small stills up
    w, h = max(1, int(tw * s)), max(1, int(th * s))
    lh = max(14, int(LABEL * tw * s))
    rows = math.ceil(len(files) / cols)
    sheet = Image.new("RGB", (cols * w + (cols + 1) * GAP, rows * (h + lh) + (rows + 1) * GAP), "#202020")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=max(10, int(lh * 0.7)))
    except TypeError:            # Pillow < 10.1 has one fixed-size bitmap font
        font = ImageFont.load_default()
    before, tiles = 0, []
    for i, (name, f) in enumerate(files):
        x = GAP + (i % cols) * (w + GAP)
        y = GAP + (i // cols) * (h + lh + GAP)
        tiles.append(f"{i + 1}  {names[name]}")
        draw.text((x + 3, y + 1), tiles[-1], fill="#FFFFFF", font=font)
        im = load(f)
        before += tokens(*im.size)
        sheet.paste(im.resize((w, h), Image.LANCZOS), (x, y + lh))
    sheet.save(out, optimize=True)
    return {"sheet": str(out), "stills": len(files), "size": sheet.size, "tiles": tiles,
            "tokens_sheet": tokens(*sheet.size), "tokens_stills": before}


def demo():
    import tempfile
    from PIL import Image
    assert tokens(1080, 1920) == TOKENS_CAP and tokens(400, 300) == 160
    cols, s = grid(27, 1080, 1920)
    rows = math.ceil(27 / cols)
    assert 1500 < max(cols * 1080 * s + (cols + 1) * GAP, rows * (1920 + LABEL * 1080) * s + (rows + 1) * GAP) <= 1568
    assert grid(1, 1080, 1920)[0] == 1
    plan = {"fps": 30, "durationInFrames": 300, "zooms": [], "captions": {"chunks": [{"start": 0, "end": 0.4}]},
            "cards": [{"start": 2, "end": 5, "src": "images/capture-1-x.png"},
                      {"start": 6, "end": 8, "anim": {"type": "race"}}]}
    lab = labels(plan)
    assert lab["4-card"].endswith("capture") and lab["5-card-late"] == "card 2 late  7.70s  race", lab
    assert lab["1-opening"] == "opening  0.50s", lab
    # time order (the caption at 0.50 s sorts with the opening, not after it by name); no zoom, no gap
    times = [float(v.split("  ")[1].rstrip("s")) for v in lab.values()]
    assert times == sorted(times), lab
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        for n in lab:
            Image.new("RGB", (540, 960), (200, 30, 30)).save(d / f"{n}.png")
        r = build(d, plan, d / "sheet.png")
        assert max(r["size"]) <= LONG_EDGE + 1 and r["stills"] == len(lab), r
        assert [int(t.split()[0]) for t in r["tiles"]] == list(range(1, len(lab) + 1)), r["tiles"]
        assert r["tiles"][0] == "1  caption  0.20s", r["tiles"]
        assert r["tokens_sheet"] < r["tokens_stills"], r
        with Image.open(d / "sheet.png") as im:
            assert im.getpixel((GAP + 5, GAP + 40))[0] == 200            # a tile, under its label
        # edit.py stills --at: its labels.json names the tiles
        (d / "at").mkdir()
        Image.new("RGB", (540, 960), (30, 30, 200)).save(d / "at" / "t0015.40.png")
        (d / "at" / "labels.json").write_text(json.dumps({"t0015.40": "15.40s  card 1 logo 'x'"}))
        assert build(d / "at", plan, d / "at" / "sheet.png")["tiles"] == ["1  15.40s  card 1 logo 'x'"]
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("edit")
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--dir", help="the stills folder (default stills/; edit.py stills --at uses stills-at/)")
    a = ap.parse_args()
    edit = Path(a.edit).resolve()
    plan_path = edit / a.plan
    stills = edit / (a.dir or f"stills{plan_path.stem[len('plan'):]}")
    r = build(stills, json.loads(plan_path.read_text()), stills / "sheet.png")
    print(json.dumps(r))


if __name__ == "__main__":
    main()
