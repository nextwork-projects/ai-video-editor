#!/usr/bin/env python3
"""End-to-end smoke test: the whole editor on a made-up 4 s video, on whatever OS runs it.

    python tests/smoke.py        (after setup.py venv, model and remotion)

Makes a vertical test video with ffmpeg, then runs every step a learner runs: transcribe,
capture (an icon, a logo and a real page), face, sound, plan in both layouts, stills and a
render. Fails loudly at the first broken step. CI runs it on Mac, Windows and Linux.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SK = ROOT / "plugins" / "ai-editor" / "skills"
HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
VPY = HOME / "venv" / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
PY = sys.executable


def run(*cmd, cwd):
    print("$", " ".join(map(str, cmd)), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd)
    if r.returncode:
        sys.exit(f"SMOKE FAIL: exit {r.returncode} from {cmd[1] if len(cmd) > 1 else cmd[0]}")


def main():
    work = Path(tempfile.mkdtemp(prefix="ave-smoke-"))
    edit = work / "edits" / "smoke"
    edit.mkdir(parents=True)
    # A 4 s vertical clip with a tone, the shape of a phone video.
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=540x960:r=30:d=4",
        "-f", "lavfi", "-i", "sine=f=220:d=4", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", edit / "cut.mp4", cwd=work)
    # The transcriber loads and runs (a tone has no words; loading the model is the test).
    run(VPY, SK / "cut/scripts/transcribe.py", edit / "cut.mp4", edit / "words.raw.json",
        "--engine", "whisper", cwd=work)
    words = [{"text": t, "start": round(0.3 + i * 0.45, 2), "end": round(0.3 + i * 0.45 + 0.35, 2), "type": "word"}
             for i, t in enumerate("so notion is 10x faster than email now".split())]
    (edit / "captions.json").write_text(json.dumps(words))
    style = {"handle": "smoke", "pace": {"max_pause_s": 0.2}, "zoom": {"per_min": 20, "kind": "punch", "scale": 1.15,
             "on": "sentence_start"}, "captions": {"present": True, "words_per_caption": 2, "y_pct": 68, "size_pct": 5,
             "case": "lower", "font_match": "Inter", "weight": 800, "color": "#FFFFFF", "stroke": True}}
    (work / "style.json").write_text(json.dumps(style))
    (edit / "visuals.json").write_text(json.dumps([
        {"word": "notion", "nth": 1, "kind": "logo", "brand": "notion"},
        {"word": "notion", "nth": 1, "kind": "capture", "url": "https://example.com", "width": 500},
        {"word": "faster", "nth": 1, "kind": "anim", "type": "flow",
         "props": {"nodes": [{"icon": "mail", "label": "email"}, {"logo": "notion", "label": "notion"}]}},
    ]))
    run("node", SK / "style-edit/scripts/capture.mjs", edit, cwd=work)
    run(VPY, SK / "style-edit/scripts/face.py", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/sfx.py", "build", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/plan.py", work / "style.json", edit / "captions.json", cwd=work)
    run(PY, SK / "style-edit/scripts/plan.py", work / "style.json", edit / "captions.json",
        "--layout", "split", "--out", edit / "plan-split.json", cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "stills", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "render", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "render", edit, "--plan", "plan-split.json", cwd=work)
    for f in ("render.mp4", "render-split.mp4"):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(edit / f)], capture_output=True, text=True).stdout.strip()
        if not out or abs(float(out) - 4) > 0.3:
            sys.exit(f"SMOKE FAIL: {f} duration {out!r}, expected about 4 s")
    stills = list((edit / "stills").glob("*.png"))
    if not stills:
        sys.exit("SMOKE FAIL: no stills")
    print(f"SMOKE OK on {platform.system()}: {len(stills)} stills, both renders 4 s ({work})")
    if os.environ.get("CI"):
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
