"""One key store for both plugins.

    from ai_editor import keys
    key, where = keys.get("typesafe")      # (None, None) when there is none
    keys.save("typesafe", "ts-...")        # keeps the other keys in the file
    ok, msg = keys.verify("typesafe", key) # one free request

The file is ~/.config/creator-teardown/.env (KEY=value lines, chmod 600), the same one
creator-teardown's `fetch.py setkey` writes, so a key saved by either plugin works in both.
With AI_EDITOR_HOME set, the file is $AI_EDITOR_HOME/.env instead and the shared one is never
read or written, so an isolated test run never finds or spends real keys.
An environment variable of the same name wins over the file; a .env in the working folder
comes next, as in creator-teardown.
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


def get(name):
    """(key, where it came from) or (None, None). `name` is typesafe, gemini or elevenlabs."""
    var = VARS[name]
    if os.environ.get(var, "").strip():
        return os.environ[var].strip(), f"the {var} variable"
    for p in (key_file(), Path.cwd() / ".env"):
        try:
            lines = p.read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith(f"{var}="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key, str(p)
    return None, None


def save(name, key, path=None):
    """Write VAR=key, keeping every other line. Readable by this user only."""
    var, path = VARS[name], Path(path or key_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    keep = [ln for ln in (path.read_text().splitlines() if path.exists() else [])
            if ln.strip() and not ln.startswith(f"{var}=")]
    path.write_text("\n".join(keep + [f"{var}={key}"]) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


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
    """(ok, message). Each check is a free listing call: nothing is billed."""
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
        cwd = os.getcwd()
        os.chdir(d)   # an empty folder: nothing else may answer
        try:
            assert get("typesafe") == (None, None), "found a key outside AI_EDITOR_HOME"
        finally:
            os.chdir(cwd)
    print("keys ok")
