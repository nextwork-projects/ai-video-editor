// The rendered product film: the site's UI states (captured as stills at 3x by record.mjs --states) laid out
// on one canvas, one camera moving through them. Nothing recorded plays back: every frame is drawn here, so
// the motion is as smooth as the plan's camera, which product-video/scripts/journey.py computes per frame
// (and checks: the focus in the safe frame, the cursor wholly in or out, no capture shown past 1:1).
//   layers  base (there), fade, plate-in (a new page rises in), pop (one region scales in), modal (the page
//           dims, a panel rises), sweep (results arriving top to bottom), type (the typed text revealed
//           character by character up to the measured caret)
//   cursor  drawn at a constant size over the canvas; a press dips it; a ring spreads where it clicks
// The camera blurs along its own path on fast moves (CameraMotionBlur, centred on the frame).
import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { CameraMotionBlur } from "@remotion/motion-blur";
import { prog } from "../motion";
import { clamp01, Fams, Logo, ProductPlan, Words, wordsBox } from "./kit";

type Layer = { plate: number; src: string; x: number; y: number; w: number; h: number; t: number; kind: string; dur: number;
  rect?: number[]; weak?: number[] | null; caret?: { left: number; top: number; lh: number; pos: [number, number][]; color: string; size: number };
  cps?: number; n?: number };
export type JourneyPlan = ProductPlan & {
  journey: true; tone: "dark" | "light"; dsf: number;
  canvas: { plates: { x: number; y: number; w: number; h: number }[]; layers: Layer[] };
  cam: [number, number, number][]; cursor: [number, number, number, number, number][]; touch?: boolean;
  clicks: { t: number; x: number; y: number }[]; words: { text: string; start: number; end: number }[];
  beats: { job: string; start: number; end: number; text?: string }[]; end: number;
};

// the same curve journey.py moves the camera on, for the layers' own entrances
const bez = (p1x: number, p1y: number, p2x: number, p2y: number) => (p: number) => {
  if (p <= 0) return 0; if (p >= 1) return 1;
  let lo = 0, hi = 1;
  for (let i = 0; i < 30; i++) { const t = (lo + hi) / 2, x = 3 * (1 - t) ** 2 * t * p1x + 3 * (1 - t) * t * t * p2x + t ** 3; if (x < p) lo = t; else hi = t; }
  const t = (lo + hi) / 2; return 3 * (1 - t) ** 2 * t * p1y + 3 * (1 - t) * t * t * p2y + t ** 3;
};
const settle = bez(0.2, 0.8, 0.2, 1);
const at = <T extends number[]>(arr: T[], f: number): number[] => {
  const i = Math.max(0, Math.min(arr.length - 1, Math.floor(f))), j = Math.min(arr.length - 1, i + 1), u = Math.min(1, Math.max(0, f - i));
  return arr[i].map((v, k) => v + (arr[j][k] - v) * u);
};
const crop = (L: Layer, r: number[]): React.CSSProperties => ({ position: "absolute", left: r[0], top: r[1], width: r[2], height: r[3], overflow: "hidden" });
const Pic: React.FC<{ L: Layer; r?: number[]; style?: React.CSSProperties }> = ({ L, r, style }) => (
  <Img src={staticFile(L.src)} style={{ position: "absolute", left: r ? L.x - r[0] : 0, top: r ? L.y - r[1] : 0, width: L.w, height: L.h, maxWidth: "none", ...style }} />
);

