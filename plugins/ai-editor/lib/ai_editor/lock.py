#!/usr/bin/env python3
"""Pinned subsets of requirements/requirements.lock. Stdlib only.

    python3 lock.py teardown   rewrite creator-teardown's copy (its share of the lock, hashes and all)
    python3 lock.py demo       self-check

subset(roots) keeps each root and everything the lock says it pulls in (the `# via` lines), every
platform's line, hashes included, so `pip install --no-deps --require-hashes -r` installs exactly
those pins anywhere. matte.py builds the Modal image from one; creator-teardown ships another,
and tests/check_plugins.py fails when that copy drifts from the lock.
"""
import re
import sys
from pathlib import Path

LOCK = Path(__file__).resolve().parents[2] / "requirements" / "requirements.lock"
TEARDOWN_LOCK = (Path(__file__).resolve().parents[4] / "plugins" / "creator-teardown" / "skills"
                 / "creator-teardown" / "requirements.lock")
# What creator-teardown's scripts import: transcription, frames, OCR, listing.
TEARDOWN_ROOTS = ("faster-whisper", "numpy", "pillow", "yt-dlp", "opencv-python-headless", "ocrmac", "rapidocr")
MATTE_ROOTS = ("numpy", "opencv-python-headless", "onnxruntime")
REQ = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)(?:\s*;\s*(.*?))?\s*\\?$")


def blocks(text):
    """[{name, version, marker, via, text}] in file order. A block is a pin line and its hashes and comments."""
    out = []
    for line in text.splitlines():
        m = REQ.match(line)
        if m:
            out.append({"name": m[1].lower(), "version": m[2], "marker": m[3] or None, "via": set(), "lines": [line]})
        elif out and line.startswith("    "):
            out[-1]["lines"].append(line)
            v = re.match(r"\s*#\s+(?:via\s+)?([A-Za-z0-9][A-Za-z0-9._-]*)\s*$", line)
            if v and not line.strip().startswith("# via -r"):
                out[-1]["via"].add(v[1].lower())
    for b in out:
        b["text"] = "\n".join(b.pop("lines"))
    return out


def subset(roots, text=None):
    """The lock's lines for `roots` and everything they pull in, as a requirements file."""
    bs = blocks(text if text is not None else LOCK.read_text(encoding="utf-8"))
    keep = {r.lower() for r in roots}
    missing = keep - {b["name"] for b in bs}
    if missing:
        raise SystemExit(f"not in the lock: {', '.join(sorted(missing))}")
    while True:
        more = {b["name"] for b in bs if b["via"] & keep} - keep
        if not more:
            break
        keep |= more
    head = ("# Generated from plugins/ai-editor/requirements/requirements.lock by plugins/ai-editor/lib/ai_editor/lock.py\n"
            f"# (roots: {' '.join(roots)}). Do not edit; run `python3 lock.py teardown` there.\n"
            "# Install: pip install --no-deps --require-hashes -r requirements.lock\n")
    return head + "\n".join(b["text"] for b in bs if b["name"] in keep) + "\n"


def pins(text):
    """{name: {version, ...}} of a requirements file."""
    out = {}
    for b in blocks(text):
        out.setdefault(b["name"], set()).add(b["version"])
    return out


def demo():
    lock = LOCK.read_text(encoding="utf-8")
    full = pins(lock)
    s = subset(MATTE_ROOTS, lock)
    got = pins(s)
    for r in MATTE_ROOTS:
        assert got[r] == full[r], (r, got[r], full[r])
    assert "flatbuffers" in got and "protobuf" in got, got        # onnxruntime's own deps came along
    assert "yt-dlp" not in got and "faster-whisper" not in got, got
    assert s.count("--hash=sha256:") >= 10
    # every block kept verbatim, hashes and markers included
    whole = {b["text"] for b in blocks(lock)}
    assert all(b["text"] in whole for b in blocks(s))
    t = pins(subset(TEARDOWN_ROOTS, lock))
    assert t["yt-dlp"] == full["yt-dlp"] and "pip" not in t and "huggingface-hub" in t, t
    print(f"demo ok (matte image: {len(got)} packages, creator-teardown: {len(t)})")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["demo"]:
        demo()
    elif a == ["teardown"]:
        TEARDOWN_LOCK.write_text(subset(TEARDOWN_ROOTS), encoding="utf-8")
        print(TEARDOWN_LOCK)
    else:
        sys.exit(__doc__)
