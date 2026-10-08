#!/usr/bin/env python3
"""A fresh install, twice: the bootstrap from zero, a second run that must change nothing, then
drift that doctor must catch and repair must undo.

    python tests/fresh_install.py [--matte]
    python tests/fresh_install.py demo        # self-check of the timing table

Ends with a table of how long each step took (the cold install times on CI), also written to
$GITHUB_STEP_SUMMARY when set.

Installs into AI_EDITOR_HOME when it is set (CI sets it, then runs tests/smoke.py against it),
else into a new temp folder. Needs Python 3.10+, ffmpeg, Node and git (doctor says how).
"""
import json
import os
import re
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
TIMES = []   # (step, seconds), in run order


def step_times(out):
    """The bootstrap's own '[1/4] python packages: installed (19 s)' lines -> [(name, seconds)]."""
    return [(n, int(s)) for n, s in re.findall(r"^\[\d+/\d+\] (.+?): \S.*?\((\d+) s\)$", out, re.M)]


def table(rows):
    """Markdown table of (step, seconds)."""
    return "\n".join(["| step | seconds |", "|---|---:|", *(f"| {n} | {s:.0f} |" for n, s in rows)])


def demo():
    out = "[1/4] python packages\nready\n[1/4] python packages: installed (19 s)\n[3/4] renderer: up to date (0 s)\n"
    assert step_times(out) == [("python packages", 19), ("renderer", 0)], step_times(out)
    assert table([("a b", 1.4)]) == "| step | seconds |\n|---|---:|\n| a b | 1 |"
    print("fresh_install demo ok")


def setup(*args, check=True):
    t = time.time()
    r = subprocess.run([sys.executable, str(SETUP), *args], env=ENV, capture_output=True, text=True)
    took = time.time() - t
    TIMES.append((f"setup.py {' '.join(args)}", took))
    print(f"--- setup.py {' '.join(args)}: exit {r.returncode} in {took:.0f} s\n{r.stdout}{r.stderr}", flush=True)
    if check and r.returncode:
        sys.exit(f"FRESH INSTALL FAIL: setup.py {' '.join(args)} exited {r.returncode}")
    return r


def main():
    print(f"AI_EDITOR_HOME={HOME}  python {sys.version.split()[0]}", flush=True)
    boot = ["bootstrap", "--matte"] if "--matte" in sys.argv else ["bootstrap"]
    first = setup(*boot).stdout
    TIMES[0:0] = [(f"cold: {n}", t) for n, t in step_times(first)]
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
    md = f"### Fresh install times ({sys.platform}, python {sys.version.split()[0]})\n\n{table(TIMES)}\n"
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)


if __name__ == "__main__":
    demo() if sys.argv[1:] == ["demo"] else main()
