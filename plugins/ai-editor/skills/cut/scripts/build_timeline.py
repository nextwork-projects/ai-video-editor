#!/usr/bin/env python3
"""Compile the edit: quoted removals + transcript -> kept spans, frame-accurate.

    python3 build_timeline.py <source> <edit_dir> [--max-pause S] [--dry-run]

Reads   <edit_dir>/words.raw.json   the transcript of the source
        <edit_dir>/spans.json       what to remove, QUOTED from the transcript
        <edit_dir>/lead.json        optional, one quoted range that plays first (an alternate
                                    hook recorded after the body; retakes.py hook writes it)
Writes  <edit_dir>/decisions.json   kept spans in source seconds (docs/CONTRACTS.md)
        <edit_dir>/report.json      every cut with its kind, evidence and note
        <edit_dir>/words.json       the kept words re-timed onto cut.mp4's timeline
        <edit_dir>/paper-edit.md    the cut as text, for a read-through
        <edit_dir>/cut-check.html   the whole transcript, removed words struck through

spans.json is a list of removals. Claude writes it; nothing here decides what to cut:

    [{"text": "so the thing about, um", "kind": "false_start", "note": "restarts at 5.8s"},
     {"text": "wait, sorry", "kind": "meta"},
     {"text": "he ended up getting found", "kind": "retake", "occurrence": 1,
      "confidence": "medium", "note": "keeper at 70.4s"}]

A phrase said more than once is an ERROR until "occurrence": N (1-based) or
"after": <seconds> picks one. Taking the first match silently is how the keeper
gets cut and the flub stays.

The mechanical jobs this does so nobody types a timestamp:
  1. Boundaries. Quoted text resolves to token edges. Each cut is snapped out to
     the neighbouring kept words (absorbing the dead air round a flub), then
     padded back in so no onset or tail is clipped.
  2. Pauses. Any silence over the pause target is tightened. Silence is measured
     from the audio, with a threshold derived from this take.
  3. Splice budget. The TOTAL silence a splice leaves is capped, because the
     parts (pad after one word + pad before the next) add up past it on their own.
  4. Frames. Boundaries are quantized to frames: start floored, end ceiled, and
     the end clamped so it never reaches into the next kept word's frame.
  5. Splices against the audio. Word times can be wrong (numbers worst: one started
     0.6 s late and a pause cut took "a hun-"). Any kept edge with speech on both
     sides moves out to the nearest quiet frame, never into a removed word.

Pause target: --max-pause (default 0.15 s), tightened to two thirds of it (0.10 s).
Exit codes: 0 ok, 1 error
"""
import argparse
import array
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from textnorm import load_words, locate  # noqa: E402

KINDS = {"alt_hook", "retake", "false_start", "filler", "meta", "audio_event", "redundant"}
CONF = {"high", "medium", "low"}
DEFAULT_MAX_PAUSE = 0.15
GAP_QUIET_DB = 12.0   # a word gap counts as a pause only if it stays this far under speech


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("FAIL: " + " ".join(cmd) + "\n" + r.stderr)
    return r.stdout.strip()


def probe(src):
    rate = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=r_frame_rate", "-of", "default=nw=1:nk=1", str(src)])
    n, _, d = rate.partition("/")
    fps = float(n) / float(d or 1)
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=nw=1:nk=1", str(src)]))
    # The frame count comes from the video stream, never duration * fps: a phone's audio often
    # runs a frame or two past its video, and a last span sized from the format duration asks
    # render.py for frames that do not exist ("span N: 179 frames, wanted 180").
    n = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
             "stream=nb_read_packets", "-of", "default=nw=1:nk=1", str(src)])
    return fps, dur, int(n) if n.isdigit() else int(round(dur * fps))


# --- 1. quoted spans -> cuts on token edges ----------------------------------