const LayerView: React.FC<{ L: Layer; t: number; dark: boolean }> = ({ L, t, dark }) => {
  const p = L.dur > 0 ? settle(clamp01((t - L.t) / L.dur)) : 1;
  const box: React.CSSProperties = { position: "absolute", left: L.x, top: L.y, width: L.w, height: L.h };
  const shadow = `0 30px 90px rgba(0,0,0,${dark ? 0.55 : 0.18}), 0 0 0 1px rgba(${dark ? "255,255,255,0.07" : "0,0,0,0.06"})`;
  if (L.kind === "base") return <div style={{ ...box, overflow: "hidden" }}><Pic L={L} /></div>;
  if (L.kind === "fade") return <div style={{ ...box, overflow: "hidden", opacity: p }}><Pic L={L} /></div>;
  if (L.kind === "plate-in") return <div style={{ ...box, overflow: "hidden", opacity: clamp01(p * 1.4), boxShadow: shadow, borderRadius: 14,
    transform: `translateY(${(1 - p) * 36}px) scale(${0.985 + 0.015 * p})`, transformOrigin: "50% 0%" }}><Pic L={L} /></div>;
  const r = L.rect ?? [L.x, L.y, L.w, L.h];
  if (L.kind === "pop") return <div style={{ ...crop(L, r), opacity: clamp01(p * 1.6), transform: `scale(${0.97 + 0.03 * p})`,
    filter: p < 1 ? `blur(${(1 - p) * 6}px)` : undefined }}><Pic L={L} r={r} /></div>;
  if (L.kind === "modal") {
    const w = L.weak ?? [L.x, L.y, L.w, L.h];
    const q = settle(clamp01((t - L.t - 0.06) / Math.max(0.1, L.dur)));
    return <>
      <div style={{ ...crop(L, w), opacity: clamp01(p * 1.3) }}><Pic L={L} r={w} /></div>
      <div style={{ ...crop(L, r), opacity: clamp01(q * 1.5), transform: `translateY(${(1 - q) * 18}px) scale(${0.965 + 0.035 * q})`,
        boxShadow: `0 ${24 * q}px ${70 * q}px rgba(0,0,0,${dark ? 0.5 : 0.16})`, borderRadius: 12 }}><Pic L={L} r={r} /></div>
    </>;
  }
  if (L.kind === "sweep") {
    // results arriving top to bottom: a soft edge travels down the changed block, the rows rising into place
    const w = L.weak ?? r, f = 140;
    const y = p * (w[3] + f);
    const mask = `linear-gradient(to bottom, black ${y - f}px, transparent ${y}px)`;
    return <div style={{ ...crop(L, w), WebkitMaskImage: mask, maskImage: mask }}>
      <div style={{ position: "absolute", inset: 0, transform: `translateY(${(1 - p) * 14}px)` }}><Pic L={L} r={w} /></div></div>;
  }
  if (L.kind === "type" && L.caret) {
    const c = L.caret, n = L.n ?? 0;
    const k = Math.max(0, Math.min(n, (t - L.t) * (L.cps ?? 14)));
    const i = Math.floor(k), u = k - i;
    const [cx0, line] = c.pos[i], nx = c.pos[Math.min(n, i + 1)];
    // the caret glides between characters on the same line
    const cx = nx && nx[1] === line ? cx0 + (nx[0] - cx0) * u : cx0;
    const lines = Array.from({ length: line + 1 }, (_, L2) => L2);
    const blink = t - L.t > n / (L.cps ?? 14) + 0.2 ? (Math.floor((t - L.t) * 2) % 2 === 0 ? 1 : 0.15) : 1;
    return <>
      {lines.map((L2) => {
        const wLine = L2 < line ? Math.max(...c.pos.filter((q) => q[1] === L2).map((q) => q[0])) + 2 : cx;
        const r2 = [L.x + c.left - 2, c.top + L2 * c.lh, wLine + 4, c.lh];   // plates sit at y 0: plate px = canvas px
        return <div key={L2} style={crop(L, r2)}><Pic L={L} r={r2} /></div>;
      })}
      {t < L.t + n / (L.cps ?? 14) + 1.6 ? <div style={{ position: "absolute", left: L.x + c.left + cx + 1, top: c.top + line * c.lh + c.lh * 0.12,
        width: 2, height: c.lh * 0.76, background: c.color, opacity: blink, borderRadius: 1 }} /> : null}
    </>;
  }
  return <div style={{ ...box, opacity: p }}><Pic L={L} /></div>;
};

