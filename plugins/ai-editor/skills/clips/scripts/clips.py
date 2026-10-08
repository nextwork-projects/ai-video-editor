#!/usr/bin/env python3
"""Find the best short clips in a long video. Transcribe once, then code and Jev do the reading.

    python3 clips.py link       <video file> <clips_dir>   the source, linked (never copied when avoidable)
    python3 clips.py candidates <clips_dir> [--min 20 --max 40] [--speakers 1|2] [--style style.json] [--top 8]
    python3 clips.py page       <clips_dir> [--recommend c3,c7]
    python3 clips.py trim       <clips_dir> <cand_id> [<cand_id> ...] [--name NAME] [--edits edits]
    $PY     clips.py reframe    <edit_dir>        (venv python: OpenCV) a wide clip to 9:16 round the speaker
    python3 clips.py demo

<clips_dir> holds source.mp4 (or a symlink to it; a podcast's audio keeps its own extension, source.mp3)
and words.raw.json from the cut skill's transcribe.py. Nothing here reads the whole transcript into a model.

candidates  1. Sentences from the word timings (. ? ! or a 1.2 s silence ends one).
            2. Every run of whole sentences whose length is inside --min/--max is a candidate:
               it starts on a sentence start and ends on a sentence end, so no clip cuts a thought.
            3. Code features per candidate: speech rate, loudness against the whole video (RMS
               from ffmpeg), words in the first 3 s, laughter and other audio events, names and
               numbers said (things style-edit can show as real captures), a start that leans on
               earlier context ("and", "so", "that's why").
            4. Jev, with a TypeSafe key: four yes/no questions a candidate (the hook alone, self
               contained, pays off, a concrete claim / number / story), plus one per "what works"
               move from the creator's style.json. One batched request, a cent or two a video.
            5. Score = 0.7 Jev + 0.3 features (features only with no key), then the top --top
               candidates that do not overlap: shortlist.md (about 1,500 tokens) for Claude.
            Writes candidates.json, shortlist.json, shortlist.md. Exit 4 with no key: the
            shortlist is ranked by features only and Claude judges the four questions itself.
page        picks.html: one self-contained page with every shortlisted clip, its transcript, its
            score breakdown and a low-res preview (base64 mp4, 360 px, cut with ffmpeg).
reframe     A wide source.mp4 cropped to 9:16, the crop following the speaker's head shot by shot
            (camera cuts snapped to ffmpeg's scene changes). Before the cut, so every later step
            sees a vertical take. The wide file stays as source-wide.mp4.
link        <clips_dir>/source.mp4: a hard link on the same drive (no admin needed, NTFS too), else a
            symlink, else a copy as the last resort. Nothing here writes to source.mp4 in place.
trim        For each chosen id, edits/<name>-clip<N>/source.mp4 (frame-accurate re-encode) and
            words.raw.json re-timed to it, so the cut skill starts at retakes.py with no second
            transcription. An audio source's clip is the audio over the podcast's cover (cover.<ext> from
            links.py, else the file's embedded art, else black), 1080x1920; clip.json says audio_only.

Exit codes: 0 ok, 1 error, 2 usage, 4 no TypeSafe key (features-only ranking)
"""
import argparse
import array
import base64
import html
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "lib"))
from ai_editor import jev, keys  # noqa: E402
from ai_editor.links import AUDIO_EXT  # noqa: E402

SOURCES = [f"source{e}" for e in (".mp4", ".mov", ".mkv", ".webm", ".m4v") + AUDIO_EXT]
COVERS = ("cover.jpg", "cover.jpeg", "cover.png", "cover.webp")
GROUND_W, GROUND_H, COVER_PX, COVER_Y = 1080, 1920, 720, 200   # an audio clip: the cover above the captions


def source(d):
    """The long source in a clips folder: a video, or a podcast's audio (links.py names both source.<ext>)."""
    return next((Path(d) / n for n in SOURCES if (Path(d) / n).exists()), None)


def is_audio(src):
    return bool(src) and Path(src).suffix.lower() in AUDIO_EXT


def cover_of(d, src=None):
    """The podcast's own artwork: links.py's cover.<ext>, else the picture embedded in the audio file
    (extracted once to cover.jpg), else None (a plain black ground)."""
    found = next((Path(d) / n for n in COVERS if (Path(d) / n).exists()), None)
    if found or not src:
        return found
    out = Path(d) / "cover.jpg"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an", "-frames:v", "1", str(out)],
                       capture_output=True)
    return out if r.returncode == 0 and out.exists() and out.stat().st_size else None


def ground_cmd(src, a, b, cover, out, fps=30):
    """ffmpeg: a vertical video of the audio from a to b over the cover (a blurred copy dimmed to 30%
    fills the frame, so white captions read on it; the sharp cover sits above where captions go). No cover: black. No invented graphics."""
    dur = f"{b - a:.3f}"
    if cover:
        pic = ["-loop", "1", "-framerate", str(fps), "-i", str(cover)]
        vf = (f"[0:v]scale={GROUND_W}:{GROUND_H}:force_original_aspect_ratio=increase,crop={GROUND_W}:{GROUND_H},"
              f"boxblur=40:2,colorchannelmixer=rr=0.3:gg=0.3:bb=0.3[bg];[0:v]scale={COVER_PX}:{COVER_PX}:force_original_aspect_ratio="
              f"decrease[fg];[bg][fg]overlay=(W-w)/2:{COVER_Y},format=yuv420p[v]")
    else:
        pic = ["-f", "lavfi", "-i", f"color=c=black:s={GROUND_W}x{GROUND_H}:r={fps}"]
        vf = "[0:v]format=yuv420p[v]"
    return ["ffmpeg", "-v", "error", "-y", *pic, "-ss", f"{a:.3f}", "-t", dur, "-i", str(src),
            "-filter_complex", vf, "-map", "[v]", "-map", "1:a", "-t", dur, "-c:v", "libx264", "-tune", "stillimage",
            "-crf", "18", "-preset", "fast", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]

