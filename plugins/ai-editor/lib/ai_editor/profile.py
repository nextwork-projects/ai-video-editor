#!/usr/bin/env python3
"""The user's editing profile: the start skill's answers, asked once and reused on every video.

    python3 profile.py show                       the profile as JSON
    python3 profile.py missing                    the intake questions still unanswered, one id per line
    python3 profile.py set <key.path>=<value> ...  several answers in one call, one line out;
                                                  each value parsed as JSON if it can be
    python3 profile.py set <key.path> <value>     one answer (the older form)
    python3 profile.py defaults                   "use the defaults": every unanswered question saved as its
                                                  first option (audience and names too), so nothing is asked again
    python3 profile.py style <edits/NAME> [--out F] [--from <style.json>] [--as mine|defaults|@handle]
                                                  blend the profile's creators into edits/NAME/style.json
                                                  (no creators: the default style, DEFAULT_STYLE). --from: that one
                                                  saved style instead (an edit-like-<handle> skill passes it).
                                                  "source" records the creator style.json(s) used, so a review note
                                                  can be saved on that style (styleskill.py). --as: the style the
                                                  user picked for this one video (the home page's as=): @handle
                                                  copies that creator, defaults no creator, mine the profile's.
                                                  Never written to profile.json: only Make default changes it.
                                                  No --as or --from over a style.json of another style: kept as it is
    python3 profile.py demo                       self-check

File: ~/.ai-video-editor/profile.json (AI_EDITOR_HOME overrides). Shape:

  {"platform": "tiktok", "aspect": "9:16",
   "creators": [{"handle": "somecreator", "take": ["captions", "pace", "visuals"]}],
   "audience": "developers who use Claude", "goal": "follow + comment for the guide",
   "brand": {"colors": ["#F2EEE6", "#E5482C"], "font": "Archivo", "logo": "/path/logo.svg"}  or {"use_creator": true},
   "assets_dir": "/path/to/my/screenshots",
   "broll": {"travel": "/path/to/Drive/B-roll/Travel"},  b-roll libraries by type of video (broll.py)
   "names": [{"name": "Claude", "domain": "claude.com"}],
   "avoid": {"emoji": true, "stock": true, "icons": true, "colors": ["#7B61FF"], "notes": ""},
   "captions": {"on": true, "style": "creator"},     style: creator | plain | bold | karaoke | minimal
   "sound": {"sfx": true, "music": false},           music: unset follows the style (a bed when the creator uses one)
   "behind": true,                                     cards sit behind the speaker (style-edit matte.py)
   "cloud_cleanup": true,                              delete uploaded footage from GitHub / S3 after a cloud render
   "render": "laptop",                                 where every render goes (laptop | modal | github | lambda), asked once
   "loudness": "leave",                                the take's own level: leave | normalize, asked once
   "past_edit": true}                                  learned from a raw take and their posted cut (taste learn.py); false: declined

Look order (plan.py): the profile's brand kit > the copied creators' measured style.json > the
`editorial` preset. No creator: DEFAULT_STYLE (style-edit references/plan.md "No creator").
`set` of a style answer and `defaults` also refresh the my-style skill (styleskill.py). Stdlib only.
"""
import colorsys
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import presets  # noqa: E402

HOME = Path(os.environ.get("AI_EDITOR_HOME", Path.home() / ".ai-video-editor"))
# Style questions are asked once, at setup. Video questions belong to each video, asked by start.
STYLE_QUESTIONS = ("platform", "creators", "liked_videos", "brand", "assets_dir", "avoid", "captions", "sound", "behind",
                   "past_edit")
VIDEO_QUESTIONS = ("audience", "names")
QUESTIONS = STYLE_QUESTIONS + VIDEO_QUESTIONS
DEFAULTS = {"platform": "tiktok", "aspect": "9:16", "creators": [], "liked_videos": [], "brand": {"use_creator": True},
            "assets_dir": "", "names": [], "avoid": {"emoji": True, "stock": True, "icons": True, "colors": []},
            "captions": {"on": True, "style": "creator"}, "sound": {"sfx": True},   # no "music": the style decides until the user does
            "behind": False,   # unanswered: off, so no plan needs the cutout step until the user says yes
            "past_edit": False,
            # the video questions' first options: used without asking, said on the review page, changed by a word
            "audience": "people curious about the topic", "goal": "follow"}
ASPECT = {"tiktok": "9:16", "reels": "9:16", "shorts": "9:16", "youtube": "16:9"}
# Fonts every AI tool reaches for, and the default geometric / neo grotesks that read as AI-made as a
# heading. Swapped for the preset's face unless the user's brand names them.
GENERIC_FONTS = {"inter", "roboto", "poppins", "montserrat", "open sans", "arial", "helvetica", "archivo", "geist",
                 "manrope", "dm sans", "plus jakarta sans", "outfit", "space grotesk", "satoshi", "general sans", "sora", "urbanist"}
