#!/usr/bin/env python3
"""Check and install everything the AI editor needs. Stdlib only.

  python3 setup.py doctor     one line per tool: ok, or FIX with the exact command for this computer;
                              also FIX on drift from the pinned versions (env.json vs what is installed)
  python3 setup.py doctor --quiet   silent when ready, else one line naming what is missing (the SessionStart hook)
  python3 setup.py bootstrap [--matte]   the whole install, idempotent: venv, model, remotion, then doctor
  python3 setup.py repair     reinstall the exact pinned set (fresh venv, npm ci, models re-verified)
  python3 setup.py venv       create ~/.ai-video-editor/venv and install requirements/requirements.lock
  python3 setup.py model      download the free transcription model (about 500 MB, once, sha256 checked)
  python3 setup.py remotion   copy the renderer to ~/.ai-video-editor/remotion and npm ci it

Pins: Python packages in plugins/ai-editor/requirements/requirements.lock (hashed, every OS);
Node packages in remotion/package-lock.json; models in lib/ai_editor/models.py (URL + sha256).
What got installed is recorded in ~/.ai-video-editor/env.json. AI_EDITOR_HOME moves the folder.
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
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from ai_editor import keys, models  # noqa: E402

OS = platform.system()  # Darwin, Windows, Linux
HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
VENV = HOME / "venv"
VPY = VENV / ("Scripts/python.exe" if OS == "Windows" else "bin/python")
PLUGIN = Path(__file__).resolve().parents[3]          # plugins/ai-editor
REMOTION_SRC = PLUGIN / "remotion"
REMOTION_HOME = HOME / "remotion"
LOCK = PLUGIN / "requirements" / "requirements.lock"   # uv pip compile --universal --generate-hashes
NPM_LOCK = REMOTION_SRC / "package-lock.json"
ENV = HOME / "env.json"           # what was installed, from which pins
MODEL = os.environ.get("AI_EDITOR_WHISPER_MODEL", "small")
PYTHON_MIN = (3, 10)   # current yt-dlp and numpy need it; macOS's built-in 3.9 gets a newer Python
NODE_MIN = 20          # Remotion 4
FFMPEG_MIN = (4, 4)    # sfx.py mixes with amix normalize=0, added in FFmpeg 4.4
# Optional extras, pinned; installed with the lock as constraints so they never move a pinned package.
OPTIONAL = {"modal": "modal==1.6.1", "crisperwhisper": "crisperwhisper[transformers]==2.0.3"}

INSTALL = {  # tool -> (mac, windows, linux)
    "python": ("brew install python", "winget install -e --id Python.Python.3.12",
               "sudo apt install -y python3 python3-venv"),
    "ffmpeg": ("brew install ffmpeg", "winget install -e --id Gyan.FFmpeg",
               "sudo apt install -y ffmpeg"),
    "node": ("brew install node", "winget install -e --id OpenJS.NodeJS.LTS",
             "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt install -y nodejs"),
    "git": ("xcode-select --install", "winget install -e --id Git.Git", "sudo apt install -y git"),
}


UPGRADE = {  # installed but older than the minimum
    "ffmpeg": ("brew upgrade ffmpeg", "winget upgrade -e --id Gyan.FFmpeg",
               "sudo apt update && sudo apt install -y ffmpeg   (Ubuntu 22.04 or newer)"),
    "node": ("brew upgrade node", "winget upgrade -e --id OpenJS.NodeJS.LTS", INSTALL["node"][2]),
}


def fix(tool, table=INSTALL):
    mac, win, linux = table[tool]
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


def ffmpeg_version(text):
    """(major, minor) from `ffmpeg -version`; a git build (version N-...) counts as new."""
    if re.search(r"version N-", text or ""):
        return (99, 0)
    m = re.search(r"version n?(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def installed():
    """{package: version} in the venv, {} without one."""
    if not VPY.exists():
        return {}
    code = ("import json, importlib.metadata as m; print(json.dumps({d.metadata['Name']: d.version "
            "for d in m.distributions() if d.metadata['Name']}))")
    r = run([str(VPY), "-c", code])
    return {norm(k): v for k, v in json.loads(r.stdout).items()} if r.returncode == 0 else {}


def env_load():
    try:
        return json.loads(ENV.read_text())
    except (OSError, ValueError):
        return {}


def env_save(**kv):
    """Merge into env.json; untouched when nothing changed, so a re-run leaves it byte-identical."""
    old = env_load()
    new = {**old, **kv}
    if new != old:
        HOME.mkdir(parents=True, exist_ok=True)
        ENV.write_text(json.dumps(new, indent=1, sort_keys=True) + "\n")


def npm_version(name):
    """The version npm ci installs for a package, from the shipped package-lock.json."""
    try:
        return json.loads(NPM_LOCK.read_text())["packages"][f"node_modules/{name}"]["version"]
    except (OSError, ValueError, KeyError):
        return None


def drift(env, have, remotion_have):
    """What differs from the pins, per area: {"python": [...], "renderer": [...], "model": [...]}.
    env is env.json, have the venv's {package: version}, remotion_have the installed remotion
    version. Pure, so the demo can feed it a made-up env.json."""
    out = {"python": [], "renderer": [], "model": []}
    if have:
        if not env.get("python_packages"):
            out["python"].append("installed before version pins")
        elif env.get("python_lock") != file_sha(LOCK):
            out["python"].append("requirements.lock changed since the install")
        for name, want in sorted(env.get("python_packages", {}).items()):
            if have.get(name) != want:
                out["python"].append(f"{name} {have.get(name, 'missing')}, pinned {want}")
    if remotion_have:
        if env.get("node_lock") != file_sha(NPM_LOCK):
            out["renderer"].append("package-lock.json changed since the install (or installed before pins)")
        if remotion_have != npm_version("remotion"):
            out["renderer"].append(f"remotion {remotion_have}, pinned {npm_version('remotion')}")
    for rel, sha in sorted(env.get("models", {}).items()):
        if rel in models.PINS and models.PINS[rel][1] != sha:
            out["model"].append(f"{rel}: pin changed since the download")
    return out


def remotion_installed():
    try:
        return json.loads((REMOTION_HOME / "node_modules" / "remotion" / "package.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        return None


def venv_has(module):
    return VPY.exists() and run([str(VPY), "-c", f"import {module}"]).returncode == 0


def model_cached():
    if MODEL in models.WHISPER:
        return models.whisper_dir(MODEL) is not None
    return any((HOME / "models").glob(f"**/*faster-whisper-{MODEL}*"))   # a size with no pin


def checks():
    """(name, ok, detail, fix command or None)"""
    rows = []
    py = sys.version_info
    need = ".".join(map(str, PYTHON_MIN))
    rows.append(("python", py >= PYTHON_MIN, f"{py.major}.{py.minor} (need {need}+)", fix("python")))
    ff = version(["ffmpeg", "-version"])
    ff_ok = ffmpeg_version(ff) >= FFMPEG_MIN
    rows.append(("ffmpeg", ff_ok, f"{ff or 'missing'} (need {'.'.join(map(str, FFMPEG_MIN))}+)",
                 fix("ffmpeg", UPGRADE if ff else INSTALL)))
    node = version(["node", "--version"])
    rows.append(("node", major(node) >= NODE_MIN, f"{node or 'missing'} (need {NODE_MIN}+)",
                 fix("node", UPGRADE if node else INSTALL)))
    git = version(["git", "--version"])
    rows.append(("git", bool(git), git or "missing", fix("git")))
    py_self = "py" if OS == "Windows" else "python3"
    here = Path(__file__).resolve()
    remo = remotion_installed()
    d = drift(env_load(), installed(), remo)
    rows.append(("python packages", VPY.exists() and not d["python"], "; ".join(d["python"][:4]) or str(VENV),
                 f'{py_self} "{here}" ' + ("repair" if VPY.exists() else "venv")))
    rows.append(("transcription model", model_cached() and not d["model"], f"faster-whisper {MODEL}",
                 f'{py_self} "{here}" model'))
    rows.append(("renderer", bool(remo) and not d["renderer"], "; ".join(d["renderer"]) or str(REMOTION_HOME),
                 f'{py_self} "{here}" ' + ("repair" if remo else "remotion")))
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
    if ENV.exists():
        print(f"     installed versions: {ENV}")
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
    pip_optional("crisperwhisper")
    env = dict(os.environ, HF_HOME=str(HOME / "models"))
    name = os.environ.get("AI_EDITOR_CRISPER_MODEL", "small")
    subprocess.run([str(VPY), "-c", f"from crisperwhisper import CrisperWhisperModel; "
                    f"CrisperWhisperModel('{name}'); print('crisperwhisper ready')"], check=True, env=env)


def doctor_quiet():
    rows = [r for r in checks() if not r[1]]
    missing = [name for name, _, _, cmd in rows if not cmd.endswith("repair")]
    drifted = [name for name, _, _, cmd in rows if cmd.endswith("repair")]
    if missing:
        print(f"AI video editor: {', '.join(missing)} not set up yet. Say \"set up the editor\" to install.")
    elif drifted:
        print(f"AI video editor: {', '.join(drifted)} moved off the pinned versions. "
              f"Run: {'py' if OS == 'Windows' else 'python3'} \"{Path(__file__).resolve()}\" repair")
    elif still_later():
        print(f"AI video editor: saved for later: {', '.join(still_later())}. Say \"finish setup\" to add.")
    return 0   # never block the session


def pip_optional(name):
    """Install an optional extra at its pin, holding every recorded package where it is."""
    cons = HOME / "constraints.txt"
    cons.write_text("".join(f"{k}=={v}\n" for k, v in sorted(env_load().get("python_packages", {}).items())))
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "-c", str(cons), OPTIONAL[name]], check=True)


def step_venv(force=False):
    """A venv holding exactly requirements.lock. Rebuilt from scratch on drift, so nothing stale stays."""
    if sys.version_info < PYTHON_MIN:
        sys.exit(f"Python {'.'.join(map(str, PYTHON_MIN))}+ needed, this is {sys.version.split()[0]}. "
                 f"Install it: {fix('python')}, then run this again in a new terminal.")
    have = installed()
    if have and not force and not drift(env_load(), have, None)["python"]:
        print(f"python packages: up to date ({VENV})")
        return "up to date"
    extras = [x for x in OPTIONAL if norm(x) in have]     # reinstalled after the rebuild
    if VENV.exists():
        shutil.rmtree(VENV)
    HOME.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
    # --no-deps: the lock is complete. It also keeps rapidocr's opencv-python out, which would
    # fight opencv-python-headless over the same cv2 folder.
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-deps",
                    "--require-hashes", "-r", str(LOCK)], check=True)
    env_save(python_lock=file_sha(LOCK), python_packages=installed(),
             python=platform.python_version(), os=f"{OS} {platform.machine()}")
    for x in extras:
        pip_optional(x)
    print(f"Python packages ready in {VENV}")
    return "installed"


def step_model(force=False):
    """The pinned transcription model, sha256 checked on download (and on every repair)."""
    if not venv_has("faster_whisper"):
        sys.exit("Run the venv step first.")
    whisper = {r: models.PINS[r][1] for r in models.PINS if r.startswith(f"faster-whisper-{MODEL}/")}
    pins = {**whisper, "yunet.onnx": models.PINS["yunet.onnx"][1]}     # + the face finder, 230 KB
    rec = env_load().get("models", {})
    fresh = not model_cached() or not (models.DIR / "yunet.onnx").exists()
    check = force or any(rec.get(r) != v for r, v in pins.items())
    models.fetch("yunet.onnx", check)
    if whisper:
        models.whisper(MODEL, check)
    else:   # a size with no pin (AI_EDITOR_WHISPER_MODEL=medium...): faster-whisper's own download
        code = ("from faster_whisper import WhisperModel; "
                f"WhisperModel('{MODEL}', device='cpu', compute_type='int8', download_root=r'{HOME / 'models'}')")
        subprocess.run([str(VPY), "-c", code], check=True)
    env_save(models={**rec, **pins})
    print(f"transcription model ready: faster-whisper {MODEL}" + ("" if whisper else " (no pin for this size)"))
    return "installed" if fresh or force else "up to date"


def sync_tree(src, dst):
    """Copy files that differ; a re-run touches nothing."""
    for f in src.rglob("*"):
        rel = f.relative_to(src)
        if rel.parts[0] in ("node_modules", "out") or f.name == ".DS_Store" or not f.is_file():
            continue
        to = dst / rel
        if not to.exists() or to.read_bytes() != f.read_bytes():
            to.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, to)


def step_remotion(force=False):
    npm = shutil.which("npm")
    if not npm:
        sys.exit(f"npm missing. Install Node first: {fix('node')}")
    REMOTION_HOME.mkdir(parents=True, exist_ok=True)
    sync_tree(REMOTION_SRC, REMOTION_HOME)
    done = "up to date"
    if force or drift(env_load(), {}, remotion_installed() or "missing")["renderer"]:
        # npm ci: exactly package-lock.json, never a re-resolve. --ignore-scripts: the one install
        # script (esbuild's) only re-checks a binary npm already placed; newer npm warns about it.
        subprocess.run([npm, "ci", "--ignore-scripts", "--no-audit", "--no-fund", "--loglevel=error"],
                       cwd=REMOTION_HOME, check=True)
        done = "installed"
    if not list((REMOTION_HOME / "node_modules" / ".remotion").glob("chrome-headless-shell/*")):
        subprocess.run([shutil.which("npx"), "remotion", "browser", "ensure"], cwd=REMOTION_HOME, check=True)
        done = "installed"
    env_save(node_lock=file_sha(NPM_LOCK), node=version(["node", "--version"]),
             npm=version([npm, "--version"]))
    print(f"Renderer {done} in {REMOTION_HOME}")
    return done


def bootstrap(force=False, matte=False):
    """Everything, in order, safe to re-run: a second run downloads nothing and changes nothing."""
    rows = checks()[:4]
    for name, ok, detail, cmd in rows:
        if not ok:
            print(f"FIX  {name:<20} {detail}\n     run: {cmd}")
    if not all(r[1] for r in rows):
        print("Install the tools above first (they ask for a password or need a new terminal), "
              "then run this again.")
        return 1
    steps = [("python packages", step_venv), ("transcription model", step_model), ("renderer", step_remotion)]
    if matte:
        steps.append(("matting model", step_matte))
    for i, (name, fn) in enumerate(steps, 1):
        t = time.time()
        print(f"[{i}/{len(steps)}] {name}", flush=True)
        done = fn(force)
        print(f"[{i}/{len(steps)}] {name}: {done} ({time.time() - t:.0f} s)", flush=True)
    env_save(ffmpeg=version(["ffmpeg", "-version"]), git=version(["git", "--version"]))
    return doctor()


def repair():
    """The exact pinned set again: a fresh venv, npm ci, every model re-verified."""
    return bootstrap(force=True, matte=(models.DIR / "rvm_mobilenetv3_fp32.onnx").exists())


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
    pip_optional("modal")
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


def step_matte(force=False):
    """The Robust Video Matting model matte.py cuts the speaker out with, then a 10-frame test cut."""
    if not VPY.exists():
        sys.exit("Run the venv step first.")
    rel = "rvm_mobilenetv3_fp32.onnx"
    fresh = not (models.DIR / rel).exists()
    script = PLUGIN / "skills" / "style-edit" / "scripts" / "matte.py"
    subprocess.run([str(VPY), str(script), "fetch"], check=True)
    env_save(models={**env_load().get("models", {}), rel: models.PINS[rel][1]})
    r = run([str(VPY), str(script), "demo"])
    if r.returncode:
        sys.exit(f"matte.py demo failed:\n{r.stderr[-1500:]}")
    print("Tested: cutting the speaker out works.")
    return "installed" if fresh or force else "up to date"


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
    # Minimum versions, as each OS prints them.
    assert ffmpeg_version("ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright") == (4, 4) >= FFMPEG_MIN
    assert ffmpeg_version("ffmpeg version 4.2.7-0ubuntu0.1") < FFMPEG_MIN
    assert ffmpeg_version("ffmpeg version 7.1-full_build-www.gyan.dev") >= FFMPEG_MIN
    assert ffmpeg_version("ffmpeg version n7.0.2") >= FFMPEG_MIN
    assert ffmpeg_version("ffmpeg version N-118000-gabc") >= FFMPEG_MIN and ffmpeg_version(None) == (0, 0)
    # The lock pins every package to one version with hashes; opencv-python never sneaks in.
    lines = [x for x in LOCK.read_text().splitlines() if x and not x.startswith((" ", "#"))]
    assert lines and all("==" in x and x.endswith("\\") for x in lines), lines[:3]
    assert not any(x.startswith("opencv-python==") for x in lines)
    assert npm_version("remotion") == json.loads((REMOTION_SRC / "package.json").read_text())["dependencies"]["remotion"]
    # Drift from the pins, fed a made-up env.json: each kind is caught, a clean match is not.
    good = {"python_lock": file_sha(LOCK), "python_packages": {"numpy": "2.5.3", "yt-dlp": "2026.8.19"},
            "node_lock": file_sha(NPM_LOCK), "models": {"yunet.onnx": models.PINS["yunet.onnx"][1]}}
    have = {"numpy": "2.5.3", "yt-dlp": "2026.8.19", "pip": "26.2.1"}
    remo = npm_version("remotion")
    assert drift(good, have, remo) == {"python": [], "renderer": [], "model": []}
    d = drift(good, {**have, "numpy": "1.26.4"}, remo)
    assert d["python"] == ["numpy 1.26.4, pinned 2.5.3"], d
    assert drift(good, {"numpy": "2.5.3"}, remo)["python"] == ["yt-dlp missing, pinned 2026.8.19"]
    assert drift({**good, "python_lock": "old"}, have, remo)["python"][0].startswith("requirements.lock changed")
    assert drift({}, have, None)["python"] == ["installed before version pins"]
    assert drift(good, {}, None) == {"python": [], "renderer": [], "model": []}   # nothing installed: no drift
    assert drift({**good, "node_lock": "old"}, have, remo)["renderer"]
    assert drift(good, have, "4.0.1")["renderer"] == [f"remotion 4.0.1, pinned {remo}"]
    assert drift({**good, "models": {"yunet.onnx": "0" * 64}}, have, remo)["model"]
    # env.json is rewritten only on change, so a second bootstrap leaves it byte-identical.
    global ENV
    keep_env = ENV
    with tempfile.TemporaryDirectory() as d:
        ENV = Path(d) / "env.json"
        env_save(**good)
        before = ENV.stat().st_mtime_ns
        time.sleep(0.01)
        env_save(**good)
        assert ENV.stat().st_mtime_ns == before and env_load() == good
    ENV = keep_env
    print("demo ok")


if __name__ == "__main__":
    cmds = {"doctor": doctor, "venv": step_venv, "model": step_model, "remotion": step_remotion,
            "bootstrap": bootstrap, "repair": repair, "awskey": save_aws_key,
            "lambda": check_lambda, "modal": install_modal, "modal-check": check_modal, "matte": step_matte,
            "demo": demo, "keys": test_keys, "todo": todo, "crisper": install_crisper}
    if sys.argv[1:] == ["doctor", "--quiet"]:
        sys.exit(doctor_quiet())
    if sys.argv[1:] == ["bootstrap", "--matte"]:
        sys.exit(bootstrap(matte=True))
    if len(sys.argv) == 3 and sys.argv[1] == "later":
        sys.exit(later(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "setkey":
        sys.exit(set_key(sys.argv[2]))
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(2)
    r = cmds[sys.argv[1]]()
    sys.exit(r if isinstance(r, int) else 0)   # steps return "installed" / "up to date"
