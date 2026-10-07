"""Run a script with the editor's venv Python, wherever AI_EDITOR_HOME puts it. Stdlib only.

    python3 run.py <script.py> [args]      (`py` instead of `python3` on Windows)
    python3 run.py -m modal token new
    python3 run.py demo                    self-check

The venv is $AI_EDITOR_HOME/venv (default ~/.ai-video-editor/venv), bin/python or Scripts\\python.exe.
Before setup has made it, the script runs with this Python and a note says so.
"""
import os
import subprocess
import sys
from pathlib import Path


def venv_python(home=None, windows=os.name == "nt"):
    home = Path(home or os.environ.get("AI_EDITOR_HOME", "").strip() or Path.home() / ".ai-video-editor")
    return home / "venv" / ("Scripts/python.exe" if windows else "bin/python")


def demo():
    assert venv_python("/x", windows=False) == Path("/x/venv/bin/python")
    assert venv_python("/x", windows=True) == Path("/x/venv/Scripts/python.exe")
    os.environ["AI_EDITOR_HOME"] = "/elsewhere"
    assert venv_python(windows=False) == Path("/elsewhere/venv/bin/python")
    print("run demo ok")


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    if argv == ["demo"]:
        return demo()
    py = venv_python()
    if not py.exists():
        print(f"note: no editor venv at {py} yet (the setup skill makes it); running with {sys.executable}",
              file=sys.stderr)
        py = Path(sys.executable)
    if os.name != "nt":
        os.execv(str(py), [str(py), *argv])
    return subprocess.call([str(py), *argv])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