# Flat saturated colour grounds read as AI-made: only the user's own brand kit may name one.
FLAT_GROUND_PRESETS = ("poster-red", "poster-green", "poster-blue")
# The caption answers are the built-in caption presets (plugins/ai-editor/presets/captions/*.json, presets.py).
# plain: the no-creator default and an answer of its own. White TikTok Sans (SIL OFL, on Google Fonts) at 4.2% of the
# long side, weight 600, as spoken (no forced case), no stroke, box, shadow, highlight or animation: each page cuts on.
# plan.py's contrast ladder adds a soft shadow first, and more only where the footage behind a page needs it.
CAPTION_STYLES = {k: v for k, v in presets.built_in().items() if k in presets.ORDER}   # never the user's files
PLAIN_CAPTIONS = CAPTION_STYLES["plain"]


def path():
    return HOME / "profile.json"


def load():
    p = path()
    return {**DEFAULTS, **(json.loads(p.read_text(encoding="utf-8")) if p.exists() else {})}


def save(prof):
    HOME.mkdir(parents=True, exist_ok=True)
    raw = dict(prof)   # only what was answered: missing() reads the file
    raw["aspect"] = ASPECT.get(raw.get("platform"), raw.get("aspect", "9:16"))
    path().write_text(json.dumps(raw, indent=1), encoding="utf-8")
    return path()


def save_defaults():
    """Every unanswered question saved as its first option: the answer "use the defaults" (or a style step
    finished on the recommended options) is an answer, so start never asks it again. The video questions too:
    audience "people curious about the topic" + goal "follow", names [] (found in what they say). A saved answer
    is kept, so the next video asks nothing."""
    have = json.loads(path().read_text(encoding="utf-8")) if path().exists() else {}
    new = [q for q in QUESTIONS if q not in have]
    extra = {"goal": DEFAULTS["goal"]} if "audience" in new and "goal" not in have else {}
    save({**have, **{q: DEFAULTS[q] for q in new}, **extra})
    return new


def missing(group=QUESTIONS):
    """The intake questions in `group` with no saved answer yet."""
    have = json.loads(path().read_text(encoding="utf-8")) if path().exists() else {}
    return [q for q in group if q not in have]


# ---------- colour ----------
def rgb(hexs):
    h = hexs.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def hls(hexs):
    return colorsys.rgb_to_hls(*rgb(hexs))


def lum(hexs):
    r, g, b = rgb(hexs)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def is_hex(s):
    return isinstance(s, str) and re.fullmatch(r"#?[0-9a-fA-F]{6}|#?[0-9a-fA-F]{3}", s) is not None


def generic_colour(hexs):
    """The AI-default accents: saturated purple to blue, and neon on near-black."""
    h, l, s = hls(hexs)
    return s > 0.45 and 0.5 < l < 0.85 and 225 <= h * 360 <= 290


def near(a, b, tol=0.12):
    return sum((x - y) ** 2 for x, y in zip(rgb(a), rgb(b))) ** 0.5 < tol


# The keys the renderer reads (remotion/src/look.tsx). A teardown's look.json-style notes are dropped.
LOOK_KEYS = ("preset", "ground", "ink", "muted", "accent", "accent_ink", "line", "surface", "radius", "shadow", "font",
             "font_display", "font_serif", "weight", "weight_display", "tracking", "case", "texture", "texture_amount", "decor")


def creator_look(style):
    """A look from a creator's measured style.json: graphics.palette (hex + share) and captions.font_match.
    Ground: the most used light palette colour (paper) or, with none, editorial-dark. Accent: the most
    saturated palette colour, when there is one. Nothing measured: {} (the preset stands)."""
    out = {k: v for k, v in (style.get("look") or {}).items() if k in LOOK_KEYS}
    pal = [p["hex"] for p in sorted((style.get("graphics") or {}).get("palette") or [], key=lambda p: -p.get("pct", 0))
           if is_hex(p.get("hex"))]
    if pal and "ground" not in out:
        light = [c for c in pal if lum(c) > 0.72 and hls(c)[2] < 0.35]
        if light:
            out["ground"] = light[0]
        elif lum(pal[0]) < 0.15:
            out.setdefault("preset", "editorial-dark")
    sat = [c for c in pal if hls(c)[2] > 0.5 and 0.25 < hls(c)[1] < 0.75]
    if sat and "accent" not in out:
        out["accent"] = sat[0]
    font = ((style.get("captions") or {}).get("font_match") or "").strip()
    if font and (style.get("captions") or {}).get("style") not in presets.captions() and font.lower() not in GENERIC_FONTS and "font" not in out:
        out["font"] = font
    return out


