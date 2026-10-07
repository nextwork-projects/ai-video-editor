#!/usr/bin/env python3
"""Word-level transcription: local faster-whisper (free) or ElevenLabs Scribe v2.

Engine: Scribe v2 when an ElevenLabs key exists, else faster-whisper. Force one
with --engine. Both write the same transcript.json: text, audio_duration_secs and
a words list ({text, start, end, type}), in seconds.

Whisper runs locally on a media file. Its initial prompt is seeded with fillers
so it keeps more of the ums and false starts, but it still drops some. Scribe is
verbatim by default and keeps them all, which makes the voice profile better.
Scribe also takes a TikTok or YouTube link and fetches it itself.

Whisper needs the venv at ~/.ai-video-editor/venv (faster-whisper). Model size:
AI_EDITOR_WHISPER_MODEL (default small).

Usage:
  python3 scripts/transcribe.py <media file> <out.json>
  python3 scripts/transcribe.py https://www.tiktok.com/@someone/video/123 <out.json> --engine scribe
  python3 scripts/transcribe.py <media> <out.json> --keyterm Duolingo --keyterm AlphaFold

Options:
  --engine NAME    whisper | scribe (default: scribe if a key exists, else whisper)
  --keyterm TERM   add one keyterm (repeatable) to bias transcription toward it
                   (Scribe: keyterms; Whisper: added to the initial prompt)
  --clean          Scribe only. ALSO fetch a no_verbatim=true pass, saved as
                   <out>.clean.json.
  --lang CODE      ISO-639-1 language code (default: en)

The key comes from the ELEVENLABS_API_KEY variable, a .env in the current
folder, or the file `fetch.py setkey` writes, in that order.

Scribe keyterms add $0.05 per hour of audio. Cap is 1000 terms, <=50 chars each,
<=5 words each; this script enforces those limits and drops what violates them.

Exit codes: 0 ok · 1 error · 2 usage/missing key · 3 HTTP error
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
MODEL = "scribe_v2"
# One key for every folder. Outside the skill folder, so git pull and plugin
# updates never touch it.
KEY_FILE = Path.home() / ".config" / "creator-teardown" / ".env"
HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
VENV_PY = HOME / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
FILLER_PROMPT = "Umm, uh, so, like, you know, I mean... uh, okay, um, right."

# Keyterm limits, per the Scribe v2 API reference.
MAX_KEYTERMS = 1000
MAX_KEYTERM_CHARS = 50
MAX_KEYTERM_WORDS = 5
BAD_KEYTERM_CHARS = set('<>{}[]\\')


def find_key(var="ELEVENLABS_API_KEY"):
    """(key, where it came from), or (None, None). `var` picks which key:
    ELEVENLABS_API_KEY (transcripts) or GEMINI_API_KEY (the look pass)."""
    if os.environ.get(var):
        return os.environ[var].strip(), f"the {var} variable"
    for p in (Path.cwd() / ".env", KEY_FILE):
        if p.exists():
            for line in p.read_text().splitlines():
                if line.startswith(f"{var}="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key, str(p)
    return None, None


def api_key():
    key, _ = find_key()
    if not key:
        fetch = Path(__file__).resolve().with_name("fetch.py")
        print(f"ERROR: no ElevenLabs key. Save one with: python3 {fetch} setkey",
              file=sys.stderr)
        sys.exit(2)
    return key


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("FAIL: " + " ".join(cmd) + "\n" + r.stderr + "\n")
        sys.exit(1)
    return r


def extract_audio(src, dst):
    """16 kHz mono WAV -- ~1.5 MB/min instead of uploading multi-GB video."""
    run(["ffmpeg", "-y", "-i", str(src), "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])


def clean_keyterms(raw):
    out = []
    seen = set()
    for t in raw:
        t = t.strip()
        if not t or t.lower() in seen:
            continue
        if len(t) > MAX_KEYTERM_CHARS:
            continue
        if len(t.split()) > MAX_KEYTERM_WORDS:
            continue
        if any(c in BAD_KEYTERM_CHARS for c in t):
            continue
        seen.add(t.lower())
        out.append(t)
    return out[:MAX_KEYTERMS]


def multipart_nofile(fields):
    """Same encoding, no file part -- for source_url requests."""
    boundary = "----oneshotedit" + os.urandom(16).hex()
    body = bytearray()
    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += str(value).encode() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def multipart(fields, filename, filedata):
    """Hand-rolled multipart/form-data -- stdlib only, no `requests`.

    `fields` is a list of (name, value) pairs; repeated names are how a
    list-valued param (keyterms) is sent.
    """
    boundary = "----oneshotedit" + os.urandom(16).hex()
    body = bytearray()
    for name, value in fields:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += str(value).encode() + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
             f"Content-Type: audio/wav\r\n\r\n").encode()
    body += filedata + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def transcribe(wav_path, key, keyterms, lang, no_verbatim, url=None):
    """wav_path is a local file, OR pass url= to let Scribe fetch it.

    source_url accepts hosted media plus YouTube and TikTok video URLs. Tested
    against a downloaded-audio transcript of the same TikTok: 64 words vs 63,
    identical first-word timing.
    """
    fields = [
        ("model_id", MODEL),
        ("timestamps_granularity", "word"),
        ("tag_audio_events", "true"),
        ("no_verbatim", "true" if no_verbatim else "false"),
        ("diarize", "false"),
        ("num_speakers", "1"),
        ("temperature", "0"),
        ("seed", "0"),
    ]
    if lang:
        fields.append(("language_code", lang))
    for t in keyterms:
        fields.append(("keyterms", t))

    if url:
        fields.append(("source_url", url))
        body, ctype = multipart_nofile(fields)
    else:
        data = Path(wav_path).read_bytes()
        body, ctype = multipart(fields, Path(wav_path).name, data)
    req = urllib.request.Request(
        API_URL, data=body,
        headers={"xi-api-key": key, "Content-Type": ctype},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {detail[:600]}", file=sys.stderr)
        sys.exit(3)


def whisper(media, lang, keyterms):
    """faster-whisper with word timestamps, in the same shape Scribe returns."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
            # Rerun inside the tool venv, where faster-whisper lives.
            sys.exit(subprocess.run([str(VENV_PY), *sys.argv]).returncode)
        print("ERROR: faster-whisper is not installed. Run fetch.py doctor for the fix.",
              file=sys.stderr)
        sys.exit(2)
    name = os.environ.get("AI_EDITOR_WHISPER_MODEL", "small")
    pinned = HOME / "models" / f"faster-whisper-{name}"   # the ai-editor setup's pinned copy
    model = WhisperModel(str(pinned) if (pinned / "model.bin").exists() else name, device="cpu",
                         compute_type="int8", download_root=str(HOME / "models"))
    prompt = FILLER_PROMPT + (" " + ", ".join(keyterms) + "." if keyterms else "")
    segs, info = model.transcribe(str(media), language=lang or None, word_timestamps=True,
                                  initial_prompt=prompt, vad_filter=False)
    words = []
    for seg in segs:
        for w in seg.words or []:
            if words and w.start > words[-1]["end"]:
                words.append({"text": " ", "start": words[-1]["end"], "end": round(w.start, 3),
                              "type": "spacing"})
            words.append({"text": w.word.strip(), "start": round(w.start, 3),
                          "end": round(w.end, 3), "type": "word"})
    text = " ".join(w["text"] for w in words if w["type"] == "word")
    return {"text": text, "language_code": info.language,
            "audio_duration_secs": round(info.duration, 3), "words": words,
            "_engine": "whisper"}


