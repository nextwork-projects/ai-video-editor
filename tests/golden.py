#!/usr/bin/env python3
"""Golden stills: the renderer's look, pinned. Catches a change that moves, recolours or drops a card,
a caption or the footage without anyone looking.

    ~/.ai-video-editor/venv/bin/python tests/golden.py            render, compare with tests/golden/<os>/
    ~/.ai-video-editor/venv/bin/python tests/golden.py --update   render, overwrite tests/golden/<os>/
    ~/.ai-video-editor/venv/bin/python tests/golden.py --out DIR  also keep the fresh stills and diffs in DIR
    python tests/golden.py demo                                   self-check of the diff, and the default look
                                                                  planned with no banned AI tell; no renderer

Makes a 5 s test video, captions and three overlay cards that need no network capture (chat,
terminal, toasts), plans it without sound, renders the stills and compares four of them with the
references. Needs numpy + OpenCV (the venv) and the renderer (setup.py remotion).

The diff, and why it passes a font rasterised a little differently but fails a real change:
both images are shrunk to 135x240 (area average), so a glyph edge that moved a pixel moves an
eighth of one. Then, per 15x15 tile (an eighth of the width), the mean absolute difference in any
channel. A tile over TILE_MAX means something in that area changed: a card missing or moved, a
caption gone, a colour swapped. Text that reflows to a different line width moves whole words,
which also lands over it.

Each OS rasterises fonts its own way (Linux moves a chat bubble's text enough to cross TILE_MAX), so
the references are per OS: tests/golden/linux/ (CI, from the golden-out artifact or --update on
Linux), tests/golden/darwin/ (made on a Mac). An OS with no set fails and says to run --update there.
Every run also proves the threshold still bites on the real stills: the fresh still moved down 24 px
(a card moved) and with its middle third blanked (a card gone) must both fail against the reference.
"""
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / "plugins" / "ai-editor" / "skills" / "style-edit" / "scripts"
GOLDEN = Path(__file__).resolve().parent / "golden" / platform.system().lower()   # linux, darwin, windows
STILLS = ("1-opening", "4-card", "5-card", "6-card")
SMALL = (135, 240)       # w, h the diff runs at
KEEP = (270, 480)        # w, h the references are stored at (small enough for the repo)
TILE = 15
TILE_MAX = 10.0          # mean abs difference (0-255) in one tile; a card or caption changing is 30+


def diff(a, b):
    """(worst tile difference, (x, y) of that tile) between two BGR images of any size."""
    import cv2
    import numpy as np
    a, b = (cv2.resize(x, SMALL, interpolation=cv2.INTER_AREA).astype(np.float32) for x in (a, b))
    d = np.abs(a - b).max(axis=2)
    h, w = d.shape
    t = d[:h // TILE * TILE, :w // TILE * TILE].reshape(h // TILE, TILE, w // TILE, TILE).mean(axis=(1, 3))
    y, x = np.unravel_index(int(t.argmax()), t.shape)
    return float(t.max()), (int(x) * TILE, int(y) * TILE)


def run(*cmd, cwd):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"GOLDEN FAIL: {Path(str(cmd[1])).name if len(cmd) > 1 else cmd[0]} exited {r.returncode}\n{r.stdout[-2000:]}{r.stderr[-2000:]}")


def make_plan(work):
    """The golden edit, planned with the defaults (no look, no brand): returns its edit folder."""
    edit = work / "edits" / "golden"
    edit.mkdir(parents=True)
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=5",
        "-f", "lavfi", "-i", "sine=f=220:d=5", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", edit / "cut.mp4", cwd=work)
    words = [{"text": t, "start": round(0.3 + i * 0.4, 2), "end": round(0.3 + i * 0.4 + 0.3, 2), "type": "word"}
             for i, t in enumerate("so this is ten times faster in three steps comment now".split())]
    (edit / "captions.json").write_text(json.dumps(words))
    (work / "style.json").write_text(json.dumps({
        "handle": "golden", "sfx": False, "pace": {"max_pause_s": 0.2},
        "zoom": {"per_min": 0, "kind": "punch", "scale": 1.15, "on": "sentence_start"},
        "captions": {"present": True, "words_per_caption": 2, "y_pct": 68, "size_pct": 5, "case": "lower",
                     "font_match": "Inter", "weight": 800, "color": "#FFFFFF", "stroke": True}}))
    (edit / "visuals.json").write_text(json.dumps([
        {"word": "ten", "nth": 1, "kind": "anim", "type": "chat", "hold_s": 1.0,
         "props": {"app": "Router", "messages": [{"from": "user", "text": "ten times faster", "word": "ten"},
                                                 {"from": "app", "text": "yes", "word": "faster"}]}},
        {"word": "three", "nth": 1, "kind": "anim", "type": "terminal", "hold_s": 1.0,
         "props": {"title": "zsh", "lines": [{"text": "make plan build ship", "kind": "cmd", "word": "three"}]}},
        {"word": "comment", "nth": 1, "kind": "anim", "type": "toasts", "hold_s": 0.9,
         "props": {"items": [{"app": "Inbox", "title": "comment now", "word": "comment"}]}},
    ]))
    run(sys.executable, SK / "plan.py", work / "style.json", edit / "captions.json", "--no-sfx", cwd=work)
    return edit