def brand_look(brand):
    """A look from the profile's brand kit: colours (lightest = ground when light enough, the most
    saturated = accent, the darkest = ink) and fonts."""
    out = {}
    cols = [c if c.startswith("#") else "#" + c for c in (brand.get("colors") or []) if is_hex(c)]
    if cols:
        by_l = sorted(cols, key=lum)
        if lum(by_l[-1]) > 0.72:
            out["ground"] = by_l[-1]
        if lum(by_l[0]) < 0.2:
            out["ink"] = by_l[0]
        sat = sorted(cols, key=lambda c: -hls(c)[2])
        if hls(sat[0])[2] > 0.3:
            out["accent"] = sat[0]
    for k in LOOK_KEYS:
        if k not in out and brand.get(k):
            out[k] = brand[k]
    if brand.get("font") and not brand.get("font_display"):
        out["font_display"] = brand["font"]
    return out


def resolve_look(style, prof=None, warn=print):
    """plan.json "look": profile brand kit > style.json (creator, with taste.json merged in) > editorial.
    The anti-generic rules apply to everything that did not come from the user's own brand kit."""
    prof = prof or {}
    brand = prof.get("brand") or {}
    look = {"preset": "editorial", **creator_look(style)}
    if look.get("preset") == "glass" and not (style.get("look") or {}).get("preset") == "glass":
        look["preset"] = "editorial"
    own = brand_look(brand) if not brand.get("use_creator") or brand.get("colors") or brand.get("font") else {}
    for k in ("accent", "ground"):
        if k in look and k not in own and generic_colour(look[k]):
            warn(f"look: {k} {look[k]} is the purple-blue AI default; using the preset's")
            look.pop(k)
    if look.get("preset") in FLAT_GROUND_PRESETS and look["preset"] != brand.get("preset"):
        warn(f"look: {look['preset']} is a flat saturated ground, the AI-made look; using neutral")
        look["preset"] = "neutral"
    if look.get("preset") == "glass" and "glass" != brand.get("preset"):
        warn("look: the dark glass panel with a neon accent is the AI default; using editorial")
        look["preset"] = "editorial"
    for k in ("font", "font_display"):
        if (look.get(k) or "").lower() in GENERIC_FONTS and k not in own:
            warn(f"look: {look[k]} is the font every AI tool uses; using the preset's")
            look.pop(k)
    for c in (prof.get("avoid") or {}).get("colors") or []:
        if not is_hex(c):
            continue
        c = c if c.startswith("#") else "#" + c
        for k in ("accent", "ground", "ink"):
            if k in look and k not in own and near(look[k], c):
                warn(f"look: {k} {look[k]} is close to {c}, which the profile avoids; using the preset's")
                look.pop(k)
    look.update(own)
    return look


# ---------- no creator: the default style ----------
# The recommended answer when no creator is named. Overlay-first and smooth (PRINCIPLES.md "Smooth before varied"):
# the smooth personality, push zooms eased 0.8 s each way on sine.inOut (a camera move, never a step), captions the
# footage decides the treatment of (plan.py's contrast ladder). Numbers: the median of the measured styles the editor
# was built against (the style.json example in style-edit references/contracts.md, the test teardown, one 7-video
# creator teardown): scale 1.18 / 1.18 / 1.2, 6 / 9.5 / 10 zooms a minute; median shot 2.4 / 2.4 / 3.98 s;
# 1 / 3 / 3 words a caption, 4.7 / 5.5 / 6.5% type, y 62 / 66 / 75%, lower case in all three. Captions are the owner's
# plain look (PLAIN_CAPTIONS), smaller than the measured median; words a page and y stay measured. The three measured
# punch zooms; the default pushes, because check.py render judges a punch by its one-frame travel. The zoom is the
# style page's Smooth preset (presets.py: a 0.8 s push at scale 1.18, a change at least every 5 s); cards land "Sometimes" (at most 4 a minute, plan.py thin_cards).
# max_hold_s: a sentence longer than this still gets a zoom change (plan.py place_zooms), so nothing holds still
# past check.py's 6 s.
DEFAULT_STYLE = {
    "handle": "default",
    "pace": {"median_shot_s": 2.4, "max_pause_s": 0.25},
    "motion": "smooth",
    "zoom": dict(presets.ZOOM["smooth"]["zoom"]),
    "cards": {"per_min": presets.CARDS["sometimes"]["per_min"]},
    "captions": {"present": True, "words_per_caption": 3, "y_pct": 66, **PLAIN_CAPTIONS},
}


def default_style(prof=None):
    """DEFAULT_STYLE with the profile's caption and sound answers laid over."""
    return answers(json.loads(json.dumps(DEFAULT_STYLE)), prof or {})


# A cut kind -> style-edit's scene transition: the same map and 5% floor as creator-teardown visual.py
# TRANSITION / transitions_of (hard, jump and zoom-punch cuts have none).
CUT_TRANSITION = {"whip": "push", "match": "match", "mask": "wipe", "dissolve": "fade"}


