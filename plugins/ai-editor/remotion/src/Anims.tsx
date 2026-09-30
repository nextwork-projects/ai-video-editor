import React from "react";
import { Easing, Img, interpolate, spring, staticFile } from "remotion";

// Built animation cards. One idea per card. Text cards (counter, steps, versus, logo, keyword) and scenes
// (flow, race, pile: pictures that move, each part landing on its word). Theme "dark" draws them on a panel
// over the footage (the overlay layout); "light" draws them straight on the split layout's ground.
// Shapes: docs/CONTRACTS.md "visuals.json". Text is shown exactly as written (keep the speaker's words).
export type Anim = {
  type: "counter" | "steps" | "versus" | "logo" | "keyword" | "flow" | "race" | "pile";
  props: Record<string, any>;
};
export type Theme = "dark" | "light";

type Pal = { text: string; dim: string; line: string; accent: string; accentInk: string; track: string;
  bar: string; edge: string; shadow: string };
const PALS: Record<Theme, Pal> = {
  dark: { text: "#F5F5F2", dim: "rgba(245,245,242,0.62)", line: "rgba(255,255,255,0.16)", accent: "#7CF2B0",
    accentInk: "#0B1A12", track: "rgba(255,255,255,0.08)", bar: "rgba(245,245,242,0.55)", edge: "rgba(0,0,0,0)",
    shadow: "rgba(0,0,0,0.4)" },
  light: { text: "#15171C", dim: "rgba(21,23,28,0.5)", line: "rgba(21,23,28,0.12)", accent: "#16A34A",
    accentInk: "#FFFFFF", track: "rgba(21,23,28,0.07)", bar: "rgba(21,23,28,0.32)", edge: "rgba(21,23,28,0.1)",
    shadow: "rgba(30,30,40,0.16)" },
};

const INK = "#111111";
const MUTED = "#6B6B6B";
const PANEL = "rgba(255,255,255,0.96)";
const GLASS = "rgba(14,15,19,0.78)";
// Smallest label, px on a 1080-wide frame: what still reads on a phone.
const LABEL_MIN = 34;

// Slow ease in from `at` seconds over `dur` seconds, 0 -> 1.
const ease = (t: number, at = 0, dur = 0.7) =>
  interpolate(t, [at, at + dur], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

// Slow ease that reads as motion, not a jump.
const glide = (t: number, at: number, dur = 0.9) =>
  interpolate(t, [at, at + dur], [0, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

// A spring from `at`: 0 -> about 1.08 -> settles on 1. Seconds in, so it is the same at any fps.
export const pop = (t: number, at: number) =>
  t < at ? 0 : spring({ frame: (t - at) * 30, fps: 30, config: { damping: 11, stiffness: 170, mass: 0.7 } });

const rise = (p: number, px: number): React.CSSProperties => ({
  opacity: Math.min(1, p),
  transform: `translateY(${(1 - p) * px}px)`,
});

// Font size so `text` fits `w` px on one line (a bold sans glyph averages about 0.52em).
const fit = (text: string, w: number, max: number) => Math.min(max, w / (0.52 * Math.max(1, text.length)));
// The same, never under LABEL_MIN.
const label = (text: string, w: number, max: number) => Math.max(LABEL_MIN, fit(text, w, max));

type P = { anim: Anim; t: number; w: number; h: number; family: string; theme?: Theme; dur?: number };

const Counter: React.FC<P> = ({ anim, t, w, h }) => {
  const { to, from = 0, prefix = "", suffix = "", label: lab = "", decimals = 0 } = anim.props;
  const v = interpolate(ease(t, 0.15, 1.1), [0, 1], [Number(from), Number(to)]);
  const num = `${prefix}${v.toFixed(decimals)}${suffix}`;
  const full = `${prefix}${Number(to).toFixed(decimals)}${suffix}`;
  const p = pop(t, 0);
  return (
    <>
      <div style={{ fontSize: fit(full, w * 0.86, h * 0.5), fontWeight: 800, lineHeight: 1, color: INK,
        fontVariantNumeric: "tabular-nums", transform: `scale(${0.7 + 0.3 * p})` }}>{num}</div>
      {lab ? (
        <div style={{ ...rise(pop(t, 0.5), h * 0.08), fontSize: label(lab, w * 0.86, h * 0.13), color: MUTED,
          marginTop: h * 0.04 }}>{lab}</div>
      ) : null}
    </>
  );
};

const Steps: React.FC<P> = ({ anim, t, w, h }) => {
  const items: string[] = (anim.props.items ?? []).slice(0, 4);
  const longest = items.reduce((a, b) => (b.length > a.length ? b : a), "");
  const size = Math.max(LABEL_MIN, Math.min(h / (items.length * 1.6 + 0.2), fit(longest, w * 0.8, h)));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: size * 0.5, alignItems: "flex-start" }}>
      {items.map((it, i) => {
        const p = pop(t, 0.1 + i * 0.5);
        return (
          <div key={i} style={{ opacity: Math.min(1, p * 1.5), transform: `translateX(${(1 - p) * -size}px)`,
            display: "flex", alignItems: "center", gap: size * 0.45, fontSize: size, lineHeight: 1.1, color: INK }}>
            <span style={{ width: size * 1.25, height: size * 1.25, borderRadius: "50%", background: INK, color: "#fff",
              fontSize: size * 0.7, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
              flexShrink: 0, transform: `scale(${p})` }}>{i + 1}</span>
            <span style={{ fontWeight: 600 }}>{it}</span>
          </div>
        );
      })}
    </div>
  );
};

