"""Every model the editor downloads, pinned by URL and sha256, and the one fetch that checks it.

Files land in AI_EDITOR_HOME/models (default ~/.ai-video-editor/models). A download that does not
match its sha256 is deleted, never used. Stdlib only.

    python models.py     self-check (no network)
"""
import hashlib
import os
import shutil
import sys
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
DIR = HOME / "models"

# faster-whisper models: the Hugging Face repo at a fixed commit, so a model update upstream never
# changes a transcript here. Shared files (tokenizer, vocabulary) are identical across sizes.
_TOK = "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"
_VOC = "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"
WHISPER = {  # size -> (commit, {file: sha256})
    "tiny": ("d90ca5fe260221311c53c58e660288d3deb8d356", {
        "config.json": "a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8",
        "model.bin": "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1",
        "tokenizer.json": _TOK, "vocabulary.txt": _VOC}),
    "small": ("536b0662742c02347bc0e980a01041f333bce120", {
        "config.json": "b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828",
        "model.bin": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
        "tokenizer.json": _TOK, "vocabulary.txt": _VOC}),
}

PINS = {  # path under models/ -> (url, sha256)
    # Robust Video Matting (GPL-3.0, downloaded at first use, never shipped): the speaker cutout.
    "rvm_mobilenetv3_fp32.onnx": (
        "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx",
        "88d4531297118f595bf2fd60f6f566aec2e559393802d1f436c380f0cbbd2828"),
    # OpenCV YuNet face detector (MIT), at a fixed opencv_zoo commit.
    "yunet.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/f12e12798e8314f7c074a6656816c048dcc95b7a/"
        "models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
}
for _size, (_rev, _files) in WHISPER.items():
    for _f, _sha in _files.items():
        PINS[f"faster-whisper-{_size}/{_f}"] = (
            f"https://huggingface.co/Systran/faster-whisper-{_size}/resolve/{_rev}/{_f}", _sha)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(rel, check=True):
    """The local path of a pinned file, downloaded and verified if missing (or wrong, when check)."""
    url, want = PINS[rel]
    dest = DIR / rel
    if dest.exists() and (not check or sha256(dest) == want):
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    print(f"downloading {rel}", flush=True)
    urllib.request.urlretrieve(url, part)
    got = sha256(part)
    if got != want:
        part.unlink()
        sys.exit(f"ERROR: {rel} downloaded with sha256 {got}, expected {want}. Nothing kept. "
                 "Try again; if it repeats, the file changed upstream: report it as a bug.")
    part.replace(dest)
    return dest


def whisper_dir(size):
    """The pinned faster-whisper folder if all its files are on disk, else None. No hashing."""
    if size not in WHISPER:
        return None
    d = DIR / f"faster-whisper-{size}"
    return d if all((d / f).exists() for f in WHISPER[size][1]) else None


def whisper(size, check=True):
    """Download (or verify) a pinned faster-whisper model; returns its folder, or None if unpinned.
    Reuses a copy at the same commit from faster-whisper's own cache (installs before the pins)."""
    if size not in WHISPER:
        return None
    rev, files = WHISPER[size]
    old = DIR / f"models--Systran--faster-whisper-{size}" / "snapshots" / rev
    for f, want in files.items():
        dest = DIR / f"faster-whisper-{size}" / f
        if not dest.exists() and (old / f).exists() and sha256(old / f) == want:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(old / f, dest)
        fetch(f"faster-whisper-{size}/{f}", check)
    return DIR / f"faster-whisper-{size}"


def demo():
    import tempfile
    global DIR
    for rel, (url, sha) in PINS.items():
        assert url.startswith("https://") and len(sha) == 64, rel
        assert "/main/" not in url and "/resolve/main" not in url, f"{rel} is not pinned to a commit"
    keep = DIR
    with tempfile.TemporaryDirectory() as d:
        DIR = Path(d)
        assert whisper_dir("small") is None and whisper_dir("medium") is None
        for f in WHISPER["tiny"][1]:
            (DIR / "faster-whisper-tiny").mkdir(exist_ok=True)
            (DIR / "faster-whisper-tiny" / f).write_text("x", encoding="utf-8")
        assert whisper_dir("tiny") == DIR / "faster-whisper-tiny"
        assert sha256(DIR / "faster-whisper-tiny" / "config.json") == hashlib.sha256(b"x").hexdigest()
        # a download says which file in plain words, never the pinned URL with its commit hash
        import contextlib
        import io
        PINS["t.bin"] = ("https://example.com/abc123def/t.bin", hashlib.sha256(b"x").hexdigest())
        real, out = urllib.request.urlretrieve, io.StringIO()
        try:
            urllib.request.urlretrieve = lambda u, dest: Path(dest).write_bytes(b"x")
            with contextlib.redirect_stdout(out):
                fetch("t.bin")
        finally:
            urllib.request.urlretrieve = real
            PINS.pop("t.bin")
        assert out.getvalue() == "downloading t.bin\n", out.getvalue()
    DIR = keep
    print("demo ok")


if __name__ == "__main__":
    demo()
