#!/usr/bin/env python3
"""Full-frame-rate filmstrip around a moment, plus an optional entrance measurement.

Usage:
  strip.py <handle> <id> <t> [--before 0.4] [--after 0.8] [--crop x0,y0,x1,y1] [--measure x0,y0,x1,y1]

  <t>        seconds. Every source frame from t-before to t+after is tiled 8 per row,
             each labelled with its frame number and exact time (30 fps sources).
  --crop     % of frame to show (default whole frame). Use it to zoom on a card.
  --measure  % box of the card's resting position. Prints, per frame:
               prog  = how far the box has moved from the first frame toward the last
                       (0 = looks like the first frame, 1 = looks like the last)
               bbox  = box of pixels that differ from the first frame (% of frame)
             Reading it: cut = prog jumps 0 to 1 in one frame. fade = bbox full-size
             from the first changed frame while prog ramps. scale/pop = bbox grows
             around a fixed centre (overshoot if prog passes 1 then settles). slide =
             bbox keeps its size and moves. Pick t so the window starts BEFORE the card
             and ends AFTER it settles.
Downloads the video to audio/<id>.mp4 first if it is not there (fetch.py keeps only
the audio). Writes creator-teardowns/<handle>/strips/<id>_<t>.jpg and prints its path.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path.cwd() / 'creator-teardowns'


def box(arg, w, h):
    x0, y0, x1, y1 = (float(v) for v in arg.split(','))
    return int(x0 / 100 * w), int(y0 / 100 * h), int(x1 / 100 * w), int(y1 / 100 * h)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('handle'); ap.add_argument('id'); ap.add_argument('t', type=float)
    ap.add_argument('--before', type=float, default=0.4); ap.add_argument('--after', type=float, default=0.8)
    ap.add_argument('--crop'); ap.add_argument('--measure')
    a = ap.parse_args()
    src = ROOT / a.handle / 'audio' / f'{a.id}.mp4'
    if not src.exists():
        urls = {v['id']: v['webpage_url'] for v in json.loads((ROOT / a.handle / 'videos.json').read_text(encoding="utf-8"))['videos']}
        if a.id not in urls: sys.exit(f'{a.id} not in videos.json')
        subprocess.run(['yt-dlp', '-f', 'b[ext=mp4]/b', '--no-warnings', '-o', str(src), urls[a.id]], check=True)
    strips = ROOT / a.handle / 'strips'
    t0 = max(0.0, a.t - a.before); dur = a.before + a.after
    tmp = strips / f'_{a.id}_{a.t:.2f}'
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob('*.png'): f.unlink()
    subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{t0:.3f}', '-i', str(src), '-t', f'{dur:.3f}',
                    '-vf', 'fps=30', str(tmp / 'f_%03d.png')], check=True)
    frames = sorted(tmp.glob('f_*.png'))
    if not frames: sys.exit('no frames')
    ims = [Image.open(f).convert('RGB') for f in frames]
    W, H = ims[0].size
    times = [t0 + i / 30 for i in range(len(ims))]

    if a.measure:
        x0, y0, x1, y1 = box(a.measure, W, H)
        arr = [np.asarray(im, dtype=np.int16)[y0:y1, x0:x1] for im in ims]
        first, last = arr[0], arr[-1]
        span = np.abs(last - first).mean() + 1e-6
        print('frame  time     prog   bbox(% of frame) of pixels changed vs first frame')
        for i, (t, fr) in enumerate(zip(times, arr)):
            prog = 1 - np.abs(fr - last).mean() / span
            m = np.abs(fr - first).max(2) > 40
            if m.sum() > 50:
                ys, xs = np.where(m)
                bb = (f'{(x0 + xs.min()) / W * 100:5.1f},{(y0 + ys.min()) / H * 100:5.1f},'
                      f'{(x0 + xs.max()) / W * 100:5.1f},{(y0 + ys.max()) / H * 100:5.1f}')
            else:
                bb = '-'
            print(f'{round(t * 30):5d}  {t:7.3f}  {prog:5.2f}  {bb}')

    if a.crop:
        c = box(a.crop, W, H); ims = [im.crop(c) for im in ims]
    tw = 216; th = int(ims[0].height * tw / ims[0].width)
    cols = 8; rows = -(-len(ims) // cols)
    sheet = Image.new('RGB', (cols * tw, rows * (th + 22)), 'black')
    d = ImageDraw.Draw(sheet); font = ImageFont.load_default(size=15)
    for i, (im, t) in enumerate(zip(ims, times)):
        x, y = (i % cols) * tw, (i // cols) * (th + 22)
        sheet.paste(im.resize((tw, th)), (x, y + 22))
        d.text((x + 3, y + 3), f'f{round(t * 30)} {t:.3f}s', fill='yellow', font=font)
    out = strips / f'{a.id}_{a.t:.2f}.jpg'
    sheet.save(out, quality=80)
    for f in frames: f.unlink()
    tmp.rmdir()
    print(out, f'{len(ims)} frames')


if __name__ == '__main__':
    main()
