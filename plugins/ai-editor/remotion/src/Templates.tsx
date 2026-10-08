// Motion templates. Each takes ~200 tokens of JSON props (references/motion.md) and owns one GSAP
// timeline (motion.ts useTl) that the Remotion frame seeks. Motion ported by hand from the HyperFrames
// registry (Apache-2.0, see THIRD_PARTY_NOTICES.md); no upstream assets or data.
// Rules every template follows: text is shown exactly as given; every number and value comes from props;
// lines DRAW along their length, boxes and pills FADE AND SCALE; things land with an overshoot or a
// settle, never linearly; secondary pieces follow the primary one; the camera drifts so nothing is still.
import React from "react";
import { Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { fitTextOnNLines, measureText } from "@remotion/layout-utils";
import { Motion, SplitText, camera, exit, prog, rng, useTl } from "./motion";
import { Fonts, Look, Texture, shadowOf, textCase } from "./look";
import { Diagram } from "./Diagrams";

export type TP = { p: Record<string, any>; w: number; h: number; look: Look; m: Motion; fonts: Fonts; dur: number; id: string };

// ---------- helpers ----------
const u_ = (w: number, h: number) => Math.min(w, h) / 100;
/** Smallest label px on a 1080-wide frame that still reads on a phone. */
const LABEL_MIN = 30;
const src_ = (s?: string) => (!s ? undefined : /^(https?:|data:)/.test(s) ? s : staticFile(s));

/** Biggest font size that fits `text` in `maxW` on at most `lines` lines (measured, not estimated). */
export const fit = (text: string, maxW: number, lines: number, family: string, weight: number, max: number, tracking = 0,
  maxH = Infinity, lineHeight = 1.05) => {
  if (!text) return max;
  // the biggest size over every allowed line count that fits the width AND the height
  let best = 0;
  for (let n = 1; n <= lines; n++) {
    const r = fitTextOnNLines({ text: text.replace(/\*/g, ""), maxLines: n, maxBoxWidth: maxW, fontFamily: family,
      fontWeight: weight, maxFontSize: max, letterSpacing: `${tracking}em` });
    best = Math.max(best, Math.min(r.fontSize, maxH / (Math.max(1, r.lines.length) * lineHeight)));
  }
  return best * 0.97;
};
/** oneLine for a line with "*serif*" words: measures each run in its own face. */
const oneLineRich = (text: string, maxW: number, fonts: Fonts, look: Look) => {
  const at100 = text.split(/(\*[^*]+\*)/g).filter(Boolean).reduce((acc, s) => acc + measureText({ text: s.replace(/\*/g, ""),
    fontFamily: s.startsWith("*") && look.font_serif ? fonts.serif : fonts.display, fontWeight: s.startsWith("*") && look.font_serif ? 400 : look.weight_display,
    fontSize: 100, letterSpacing: `${look.tracking}em` }).width, 0);
  return (maxW / Math.max(1, at100)) * 100 * 0.96;
};
const oneLine = (text: string, maxW: number, family: string, weight: number, max: number, min = LABEL_MIN) => {
  const wAt100 = measureText({ text: text || " ", fontFamily: family, fontWeight: weight, fontSize: 100 }).width;
  return Math.max(min, Math.min(max, (maxW / Math.max(1, wAt100)) * 100));
};

/** "*word*" in a text renders that word in the look's serif italic, in the accent. */
const Rich: React.FC<{ text: string; look: Look; fonts: Fonts; cls?: string }> = ({ text: raw, look, fonts, cls }) => {
  const text = raw.replace(/ (\*[^*]+\*)/g, "\u00A0$1"); // never break right before the accent word
  return (
  <>
    {text.split(/(\*[^*]+\*)/g).filter(Boolean).map((s, i) =>
      s.startsWith("*") && s.endsWith("*") ? (
        <span key={i} className={cls} style={{ fontFamily: look.font_serif ? fonts.serif : undefined, fontStyle: "italic",
          fontWeight: look.font_serif ? 400 : undefined, color: look.accent, letterSpacing: 0 }}>{s.slice(1, -1)}</span>
      ) : <React.Fragment key={i}>{s}</React.Fragment>,
    )}
  </>
  );
};

/** SplitText line masks clip italic overhang and descenders; give them room without moving the text. */
const roomy = (masks: Element[] | undefined) => {
  for (const m of masks ?? []) Object.assign((m as HTMLElement).style, { padding: "0.06em 0.18em 0.1em", margin: "-0.06em -0.18em -0.1em" });
};
const useT = () => { const f = useCurrentFrame(); const { fps } = useVideoConfig(); return f / fps; };

const fill: React.CSSProperties = { position: "absolute", inset: 0 };
const center: React.CSSProperties = { ...fill, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" };

/** A hand-drawn closed ellipse through 14 wobbled points (hwWobbleEllipse, HyperFrames), seeded. */
const wobbleEllipse = (cx: number, cy: number, rx: number, ry: number, seed: number, pct = 3.5) => {
  const r = rng(seed), N = 14, pts: [number, number][] = [];
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2 - 0.5, k = 1 + (r() - 0.5) * 2 * (pct / 100);
    pts.push([cx + Math.cos(a) * rx * k, cy + Math.sin(a) * ry * k]);
  }
  // overshoot past the start like a pen that does not stop exactly where it began
  pts.push([pts[0][0] + rx * 0.12, pts[0][1] - ry * 0.1], [pts[1][0] + rx * 0.05, pts[1][1] - ry * 0.12]);
  let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`;
  for (let j = 1; j < pts.length - 1; j++) {
    const p = pts[j], q = pts[j + 1];
    d += ` Q${p[0].toFixed(1)} ${p[1].toFixed(1)} ${((p[0] + q[0]) / 2).toFixed(1)} ${((p[1] + q[1]) / 2).toFixed(1)}`;
  }
  return d;
};
/** A slightly uneven pen line from a to b. */
const penLine = (x1: number, y1: number, x2: number, y2: number, seed: number, wob: number) => {
  const r = rng(seed), mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  return `M${x1} ${y1} Q${mx + (r() - 0.5) * wob} ${my + (r() - 0.5) * wob} ${x2} ${y2}`;
};

/** The flat white tile a logo or image sits in (real logos read on white). */
export const isIcon = (src?: string) => !src || /(^|\/)icon-/.test(src);
const Tile: React.FC<{ src?: string; s: number; look: Look; letter?: string; cls?: string; style?: React.CSSProperties }> =
  ({ src, s, look, letter, cls, style }) => !isIcon(src) ? (
    // a real logo is drawn bare at full size: no tile, no shadow
    <div className={cls} style={{ width: s, height: s, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, ...style }}>
      <Img src={src_(src)!} style={{ width: s * 0.92, height: s * 0.92, objectFit: "contain" }} />
    </div>
  ) : (
    <div className={cls} style={{ width: s, height: s, borderRadius: s * 0.22, background: "#FFFFFF", display: "flex",
      alignItems: "center", justifyContent: "center", boxShadow: look.shadow === "hard" ? `${s * 0.05}px ${s * 0.05}px 0 ${look.ink}`
        : `0 0 0 1px ${look.line}, 0 ${s * 0.06}px ${s * 0.16}px rgba(0,0,0,0.12)`, flexShrink: 0, ...style }}>
      {src ? <Img src={src_(src)!} style={{ width: s * 0.58, height: s * 0.58, objectFit: "contain" }} />
        : <span style={{ fontSize: s * 0.42, fontWeight: 800, color: "#141414" }}>{letter}</span>}
    </div>
  );

// =====================================================================================================
// logo_sting: the real logo lands (scale 1.15 -> 1, expo.out), then a light sweep crosses the logo inside its
// own silhouette (logo-sting). Name rises under it. No ring: it popped in on one frame and grew then vanished.
// props: src (the real logo file), label?
const LogoSting: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = u_(w, h);
  const small = h < 400;
  const lab = p.label ? String(p.label) : "";
  const L = Math.min(w * 0.62, h * (lab && !small ? 0.58 : 0.8));
  const ref = useTl((tl, q, root) => {
    camera(tl, q, root, m, dur, u, p.ambient);
    const IMPACT = 0.55 * m.k;
    tl.fromTo(q(".ls-logo")[0], { scale: 1.15, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: IMPACT, ease: "expo.out" }, 0.05);
    tl.fromTo(q(".ls-sweep")[0], { xPercent: -160 }, { xPercent: 160, duration: 0.9 * m.k, ease: "power2.inOut" }, 0.05 + IMPACT);
    if (lab) tl.fromTo(q(".ls-label")[0], { yPercent: 110 }, { yPercent: 0, duration: 0.5 * m.k, ease: m.text }, 0.05 + IMPACT * 0.8);
    tl.fromTo(q(".ls-logo")[0], { y: 0 }, { y: -u * 0.8, duration: Math.max(0.6, dur - 1.2), ease: "sine.inOut", immediateRender: false }, 0.05 + IMPACT);
    exit(tl, root, m, dur, u);
  }, [p.src, lab, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  const mask = p.src ? { WebkitMaskImage: `url(${src_(p.src)})`, maskImage: `url(${src_(p.src)})`, WebkitMaskSize: "contain", maskSize: "contain",
    WebkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", WebkitMaskPosition: "center", maskPosition: "center" } as React.CSSProperties : {};
  return (
    <div ref={ref} style={center}>
      <div style={{ position: "relative", width: L, height: L, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div className="ls-logo" style={{ position: "relative", width: L * 0.8, height: L * 0.8 }}>
          {p.src ? <Img src={src_(p.src)!} style={{ width: "100%", height: "100%", objectFit: "contain" }} /> : null}
          <div style={{ ...fill, ...mask, overflow: "hidden" }}>
            <div className="ls-sweep" style={{ position: "absolute", top: "-20%", bottom: "-20%", left: "30%", width: "40%",
              background: "linear-gradient(100deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.75) 50%, rgba(255,255,255,0) 100%)", transform: "skewX(-18deg)" }} />
          </div>
        </div>
      </div>
      {lab && !small ? <div style={{ overflow: "hidden", marginTop: L * 0.06 }}>
        <div className="ls-label" style={{ fontFamily: fonts.display, fontWeight: look.weight_display, letterSpacing: `${look.tracking}em`,
          fontSize: oneLine(lab, w * 0.8, fonts.display, look.weight_display, L * 0.26), color: look.ink }}>{textCase(lab, look)}</div>
      </div> : null}
    </div>
  );
};

// =====================================================================================================
// social_post: a real post (X, Reddit or a YouTube comment) rises in, its words fade up in a fast wave,
// the quoted phrase gets a marker sweep, the like count bumps (x-post, yt-comment-card, reddit-post).
// All text and numbers from props (copied from the real post). No platform branding is drawn; pass the
// platform's logo file as logo_src if wanted.
// props: platform: x|reddit|youtube, name, handle?, avatar? (image), text, highlight? (substring),
//        likes?, replies?, reposts?, time?, subreddit?, logo_src?, excerpt? (default true)
// When the whole post would set its text too small to read on a phone (under 5% of the frame width,
// x-height about 28 px on 1080), it shows only the sentence holding `highlight`, with an ellipsis where
// text was left out, in a compact card that spends its height on that sentence.
const SocialPost: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = u_(w, h);
  const { width: FW, height: FH } = useVideoConfig();
  if (!p.text || !p.name) throw new Error("social_post needs `name` and `text` copied from the real post; refusing to draw a placeholder.");
  const full = String(p.text);
  const hl = String(p.highlight ?? "");
  let text = full, cw = Math.min(w * 0.92, h * 1.5);
  let size = fit(text, cw * 0.86, 5, fonts.body, 500, Math.min(h * 0.13, cw * 0.075), 0, h * 0.5, 1.32);
  const READ = Math.min(FW, FH) * 0.05;
  const sents = full.split(/(?<=[.!?])\s+|\n+/).map((x) => x.trim()).filter(Boolean);
  const si = hl ? sents.findIndex((x) => x.toLowerCase().includes(hl.toLowerCase())) : -1;
  const compact = p.excerpt !== false && size < READ && si >= 0 && sents.length > 1;
  if (compact) {
    text = (si > 0 ? "… " : "") + sents[si] + (si < sents.length - 1 ? " …" : "");
    cw = w * 0.94;
    // chrome in units of the text size: padding 1.5, the name row 2.3, the stats row 1.6
    let best = 0;
    for (let n = 1; n <= 4; n++) {
      const r = fitTextOnNLines({ text, maxLines: n, maxBoxWidth: cw - 1.6 * READ, fontFamily: fonts.body, fontWeight: 500, maxFontSize: READ * 1.4 });
      best = Math.max(best, Math.min(r.fontSize, (h * 0.96) / (Math.max(1, r.lines.length) * 1.32 + 5.4)));
    }
    size = best * 0.97;
  }
  const meta = size * 0.72;
  const hi = hl ? text.toLowerCase().indexOf(hl.toLowerCase()) : -1;
  const [pre, mid, post] = hi >= 0 ? [text.slice(0, hi), text.slice(hi, hi + hl.length), text.slice(hi + hl.length)] : [text, "", ""];
  const ref = useTl((tl, q, root) => {
    camera(tl, q, root, m, dur, u, p.ambient);
    tl.fromTo(q(".sp-card")[0], { y: u * 14, autoAlpha: 0, rotate: 1.5 }, { y: 0, autoAlpha: 1, rotate: 0, duration: 0.7 * m.k, ease: m.antic }, 0.05);
    tl.fromTo(q(".sp-av")[0], { scale: 0 }, { scale: 1, duration: 0.45, ease: "back.out(1.6)" }, 0.25);
    tl.fromTo(q(".sp-meta")[0], { autoAlpha: 0, y: u }, { autoAlpha: 1, y: 0, duration: 0.4, ease: "power2.out" }, 0.37);
    const split = SplitText.create(q(".sp-text")[0], { type: "words" });
    tl.fromTo(split.words, { autoAlpha: 0, y: size * 0.3 }, { autoAlpha: 1, y: 0, duration: 0.3, ease: "power2.out",
      stagger: Math.min(0.035, 0.9 / Math.max(1, split.words.length)) }, 0.45);
    const words = 0.45 + Math.min(0.9, split.words.length * 0.035);
    if (mid) tl.fromTo(q(".sp-hl")[0], { backgroundSize: "0% 100%" }, { backgroundSize: "100% 100%", duration: 0.6 * m.k, ease: "power2.inOut" }, words + 0.2);
    tl.fromTo(q(".sp-like")[0], { scale: 1 }, { scale: 1.25, duration: 0.12, ease: "power2.out", yoyo: true, repeat: 1 }, words + 0.7);
    exit(tl, root, m, dur, u);
  }, [text, hl, size, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  const name = String(p.name ?? ""), handle = p.handle ? String(p.handle) : "";
  const stats = [["replies", p.replies], ["reposts", p.reposts], ["likes", p.likes]].filter(([, v]) => v !== undefined && v !== null && v !== "");
  const plat = p.platform ?? "x";
  const sub = plat === "reddit" && p.subreddit ? `r/${String(p.subreddit).replace(/^r\//, "")}` : "";
  return (
    <div ref={ref} style={center}>
      <div className="sp-card" style={{ width: cw, background: "#FFFFFF", color: "#0F1419", borderRadius: u * 3, padding: compact ? `${size * 0.75}px ${size * 0.8}px` : size * 1.1, boxSizing: "border-box",
        boxShadow: shadowOf(look, u), fontFamily: fonts.body, border: look.shadow === "hard" ? `2px solid ${look.ink}` : undefined }}>
        <div className="sp-meta" style={{ display: "flex", alignItems: "center", gap: size * 0.55, marginBottom: size * (compact ? 0.5 : 0.7) }}>
          <div className="sp-av" style={{ width: size * (compact ? 1.5 : 2.1), height: size * (compact ? 1.5 : 2.1), borderRadius: "50%", background: look.ink, color: look.ground, overflow: "hidden",
            display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: size, flexShrink: 0 }}>
            {p.avatar ? <Img src={src_(p.avatar)!} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : name.slice(0, 1).toUpperCase()}
          </div>
          <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 800, fontSize: meta * 1.08, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{sub || name}</div>
            <div style={{ fontWeight: 500, fontSize: meta, color: "#536471", whiteSpace: "nowrap" }}>
              {[sub ? name : handle && (plat === "x" ? `@${handle.replace(/^@/, "")}` : handle), p.time].filter(Boolean).join(" · ")}</div>
          </div>
          {p.logo_src ? <Img src={src_(p.logo_src)!} style={{ height: size * 1.2, width: size * 1.2, objectFit: "contain" }} /> : null}
        </div>
        <div className="sp-text" style={{ fontSize: size, lineHeight: 1.32, fontWeight: 500, whiteSpace: "pre-wrap" }}>
          {pre}{mid ? <span className="sp-hl" style={{ backgroundImage: `linear-gradient(${look.mark}, ${look.mark})`, backgroundRepeat: "no-repeat",
            backgroundSize: "0% 100%", padding: "0 0.08em", borderRadius: "0.12em" }}>{mid}</span> : null}{post}
        </div>
        {stats.length ? <div style={{ display: "flex", gap: size * 1.4, marginTop: size * (compact ? 0.6 : 0.9), fontSize: meta, color: "#536471", fontWeight: 600 }}>
          {stats.map(([k, v]) => <span key={String(k)} className={k === "likes" ? "sp-like" : undefined} style={{ display: "inline-block" }}>
            <b style={{ color: "#0F1419" }}>{String(v)}</b> {String(k)}</span>)}
        </div> : null}
      </div>
    </div>
  );
};

// =====================================================================================================
// arrow_callout: a label pill fades and scales in, then a hand-drawn arrow draws from it to a point
// (hw-arrow: ink-paced stroke, head drawn after the shaft). props: label, point: [fx, fy] (fractions of
// the card box the arrow points at), side?: auto|left|right
const ArrowCallout: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = u_(w, h);
  const [fx, fy] = p.point ?? [0.75, 0.3];
  const px = fx * w, py = fy * h;
  const lab = String(p.label ?? "");
  const lS = Math.max(LABEL_MIN, Math.min(u * 7, oneLine(lab, w * 0.5, fonts.body, 800, u * 7)));
  const lw = measureText({ text: lab, fontFamily: fonts.body, fontWeight: 800, fontSize: lS }).width + lS * 1.2;
  const left = (p.side ?? "auto") === "auto" ? fx > 0.5 : p.side === "left";
  const lx = left ? Math.max(u * 3, px - w * 0.45) : Math.min(w - lw - u * 3, px + w * 0.45 - lw), ly = Math.min(h - lS * 2.5, py + h * 0.28);
  const sx = lx + lw / 2, sy = ly - lS * 0.3, ex = px + (left ? -1 : 1) * u * 2, ey = py + u * 3;
  const cx = (sx + ex) / 2 + (left ? -1 : 1) * u * 10, cy = (sy + ey) / 2 + u * 6;
  const ang = Math.atan2(ey - cy, ex - cx), hl = Math.max(u * 4, 22);
  const head = `M${ex - hl * Math.cos(ang - 0.5)} ${ey - hl * Math.sin(ang - 0.5)} L${ex} ${ey} L${ex - hl * Math.cos(ang + 0.5)} ${ey - hl * Math.sin(ang + 0.5)}`;
  const ref = useTl((tl, q, root) => {
    tl.fromTo(q(".ac-pill")[0], { scale: 0.7, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.45, ease: m.pop }, 0.1);
    tl.set(q(".ac-shaft")[0], { opacity: 1 }, 0.35);
    tl.fromTo(q(".ac-shaft")[0], { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.55 * m.k, ease: "ink" }, 0.35);
    tl.set(q(".ac-head")[0], { opacity: 1 }, 0.35 + 0.5 * m.k);
    tl.fromTo(q(".ac-head")[0], { drawSVG: "50% 50%" }, { drawSVG: "0% 100%", duration: 0.2, ease: "power2.out" }, 0.35 + 0.5 * m.k);
    exit(tl, root, m, dur, u);
  }, [lab, px, py, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  const sw = Math.max(4, u * 0.9);
  return (
    <div ref={ref} style={fill}>
      <svg width={w} height={h} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <path className="ac-shaft" d={`M${sx} ${sy} Q${cx} ${cy} ${ex} ${ey}`} fill="none" stroke={look.accent} strokeWidth={sw} strokeLinecap="round" opacity={0} />
        <path className="ac-head" d={head} fill="none" stroke={look.accent} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" opacity={0} />
      </svg>
      <div className="ac-pill" style={{ position: "absolute", left: lx, top: ly, padding: `${lS * 0.25}px ${lS * 0.6}px`, background: look.accent,
        color: look.accent_ink, fontFamily: fonts.body, fontWeight: 800, fontSize: lS, borderRadius: lS, whiteSpace: "nowrap",
        boxShadow: shadowOf(look, u * 0.6) }}>{lab}</div>
    </div>
  );
};

// =====================================================================================================
// icon_burst: the subject (a real logo/image or a word) springs in and throws flat confetti shapes out
// on Physics2D arcs (confetti). Seeded, so every render matches. props: src? | text?, count? (default
// 18), seed?, at?
const IconBurst: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = u_(w, h);
  const N = Math.min(40, Number(p.count ?? 18)), r = rng(Number(p.seed ?? 1));
  // evenly spread round the circle (seeded jitter), biased upward, so the burst reads as radial
  const parts = Array.from({ length: N }, (_, i) => ({ a: -90 + ((i / N) - 0.5) * 320 + (r() - 0.5) * 14, v: (0.45 + r() * 0.5) * Math.min(w, h) * 1.6,
    s: u * (3.5 + r() * 4.5), shape: i % 3, c: [look.accent, look.ink, look.muted][i % 3], rot: (r() - 0.5) * 720 }));
  const S = Math.min(w, h) * 0.5;
  const at = Number(p.at ?? 0.35);
  const ref = useTl((tl, q, root) => {
    camera(tl, q, root, m, dur, u, p.ambient);
    tl.fromTo(q(".ib-core")[0], { scale: 0, rotate: -10 }, { scale: 1, rotate: 0, duration: 0.6, ease: m.pop }, 0.05);
    q(".ib-p").forEach((el, i) => {
      const pt = parts[i];
      tl.set(el, { opacity: 1 }, at);
      tl.fromTo(el, { x: 0, y: 0, rotate: 0 }, { physics2D: { velocity: pt.v, angle: pt.a, gravity: Math.min(w, h) * 1.6 }, rotate: pt.rot,
        duration: 1.6, ease: "none" }, at);
      tl.to(el, { opacity: 0, duration: 0.4 }, at + 1.2 + (i % 5) * 0.05);
    });
    tl.fromTo(q(".ib-core")[0], { scale: 1 }, { scale: 1.08, duration: 0.14, ease: "power2.out", yoyo: true, repeat: 1, immediateRender: false }, at);
    exit(tl, root, m, dur, u);
  }, [N, p.seed, p.src, p.text, dur, m.name, w, h]);
  return (
    <div ref={ref} style={center}>
      {parts.map((pt, i) => (
        <div key={i} className="ib-p" style={{ position: "absolute", left: w / 2 - pt.s / 2, top: h / 2 - pt.s / 2, width: pt.s, height: pt.shape === 2 ? pt.s * 0.4 : pt.s,
          background: pt.c, borderRadius: pt.shape === 0 ? "50%" : pt.s * 0.1, opacity: 0 }} />
      ))}
      <div className="ib-core">
        {p.src ? <Tile src={p.src} s={S} look={look} /> : (
          <div style={{ fontFamily: fonts.display, fontWeight: look.weight_display, fontSize: oneLine(String(p.text ?? ""), w * 0.8, fonts.display,
            look.weight_display, S * 0.6), color: look.ink, letterSpacing: `${look.tracking}em` }}>{textCase(String(p.text ?? ""), look)}</div>
        )}
      </div>
    </div>
  );
};

// =====================================================================================================
// Type cards (slam, title, phrase_mark, counter, bar_chart, line_chart, versus, checklist, lower_third,
// pile) were removed 2026-10-06: words on a ground read as AI-made. The real source, captured and marked,
// carries those beats (references/visuals.md).
export const TEMPLATES: Record<string, React.FC<TP>> = {
  flow: Diagram, logo_sting: LogoSting, social_post: SocialPost, arrow_callout: ArrowCallout, icon_burst: IconBurst,
};
/** Templates that float over the footage with no card under them (flow: its nodes are the cards, Diagrams.tsx). */
export const FLOATING = new Set(["arrow_callout", "caption_page", "flow"]);
