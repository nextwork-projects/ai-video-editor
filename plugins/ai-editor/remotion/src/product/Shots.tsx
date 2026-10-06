// The shot library beyond the camera-on-a-page shot: every one is made of the site's real captures or its
// real recorded click-throughs. Each takes the shot's local time t and draws the whole frame.
//   macro  a crop so close the page has depth of field: a sharp band racks focus from one element to another
//   stack  three real screens in an isometric stack that fans apart
//   push   the camera pushes into a component until it becomes the next screen (a match cut)
//   split  two real click-throughs side by side (stacked on a vertical frame)
//   orbit  one lifted component turning slowly in 3D, its shadow sliding the other way on the page below
//   whip   a whip pan from one page to the next, motion-blurred
//   grid   the site's real components flying in to a grid
//   type   a few of the site's words typed in its own font, low left (never a centred heading + subline)
//   Keycaps: the keyboard-shortcut moment drawn over a flow, the key pressing as the UI answers
import React from "react";
import { AbsoluteFill, Img, staticFile, useVideoConfig } from "remotion";
import { prog } from "../motion";
import { clamp01, FlowRef, FlowVideo, Fams, lerp, Page, ProductPlan, Rect, Shot, STYLES, shade } from "./kit";

type P = { plan: ProductPlan; shot: Shot; t: number; fams: Fams };
const dims = () => { const { width: W, height: H, fps } = useVideoConfig(); return { W, H, fps, S: Math.min(W, H) / 1080, vertical: H > W * 1.2 }; };
const radiusOf = (plan: ProductPlan) => Math.max(10, Math.min(28, plan.brand.radius_px * 1.6));

const Shot2D: React.FC<{ src: string; size: [number, number]; style?: React.CSSProperties }> = ({ src, style }) =>
  <Img src={staticFile(src)} style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", objectFit: "cover", ...style }} />;

// ---------------------------------------------------------------- macro + rack focus
export const Macro: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H, vertical } = dims();
  const dur = shot.end - shot.start;
  const m = shot.macro!;
  const vh = plan.page.vh;
  const f = prog(t, m.at, 0.9, "power2.inOut");                  // focus pull a -> b
  const c = (r: Rect) => [r[0] + r[2] / 2, r[1] + r[3] / 2];
  const [ax, ay] = c(m.a), [bx, by] = c(m.b);
  const fy = lerp(ay, by, f);
  const scroll = Math.max(0, Math.min(plan.page.height - vh, (ay + by) / 2 - vh / 2));
  const span = Math.max(m.a[2], m.b[2], Math.abs(bx - ax) + 200);
  const z = Math.min(3.2, (W * (vertical ? 1.5 : 0.95)) / span) * (1 + 0.05 * t / dur);
  // the camera follows the focus a little behind it
  const cx = lerp(ax, bx, prog(t, m.at - 0.2, 1.4, "sine.inOut")), cy = lerp(ay, by, prog(t, m.at - 0.2, 1.4, "sine.inOut")) - scroll;
  const tx = W / 2 - cx * z, ty = H / 2 - cy * z;
  const band = (fy - scroll) * z + ty;            // the in-focus line, frame px
  const w = H * 0.16;
  const mask = `linear-gradient(to bottom, transparent ${band - w * 1.6}px, black ${band - w * 0.5}px, black ${band + w * 0.5}px, transparent ${band + w * 1.6}px)`;
  const world = (blur: number) => (
    <div style={{ position: "absolute", inset: 0, transform: `perspective(${1400}px) rotateX(18deg)`, transformOrigin: `50% ${band}px` }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: plan.page.vw, height: vh, transformOrigin: "0 0",
        transform: `translate(${tx}px, ${ty}px) scale(${z})`, filter: blur ? `blur(${blur / z}px)` : undefined }}>
        <Page plan={plan} scroll={scroll} vh={vh} />
      </div>
    </div>
  );
  return <AbsoluteFill>{world(14)}<div style={{ position: "absolute", inset: 0, WebkitMaskImage: mask, maskImage: mask }}>{world(0)}</div></AbsoluteFill>;
};