def resolve_spans(spans, toks):
    """[(cut dict)] or exit listing every span that did not resolve."""
    cuts, errs = [], []
    for i, sp in enumerate(spans):
        text, kind, conf = sp.get("text", ""), sp.get("kind", "retake"), sp.get("confidence", "high")
        if kind not in KINDS:
            errs.append(f"span[{i}]: kind {kind!r} not in {sorted(KINDS)}")
            continue
        if conf not in CONF:
            errs.append(f"span[{i}]: confidence {conf!r} not in {sorted(CONF)}")
            continue
        hits = locate(text, toks)
        if "after" in sp:
            hits = [h for h in hits if toks[h[0]]["start"] >= float(sp["after"])]
        if not hits:
            errs.append(f"span[{i}] {text[:50]!r}: no match. Quote it from the transcript.")
            continue
        if "occurrence" in sp:
            k = int(sp["occurrence"]) - 1
            if not 0 <= k < len(hits):
                errs.append(f"span[{i}] {text[:50]!r}: occurrence {k + 1} but it appears {len(hits)}x")
                continue
            a, b = hits[k]
        elif "after" in sp:
            a, b = hits[0]    # the first match after that second
        elif len(hits) > 1:
            where = ", ".join(f"{toks[x]['start']:.2f}s" for x, _ in hits[:6])
            errs.append(f"span[{i}] {text[:50]!r}: appears {len(hits)}x ({where}). "
                        f"Add \"occurrence\": N or \"after\": <seconds>.")
            continue
        else:
            a, b = hits[0]
        cuts.append({"start": toks[a]["start"], "end": toks[b]["end"], "kind": kind,
                     "evidence": " ".join(t["text"].strip() for t in toks[a:b + 1]),
                     "confidence": conf, "note": sp.get("note", "")})
    cuts.sort(key=lambda c: c["start"])
    for x, y in zip(cuts, cuts[1:]):
        if y["start"] < x["end"]:
            errs.append(f"overlap {x['start']:.2f}-{x['end']:.2f}s and {y['start']:.2f}-"
                        f"{y['end']:.2f}s. Merge them into one span.")
    if errs:
        for e in errs:
            print("ERROR: " + e, file=sys.stderr)
        sys.exit(1)
    return cuts


def covered_by(w, cuts):
    return any(c["start"] <= w["start"] and w["end"] <= c["end"] for c in cuts)


# --- 2. boundary safety -------------------------------------------------------

def edge(left, right, pad, from_left):
    """A point inside [left, right]: padded from the near side, or the midpoint
    when the gap cannot hold the pad. Never outside the gap."""
    gap = right - left
    if gap <= 0:
        return right if from_left else left
    if gap >= 2 * pad:
        return left + pad if from_left else right - pad
    return left + gap / 2.0


# A word this short has no onset to hear when spliced hard against: a 40-60 ms
# "so" or "I" right after a cut gets lost even when its audio is in the render.
# One frame at 30 fps is 33 ms, so padding cannot buy the room; leaving a little
# more of the pause in front of it can.
SHORT_WORD_S = 0.12
RUNWAY_S = 0.25


def snap_and_pad(cuts, words, pad):
    """Extend each cut out to its neighbouring KEPT words, then pad back in."""
    kept = [w for w in words if not covered_by(w, cuts)]
    out = []
    for c in cuts:
        prev_end = max((w["end"] for w in kept if w["end"] <= c["start"] + 1e-6), default=0.0)
        nxt = min((w for w in kept if w["start"] >= c["end"] - 1e-6),
                  key=lambda w: w["start"], default=None)
        pad_r = max(pad, RUNWAY_S) if nxt and nxt["end"] - nxt["start"] < SHORT_WORD_S else pad
        a = edge(prev_end, c["start"], pad, True)
        b = c["end"] if nxt is None else edge(c["end"], nxt["start"], pad_r, False)
        if b <= a:
            a, b = c["start"], c["end"]
        # a removal that runs to the end of the take would otherwise leave a stub
        # of the last frames after the last removed word
        if nxt is None:
            b = math.inf
        out.append(dict(c, start=a, end=b, _next=nxt["start"] if nxt else None))
    return out


# --- 3. silence: threshold derived from this take -----------------------------
# A fixed dB threshold is wrong: what it has to separate is a DISTANCE (this
# speaker's speech vs this room's floor), and both move from take to take. So:
# speech = p99 of 20 ms window levels, threshold = speech - 26 dB, never closer
# than 6 dB above the room floor.
# Under 20 dB between speech and floor there is a music bed (or a loud room) under
# the voice. Measured silence cannot see a pause there, and a threshold high enough
# to see one also sees the quiet ends of words. So the transcript becomes the
# authority: only gaps BETWEEN words are trimmed, and only where the audio stays
# near the bed, measured per file from the quietest 10% of the take (the bed level)
# plus a third of the speech-to-bed distance. Under 10 dB the run stops rather than guess.
SPEECH_OFFSET_DB = 26.0
MIN_SEPARATION_DB = 20.0
BED_PERCENTILE = 0.10
FLOOR_SEARCH_DB = 10
FLOOR_HEADROOM_DB = 6.0
RMS_WIN_S = 0.020


