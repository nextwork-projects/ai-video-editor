// Shared pieces of the product video: plan types, the style families, geometry, the page, the words.
import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, staticFile } from "remotion";
import { ease, prog } from "../motion";

export type Rect = [number, number, number, number];
export type Key = { t: number; scroll: number; rect: Rect };
export type Crop = { src: string; size: [number, number]; crop: Rect; hover_src?: string };
export type Screen = { src: string; size: [number, number] };
export type FlowRef = { src: string; size: [number, number]; viewport: [number, number]; from: number;
  keys?: Key[]; keycaps?: { t: number; label: string }[] };
export type Kind = "page" | "lift" | "media" | "end" | "flow" | "keys" | "macro" | "stack" | "push" | "split" | "orbit" | "whip" | "grid" | "type";
export type Shot = {
  kind: Kind;
  start: number; end: number;
  text?: string;
  keys?: Key[];
  cursor?: { from: [number, number]; to: [number, number]; move_at: number; click_at: number; el?: Crop };
  lift?: Crop & { at: number };
  media?: { src: string; size?: [number, number] };
  tilt?: [number, number];
  cut_in?: "cut" | "blur" | "continue";
  flow?: FlowRef;                                  // flow, keys: a recorded click-through
  macro?: { a: Rect; b: Rect; at: number };        // rack focus from a to b (page px)
  screens?: Screen[];                              // stack: 3 screens; whip: [from, to]
  push?: { rect: Rect; to: Screen };               // push-through into `to`
  pair?: [FlowRef, FlowRef];                       // split
  orbit?: Crop;                                    // the component the camera circles
  grid?: Crop[];                                   // components that assemble
  tone?: "dark" | "light";                         // the recording is darker or lighter than the site's ground
};
type Font = { family: string; weight: string; style: string; src: string };
export type Style = "linear" | "apple" | "stripe" | "arc" | "raycast";
export type ProductPlan = {
  composition?: string;
  width: number; height: number; fps: number; durationInFrames: number;
  variant: Style;
  brand: { ground: string; ink: string; muted: string; accent: string; dark: boolean; radius_px: number;
    display: { family: string; weight: number; tracking_em: number }; body: { family: string; weight: number }; fonts: Font[] };
  page: { vw: number; vh: number; tiles: { src: string; y: number; size: [number, number] }[]; height: number; domain: string };
  logo?: { src?: string; word?: string; aspect?: number };
  url: string;
  shots: Shot[];
  camera?: "linear";   // the old straight-line camera, kept only to show the before
  audio?: { mix?: string; music?: string; music_volume?: number; vo?: string; sfx?: { t: number; src: string }[] };
};
export type Fams = { display: string; body: string };

/** What each style family does with the same shots (references/style.md, measured from their films). */
export const STYLES: Record<Style, {
  tilt: boolean;            // page and flow shots as a plane in perspective
  drift: number;            // constant sideways drift, share of the frame width over a shot
  push: number;             // zoom-in over a shot on held frames
  fill: number;             // share of the stage the focus fills
  maxZ: number;
  cut: "hard" | "blur";
  words: { size: number; pos: "above" | "low-left" | "centre"; mono?: boolean; lower?: boolean; caps?: boolean; blur: boolean; spring?: boolean };
  shadow: number;           // window shadow strength
  move: string;             // camera ease
}> = {
  linear: { tilt: true, drift: 0.025, push: 0.05, fill: 0.8, maxZ: 2.6, cut: "blur", words: { size: 60, pos: "low-left", blur: true }, shadow: 0, move: "sine.inOut" },
  apple: { tilt: false, drift: 0, push: 0.04, fill: 0.86, maxZ: 3.2, cut: "hard", words: { size: 76, pos: "above", blur: false }, shadow: 1, move: "sine.inOut" },
  stripe: { tilt: false, drift: 0, push: 0.015, fill: 0.72, maxZ: 2.2, cut: "hard", words: { size: 84, pos: "low-left", blur: false }, shadow: 0.8, move: "sine.inOut" },
  arc: { tilt: false, drift: 0, push: 0.03, fill: 0.9, maxZ: 2.8, cut: "hard", words: { size: 44, pos: "centre", lower: true, blur: false, spring: true }, shadow: 0.6, move: "expo.inOut" },
  raycast: { tilt: false, drift: 0.02, push: 0.06, fill: 0.84, maxZ: 3.4, cut: "blur", words: { size: 26, pos: "low-left", mono: true, caps: true, blur: true }, shadow: 0.5, move: "sine.inOut" },
};