def fill_transitions(style, warn=print):
    """A style.json from a teardown made before visual.py wrote "transitions": derive them from the measured
    pace.cut_kinds ([] for a creator who only cuts). No cut kinds measured: leave style-edit's default and,
    for a creator's style, say re-running the teardown gets them. Never guessed."""
    if "transitions" in style or style.get("handle", "default") == "default":
        return style
    ck = (style.get("pace") or {}).get("cut_kinds")
    if ck:
        style["transitions"] = [CUT_TRANSITION[k] for k, v in sorted(ck.items(), key=lambda kv: -kv[1])
                                if k in CUT_TRANSITION and v >= 5]
    elif ck is None:
        warn(f"style.json for {style['handle']} has no \"transitions\" and no measured cut kinds, so scenes use "
             "match / iris; re-run the creator-teardown (visual.py) to get the creator's transitions")
    return style


# ---------- blending creators ----------
# The same keys as creator-teardown editplan.py PARTS: camera goes with pace, face and hook with visuals, and sound
# is its own part (claimed by nobody in the profile, so it comes from the first creator, as every unclaimed part does).
PARTS = {"captions": ("captions",), "pace": ("pace", "zoom", "cuts", "motion", "transitions", "camera"),
         "visuals": ("graphics", "look", "layout", "cats", "events", "face", "hook", "per_min", "first_in_s", "gap_s", "behind",
                     "cards", "card_kinds", "grade"),
         "sound": ("sound", "sfx")}
HOME_TAKE = {"captions", "pace", "graphics", "sound"}   # the home page's four boxes (home.py TAKE)


def heal(style, path=None):
    """A <h>-mine the home page wrote before its "graphics" box also sent entrance motion and layout: those come
    back from the measured creator-teardowns/<h>/style.json beside it, so the cards land where and how she lands them.
    ponytail: told apart by its take alone (only home boxes, graphics without entrances/layout); a quick-mode pick of
    exactly those parts gets them too. Stamp the source on the take if that ever matters."""
    take = (style.get("blend") or {}).get("take")
    p = path and Path(path).resolve()
    if not (p and take and "graphics" in take and set(take) <= HOME_TAKE and p.parent.name.endswith("-mine")):
        return style
    full = p.parent.with_name(p.parent.name[:-5]) / "style.json"
    if not full.is_file():
        return style
    m = json.loads(full.read_text(encoding="utf-8"))
    g = m.get("graphics") or {}
    style["graphics"] = {**(style.get("graphics") or {}),
                         **{k: g[k] for k in ("entrances", "exits", "secondary_motion", "ease_in_s", "layout") if k in g}}
    style.update({k: m[k] for k in ("face", "layout") if k in m})
    style["blend"] = {**style["blend"], "take": list(take) + ["entrances", "layout"]}
    return style


SAMPLE_KEYS = ("card_kinds", "behind", "graphics", "cats", "format")   # what makes a sample style's cards its own


def like_sample(style, handle):
    """A style the user made themselves (own-<x>, e.g. imported from their own card-edit skill) that names a sample's
    format (sample-<x>: own-card-edit -> sample-card-edit) but carries no card settings takes the sample's: its card
    kinds (real pictures only), cards behind the speaker, rate, place and motion. Its own keys always win. A skill style
    ("skill" set) takes nothing: its skill decides the cards.
    ponytail: matched by name; a style page "format" pick would be the general way."""
    base = re.sub(r"-\d+$", "", handle or "")
    src = Path(__file__).resolve().parents[2] / "presets" / "styles" / ("sample-" + base[4:]) / "style.json"
    if not base.startswith("own-") or style.get("card_kinds") or style.get("skill") or not src.is_file():
        return style
    sample = json.loads(src.read_text(encoding="utf-8"))
    return {**{k: sample[k] for k in SAMPLE_KEYS if k in sample}, **style}


def creator_style(root, handle):
    """(style, path) for one profile creator: the parts the user ticked (<h>-mine, the same file its edit-like skill
    and its corrections use) when there is one, else the whole measured <h>/style.json. (None, path) when neither."""
    d = Path(root) / "creator-teardowns"
    for p in (d / f"{handle}-mine" / "style.json", d / handle / "style.json"):
        if p.is_file():
            return like_sample(heal(json.loads(p.read_text(encoding="utf-8")), p), handle), p
    return None, d / handle / "style.json"


def blend(styles, creators, prof=None):
    """One style.json from several creators: each creator gives the parts listed in its `take`
    (captions, pace, visuals). A part nobody claims comes from the first creator. Then the profile's
    caption and sound answers lay over it."""
    prof = prof or {}
    order = [c["handle"] for c in creators if c.get("handle") in styles] or list(styles)
    out = {"handle": "+".join(order), "blend": {}}
    for part, keys in PARTS.items():
        src = next((c["handle"] for c in creators if c.get("handle") in styles and part in (c.get("take") or [])),
                   order[0] if order else None)
        if not src:
            continue
        out["blend"][part] = src
        for k in keys:
            if k in styles[src]:
                out[k] = json.loads(json.dumps(styles[src][k]))
    if order:
        out.setdefault("aspect", styles[order[0]].get("aspect"))
    return answers(out, prof)


