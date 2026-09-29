import React from "react";
import { Easing, Img, interpolate, staticFile } from "remotion";

// Built animation cards. One idea per card. Text cards (counter, steps, versus, logo, keyword) sit on a
// light panel; scenes (flow, race, pile) are pictures that move, on a dark glass panel.
// Shapes: docs/CONTRACTS.md "visuals.json". Text is shown exactly as written (keep the speaker's words).
export type Anim = {
  type: "counter" | "steps" | "versus" | "logo" | "keyword" | "flow" | "race" | "pile";
  props: Record<string, any>;
};

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
      {/* An explicit height: icon SVGs carry only a viewBox, so max sizes alone render them at 24 px. */}
      {src ? <Img src={staticFile(src)} style={{ ...rise(p, h * 0.05), height: h * (label ? 0.5 : 0.7),
        maxWidth: w * 0.8, objectFit: "contain" }} /> : null}
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

// ---------- Scenes: pictures that move, each part landing on its word ----------
// A part: {src (an image in images/, plan.py fills it from "icon" / "logo"), label, at (seconds after the
// card lands, plan.py fills it from "word"), off_at (from "off_word": the part dims again)}.
type Part = { src?: string; label?: string | { text: string; at?: number }[]; at?: number; off_at?: number;
  value?: number; from?: number };

const GLASS = "rgba(14,15,19,0.78)";
const LINE = "rgba(255,255,255,0.16)";
const TEXT = "#F5F5F2";
const DIM = "rgba(245,245,242,0.62)";
const ACCENT = "#7CF2B0";