const Canvas: React.FC<{ plan: JourneyPlan; lead: number }> = ({ plan, lead }) => {
  const { width: W, height: H, fps } = useVideoConfig();
  const f = useCurrentFrame() - lead;
  const t = f / fps;
  const [cx, cy, cw] = at(plan.cam, f);
  const k = W / cw;
  const dark = plan.tone === "dark";
  const view = [cx - cw / 2, cy - (cw * H) / W / 2, cw, (cw * H) / W];
  const sees = (L: Layer) => L.x < view[0] + view[2] + 200 && L.x + L.w > view[0] - 200 && L.y < view[1] + view[3] + 200 && L.y + L.h > view[1] - 200;
  // per plate, drop what a later finished full-page layer already covers
  const live = plan.canvas.layers.filter((L) => L.t <= t);
  const shown = live.filter((L, i) => sees(L) && !live.slice(i + 1).some((M) => M.plate === L.plate && ["base", "fade", "plate-in"].includes(M.kind)
    && t >= M.t + M.dur && M.x <= L.x && M.y <= L.y && M.x + M.w >= L.x + L.w && M.y + M.h >= L.y + L.h));
  return (
    <AbsoluteFill style={{ transformOrigin: "0 0", transform: `translate(${W / 2 - cx * k}px, ${H / 2 - cy * k}px) scale(${k})` }}>
      {plan.canvas.plates.map((p, i) => (
        <div key={`s${i}`} style={{ position: "absolute", left: p.x, top: p.y, width: p.w, height: p.h, borderRadius: 14,
          boxShadow: `0 40px 120px rgba(0,0,0,${dark ? 0.6 : 0.2}), 0 0 0 1px rgba(${dark ? "255,255,255,0.06" : "0,0,0,0.05"})`,
          opacity: live.some((L) => L.plate === i) ? 1 : 0 }} />
      ))}
      {shown.map((L, i) => <LayerView key={`${L.src}${L.t}${i}`} L={L} t={t} dark={dark} />)}
      {plan.clicks.filter((c) => t >= c.t && t < c.t + 0.6).map((c) => {
        const q = settle(clamp01((t - c.t) / 0.55));
        return <div key={c.t} style={{ position: "absolute", left: c.x - 34 * q, top: c.y - 34 * q, width: 68 * q, height: 68 * q, borderRadius: "50%",
          border: `${2 / Math.max(0.6, k)}px solid rgba(${dark ? "255,255,255" : "0,0,0"},${0.45 * (1 - q)})` }} />;
      })}
    </AbsoluteFill>
  );
};

const Cursor: React.FC<{ plan: JourneyPlan; lead: number }> = ({ plan, lead }) => {
  const { width: W, height: H } = useVideoConfig();
  const f = useCurrentFrame() - lead;
  const [x, y, a, press, hand] = at(plan.cursor, f);
  if (a < 0.01) return null;
  const [cx, cy, cw] = at(plan.cam, f);
  const k = W / cw, S = (Math.min(W, H) / 1080) * 1.25;
  const sx = (x - cx) * k + W / 2, sy = (y - cy) * k + H / 2;
  if (plan.touch) return <div style={{ position: "absolute", left: sx - 22 * S, top: sy - 22 * S, width: 44 * S, height: 44 * S, borderRadius: "50%",
    background: "rgba(150,150,150,0.3)", border: `${2 * S}px solid rgba(255,255,255,0.85)`, opacity: a, transform: `scale(${1 - 0.14 * press})` }} />;
  const shape = hand > 0.5
    ? <path d="M9 3.5c0-1.4 1-2.5 2.3-2.5S13.6 2.1 13.6 3.5V13l.6-.2c1.3-.4 2.6.3 2.9 1.5l.2.6.5-.2c1.3-.4 2.6.3 2.9 1.5l.1.5.4-.1c1.3-.3 2.6.5 2.8 1.8l.8 6c.3 2.4-.4 4.8-1.9 6.7L21 33H10.2l-5.3-8.6c-.7-1.2-.4-2.7.7-3.4 1.1-.7 2.5-.4 3.3.6L9 22V3.5z" fill="#fff" stroke="#111" strokeWidth={1.6} strokeLinejoin="round" />
    : <path d="M3 2 L3 31 L10 24.5 L14.6 35.2 L19.4 33.2 L14.8 22.6 L24 22.6 Z" fill="#111" stroke="#fff" strokeWidth={2.2} strokeLinejoin="round" />;
  return <svg width={28 * S} height={40 * S} viewBox={hand > 0.5 ? "-2 0 30 36" : "0 0 28 40"} style={{ position: "absolute", left: sx - (hand > 0.5 ? 9 : 3) * S, top: sy - 2 * S,
    opacity: a, transform: `scale(${1 - 0.14 * press})`, transformOrigin: "3px 2px", filter: `drop-shadow(0 ${3 * S}px ${5 * S}px rgba(0,0,0,0.4))` }}>{shape}</svg>;
};