def window_rms_db(src):
    n = int(16000 * RMS_WIN_S)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    out = []
    for i in range(0, len(a) - n, n):
        m = sum(v * v for v in a[i:i + n]) / n
        out.append(10 * math.log10(m / 32768.0 ** 2) if m > 0 else -120.0)
    return out


def audible_end(lvl, noise_db, t):
    """When the audio last had energy at or before t. Word END labels lag the
    audio (transcribers fold trailing silence into the last word), so splices
    are budgeted from here, not from the label."""
    if not lvl:
        return None
    i = min(len(lvl) - 1, int(t / RMS_WIN_S))
    while i >= 0 and lvl[i] <= noise_db:
        i -= 1
    return None if i < 0 else min(t, (i + 1) * RMS_WIN_S)


ONSET_MARGIN_S = 0.04   # soft onsets (p, f, h) start under the threshold


def audible_start(lvl, noise_db, t, limit):
    """When the audio first has energy at or after t. Whisper labels a word as
    starting early, folding the silence before it in; a splice budgeted from the
    label leaves that silence in the cut."""
    i, end = max(0, int(t / RMS_WIN_S)), min(len(lvl), int(limit / RMS_WIN_S))
    while i < end and lvl[i] <= noise_db:
        i += 1
    return None if i >= end else max(t, i * RMS_WIN_S - ONSET_MARGIN_S)


# A label far longer than the word can be said in (over 2.5x a speech-rate length and 0.4 s more) is a
# transcriber artefact: Whisper times a 0.15 s "if" at 0.7 s, or folds a 3 s pause into an "I". Judged
# on that label, a pause cut "clips" a word the render still plays, and the cut is rebuilt for nothing. So such a label is fitted to where the
# audio has energy inside it (or just after it, when the label runs ahead of the word), and failing
# that its end is clamped to a speech-rate length.
def plausible_s(text):
    return 0.1 + 0.065 * len(re.sub(r"[^a-z0-9]", "", str(text).lower()))


def implausible(w):
    d, est = w["end"] - w["start"], plausible_s(w["text"])
    return d > max(2.5 * est, est + 0.4)


def fit_labels(toks, lvl, noise_db):
    """{index: (start, end)} for each implausibly long word label, fitted to the audio: from the first
    audible window to the end of that audible run, at most a speech-rate length.
    ponytail: a breath before the word inside the label is taken for the word; judged by level, not voice."""
    out = {}
    for i, w in enumerate(toks):
        if w.get("type") != "word" or not implausible(w):
            continue
        est = plausible_s(w["text"])
        nxt = next((t["start"] for t in toks[i + 1:] if t.get("type") in ("word", "audio_event")), w["end"] + est)
        a = audible_start(lvl, noise_db, w["start"], min(nxt, w["end"] + est)) if lvl else None
        if a is None:
            out[i] = (w["start"], round(w["start"] + est, 3))
            continue
        j = int((a + ONSET_MARGIN_S) / RMS_WIN_S)   # the word ends where its first audible run does
        while j < len(lvl) and lvl[j] > noise_db and j * RMS_WIN_S < a + est:
            j += 1
        out[i] = (round(a, 3), round(max(min(j * RMS_WIN_S, nxt), a + 0.04), 3))
    return out


def unheard(toks, lvl, noise_db):
    """[(index, voiced_s)]: implausibly long labels holding more voiced audio than their word can.
    Whisper can fold a whole spoken repeat into one label (the sample's "content" over "and to break
    down competitor ads and"); fitting the label cannot bring those words back, so transcribe.py
    re-transcribes the stretch, and transcript.txt marks what is still missing."""
    out = []
    for i, w in enumerate(toks):
        if w.get("type") != "word" or not implausible(w):
            continue
        voiced = sum(v > noise_db for v in lvl[int(w["start"] / RMS_WIN_S):int(w["end"] / RMS_WIN_S)]) * RMS_WIN_S
        est = plausible_s(w["text"])
        if voiced > max(2 * est, est + 0.5):   # the sample's "content": 1.3 s voiced, 0.56 s word
            out.append((i, round(voiced, 2)))
    return out