SENT_GAP_S = 1.2          # a silence this long ends a sentence when punctuation is missing
HOOK_S = 3.0
PAD_IN, PAD_OUT = 0.12, 0.35
RMS_HZ, RMS_WIN = 2000, 0.25
CONNECTIVE = re.compile(r"^(and|but|so|because|which|that's why|that is why|also|then|or|"
                        r"this is why|like i said|as i said|anyway)\b", re.I)
NUMBER = re.compile(r"\d|\b(hundred|thousand|million|billion|percent|half|double|twice|"
                    r"ten|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\b", re.I)
# Ad reads and sign-offs: never a clip on their own, and a clip that runs into one is cut short.
PROMO = re.compile(r"\b(sponsor(?:ed)?|link in the description|use (?:my )?code|promo code|check (?:them|it) out|"
                   r"subscribe|that's all i have|see you (?:in the )?next|thanks for watching|today's video is)\b", re.I)
SKIP_CAPS = {"I", "I'm", "I've", "I'll", "I'd", "AM", "PM", "OK", "Okay", "Yeah", "Oh", "Mm-hmm", "Uh", "Um"}
W_JEV = {"hook": 0.35, "self": 0.25, "payoff": 0.25, "concrete": 0.15}
W_WHAT_WORKS = 0.15       # share of the Jev score the creator's moves get, when there are any

STATE = ("Excerpts from the transcript of one long video (a talk, tutorial or podcast) that is "
         "being cut into short vertical clips for TikTok, Reels and Shorts. A viewer of a clip "
         "has seen nothing else of the video. Transcription can misspell names.")


# --- transcript ------------------------------------------------------------------

def load_words(path):
    d = json.loads(Path(path).read_text())
    toks = d["words"] if isinstance(d, dict) else d
    return [t for t in toks if t.get("type") in ("word", "audio_event")]


def sentences(toks):
    """[{a, b, start, end, text}] over word tokens (audio events ride along inside)."""
    out, a = [], 0
    for i in range(1, len(toks) + 1):
        end = i == len(toks) or toks[i - 1]["text"].strip().endswith((".", "?", "!")) \
            or toks[i]["start"] - toks[i - 1]["end"] >= SENT_GAP_S
        if end:
            words = [t for t in toks[a:i] if t["type"] == "word"]
            if words:
                out.append({"a": a, "b": i - 1, "start": words[0]["start"], "end": words[-1]["end"],
                            "text": " ".join(t["text"].strip() for t in words)})
            a = i
    return out


def opens(s):
    """Can a clip start here? Not on a backchannel ("Mm-hmm.", "Yeah.") or a two-word fragment."""
    return len(s["text"].split()) >= 4


def closes(s):
    """Can a clip end here? On a finished sentence, not one cut off ("and it would know- ...")."""
    t = s["text"].rstrip()
    return t.endswith((".", "?", "!")) and not t.endswith(("...", "-", "..")) and len(t.split()) >= 3


def windows(sents, lo, hi):
    """Every run of whole sentences lasting lo..hi seconds: (first, last) sentence index."""
    out = []
    for i, s in enumerate(sents):
        if not opens(s):
            continue
        for j in range(i, len(sents)):
            d = sents[j]["end"] - s["start"]
            if d > hi:
                break
            if d >= lo and closes(sents[j]):
                out.append((i, j))
    return out


# --- audio ------------------------------------------------------------------------

def rms_track(media):
    """Loudness in dB per RMS_WIN seconds, from a 2 kHz mono decode (stdlib, ~2 MB a 15 min video)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(media), "-vn", "-ac", "1", "-ar", str(RMS_HZ),
                        "-f", "s16le", "-"], capture_output=True)
    if r.returncode:
        return []
    pcm = array.array("h", r.stdout)
    n = int(RMS_HZ * RMS_WIN)
    out = []
    for k in range(0, len(pcm) - n + 1, n):
        ms = sum(x * x for x in pcm[k:k + n]) / n
        out.append(10 * math.log10(ms + 1e-9))
    return out


def energy_db(track, start, end):
    """Mean loudness of the speech in start..end minus the video's median: + is livelier."""
    if not track:
        return 0.0
    med = statistics.median(track)
    seg = track[int(start / RMS_WIN):max(int(start / RMS_WIN) + 1, int(end / RMS_WIN))]
    loud = [x for x in seg if x > med - 15] or seg   # speech only: pauses would drag it down
    return round(statistics.mean(loud) - med, 2) if loud else 0.0


# --- candidates ------------------------------------------------------------------------

def name_list(profile_names):
    return [n["name"] if isinstance(n, dict) else str(n) for n in profile_names or []]


