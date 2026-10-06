"""Contact sheet of template stills: one row per case, its 4 stills side by side.
    python3 test/sheet.py <stills dir> <out.png> [name-substring ...]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw

src, out, only = Path(sys.argv[1]), sys.argv[2], sys.argv[3:]
names = sorted({p.name.rsplit("-", 1)[0] for p in src.glob("*-0.png")})
names = [n for n in names if not only or any(o in n for o in only)]
H, LABEL, GAP = 300, 28, 8
rows = []
for n in names:
    ims = [Image.open(src / f"{n}-{i}.png").convert("RGB") for i in range(4)]
    ims = [im.resize((int(im.width * H / im.height), H)) for im in ims]
    row = Image.new("RGB", (sum(i.width for i in ims) + GAP * 3, H + LABEL), "#1a1a1a")
    x = 0
    for im in ims:
        row.paste(im, (x, LABEL)); x += im.width + GAP
    ImageDraw.Draw(row).text((6, 6), n, fill="#eeeeee")
    rows.append(row)
cols = 2
W = max(r.width for r in rows)
sheet = Image.new("RGB", (W * cols + GAP, sum(r.height + GAP for r in rows[::cols])), "#0d0d0d")
y = 0
for i in range(0, len(rows), cols):
    for j, r in enumerate(rows[i:i + cols]):
        sheet.paste(r, (j * (W + GAP), y))
    y += max(r.height for r in rows[i:i + cols]) + GAP
sheet.save(out)
print(out, sheet.size)