def apply_labels(toks, labels):
    """toks with fitted labels as copies; the raw list is never changed."""
    return [dict(t, start=labels[i][0], end=labels[i][1]) if i in labels else t for i, t in enumerate(toks)]


def load_fitted(d):
    """words.raw.json with build_timeline's fitted labels (report.json): the words paper-edit.md,
    words.json and verify_cut.py all judge, so the three agree."""
    toks = load_words(Path(d) / "words.raw.json")
    rep = Path(d) / "report.json"
    labels = json.loads(rep.read_text()).get("labels", {}) if rep.exists() else {}
    return apply_labels(toks, {int(k): v for k, v in labels.items()})


def derive_noise_db(lvl):
    """(noise_db or None, diag)."""
    if len(lvl) < 50:
        return None, {"reason": f"only {len(lvl)} audio windows, too short to measure"}
    hist = {}
    for v in lvl:
        hist[int(math.floor(v))] = hist.get(int(math.floor(v)), 0) + 1
    srt = sorted(lvl)
    speech = int(math.floor(srt[min(len(srt) - 1, int(0.99 * len(srt)))]))
    floor = max((b for b in hist if b < speech - FLOOR_SEARCH_DB), key=lambda b: hist[b], default=None)
    if floor is None:
        return None, {"reason": f"no floor below speech ({speech} dB)", "speech": speech}
    sep = speech - floor
    diag = {"speech": float(speech), "floor": float(floor), "sep": float(sep)}
    if sep < MIN_SEPARATION_DB:
        bed = srt[int(BED_PERCENTILE * (len(srt) - 1))]
        diag.update(bed=round(bed, 1), noise=round(bed + (speech - bed) / 3, 1))
        return diag["noise"], diag
    diag["noise"] = noise = max(speech - SPEECH_OFFSET_DB, floor + FLOOR_HEADROOM_DB)
    return noise, diag