def names_said(words, starts, names):
    """The profile's names said, plus runs of capitalised words ("Claude Code") that do not start a
    sentence (ids in `starts`, or after . ? !), are not single letters, and are never said in lower
    case in the same words ("And" next to "and"). Whisper's "-for" tokens join the word before."""
    joined = []
    for t in words:
        x = t["text"].strip()
        if x.startswith("-") and joined:
            joined[-1] = (joined[-1][0] + x, joined[-1][1])
        else:
            joined.append((x, id(t) in starts))
    lower = {x.lower().strip(".,?!") for x, _ in joined if x[:1].islower()}
    text = " ".join(x for x, _ in joined)
    caps, run = set(), []
    for k, (x, start) in enumerate(joined + [(".", True)]):
        w = re.sub(r"[^\w.'-]", "", x).strip(".")
        if (k and not start and len(w) > 1 and w[:1].isupper() and w not in SKIP_CAPS
                and w.lower() not in lower and joined[k - 1][0][-1:].isalnum()):
            run.append(w)
            continue
        if run:
            caps.add(" ".join(run))
        run = []
    return sorted({n for n in names if re.search(rf"\b{re.escape(n)}\b", text, re.I)} | caps)


def features(toks, sents, i, j, track, names):
    s0, s1 = sents[i], sents[j]
    seg = toks[s0["a"]:s1["b"] + 1]
    words = [t for t in seg if t["type"] == "word"]
    dur = s1["end"] - s0["start"]
    text = " ".join(t["text"].strip() for t in words)
    events = [t["text"].strip("()[] ").lower() for t in seg if t["type"] == "audio_event"]
    firsts = {id(next(t for t in toks[s["a"]:s["b"] + 1] if t["type"] == "word")) for s in sents[i:j + 1]}
    named = names_said(words, firsts, names)
    return {
        "start": s0["start"], "end": s1["end"], "dur": round(dur, 1),
        "wpm": round(len(words) / dur * 60) if dur else 0,
        "energy_db": energy_db(track, s0["start"], s1["end"]),
        "hook_words_3s": sum(1 for t in words if t["start"] < s0["start"] + HOOK_S),
        "laughs": sum(1 for e in events if "laugh" in e),
        "events": len(events),
        "named": named[:8],
        "numbers": len(NUMBER.findall(text)),
        "leans_back": bool(CONNECTIVE.match(s0["text"])),
        "promo": len(PROMO.findall(text)),
        "sentences": j - i + 1,
        "hook": s0["text"], "text": text, "last": s1["text"],
        "middle": " / ".join(" ".join(s["text"].split()[:7]) + "..." for s in sents[i + 1:j]),
    }


def feature_score(f, med_wpm):
    """0..1 from code features only: livelier, faster, a hook that gets words out, concrete, named."""
    x = (0.25 * max(-2, min(2, f["energy_db"] / 3))
         + 0.15 * max(-2, min(2, (f["wpm"] - med_wpm) / 30))
         + 0.3 * (1 if f["hook_words_3s"] >= 6 else 0 if f["hook_words_3s"] >= 3 else -1)
         + 0.25 * min(2, f["numbers"]) + 0.2 * min(3, len(f["named"])) / 1.5
         + 0.3 * min(1, f["laughs"])
         - 1.0 * f["leans_back"] - 1.5 * min(1, f.get("promo", 0)))
    return round(1 / (1 + math.exp(-x)), 3)


def what_works(style):
    """The creator's measured moves as short strings: style.json's `what_works`, any shape
    (a list, or a dict of lists or strings). At most 4, so the Jev bill stays flat."""
    ww = (style or {}).get("what_works")
    out = []

    def walk(v):
        if isinstance(v, str) and 8 <= len(v) <= 200:
            out.append(v)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for k in ("levers", "hooks", "hook", "moves"):
                if k in v:
                    walk(v[k])
            for k, x in v.items():
                if k not in ("levers", "hooks", "hook", "moves", "source", "videos", "evidence"):
                    walk(x)
    walk(ww)
    return list(dict.fromkeys(out))[:4]


def questions(c, moves):
    cid, clip = c["id"], c["text"]
    qs = {
        f"{cid}_self": jev.noul(
            "Can someone who has seen nothing else of the video follow `clip` on its own?",
            true="Yes: it sets up what it is about and ends on a finished thought.",
            false="No: it leans on something said earlier (an unexplained 'this', 'he', 'as I said') "
                  "or stops mid-thought.", clip=clip),
        f"{cid}_payoff": jev.noul(
            "Does `clip` pay off what its first sentence sets up (an answer, a result, a lesson or a "
            "punchline) before it ends?", clip=clip),
        f"{cid}_concrete": jev.noul(
            "Does `clip` contain a concrete claim, a number, a named example or a short story, rather "
            "than only general talk?", clip=clip),
    }
    for k, m in enumerate(moves):
        qs[f"{cid}_ww{k}"] = jev.noul("Does `clip` do this: `move`?", clip=clip, move=m)
    return qs


def hook_question(text):
    return jev.noul(
        "Heard alone in the first 3 seconds of a short video, with no context, would `first_sentence` "
        "make a viewer want to keep watching?",
        true="Yes: it opens a question, makes a bold or surprising claim, or names a problem the viewer has.",
        false="No: it is a greeting, a transition, or needs earlier context to mean anything.",
        first_sentence=text)


