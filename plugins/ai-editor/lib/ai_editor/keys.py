"""One key store for both plugins.

    from ai_editor import keys
    key, where = keys.get("typesafe")      # (None, None) when there is none
    keys.save("typesafe", "ts-...")        # keeps the other keys in the file
    ok, msg = keys.verify("typesafe", key) # one free request

The file is ~/.config/creator-teardown/.env (KEY=value lines, chmod 600), the same one
creator-teardown's `fetch.py setkey` writes, so a key saved by either plugin works in both.
With AI_EDITOR_HOME set, the file is $AI_EDITOR_HOME/.env instead and the shared one is never
read or written, so an isolated test run never finds or spends real keys.
An environment variable of the same name wins over the file. A .env in the working folder is never
read: it belongs to whatever project Claude Code started in.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

KEY_FILE = Path.home() / ".config" / "creator-teardown" / ".env"


def key_file():
    """$AI_EDITOR_HOME/.env when AI_EDITOR_HOME is set, else the shared KEY_FILE."""
    home = os.environ.get("AI_EDITOR_HOME", "").strip()
    return Path(home) / ".env" if home else KEY_FILE
VARS = {"typesafe": "TYPESAFE_API_KEY", "gemini": "GEMINI_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY"}
# The fixed start of each vendor's key, checked before any request. Google API keys start with AIza
# (creator-teardown references/setup.md). TypeSafe documents none; ElevenLabs' older keys have none.
PREFIX = {"gemini": "AIza"}
NAMES = {"typesafe": "TypeSafe", "gemini": "Gemini", "elevenlabs": "ElevenLabs"}


def get(name):
    """(key, where it came from) or (None, None). `name` is typesafe, gemini or elevenlabs.
    Never a .env in the working folder: that is another project's, and its key would be billed."""
    var, p = VARS[name], key_file()
    if os.environ.get(var, "").strip():
        return os.environ[var].strip(), f"the {var} variable"
    try:
        lines = p.read_text().splitlines()
    except OSError:
        return None, None
    for line in lines:
        if line.startswith(f"{var}="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key, str(p)
    return None, None


def write_private(path, text):
    """Write a secrets file readable by this user only, 0600 from the moment it exists (never written, then
    chmodded). An older file gets 0600 before the new text goes in."""
    path = Path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def save(name, key, path=None):
    """Write VAR=key, keeping every other line. Readable by this user only."""
    var, path = VARS[name], Path(path or key_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = [ln for ln in (path.read_text().splitlines() if path.exists() else [])
            if ln.strip() and not ln.startswith(f"{var}=")]
    return write_private(path, "\n".join(keep + [f"{var}={key}"]) + "\n")


def _get(url, headers):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-video-editor", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def verify(name, key):
    """(ok, message). Each check is a free listing call: nothing is billed. A key without its vendor's
    fixed prefix is refused here, so text that is not that key never leaves the computer."""
    if name in PREFIX and not key.startswith(PREFIX[name]):
        return False, f"this is not a {NAMES[name]} key: {NAMES[name]} keys start with {PREFIX[name]}. Nothing was sent."
    if name == "typesafe":
        code, body = _get("https://api.typesafe.ai/v1/models", {"Authorization": f"Bearer {key}"})
    elif name == "gemini":
        code, body = _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                          {"x-goog-api-key": key})
    else:
        code, body = _get("https://api.elevenlabs.io/v1/user", {"xi-api-key": key})
        # A key restricted to Speech to Text (what setup asks for) may not read /v1/user.
        # That refusal still proves the key exists.
        if code == 401 and "missing_permissions" in body:
            code = 200
    if code == 200:
        return True, "key works"
    if code == 0:
        return False, f"no connection ({body[:80]})"
    if code in (401, 403) or (code == 400 and "key" in body.lower()):
        return False, "the service rejected this key. Copy it again, or make a new one."
    return False, f"HTTP {code}: {body[:120]}"


if __name__ == "__main__":   # self-check: saving one key keeps the others
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / ".env"
        save("elevenlabs", "a" * 24, f)
        save("typesafe", "b" * 24, f)
        save("typesafe", "c" * 24, f)
        assert f.read_text() == f"ELEVENLABS_API_KEY={'a' * 24}\nTYPESAFE_API_KEY={'c' * 24}\n"
        assert os.name == "nt" or f.stat().st_mode & 0o777 == 0o600
        # AI_EDITOR_HOME isolates: its .env is read first, the shared file never
        os.environ["AI_EDITOR_HOME"] = d
        os.environ.pop("TYPESAFE_API_KEY", None)
        assert key_file() == f and get("typesafe") == ("c" * 24, str(f))
        assert save("gemini", "d" * 24) == f
        f.unlink()
        # text without the vendor's prefix is refused before any request
        real_get, sent = _get, []
        globals()["_get"] = lambda *a: sent.append(a) or (200, "")
        try:
            ok, msg = verify("gemini", "x" * 39)
            assert not ok and "Gemini" in msg and "AIza" in msg and not sent, (msg, sent)
            assert verify("gemini", "AIza" + "x" * 35)[0] and len(sent) == 1
            assert verify("typesafe", "x" * 30)[0] and verify("elevenlabs", "x" * 32)[0]   # no fixed prefix
        finally:
            globals()["_get"] = real_get
        cwd = os.getcwd()
        work = Path(d) / "another-project"
        work.mkdir()
        (work / ".env").write_text(f"TYPESAFE_API_KEY={'e' * 24}\n")
        os.chdir(work)   # the folder Claude Code started in: its .env is another project's, never read
        try:
            assert get("typesafe") == (None, None), "read a key from the working folder's .env"
        finally:
            os.chdir(cwd)
        # a new key file is 0600 from its first byte: with chmod doing nothing, the mode is still 0600
        if os.name != "nt":
            real, old_mask = os.chmod, os.umask(0)
            os.chmod = lambda *a, **k: None
            try:
                g = save("typesafe", "f" * 24, Path(d) / "new" / ".env")
            finally:
                os.chmod, _ = real, os.umask(old_mask)
            assert g.stat().st_mode & 0o777 == 0o600, oct(g.stat().st_mode)
    print("keys ok")