const Versus: React.FC<P> = ({ anim, t, w, h }) => {
  const { a = "", b = "", a_label = "", b_label = "" } = anim.props;
  // One size for both sides so neither reads as the winner.
  const big = Math.min(fit(a, w * 0.42, h * 0.3), fit(b, w * 0.42, h * 0.3));
  const small = Math.max(LABEL_MIN, Math.min(fit(a_label, w * 0.42, h * 0.14), fit(b_label, w * 0.42, h * 0.14)));
  const col = (title: string, lab: string, p: number) => (
    <div style={{ ...rise(p, h * 0.1), flex: 1, textAlign: "center" }}>
      {lab ? <div style={{ fontSize: small, color: MUTED, marginBottom: h * 0.03 }}>{lab}</div> : null}
      <div style={{ fontSize: big, fontWeight: 800, color: INK, lineHeight: 1.05 }}>{title}</div>
    </div>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", width: w }}>
      {col(a, a_label, pop(t, 0.1))}
      <div style={{ opacity: ease(t, 0.45), transform: `scale(${0.5 + 0.5 * pop(t, 0.45)})`, fontSize: h * 0.1,
        color: MUTED, padding: `0 ${w * 0.03}px` }}>vs</div>
      {col(b, b_label, pop(t, 0.7))}
    </div>
  );
};

const Logo: React.FC<P> = ({ anim, t, w, h }) => {
  const { src, label: lab = "" } = anim.props;
  const p = pop(t, 0.05);
  const bob = Math.sin(t * 1.6) * h * 0.012;
  return (
    <>
      {/* An explicit height: icon SVGs carry only a viewBox, so max sizes alone render them at 24 px. */}
      {src ? <Img src={staticFile(src)} style={{ opacity: Math.min(1, p * 2), transform: `translateY(${bob}px) scale(${0.5 + 0.5 * p})`,
        height: h * (lab ? 0.5 : 0.7), maxWidth: w * 0.8, objectFit: "contain" }} /> : null}
      {lab ? <div style={{ ...rise(pop(t, 0.4), h * 0.05), fontSize: label(lab, w * 0.86, h * 0.16), fontWeight: 700,
        color: INK, marginTop: h * 0.05 }}>{lab}</div> : null}
    </>
  );
};