def candidates(d, lo=20, hi=40, speakers=1, style=None, top=8, key=None, canned=None, names=None):
    d = Path(d)
    toks = load_words(d / "words.raw.json")
    sents = sentences(toks)
    src = source(d)
    track = rms_track(src) if src else []
    cands = []
    for i, j in windows(sents, lo, hi):
        f = features(toks, sents, i, j, track, names or [])
        cands.append({"id": f"c{len(cands)}", "first": i, **f})
    if not cands:
        sys.exit(f"ERROR: no run of whole sentences lasts {lo}-{hi} s. Try a wider length.")
    med_wpm = statistics.median(c["wpm"] for c in cands)
    for c in cands:
        c["features_score"] = feature_score(c, med_wpm)

    moves = what_works(style)
    qs, hook_ids = {}, {}
    for c in cands:
        hid = hook_ids.setdefault(c["first"], f"h{c['first']}")
        qs[hid] = hook_question(c["hook"])
        qs.update(questions(c, moves))
    state = STATE + (" Two people talk in it: a host and a guest." if speakers == 2 else "")
    est_tokens = round((len(json.dumps(qs)) + len(state)) / 4)
    code = 0
    try:
        if key is None and canned is None:
            raise jev.JevError("no TypeSafe key")
        ans = jev.ask(state, qs, key=key, log_dir=d, canned=canned)
        usage = jev.ask.last_usage
    except jev.JevError as e:
        print(f"{e}: ranking on code features only.", file=sys.stderr)
        ans, usage, code = {}, None, 4
    for c in cands:
        a = {"hook": ans.get(f"h{c['first']}")} | {k: ans.get(f"{c['id']}_{k}") for k in ("self", "payoff", "concrete")}
        if all(a.values()):
            c["jev"] = {k: round(jev.yes(v), 3) for k, v in a.items()}
            ww = [jev.yes(ans[f"{c['id']}_ww{k}"]) for k in range(len(moves)) if f"{c['id']}_ww{k}" in ans]
            j_score = sum(W_JEV[k] * c["jev"][k] for k in W_JEV)
            if ww:
                c["jev"]["what_works"] = round(sum(ww) / len(ww), 3)
                j_score = (1 - W_WHAT_WORKS) * j_score + W_WHAT_WORKS * c["jev"]["what_works"]
            c["score"] = round(0.7 * j_score + 0.3 * c["features_score"], 3)
        else:
            c["jev"], c["score"] = None, c["features_score"]
    short = shortlist(cands, top)
    (d / "candidates.json").write_text(json.dumps(cands, indent=1))
    (d / "shortlist.json").write_text(json.dumps(short, indent=1))
    (d / "shortlist.md").write_text(shortlist_md(short, moves, jev_used=code == 0))
    cost = usage["cost_usd"] if usage else round(est_tokens * jev.USD_PER_MTOK / 1e6, 4)
    print(f"{len(sents)} sentences, {len(cands)} candidates {lo}-{hi} s, {len(qs)} Jev questions "
          f"({'$%.4f' % cost if usage else 'about %d tokens, $%.4f with a key' % (est_tokens, cost)}); "
          f"shortlist {len(short)} -> {d / 'shortlist.md'} ({(d / 'shortlist.md').stat().st_size} bytes)")
    return code


def shortlist(cands, top):
    """The best `top` candidates, highest score first, no two sharing a second of video."""
    out = []
    for c in sorted(cands, key=lambda c: -c["score"]):
        if all(c["end"] <= o["start"] or c["start"] >= o["end"] for o in out):
            out.append(c)
        if len(out) == top:
            break
    return out


def clip_text(c, n=60):
    w = c["text"].split()
    return c["text"] if len(w) <= 2 * n else " ".join(w[:n]) + " [...] " + " ".join(w[-n // 2:])


def shortlist_md(short, moves, jev_used):
    lines = [f"# Shortlist: {len(short)} clips, best first",
             "" if jev_used else "No Jev answers: judge each one yourself on hook alone, self-contained, "
                                 "pays off, concrete (claim, number, story). The features are measured.",
             f"Creator's moves scored: {'; '.join(moves)}" if moves else "", ""]
    for c in short:
        j = c["jev"]
        js = " ".join(f"{k} {v:.2f}" for k, v in j.items()) if j else "no Jev"
        lines += [f"## {c['id']}  {mmss(c['start'])}-{mmss(c['end'])}  {c['dur']} s  score {c['score']:.2f}",
                  f"Jev: {js}. Features {c['features_score']:.2f}: {c['wpm']} wpm, {c['energy_db']:+.1f} dB, "
                  f"{c['hook_words_3s']} words in 3 s, {c['numbers']} numbers, laughs {c['laughs']}"
                  f"{', starts on a connective' if c['leans_back'] else ''}"
                  f"{', ad read or sign-off' if c['promo'] else ''}"
                  f"{', names: ' + ', '.join(c['named']) if c['named'] else ''}",
                  f"Hook: \"{c['hook']}\"", f"Then: {c['middle']}" if c["middle"] else "",
                  f"Ends: \"{c['last']}\"", ""]
    return "\n".join(x for x in lines if x is not None) + "\n"


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


# --- page --------------------------------------------------------------------------------

def preview(src, start, end, out):
    vid = ["-vn"] if is_audio(src) else ["-vf", "scale=-2:360", "-c:v", "libx264", "-preset", "veryfast", "-crf", "33"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, start - PAD_IN):.3f}", "-i", str(src),
                    "-t", f"{end - start + PAD_IN + PAD_OUT:.3f}", *vid, "-c:a", "aac", "-b:a", "48k", "-ac", "1",
                    "-movflags", "+faststart", str(out)], check=True)