// ---------------------------------------------------------------- isometric stack fanning apart
export const Stack: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H, S, vertical } = dims();
  const dur = shot.end - shot.start;
  const scr = (shot.screens ?? []).slice(0, 3);
  const fan = prog(t, 0.15, Math.min(1.8, dur * 0.6), "power3.inOut");
  const w = W * (vertical ? 1.15 : 0.74), r = radiusOf(plan);
  const spin = -36 + 6 * prog(t, 0, dur, "sine.inOut");
  return (
    <AbsoluteFill style={{ perspective: 2600 * S, perspectiveOrigin: "50% 40%" }}>
      <div style={{ position: "absolute", left: W / 2, top: H * (vertical ? 0.5 : 0.52), transformStyle: "preserve-3d",
        transform: `rotateX(54deg) rotateZ(${spin}deg) scale(${1 + 0.05 * t / dur})` }}>
        {scr.map((s, i) => {
          const h = w * (s.size[1] / s.size[0]);
          const z = (i - (scr.length - 1) / 2) * H * 0.24 * fan;
          return <div key={i} style={{ position: "absolute", left: -w / 2, top: -h / 2, width: w, height: h, borderRadius: r, overflow: "hidden",
            transform: `translateZ(${z}px) translateY(${-(i - 1) * h * 0.06 * fan}px)`,
            boxShadow: `0 ${40 * S}px ${120 * S}px ${shade(plan.brand.dark, 1)}, 0 0 0 ${1.5 * S}px rgba(${plan.brand.dark ? "255,255,255,0.12" : "0,0,0,0.08"})` }}>
            <Shot2D src={s.src} size={s.size} />
          </div>;
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- push-through into the next screen
export const Push: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H, vertical } = dims();
  const dur = shot.end - shot.start;
  const p = shot.push!;
  const vh = plan.page.vh;
  const [x, y, w, h] = p.rect;
  const scroll = Math.max(0, Math.min(plan.page.height - vh, y + h / 2 - vh / 2));
  const k = prog(t, dur * 0.25, dur * 0.7, "expo.in");           // the dive
  // a tall frame starts already inside the page (fit its height), never a thin strip of it
  const z0 = vertical ? (H * 0.9) / vh : Math.min(W / plan.page.vw, H / vh) * 1.1, z1 = Math.max(W / w, H / h) * 1.15;
  const z = z0 * Math.pow(z1 / z0, k);
  const cx = x + w / 2, cy = y + h / 2 - scroll;
  const tx = W / 2 - cx * z, ty = H / 2 - cy * z;
  // the next screen grows out of the component's own rect
  const q = prog(t, dur * 0.7, dur * 0.3, "power2.out");
  const rx = tx + x * z, ry = ty + (y - scroll) * z, rw = w * z, rh = h * z;
  const nx = lerp(rx, 0, q), ny = lerp(ry, 0, q), nw = lerp(rw, W, q), nh = lerp(rh, H, q);
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 0, top: 0, width: plan.page.vw, height: vh, transformOrigin: "0 0", transform: `translate(${tx}px, ${ty}px) scale(${z})`,
        filter: k > 0.6 ? `blur(${(k - 0.6) * 10}px)` : undefined }}>
        <Page plan={plan} scroll={scroll} vh={vh} />
      </div>
      {t > dur * 0.66 ? <div style={{ position: "absolute", left: nx, top: ny, width: nw, height: nh, overflow: "hidden", opacity: clamp01((t - dur * 0.66) / 0.12),
        borderRadius: (1 - q) * radiusOf(plan) }}><Shot2D src={p.to.src} size={p.to.size} /></div> : null}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- split screen of two real flows
const FlowBox: React.FC<{ flow: FlowRef; x: number; y: number; w: number; h: number; plan: ProductPlan; fps: number; S: number }> = ({ flow, x, y, w, h, plan, fps, S }) => {
  const [vw, vh] = flow.viewport;
  const z = Math.max(w / vw, h / vh);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: radiusOf(plan) * S, overflow: "hidden",
      boxShadow: `0 ${24 * S}px ${70 * S}px ${shade(plan.brand.dark, 0.9)}, 0 0 0 ${1.2 * S}px rgba(${plan.brand.dark ? "255,255,255,0.1" : "0,0,0,0.07"})` }}>
      <div style={{ position: "absolute", left: (w - vw * z) / 2, top: 0, width: vw, height: vh, transformOrigin: "0 0", transform: `scale(${z})` }}>
        <FlowVideo flow={flow} fps={fps} />
      </div>
    </div>
  );
};
export const Split: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H, S, fps, vertical } = dims();
  const dur = shot.end - shot.start;
  const [a, b] = shot.pair!;
  const g = W * 0.025, push = 1 + 0.03 * t / dur;
  const inA = prog(t, 0, 0.6, "power3.out"), inB = prog(t, 0.15, 0.6, "power3.out");
  // each recording whole and readable: fit to the box's width, the box as tall as the recording
  const bw = vertical ? W * 0.9 : (W * 0.92 - g) / 2;
  const box = { w: bw, h: Math.min(vertical ? (H * 0.84 - g) / 2 : H * 0.8, (bw * a.viewport[1]) / a.viewport[0]) };
  const ox = (W - (vertical ? box.w : box.w * 2 + g)) / 2, oy = (H - (vertical ? box.h * 2 + g : box.h)) / 2;
  return (
    <AbsoluteFill style={{ transform: `scale(${push})` }}>
      <div style={{ opacity: inA, transform: `translateY(${(1 - inA) * 40 * S}px)` }}>
        <FlowBox flow={a} x={ox} y={oy} w={box.w} h={box.h} plan={plan} fps={fps} S={S} /></div>
      <div style={{ opacity: inB, transform: `translateY(${(1 - inB) * 40 * S}px)` }}>
        <FlowBox flow={b} x={vertical ? ox : ox + box.w + g} y={vertical ? oy + box.h + g : oy} w={box.w} h={box.h} plan={plan} fps={fps} S={S} /></div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- parallax orbit around a lifted component
export const Orbit: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H, S, vertical } = dims();
  const dur = shot.end - shot.start;
  const el = shot.orbit!;
  const [x, y, w, h] = el.crop;
  const vh = plan.page.vh;
  const scroll = Math.max(0, Math.min(plan.page.height - vh, y + h / 2 - vh / 2));
  const a = Math.sin((t / dur - 0.5) * Math.PI) * 16;            // degrees, slow
  const rise = prog(t, 0, 0.9, "power3.out");
  const f = Math.min((W * (vertical ? 0.86 : 0.6)) / w, (H * 0.6) / h);
  const zb = Math.max(W / plan.page.vw, H / vh) * 1.25;
  return (
    <AbsoluteFill style={{ perspective: 1800 * S }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: plan.page.vw, height: vh, transformOrigin: "50% 50%",
        transform: `translate(${(W - plan.page.vw) / 2 - a * 6 * S}px, ${(H - vh) / 2}px) scale(${zb}) rotateX(28deg)`,
        filter: `blur(${6 + 4 * rise}px) brightness(${plan.brand.dark ? 0.6 : 0.97})`, opacity: 0.85 }}>
        <Page plan={plan} scroll={scroll} vh={vh} />
      </div>
      {/* the shadow on the page below, sliding the other way */}
      <div style={{ position: "absolute", left: W / 2 - w * f * 0.45 + a * 5 * S, top: H / 2 + h * f * 0.42, width: w * f * 0.9, height: h * f * 0.22,
        borderRadius: "50%", background: shade(plan.brand.dark, 1.3), filter: `blur(${40 * S}px)`, opacity: rise }} />
      <Img src={staticFile(el.src)} style={{ position: "absolute", left: W / 2 - (w * f) / 2, top: H / 2 - (h * f) / 2 - rise * 20 * S, width: w * f, height: h * f,
        borderRadius: Math.min(radiusOf(plan), plan.brand.radius_px) * f, transform: `rotateY(${a}deg) rotateX(${8 - 4 * rise}deg) translateZ(${rise * 60 * S}px)`,
        boxShadow: `0 ${20 * S}px ${50 * S}px ${shade(plan.brand.dark, 0.7)}` + (plan.brand.dark ? `, 0 0 0 ${S}px rgba(255,255,255,0.14)` : "") }} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- whip pan between two pages