def answers(out, prof):
    """The profile's caption and sound answers over a style."""
    cap = prof.get("captions") or {}
    if cap.get("on") is False:
        out["captions"] = {**out.get("captions", {}), "present": False}
    elif cap.get("style") in CAPTION_STYLES:
        out["captions"] = {**out.get("captions", {}), **CAPTION_STYLES[cap["style"]]}
    if (prof.get("sound") or {}).get("sfx") is False:
        out["sfx"] = False
    return out


def write_style(edit_dir, root=Path("."), out=None, src=None, as_=None):
    prof = load()
    if as_ and as_ != "mine":   # this video's pick, over the profile in memory only
        prof = {**prof, "creators": [] if as_ == "defaults" else [{"handle": as_.lstrip("@"), "take": ["captions", "pace", "visuals"]}]}
    styles, paths = {}, []
    for c in [] if src else prof.get("creators") or []:
        st, p = creator_style(root, c["handle"])
        if st is not None:
            styles[c["handle"]] = st
            paths.append(str(p.resolve()))
        else:
            print(f"warning: no {p}; run creator-teardown on @{c['handle']} first", file=sys.stderr)
    if src:
        if not Path(src).is_file():
            sys.exit(f"ERROR: no {src}")
        style, paths = answers(like_sample(heal(json.loads(Path(src).read_text(encoding="utf-8")), src),
                                           Path(src).resolve().parent.name), prof), [str(Path(src).resolve())]
        style.setdefault("handle", Path(src).resolve().parent.name)
    elif not prof.get("creators"):
        style = default_style(prof)
    elif not styles:
        sys.exit("ERROR: no creator style.json found for the profile's creators")
    else:
        style = blend(styles, prof["creators"], prof)
    if paths:
        style["source"] = paths
    clip = Path(edit_dir) / "clip.json"
    if clip.exists() and json.loads(clip.read_text(encoding="utf-8")).get("audio_only"):   # a podcast clip: the words are the picture
        style["captions"] = {**style.get("captions", {}), "present": True}
    out = Path(out or Path(edit_dir) / "style.json")
    if not (as_ or src):   # only the window's pick (--as, seed_style) or --from changes the style an edit already has
        try:
            had = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            had = None
        if isinstance(had, dict) and (had.get("handle") or "default") != (style.get("handle") or "default"):
            print(f"kept {out}: it is {had.get('handle') or 'default'}, the style picked for this video "
                  "(--as changes it)", file=sys.stderr)
            return out, had
    out.parent.mkdir(parents=True, exist_ok=True)   # start writes the style before cut makes edits/<name>/
    out.write_text(json.dumps(style, indent=1), encoding="utf-8")
    return out, style


def picked(style, as_):
    """None when style.json is the style the user picked for the video (the home page's as=: @handle, defaults or
    mine), else the handle it holds instead. An as= of anything else: None (nothing to compare)."""
    if as_ == "mine":
        cs = [c.get("handle") for c in load().get("creators") or [] if c.get("handle")]
        want = "+".join(cs) if cs else "default"
    else:
        want = "default" if as_ == "defaults" else as_[1:] if isinstance(as_, str) and as_.startswith("@") else None
    got = (style or {}).get("handle") or "default"
    return None if want is None or got == want else got


def set_pairs(prof, pairs):
    """Each (dotted key, text) into prof; the text is parsed as JSON if it can be."""
    for key, text in pairs:
        try:
            val = json.loads(text)
        except json.JSONDecodeError:
            val = text
        *head, last = key.split(".")
        cur = prof
        for k in head:
            cur = cur.setdefault(k, {})
        cur[last] = val
    return prof