def detect_silence(src, noise_db, min_dur):
    """Measured silence. Catches the pauses a transcriber hides INSIDE a word
    token (a 0.25 s word labelled 1.6 s long), which token gaps cannot see."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-vn", "-af",
                          f"silencedetect=noise={noise_db}dB:d={min_dur}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    spans, start = [], None
    for line in err.splitlines():
        if "silence_start:" in line:
            start = float(line.split("silence_start:")[1].split()[0])
        elif "silence_end:" in line and start is not None:
            end = float(line.split("silence_end:")[1].split()[0])
            if spans and start - spans[-1][1] <= 0.05:   # coalesce touching runs
                spans[-1][1] = max(spans[-1][1], end)
            elif end > start:
                spans.append([start, end])
            start = None
    return [tuple(s) for s in spans]


def quiet_word_gaps(words, gap_max, lvl, quiet_db):
    """Gaps between words that the audio confirms are not speech (90% of the gap's
    windows under quiet_db). Breaths sit above the silence threshold, so measured
    silence alone leaves every breath in. A gap Whisper left by dropping a word is
    loud, so the level check keeps it."""
    out = []
    for p, n in zip(words, words[1:]):
        a, b = p["end"], n["start"]
        if b - a <= gap_max or not lvl:
            continue
        win = sorted(lvl[int(a / RMS_WIN_S):int(b / RMS_WIN_S)])
        if win and win[int(0.9 * (len(win) - 1))] < quiet_db:
            out.append((a, b))
    return out


def merge_spans(spans):
    out = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def silence_cuts(words, gap_max, gap_keep, heard):
    """Tighten (never fully close) every silence longer than gap_max: measured
    silence plus the audio-checked word gaps from quiet_word_gaps."""
    out = []
    for a, b in heard:
        if b - a <= gap_max:
            continue
        nxt = next((w for w in words if w["start"] >= b - 0.05), None)
        keep = max(gap_keep, RUNWAY_S) if nxt and nxt["end"] - nxt["start"] < SHORT_WORD_S else gap_keep
        s, e = a + keep / 2, b - keep / 2
        if e - s >= 0.04:
            out.append({"start": s, "end": e, "kind": "silence", "confidence": "high",
                        "evidence": f"{b - a:.2f}s silence", "note": f"tightened to {keep:.2f}s"})
    return out


def lead_trail_cuts(kept, dur, gap_keep):
    """Dead air before the first KEPT word and after the last one."""
    out = []
    if not kept:
        return out
    first, last = kept[0]["start"], max(w["end"] for w in kept)
    if first > gap_keep:
        out.append({"start": 0.0, "end": first - gap_keep, "kind": "silence", "confidence": "high",
                    "evidence": f"{first:.2f}s before first word", "note": "lead-in"})
    if dur - last > gap_keep:
        out.append({"start": last + gap_keep, "end": math.inf, "kind": "silence",
                    "confidence": "high", "evidence": "after last word", "note": "tail"})
    return out


# When cuts merge, the survivor keeps the kind a human most needs to see.
KIND_RANK = {"redundant": 4, "retake": 2, "false_start": 2, "meta": 2, "filler": 2,
             "audio_event": 1, "silence": 0}


def merge(cuts):
    out = []
    for c in sorted(cuts, key=lambda c: c["start"]):
        if out and c["start"] <= out[-1]["end"] + 1e-6:
            last = out[-1]
            last["end"] = max(last["end"], c["end"])
            if KIND_RANK.get(c["kind"], 2) > KIND_RANK.get(last["kind"], 2):
                last["kind"] = c["kind"]
            if c.get("_next") is not None:
                last["_next"] = max(last.get("_next") or 0, c["_next"])
            last["evidence"] = (last["evidence"] + " | " + c["evidence"])[:300]
            if c.get("confidence") == "low":
                last["confidence"] = "low"
        else:
            out.append(dict(c))
    return out


# --- 4. splice budget ---------------------------------------------------------
SPLICE_LEFT_MIN_S = 0.05   # silence always left after the previous word


def splice_neighbours(c, kept, lvl, noise_db):
    left = None
    for w in kept:
        if w["start"] < c["start"]:
            e = min(w["end"], c["start"])
            left = e if left is None else max(left, e)
    if left is not None and lvl and noise_db is not None:
        a = audible_end(lvl, noise_db, left)
        if a is not None:
            floor_t = max((w["start"] for w in kept if w["start"] < c["start"]), default=0.0)
            left = max(min(left, a), floor_t)
    nxt = min((w for w in kept if w["end"] > c["end"]), key=lambda w: w["start"], default=None)
    if nxt is not None and lvl and noise_db is not None:
        on = audible_start(lvl, noise_db, max(nxt["start"], c["end"]), nxt["end"])
        if on is not None and on > nxt["start"]:
            nxt = {**nxt, "start": on}
    return left, nxt


def enforce_splice_budget(cuts, words, model_cuts, budget, lvl=None, noise_db=None):
    """Cap the TOTAL silence each splice leaves. Only ever WIDENS a cut, never past
    SPLICE_LEFT_MIN_S after the previous word or into the next word's runway, so
    it cannot reach a kept word."""
    budget = max(budget, SPLICE_LEFT_MIN_S)
    kept = [w for w in words if not covered_by(w, model_cuts)]
    for c in cuts:
        prev_end, nxt = splice_neighbours(c, kept, lvl, noise_db)
        if prev_end is None or nxt is None:
            continue
        c["_next"] = nxt["start"]   # the audible onset: the frame clamp must not reach back past it
        left, right = max(0.0, c["start"] - prev_end), max(0.0, nxt["start"] - c["end"])
        if left + right <= budget + 1e-6:
            continue
        short = nxt["end"] - nxt["start"] < SHORT_WORD_S
        want_right = max(0.0, min(right, budget - SPLICE_LEFT_MIN_S if short else budget / 2))
        want_left = max(SPLICE_LEFT_MIN_S, budget - want_right)
        if want_left > left:
            want_left, want_right = left, max(0.0, budget - left)
        c["start"] = prev_end + want_left
        c["end"] = nxt["start"] - min(right, want_right)
        c["_next"] = nxt["start"]
    return cuts


def splice_gaps(cuts, words, model_cuts, lvl=None, noise_db=None):
    kept = [w for w in words if not covered_by(w, model_cuts)]
    out = []
    for c in cuts:
        prev_end, nxt = splice_neighbours(c, kept, lvl, noise_db)
        if prev_end is not None and nxt is not None:
            out.append(max(0.0, c["start"] - prev_end) + max(0.0, nxt["start"] - c["end"]))
    return out


# --- 5. frames ------------------------------------------------------------------

MIN_KEPT_S = 0.2
END_TAIL_S = 0.4   # room after the final word, so the video does not stop mid-release


def kept_frames(cuts, fps, dur, total=None):
    """Cuts -> kept [start_frame, end_frame) pairs. Cut start floored (a flub's
    onset starts before its label; rounding later re-admits it), cut end ceiled
    but clamped to the frame the next kept word starts in (ceiling into it
    deletes the word). total: the video stream's real frame count."""
    total = int(round(dur * fps)) if total is None else total
    kept, cursor = [], 0
    for c in cuts:
        a = max(0, min(total, math.floor(c["start"] * fps)))
        b = total if c["end"] == math.inf else max(0, min(total, math.ceil(c["end"] * fps)))
        if c.get("_next") is not None:
            b = min(b, max(a + 1, math.floor(c["_next"] * fps)))
        a = max(a, cursor)
        if b <= a:
            continue
        # A sliver between two cuts is the tail of a flub the transcriber mislabelled, not a word.
        if a > cursor and (not kept and cursor == 0 or a - cursor >= MIN_KEPT_S * fps):
            kept.append([cursor, a])
        cursor = b
    if cursor < total:
        kept.append([cursor, total])
    return kept