CSS = """
:root{--bg:#fafaf9;--card:#fff;--ink:#1c1917;--mute:#78716c;--line:#e7e5e4;--bar:#1c1917;--pick:#0f766e}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0c0a09;--card:#1c1917;--ink:#f5f5f4;--mute:#a8a29e;--line:#292524;--bar:#f5f5f4;--pick:#2dd4bf}}
:root[data-theme=dark]{--bg:#0c0a09;--card:#1c1917;--ink:#f5f5f4;--mute:#a8a29e;--line:#292524;--bar:#f5f5f4;--pick:#2dd4bf}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 20px}
.c{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:0 0 16px;display:grid;grid-template-columns:280px 1fr;gap:16px}
.c.rec{border-color:var(--pick);border-width:2px}video{width:100%;border-radius:6px;background:#000}
.h{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap;margin:0 0 6px}.id{font-weight:700;font-size:18px}.m{color:var(--mute);font-size:13px}
.tag{color:var(--pick);font-weight:600;font-size:13px}.t{font-size:14px;margin:8px 0 0}.t b{background:color-mix(in srgb,var(--pick) 18%,transparent)}
table{border-collapse:collapse;font-size:13px;width:100%}td{padding:2px 6px 2px 0;white-space:nowrap}td.b{width:100%}
.bar{height:6px;background:var(--line);border-radius:3px}.bar i{display:block;height:6px;border-radius:3px;background:var(--bar)}
@media (max-width:640px){.c{grid-template-columns:1fr}}
"""


def page(d, recommend=()):
    d = Path(d)
    short = json.loads((d / "shortlist.json").read_text())
    src = source(d)
    rec = list(recommend)
    order = [c for r in rec for c in short if c["id"] == r] + [c for c in short if c["id"] not in rec]
    cards = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in order:
            vid = ""
            if src:
                mp4 = Path(tmp) / f"{c['id']}.mp4"
                preview(src, c["start"], c["end"], mp4)
                tag = "audio" if is_audio(src) else "video"
                vid = (f'<{tag} controls preload="auto" src="data:{tag}/mp4;base64,'
                       f'{base64.b64encode(mp4.read_bytes()).decode()}"></{tag}>')
            rows = [("score", c["score"]), ("features", c["features_score"])] + list((c["jev"] or {}).items())
            table = "".join(f'<tr><td>{html.escape(k.replace("_", " "))}</td><td>{v:.2f}</td>'
                            f'<td class="b"><div class="bar"><i style="width:{v * 100:.0f}%"></i></div></td></tr>'
                            for k, v in rows)
            facts = (f"{c['wpm']} wpm, {c['energy_db']:+.1f} dB vs the video, {c['hook_words_3s']} words in the "
                     f"first 3 s, {c['numbers']} numbers" + (f", names: {', '.join(c['named'])}" if c["named"] else ""))
            body = html.escape(c["text"])
            hook = html.escape(c["hook"])
            body = body.replace(hook, f"<b>{hook}</b>", 1)
            tag = f'<span class="tag">Recommended #{rec.index(c["id"]) + 1}</span>' if c["id"] in rec else ""
            cards.append(f'<section class="c{" rec" if c["id"] in rec else ""}"><div>{vid}</div><div>'
                         f'<div class="h"><span class="id">{c["id"]}</span><span class="m">{mmss(c["start"])}-'
                         f'{mmss(c["end"])} &middot; {c["dur"]} s</span>{tag}</div><table>{table}</table>'
                         f'<p class="m">{html.escape(facts)}</p><p class="t">{body}</p></div></section>')
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
           f'content="width=device-width,initial-scale=1"><title>Clip picks</title><style>{CSS}</style></head>'
           f'<body><main><h1>Clip picks: {html.escape(d.name)}</h1><p class="sub">{len(order)} clips, best first. '
           f'The bold line is the hook. Pick in the question box in Claude Code.</p>{"".join(cards)}</main></body></html>')
    out = d / "picks.html"
    out.write_text(doc)
    print(f"{out} ({out.stat().st_size // 1024} KB)")
    return out


# --- trim --------------------------------------------------------------------------------

def trim(d, ids, name=None, edits="edits"):
    d = Path(d)
    cands = {c["id"]: c for c in json.loads((d / "candidates.json").read_text())}
    raw = json.loads((d / "words.raw.json").read_text())
    raw = raw["words"] if isinstance(raw, dict) else raw
    src = source(d)
    audio = is_audio(src)
    cover = cover_of(d, src) if audio else None
    name, outs = name or d.name, []
    for n, cid in enumerate(ids, 1):
        if cid not in cands:
            sys.exit(f"ERROR: no candidate {cid} in {d / 'candidates.json'}")
        c = cands[cid]
        # Pad round the clip, but never into the word before or after it.
        prev = max((t["end"] for t in raw if t["type"] == "word" and t["end"] <= c["start"]), default=0.0)
        nxt = min((t["start"] for t in raw if t["type"] == "word" and t["start"] >= c["end"]), default=1e9)
        a = max(0.0, c["start"] - PAD_IN, min(c["start"], prev + 0.03))
        b = min(c["end"] + PAD_OUT, max(c["end"], nxt - 0.03))
        e = Path(edits) / f"{name}-clip{n}"
        e.mkdir(parents=True, exist_ok=True)
        words = [{**t, "start": round(max(0.0, t["start"] - a), 3), "end": round(min(b, t["end"]) - a, 3)}
                 for t in raw if t["end"] > a and t["start"] < b]
        while words and words[0]["type"] == "spacing":
            words.pop(0)
        while words and words[-1]["type"] == "spacing":
            words.pop()
        (e / "words.raw.json").write_text(json.dumps(words, indent=1))
        meta = {"from": str(d.resolve()), "id": cid, "start": a, "end": b, "hook": c["hook"]}
        if audio:   # no picture: the podcast's cover is the ground, the speaker's words the only text
            meta |= {"audio_only": True, "cover": str(cover.resolve()) if cover else None, "captions": True}
        (e / "clip.json").write_text(json.dumps(meta, indent=1))
        if audio:
            subprocess.run(ground_cmd(src, a, b, cover, e / "source.mp4"), check=True)
        elif src:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-i", str(src), "-t", f"{b - a:.3f}",
                            "-c:v", "libx264", "-crf", "16", "-preset", "fast", "-c:a", "aac", "-b:a", "192k",
                            "-movflags", "+faststart", str(e / "source.mp4")], check=True)
        outs.append(e)
        print(f"{cid} -> {e} ({b - a:.1f} s{', audio over ' + (cover.name if cover else 'black') if audio else ''})")
    return outs


