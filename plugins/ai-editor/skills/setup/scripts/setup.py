#!/usr/bin/env python3
"""Check and install everything the AI editor needs. Stdlib only.

  python3 setup.py doctor     one line per tool: ok, or FIX with the exact command for this computer
  python3 setup.py venv       create ~/.ai-video-editor/venv and install the Python packages
  python3 setup.py model      download the free transcription model (about 500 MB, once)
  python3 setup.py remotion   copy the renderer to ~/.ai-video-editor/remotion and npm install it
  python3 setup.py awskey     save AWS keys for Lambda renders (asks, hides what you type)
  python3 setup.py lambda     check the AWS keys and permissions for Lambda renders
  python3 setup.py demo       self-check

Exit codes: 0 ready or done, 1 something to fix, 2 usage.
"""
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

OS = platform.system()  # Darwin, Windows, Linux
HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
VENV = HOME / "venv"
VPY = VENV / ("Scripts/python.exe" if OS == "Windows" else "bin/python")
PLUGIN = Path(__file__).resolve().parents[3]          # plugins/ai-editor
REMOTION_SRC = PLUGIN / "remotion"
REMOTION_HOME = HOME / "remotion"
PACKAGES = ["faster-whisper", "av<16", "numpy", "pillow>=10.1", "yt-dlp", "opencv-python-headless>=4.8"]
MODEL = os.environ.get("AI_EDITOR_WHISPER_MODEL", "small")
NODE_MIN = 20

INSTALL = {  # tool -> (mac, windows, linux)
    "python": ("brew install python", "winget install -e --id Python.Python.3.12",
               "sudo apt install -y python3 python3-venv"),
    "ffmpeg": ("brew install ffmpeg", "winget install -e --id Gyan.FFmpeg",
               "sudo apt install -y ffmpeg"),
    "node": ("brew install node", "winget install -e --id OpenJS.NodeJS.LTS",
             "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"),
    "git": ("xcode-select --install", "winget install -e --id Git.Git", "sudo apt install -y git"),
}


def fix(tool):
    mac, win, linux = INSTALL[tool]
    return {"Darwin": mac, "Windows": win}.get(OS, linux)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def version(cmd):
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    try:
        out = run([exe, *cmd[1:]], timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return (out.stdout + out.stderr).strip().splitlines()[0] if out.returncode == 0 else None


def major(text):
    m = re.search(r"(\d+)\.", text or "")
    return int(m.group(1)) if m else 0


def venv_has(module):
    return VPY.exists() and run([str(VPY), "-c", f"import {module}"]).returncode == 0


def model_cached():
    return any((HOME / "models").glob(f"**/*faster-whisper-{MODEL}*"))


def checks():
    """(name, ok, detail, fix command or None)"""
    rows = []
    py = sys.version_info
    rows.append(("python", py >= (3, 9), f"{py.major}.{py.minor}", fix("python")))
    ff = version(["ffmpeg", "-version"])
    rows.append(("ffmpeg", bool(ff), ff or "missing", fix("ffmpeg")))
    node = version(["node", "--version"])
    rows.append(("node", major(node) >= NODE_MIN, node or "missing", fix("node")))
    rows.append(("git", bool(version(["git", "--version"])), "", fix("git")))
    py_self = "py" if OS == "Windows" else "python3"
    here = Path(__file__).resolve()
    rows.append(("python packages", venv_has("faster_whisper") and venv_has("yt_dlp") and venv_has("cv2"),
                 str(VENV), f'{py_self} "{here}" venv'))
    rows.append(("transcription model", model_cached(), f"faster-whisper {MODEL}",
                 f'{py_self} "{here}" model'))
    rows.append(("renderer", (REMOTION_HOME / "node_modules" / "remotion").exists(),
                 str(REMOTION_HOME), f'{py_self} "{here}" remotion'))
    return rows


def doctor():
    rows = checks()
    for name, ok, detail, cmd in rows:
        print(f"{'ok ' if ok else 'FIX'}  {name:<20} {detail}")
        if not ok:
            print(f"     run: {cmd}")
    key = Path.home() / ".config" / "creator-teardown" / ".env"
    has_key = key.exists() and "ELEVENLABS_API_KEY=" in key.read_text()
    print(f"{'ok ' if has_key else '-- '}  {'elevenlabs key':<20} "
          f"{'found: better cuts' if has_key else 'optional, free Whisper is used without it'}")
    ready = all(r[1] for r in rows)
    print("Ready." if ready else "Not ready. Fix the lines above, top to bottom.")
    return 0 if ready else 1


def make_venv():
    HOME.mkdir(parents=True, exist_ok=True)
    if not VPY.exists():
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "--upgrade", *PACKAGES], check=True)
    print(f"Python packages ready in {VENV}")