export const Whip: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H } = dims();
  const dur = shot.end - shot.start;
  const [a, b] = shot.screens!;
  const at = dur * 0.45, len = 0.42;
  const p = prog(t, at - len / 2, len, "expo.inOut");
  const v = Math.max(0, 1 - Math.abs(t - at) / (len / 2));      // speed, 0..1, peak mid-whip
  const drift = (s: number) => 1.04 + 0.03 * s;
  const strip = (dx: number) => (
    <div style={{ position: "absolute", left: dx, top: 0, width: W * 2.1, height: H }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, overflow: "hidden" }}><Shot2D src={a.src} size={a.size} style={{ transform: `scale(${drift(t / dur)})` }} /></div>
      <div style={{ position: "absolute", left: W * 1.1, top: 0, width: W, height: H, overflow: "hidden" }}><Shot2D src={b.src} size={b.size} style={{ transform: `scale(${drift(1 - t / dur)})` }} /></div>
    </div>
  );
  const x = -W * 1.1 * p;
  // motion blur: the same strip sampled along its path, the way a shutter smears a fast pan
  const n = v > 0.05 ? 9 : 1;
  return <AbsoluteFill style={{ background: plan.brand.ground }}>
    {Array.from({ length: n }, (_, i) => <div key={i} style={{ position: "absolute", inset: 0, opacity: n > 1 ? 1 / (i + 1) : 1, mixBlendMode: "normal" }}>
      {strip(x + (n > 1 ? (i / (n - 1) - 0.5) * W * 0.22 * v : 0))}</div>)}
  </AbsoluteFill>;
};

