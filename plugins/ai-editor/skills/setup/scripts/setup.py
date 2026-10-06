#!/usr/bin/env python3
"""Check and install everything the AI editor needs. Stdlib only.

  python3 setup.py doctor     one line per tool: ok, or FIX with the exact command for this computer
  python3 setup.py doctor --quiet   silent when ready, else one line naming what is missing (the SessionStart hook)
  python3 setup.py venv       create ~/.ai-video-editor/venv and install the Python packages
  python3 setup.py model      download the free transcription model (about 500 MB, once)
  python3 setup.py remotion   copy the renderer to ~/.ai-video-editor/remotion and npm install it
  python3 setup.py setkey typesafe|gemini|elevenlabs   save an API key (asks, hides what you type),
                              after one free test request proves it works
  python3 setup.py keys       test every saved key (one free request each)
  python3 setup.py crisper    install CrisperWhisper, free verbatim transcription (about 1 GB; non-commercial licence)
  python3 setup.py awskey     save AWS keys for Lambda renders (asks, hides what you type)
  python3 setup.py lambda     check the AWS keys and permissions for Lambda renders
  python3 setup.py modal      install Modal (cloud renders) in the venv, then say how to log in
  python3 setup.py modal-check   one tiny function on Modal: proves the login works
  python3 setup.py matte      download the person-matting model (15 MB) for cards behind the speaker
  python3 setup.py demo       self-check

Exit codes: 0 ready or done, 1 something to fix, 2 usage.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from ai_editor import keys  # noqa: E402

OS = platform.system()  # Darwin, Windows, Linux
HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
VENV = HOME / "venv"
VPY = VENV / ("Scripts/python.exe" if OS == "Windows" else "bin/python")
PLUGIN = Path(__file__).resolve().parents[3]          # plugins/ai-editor
REMOTION_SRC = PLUGIN / "remotion"
REMOTION_HOME = HOME / "remotion"
PACKAGES = ["faster-whisper", "av<16", "numpy", "pillow>=10.1", "yt-dlp", "opencv-python-headless>=4.8",
            'ocrmac; sys_platform == "darwin"',
            'rapidocr; sys_platform != "darwin"', "onnxruntime"]
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
    here = Path(__file__).resolve()
    py_self = "py" if OS == "Windows" else "python3"
    for name, have, without in KEY_ROWS:
        _, where = keys.get(name)
        print(f"{'ok ' if where else '-- '}  {name + ' key':<20} " + (f"{have} ({where})" if where else
              f"{without}. Run in a terminal: {py_self} \"{here}\" setkey {name}"))
    cw = venv_has("crisperwhisper")
    print(f"{'ok ' if cw else '-- '}  {'crisperwhisper':<20} " + ("installed: free verbatim transcripts" if cw else
          f"optional, keeps every um and restart for free (non-commercial licence): {py_self} \"{here}\" crisper"))
    gh = shutil.which("gh")
    gh_ok = bool(gh) and run([gh, "auth", "status"]).returncode == 0
    gh_fix = {"Darwin": "brew install gh", "Windows": "winget install --id GitHub.CLI"}.get(
        OS, "see github.com/cli/cli/blob/trunk/docs/install_linux.md")
    print(f"{'ok ' if gh_ok else '-- '}  {'github cli':<20} " + ("logged in: GitHub Actions renders" if gh_ok else
          f"optional, for free GitHub Actions renders. {'run: gh auth login --web' if gh else 'install: ' + gh_fix}"))
    mo = modal_status()
    print(f"{'ok ' if mo == 'ready' else '-- '}  {'modal':<20} " + {
        "ready": "logged in: cloud renders on Modal",
        "no token": f"installed, not logged in. In your own terminal: {modal_exe()} token new",
        "missing": f"optional, cloud renders on Modal ($30 free credit a month): {py_self} \"{here}\" modal"}[mo])
    ready = all(r[1] for r in rows)
    print("Ready." if ready else "Not ready. Fix the lines above, top to bottom.")
    return 0 if ready else 1


KEY_ROWS = [  # name, what it gives, what happens without it
    ("typesafe", "found: Jev decides the cut, far fewer Claude tokens",
     "Recommended: without it Claude reads the whole transcript to decide the cut"),
    ("gemini", "found: the teardown reads a creator's look from video frames",
     "Recommended: without it the teardown look pass uses one frame sheet per video"),
    ("elevenlabs", "found: Scribe transcripts keep every filler",
     "Optional: without it transcripts are free and local"),
]
KEY_HELP = {"typesafe": "https://console.typesafe.ai/keys", "gemini": "https://aistudio.google.com/apikey",
            "elevenlabs": "https://elevenlabs.io/app/settings/api-keys"}
LATER = HOME / "later.json"   # steps the user chose to do later; doctor reminds, "finish setup" resumes


def later_load():
    try:
        return json.loads(LATER.read_text())
    except (OSError, ValueError):
        return []


def later(name):
    """Remember a skipped step (a key name, "modal", "style", "matte")."""
    items = [x for x in later_load() if x != name] + [name]
    HOME.mkdir(parents=True, exist_ok=True)
    LATER.write_text(json.dumps(items))
    print(f"Saved for later: {name}. Say \"finish setup\" any time to add it.")
    return 0


def still_later():
    """Skipped steps that are still not done."""
    done = {"modal": lambda: modal_status() == "ready"}
    out = []
    for x in later_load():
        if x in KEY_HELP and keys.get(x)[0]:
            continue
        if x in done and done[x]():
            continue
        out.append(x)
    return out


def todo():
    items = still_later()
    print("\n".join(f"later  {x:<11} {KEY_HELP.get(x, '')}" for x in items) or "Nothing saved for later.")
    return 0


def clip_kind(text):
    """What the clipboard holds instead of a key, without showing it."""
    t = text.strip()
    if not t:
        return "the clipboard is empty"
    if "\n" in t:
        return f"the clipboard holds {t.count(chr(10)) + 1} lines of text, not one key"
    if t.startswith(("/", "!", "python", "pbpaste", "claude", "npx")):
        return "the clipboard holds a command, not the key"
    if t.startswith("http"):
        return "the clipboard holds a web address, not the key"
    if " " in t:
        return "the clipboard holds words with spaces, not the key"
    if len(t) < 20:
        return f"the clipboard holds something {len(t)} characters long; keys are longer"
    return "that doesn't look like a key"


def set_key(name):
    import getpass
    if name not in keys.VARS:
        sys.exit(f"Which key? setkey {' | '.join(keys.VARS)}")
    if sys.stdin.isatty():
        key = getpass.getpass(f"Paste your {name} API key and press Enter (it stays hidden): ")
    else:
        key = sys.stdin.readline()
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-.]{20,}", key):
        sys.exit(f"Nothing saved: {clip_kind(key)}. Copy only the key from {KEY_HELP[name]}, then pick Copied again.")
    ok, msg = keys.verify(name, key)
    if not ok and not msg.startswith("no connection"):
        sys.exit(f"Not saved: {msg}")
    path = keys.save(name, key)
    print(f"Saved to {path}." + ("" if ok else f" Not tested ({msg}): run `setup.py keys` when online."))
    if ok:
        print(f"Tested: the {name} key works.")
    return 0


def test_keys():
    bad = 0
    for name in keys.VARS:
        key, where = keys.get(name)
        if not key:
            print(f"--   {name:<11} not saved")
            continue
        ok, msg = keys.verify(name, key)
        bad += not ok
        print(f"{'ok ' if ok else 'FIX'}  {name:<11} {msg} ({where})")
    return 1 if bad else 0


def install_crisper():
    if not VPY.exists():
        sys.exit("Run the venv step first.")
    v = run([str(VPY), "-c", "import sys; print(sys.version_info >= (3, 10))"]).stdout.strip()
    if v != "True":
        sys.exit("CrisperWhisper needs Python 3.10 or newer in the venv. Keep using Whisper, or "
                 f"install a newer Python ({fix('python')}), delete {VENV} and run the venv step again.")
    # The PyTorch build runs on Mac, Windows and Linux, CPU or GPU. The faster ct2 build is NVIDIA-only.
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "crisperwhisper[transformers]"], check=True)
    env = dict(os.environ, HF_HOME=str(HOME / "models"))
    name = os.environ.get("AI_EDITOR_CRISPER_MODEL", "small")
    subprocess.run([str(VPY), "-c", f"from crisperwhisper import CrisperWhisperModel; "
                    f"CrisperWhisperModel('{name}'); print('crisperwhisper ready')"], check=True, env=env)


def doctor_quiet():
    missing = [name for name, ok, _, _ in checks() if not ok]
    if missing:
        print(f"AI video editor: {', '.join(missing)} not set up yet. Say \"set up the editor\" to install.")
    elif still_later():
        print(f"AI video editor: saved for later: {', '.join(still_later())}. Say \"finish setup\" to add.")
    return 0   # never block the session


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


def modal_exe():
    return VENV / ("Scripts/modal.exe" if OS == "Windows" else "bin/modal")


def modal_status():
    """ready, no token, or missing. No network call: a token saved by `modal token new` counts."""
    if not venv_has("modal"):
        return "missing"
    token = (Path.home() / ".modal.toml").exists() or os.environ.get("MODAL_TOKEN_ID")
    return "ready" if token else "no token"


def install_modal():
    if not VPY.exists():
        sys.exit("Run the venv step first.")
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "--upgrade", "modal"], check=True)
    print("Modal installed.")
    if modal_status() != "ready":
        print(f"Next, log in. In your own terminal (it opens the browser):\n  {modal_exe()} token new")
    return 0


def check_modal():
    st = modal_status()
    if st != "ready":
        print("Modal is not installed yet: setup.py modal" if st == "missing" else
              f"Not logged in. In your own terminal: {modal_exe()} token new")
        return 1
    script = PLUGIN / "skills" / "style-edit" / "scripts" / "modal_render.py"
    r = run([str(VPY), str(script), "hello"], timeout=900)
    if r.returncode == 0 and "modal ok" in r.stdout:
        print("Tested: Modal works. The render machine is built and cached in your account.")
        return 0
    print(f"Modal did not answer:\n{(r.stderr or r.stdout).strip()[-1500:]}")
    return 1


def fetch_matte():
    """The Robust Video Matting model matte.py cuts the speaker out with, then a 10-frame test cut."""
    if not VPY.exists():
        sys.exit("Run the venv step first.")
    script = PLUGIN / "skills" / "style-edit" / "scripts" / "matte.py"
    subprocess.run([str(VPY), str(script), "fetch"], check=True)
    r = run([str(VPY), str(script), "demo"])
    print("Tested: cutting the speaker out works." if r.returncode == 0 else f"matte.py demo failed:\n{r.stderr[-1500:]}")
    return r.returncode


def demo():
    assert modal_status() in ("ready", "no token", "missing")
    assert major("v22.3.0") == 22 and major(None) == 0
    assert fix("ffmpeg").split()[0] in ("brew", "winget", "sudo")
    names = [r[0] for r in checks()]
    assert names[:3] == ["python", "ffmpeg", "node"], names
    global HOME, LATER
    import tempfile
    keep = HOME, LATER
    with tempfile.TemporaryDirectory() as d:
        HOME, LATER = Path(d), Path(d) / "later.json"
        later("style"); later("style")
        assert later_load() == ["style"] and "style" in still_later()
    HOME, LATER = keep
    print("demo ok")


if __name__ == "__main__":
    cmds = {"doctor": doctor, "venv": make_venv, "model": fetch_model,
            "remotion": install_remotion, "awskey": save_aws_key,
            "lambda": check_lambda, "modal": install_modal, "modal-check": check_modal, "matte": fetch_matte, "demo": demo, "keys": test_keys, "todo": todo, "crisper": install_crisper}
    if sys.argv[1:] == ["doctor", "--quiet"]:
        sys.exit(doctor_quiet())
    if len(sys.argv) == 3 and sys.argv[1] == "later":
        sys.exit(later(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "setkey":
        sys.exit(set_key(sys.argv[2]))
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(2)
    sys.exit(cmds[sys.argv[1]]() or 0)