# --- reframe -----------------------------------------------------------------------------

def shots_x(heads, jump=12.0):
    """[(start_t, head centre x %)] per camera shot. A new shot starts when the head's centre moves
    more than `jump` % of the width and stays there for two samples (one stray detection is noise)."""
    out = []
    pts = [(h["t"], h["box"][0] + h["box"][2] / 2) for h in heads if h.get("box")]
    k = 0
    while k < len(pts):
        t, x = pts[k]
        if not out:
            out.append([0.0, [x]])
        elif abs(x - statistics.median(out[-1][1])) > jump and k + 1 < len(pts) \
                and abs(pts[k + 1][1] - x) <= jump:
            out.append([t, [x]])
        else:
            out[-1][1].append(x)
        k += 1
    return [(t, round(statistics.median(xs), 2)) for t, xs in out]


def scene_cuts(video):
    """Hard cuts in the video, seconds (ffmpeg's scene score)."""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", str(video), "-vf", "scale=320:-2,select='gt(scene,0.3)',showinfo",
                        "-an", "-f", "null", "-"], capture_output=True, text=True)
    return [float(m) for m in re.findall(r"pts_time:([\d.]+)", r.stderr)]


def snap(shots, cuts, step=0.5):
    """Move each shot start back onto the real cut just before it (the head scan samples every 0.5 s)."""
    out = []
    for t, x in shots:
        near = [c for c in cuts if t - step - 0.05 <= c <= t + step / 2]   # the fps sampler rounds
        out.append((max(near) if near and t else t, x))
    return out


def crop_x_expr(shots, src_w, crop_w):
    """ffmpeg crop x for each shot: the head centred, clamped inside the frame."""
    px = [min(src_w - crop_w, max(0, round(x / 100 * src_w - crop_w / 2))) for _, x in shots]
    expr = str(px[-1])
    for k in range(len(shots) - 2, -1, -1):
        expr = f"if(lt(t,{shots[k + 1][0]:.3f}),{px[k]},{expr})"
    return expr


def reframe(edit_dir):
    """Crop a wide source.mp4 to 9:16 round the speaker, shot by shot. Keeps source-wide.mp4."""
    sys.path.insert(0, str(HERE.parents[1] / "style-edit" / "scripts"))
    import face  # noqa: E402  (OpenCV: run with the venv python)
    e = Path(edit_dir)
    src = e / "source.mp4"
    w, h = map(int, subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height", "-of", "csv=p=0", str(src)],
                                   capture_output=True, text=True, check=True).stdout.strip().split(","))
    crop_w = round(h * 9 / 16 / 2) * 2
    if crop_w >= w:
        print(f"{src} is already {w}x{h}: nothing to reframe")
        return
    shots = snap(shots_x(face.scan(src)), scene_cuts(src))
    if not shots:
        shots = [(0.0, 50.0)]
    wide, tmp = e / "source-wide.mp4", e / ".reframe.mp4"
    vf = f"crop=w={crop_w}:h={h}:x='{crop_x_expr(shots, w, crop_w)}':y=0"   # quotes keep the commas
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-crf", "16",
                    "-preset", "fast", "-c:a", "copy", "-movflags", "+faststart", str(tmp)], check=True)
    src.replace(wide)
    tmp.replace(src)
    (e / "reframe.json").write_text(json.dumps({"shots": shots, "crop_w": crop_w, "from": [w, h]}, indent=1))
    print(f"{src}: {crop_w}x{h}, {len(shots)} shot(s), crop follows the head (wide original: {wide.name})")


def link_source(video, clips_dir, link=os.link, symlink=os.symlink):
    """<clips_dir>/source.mp4 pointing at the user's file: hard link, else symlink, else copy.
    Returns (path, how). Windows makes symlinks only with Developer Mode or admin, and a multi-GB copy
    fills the disk, so the hard link comes first; it fails only across drives."""
    src = Path(video).resolve()
    if not src.is_file():
        sys.exit(f"ERROR: no such file: {video}")
    d = Path(clips_dir)
    d.mkdir(parents=True, exist_ok=True)
    # every step names it so; ffmpeg reads the container, not the extension. Audio keeps its own, so trim
    # knows to give it a picture.
    dst = d / ("source" + (src.suffix.lower() if is_audio(src) else ".mp4"))
    if dst.exists() or dst.is_symlink():
        if dst.exists() and os.path.samefile(dst, src):
            return dst, "already there"
        sys.exit(f"ERROR: {dst} already exists and is another file; pick another clips folder")
    for how, make in (("hard link", link), ("symlink", symlink)):
        try:
            make(src, dst)
            return dst, how
        except (OSError, NotImplementedError):
            pass
    shutil.copy2(src, dst)
    return dst, "copy"