def summarise(payload, label):
    words = [w for w in payload.get("words", []) if w.get("type") == "word"]
    events = [w for w in payload.get("words", []) if w.get("type") == "audio_event"]
    dur = max((w.get("end", 0) for w in payload.get("words", [])), default=0)
    print(f"  {label}: {len(words)} words, {len(events)} audio events, {dur:.1f}s")
    return words


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("media")
    ap.add_argument("out")
    ap.add_argument("--keyterm", action="append", default=[])
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--engine", choices=["whisper", "scribe"], default=None)
    args = ap.parse_args()
    engine = args.engine or ("scribe" if find_key()[0] else "whisper")

    is_url = args.media.startswith(("http://", "https://"))
    src = Path(args.media)
    if not is_url and not src.exists():
        print(f"ERROR: no such file: {src}", file=sys.stderr)
        sys.exit(1)

    keyterms = clean_keyterms(set(args.keyterm))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if engine == "whisper":
        if is_url:
            print("ERROR: whisper needs a local file. Download it first, or use --engine scribe.",
                  file=sys.stderr)
            sys.exit(2)
        print("transcribing locally with faster-whisper...")
        payload = whisper(src, args.lang, keyterms)
        payload["_source"] = str(src.resolve())
        summarise(payload, "whisper")
        out_path.write_text(json.dumps(payload, indent=2))
        print(out_path)
        return

    key = api_key()

    if is_url:
        wav = None
        print(f"source_url -> {args.media}")
    else:
        wav = out_path.parent / (src.stem + ".16k.wav")
        print(f"extracting audio -> {wav}")
        extract_audio(src, wav)
        print(f"  {wav.stat().st_size / 1e6:.1f} MB")

    if keyterms:
        print(f"keyterms: {len(keyterms)} (+$0.05/hour) e.g. {', '.join(keyterms[:8])}")

    print("transcribing (verbatim)...")
    payload = transcribe(wav, key, keyterms, args.lang, no_verbatim=False,
                         url=args.media if is_url else None)
    payload["_source"] = args.media if is_url else str(src.resolve())
    payload["_keyterms"] = keyterms
    payload["_engine"] = "scribe"
    summarise(payload, "verbatim")
    out_path.write_text(json.dumps(payload, indent=2))
    print(out_path)

    if args.clean:
        print("transcribing (no_verbatim=true, for diff)...")
        clean = transcribe(wav, key, keyterms, args.lang, no_verbatim=True,
                           url=args.media if is_url else None)
        summarise(clean, "clean")
        cp = out_path.with_suffix(".clean.json")
        cp.write_text(json.dumps(clean, indent=2))
        print(cp)

    if wav:
        wav.unlink(missing_ok=True)  # 1.5 MB/min, and the transcript is the product


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main()