// Slow ease that reads as motion, not a jump.
const glide = (t: number, at: number, dur = 0.9) =>
  interpolate(t, [at, at + dur], [0, 1], {
    easing: Easing.bezier(0.22, 1, 0.36, 1),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const labelNow = (label: Part["label"], t: number) =>
  typeof label === "string" || !label ? label ?? "" : [...label].reverse().find((l) => (l.at ?? 0) <= t)?.text ?? "";

/** A white rounded tile with a logo, icon or image in it. lit 0..1 brings it up; ring 0..1 draws the accent ring. */
const Tile: React.FC<{ src?: string; s: number; lit: number; ring?: number; x: number; y: number; letter?: string }> =
  ({ src, s, lit, ring = 0, x, y, letter }) => (
    <div style={{ position: "absolute", left: x - s / 2, top: y - s / 2, width: s, height: s, borderRadius: s * 0.26,
      background: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center",
      opacity: 0.28 + 0.72 * lit, transform: `scale(${0.86 + 0.14 * lit + 0.04 * ring})`,
      boxShadow: `0 0 0 ${s * 0.045 * ring}px ${ACCENT}, 0 0 ${s * 0.5 * ring}px ${ACCENT}88, 0 ${s * 0.06}px ${s * 0.18}px rgba(0,0,0,0.4)` }}>
      {src ? <Img src={staticFile(src)} style={{ width: s * 0.6, height: s * 0.6, objectFit: "contain" }} />
        : <span style={{ fontSize: s * 0.42, fontWeight: 800, color: INK }}>{letter}</span>}
    </div>
  );

const Tag: React.FC<{ tag?: { text: string; at?: number }; t: number; w: number; h: number }> = ({ tag, t, w, h }) => {
  if (!tag?.text) return null;
  const p = glide(t, tag.at ?? 1.2, 0.7);
  const size = Math.min(h * 0.13, w * 0.06);
  return (
    <div style={{ position: "absolute", right: 0, top: -Math.min(w, h) * 0.125 - size * 0.66, padding: `${size * 0.22}px ${size * 0.6}px`,
      borderRadius: size, background: ACCENT, color: "#0B1A12", fontSize: size, fontWeight: 800, lineHeight: 1.1,
      opacity: p, transform: `translateY(${(1 - p) * -size}px) scale(${0.8 + 0.2 * p})`, transformOrigin: "100% 0" }}>
      {tag.text}
    </div>
  );
};

/** A line that draws itself from 0 to 1, with an arrowhead pointing right once it arrives. */
const Arrow: React.FC<{ d: string; end: [number, number]; p: number; size: number; alpha?: number }> =
  ({ d, end, p, size, alpha = 1 }) => (
    <g opacity={alpha}>
      <path d={d} pathLength={1} fill="none" stroke={p >= 1 ? TEXT : DIM} strokeWidth={size * 0.035}
        strokeLinecap="round" strokeDasharray="1 1" strokeDashoffset={1 - p} />
      <path d={`M ${end[0] - size * 0.14} ${end[1] - size * 0.11} L ${end[0]} ${end[1]} L ${end[0] - size * 0.14} ${end[1] + size * 0.11}`}
        fill="none" stroke={TEXT} strokeWidth={size * 0.035} strokeLinecap="round" strokeLinejoin="round"
        opacity={interpolate(p, [0.85, 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })} />
    </g>
  );

// Flow: nodes left to right joined by arrows that draw in, the last node optionally splitting to 2-3 nodes.
const Flow: React.FC<P> = ({ anim, t, w, h }) => {
  const nodes: Part[] = anim.props.nodes ?? [];
  const split: Part[] = (anim.props.split ?? []).slice(0, 3);
  const n = nodes.length, k = split.length;
  if (!n) return null;
  const at = (p: Part, i: number) => p.at ?? 0.3 + i * 0.7;
  const labelled = nodes.some((p) => p.label);
  const S = Math.min(w / (n + 0.8 * (n - 1) + (k ? 0.8 + 0.7 * 2.7 : 0)), h * (labelled ? 0.56 : 0.7));
  const ts = k ? Math.min(S * 0.7, h / (k * 1.3)) : 0;
  const total = S * n + 0.8 * S * (n - 1) + (k ? 0.8 * S + ts * 2.7 : 0);
  const x0 = (w - total) / 2;
  const cy = h / 2 - (labelled ? S * 0.14 : 0);
  const cx = (i: number) => x0 + S / 2 + i * 1.8 * S;
  const sx = x0 + n * S + (n - 1) * 0.8 * S + 0.8 * S;
  const sy = (j: number) => h / 2 + (j - (k - 1) / 2) * ts * 1.3;
  const times = [...nodes.map(at), ...split.map((p, j) => at(p, n + j))];
  // The ring sits on the node said most recently.
  const ring = (i: number) => {
    const next = times.filter((x) => x > times[i]).sort((a, b) => a - b)[0];
    return glide(t, times[i] - 0.1, 0.5) * (next === undefined ? 1 : 1 - glide(t, next - 0.1, 0.5));
  };
  const litOf = (p: Part, i: number) => glide(t, times[i] - 0.15, 0.6) * (p.off_at === undefined ? 1 : 1 - 0.65 * glide(t, p.off_at, 0.6));
  const pad = S * 0.1;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <svg width={w} height={h} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        {nodes.slice(1).map((_, i) => {
          const a = cx(i) + S / 2 + pad, b = cx(i + 1) - S / 2 - pad;
          return <Arrow key={i} d={`M ${a} ${cy} L ${b} ${cy}`} end={[b, cy]} size={S}
            p={glide(t, times[i + 1] - 0.55, 0.55)} />;
        })}
        {split.map((p, j) => {
          const a = cx(n - 1) + S / 2 + pad, b = sx - ts * 0.14, y = sy(j), m = (a + b) / 2;
          return <Arrow key={`s${j}`} d={`M ${a} ${cy} C ${m} ${cy}, ${m} ${y}, ${b} ${y}`} end={[b, y]} size={S}
            p={glide(t, times[n + j] - 0.55, 0.55)} alpha={0.35 + 0.65 * litOf(p, n + j)} />;
        })}
      </svg>
      {nodes.map((p, i) => {
        const text = labelNow(p.label, t);
        return (
          <React.Fragment key={i}>
            <Tile src={p.src} s={S} x={cx(i)} y={cy} lit={litOf(p, i)} ring={ring(i)} letter={text.slice(0, 1)} />
            {text ? <div style={{ position: "absolute", left: cx(i) - S * 0.9, width: S * 1.8, top: cy + S * 0.58,
              textAlign: "center", fontSize: fit(text, S * 1.8, S * 0.24), fontWeight: 700, color: TEXT,
              opacity: 0.35 + 0.65 * litOf(p, i), whiteSpace: "nowrap" }}>{text}</div> : null}
          </React.Fragment>
        );
      })}
      {split.map((p, j) => {
        const text = labelNow(p.label, t), lit = litOf(p, n + j);
        return (
          <React.Fragment key={`s${j}`}>
            <Tile src={p.src} s={ts} x={sx + ts / 2} y={sy(j)} lit={lit} ring={ring(n + j)} letter={text.slice(0, 1)} />
            {text ? <div style={{ position: "absolute", left: sx + ts * 1.18, top: sy(j), transform: "translateY(-50%)",
              fontSize: fit(text, ts * 1.5, ts * 0.42), fontWeight: 700, color: TEXT, opacity: 0.35 + 0.65 * lit,
              whiteSpace: "nowrap" }}>{text}</div> : null}
          </React.Fragment>
        );
      })}
      <Tag tag={anim.props.tag} t={t} w={w} h={h} />
    </div>
  );
};

// Race: 2-3 bars, each led by a logo, growing to the values said. The biggest is the accent and counts up.
const Race: React.FC<P> = ({ anim, t, w, h }) => {
  const rows: Part[] = (anim.props.rows ?? []).slice(0, 3);
  const { prefix = "", suffix = "" } = anim.props;
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => Number(r.value) || 0), 1);
  const rh = Math.min(h / (rows.length * 1.3), w * 0.2);
  const size = rh * 0.44;
  const longest = Math.max(...rows.map((r) => `${prefix}${r.value}${suffix}`.length));
  const valW = size * 0.62 * longest + size * 0.5;
  const trackX = rh * 1.05, trackW = w - trackX - valW;
  const y0 = (h - rows.length * rh * 1.3 + rh * 0.3) / 2;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      {rows.map((r, i) => {
        const at = r.at ?? 0.3 + i * 0.8;
        const win = Number(r.value) === max;
        const grow = glide(t, at, win ? 1.6 : 0.9);
        const v = win ? interpolate(grow, [0, 1], [Number(r.from ?? 0), Number(r.value)]) : Number(r.value);
        const len = Math.max(rh * 0.36, (Number(r.value) / max) * trackW) * grow;
        const y = y0 + i * rh * 1.3 + rh / 2;
        const lit = glide(t, at - 0.4, 0.5);
        const text = labelNow(r.label, t);
        return (
          <React.Fragment key={i}>
            <Tile src={r.src} s={rh * 0.86} x={rh * 0.43} y={y} lit={0.35 + 0.65 * lit} ring={win ? glide(t, at + 1.2, 0.6) : 0}
              letter={text.slice(0, 1)} />
            <div style={{ position: "absolute", left: trackX, top: y - rh * 0.2, width: trackW, height: rh * 0.4,
              borderRadius: rh, background: "rgba(255,255,255,0.08)" }} />
            <div style={{ position: "absolute", left: trackX, top: y - rh * 0.2, width: len, height: rh * 0.4,
              borderRadius: rh, background: win ? ACCENT : "rgba(245,245,242,0.55)",
              boxShadow: win ? `0 0 ${rh * 0.4}px ${ACCENT}66` : undefined }} />
            <div style={{ position: "absolute", left: trackX + len + size * 0.35, top: y, transform: "translateY(-50%)",
              fontSize: size, fontWeight: 800, color: win ? ACCENT : TEXT, opacity: Math.min(1, grow * 3),
              fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>
              {`${prefix}${Math.round(v)}${suffix}`}
            </div>
            {text ? <div style={{ position: "absolute", left: trackX, top: y - rh * 0.52, fontSize: rh * 0.2,
              fontWeight: 700, color: DIM, opacity: lit, whiteSpace: "nowrap" }}>{text}</div> : null}
          </React.Fragment>
        );
      })}
      <Tag tag={anim.props.tag} t={t} w={w} h={h} />
    </div>
  );
};