const Keyword: React.FC<P> = ({ anim, t, w, h }) => {
  const { text = "", sub = "" } = anim.props;
  const p = pop(t, 0.05);
  return (
    <>
      <div style={{ opacity: Math.min(1, p * 2), transform: `scale(${0.8 + 0.2 * p})`, fontSize: fit(text, w * 0.86, h * 0.34),
        fontWeight: 800, color: INK, lineHeight: 1.05, textAlign: "center" }}>{text}</div>
      {sub ? <div style={{ ...rise(pop(t, 0.5), h * 0.08), fontSize: label(sub, w * 0.86, h * 0.13), color: MUTED,
        marginTop: h * 0.04, textAlign: "center" }}>{sub}</div> : null}
    </>
  );
};

// ---------- Scenes: pictures that move, each part landing on its word ----------
// A part: {src (an image in images/, plan.py fills it from "icon" / "logo"), label, at (seconds after the
// card lands, plan.py fills it from "word"), off_at (from "off_word": the part dims again)}.
type Part = { src?: string; label?: string | { text: string; at?: number }[]; at?: number; off_at?: number;
  value?: number; from?: number };
type SP = P & { pal: Pal };

const labelNow = (lab: Part["label"], t: number) =>
  typeof lab === "string" || !lab ? lab ?? "" : [...lab].reverse().find((l) => (l.at ?? 0) <= t)?.text ?? "";

/** A white rounded tile with a logo, icon or image in it. p: its landing spring (0 not yet, 1 landed, overshoots
 *  on the way). ghost: before it lands it waits as a faint placeholder, so the picture's shape is there from
 *  the start. dim 0..1 greys it after its off word; ring 0..1 draws the accent ring. Bobs gently once landed. */
const Tile: React.FC<{ src?: string; s: number; p: number; dim?: number; ring?: number; x: number; y: number;
  letter?: string; t: number; i: number; pal: Pal; ghost?: boolean }> =
  ({ src, s, p, dim = 0, ring = 0, x, y, letter, t, i, pal, ghost }) => {
    if (p <= 0.001 && ghost) {
      return <div style={{ position: "absolute", left: x - s / 2, top: y - s / 2, width: s, height: s, borderRadius: s * 0.26,
        border: `${Math.max(2, s * 0.02)}px dashed ${pal.dim}`, opacity: 0.45, transform: "scale(0.86)", boxSizing: "border-box" }} />;
    }
    if (p <= 0.001) return null;
    const bob = Math.sin(t * 1.7 + i * 1.3) * s * 0.025 * Math.min(1, p);
    return (
      <div style={{ position: "absolute", left: x - s / 2, top: y - s / 2 + bob, width: s, height: s, borderRadius: s * 0.26,
        background: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center",
        opacity: Math.min(1, p * 2) * (1 - 0.62 * dim), transform: `scale(${(0.55 + 0.45 * p) * (1 + 0.05 * ring)})`,
        boxShadow: `0 0 0 ${s * 0.045 * ring}px ${pal.accent}, 0 0 ${s * 0.45 * ring}px ${pal.accent}77, ` +
          `inset 0 0 0 1.5px ${pal.edge}, 0 ${s * 0.07}px ${s * 0.2}px ${pal.shadow}` }}>
        {src ? <Img src={staticFile(src)} style={{ width: s * 0.6, height: s * 0.6, objectFit: "contain" }} />
          : <span style={{ fontSize: s * 0.42, fontWeight: 800, color: INK }}>{letter}</span>}
      </div>
    );
  };

