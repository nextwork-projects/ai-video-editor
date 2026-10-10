#!/usr/bin/env python3
"""Propose the visuals cheaply: one routing pick per sentence, so Claude only fills small template JSON.

    python3 route.py beats edits/NAME            captions.json -> edits/NAME/beats.json
    python3 route.py highlight edits/NAME images/capture-2-x.text.json "what the speaker says there"
    python3 route.py demo                        self-check (offline)

beats: code splits captions.json into sentences (times kept in code), marks the profile's named
products, tools and people found in each, plus any word written with a capital inside a sentence (a
product or person the profile does not list: "Jev", "Claude", "Haiku"), then, when a TypeSafe key is saved, asks Jev once per
sentence to pick one of: none, a capture format (capture:shot, capture:browser, capture:sticker), post, logo,
or an overlay format (logo_cluster, chat, terminal, toasts, side_by_side, video_card). Without a key every pick is null and Claude decides from
the same file. Either way Claude (or the template-filler agent) writes visuals.json. When edits/NAME/style.json
carries the creator's graphics.kinds, her mix weights the picks (prefer) and is printed for Claude.

highlight: the capture's text blocks (capture.mjs "page_text": true) and the spoken line in; the one
block that is the evidence out (Jev picks line by line; without a key the blocks are printed for Claude).
Stdlib only. Cost lands in edits/NAME/jev-usage.jsonl.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))

# Jev leans to the first option, so "none" leads: a card has to earn its place. Only overlay formats:
# type cards (words on a ground) were removed from the product.
ROUTES = {
    "none": "the speaker alone carries this line: filler, a transition, or nothing to show",
    "capture:shot": "a real product, website or page is named: its real page floats in, pushed into the marked part",
    "capture:browser": "the speaker talks about going to a site or doc: the real page in a browser window, a cursor to the line",
    "capture:sticker": "a figure or claim from a real page or doc: that one sentence cut out, the said words highlighted",
    "post": "a real social post or comment is quoted",
    "logo": "one brand, product or tool is named in passing: its real logo",
    "logo_cluster": "several brands or tools are named together: their real logos round the head",
    "chat": "what an app or AI replies is described: its chat thread, in the speaker's words",
    "terminal": "a command, install or script run is described: a real terminal",
    "toasts": "notifications, alerts or messages arriving are described: the app's real notifications",
    "side_by_side": "two real products or pages are compared: both screenshots side by side",
    "video_card": "the speaker's own clip or a recording shows it: a short real clip in a card",
}
# graphics.kinds (creator-teardown style.json) -> the routes that show that kind of thing from a real source.
# A text card is never built (type cards were removed): it routes to a sticker of the real sentence.
KIND_ROUTES = {"real screenshot": ("capture:shot", "capture:sticker"), "UI recording": ("capture:browser", "video_card"),
               "text card": ("capture:sticker",), "chart": ("capture:sticker",), "photo": ("capture:shot",),
               "meme": ("capture:shot",), "logo": ("logo", "logo_cluster"), "b-roll": ("video_card",)}
MAX_LINES = 30   # blocks offered to Jev for a highlight, nearest the spoken words first


def sentences(words):
    """[{i, text, start, end, words}] split at . ? ! and at pauses over 0.8 s."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or w["text"].rstrip().endswith((".", "?", "!")) or nxt["start"] - w["end"] > 0.8:
            out.append({"i": len(out), "text": " ".join(x["text"] for x in cur).strip(),
                        "start": cur[0]["start"], "end": cur[-1]["end"]})
            cur = []
    return out


def named(text, names):
    """The profile's names that appear in a sentence, matched on whole words, case-insensitive."""
    low = f" {re.sub(r'[^a-z0-9 ]+', ' ', text.lower())} "
    return [n["name"] for n in names if f" {re.sub(r'[^a-z0-9 ]+', ' ', n['name'].lower()).strip()} " in low]


NOT_NAMES = {"i", "i'm", "i'll", "i've", "i'd", "ai", "ok"}
# Common words a transcriber capitalises where it heard a new sentence but wrote no full stop ("every day,
# This is", "hard Can you"). ponytail: a fixed stopword list; a name that is also a common word ("Notion",
# "Linear") is still found, a common word missing here still shows up.
COMMON = set("""a about after again all also am an and any are as at back be because been before being both but by
can can't could did didn't do does doesn't don't down each even every first for from get go going gonna got had has
have he her here hey him his how if in into is isn't it it's its just know let let's like look make maybe me more
most my new next no not now of oh okay on once one only or other our out over really right said say says see she
should so some still such sure take than thank thanks that that's the their them then there there's these they
they're thing things think this those though through to today too try two um uh up us use very want was way we
we're well were what what's when where which while who why will with would yeah yes yet you you'll you're your
check""".split())


