#!/usr/bin/env python3
"""The cut as text: paper-edit.md (for Claude's read-through) and cut-check.html
(for the user to approve). build_timeline.py calls write_all(); run this directly
to rebuild both from an edit folder:

    python3 preview_cut.py <edit_dir> [--no-open]

Run directly, it also opens cut-check.html in the browser once cut.mp4 exists, so the user always
gets the page (--no-open to skip).

A token counts as removed unless build_timeline.is_kept() says it plays, the same
rule verify_cut.py and words.json use. A removed word that no spans.json entry
asked for was trimmed by a pause cut: that is a clipped word, and it is flagged.
"""
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_timeline import is_kept, load_fitted  # noqa: E402

PARA_GAP_S = 1.2     # a pause this long starts a new paragraph in the page
SHOW_GAP_S = 0.5     # a pause this long gets a marker showing what it became


def kept_len(a, b, spans):
    return sum(max(0.0, min(b, s["end"]) - max(a, s["start"])) for s in spans)


def label(toks, cuts, spans):
    """[(token, cut index or None, removed?)]"""
    out = []
    for t in toks:
        mid = (t["start"] + t["end"]) / 2
        ci = next((i for i, c in enumerate(cuts) if c["start"] <= mid <= c["end"]), None)
        gone = not is_kept(t, spans)
        out.append((t, ci, gone))
    return out