// Pile: a source tile throws N copies of an icon into 1-3 stacks, one after another.
const Pile: React.FC<P> = ({ anim, t, w, h }) => {
  const { count = 12, src, source, at = 0.4, every = 0.09 } = anim.props;
  const stacks: Part[] = (anim.props.stacks ?? [{}, {}, {}]).slice(0, 3);
  const k = stacks.length;
  const labelled = stacks.some((s) => s.label);
  const sT = Math.min(h * 0.5, w * 0.2);
  const srcX = sT / 2 + w * 0.02, srcY = h / 2;
  const left = w * 0.38, regionW = w - left;
  const b = Math.min(h * (labelled ? 0.26 : 0.32), regionW / (k * 1.6));
  const e = b * 0.72;
  const binY = h - b / 2 - (labelled ? b * 0.42 : h * 0.02);
  const binX = (j: number) => left + regionW * ((j + 0.5) / k);
  const items = Array.from({ length: count }, (_, i) => i);
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Tile src={(source && source.src) || src} s={sT} x={srcX} y={srcY} lit={glide(t, 0, 0.5)}
        ring={glide(t, at - 0.2, 0.4) * (1 - glide(t, at + count * every, 0.5))} />
      {stacks.map((s, j) => (
        <React.Fragment key={j}>
          <Tile src={s.src} s={b} x={binX(j)} y={binY} lit={glide(t, 0.15 + j * 0.1, 0.5)} letter={labelNow(s.label, t).slice(0, 1)} />
          {s.label ? <div style={{ position: "absolute", left: binX(j) - b, width: b * 2, top: binY + b * 0.56,
            textAlign: "center", fontSize: fit(labelNow(s.label, t), b * 2, b * 0.3), fontWeight: 700, color: TEXT }}>
            {labelNow(s.label, t)}</div> : null}
        </React.Fragment>
      ))}
      {items.map((i) => {
        const j = i % k, m = Math.floor(i / k);
        const p = glide(t, at + i * every, 0.75);
        if (p <= 0) return null;
        const tx = binX(j) + (m % 2 ? 1 : -1) * e * 0.05, ty = binY - b / 2 - e * 0.42 - m * e * 0.2;
        const x = interpolate(p, [0, 1], [srcX, tx]);
        const y = interpolate(p, [0, 1], [srcY, ty]) - Math.sin(Math.PI * p) * h * 0.28;
        return <Tile key={i} src={src} s={e * (0.55 + 0.45 * p)} x={x} y={y} lit={1} />;
      })}
      <Tag tag={anim.props.tag} t={t} w={w} h={h} />
    </div>
  );
};

