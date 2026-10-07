#!/usr/bin/env python3
"""A fresh install, twice: the bootstrap from zero, a second run that must change nothing, then
drift that doctor must catch and repair must undo.

    python tests/fresh_install.py [--matte]

Installs into AI_EDITOR_HOME when it is set (CI sets it, then runs tests/smoke.py against it),
else into a new temp folder. Needs Python 3.10+, ffmpeg, Node and git (doctor says how).
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "plugins" / "ai-editor" / "skills" / "setup" / "scripts" / "setup.py"
HOME = Path(os.environ.get("AI_EDITOR_HOME") or tempfile.mkdtemp(prefix="ave-home-"))
ENV = dict(os.environ, AI_EDITOR_HOME=str(HOME))
VPY = HOME / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def setup(*args, check=True):
    t = time.time()
    r = subprocess.run([sys.executable, str(SETUP), *args], env=ENV, capture_output=True, text=True)
    print(f"--- setup.py {' '.join(args)}: exit {r.returncode} in {time.time() - t:.0f} s\n{r.stdout}{r.stderr}",
          flush=True)
    if check and r.returncode:
        sys.exit(f"FRESH INSTALL FAIL: setup.py {' '.join(args)} exited {r.returncode}")
    return r


def main():
    print(f"AI_EDITOR_HOME={HOME}  python {sys.version.split()[0]}", flush=True)
    boot = ["bootstrap", "--matte"] if "--matte" in sys.argv else ["bootstrap"]
    setup(*boot)
    env1 = (HOME / "env.json").read_bytes()

    again = setup(*boot).stdout
    steps = [x for x in again.splitlines() if x.startswith("[") and ": " in x]
    assert steps and all(": up to date" in x for x in steps), f"second bootstrap did work: {steps}"
    assert "downloading" not in again, "second bootstrap downloaded something"
    assert (HOME / "env.json").read_bytes() == env1, "second bootstrap rewrote env.json"

    pinned = json.loads(env1)["python_packages"]["idna"]
    other = "3.10" if pinned != "3.10" else "3.9"
    subprocess.run([str(VPY), "-m", "pip", "install", "-q", "--disable-pip-version-check", f"idna=={other}"],
                   check=True)
    doc = setup("doctor", check=False)
    assert doc.returncode == 1 and f"idna {other}, pinned {pinned}" in doc.stdout and "repair" in doc.stdout, \
        "doctor missed the drift"
    setup("repair")
    assert setup("doctor").returncode == 0
    print(f"FRESH INSTALL OK: bootstrap, idempotent re-run, drift caught, repair restored ({HOME})")


if __name__ == "__main__":
    main()