// ---------------------------------------------------------------- the site's components assembling into a grid
export const Grid: React.FC<P> = ({ plan, shot, t }) => {
  const { W, H, S, vertical } = dims();
  const dur = shot.end - shot.start;
  const els = (shot.grid ?? []).slice(0, vertical ? 6 : 6);
  const cols = vertical ? 2 : 3, rows = Math.ceil(els.length / cols);
  const g = W * 0.022;
  const cw = (W * (vertical ? 0.96 : 0.9) - g * (cols - 1)) / cols, ch = (H * (vertical ? 0.86 : 0.84) - g * (rows - 1)) / rows;
  const ox = (W - (cw * cols + g * (cols - 1))) / 2, oy = (H - (ch * rows + g * (rows - 1))) / 2;
  const push = 1 + 0.04 * prog(t, 0.6, dur, "sine.inOut");
  const spring = STYLES[plan.variant]?.words.spring;
  return (
    <AbsoluteFill style={{ transform: `scale(${push})` }}>
      {els.map((e, i) => {
        const p = prog(t, 0.1 + i * 0.11, 0.75, spring ? "back.out(1.6)" : "power3.out");
        const [w, h] = [e.crop[2], e.crop[3]];
        const f = Math.min(cw / w, ch / h);
        const x = ox + (i % cols) * (cw + g) + (cw - w * f) / 2, y = oy + Math.floor(i / cols) * (ch + g) + (ch - h * f) / 2;
        return <Img key={i} src={staticFile(e.src)} style={{ position: "absolute", left: x, top: y, width: w * f, height: h * f, opacity: clamp01(p * 1.5),
          borderRadius: Math.min(radiusOf(plan), plan.brand.radius_px) * f,
          transform: `translateY(${(1 - p) * 140 * S}px) scale(${0.92 + 0.08 * p})`, filter: `blur(${(1 - Math.min(1, p)) * 12}px)`,
          boxShadow: `0 ${16 * S}px ${44 * S}px ${shade(plan.brand.dark, 0.6)}` + (plan.brand.dark ? `, 0 0 0 ${S}px rgba(255,255,255,0.12)` : "") }} />;
      })}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- a type moment in the site's own font
export const Type: React.FC<P> = ({ plan, shot, t, fams }) => {
  const { W, H, S, vertical } = dims();
  const dur = shot.end - shot.start;
  const st = STYLES[plan.variant] ?? STYLES.linear;
  const raw = shot.text ?? "";
  const text = st.words.lower ? raw.toLowerCase() : st.words.caps ? raw.toUpperCase() : raw;
  const cps = 16;
  const n = Math.min(text.length, Math.floor(Math.max(0, t - 0.3) * cps));
  const out = prog(t, dur - 0.3, 0.3, "power2.in");
  const caret = t < 0.3 + text.length / cps + 0.6 ? 1 : (Math.floor(t * 2) % 2);
  const size = (st.words.mono ? 40 : 92) * S * (vertical ? 1.1 : 1);
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: W * 0.07, bottom: H * (vertical ? 0.2 : 0.16), maxWidth: W * 0.8, fontFamily: st.words.mono ? "ui-monospace, Menlo, monospace" : fams.display,
        fontWeight: plan.brand.display.weight, fontSize: size, lineHeight: 1.05, color: plan.brand.ink, letterSpacing: `${plan.brand.display.tracking_em}em`,
        opacity: 1 - out, filter: `blur(${out * 10}px)`, transform: `translateX(${-12 * S * (t / dur)}px)` }}>
        {text.slice(0, n)}<span style={{ display: "inline-block", width: size * 0.06, height: size * 0.9, marginLeft: size * 0.06, verticalAlign: "-0.1em",
          background: plan.brand.ink, opacity: caret * (1 - out) }} />
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- keycaps over a flow
const KEYNAME: Record<string, string> = { Enter: "return", Meta: "⌘", Control: "ctrl", Shift: "⇧", Alt: "⌥", Escape: "esc", ArrowDown: "↓", ArrowUp: "↑", Tab: "tab" };
export const Keycaps: React.FC<{ plan: ProductPlan; caps: { t: number; label: string }[]; t: number; fams: Fams }> = ({ plan, caps, t, fams }) => {
  const { W, H, S } = dims();
  const cur = [...caps].reverse().find((c) => t >= c.t - 0.45 && t < c.t + 1.3);
  if (!cur) return null;
  const keys = cur.label.split("+").map((k) => KEYNAME[k] ?? k);
  const p = prog(t, cur.t - 0.45, 0.35, "back.out(1.8)"), out = prog(t, cur.t + 1.0, 0.3, "power2.in");
  const press = Math.max(0, 1 - Math.abs(t - cur.t) / 0.1);
  const dark = plan.brand.dark;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, bottom: H * 0.08, display: "flex", justifyContent: "center", gap: 14 * S,
      opacity: p * (1 - out), transform: `translateY(${(1 - p) * 30 * S}px)` }}>
      {keys.map((k, i) => (
        <div key={i} style={{ minWidth: 84 * S, height: 84 * S, padding: `0 ${22 * S}px`, borderRadius: 18 * S, display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: fams.body, fontSize: (k.length > 2 ? 30 : 40) * S, fontWeight: 500, color: dark ? "#F2F2F2" : "#1A1A1A",
          background: dark ? "linear-gradient(#2A2A2C, #1C1C1E)" : "linear-gradient(#FFFFFF, #ECECEC)",
          boxShadow: `0 ${(6 - 5 * press) * S}px 0 ${dark ? "#0A0A0B" : "#C9C9C9"}, 0 ${14 * S}px ${30 * S}px rgba(0,0,0,${dark ? 0.6 : 0.18}), inset 0 ${S}px 0 rgba(255,255,255,${dark ? 0.08 : 0.9})`,
          transform: `translateY(${5 * press * S}px)` }}>{k}</div>
      ))}
    </div>
  );
};