export const Journey: React.FC<{ plan: JourneyPlan; fams: Fams }> = ({ plan, fams }) => {
  const { width: W, height: H, fps } = useVideoConfig();
  const frame = useCurrentFrame();
  const t = frame / fps;
  const S = Math.min(W, H) / 1080;
  const vertical = H > W * 1.2;
  const dark = plan.tone === "dark";
  const ground = dark ? "#0B0A0A" : plan.brand.ground;
  // the camera's speed this frame (frame px): fast moves get a shutter
  const a = at(plan.cam, frame), b = at(plan.cam, Math.min(plan.cam.length - 1, frame + 1));
  const speed = Math.hypot((b[0] - a[0]) * (W / a[2]), (b[1] - a[1]) * (W / a[2])) + Math.abs(Math.log(b[2] / a[2])) * W;
  const blur = speed > 7;
  const out = prog(t, plan.end - 0.15, 0.7, "power2.inOut");
  const word = plan.words.find((w) => t >= w.start && t < w.end);
  const ink = dark ? "#F4F2EF" : undefined;
  const sg = dark ? "#0B0A0A" : plan.brand.ground;
  const scene = (lead: number) => <AbsoluteFill><Canvas plan={plan} lead={lead} /><Cursor plan={plan} lead={lead} /></AbsoluteFill>;
  return (
    <AbsoluteFill style={{ background: ground }}>
      {/* gentle light falloff: the middle of the frame a little lifted, the corners a little down */}
      <AbsoluteFill style={{ background: `radial-gradient(ellipse 70% 60% at 50% 42%, ${dark ? "rgba(255,240,225,0.07)" : "rgba(255,255,255,0.5)"}, transparent 70%)` }} />
      {t < plan.end + 0.6 ? (
        <AbsoluteFill style={{ opacity: 1 - out, filter: out > 0.01 ? `blur(${out * 16}px)` : undefined }}>
          {/* inside the blur, Freeze runs half a frame to a frame ahead: lead 0.75 centres the shutter on this frame */}
          {blur ? <CameraMotionBlur samples={6} shutterAngle={180}>{scene(0.75)}</CameraMotionBlur> : scene(0)}
          <AbsoluteFill style={{ pointerEvents: "none", background: `radial-gradient(ellipse 120% 90% at 50% 45%, transparent 60%, rgba(0,0,0,${dark ? 0.35 : 0.08}) 100%)` }} />
          {word ? <>
            <AbsoluteFill style={{ background: `linear-gradient(to top, ${sg} 0%, ${sg}D0 22%, ${sg}00 46%)`,
              opacity: clamp01(Math.min((t - word.start) / 0.4, (word.end - t) / 0.4)) }} />
            <Words text={word.text} t={t - word.start} dur={word.end - word.start} plan={plan} fam={fams.display}
              box={wordsBox(plan, W, H, vertical, 0)} S={S} vertical={vertical} ink={ink} />
          </> : null}
        </AbsoluteFill>
      ) : null}
      {t >= plan.end ? <AbsoluteFill style={{ background: plan.brand.ground, opacity: prog(t, plan.end, 0.5, "power2.out") }}>
        <Logo plan={plan} t={t - plan.end} fams={fams} W={W} H={H} />
      </AbsoluteFill> : null}
    </AbsoluteFill>
  );
};
