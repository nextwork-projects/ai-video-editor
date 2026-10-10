#!/usr/bin/env python3
"""End-to-end smoke test: the whole editor on a made-up 4 s video, on whatever OS runs it.

    python tests/smoke.py            (after setup.py venv, model and remotion)
    python tests/smoke.py --load 8   the same with 8 busy loops pinning the CPU (stills and renders under load)

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


def run_out(*cmd, cwd):
    """run, with the output kept (and printed) so a step can be checked for noise a user should never see."""
    print("$", " ".join(map(str, cmd)), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    print(r.stdout + r.stderr, end="", flush=True)
    if r.returncode:
        sys.exit(f"SMOKE FAIL: exit {r.returncode} from {cmd[1] if len(cmd) > 1 else cmd[0]}")
    return r.stdout + r.stderr


def main():
    work = Path(tempfile.mkdtemp(prefix="ave-smoke-"))
    try:
        steps(work)
    except BaseException:
        print(f"SMOKE: kept the work folder for a look: {work}", file=sys.stderr)
        raise
    shutil.rmtree(work, ignore_errors=True)


def steps(work):
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
    (edit / "captions.json").write_text(json.dumps(words), encoding="utf-8")
    style = {"handle": "smoke", "pace": {"max_pause_s": 0.2}, "zoom": {"per_min": 20, "kind": "punch", "scale": 1.15,
             "on": "sentence_start"}, "captions": {"present": True, "words_per_caption": 2, "y_pct": 68, "size_pct": 5,
             "case": "lower", "font_match": "Inter", "weight": 800, "color": "#FFFFFF", "stroke": True}}
    (work / "style.json").write_text(json.dumps(style), encoding="utf-8")
    (edit / "visuals.json").write_text(json.dumps([
        {"word": "notion", "nth": 1, "kind": "logo", "brand": "notion"},
        {"word": "notion", "nth": 1, "kind": "capture", "url": "https://example.com", "width": 500, "format": "sticker",
         "marks": [{"kind": "highlight", "find": "This domain is for use in"}]},
        # a page's body text reads on a phone only re-set as a sticker (check.py plan FAILs a capture under 28 px x-height)
        {"word": "faster", "nth": 1, "kind": "anim", "type": "flow",
         "props": {"nodes": [{"icon": "mail", "label": "email"}, {"logo": "notion", "label": "notion"}]}},
    ]), encoding="utf-8")
    run("node", SK / "style-edit/scripts/capture.mjs", edit, cwd=work)
    run(VPY, SK / "style-edit/scripts/face.py", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/sfx.py", "build", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/plan.py", work / "style.json", edit / "captions.json", cwd=work)
    run(PY, SK / "style-edit/scripts/plan.py", work / "style.json", edit / "captions.json",
        "--layout", "split", "--out", edit / "plan-split.json", cwd=work)
    out = run_out(PY, SK / "style-edit/scripts/edit.py", "stills", edit, cwd=work)
    if "GSAP target" in out:     # a tween on an element the card did not draw (the flow scene's veil)
        sys.exit("SMOKE FAIL: the stills printed GSAP 'target not found' warnings")
    # graphics behind the speaker: the capture card goes behind, the speaker is cut out under it
    run(PY, SK / "style-edit/scripts/plan.py", work / "style.json", edit / "captions.json", "--layout", "overlay",
        "--behind", "on", "--out", edit / "plan-behind.json", cwd=work)
    run(VPY, SK / "style-edit/scripts/matte.py", edit, "--plan", "plan-behind.json", cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "stills", edit, "--plan", "plan-behind.json", cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "render", edit, cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "render", edit, "--plan", "plan-split.json", cwd=work)
    for f in ("render.mp4", "render-split.mp4"):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(edit / f)], capture_output=True, text=True).stdout.strip()
        if not out or abs(float(out) - 4) > 0.3:
            sys.exit(f"SMOKE FAIL: {f} duration {out!r}, expected about 4 s")
    contrast(work)
    podcast(work)
    stills = list((edit / "stills").glob("*.png"))
    if not stills:
        sys.exit("SMOKE FAIL: no stills")
    print(f"SMOKE OK on {platform.system()}: {len(stills)} stills, both renders 4 s")


def contrast(work):
    """White captions with no stroke (the creator's look) on a bright desk: plan.py adds the treatment
    and check.py render passes; on a dark desk the plan keeps her plain look. A creator measured with no
    drop shadow still gets the treatment rendered on the bright desk."""
    words = [{"text": t, "start": round(0.2 + i * 0.32, 2), "end": round(0.48 + i * 0.32, 2), "type": "word"}
             for i, t in enumerate("this desk is far too bright for white words".split())]
    style = {"handle": "plain", "captions": {"present": True, "words_per_caption": 3, "y_pct": 68, "size_pct": 5,
             "case": "lower", "font_match": "Inter", "weight": 800, "color": "#FFFFFF", "stroke": False}}
    (work / "plain.json").write_text(json.dumps(style), encoding="utf-8")
    style["captions"]["shadow"] = False
    (work / "noshadow.json").write_text(json.dumps(style), encoding="utf-8")
    for name, colour, sj in (("bright", "0xE6E1D8", "plain.json"), ("dark", "0x262626", "plain.json"),
                             ("noshadow", "0xE6E1D8", "noshadow.json")):
        ed = work / "edits" / name
        ed.mkdir(parents=True)
        run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={colour}:s=540x960:r=30:d=3", "-f", "lavfi",
            "-i", "sine=f=220:d=3", "-vf", "noise=alls=12:allf=t", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", ed / "cut.mp4", cwd=work)
        (ed / "captions.json").write_text(json.dumps(words), encoding="utf-8")
        run(PY, SK / "style-edit/scripts/plan.py", work / sj, ed / "captions.json", "--no-sfx", cwd=work)
        treats = {c.get("treat") for c in json.loads((ed / "plan.json").read_text(encoding="utf-8"))["captions"]["chunks"]}
        if treats != ({None} if name == "dark" else {"backing"}):   # aimed at the render WARN line (4.7:1)
            sys.exit(f"SMOKE FAIL: {name} desk captions treated {treats}")
        if name != "dark":
            run(PY, SK / "style-edit/scripts/edit.py", "render", ed, cwd=work)
            run(VPY, SK / "style-edit/scripts/check.py", "render", ed, cwd=work)   # exit 1 on a contrast FAIL


def podcast(work):
    """An audio-only podcast clip: clips.py trim puts the audio over the podcast's cover, then the real
    renderer draws the speaker's words on it, the cover moving all the way through (14 s, past the 6 s a
    frame may hold still), and check.py render passes with no "nothing moves" WARN."""
    pod = work / "clips" / "pod"
    pod.mkdir(parents=True)
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=180:d=16", pod / "source.mp3", cwd=work)
    run("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=800x800", "-frames:v", "1", pod / "cover.png", cwd=work)
    said = ("this is the part nobody tells you about. most people quit in the first week. "
            "the ones who stay do one small thing every day. and that is the whole secret.").split()
    words = [{"text": t, "start": round(0.4 + i * 0.5, 2), "end": round(0.8 + i * 0.5, 2), "type": "word"}
             for i, t in enumerate(said)]
    (pod / "words.raw.json").write_text(json.dumps(words), encoding="utf-8")
    (pod / "candidates.json").write_text(json.dumps([{"id": "c0", "start": 0.4, "end": words[-1]["end"],
                                                      "hook": "this is the part"}]), encoding="utf-8")
    run(PY, SK / "clips/scripts/clips.py", "trim", pod, "c0", "--edits", work / "edits", cwd=work)
    ed = work / "edits" / "pod-clip1"
    if not json.loads((ed / "clip.json").read_text(encoding="utf-8")).get("audio_only"):
        sys.exit("SMOKE FAIL: an audio source's clip is not marked audio_only")
    (ed / "source.mp4").rename(ed / "cut.mp4")
    (ed / "captions.json").write_text((ed / "words.raw.json").read_text(encoding="utf-8"), encoding="utf-8")
    style = {"handle": "pod", "captions": {"present": True, "words_per_caption": 3, "y_pct": 72, "size_pct": 5.5,
             "case": "lower", "font_match": "Inter", "weight": 800, "color": "#FFFFFF", "stroke": True}}
    (work / "pod.json").write_text(json.dumps(style), encoding="utf-8")
    run(PY, SK / "style-edit/scripts/plan.py", work / "pod.json", ed / "captions.json", "--no-sfx", cwd=work)
    run(PY, SK / "style-edit/scripts/edit.py", "render", ed, cwd=work)
    run(VPY, SK / "style-edit/scripts/check.py", "render", ed, cwd=work)   # exit 1 on any FAIL
    still = [f["what"] for f in json.loads((ed / "check.json").read_text(encoding="utf-8"))["render"]["findings"]
             if "nothing moves" in f["what"] or "push did not render" in f["what"]]
    if still:
        sys.exit(f"SMOKE FAIL: the podcast clip holds still: {still}")


if __name__ == "__main__":
    n = int(sys.argv[sys.argv.index("--load") + 1]) if "--load" in sys.argv else 0
    hogs = [subprocess.Popen([PY, "-c", "while True: pass"]) for _ in range(n)]
    try:
        main()
    finally:
        for h in hogs:
            h.kill()