# --- demo ---------------------------------------------------------------------------------

def demo():
    """Offline: a synthetic 4-minute transcript, canned Jev answers, every invariant asserted."""
    filler = "and we talked about a few things that came up over the week in general terms."
    plan = []
    for k in range(24):
        plan.append(filler)
        if k == 9:   # the planted clip: a strong hook, a number, a story, a payoff
            plan += ["Why does every team that adopts AI agents ship slower in the first month?",
                     "We measured it at Acme across 40 engineers for six weeks.",
                     "Pull requests got 3 times bigger and review time doubled.",
                     "The fix was one rule: an agent may only open a pull request under 200 lines.",
                     "After that rule our cycle time fell by half in two weeks."]
    toks, t = [], 0.0
    for s in plan:
        for w in s.split():
            toks.append({"text": w, "start": round(t, 3), "end": round(t + 0.32, 3), "type": "word"})
            t += 0.4
        toks.append({"text": " ", "start": round(t - 0.08, 3), "end": round(t + 0.5, 3), "type": "spacing"})
        t += 0.6
    toks.insert(5, {"text": "(laughter)", "start": 2.0, "end": 2.3, "type": "audio_event"})
    style = {"what_works": {"levers": ["opens with a question the viewer has", "names a real company"]}}
    assert what_works(style) == style["what_works"]["levers"]
    assert what_works({"what_works": ["x"]}) == [] and what_works({}) == []
    # names: no sentence starts (a gap ends a sentence with no full stop), no single letters, real names kept
    ws_ = [{"text": x} for x in "we tried it at Acme and it worked So we told Claude Code about T".split()]
    got = names_said(ws_, {id(ws_[0]), id(ws_[8])}, ["Jev"])
    assert got == ["Acme", "Claude Code"], got
    assert names_said([{"text": "Ask"}, {"text": "Jev"}], set(), ["Jev"]) == ["Jev"]
    assert PROMO.search("Today's video is sponsored by Acme") and not PROMO.search("the subscription price")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "talk"
        d.mkdir()
        (d / "words.raw.json").write_text(json.dumps(toks))
        sents = sentences(load_words(d / "words.raw.json"))
        assert len(sents) == len(plan), (len(sents), len(plan))
        assert not opens({"text": "Mm-hmm."}) and not closes({"text": "and it would know- ..."})
        good = next(i for i, s in enumerate(sents) if s["text"].startswith("Why does"))

        # canned Jev: the planted run scores high, everything else low
        ws = windows(sents, 15, 40)
        hi, lo = {"type": "noul", "noul": 0.92}, {"type": "noul", "noul": 0.15}
        canned = {}
        for n, (i, j) in enumerate(ws):
            planted = i == good and j >= good + 4
            canned[f"h{i}"] = hi if i == good else lo
            for k in ("self", "payoff", "concrete", "ww0", "ww1"):
                canned[f"c{n}_{k}"] = hi if planted else lo
        code = candidates(d, lo=15, hi=40, style=style, canned=canned, names=["Acme"])
        assert code == 0
        cands = json.loads((d / "candidates.json").read_text())
        starts = {s["start"] for s in sents}
        ends = {s["end"] for s in sents}
        for c in cands:   # no clip starts or ends mid-thought, and every length is in range
            assert c["start"] in starts and c["end"] in ends and 15 <= c["dur"] <= 40, c
        short = json.loads((d / "shortlist.json").read_text())
        assert short[0]["hook"].startswith("Why does") and "Acme" in short[0]["named"], short[0]
        assert short[0]["jev"]["what_works"] > 0.9 and short[0]["numbers"] >= 3
        for x in short:
            for y in short:
                assert x is y or x["end"] <= y["start"] or x["start"] >= y["end"], "shortlist overlaps"
        md = (d / "shortlist.md").read_text()
        assert len(md) < 8000 and short[0]["id"] in md and chr(0x2014) not in md
        filler_starts = [c for c in cands if c["leans_back"]]
        assert filler_starts and all(c["features_score"] < short[0]["features_score"] for c in filler_starts)
        assert json.loads(Path(d / "jev-usage.jsonl").read_text().splitlines()[-1])["cost_usd"] == 0

        # no key: features only, exit 4, same files
        assert candidates(d, lo=15, hi=40, style=style, names=["Acme"]) == 4
        assert json.loads((d / "shortlist.json").read_text())[0]["jev"] is None

        # page without media still renders, recommended first
        candidates(d, lo=15, hi=40, style=style, canned=canned, names=["Acme"])
        rec = short[0]["id"]
        p = page(d, [rec]).read_text()
        assert "Recommended #1" in p and p.index(f">{rec}<") < p.index(f'>{short[1]["id"]}<') and "<video" not in p

        # trim: words re-timed to the clip, first word near 0, nothing past the end
        e = trim(d, [rec], edits=Path(tmp) / "edits")[0]
        w = json.loads((e / "words.raw.json").read_text())
        words = [x for x in w if x["type"] == "word"]
        assert words[0]["text"] == "Why" and abs(words[0]["start"] - PAD_IN) < 1e-6
        assert words[-1]["end"] <= short[0]["end"] - short[0]["start"] + PAD_IN + PAD_OUT + 1e-6
        assert words[-1]["text"] == short[0]["last"].split()[-1], words[-1]
        assert e.name == "talk-clip1"

    # reframe: two camera angles, one stray detection ignored, crop clamped inside the frame
    heads = [{"t": k * 0.5, "box": [55, 10, 10, 40]} for k in range(6)] + [{"t": 3.0, "box": [5, 10, 10, 40]}] \
        + [{"t": 3.5 + k * 0.5, "box": [55, 10, 10, 40]} for k in range(3)] \
        + [{"t": 5.0 + k * 0.5, "box": [20, 10, 10, 40]} for k in range(4)] + [{"t": 7.0, "box": None}]
    shots = shots_x(heads)
    assert shots == [(0.0, 60.0), (5.0, 25.0)], shots
    assert snap(shots, [4.62, 9.0]) == [(0.0, 60.0), (4.62, 25.0)] and snap(shots, [5.1]) == [(0.0, 60.0), (5.1, 25.0)]
    assert crop_x_expr([(0.0, 60.0), (4.62, 25.0)], 1920, 608) == "if(lt(t,4.620),848,176)"
    assert crop_x_expr([(0.0, 99.0)], 1920, 608) == "1312"
    # link: hard link first, then symlink, then copy; never a copy when a link works
    with tempfile.TemporaryDirectory() as td:
        v = Path(td) / "Talk.MOV"
        v.write_bytes(b"video")
        dst, how = link_source(v, Path(td) / "a")
        assert how == "hard link" and dst.name == "source.mp4" and os.path.samefile(dst, v), (dst, how)
        assert link_source(v, Path(td) / "a")[1] == "already there"
        def no(*_):
            raise OSError("cross-device link")
        dst, how = link_source(v, Path(td) / "b", link=no)
        assert how == "symlink" and dst.is_symlink() and dst.read_bytes() == b"video", how
        dst, how = link_source(v, Path(td) / "c", link=no, symlink=no)
        assert how == "copy" and not dst.is_symlink() and dst.read_bytes() == b"video", how
    # an audio-only podcast: found like a video, and each clip is its audio over the podcast's own cover
    with tempfile.TemporaryDirectory() as td:
        d, mp3 = Path(td) / "pod", Path(td) / "Episode.MP3"
        ff = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi"]
        subprocess.run(ff + ["-i", "sine=f=220:d=6", str(mp3)], check=True)
        dst, _ = link_source(mp3, d)
        assert dst.name == "source.mp3" and source(d) == dst and is_audio(dst), dst
        subprocess.run(ff + ["-i", "color=c=0x3a6ea5:s=600x600", "-frames:v", "1", str(d / "cover.png")], check=True)
        ws = [{"text": t, "start": 0.5 + k * 0.5, "end": 0.9 + k * 0.5, "type": "word"}
              for k, t in enumerate("why does this work so well.".split())]
        (d / "words.raw.json").write_text(json.dumps(ws))
        (d / "candidates.json").write_text(json.dumps([{"id": "c0", "start": 0.5, "end": 3.4, "hook": "why does this"}]))
        for has_cover in (True, False):
            if not has_cover:
                (d / "cover.png").unlink()   # a sine has no embedded art: a black ground, never an invented one
            e = trim(d, ["c0"], edits=Path(td) / "edits")[0]
            meta = json.loads((e / "clip.json").read_text())
            assert meta["audio_only"] and meta["captions"] is True, meta
            assert (meta["cover"] or "").endswith("cover.png") == has_cover, meta
            got = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of",
                                  "json", str(e / "source.mp4")], capture_output=True, text=True, check=True).stdout
            kinds = {x["codec_type"]: x for x in json.loads(got)["streams"]}
            assert set(kinds) == {"video", "audio"} and (kinds["video"]["width"], kinds["video"]["height"]) == (1080, 1920)
    print("clips ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["link", "candidates", "page", "trim", "reframe", "demo"])
    ap.add_argument("clips_dir", nargs="?")
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--min", type=float, default=20)
    ap.add_argument("--max", type=float, default=40)
    ap.add_argument("--speakers", type=int, choices=[1, 2], default=1)
    ap.add_argument("--style", help="the creator's or the edit's style.json (its what_works moves are scored)")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--recommend", default="", help="page: comma-separated ids Claude recommends, in order")
    ap.add_argument("--name", help="trim: edit name prefix (default: the clips folder name)")
    ap.add_argument("--edits", default="edits")
    a = ap.parse_args()
    if a.cmd == "demo":
        return demo()
    if not a.clips_dir:
        ap.error("clips_dir is required")
    if a.cmd == "link":
        if len(a.ids) != 1:
            ap.error("link needs <video file> <clips_dir>")
        dst, how = link_source(a.clips_dir, a.ids[0])
        print(f"{dst} ({how})")
        return 0
    if a.cmd == "candidates":
        style = json.loads(Path(a.style).read_text()) if a.style else None
        prof = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor")) / "profile.json"
        names = name_list(json.loads(prof.read_text()).get("names")) if prof.exists() else []
        return candidates(a.clips_dir, a.min, a.max, a.speakers, style, a.top, keys.get("typesafe")[0], names=names)
    if a.cmd == "page":
        page(a.clips_dir, [x for x in a.recommend.split(",") if x])
    elif a.cmd == "reframe":
        reframe(a.clips_dir)
    else:
        if not a.ids:
            ap.error("trim needs at least one candidate id")
        trim(a.clips_dir, a.ids, a.name, a.edits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