def found_names(beats):
    """Words written with a capital letter anywhere but a sentence's first word: the products, tools and
    people said, when the profile's names question was left blank. ponytail: a capital-letter heuristic,
    so it relies on the transcriber's casing (Whisper and Scribe capitalise names); a lower-case
    transcript finds none."""
    out = []
    for b in beats:
        for w in re.findall(r"[A-Za-z][\w'-]*", b["text"])[1:]:
            w = w.strip("'-")
            if w[:1].isupper() and w.lower() not in NOT_NAMES | COMMON and w not in out:
                out.append(w)
    return out


def key():
    try:
        from ai_editor import keys
        return keys.get("typesafe")[0]
    except Exception:
        return None


def ask_jev(qs, edit_dir, canned=None):
    """Jev's answers, or {} when TypeSafe fails (a rejected key, an outage): picks stay null, as with no key."""
    from ai_editor import jev
    try:
        return jev.ask("A short talking-head video. Each question is one sentence of it.", qs,
                       key=key(), log_dir=edit_dir, canned=canned)
    except jev.JevError as e:
        print(f"{e}: picks left null, Claude routes from beats.json", file=sys.stderr)
        return {}


def prefer(style):
    """{route: 0-1}: the creator's graphics.kinds mix, each kind's share split over its routes. {} when the
    style has none or the blend did not take "graphics"."""
    from plan import graphics
    out = {}
    for k, v in (graphics(style or {}, "graphics").get("kinds") or {}).items():
        rs = KIND_ROUTES.get(k, ())
        for r in rs:
            out[r] = round(out.get(r, 0) + v / 100 / len(rs), 3)
    return out


def route(beats, edit_dir=None, canned=None, goal="", pref=None):
    """Adds "pick" and "p" to each beat. Jev when a key (or canned answers) exists, else null.
    pref (prefer()): every route but "none" is weighted by 1 + its share of the creator's mix, so her
    kinds of graphic win close calls; "none" is never pushed down."""
    if not canned and not key():
        print("no TypeSafe key: picks left null, Claude routes from beats.json", file=sys.stderr)
        for b in beats:
            b["pick"] = None
        return beats
    from ai_editor import jev
    qs = {f"s{b['i']}": jev.choice(
        "What should be on screen while `sentence` is said? Prefer what is real (a capture, a logo, a post) over "
        "a built card. Most sentences need nothing.", ROUTES,
        sentence=b["text"], named_things=", ".join(b["names"]) or "none", video_goal=goal or "not given")
        for b in beats}
    ans = ask_jev(qs, edit_dir, canned)
    for b in beats:
        a = ans.get(f"s{b['i']}") or {}
        probs = a.get("probabilities") or {}
        if pref and probs:
            w = {k: v * (1 + pref.get(k, 0)) if k != "none" else v for k, v in probs.items()}
            probs = {k: v / sum(w.values()) for k, v in w.items()}
        b["pick"] = (max(probs, key=probs.get) if pref and probs else a.get("choice")) or (max(probs, key=probs.get) if probs else None)
        b["p"] = round(probs.get(b["pick"], 0), 3) if b["pick"] else None
    return beats


def pick_highlight(blocks, said, edit_dir=None, canned=None):
    """The text block of a captured page that is the evidence for `said`."""
    # one sentence per option: the highlight sweeps a sentence, not a paragraph
    blocks = [x for b in blocks for x in re.split(r"(?<=[.!?])\s+", b) if len(x) > 15]
    if not blocks:
        return None
    toks = set(re.findall(r"[a-z0-9]+", said.lower()))
    ranked = sorted(blocks, key=lambda b: -len(toks & set(re.findall(r"[a-z0-9]+", b.lower()))))[:MAX_LINES]
    if not canned and not key():
        return None
    from ai_editor import jev
    opts = {f"line{i}": b for i, b in enumerate(ranked)}
    ans = ask_jev({"h": jev.choice("Which line of the page is the evidence for what the speaker says in `said`?",
                                   opts, said=said)}, edit_dir, canned).get("h") or {}
    probs = ans.get("probabilities") or {}
    best = ans.get("choice") or (max(probs, key=probs.get) if probs else None)
    return opts.get(best)