export const lerp = (a: number, b: number, p: number) => a + (b - a) * p;
export const lerpR = (a: Rect, b: Rect, p: number): Rect => [0, 1, 2, 3].map((i) => lerp(a[i], b[i], p)) as Rect;
export const clamp01 = (x: number) => Math.min(1, Math.max(0, x));

/** A camera move between two framings that feels like one steady zoom: the size changes in log space
 *  (exp of the lerped log), so every frame scales by the same factor, and the centre travels in step
 *  with the zoom (zooming about the focal point, never zoom-then-pan). */
export const zoomR = (a: Rect, b: Rect, p: number): Rect => {
  const w = Math.exp(lerp(Math.log(a[2]), Math.log(b[2]), p)), h = Math.exp(lerp(Math.log(a[3]), Math.log(b[3]), p));
  // the centre moves by how far the zoom has gone, not by time, so the target holds still on screen
  const q = Math.abs(b[2] - a[2]) > 1 ? (w - a[2]) / (b[2] - a[2]) : p;
  const cx = lerp(a[0] + a[2] / 2, b[0] + b[2] / 2, q), cy = lerp(a[1] + a[3] / 2, b[1] + b[3] / 2, q);
  return [cx - w / 2, cy - h / 2, w, h];
};

/** The camera at time t inside a shot: page scroll and the rect (page px) to frame. */
export const camAt = (keys: Key[], t: number, move: string, linear = false) => {
  if (t <= keys[0].t) return keys[0];
  for (let i = 0; i < keys.length - 1; i++) {
    const a = keys[i], b = keys[i + 1];
    if (t <= b.t) {
      const p = ease(move)(clamp01((t - a.t) / Math.max(1e-3, b.t - a.t)));
      return { t, scroll: lerp(a.scroll, b.scroll, p), rect: linear ? lerpR(a.rect, b.rect, p) : zoomR(a.rect, b.rect, p) };
    }
  }
  return keys[keys.length - 1];
};

export type Stage = { x: number; y: number; w: number; h: number };
/** Scale and offset that put `r` (window px) in the middle of the stage, never smaller than the whole window,
 *  and once the window is bigger than the frame, never showing the ground beside it. */
export const frameOn = (r: Rect, winW: number, winH: number, st: Stage, W: number, H: number, fill: number, maxZ: number, top = false) => {
  // a tall frame crops into a wide page, as Apple's vertical cuts crop a device
  const tall = st.h > st.w * 1.2;
  const zFit = tall ? (st.h * 0.9) / winH : Math.min(st.w / winW, st.h / winH);
  const z = Math.min(zFit * maxZ, Math.max(zFit, Math.min((st.w * fill * (tall ? 1.6 : 1)) / r[2], (st.h * fill) / r[3])));
  let tx = st.x + st.w / 2 - (r[0] + r[2] / 2) * z, ty = st.y + st.h / 2 - (r[1] + r[3] / 2) * z;
  if (top && r[2] / r[3] > st.w / st.h) ty = st.y + st.h * 0.04 - r[1] * z;
  if (r[2] * z > st.w) tx = st.x + st.w * 0.02 - r[0] * z;
  if (winW * z > W) tx = Math.min(0, Math.max(W - winW * z, tx)); else if (winW * z <= st.w) tx = st.x + (st.w - winW * z) / 2;
  if (winH * z > H) ty = Math.min(0, Math.max(H - winH * z, ty)); else if (winH * z <= st.h) ty = Math.min(Math.max(ty, st.y), st.y + st.h - winH * z);
  return { z, tx, ty };
};

/** The page as its viewport tiles, scrolled. */
export const Page: React.FC<{ plan: ProductPlan; scroll: number; vh: number }> = ({ plan, scroll, vh }) => {
  const { vw, tiles } = plan.page;
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: vw, height: vh, overflow: "hidden", background: plan.brand.ground }}>
      {tiles.filter((t) => t.y + vh > scroll - 10 && t.y < scroll + vh + 10).map((t) => (
        <Img key={t.src} src={staticFile(t.src)} style={{ position: "absolute", left: 0, top: t.y - scroll, width: vw, height: (t.size[1] / t.size[0]) * vw }} />
      ))}
    </div>
  );
};

/** A recorded click-through, playing from `from` s of its file, sized to its viewport in page px. */
export const FlowVideo: React.FC<{ flow: FlowRef; fps: number }> = ({ flow, fps }) => (
  <OffthreadVideo src={staticFile(flow.src)} startFrom={Math.round(flow.from * fps)} muted
    style={{ position: "absolute", left: 0, top: 0, width: flow.viewport[0], height: flow.viewport[1] }} />
);

export const shade = (dark: boolean, k: number) => `rgba(0,0,0,${(dark ? 0.6 : 0.22) * k})`;