def fetch_model():
    if not venv_has("faster_whisper"):
        sys.exit("Run the venv step first.")
    code = ("import os; from faster_whisper import WhisperModel; "
            f"WhisperModel('{MODEL}', device='cpu', compute_type='int8', "
            f"download_root=r'{HOME / 'models'}'); print('model ready')")
    subprocess.run([str(VPY), "-c", code], check=True)


def install_remotion():
    npm = shutil.which("npm")
    if not npm:
        sys.exit(f"npm missing. Install Node first: {fix('node')}")
    # Copy everything but build output; node_modules stays between updates.
    REMOTION_HOME.mkdir(parents=True, exist_ok=True)
    for src in REMOTION_SRC.iterdir():
        if src.name in ("node_modules", "out", ".DS_Store"):
            continue
        dst = REMOTION_HOME / src.name
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=REMOTION_HOME, check=True)
    npx = shutil.which("npx")
    subprocess.run([npx, "remotion", "browser", "ensure"], cwd=REMOTION_HOME, check=True)
    print(f"Renderer ready in {REMOTION_HOME}")


def save_aws_key():
    import getpass
    key_id = input("AWS access key ID: ").strip()
    secret = getpass.getpass("AWS secret access key (hidden): ").strip()
    region = input("AWS region [us-east-1]: ").strip() or "us-east-1"
    if not key_id.startswith(("AKIA", "ASIA")) or len(secret) < 30:
        sys.exit("That does not look like an AWS access key. Nothing saved.")
    HOME.mkdir(parents=True, exist_ok=True)
    f = HOME / "aws.env"
    f.write_text(f"REMOTION_AWS_ACCESS_KEY_ID={key_id}\nREMOTION_AWS_SECRET_ACCESS_KEY={secret}\n"
                 f"REMOTION_AWS_REGION={region}\n")
    if OS != "Windows":
        f.chmod(0o600)
    print(f"Saved to {f}")


def check_lambda():
    f = HOME / "aws.env"
    if not f.exists():
        sys.exit("No AWS keys yet. Run: setup.py awskey")
    env = dict(os.environ)
    for line in f.read_text().splitlines():
        k, _, v = line.partition("=")
        if v:
            env[k] = v
    npx = shutil.which("npx")
    r = subprocess.run([npx, "remotion", "lambda", "policies", "validate"], cwd=REMOTION_HOME, env=env)
    return r.returncode


def demo():
    assert major("v22.3.0") == 22 and major(None) == 0
    assert fix("ffmpeg").split()[0] in ("brew", "winget", "sudo")
    names = [r[0] for r in checks()]
    assert names[:3] == ["python", "ffmpeg", "node"], names
    print("demo ok")


if __name__ == "__main__":
    cmds = {"doctor": doctor, "venv": make_venv, "model": fetch_model,
            "remotion": install_remotion, "awskey": save_aws_key,
            "lambda": check_lambda, "demo": demo}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(2)
    sys.exit(cmds[sys.argv[1]]() or 0)