def render(work):
    edit = make_plan(work)
    run(sys.executable, SK / "edit.py", "stills", edit, "--no-check", cwd=work)
    return edit / "stills"


def banned(edit, stills=None):
    """The default look must carry no banned AI tell (references/ai-tells.md): plan side, and on the stills."""
    sys.path.insert(0, str(SK))
    from ai_tells import check_plan, check_stills
    plan = json.loads((edit / "plan.json").read_text())
    found = check_plan(plan) + (check_stills(stills, plan) if stills else [])
    return [f"{f['tell']}: {f['where']}" for f in found if f["level"] == "BAN"]


def demo():
    import numpy as np
    import cv2
    base = np.full((960, 540, 3), 90, np.uint8)
    cv2.rectangle(base, (60, 150), (480, 300), (30, 30, 30), -1)
    cv2.putText(base, "card", (180, 250), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 5)
    assert diff(base, base)[0] == 0
    aa = cv2.GaussianBlur(base, (3, 3), 0)                          # anti-aliasing drift: passes
    assert diff(base, aa)[0] < TILE_MAX, diff(base, aa)
    shifted = np.roll(base, 1, axis=1)                              # one pixel off: passes
    assert diff(base, shifted)[0] < TILE_MAX, diff(base, shifted)
    gone = base.copy()
    gone[150:300, 60:480] = 90                                      # the card missing: fails, at the card
    worst, (x, y) = diff(base, gone)
    assert worst > TILE_MAX and 60 / 4 - TILE <= x <= 480 / 4 and 150 / 4 - TILE <= y <= 300 / 4, (worst, x, y)
    moved = np.roll(base, 40, axis=0)                               # moved 40 px down: fails
    assert diff(base, moved)[0] > TILE_MAX
    recolour = base.copy()
    recolour[150:300, 60:480] = (30, 30, 200)                       # panel turned red: fails
    assert diff(base, recolour)[0] > TILE_MAX
    with tempfile.TemporaryDirectory() as t:
        edit = make_plan(Path(t))
        assert banned(edit) == [], banned(edit)                     # the default look has no banned tell
        plan = json.loads((edit / "plan.json").read_text())
        plan["look"] = {"preset": "neutral", "ground": "linear-gradient(135deg,#6366F1,#8B5CF6)"}
        (edit / "plan.json").write_text(json.dumps(plan))
        assert any("purple-blue" in b for b in banned(edit)), banned(edit)   # and the check can fail
    print("demo ok")


def main():
    if sys.argv[1:] == ["demo"]:
        return demo()
    import argparse
    import cv2
    import numpy as np
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="overwrite tests/golden/<os>/ with this render")
    ap.add_argument("--out", help="keep the fresh stills and the diff images here")
    a = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="ave-golden-"))
    try:
        compare(a, work)
    except BaseException:
        print(f"GOLDEN: kept the work folder for a look: {work}", file=sys.stderr)
        raise
    shutil.rmtree(work, ignore_errors=True)
    print("GOLDEN OK" if not a.update else "golden stills updated")


def compare(a, work):
    import cv2
    import numpy as np
    stills = render(work)
    ban = banned(stills.parent, stills)
    if ban:
        sys.exit("GOLDEN FAIL: the default look carries a banned AI tell: " + "; ".join(ban))
    out = Path(a.out).resolve() if a.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)
    bad = []
    for n in STILLS:
        f = stills / f"{n}.png"
        if not f.exists():
            sys.exit(f"GOLDEN FAIL: no {f.name} in {stills} (still names changed? update STILLS)")
        img = cv2.imread(str(f))
        small = cv2.resize(img, KEEP, interpolation=cv2.INTER_AREA)
        if out:
            cv2.imwrite(str(out / f"{n}.png"), small)
        ref = GOLDEN / f"{n}.png"
        if a.update:
            GOLDEN.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(ref), small)
            print(f"updated {ref}")
            continue
        if not ref.exists():
            sys.exit(f"GOLDEN FAIL: {ref} missing: no references for {platform.system()} yet. "
                     f"Run with --update on {platform.system()} and commit {GOLDEN.relative_to(ROOT).as_posix()}/")
        ref_img = cv2.imread(str(ref))
        worst, (x, y) = diff(ref_img, small)
        moved = diff(ref_img, np.roll(small, 24, axis=0))[0]
        gone = small.copy()
        gone[KEEP[1] // 3:KEEP[1] * 2 // 3] = small.mean(axis=(0, 1)).astype(np.uint8)
        gone = diff(ref_img, gone)[0]
        if moved <= TILE_MAX or gone <= TILE_MAX:
            sys.exit(f"GOLDEN FAIL: TILE_MAX {TILE_MAX} is too loose on {n}: a moved still scores {moved:.1f}, "
                     f"a blanked one {gone:.1f}; both must fail")
        print(f"{n}: worst tile {worst:.1f} (max {TILE_MAX}) at {x * 4},{y * 4} px of 540x960")
        if worst > TILE_MAX:
            bad.append(n)
            if out:
                cv2.imwrite(str(out / f"{n}-diff.png"), cv2.absdiff(cv2.imread(str(ref)), small) * 4)
    if bad:
        sys.exit(f"GOLDEN FAIL on {platform.system()}: {', '.join(bad)} differ. Look at them"
                 + (f" in {out}" if out else " (--out DIR keeps them)") + "; if the change is intended, run --update.")


if __name__ == "__main__":
    main()