const SCENES = { flow: Flow, race: Race, pile: Pile };

/** A scene fills its whole box on a dark glass panel. */
const SceneCard: React.FC<P> = (p) => {
  const View = SCENES[p.anim.type as keyof typeof SCENES];
  const pad = Math.min(p.w, p.h) * 0.1;
  return (
    <div style={{ position: "relative", width: p.w, height: p.h, boxSizing: "border-box", borderRadius: Math.min(p.w, p.h) * 0.12,
      background: GLASS, backdropFilter: "blur(22px)", border: `1.5px solid ${LINE}`, fontFamily: p.family,
      boxShadow: `0 ${p.h * 0.04}px ${p.h * 0.14}px rgba(0,0,0,0.45)` }}>
      <div style={{ position: "absolute", left: pad, top: pad, right: pad, bottom: pad }}>
        <View {...p} w={p.w - pad * 2} h={p.h - pad * 2} />
      </div>
    </div>
  );
};

const VIEWS = { counter: Counter, steps: Steps, versus: Versus, logo: Logo, keyword: Keyword };

/** t: seconds since the card landed. w, h: the card box in px. The panel hugs its content inside that box. */
export const AnimCard: React.FC<P> = (p) => {
  if (p.anim.type in SCENES) return <SceneCard {...p} />;
  const View = VIEWS[p.anim.type as keyof typeof VIEWS];
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
