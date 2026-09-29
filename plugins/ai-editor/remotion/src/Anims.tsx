import React from "react";
import { Easing, Img, interpolate, staticFile } from "remotion";

// Built animation cards. One idea per card, drawn on a light panel so it reads over any footage.
// Shapes: docs/CONTRACTS.md "visuals.json". Text is shown exactly as written (keep the speaker's words).
export type Anim = { type: "counter" | "steps" | "versus" | "logo" | "keyword"; props: Record<string, any> };

const INK = "#111111";
const MUTED = "#6B6B6B";
const PANEL = "rgba(255,255,255,0.96)";

// Slow ease in from `at` seconds over `dur` seconds, 0 -> 1.
const ease = (t: number, at = 0, dur = 0.7) =>
  interpolate(t, [at, at + dur], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const rise = (p: number, px: number): React.CSSProperties => ({
  opacity: p,
  transform: `translateY(${(1 - p) * px}px)`,
});

// Font size so `text` fits `w` px on one line (a bold sans glyph averages about 0.52em).
const fit = (text: string, w: number, max: number) => Math.min(max, w / (0.52 * Math.max(1, text.length)));

type P = { anim: Anim; t: number; w: number; h: number; family: string };

const Counter: React.FC<P> = ({ anim, t, w, h }) => {
  const { to, from = 0, prefix = "", suffix = "", label = "", decimals = 0 } = anim.props;
  const v = interpolate(ease(t, 0.15, 1.1), [0, 1], [Number(from), Number(to)]);
  const num = `${prefix}${v.toFixed(decimals)}${suffix}`;
  const full = `${prefix}${Number(to).toFixed(decimals)}${suffix}`;
  return (
    <>
      <div style={{ fontSize: fit(full, w * 0.86, h * 0.5), fontWeight: 800, lineHeight: 1, color: INK,
        fontVariantNumeric: "tabular-nums" }}>{num}</div>
      {label ? (
        <div style={{ ...rise(ease(t, 0.5), h * 0.05), fontSize: fit(label, w * 0.86, h * 0.13), color: MUTED,
          marginTop: h * 0.04 }}>{label}</div>
      ) : null}
    </>
  );
};

const Steps: React.FC<P> = ({ anim, t, w, h }) => {
  const items: string[] = (anim.props.items ?? []).slice(0, 4);
  const longest = items.reduce((a, b) => (b.length > a.length ? b : a), "");
  const size = Math.min(h / (items.length * 1.6 + 0.2), fit(longest, w * 0.8, h));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: size * 0.5, alignItems: "flex-start" }}>
      {items.map((it, i) => (
        <div key={i} style={{ ...rise(ease(t, 0.1 + i * 0.5), size * 0.6), display: "flex", alignItems: "center",
          gap: size * 0.45, fontSize: size, lineHeight: 1.1, color: INK }}>
          <span style={{ width: size * 1.25, height: size * 1.25, borderRadius: "50%", background: INK, color: "#fff",
            fontSize: size * 0.7, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0 }}>{i + 1}</span>
          <span style={{ fontWeight: 600 }}>{it}</span>
        </div>
      ))}
    </div>
  );
};

const Versus: React.FC<P> = ({ anim, t, w, h }) => {
  const { a = "", b = "", a_label = "", b_label = "" } = anim.props;
  // One size for both sides so neither reads as the winner.
  const big = Math.min(fit(a, w * 0.42, h * 0.3), fit(b, w * 0.42, h * 0.3));
  const small = Math.min(fit(a_label, w * 0.42, h * 0.14), fit(b_label, w * 0.42, h * 0.14));
  const col = (title: string, label: string, p: number) => (
    <div style={{ ...rise(p, h * 0.06), flex: 1, textAlign: "center" }}>
      {label ? <div style={{ fontSize: small, color: MUTED, marginBottom: h * 0.03 }}>{label}</div> : null}
      <div style={{ fontSize: big, fontWeight: 800, color: INK, lineHeight: 1.05 }}>{title}</div>
    </div>
  );
  return (
    <div style={{ display: "flex", alignItems: "center", width: w }}>
      {col(a, a_label, ease(t, 0.1))}
      <div style={{ opacity: ease(t, 0.45), fontSize: h * 0.1, color: MUTED, padding: `0 ${w * 0.03}px` }}>vs</div>
      {col(b, b_label, ease(t, 0.7))}
    </div>
  );
};

const Logo: React.FC<P> = ({ anim, t, w, h }) => {
  const { src, label = "" } = anim.props;
  const p = ease(t, 0.1);
  return (
    <>
      {src ? <Img src={staticFile(src)} style={{ ...rise(p, h * 0.05), maxHeight: h * 0.5, maxWidth: w * 0.7,
        objectFit: "contain" }} /> : null}
      {label ? <div style={{ ...rise(ease(t, 0.45), h * 0.05), fontSize: fit(label, w * 0.86, h * 0.16), fontWeight: 700,
        color: INK, marginTop: h * 0.05 }}>{label}</div> : null}
    </>
  );
};

const Keyword: React.FC<P> = ({ anim, t, w, h }) => {
  const { text = "", sub = "" } = anim.props;
  const p = ease(t, 0.05, 0.8);
  return (
    <>
      <div style={{ opacity: p, transform: `scale(${0.94 + 0.06 * p})`, fontSize: fit(text, w * 0.86, h * 0.34),
        fontWeight: 800, color: INK, lineHeight: 1.05, textAlign: "center" }}>{text}</div>
      {sub ? <div style={{ ...rise(ease(t, 0.5), h * 0.05), fontSize: fit(sub, w * 0.86, h * 0.13), color: MUTED,
        marginTop: h * 0.04 }}>{sub}</div> : null}
    </>
  );
};

const VIEWS = { counter: Counter, steps: Steps, versus: Versus, logo: Logo, keyword: Keyword };

/** t: seconds since the card landed. w, h: the card box in px. The panel hugs its content inside that box. */
export const AnimCard: React.FC<P> = (p) => {
  const View = VIEWS[p.anim.type];
  if (!View) return null;
  const pad = Math.min(p.w, p.h) * 0.1;
  const inner = { ...p, w: p.w - pad * 2, h: p.h - pad * 2 };
  return (
    <div style={{ maxWidth: "100%", maxHeight: "100%", boxSizing: "border-box", padding: pad, background: PANEL,
      borderRadius: p.h * 0.08, boxShadow: `0 ${p.h * 0.03}px ${p.h * 0.1}px rgba(0,0,0,0.35)`, fontFamily: p.family,
      display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", overflow: "hidden" }}>
      <View {...inner} />
    </div>
  );
};