# --- 6. splices against the audio ---------------------------------------------
SPLICE_REACH_S = 0.6     # how far an edge may move to find a quiet frame
LOUD_OVER_DB = 10.0      # speech: this far over the silence threshold


def in_speech(lvl, t, quiet_db):
    """The 20 ms windows just before and just after t are both speech."""
    w = int(t / RMS_WIN_S)
    return 0 < w < len(lvl) and min(lvl[w - 1], lvl[w]) > quiet_db + LOUD_OVER_DB


def fix_splices(frames, fps, lvl, quiet_db, total, removed=()):
    """Move each kept edge that lands inside speech out into its removed side, to the first frame
    with a quiet window next to it (at most SPLICE_REACH_S, never into a removed word's label).
    removed: [(start, end)] of the words the cut removes on purpose. total: the source's frame count.
    Returns (frames, moved [(old_s, new_s)], left [edge_s]): left are edges no quiet frame could fix."""
    frames = [list(f) for f in frames]
    reach = int(SPLICE_REACH_S * fps)

    def quiet(g):
        w = int(g / fps / RMS_WIN_S)
        return min(lvl[max(0, w - 1):w + 1] or [0.0]) <= quiet_db

    moved, left = [], []
    for k, fr in enumerate(frames):
        for side in (0, 1):    # 0: the keep's start (walk back), 1: its end (walk on)
            f = fr[side]
            t = f / fps
            if f == (0 if side == 0 else total) or not in_speech(lvl, t, quiet_db):
                continue
            if side == 0:
                lo = max([frames[k - 1][1] if k else 0, f - reach]
                         + [math.ceil(min(e, t) * fps) for s, e in removed if s < t])
                to = next((g for g in range(f, lo - 1, -1) if quiet(g)), None)
            else:
                hi = min([frames[k + 1][0] if k + 1 < len(frames) else total, f + reach]
                         + [math.floor(max(s, t) * fps) for s, e in removed if e > t])
                to = next((g for g in range(f, hi + 1) if quiet(g)), None)
            if to is None:
                left.append(round(t, 2))
            else:
                fr[side] = to
                moved.append((round(t, 2), round(to / fps, 2)))
    out = []
    for fr in frames:   # an edge moved up to its neighbour joins the two
        if out and fr[0] <= out[-1][1]:
            out[-1][1] = max(out[-1][1], fr[1])
        else:
            out.append(fr)
    return out, moved, left


def lead_first(frames, a, b):
    """Kept frame ranges with source frames [a, b) moved to the front, split at a and b."""
    cut = []
    for s, e in frames:
        cut += [[x, y] for x, y in ((s, min(e, a)), (max(s, a), min(e, b)), (max(s, b), e)) if y > x]
    return [f for f in cut if a <= f[0] and f[1] <= b] + [f for f in cut if not (a <= f[0] and f[1] <= b)]