def demo():
    ws = [{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, t in
          enumerate("I built a router with Jev. It is 40 times faster than Claude. Follow me.".split())]
    bs = sentences(ws)
    assert [b["text"] for b in bs] == ["I built a router with Jev.", "It is 40 times faster than Claude.", "Follow me."]
    names = [{"name": "Jev"}, {"name": "Claude"}, {"name": "Claude Code"}]
    for b in bs:
        b["names"] = named(b["text"], names)
    assert bs[0]["names"] == ["Jev"] and bs[1]["names"] == ["Claude"] and bs[2]["names"] == []
    # the names question left blank: the sample take's own capitalised names are found, sentence starts are not
    sample = sentences([{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, t in enumerate(
        "I built a router with Jev that picks my Claude model. Jev is good at different things. If it's a small "
        "task, it'll automatically use the Haiku model. If it's harder, it'll use Opus. I'm sure AI helps.".split())])
    assert found_names(sample) == ["Jev", "Claude", "Haiku", "Opus"], found_names(sample)
    # the real-footage test: Whisper capitalised sentence starts it wrote no full stop before, and every one
    # read as a name ("YouTube, This, Can, It, And, You, Just, So")
    run_on = sentences([{"text": t, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, t in enumerate(
        "I edit my YouTube videos. So because it is open source, This is a new view and be like Oh, I don't like "
        "it Can you change it and It saves and You can just see it So you can add reels. And Just send it to Claude".split())])
    assert found_names(run_on) == ["YouTube", "Claude"], found_names(run_on)
    assert named(sample[1]["text"], [{"name": n} for n in found_names(sample)]) == ["Jev"]
    canned = {"s0": {"type": "choice", "probabilities": {"none": 0.1, "capture:shot": 0.8, "logo": 0.1}},
              "s1": {"type": "choice", "probabilities": {"none": 0.2, "capture:sticker": 0.7}},
              "s2": {"type": "choice", "probabilities": {"none": 0.9}}}
    r = route(bs, canned=canned)
    assert [b["pick"] for b in r] == ["capture:shot", "capture:sticker", "none"] and r[0]["p"] == 0.8, r
    assert not any(k.startswith("template:") for k in ROUTES)   # type cards were removed
    # her mix: 58% text cards (-> sticker) tips a close shot/sticker call to the sticker; a clear "none" stays
    pr = prefer({"graphics": {"kinds": {"text card": 55, "real screenshot": 40, "chart": 3}}})
    assert pr == {"capture:sticker": 0.78, "capture:shot": 0.2}, pr
    close = {"s0": {"type": "choice", "probabilities": {"none": 0.2, "capture:shot": 0.42, "capture:sticker": 0.38}},
             "s1": {"type": "choice", "probabilities": {"none": 0.8, "capture:sticker": 0.2}}}
    r = route([dict(b) for b in bs[:2]], canned=close, pref=pr)
    assert [b["pick"] for b in r] == ["capture:sticker", "none"], r
    assert prefer({"graphics": {"kinds": {"chart": 100}}, "blend": {"take": ["captions"]}}) == {}
    hl = pick_highlight(["Pricing starts at $5.", "Jev answers in 40 ms, 200x faster than a frontier model."],
                        "it's 40 to 200 times faster", canned={"h": {"type": "choice", "probabilities": {"line0": 0.9}}})
    assert hl.startswith("Jev answers"), hl   # ranked by shared words first, so line0 is the Jev line
    # a failed request (rejected key, outage) leaves every pick null instead of a traceback
    from ai_editor import jev
    old = jev._post
    try:
        def post(body, key, tries=5):
            raise jev.JevError("TypeSafe HTTP 401: bad key", 401)
        jev._post = post
        globals()["key"], real_key = (lambda: "ts-bad"), key
        r = route([dict(b) for b in bs], goal="")
        assert [b["pick"] for b in r] == [None, None, None], r
        assert pick_highlight(["Jev answers in 40 ms, 200x faster."], "40 times faster") is None
    finally:
        jev._post, globals()["key"] = old, real_key
    print("route ok")


def main():
    a = sys.argv[1:]
    if a == ["demo"]:
        return demo()
    if len(a) == 2 and a[0] == "beats":
        edit = Path(a[1])
        src = edit / "captions.json" if (edit / "captions.json").exists() else edit / "words.json"
        words = [w for w in json.loads(src.read_text(encoding="utf-8")) if w.get("type", "word") == "word" and w["text"].strip()]
        from ai_editor import profile
        prof = profile.load()
        beats = sentences(words)
        names = [n if isinstance(n, dict) else {"name": n} for n in prof.get("names") or []]
        have = {n["name"].lower() for n in names}
        extra = [w for w in found_names(beats) if w.lower() not in have]
        if extra:
            print(f"names in the words, not in the profile: {', '.join(extra)} (add a domain for any that is not "
                  "famous: profile.py set names)")
        for b in beats:
            b["names"] = named(b["text"], names + [{"name": w} for w in extra])
        st = edit / "style.json"
        pref = prefer(json.loads(st.read_text(encoding="utf-8"))) if st.exists() else {}
        if pref:
            print("the creator's mix: " + ", ".join(f"{k} {v:.0%}" for k, v in sorted(pref.items(), key=lambda kv: -kv[1])))
        route(beats, edit, goal=prof.get("goal", ""), pref=pref)
        (edit / "beats.json").write_text(json.dumps(beats, indent=1), encoding="utf-8")
        for b in beats:
            print(f"{b['start']:6.2f}  {str(b.get('pick')):20}  {b['text']}" + (f"   [{', '.join(b['names'])}]" if b["names"] else ""))
        print(f"-> {edit / 'beats.json'}")
    elif len(a) == 4 and a[0] == "highlight":
        blocks = json.loads((Path(a[1]) / a[2]).read_text(encoding="utf-8") if not Path(a[2]).exists() else Path(a[2]).read_text(encoding="utf-8"))
        best = pick_highlight(blocks, a[3], Path(a[1]))
        if best is None:
            print("no TypeSafe key: pick the evidence line from these blocks:\n" + "\n".join(f"- {b}" for b in blocks))
        else:
            print(best)
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