/** The one number said, as a badge: top right, on the panel's edge (dark) or the scene's corner (light). */
const Tag: React.FC<{ tag?: { text: string; at?: number }; t: number; w: number; h: number; pal: Pal }> =
  ({ tag, t, w, h, pal }) => {
    if (!tag?.text) return null;
    const p = pop(t, tag.at ?? 1.2);
    const size = Math.max(LABEL_MIN, Math.min(h * 0.13, w * 0.065));
    const top = pal === PALS.light ? 0 : -Math.min(w, h) * 0.1 - size * 0.66;
    return (
      <div style={{ position: "absolute", right: 0, top, padding: `${size * 0.22}px ${size * 0.6}px`,
        borderRadius: size, background: pal.accent, color: pal.accentInk, fontSize: size, fontWeight: 800, lineHeight: 1.1,
        opacity: Math.min(1, p * 2), transform: `translateY(${(1 - p) * -size}px) scale(${0.6 + 0.4 * p})`,
        transformOrigin: "100% 0", whiteSpace: "nowrap" }}>
        {tag.text}
      </div>
    );
  };

/** A line that draws itself from 0 to 1, with an arrowhead once it arrives. */
const Arrow: React.FC<{ d: string; end: [number, number]; p: number; size: number; alpha?: number; pal: Pal }> =
  ({ d, end, p, size, alpha = 1, pal }) => (
    <g opacity={alpha}>
      <path d={d} pathLength={1} fill="none" stroke={p >= 1 ? pal.text : pal.dim} strokeWidth={Math.max(3, size * 0.035)}
        strokeLinecap="round" strokeDasharray="1 1" strokeDashoffset={1 - p} />
      <path d={`M ${end[0] - size * 0.14} ${end[1] - size * 0.11} L ${end[0]} ${end[1]} L ${end[0] - size * 0.14} ${end[1] + size * 0.11}`}
        fill="none" stroke={pal.text} strokeWidth={Math.max(3, size * 0.035)} strokeLinecap="round" strokeLinejoin="round"
        opacity={interpolate(p, [0.85, 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
    </g>
  );

// Flow: nodes left to right joined by arrows that draw in, the last node optionally splitting to 2-3 nodes.
const Flow: React.FC<SP> = ({ anim, t, w, h, pal }) => {
  const nodes: Part[] = anim.props.nodes ?? [];
  const split: Part[] = (anim.props.split ?? []).slice(0, 3);
  const n = nodes.length, k = split.length;
  if (!n) return null;
  const at = (p: Part, i: number) => p.at ?? 0.3 + i * 0.7;
  const labelled = nodes.some((p) => p.label);
  const G = 0.65; // gap between nodes, in node sizes
  const S = Math.min(w / (n + G * (n - 1) + (k ? G + 0.7 * 2.9 : 0)), h * (labelled ? 0.5 : 0.66));
  const ts = k ? Math.min(S * 0.7, h / (k * 1.3)) : 0;
  const total = S * n + G * S * (n - 1) + (k ? G * S + ts * 2.9 : 0);
  const x0 = (w - total) / 2;
  const cy = h / 2 - (labelled ? S * 0.16 : 0);
  const cx = (i: number) => x0 + S / 2 + i * (1 + G) * S;
  const sx = x0 + n * S + (n - 1) * G * S + G * S;
  const sy = (j: number) => h / 2 + (j - (k - 1) / 2) * ts * 1.3;
  const times = [...nodes.map(at), ...split.map((p, j) => at(p, n + j))];
  // The ring sits on the node said most recently.
  const ring = (i: number) => {
    const next = times.filter((x) => x > times[i]).sort((a, b) => a - b)[0];
    return glide(t, times[i] - 0.1, 0.5) * (next === undefined ? 1 : 1 - glide(t, next - 0.1, 0.5));
  };
  const popOf = (i: number) => pop(t, times[i] - 0.15);
  const dimOf = (p: Part) => (p.off_at === undefined ? 0 : glide(t, p.off_at, 0.6));
  const pad = S * 0.1;
  const lab = (text: string, p: number, dim: number, style: React.CSSProperties) => (
    <div style={{ position: "absolute", fontWeight: 700, color: pal.text, whiteSpace: "nowrap",
      opacity: Math.min(1, p * 1.5) * (1 - 0.6 * dim), ...style }}>{text}</div>
  );
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <svg width={w} height={h} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        {nodes.slice(1).map((_, i) => {
          const a = cx(i) + S / 2 + pad, b = cx(i + 1) - S / 2 - pad;
          return <Arrow key={i} d={`M ${a} ${cy} L ${b} ${cy}`} end={[b, cy]} size={S} pal={pal}
            p={glide(t, times[i + 1] - 0.55, 0.55)} />;
        })}
        {split.map((p, j) => {
          const a = cx(n - 1) + S / 2 + pad, b = sx - ts * 0.14, y = sy(j), m = (a + b) / 2;
          return <Arrow key={`s${j}`} d={`M ${a} ${cy} C ${m} ${cy}, ${m} ${y}, ${b} ${y}`} end={[b, y]} size={S} pal={pal}
            p={glide(t, times[n + j] - 0.55, 0.55)} alpha={1 - 0.6 * dimOf(p)} />;
        })}
      </svg>
      {nodes.map((p, i) => {
        const text = labelNow(p.label, t), pp = popOf(i);
        const size = label(text, S * (1 + G) * 0.95, S * 0.26);
        return (
          <React.Fragment key={i}>
            <Tile ghost src={p.src} s={S} x={cx(i)} y={cy} p={pp} dim={dimOf(p)} ring={ring(i)} letter={text.slice(0, 1)}
              t={t} i={i} pal={pal} />
            {text ? lab(text, pp, dimOf(p), { left: cx(i) - S * 1.2, width: S * 2.4, top: cy + S * 0.62,
              textAlign: "center", fontSize: size, transform: `translateY(${(1 - Math.min(1, pp)) * size}px)` }) : null}
          </React.Fragment>
        );
      })}
      {split.map((p, j) => {
        const text = labelNow(p.label, t), pp = popOf(n + j);
        return (
          <React.Fragment key={`s${j}`}>
            <Tile ghost src={p.src} s={ts} x={sx + ts / 2} y={sy(j)} p={pp} dim={dimOf(p)} ring={ring(n + j)}
              letter={text.slice(0, 1)} t={t} i={n + j} pal={pal} />
            {text ? lab(text, pp, dimOf(p), { left: sx + ts * 1.18, top: sy(j),
              transform: `translateY(-50%) translateX(${(1 - Math.min(1, pp)) * -ts * 0.3}px)`,
              fontSize: label(text, ts * 1.7, ts * 0.42) }) : null}
          </React.Fragment>
        );
      })}
      <Tag tag={anim.props.tag} t={t} w={w} h={h} pal={pal} />
    </div>
  );
};

// Race: 2-3 bars, each led by a logo, growing to the values said. The biggest is the accent and counts up.
const Race: React.FC<SP> = ({ anim, t, w, h, pal }) => {
  const rows: Part[] = (anim.props.rows ?? []).slice(0, 3);
  const { prefix = "", suffix = "" } = anim.props;
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => Number(r.value) || 0), 1);
  const rh = Math.min(h / (rows.length * 1.45), w * 0.25);
  const size = Math.max(LABEL_MIN, rh * 0.46);
  const longest = Math.max(...rows.map((r) => `${prefix}${r.value}${suffix}`.length));
  const valW = size * 0.62 * longest + size * 0.5;
  const trackX = rh * 1.1, trackW = w - trackX - valW;
  const gap = rh * 1.45;
  const y0 = (h - rows.length * gap + gap - rh) / 2 + rh * 0.62;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {rows.map((r, i) => {
        const at = r.at ?? 0.3 + i * 0.8;
        const win = Number(r.value) === max;
        const grow = glide(t, at, win ? 1.6 : 0.9);
        const v = win ? interpolate(grow, [0, 1], [Number(r.from ?? 0), Number(r.value)]) : Number(r.value);
        const len = Math.max(rh * 0.36, (Number(r.value) / max) * trackW) * grow;
        const y = y0 + i * gap;
        const pp = pop(t, at - 0.4);
        const text = labelNow(r.label, t);
        const ls = Math.max(LABEL_MIN, rh * 0.24);
        return (
          <React.Fragment key={i}>
            <Tile ghost src={r.src} s={rh * 0.9} x={rh * 0.45} y={y} p={pp} ring={win ? glide(t, at + 1.2, 0.6) : 0}
              letter={text.slice(0, 1)} t={t} i={i} pal={pal} />
            <div style={{ position: "absolute", left: trackX, top: y - rh * 0.2, width: trackW, height: rh * 0.4,
              borderRadius: rh, background: pal.track }} />
            <div style={{ position: "absolute", left: trackX, top: y - rh * 0.2, width: len, height: rh * 0.4,
              borderRadius: rh, background: win ? pal.accent : pal.bar,
              boxShadow: win ? `0 0 ${rh * 0.4}px ${pal.accent}55` : undefined }} />
            <div style={{ position: "absolute", left: trackX + len + size * 0.35, top: y,
              transform: `translateY(-50%) scale(${0.8 + 0.2 * Math.min(1, grow * 2)})`, transformOrigin: "0 50%",
              fontSize: size, fontWeight: 800, color: win ? pal.accent : pal.text, opacity: Math.min(1, grow * 3),
              fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
              {`${prefix}${Math.round(v)}${suffix}`}
            </div>
            {text ? <div style={{ position: "absolute", left: trackX, top: y - rh * 0.26 - ls * 1.15, fontSize: ls,
              fontWeight: 700, color: pal.dim, opacity: Math.min(1, pp), whiteSpace: "nowrap" }}>{text}</div> : null}
          </React.Fragment>
        );
      })}
      <Tag tag={anim.props.tag} t={t} w={w} h={h} pal={pal} />
    </div>
  );
};

// Pile: a source tile throws N copies of an icon into 1-3 stacks, one after another.
const Pile: React.FC<SP> = ({ anim, t, w, h, pal }) => {
  const { count = 12, src, source, at = 0.4, every = 0.09 } = anim.props;
  const stacks: Part[] = (anim.props.stacks ?? [{}, {}, {}]).slice(0, 3);
  const k = stacks.length;
  const labelled = stacks.some((s) => s.label);
  const sT = Math.min(h * 0.5, w * 0.22);
  const srcX = sT / 2 + w * 0.02, srcY = h / 2;
  const left = w * 0.38, regionW = w - left;
  const b = Math.min(h * (labelled ? 0.3 : 0.36), regionW / (k * 1.25));
  const e = b * 0.72;
  const binY = h - b / 2 - (labelled ? LABEL_MIN * 1.4 : h * 0.02);
  const binX = (j: number) => left + regionW * ((j + 0.5) / k);
  const items = Array.from({ length: count }, (_, i) => i);
  const flying = glide(t, at - 0.2, 0.4) * (1 - glide(t, at + count * every, 0.5));
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Tile src={(source && source.src) || src} s={sT} x={srcX} y={srcY} p={pop(t, 0)} ring={flying} t={t} i={0} pal={pal} />
      {stacks.map((s, j) => {
        const text = labelNow(s.label, t), pp = pop(t, 0.15 + j * 0.12);
        return (
          <React.Fragment key={j}>
            <Tile src={s.src} s={b} x={binX(j)} y={binY} p={pp} letter={text.slice(0, 1)} t={t} i={j + 1} pal={pal} />
            {text ? <div style={{ position: "absolute", left: binX(j) - b, width: b * 2, top: binY + b * 0.58,
              textAlign: "center", fontSize: label(text, b * 2, b * 0.32), fontWeight: 700, color: pal.text,
              opacity: Math.min(1, pp) }}>{text}</div> : null}
          </React.Fragment>
        );
      })}
      {items.map((i) => {
        const j = i % k, m = Math.floor(i / k);
        const p = glide(t, at + i * every, 0.75);
        if (p <= 0) return null;
        const tx = binX(j) + (m % 2 ? 1 : -1) * e * 0.05, ty = binY - b / 2 - e * 0.42 - m * e * 0.2;
        const x = interpolate(p, [0, 1], [srcX, tx]);
        const y = interpolate(p, [0, 1], [srcY, ty]) - Math.sin(Math.PI * p) * h * 0.28;
        // Each item turns as it flies and lands square.
        return (
          <div key={i} style={{ position: "absolute", inset: 0, transform: `rotate(${(1 - p) * (i % 2 ? 40 : -40)}deg)`,
            transformOrigin: `${x}px ${y}px` }}>
            <Tile src={src} s={e * (0.55 + 0.45 * p)} x={x} y={y} p={1} t={0} i={i} pal={pal} />
          </div>
        );
      })}
      <Tag tag={anim.props.tag} t={t} w={w} h={h} pal={pal} />
    </div>
  );
};

