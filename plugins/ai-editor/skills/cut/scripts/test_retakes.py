#!/usr/bin/env python3
"""Self-check for retakes.py, offline: canned Jev answers, no key, no network.

    python3 test_retakes.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_timeline as B  # noqa: E402
import retakes as R  # noqa: E402


def take(text):
    """'|' is a 1.2 s pause; words are 0.3 s apart."""
    toks, t = [], 0.0
    for part in text.split("|"):
        for w in part.split():
            toks.append({"text": w, "start": round(t, 2), "end": round(t + 0.25, 2), "type": "word"})
            t += 0.3
        t += 1.2
    return toks


def run(text, same=0.95, keep="second", other=0.9):
    """spans, review and the questions asked, with every answer canned."""
    toks = take(text)
    cands = R.find(toks)
    qs = {q: v for c in cands for q, v in c["questions"].items()}
    canned = {}
    for q in qs:
        kind = q.rsplit("_", 1)[1]
        if kind == "keep":
            canned[q] = {"type": "choice", "choice": keep, "confidence": 0.9,
                         "probabilities": {keep: 0.95}}
        else:
            canned[q] = {"type": "noul", "noul": same if kind == "same" else other}
    cuts, review = R.decide(cands, R.jev.ask(R.STATE, qs, canned=canned) if qs else {})
    spans = R.to_spans(cuts, toks)
    B.resolve_spans(spans, toks)   # every span must quote cleanly, no overlaps
    return spans, review, qs


def test_retake_last_take_wins():
    spans, review, _ = run("so the main thing is money | so the main thing is that money compounds over time.")
    assert [s["text"] for s in spans] == ["so the main thing is money"], spans
    assert spans[0]["kind"] == "retake" and not review, (spans, review)


def test_false_start_in_a_clause():
    spans, _, _ = run("the thing about the thing about money is simple.")
    assert [s["text"] for s in spans] == ["the thing about"] and spans[0]["kind"] == "false_start", spans


def test_clean_take_asks_nothing():
    spans, review, qs = run("I moved to Lisbon last year. | The rent was half what I paid before.")
    assert not spans and not review and not qs, (spans, qs)


def test_broken_second_take_goes_to_review():
    spans, review, _ = run("so the main thing is money | so the main", keep="first")
    assert not spans and review and "kept" in review[0]["action"], (spans, review)


def test_unsure_is_a_low_cut_for_review():
    spans, review, _ = run("so the main thing is money | so the main thing is that money grows.", same=0.55)
    assert spans[0].get("confidence") == "low" and review[0]["action"] == "cut, low confidence", spans
    spans, review, _ = run("so the main thing is money | so the main thing is that money grows.", same=0.1)
    assert not spans and not review


def test_um_cut_without_asking_and_meta_asked():
    spans, _, qs = run("um I think so. | wait sorry | I think this works.", same=0.1, other=0.9)
    texts = [s["text"] for s in spans]
    assert "um" in texts and "wait sorry" in texts, spans
    assert not any(q.endswith("_filler") for q in qs)   # um is never a question


def test_chain_cuts_all_but_last():
    spans, _, qs = run("and to break down, | and to break down competitor ads, | "
                       "and to break down competitor ads for the whole niche.")
    assert [s["text"] for s in spans] == ["and to break down, and to break down competitor ads,"], spans
    assert sum(q.endswith("_keep") for q in qs) == 1, qs   # only the chain end asks which take


HOOK = "most people edit their videos backwards."
BODY = ("start with the ending you want the viewer to remember. | then write the line that gets them there. | "
        "film that line three times and keep the cleanest one. | cut every pause longer than a breath. | "
        "put a caption on the word that carries the idea. | zoom in when the point lands, not before. | "
        "add sound only where something changes on screen. | watch it once muted to check the captions. | "
        "play it back loud for the pace. | post it at the hour your audience is awake.")
CTA = "follow for the next part."


def test_alternate_hooks_after_the_cta():
    """Opening, body, call to action, then two more takes of the opening: the hook stays at the start,
    both late takes are cut from the main cut and listed, and the main cut never ends on a hook."""
    text = f"{HOOK} | {BODY} | {CTA} | {HOOK} | most people edit their videos the wrong way round."
    toks = take(text)
    assert len(R.alt_hooks(toks)) == 2, R.alt_hooks(toks)
    spans, review, qs = run(text)
    alts = [s for s in spans if s["kind"] == "alt_hook"]
    assert [s["text"] for s in alts] == [f"{HOOK} most people edit their videos the wrong way round."], spans
    assert not any(s["kind"] == "retake" for s in spans), spans   # no "last take wins" on a hook
    cuts = B.resolve_spans(spans, toks)
    kept = [w["text"] for w in toks if not B.covered_by(w, cuts)]
    assert " ".join(kept).startswith(HOOK) and kept[-1] == "part.", kept[-6:]
    with tempfile.TemporaryDirectory() as d:
        e = Path(d) / "take"
        e.mkdir()
        (e / "words.raw.json").write_text(json.dumps(toks))
        (e / "spans.json").write_text(json.dumps(spans))
        assert [a["n"] for a in R.write_hooks(e, toks)] == [1, 2]
        assert "Alternate hooks" in R.candidates_md(R.find(toks))
        v = R.hook_variant(e, 2)
        vt = B.resolve_spans(json.loads((v / "spans.json").read_text()), toks)
        lead = B.resolve_spans([json.loads((v / "lead.json").read_text())], toks)[0]
        assert lead["evidence"] == "most people edit their videos the wrong way round.", lead
        kept = [w for w in toks if not B.covered_by(w, vt)]
        assert kept[0]["text"] == "start", kept[:3]
        assert [w["text"] for w in kept[-10:]] == "part. most people edit their videos the wrong way round.".split(), kept[-10:]
    # lead_first moves the lead's frames to the front and splits a span across its edges
    assert B.lead_first([[0, 10], [20, 40]], 30, 40) == [[30, 40], [0, 10], [20, 30]]


def test_alternate_hooks_on_the_sample_whisper_words():
    """The sample take's Whisper words (testdata/sample-whisper.json). In the second audit's pass Whisper
    put the "I" of the late "I built a model router" into the previous phrase ("more tips I", the "I"
    stretched to 3 s at 179 s), so no clause opened like the hook and no alternate was found. Matching
    on the word sequence finds one run of late takes from 179 s, with the stray "I" in it."""
    toks = [{"text": t, "start": a, "end": b, "type": "word"}
            for t, a, b in json.loads((Path(__file__).parent / "testdata" / "sample-whisper.json").read_text())]
    alts = R.alt_hooks(toks)
    assert [round(toks[a]["start"]) for a, _ in alts] == [186, 191] and alts[-1][1] == len(toks) - 1, alts
    i = next(k for k, t in enumerate(toks) if t["text"] == "tips.")
    toks[i]["text"] = "tips"
    toks[i + 1].update(start=178.85, end=181.85)     # "I": attached to "tips", 3 s long
    alts = R.alt_hooks(toks)
    assert alts and alts[0][0] == i + 1 and round(toks[alts[0][0]]["start"]) == 179, [(toks[a]["text"], toks[a]["start"]) for a, _ in alts]
    assert alts[-1][1] == len(toks) - 1 and "Alternate hooks" in R.candidates_md(R.find(toks))
    cands = R.find(toks)       # no other candidate reaches into the hook run: the spans quote cleanly
    assert all(c["cut"][1] < alts[0][0] for c in cands if c["kind"] != "alt_hook"), cands


def test_text_and_fix():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "words.raw.json").write_text(json.dumps(take("I use cloud code. | cloud, daily")))
        txt = R.text_view(R.load(d))
        assert "[0.00-" in txt and "(+1.2s)" in txt and "cloud code." in txt, txt
        (Path(d) / "captions.json").write_text(json.dumps(take("cloud")))   # style-edit's caption copy
        assert R.fix(d, [("cloud", "Claude")]) == 3
        assert json.loads((Path(d) / "captions.json").read_text())[0]["text"] == "Claude"
        words = [t["text"] for t in json.loads((Path(d) / "words.raw.json").read_text())]
        assert words[2:4] == ["Claude", "code."] and words[4] == "Claude,", words


def test_fix_is_remembered_and_captions_use_the_cut_spelling():
    """A re-transcription that heard "Jev" as "Jeff" and "Claude" as "cloud": captions keep the cut's spelling
    with no fix call, and a fix made earlier applies to every later captions run."""
    cut = take("I built it with Jev and Claude | then haiku ran")
    heard = [dict(w) for w in cut]
    heard[4]["text"], heard[6]["text"] = "Jeff", "cloud."
    words, changed = R.caption_words(heard, cut, names=["Haiku"])
    assert [w["text"] for w in words] == "I built it with Jev and Claude. then Haiku ran".split(), words
    assert ("Jeff", "Jev") in changed and ("cloud.", "Claude.") in changed, changed
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "words.json").write_text(json.dumps(take("then haiku ran")))
        R.fix(d, [("haiku", "Haiku")])
        (Path(d) / "cut.transcript.json").write_text(json.dumps(take("then haiku ran")))
        words, _ = R.captions(d)
        assert words[1]["text"] == "Haiku" and (Path(d) / "captions.txt").exists(), words


def test_verify_counts_a_misheard_name_as_heard_differently():
    """Same audio, two passes: 'jev' at 1.2 s heard as 'jeff' is not a missing word; a word gone from the
    audio (nothing heard at its time) still is."""
    import contextlib
    import io
    import verify_cut as V
    from textnorm import pair_by_time, timed_words
    base = take("I built a router with jev that picks")
    exp = timed_words(base)
    misheard = [{**w, "text": "jeff" if w["text"] == "jev" else w["text"]} for w in base]
    for act, missing in ((timed_words(misheard), False), (timed_words([w for w in base if w["text"] != "jev"]), True)):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), tempfile.TemporaryDirectory() as d:
            code = V.report(Path(d), [t for t, _, _ in exp], [t for t, _, _ in act], set(), *pair_by_time(exp, act))
        assert ("MISSING" in out.getvalue()) == missing and code == int(missing), out.getvalue()
        assert ("jev -> jeff" in out.getvalue()) != missing, out.getvalue()


def test_no_key_falls_back():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "words.raw.json").write_text(json.dumps(take("so the main | so the main thing.")))
        assert R.propose(d) == 4
        assert (Path(d) / "candidates.md").exists() and not (Path(d) / "spans.json").exists()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all ok")
