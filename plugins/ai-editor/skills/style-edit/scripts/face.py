#!/usr/bin/env python3
"""Where the speaker's head is, so plan.py keeps cards and logos off it.

    ~/.ai-video-editor/venv/bin/python face.py edits/NAME      writes edits/NAME/face.json
    ~/.ai-video-editor/venv/bin/python face.py demo            self-check

Samples cut.mp4 every 0.5 s and finds the largest face with OpenCV's YuNet detector
(MIT licence, a 230 KB model fetched once into ~/.ai-video-editor/models). Each box is
the HEAD, not the face: widened for hair and ears, because a card that stops at the
eyebrows still sits on the hair.

face.json: {"step_s": 0.5, "heads": [{"t": 0.0, "box": [x, y, w, h]} ...]} in percent of
the frame, box null when no face was found.
Exit codes: 0 ok, 1 error, 2 usage
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
MODEL = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor")) / "models" / "yunet.onnx"
STEP_S = 0.5
SCAN_W = 360            # detection width; YuNet is built for small inputs
HAIR, SIDE, CHIN = 0.35, 0.2, 0.15  # head = face box grown by these fractions (top, each side, bottom)


def model():
    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    return str(MODEL)


def head_box(face, w, h):
    """YuNet face [x, y, fw, fh] in px -> head box in percent, clamped to the frame."""
    x, y, fw, fh = face
    x0, x1 = max(0.0, x - SIDE * fw), min(w, x + fw + SIDE * fw)
    y0, y1 = max(0.0, y - HAIR * fh), min(h, y + fh + CHIN * fh)
    return [round(100 * x0 / w, 1), round(100 * y0 / h, 1), round(100 * (x1 - x0) / w, 1),
            round(100 * (y1 - y0) / h, 1)]


def frames(video):
    """(t, BGR frame at SCAN_W) every STEP_S seconds, straight from ffmpeg."""
    import numpy as np
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
         "-of", "json", str(video)], capture_output=True, text=True, check=True).stdout)["streams"][0]
    sh = round(SCAN_W * probe["height"] / probe["width"] / 2) * 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={1 / STEP_S},scale={SCAN_W}:{sh}",
                          "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE)
    n, i = SCAN_W * sh * 3, 0
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield i * STEP_S, np.frombuffer(buf, np.uint8).reshape(sh, SCAN_W, 3)
        i += 1
    p.wait()


def scan(video):
    import cv2
    det, heads = None, []
    for t, im in frames(video):
        h, w = im.shape[:2]
        if det is None:
            det = cv2.FaceDetectorYN.create(model(), "", (w, h), 0.6)
        _, faces = det.detect(im)
        box = None
        if faces is not None and len(faces):
            big = max(faces, key=lambda f: f[2] * f[3])
            box = head_box(big[:4].tolist(), w, h)
        heads.append({"t": round(t, 2), "box": box})
    return heads


def demo():
    b = head_box([100, 200, 100, 100], 400, 800)
    assert b == [20.0, 20.6, 35.0, 18.8], b
    assert head_box([0, 0, 100, 100], 400, 800)[:2] == [0.0, 0.0]
    print("demo ok")


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    if sys.argv[1] == "demo":
        return demo()
    d = Path(sys.argv[1])
    video = d / "cut.mp4"
    if not video.exists():
        sys.exit(f"ERROR: no cut.mp4 in {d}")
    heads = scan(video)
    found = sum(1 for x in heads if x["box"])
    (d / "face.json").write_text(json.dumps({"step_s": STEP_S, "heads": heads}))
    print(f"{d / 'face.json'}: a head in {found} of {len(heads)} samples")


if __name__ == "__main__":
    main()