def is_kept(w, spans):
    """A word plays if at least 0.1 s (or half of it, if shorter) is inside a kept
    span. Overlap, not onset or midpoint: transcribers stretch a word into the
    silence before or after it, so either end of its label can sit in a cut."""
    need = min(0.1, (w["end"] - w["start"]) / 2)
    return sum(max(0.0, min(w["end"], s["end"]) - max(w["start"], s["start"])) for s in spans) >= need


def retime(words, spans):
    """Kept words moved onto the cut's timeline, clipped to the span they play in."""
    out, t = [], 0.0
    offs = []
    for s in spans:
        offs.append(t)
        t += s["end"] - s["start"]
    for w in words:
        if w.get("type") != "word" or not is_kept(w, spans):
            continue
        i = max(range(len(spans)), key=lambda k: min(w["end"], spans[k]["end"]) - max(w["start"], spans[k]["start"]))
        s, o = spans[i], offs[i]
        out.append({"text": w["text"], "type": "word",
                    "start": round(max(w["start"], s["start"]) - s["start"] + o, 3),
                    "end": round(min(w["end"], s["end"]) - s["start"] + o, 3)})
    return sorted(out, key=lambda w: w["start"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("edit_dir")
    ap.add_argument("--max-pause", type=float, default=None,
                    help=f"longest pause left between phrases (default {DEFAULT_MAX_PAUSE})")
    ap.add_argument("--pad", type=float, default=0.10, help="kept round each cut (s)")
    ap.add_argument("--noise", type=float, default=None,
                    help="silence threshold in dB. Default: derived from the take.")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    d = Path(a.edit_dir)
    raw = load_words(d / "words.raw.json")
    toks = [t for t in raw if t.get("type") in ("word", "audio_event")]
    if not any(t["type"] == "word" for t in toks):
        sys.exit("ERROR: transcript has no words")
    sp = d / "spans.json"
    spans_in = json.loads(sp.read_text()) if sp.exists() else []
    resolve_spans(spans_in, toks)   # a bad quote fails before the audio is read

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
    from ai_editor import taste    # the user's own pause setting (taste skill) beats the default
    max_pause = a.max_pause or taste.load_json().get("cut", {}).get("max_pause") or DEFAULT_MAX_PAUSE
    gap_max, gap_keep, splice_max = max_pause, round(2 / 3 * max_pause, 3), max_pause

    fps, dur, nframes = probe(a.source)
    lvl = window_rms_db(a.source)
    derived, diag = derive_noise_db(lvl)
    bed = "bed" in diag      # music under the voice: word gaps only, never inside a word
    noise = a.noise if a.noise is not None else derived
    if noise is None:
        sys.exit("ERROR: cannot derive a silence threshold: " + diag["reason"] +
                 "\n  Measure with `ffmpeg -i <source> -af volumedetect -vn -f null -` and "
                 "pass --noise <dB> (about 10 dB above the mean volume).")
    labels = fit_labels(raw, lvl, noise)
    if labels:
        print(f"labels     {len(labels)} implausibly long word label(s) fitted to the audio: "
              + ", ".join(f"{raw[i]['text'].strip()!r} {raw[i]['end'] - raw[i]['start']:.1f}s" for i in list(labels)[:5]))
    raw = apply_labels(raw, labels)
    toks = [t for t in raw if t.get("type") in ("word", "audio_event")]
    words = [t for t in toks if t["type"] == "word"]
    model_cuts = resolve_spans(spans_in, toks)
    if a.noise is None:
        print(f"noise      {noise:.0f} dB derived (speech {diag['speech']:.0f}, "
              + (f"music bed {diag['bed']:.0f}: trimming only between words)" if bed
                 else f"floor {diag['floor']:.0f})"))
    kept_words = [w for w in words if not covered_by(w, model_cuts)]
    if bed:
        heard = quiet_word_gaps(kept_words, gap_max, lvl, noise)
    else:
        heard = detect_silence(a.source, noise, gap_max)
        if not heard:
            sys.exit("ERROR: the threshold marked no silence at all. Pass --noise explicitly.")
        speech_db = sorted(lvl)[int(0.99 * (len(lvl) - 1))] if lvl else 0.0
        heard = merge_spans(heard + quiet_word_gaps(kept_words, gap_max, lvl, speech_db - GAP_QUIET_DB))
    splice_noise = None if bed else noise    # over a bed, word labels bound the splices
    allcuts = merge(snap_and_pad(model_cuts, words, a.pad)
                    + silence_cuts(words, gap_max, gap_keep, heard)
                    + lead_trail_cuts(kept_words, dur, gap_keep))
    allcuts = enforce_splice_budget(allcuts, words, model_cuts, splice_max, lvl, splice_noise)
    if kept_words and allcuts and allcuts[-1]["end"] >= dur:   # let the last word ring out
        last = max(w["end"] for w in kept_words)
        allcuts[-1]["start"] = max(allcuts[-1]["start"], min(dur, last + END_TAIL_S))
    frames = kept_frames(allcuts, fps, dur, nframes)
    moved, left = [], []
    if splice_noise is not None:
        removed = [(w["start"], w["end"]) for w in words if covered_by(w, model_cuts)]
        frames, moved, left = fix_splices(frames, fps, lvl, noise, nframes, removed)
    lead = d / "lead.json"
    if lead.exists():   # split halfway into the pauses either side, so no word is halved
        lc = resolve_spans([{**json.loads(lead.read_text()), "kind": "alt_hook"}], toks)[0]
        before = max([t["end"] for t in toks if t["end"] <= lc["start"]], default=0.0)
        after = min([t["start"] for t in toks if t["start"] >= lc["end"]], default=dur)
        frames = lead_first(frames, round((before + lc["start"]) / 2 * fps), round((lc["end"] + after) / 2 * fps))
        print(f"lead       {lc['evidence'][:60]!r} plays first")
    spans = [{"start": round(s / fps, 6), "end": round(e / fps, 6)} for s, e in frames]
    final = sum(s["end"] - s["start"] for s in spans)

    gaps = sorted(splice_gaps(allcuts, words, model_cuts, lvl, splice_noise))
    print(f"pause      target {max_pause:.2f}s (tighten over {gap_max:.2f}s to {gap_keep:.2f}s)")
    print(f"source     {dur:.2f}s at {fps:.3f} fps")
    print(f"cuts       {len(model_cuts)} from spans.json, {len(allcuts)} after merging with pauses")
    print(f"result     {final:.2f}s  ({dur - final:.2f}s removed, {len(spans)} kept spans)")
    if gaps:
        print(f"splices    median {gaps[len(gaps) // 2]:.3f}s  max {gaps[-1]:.3f}s")
    if splice_noise is not None:
        print(f"speech     {len(moved)} join(s) moved off speech to a quiet frame"
              + "".join(f" ({a:.2f}->{b:.2f}s)" for a, b in moved[:5]) + f"; {len(left)} still in speech"
              + (": " + ", ".join(f"{t:.2f}s" for t in left[:8]) + " (listen to these joins)" if left else ""))
    for c in model_cuts:
        flag = "  <- LOW CONFIDENCE" if c["confidence"] == "low" else ""
        print(f"  CUT {c['start']:7.2f}-{c['end']:7.2f} [{c['kind']:<11}] {c['evidence'][:60]!r}{flag}")
    if a.dry_run:
        print("(dry run, nothing written)")
        return

    for c in allcuts:
        c.pop("_next", None)
        if c["end"] == math.inf:
            c["end"] = dur
    (d / "decisions.json").write_text(json.dumps(spans, indent=1))
    (d / "report.json").write_text(json.dumps(
        {"source": str(Path(a.source).resolve()), "fps": fps, "duration": dur, "final_s": final,
         "max_pause_s": max_pause, "frames": frames, "model_cuts": model_cuts, "cuts": allcuts,
         "labels": {str(i): v for i, v in labels.items()}, "splices_in_speech": left},
        indent=1))
    (d / "words.json").write_text(json.dumps(retime(words, spans), indent=1))
    import preview_cut
    preview_cut.write_all(d, toks, model_cuts, spans, dur, final)
    for f in ("decisions.json", "report.json", "words.json", "paper-edit.md", "cut-check.html"):
        print(d / f)


if __name__ == "__main__":
    main()
