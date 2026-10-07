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