def demo():
    global HOME
    with tempfile.TemporaryDirectory() as d:
        HOME = Path(d)
        assert missing() == list(QUESTIONS) and missing(VIDEO_QUESTIONS) == ["audience", "names"]
        save({"platform": "youtube", "creators": [{"handle": "a"}]})
        assert load()["aspect"] == "16:9" and "creators" not in missing() and "audience" in missing()
        # the real-footage test: setup finished on "use the defaults", which saved nothing, so start's
        # `missing --style` printed all 10 style ids and asked them again. Defaults are saved as answers
        assert save_defaults() == [q for q in QUESTIONS if q not in ("platform", "creators")]
        # the video questions take their first option too, so no video asks them (the owner: "too many questions")
        assert missing() == [] and load()["audience"] == "people curious about the topic" and load()["goal"] == "follow"
        assert load()["platform"] == "youtube" and load()["creators"] == [{"handle": "a"}], "answers kept"
        assert save_defaults() == [] and all(q in DEFAULTS for q in QUESTIONS)
        save({**json.loads(path().read_text(encoding="utf-8")), "audience": "developers", "goal": "comment"})
        assert save_defaults() == [] and load()["audience"] == "developers" and load()["goal"] == "comment", "kept"
        # no creators (the recommended answer): the default style is written, never an exit
        save({"creators": [], "captions": {"style": "karaoke"}})
        out, st = write_style(d, out=Path(d) / "style.json")
        assert out.exists() and st["zoom"]["per_min"] == presets.ZOOM["smooth"]["zoom"]["per_min"] and st["captions"]["effect"] == "karaoke", st
        assert json.loads(out.read_text(encoding="utf-8"))["handle"] == "default"
        assert picked({"handle": "default"}, "defaults") is None and picked({"handle": "default"}, "@sample-motion-design") == "default"
        assert picked({"handle": "sample-motion-design"}, "@sample-motion-design") is None and picked({}, "defaults") is None
        save({"creators": [], "captions": {"on": True, "style": "creator"}})   # the recommended answer: plain white TikTok Sans
        cap = write_style(d, out=Path(d) / "style.json")[1]["captions"]
        assert cap["font_match"] == "TikTok Sans" and cap["size_pct"] < 5.5 and 600 <= cap["weight"] <= 700, cap
        assert cap["color"] == "#FFFFFF" and not (cap["stroke"] or cap["box"] or cap["shadow"]) and cap["effect"] == "none", cap
        assert "font" not in creator_look(default_style()), "plain captions keep the cards' own font"
        # the recommended path passes the editor's own smoothness check: a push eased at least 0.8 s (check.py
        # PUSH_MIN_S), never a punch of 0.0 s that the render check reads as a one-frame snap
        assert st["zoom"]["kind"] == "push" and st["zoom"]["duration_s"] >= 0.8, st["zoom"]
        assert st["cards"] == {"per_min": 4}, "a new user's cards land Sometimes"
        # captions off in the profile, but an audio-only podcast clip keeps them: its words are the picture
        save({"captions": {"on": False}})
        (Path(d) / "clip.json").write_text(json.dumps({"audio_only": True}), encoding="utf-8")
        assert write_style(d, out=Path(d) / "style.json")[1]["captions"]["present"] is True
        (Path(d) / "clip.json").unlink()
        assert write_style(d, out=Path(d) / "style.json")[1]["captions"]["present"] is False
        # start runs `style edits/<name>` before cut has made the folder: it is created, exit 0
        r = subprocess.run([sys.executable, __file__, "style", str(Path(d) / "edits" / "new")],
                           capture_output=True, text=True, env=dict(os.environ, AI_EDITOR_HOME=d))
        assert r.returncode == 0 and (Path(d) / "edits" / "new" / "style.json").exists(), r.stderr
    styles = {"a": {"captions": {"size_pct": 4}, "zoom": {"per_min": 6}, "graphics": {"palette": [
                  {"hex": "#000000", "pct": 14}, {"hex": "#DEDACC", "pct": 8}, {"hex": "#E5482C", "pct": 3}]}, "transitions": ["push"]},
              "b": {"captions": {"size_pct": 7, "font_match": "Inter"}, "pace": {"median_shot_s": 1.2}, "transitions": []}}
    s = blend(styles, [{"handle": "a", "take": ["visuals"]}, {"handle": "b", "take": ["captions", "pace"]}],
              {"captions": {"style": "karaoke"}, "sound": {"sfx": False}})
    # a caption answer is a whole preset (presets.py): its type and size replace the creator's
    assert s["captions"] == {**styles["b"]["captions"], **CAPTION_STYLES["karaoke"]} and s["sfx"] is False, s
    assert s["blend"] == {"captions": "b", "pace": "b", "visuals": "a", "sound": "a"} and s["pace"]["median_shot_s"] == 1.2
    # a creator's measured captions stand unless the user picks plain; plain over a creator keeps its words a page
    assert blend(styles, [{"handle": "b"}], {})["captions"] == {"size_pct": 7, "font_match": "Inter"}
    pl = blend(styles, [{"handle": "b"}], {"captions": {"style": "plain"}})["captions"]
    assert pl["font_match"] == "TikTok Sans" and pl["size_pct"] == 4.2, pl
    assert s["transitions"] == [], s     # the pace creator's transitions come with pace (b only cuts)
    # a teardown older than "transitions": its measured cut kinds give them; with none measured, a note, no guess
    w = []
    assert fill_transitions({"handle": "x", "pace": {"cut_kinds": {"hard": 92, "jump": 8}}}, w.append)["transitions"] == []
    assert fill_transitions({"handle": "x", "pace": {"cut_kinds": {"hard": 70, "whip": 20, "mask": 3}}}, w.append)["transitions"] == ["push"]
    assert fill_transitions({"handle": "x", "transitions": ["fade"], "pace": {"cut_kinds": {"hard": 100}}}, w.append)["transitions"] == ["fade"]
    assert "transitions" not in fill_transitions({"handle": "x", "pace": {"cut_kinds": {}}}, w.append) and not w
    assert "transitions" not in fill_transitions(default_style(), w.append) and not w
    assert "transitions" not in fill_transitions({"handle": "x", "pace": {"median_shot_s": 2}}, w.append) and len(w) == 1, w
    assert "re-run" in w[0] and "visual.py" in w[0], w
    lk = resolve_look(s, {}, warn=lambda m: None)
    assert lk["ground"] == "#DEDACC" and lk["accent"] == "#E5482C" and "font" not in lk, lk    # Inter refused
    w = []
    lk = resolve_look({"look": {"accent": "#7B61FF", "preset": "glass"}}, {}, warn=w.append)
    assert "accent" not in lk and lk["preset"] == "editorial" and len(w) == 2, (lk, w)
    lk = resolve_look({}, {"brand": {"colors": ["#7B61FF", "#FFFFFF", "#111111"], "font": "Inter"}}, warn=w.append)
    assert lk["accent"] == "#7B61FF" and lk["ground"] == "#FFFFFF" and lk["font"] == "Inter", lk   # the user's own brand wins
    lk = resolve_look({"look": {"accent": "#E5482C"}}, {"avoid": {"colors": ["#E04A2E"]}}, warn=w.append)
    assert "accent" not in lk
    lk = resolve_look({"look": {"preset": "poster-green", "font_display": "Archivo"}}, {}, warn=w.append)
    assert lk["preset"] == "neutral" and "font_display" not in lk, lk     # flat ground and a default grotesk refused
    # several answers in one call: one line out, every value in place
    with tempfile.TemporaryDirectory() as d:
        env = dict(os.environ, AI_EDITOR_HOME=d, AI_EDITOR_SKILLS=str(Path(d) / "skills"))
        r = subprocess.run([sys.executable, __file__, "set", "platform=youtube", "sound.music=false",
                            'names=["Jev"]', "brand.url=https://x.io/?a=b"], capture_output=True, text=True, env=env)
        assert r.returncode == 0 and r.stdout.count("\n") == 2 and "my-style" in r.stdout, (r.stdout, r.stderr)
        assert "name: my-style" in (Path(d) / "skills" / "my-style" / "SKILL.md").read_text(encoding="utf-8")
        got = json.loads((Path(d) / "profile.json").read_text(encoding="utf-8"))
        assert got["platform"] == "youtube" and got["sound"] == {"music": False} and got["names"] == ["Jev"], got
        assert got["brand"]["url"] == "https://x.io/?a=b", got
        r = subprocess.run([sys.executable, __file__, "set", "audience", "builders"], capture_output=True,
                           text=True, env=env)
        assert r.returncode == 0 and json.loads((Path(d) / "profile.json").read_text(encoding="utf-8"))["audience"] == "builders"
        # the two forms mixed: the message names the argument that is not key=value
        r = subprocess.run([sys.executable, __file__, "set", "goal", "follow", "platform=youtube"], capture_output=True,
                           text=True, env=env)
        assert r.returncode == 1 and "'goal' is not key=value" in r.stderr, r.stderr
        # --from one saved style (an edit-like skill): its numbers, the profile's answers, and where it came from
        cs = Path(d) / "creator-teardowns" / "alice" / "style.json"
        cs.parent.mkdir(parents=True)
        cs.write_text('{"captions": {"size_pct": 6}}', encoding="utf-8")   # an older study: no "handle"
        r = subprocess.run([sys.executable, __file__, "style", str(Path(d) / "edits" / "v"), "--from", str(cs)],
                           capture_output=True, text=True, env=env)
        st = json.loads((Path(d) / "edits" / "v" / "style.json").read_text(encoding="utf-8"))
        assert r.returncode == 0 and st["source"] == [str(cs.resolve())] and st["captions"]["size_pct"] == 6, (r.stderr, st)
        assert st["handle"] == "alice" and f"from {cs.resolve()}" in r.stdout, r.stdout
        # one video's style pick (the home page's as=): that style for this edit, profile.json untouched
        before = (Path(d) / "profile.json").read_bytes()
        for pick_, want in (("@alice", "alice"), ("defaults", None)):
            r = subprocess.run([sys.executable, __file__, "style", "edits/w", "--as", pick_], capture_output=True, text=True,
                               env=env, cwd=d)
            st = json.loads((Path(d) / "edits" / "w" / "style.json").read_text(encoding="utf-8"))
            assert r.returncode == 0 and (st.get("source") == [str(cs.resolve())] if want else "source" not in st), (r.stderr, st)
            assert (Path(d) / "profile.json").read_bytes() == before, "a video's style pick never changes the profile"
        # prep (visual-prep, clip-editor) runs `style EDIT` with no --as: the picked style stays (QA round 4)
        subprocess.run([sys.executable, __file__, "style", "edits/w", "--as", "@alice"], capture_output=True, env=env, cwd=d)
        r = subprocess.run([sys.executable, __file__, "style", "edits/w"], capture_output=True, text=True, env=env, cwd=d)
        st = json.loads((Path(d) / "edits" / "w" / "style.json").read_text(encoding="utf-8"))
        assert r.returncode == 0 and st["handle"] == "alice" and "kept" in r.stderr, (r.stderr, st)
    # the parts the user ticked (<h>-mine) win over the whole study; an old home-page -mine gets her card motion and
    # layout back; camera, face, hook and sound reach the blend (they were dropped before)
    with tempfile.TemporaryDirectory() as d:
        full = {"handle": "h", "camera": {"pan_per_min": 4}, "face": {"y_pct": 28}, "sound": {"sfx_per_min": 2},
                "graphics": {"per_min": 5, "layout": {"zones_pct": {"top": 84}}, "entrances": [{"kind": "cut"}]}}
        for name, st in (("h", full), ("h-mine", {**full, "graphics": {"per_min": 5}, "face": None,
                                                    "blend": {"take": ["captions", "pace", "graphics", "sound"]}})):
            (Path(d) / "creator-teardowns" / name).mkdir(parents=True)
            (Path(d) / "creator-teardowns" / name / "style.json").write_text(json.dumps(st), encoding="utf-8")
        st, p = creator_style(d, "h")
        assert p.parent.name == "h-mine" and st["graphics"]["layout"]["zones_pct"]["top"] == 84, st
        assert st["face"] == {"y_pct": 28} and "entrances" in st["blend"]["take"], st
        b = blend({"h": st}, [{"handle": "h", "take": ["captions", "pace", "visuals"]}], {})
        assert b["camera"]["pan_per_min"] == 4 and b["sound"]["sfx_per_min"] == 2 and b["graphics"]["entrances"], b
        assert creator_style(d, "nobody")[0] is None
        # a user's own card-edit style with no card settings takes the sample Card edit's; its own keys win
        own = like_sample({"handle": "own-card-edit", "cards": {"per_min": 15}}, "own-card-edit")
        assert "text" not in own["card_kinds"] and own["behind"] and own["graphics"]["per_min"] and own["cards"] == {"per_min": 15}, own
        assert like_sample({"x": 1}, "own-50-50") == {"x": 1} and "card_kinds" not in like_sample({}, "card-edit")
        assert like_sample({"skill": "my-edit"}, "own-card-edit") == {"skill": "my-edit"}   # a skill style: its skill decides
        st = blend({"own-card-edit": own}, [{"handle": "own-card-edit", "take": ["captions", "pace", "visuals"]}])
        assert st["card_kinds"] == own["card_kinds"] and st["cards"] == {"per_min": 15}, st
    print("profile ok")