def paper_edit(lab, cuts, dur, final, words_only=False):
    kept, prev = [], None
    for t, ci, gone in lab:
        if gone:
            if ci is not None and ci != prev:
                kept.append(f"<<{ci}>>")
            prev = ci
        else:
            kept.append(t["text"].strip())
            prev = None
    clipped = [t["text"] for t, ci, gone in lab if gone and ci is None]
    lines = ["# Paper edit", "",
             (f"- words only, pauses not counted: source {dur:.1f}s, cut {final:.1f}s" if words_only
              else f"- source {dur:.1f}s, cut {final:.1f}s, {dur - final:.1f}s removed"),
             f"- {len(cuts)} cuts from spans.json", ""]
    if clipped:
        lines += [f"- **CLIPPED by a pause cut, not asked for:** {' '.join(clipped)}", ""]
    lines += ["## What plays", "", "`<<n>>` marks where cut n was removed.", "",
              " ".join(kept), "", "## Cuts", ""]
    for i, c in enumerate(cuts):
        lines.append(f"- C{i} {c['start']:.2f}-{c['end']:.2f}s `{c['kind']}` "
                     f"({c['confidence']}): {c['evidence']}" + (f"  _({c['note']})_" if c.get("note") else ""))
    return "\n".join(lines) + "\n"


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cut check</title>
<style>
:root {{ --bg:#fbfaf7; --ink:#1d1d1b; --mute:#8a877f; --cut:#b3261e; --flag:#f3d36b; --line:#e6e3dc; }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#161614; --ink:#ecebe6; --mute:#8d8a82; --cut:#ff8a80; --flag:#7a6420; --line:#2c2b28; }} }}
:root[data-theme="dark"] {{ --bg:#161614; --ink:#ecebe6; --mute:#8d8a82; --cut:#ff8a80; --flag:#7a6420; --line:#2c2b28; }}
body {{ background:var(--bg); color:var(--ink); margin:0;
  font:18px/1.7 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
main {{ max-width:760px; margin:0 auto; padding:32px 16px 80px; }}
h1 {{ font-size:22px; margin:0 0 4px; }}
.stats {{ color:var(--mute); font-size:15px; margin-bottom:20px; }}
.legend {{ font-size:14px; color:var(--mute); border-top:1px solid var(--line);
  border-bottom:1px solid var(--line); padding:8px 0; margin-bottom:24px; }}
video {{ width:100%; max-height:60vh; background:#000; border-radius:8px; margin-bottom:20px; }}
p {{ margin:0 0 1em; }}
del {{ color:var(--cut); text-decoration-thickness:2px; opacity:.75; }}
del.check {{ background:var(--flag); opacity:1; }}
del.clip {{ background:var(--cut); color:var(--bg); opacity:1; }}
sup {{ font-size:11px; color:var(--mute); margin-right:2px; }}
.pause {{ font-size:12px; color:var(--mute); white-space:nowrap; }}
</style></head><body><main>
<h1>Cut check</h1>
<div class="stats">{stats}</div>
{video}
<div class="legend">Normal text plays. <del>Struck text</del> is cut.
<del class="check">Highlighted</del> cuts are judgement calls worth a second look.
Small grey marks show long pauses and what they were shortened to.
To keep something, say "keep" and quote the line.</div>
{body}
</main></body></html>
"""


def cut_check(lab, cuts, spans, dur, final, has_video):
    paras, cur, run = [], [], None   # run = [cut index, [texts], css]

    def flush():
        nonlocal run
        if run:
            ci, texts, cls = run
            c = cuts[ci] if ci is not None else None
            tip = (f"{c['kind']}: {c.get('note') or ''}" if c else "clipped by a pause cut")
            tag = f"<sup>{c['kind'].replace('_', ' ')}</sup>" if c else "<sup>clipped</sup>"
            cur.append(f'{tag}<del class="{cls}" title="{html.escape(tip)}">'
                       f'{html.escape(" ".join(texts))}</del>')
            run = None

    prev, prev_gone = None, True
    for t, ci, gone in lab:
        if prev is not None:
            gap = t["start"] - prev["end"]
            if gap >= SHOW_GAP_S and not gone and not prev_gone:
                flush()
                cur.append(f'<span class="pause">[{gap:.1f}s &rarr; '
                           f'{kept_len(prev["end"], t["start"], spans):.1f}s]</span>')
            if gap >= PARA_GAP_S and cur:
                flush()
                paras.append(" ".join(cur))
                cur = []
        prev, prev_gone = t, gone
        text = t["text"].strip()
        if not gone:
            flush()
            cur.append(html.escape(text))
            continue
        c = cuts[ci] if ci is not None else None
        cls = "clip" if c is None else ("check" if c["confidence"] == "low" or c["kind"] == "redundant" else "")
        if run and run[0] == ci:
            run[1].append(text)
        else:
            flush()
            run = [ci, [text], cls]
    flush()
    if cur:
        paras.append(" ".join(cur))
    kinds = {}
    for c in cuts:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    stats = (f"{dur:.1f}s raw &rarr; {final:.1f}s cut ({dur - final:.1f}s removed). "
             + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in sorted(kinds.items())))
    video = '<video src="cut.mp4" controls playsinline></video>' if has_video else ""
    return PAGE.format(stats=stats, video=video,
                       body="\n".join(f"<p>{p}</p>" for p in paras))


def write_all(d, toks, cuts, spans, dur, final):
    d = Path(d)
    lab = label(toks, cuts, spans)
    (d / "paper-edit.md").write_text(paper_edit(lab, cuts, dur, final), encoding="utf-8")
    (d / "cut-check.html").write_text(cut_check(lab, cuts, spans, dur, final,
                                                (d / "cut.mp4").exists()), encoding="utf-8")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-open"]
    if len(args) != 1:
        sys.exit(__doc__)
    d = Path(args[0])
    rep = json.loads((d / "report.json").read_text(encoding="utf-8"))
    toks = [t for t in load_fitted(d) if t.get("type") in ("word", "audio_event")]
    write_all(d, toks, rep["model_cuts"], json.loads((d / "decisions.json").read_text(encoding="utf-8")),
              rep["duration"], rep["final_s"])
    print(d / "paper-edit.md")
    print(d / "cut-check.html")
    if "--no-open" not in sys.argv and (d / "cut.mp4").exists():
        import webbrowser
        webbrowser.open((d / "cut-check.html").resolve().as_uri())
