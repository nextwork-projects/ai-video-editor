#!/usr/bin/env python3
"""Verbatim word-level transcription of a take. Writes a list of words.

    python transcribe.py <media> <out.json> [--engine auto|whisper|crisper|scribe] [--lang en]

Output (docs/CONTRACTS.md, Transcription):
    [{"text": "so", "start": 0.12, "end": 0.31, "type": "word"},
     {"text": " ", "start": 0.31, "end": 0.40, "type": "spacing"}, ...]

Engines:
  whisper  faster-whisper, free and local. Needs ~/.ai-video-editor/venv.
           Model from AI_EDITOR_WHISPER_MODEL (default "small").
  crisper  CrisperWhisper 2.0, free and local, verbatim: keeps ums, repeats and false
           starts, which plain Whisper tidies away. `setup.py crisper` installs it
           (about 1 GB). Model from AI_EDITOR_CRISPER_MODEL (default "small"). Its
           weights are licensed for NON-COMMERCIAL use only.
  scribe   ElevenLabs Scribe v2, verbatim. Needs a key in ELEVENLABS_API_KEY or
           ~/.config/creator-teardown/.env. Keeps every filler and false start.
  auto     scribe when a key exists, else crisper when installed, else whisper (default).

Audio is pulled out with ffmpeg first (16 kHz mono WAV), so a multi-GB 4K file
costs one fast audio demux, never a video decode.

Exit codes: 0 ok, 1 error, 2 usage or missing key, 3 HTTP error
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from ai_editor import keys  # noqa: E402

HOME = Path.home() / ".ai-video-editor"
# Whisper tidies speech by default. A prompt full of hesitations makes it keep
# more of them, and the fillers are the evidence the cut acts on.
FILLER_PROMPT = "Umm, uh, so, like, you know, I mean, uh, so, um, wait, sorry, let me start again."


def find_key():
    return keys.get("elevenlabs")[0]


def extract_audio(src, dst):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vn", "-ac", "1",
                        "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])
    if r.returncode:
        sys.exit(f"ERROR: ffmpeg could not read audio from {src}")


def with_spacing(words):
    """Insert spacing tokens for the gaps, so both engines give the same shape."""
    out = []
    for w in words:
        if out and w["start"] - out[-1]["end"] > 0.001:
            out.append({"text": " ", "start": out[-1]["end"], "end": w["start"], "type": "spacing"})
        out.append(w)
    return out


def run_whisper(wav, lang):
    os.environ.setdefault("HF_HOME", str(HOME / "models"))
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("ERROR: faster-whisper missing. Run this with ~/.ai-video-editor/venv/bin/python "
                 "(the setup skill installs it).")
    name = os.environ.get("AI_EDITOR_WHISPER_MODEL", "small")
    print(f"whisper model {name} (cpu, int8)", flush=True)
    model = WhisperModel(name, device="cpu", compute_type="int8",
                         download_root=str(HOME / "models"))
    # condition_on_previous_text=False: with it on, whisper tends to collapse a
    # repeated line into one, and repeated lines are exactly the retakes.
    # vad_filter=True: without it, word times drift after a long silence (a line
    # placed 8 s after where it was said, on a real take), and raw takes are full
    # of long silences.
    segs, _ = model.transcribe(str(wav), language=lang, word_timestamps=True,
                               initial_prompt=FILLER_PROMPT, beam_size=5,
                               condition_on_previous_text=False, vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 500})
    words = []
    for s in segs:
        for w in s.words or []:
            t = w.word.strip()
            if t:
                words.append({"text": t, "start": round(w.start, 3), "end": round(w.end, 3),
                              "type": "word"})
    return with_spacing(words)


def has_crisper():
    import importlib.util
    return importlib.util.find_spec("crisperwhisper") is not None


def run_crisper(wav, lang):
    os.environ.setdefault("HF_HOME", str(HOME / "models"))
    try:
        from crisperwhisper import CrisperWhisperModel
    except ImportError:
        sys.exit("ERROR: CrisperWhisper missing. Install it with the setup skill: setup.py crisper")
    name = os.environ.get("AI_EDITOR_CRISPER_MODEL", "small")
    print(f"crisperwhisper {name} (verbatim; weights licensed for non-commercial use)", flush=True)
    r = CrisperWhisperModel(name).transcribe(str(wav), language=lang, word_timestamps=True)
    words = []
    for w in r.words or []:
        t = w.word.strip()
        if not t:
            continue
        # Verbatim mode writes fillers as [um] and sounds as [laughter].
        inner = t.strip("[]").strip()
        tag = t.startswith("[") and t.endswith("]")
        filler = inner.lower() in ("um", "uh", "umm", "uhh", "hmm", "mm", "er", "erm", "ah")
        words.append({"text": inner if tag and filler else t, "start": round(w.start, 3),
                      "end": round(w.end, 3), "type": "audio_event" if tag and not filler else "word"})
    return with_spacing(words)


def run_scribe(wav, key, lang):
    fields = [("model_id", "scribe_v2"), ("timestamps_granularity", "word"),
              ("tag_audio_events", "true"), ("no_verbatim", "false"), ("diarize", "false"),
              ("temperature", "0"), ("seed", "0")]
    if lang:
        fields.append(("language_code", lang))
    b = "----cut" + os.urandom(12).hex()
    body = bytearray()
    for k, v in fields:
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    body += (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
             f"Content-Type: audio/wav\r\n\r\n").encode() + Path(wav).read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request("https://api.elevenlabs.io/v1/speech-to-text", data=bytes(body),
                                 headers={"xi-api-key": key,
                                          "Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode(errors='replace')[:400]}", file=sys.stderr)
        sys.exit(3)
    return [{"text": w["text"], "start": w["start"], "end": w["end"], "type": w["type"]}
            for w in payload.get("words", []) if w.get("type") in ("word", "spacing", "audio_event")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("out")
    ap.add_argument("--engine", choices=["auto", "whisper", "crisper", "scribe"], default="auto")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args()

    if not Path(a.media).exists():
        sys.exit(f"ERROR: no such file: {a.media}")
    key = find_key()
    engine = a.engine if a.engine != "auto" else (
        "scribe" if key else "crisper" if has_crisper() else "whisper")
    if engine == "scribe" and not key:
        print("ERROR: no ElevenLabs key (ELEVENLABS_API_KEY or ~/.config/creator-teardown/.env)",
              file=sys.stderr)
        sys.exit(2)

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        extract_audio(a.media, wav)
        print(f"engine {engine}", flush=True)
        run = {"whisper": run_whisper, "crisper": run_crisper}.get(engine)
        words = run(wav, a.lang) if run else run_scribe(wav, key, a.lang)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(words, indent=1))
    n = sum(1 for w in words if w["type"] == "word")
    print(f"{n} words -> {out}")


if __name__ == "__main__":
    main()
