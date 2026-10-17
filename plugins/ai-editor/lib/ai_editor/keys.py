"""One key store for both plugins.

    from ai_editor import keys
    key, where = keys.get("gemini")        # (None, None) when there is none
    keys.save("gemini", "AIza...")         # keeps the other keys in the file
    ok, msg = keys.verify("gemini", key)   # one free request

The file is ~/.config/creator-teardown/.env (KEY=value lines, chmod 600), the same one
creator-teardown's `fetch.py setkey` writes, so a key saved by either plugin works in both.
With AI_EDITOR_HOME set, the file is $AI_EDITOR_HOME/.env instead and the shared one is never
read or written, so an isolated test run never finds or spends real keys.
An environment variable of the same name wins over the file. A .env in the working folder is never
read: it belongs to whatever project Claude Code started in. Lines for other keys (creator-teardown's,
or an old TYPESAFE_API_KEY) are kept as they are and never read here.
"""
import contextlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    from ai_editor import net
except ImportError:   # run as a script from this folder
    import net

KEY_FILE = Path.home() / ".config" / "creator-teardown" / ".env"


def key_file():
    """$AI_EDITOR_HOME/.env when AI_EDITOR_HOME is set, else the shared KEY_FILE."""
    home = os.environ.get("AI_EDITOR_HOME", "").strip()
    return Path(home) / ".env" if home else KEY_FILE