const SCENES = { flow: Flow, race: Race, pile: Pile };

/** Nothing on screen is ever still: a slow push-in over the card's life and a gentle float. */
const drift = (t: number, dur: number, h: number): React.CSSProperties => ({
  transform: `translateY(${Math.sin(t * 0.9) * h * 0.01}px) scale(${1 + 0.035 * ease(t, 0, Math.max(1, dur))})`,
});

/** A scene fills its whole box: on a dark glass panel (dark), or straight on the ground (light). */
const SceneCard: React.FC<P> = (p) => {
  const View = SCENES[p.anim.type as keyof typeof SCENES];
  const light = p.theme === "light";
  const pal = PALS[p.theme ?? "dark"];
  const pad = Math.min(p.w, p.h) * (light ? 0.04 : 0.08);
  return (
    <div style={{ position: "relative", width: p.w, height: p.h, boxSizing: "border-box", fontFamily: p.family,
      ...(light ? {} : { borderRadius: Math.min(p.w, p.h) * 0.12, background: GLASS, backdropFilter: "blur(22px)",
        border: `1.5px solid ${pal.line}`, boxShadow: `0 ${p.h * 0.04}px ${p.h * 0.14}px rgba(0,0,0,0.45)` }) }}>
      <div style={{ position: "absolute", left: pad, top: pad, right: pad, bottom: pad, ...drift(p.t, p.dur ?? 3, p.h) }}>
        <View {...p} pal={pal} w={p.w - pad * 2} h={p.h - pad * 2} />
      </div>
    </div>
  );
};

const VIEWS = { counter: Counter, steps: Steps, versus: Versus, logo: Logo, keyword: Keyword };

/** t: seconds since the card landed. w, h: the card box in px. dur: how long the card is up.
 *  Dark theme: text cards sit on a white panel that hugs them. Light: straight on the ground. */
export const AnimCard: React.FC<P> = (p) => {
  if (p.anim.type in SCENES) return <SceneCard {...p} />;
  const View = VIEWS[p.anim.type as keyof typeof VIEWS];
  if (!View) return null;
  const light = p.theme === "light";
  const pad = Math.min(p.w, p.h) * (light ? 0.04 : 0.1);
  const inner = { ...p, w: p.w - pad * 2, h: p.h - pad * 2 };
  return (
    <div style={{ maxWidth: "100%", maxHeight: "100%", boxSizing: "border-box", padding: pad, fontFamily: p.family,
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", overflow: "hidden",
      ...(light ? {} : { background: PANEL, borderRadius: p.h * 0.08, boxShadow: `0 ${p.h * 0.03}px ${p.h * 0.1}px rgba(0,0,0,0.35)` }),
      ...drift(p.t, p.dur ?? 3, p.h) }}>
      <View {...inner} />
    </div>
  );
};