def my_style():
    """The user saved their own style: write or refresh the my-style skill and say its name."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ai_editor import styleskill, taste
    taste.HOME = HOME
    print(f"your style's skill: my-style -> {styleskill.write()}")


def main():
    a = sys.argv[1:]
    if a == ["demo"]:
        return demo()
    if a == ["show"]:
        print(json.dumps(load(), indent=1))
    elif a and a[0] == "missing":
        group = {"--style": STYLE_QUESTIONS, "--video": VIDEO_QUESTIONS}.get(a[1] if len(a) > 1 else "", QUESTIONS)
        print("\n".join(missing(group)) or "(all answered)")
    elif a == ["defaults"]:
        new = save_defaults()
        print(f"saved the defaults for {', '.join(new)} -> {path()}" if new else "(all questions answered)")
        my_style()
    elif len(a) >= 2 and a[0] == "set":
        pairs = [(a[1], a[2])] if len(a) == 3 and "=" not in a[1] else [x.split("=", 1) for x in a[1:]]
        bad = [x for x, p in zip(a[1:], pairs) if len(p) != 2 or not p[0]]
        if bad:
            sys.exit(f"profile.py set: {bad[0]!r} is not key=value. Write every answer as key=value "
                     "(the `set key value` form takes one answer alone)")
        prof = set_pairs(json.loads(path().read_text(encoding="utf-8")) if path().exists() else {}, pairs)
        print(f"set {', '.join(k for k, _ in pairs)} -> {save(prof)}")
        if any(k.split(".")[0] in STYLE_QUESTIONS for k, _ in pairs):
            my_style()
    elif len(a) >= 2 and a[0] == "style":
        flag = lambda k: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None
        out, style = write_style(a[1], out=flag("--out"), src=flag("--from"), as_=flag("--as"))
        print(f"{out}: {style.get('handle') or 'default'}, " + (f"from {style['source'][0]}" if flag("--from") else
                                              f"parts from {style['blend']}" if style.get("blend") else
                                              "no creator: the default style (smooth zooms, a move at least every 5 s, 3-word captions)"))
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from ai_editor import styleskill
        for sp in style.get("source") or []:   # the copied style's skill: its learned rules hold for this edit too
            md = styleskill.skills_dir() / styleskill.name(sp) / "SKILL.md"
            if md.is_file():
                print(f"skill: {styleskill.name(sp)} -> {md} (follow its \"Learned from your feedback\" in this edit)")
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    main()