VARS = {"gemini": "GEMINI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "zernio": "ZERNIO_API_KEY"}
# The fixed start of each vendor's key, checked before any request. Google keys start with AQ. or AIza
# (creator-teardown references/setup.md). ElevenLabs' older keys have none.
PREFIX = {"gemini": ("AIza", "AQ.")}   # AI Studio issues AQ. keys since mid-2026; older keys start AIza
NAMES = {"gemini": "Gemini", "elevenlabs": "ElevenLabs", "zernio": "Zernio"}


def get(name):
    """(key, where it came from) or (None, None). `name` is gemini, elevenlabs or zernio.
    Never a .env in the working folder: that is another project's, and its key would be billed."""
    var, p = VARS[name], key_file()
    if os.environ.get(var, "").strip():
        return os.environ[var].strip(), f"the {var} variable"
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None, None
    for line in lines:
        if line.startswith(f"{var}="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key, str(p)
    return None, None


def write_private(path, text):
    """Write a secrets file readable by this user only: a 0600 temp file beside it, then os.replace, so a
    reader never sees it half written and the file is never readable by others, not even for a moment."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


@contextlib.contextmanager
def _locked(path, wait=10):
    """One writer at a time (the home window's threads, setup.py): a lock file beside the key file, made
    with O_EXCL. One left by a writer that died is stale after 10 s."""
    lock = Path(path).with_name(Path(path).name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(int(wait / 0.025)):
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            break
        except (FileExistsError, PermissionError):   # Windows: a lock being deleted refuses a new open
            try:
                if time.time() - lock.stat().st_mtime > 10:
                    lock.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(0.025)
    else:
        raise TimeoutError(f"{lock} is held; delete it if nothing is saving a key")
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _rewrite(name, key, path):
    """Drop VAR= from the file and add VAR=key (None: only drop), keeping every other line, under the lock."""
    var, path = VARS[name], Path(path or key_file())
    path.parent.mkdir(parents=True, exist_ok=True)
    with _locked(path):
        keep = [ln for ln in (path.read_text(encoding="utf-8").splitlines() if path.exists() else [])
                if ln.strip() and not ln.startswith(f"{var}=")]
        lines = keep + ([f"{var}={key}"] if key is not None else [])
        return write_private(path, "\n".join(lines) + "\n" if lines else "")


def save(name, key, path=None):
    """Write VAR=key, keeping every other line. Readable by this user only."""
    return _rewrite(name, key, path)


def remove(name, path=None):
    """Delete VAR= from the key file, keeping every other line. The file is shared with creator-teardown."""
    return _rewrite(name, None, path)


def _get(url, headers):
    req = urllib.request.Request(url, headers={"User-Agent": "ai-video-editor", **headers})
    try:
        with net.urlopen(req, 20) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")
    except (urllib.error.URLError, OSError) as e:
        return 0, net.friendly(e)


def verify(name, key):
    """(ok, message). Each check is a free listing call: nothing is billed. A key without its vendor's
    fixed prefix is refused here, so text that is not that key never leaves the computer."""
    if name in PREFIX and not key.startswith(PREFIX[name]):
        return False, f"this is not a {NAMES[name]} key, so nothing was sent. {NAMES[name]} keys start with {' or '.join(PREFIX[name])}"
    if name == "gemini":
        code, body = _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                          {"x-goog-api-key": key})
    elif name == "zernio":   # the posting key (post.py): listing the connected accounts is free
        code, body = _get("https://zernio.com/api/v1/profiles", {"Authorization": f"Bearer {key}"})
    else:
        code, body = _get("https://api.elevenlabs.io/v1/user", {"xi-api-key": key})
        # A key restricted to Speech to Text (what setup asks for) may not read /v1/user.
        # That refusal still proves the key exists.
        if code == 401 and "missing_permissions" in body:
            code = 200
    if code == 200:
        return True, "key works"
    if code == 0:
        return False, body if body == net.FIX else f"no connection ({body[:80]})"
    if code in (401, 403) or (code == 400 and "key" in body.lower()):
        return False, "the service rejected this key. Copy it again, or make a new one."
    return False, f"HTTP {code}: {body[:120]}"


if __name__ == "__main__":   # self-check: saving one key keeps the others
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / ".env"
        save("elevenlabs", "a" * 24, f)
        f.write_text(f.read_text(encoding="utf-8") + f"TYPESAFE_API_KEY={'t' * 24}\n", encoding="utf-8")  # a key no longer used
        save("gemini", "AIza" + "b" * 24, f)
        save("gemini", "AIza" + "c" * 24, f)
        assert f.read_text(encoding="utf-8") == (f"ELEVENLABS_API_KEY={'a' * 24}\nTYPESAFE_API_KEY={'t' * 24}\n"
                                                 f"GEMINI_API_KEY=AIza{'c' * 24}\n")   # the old line is kept, never read
        assert os.name == "nt" or f.stat().st_mode & 0o777 == 0o600
        # AI_EDITOR_HOME isolates: its .env is read first, the shared file never
        os.environ["AI_EDITOR_HOME"] = d
        os.environ.pop("GEMINI_API_KEY", None)
        assert key_file() == f and get("gemini") == ("AIza" + "c" * 24, str(f))
        assert save("elevenlabs", "d" * 24) == f
        f.unlink()
        # many threads saving different keys at once: every key survives, no temp or lock file is left
        names = sorted(VARS) * 10   # whichever keys this plugin has
        ts = [threading.Thread(target=save, args=(n, n[0] * 24 + str(i), f)) for i, n in enumerate(names)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        got = dict(ln.split("=", 1) for ln in f.read_text(encoding="utf-8").splitlines())
        assert set(got) == set(VARS.values()), got
        assert sorted(x.name for x in Path(d).iterdir()) == [".env"], list(Path(d).iterdir())
        remove("gemini", f)
        assert "GEMINI_API_KEY" not in f.read_text(encoding="utf-8") and "ELEVENLABS_API_KEY" in f.read_text(encoding="utf-8")
        assert os.name == "nt" or f.stat().st_mode & 0o777 == 0o600
        f.unlink()
        # text without the vendor's prefix is refused before any request
        real_get, sent = _get, []
        globals()["_get"] = lambda *a: sent.append(a) or (200, "")
        try:
            ok, msg = verify("gemini", "x" * 39)
            assert not ok and "Gemini" in msg and "AIza" in msg and not sent, (msg, sent)
            assert verify("gemini", "AIza" + "x" * 35)[0] and len(sent) == 1
            assert verify("gemini", "AQ.Ab" + "x" * 40)[0] and len(sent) == 2   # the newer AI Studio format
            assert verify("elevenlabs", "x" * 32)[0]   # no fixed prefix
        finally:
            globals()["_get"] = real_get
        cwd = os.getcwd()
        work = Path(d) / "another-project"
        work.mkdir()
        (work / ".env").write_text(f"ELEVENLABS_API_KEY={'e' * 24}\n", encoding="utf-8")
        os.chdir(work)   # the folder Claude Code started in: its .env is another project's, never read
        try:
            os.environ.pop("ELEVENLABS_API_KEY", None)
            assert get("elevenlabs") == (None, None), "read a key from the working folder's .env"
        finally:
            os.chdir(cwd)
        # a new key file is 0600 from its first byte: with chmod doing nothing, the mode is still 0600
        if os.name != "nt":
            real, old_mask = os.chmod, os.umask(0)
            os.chmod = lambda *a, **k: None
            try:
                g = save("elevenlabs", "f" * 24, Path(d) / "new" / ".env")
            finally:
                os.chmod, _ = real, os.umask(old_mask)
            assert g.stat().st_mode & 0o777 == 0o600, oct(g.stat().st_mode)
    print("keys ok")