/** Words, per style: linear low-left focusing from blur, apple big above, stripe big low-left word by word,
 *  arc small lowercase centred with a bounce, raycast tiny monospace caps. Only the site's words reach here. */
export const Words: React.FC<{ text: string; t: number; dur: number; plan: ProductPlan; fam: string; box: Stage; S: number; vertical: boolean; ink?: string }> =
  ({ text, t, dur, plan, fam, box, S, vertical, ink }) => {
    const w = STYLES[plan.variant]?.words ?? STYLES.linear.words;
    const size = w.size * S * (vertical ? 1.12 : 1);
    const shown = w.lower ? text.toLowerCase() : w.caps ? text.toUpperCase() : text;
    const words = shown.split(/\s+/);
    const out = prog(t, dur - 0.35, 0.3, "power2.in");
    const family = w.mono ? "'SF Mono', 'JetBrains Mono', ui-monospace, Menlo, monospace" : fam;
    return (
      <div style={{ position: "absolute", left: box.x, top: box.y, width: box.w, height: box.h, display: "flex", alignItems: w.pos === "low-left" ? "flex-end" : "center",
        justifyContent: w.pos === "low-left" ? "flex-start" : "center", textAlign: w.pos === "low-left" ? "left" : "center" }}>
        <div style={{ fontFamily: family, fontWeight: w.mono ? 500 : plan.brand.display.weight, fontSize: size, lineHeight: 1.06, color: ink ?? plan.brand.ink,
          letterSpacing: w.mono ? "0.14em" : `${plan.brand.display.tracking_em}em`, opacity: 1 - out, maxWidth: box.w }}>
          {words.map((x, i) => {
            const p = prog(t, 0.2 + i * (w.blur ? 0.09 : w.spring ? 0.06 : 0.12), w.blur ? 0.8 : 0.6, w.spring ? "back.out(2.2)" : w.blur ? "power2.out" : "power3.out");
            return <span key={i} style={{ display: "inline-block", whiteSpace: "pre", opacity: clamp01(p * 1.4), transform: `translateY(${(1 - p) * size * 0.35}px) scale(${w.spring ? 0.85 + 0.15 * p : 1})`,
              filter: w.blur ? `blur(${(1 - Math.min(1, p)) * size * 0.14}px)` : undefined }}>{x}{i < words.length - 1 ? " " : ""}</span>;
          })}
        </div>
      </div>
    );
  };

/** Where the words sit, per style. */
export const wordsBox = (plan: ProductPlan, W: number, H: number, vertical: boolean, band: number): Stage => {
  const pos = (STYLES[plan.variant] ?? STYLES.linear).words.pos;
  if (pos === "above") return { x: W * 0.08, y: H * 0.03, w: W * 0.84, h: band };
  if (pos === "centre") return { x: W * 0.1, y: H * (vertical ? 0.78 : 0.78), w: W * 0.8, h: H * 0.14 };
  return { x: W * 0.07, y: H * (vertical ? 0.7 : 0.64), w: W * 0.86, h: H * (vertical ? 0.22 : 0.28) };
};

/** The site's logo and its domain on its own ground: the end card. */
export const Logo: React.FC<{ plan: ProductPlan; t: number; fams: Fams; W: number; H: number }> = ({ plan, t, fams, W, H }) => {
  const S = Math.min(W, H);
  const soft = STYLES[plan.variant]?.cut === "blur";
  const p = prog(t, 0.2, soft ? 1.1 : 0.9, "power2.out");
  const u = prog(t, 0.9, 0.7, "power2.out");
  const lh = S * 0.095, aspect = plan.logo?.aspect ?? 1;
  const square = aspect < 1.8;
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: S * 0.04 }}>
      <div style={{ display: "flex", alignItems: "center", gap: lh * 0.35, opacity: p, transform: `scale(${0.97 + 0.03 * p})`,
        filter: `blur(${(1 - p) * (soft ? 14 : 6)}px)` }}>
        {plan.logo?.src ? <Img src={staticFile(plan.logo.src)} style={{ height: square ? lh : lh * 0.9, width: (square ? lh : lh * 0.9) * aspect }} /> : null}
        {plan.logo?.word && (square || !plan.logo?.src) ? <span style={{ fontFamily: fams.display, fontWeight: plan.brand.display.weight,
          fontSize: lh * 0.9, color: plan.brand.ink, letterSpacing: `${plan.brand.display.tracking_em}em` }}>{plan.logo.word}</span> : null}
      </div>
      <div style={{ fontFamily: fams.body, fontSize: S * 0.026, color: plan.brand.muted, opacity: u, letterSpacing: "0.01em",
        transform: `translateY(${(1 - u) * 8}px)` }}>{plan.url}</div>
    </AbsoluteFill>
  );
};
