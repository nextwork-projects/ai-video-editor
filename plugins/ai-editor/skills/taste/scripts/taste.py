#!/usr/bin/env python3
"""CLI for the user's taste. The code lives in the plugin's lib/ai_editor/taste.py (shared with cut and style-edit).

    python3 taste.py show | rule <section> "<rule>" | set <key.path> <value> | unset <key.path> | get | demo
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from ai_editor.taste import main  # noqa: E402

if __name__ == "__main__":
    main()
