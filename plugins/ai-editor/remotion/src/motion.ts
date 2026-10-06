// Motion tokens: named eases, durations, staggers and four personalities, plus the GSAP bridge.
// Every GSAP plugin is registered here, once, at module scope. Each one is proven deterministic by
// test/determinism.mjs (same frame in two processes, and a still against the same frame of a video).
import { gsap } from "gsap";
import { CustomEase } from "gsap/CustomEase";
import { CustomWiggle } from "gsap/CustomWiggle";
import { DrawSVGPlugin } from "gsap/DrawSVGPlugin";
import { MorphSVGPlugin } from "gsap/MorphSVGPlugin";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";
import { Physics2DPlugin } from "gsap/Physics2DPlugin";
import { SplitText } from "gsap/SplitText";
import { useGsapTimeline } from "@remotion/gsap";
import { interpolate } from "remotion";

gsap.registerPlugin(CustomEase, CustomWiggle, DrawSVGPlugin, MorphSVGPlugin, MotionPathPlugin, Physics2DPlugin, SplitText);

// "ink": a pen stroke. Fast off the mark, a long soft landing.
CustomEase.create("ink", "M0,0 C0.12,0.62 0.2,0.98 1,1");
// "settle": glide in, keep the last ~7% of travel for the closing frames so nothing stops dead
// (the per-word-rise landing curve, HyperFrames, Apache-2.0).
gsap.registerEase("settle", (p: number) => {
  const S = 0.78, R = 0.07, slope = ((1 - R) / S) * 0.5;
  if (p <= 0) return 0;
  if (p >= 1) return 1;
  if (p < S) { const x = p / S, i = 1 - x; return (1 - R) * (0.5 * (1 - i * i * i) + 0.5 * x); }
  const u = (p - S) / (1 - S), b = slope * (1 - S), c = 3 * R - 2 * b, d = b - 2 * R;
  return 1 - R + b * u + c * u * u + d * u * u * u;
});
// Damped springs, normalised to end exactly on 1 (hw-callout-circle spring library, HyperFrames).
const spring = (zeta: number, response: number) => {
  const w0 = (2 * Math.PI) / response, T = Math.log(1000) / (zeta * w0), wd = w0 * Math.sqrt(1 - zeta * zeta);
  const x = (t: number) => 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + ((zeta * w0) / wd) * Math.sin(wd * t));
  const xT = x(T);
  return (p: number) => (p >= 1 ? 1 : x(p * T) / xT);
};
gsap.registerEase("spring.snappy", spring(0.72, 0.32));
gsap.registerEase("spring.bouncy", spring(0.5, 0.4));
gsap.registerEase("spring.soft", spring(0.82, 0.6));
// Anticipation + overshoot + settle in one curve: dips back ~8% first, overshoots ~4%, settles.
CustomEase.create("antic", "M0,0 C0.14,-0.02 0.22,-0.09 0.32,-0.07 0.44,-0.04 0.5,0.55 0.62,0.86 0.72,1.07 0.84,1.04 1,1");
// A softer one for calm pacing: a small dip, almost no overshoot.
CustomEase.create("antic.soft", "M0,0 C0.16,-0.01 0.24,-0.04 0.34,-0.03 0.48,0 0.56,0.7 0.7,0.93 0.82,1.01 0.9,1.005 1,1");
// A three-beat impact shake that dies away (used by slams).
CustomWiggle.create("impact", { wiggles: 4, type: "easeOut" });

export { gsap, SplitText };

export type Personality = "snappy" | "smooth" | "punchy" | "calm";
export type Motion = {
  name: Personality;
  /** Duration multiplier on every base duration. */
  k: number;
  enter: string; exit: string;
  /** Entrance with anticipation (a small wind-up before the move) and a settle. */
  antic: string; move: string; pop: string; draw: string; text: string;
  /** Seconds between staggered items. */
  stagger: number;
  /** Seconds a card takes to leave. */
  out: number;
  /** Camera push over a card's life (scale gained) and drift in % of the short side. */
  push: number; drift: number;
  /** Impact shake on slams. */
  shake: boolean;
};

export const PERSONALITIES: Record<Personality, Motion> = {
  snappy: { name: "snappy", k: 0.8, antic: "antic", enter: "expo.out", exit: "power3.in", move: "power3.inOut", pop: "back.out(1.7)",
    draw: "power2.inOut", text: "power4.out", stagger: 0.055, out: 0.32, push: 0.03, drift: 0.6, shake: false },
  smooth: { name: "smooth", k: 1, antic: "antic.soft", enter: "power3.out", exit: "power2.in", move: "sine.inOut", pop: "spring.snappy",
    draw: "ink", text: "settle", stagger: 0.08, out: 0.42, push: 0.035, drift: 0.8, shake: false },
  punchy: { name: "punchy", k: 0.7, antic: "antic", enter: "power4.out", exit: "power4.in", move: "expo.inOut", pop: "spring.bouncy",
    draw: "power3.out", text: "expo.out", stagger: 0.04, out: 0.26, push: 0.045, drift: 0.5, shake: true },
  calm: { name: "calm", k: 1.35, antic: "antic.soft", enter: "power2.out", exit: "sine.in", move: "sine.inOut", pop: "spring.soft",
    draw: "sine.inOut", text: "settle", stagger: 0.12, out: 0.6, push: 0.025, drift: 1, shake: false },
};

/** style.json "motion": {"personality": "..."} wins; otherwise the creator's measured pace picks one. */
export const pickMotion = (motion?: { personality?: string } | string, pace?: { median_shot_s?: number }): Motion => {
  const name = typeof motion === "string" ? motion : motion?.personality;
  if (name && name in PERSONALITIES) return PERSONALITIES[name as Personality];
  const s = pace?.median_shot_s;
  if (s === undefined) return PERSONALITIES.smooth;
  return PERSONALITIES[s < 1.4 ? "punchy" : s < 2.4 ? "snappy" : s < 4 ? "smooth" : "calm"];
};

/** A GSAP ease as a plain 0..1 function, for values React computes per frame (counters, captions). */
export const ease = (name: string) => gsap.parseEase(name) as (p: number) => number;

/** 0 -> 1 from `at` over `dur` seconds on a named ease. Clamped. */
export const prog = (t: number, at: number, dur: number, e = "power3.out") =>
  ease(e)(interpolate(t, [at, at + Math.max(1e-3, dur)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));

/** Seeded random, so bursts and wobbles are the same in every process. mulberry32. */
export const rng = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

type Q = (sel: string) => Element[];
/** The bridge: one paused, frame-seeked timeline per template. `q` is the scoped selector. */
export const useTl = <T extends Element = HTMLDivElement>(
  build: (tl: gsap.core.Timeline, q: Q, scope: T) => void, deps: unknown[]) =>
  useGsapTimeline<T>(({ timeline, selector, scope }) => build(timeline, selector as Q, scope), { dependencies: deps });

/** A card's ambient move while up, from the creator's graphics.secondary_motion (plan.py deals one per card):
 *  still (none), push (scale only), drift (move only); video or unset: both. */
export type Ambient = "still" | "push" | "drift" | "video";

/** The camera every card rides: a slow push and a drift over its life, layers marked data-depth moving
 *  against it for parallax (depth 1 = with the camera, 0 = still, negative = foreground). */
export const camera = (tl: gsap.core.Timeline, q: Q, root: Element, m: Motion, dur: number, u: number, ambient?: Ambient) => {
  if (ambient === "still") return;
  const push = ambient === "drift" ? 0 : m.push, drift = ambient === "push" ? 0 : m.drift;
  tl.fromTo(root, { scale: 1, x: 0, y: 0 }, { scale: 1 + push, x: -drift * u, y: -drift * 0.5 * u,
    duration: Math.max(1, dur), ease: "sine.inOut" }, 0);
  if (!drift) return;
  for (const el of q("[data-depth]")) {
    const d = Number((el as HTMLElement).dataset.depth);
    tl.fromTo(el, { x: 0, y: 0 }, { x: d * m.drift * 2.2 * u, y: d * m.drift * 0.8 * u, duration: Math.max(1, dur),
      ease: "sine.inOut" }, 0);
  }
};

// ---------- the word-labelled card timeline (GSAP skills + HyperFrames talking-head-recut) ----------

/** Every object anywhere in a card's props that carries both a spoken `word` and its `at` (plan.py turns
 *  "word" into "at", seconds after the card lands, and keeps the word). Marks carry only `at`. */
const said = (node: unknown, out: { word: string; at: number; node: object }[] = []) => {
  if (Array.isArray(node)) node.forEach((x) => said(x, out));
  else if (node && typeof node === "object") {
    const o = node as Record<string, unknown>;
    if (typeof o.word === "string" && typeof o.at === "number") out.push({ word: o.word, at: o.at, node: o });
    Object.values(o).forEach((x) => said(x, out));
  }
  return out;
};

/** When the card's own word is said, seconds after it lands. plan.py starts a card 0.1 s before its word
 *  (CARD_LEAD_S), an overlay a further 0.3 s x k (OVERLAY_LEAD_S); props.word_at wins when it is passed. */
export const landAt = (p: Record<string, any>, m: Motion, overlay = true) =>
  typeof p.word_at === "number" ? p.word_at : 0.1 + (overlay ? 0.3 * m.k : 0);

export type Pos = string | number;
/** One timeline per card, labelled with the beat's words. Defaults live in the constructor; "in" is the
 *  card's own word and every other label is a spoken word from the props ("haiku", "faster"). L(x, off)
 *  is the position parameter `label±off` for a prop object, a label name or a time (clamped at 0). */
export const wordTl = (timeline: gsap.core.Timeline, p: Record<string, any>, land: number, m: Motion) => {
  const tl = gsap.timeline({ defaults: { ease: m.enter, duration: 0.5 * m.k } });
  timeline.add(tl, 0);
  const names = new Map<object, string>(), used: Record<string, number> = { in: 1 };
  tl.addLabel("in", land);
  for (const s of said(p)) {
    const b = s.word.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "_").replace(/^_+|_+$/g, "") || "w";
    used[b] = (used[b] ?? 0) + 1;
    const n = used[b] > 1 ? `${b}_${used[b]}` : b;
    tl.addLabel(n, s.at);
    names.set(s.node, n);
  }
  const L = (x: object | string | number | undefined, off = 0): Pos => {
    const n = typeof x === "string" ? x : x && typeof x === "object" ? names.get(x) : undefined;
    const base = n !== undefined && n in tl.labels ? tl.labels[n] : typeof x === "number" ? x : Number((x as any)?.at ?? land);
    const v = base + off;
    if (n === undefined || !(n in tl.labels) || v < 0) return Math.max(0, v);
    const o = +Math.abs(off).toFixed(3);
    return o ? `${n}${off > 0 ? "+=" : "-="}${o}` : n;
  };
  return { tl, L };
};

/** Drop in just before the word: falls from above, tipped back and blurred, lands on expo.out. `px` is the
 *  fall in frame px (70 on a 1080 frame). The fall is a few % of the frame, never from the edge. */
export const dropIn = (tl: gsap.core.Timeline, el: Element | undefined, at: Pos, m: Motion, px: number) => {
  if (!el) return;
  tl.fromTo(el, { autoAlpha: 0, y: -px, rotationX: 16, scale: 0.94, filter: "blur(10px)", transformPerspective: 1400, transformOrigin: "50% 0%" },
    { autoAlpha: 1, y: 0, rotationX: 0, scale: 1, filter: "blur(0px)", duration: 0.62 * m.k, ease: "expo.out" }, at);
};

/** The hit on a spoken word: a short punch up, then an elastic settle. Put it on its own wrapper so it never
 *  fights the entrance's transform. */
export const punch = (tl: gsap.core.Timeline, el: Element | undefined, at: Pos, k = 1.025) => {
  if (!el) return;
  tl.to(el, { scale: k, duration: 0.1, ease: "power2.out" }, at);
  tl.to(el, { scale: 1, duration: 0.45, ease: "elastic.out(1, 0.5)" }, ">");
};

/** Out upward, faster than the entrance, on the personality's .in ease, blurring as it goes. */
export const exitUp = (tl: gsap.core.Timeline, el: Element | undefined, m: Motion, dur: number, px: number) => {
  if (!el || dur <= m.out * 2) return;
  const d = Math.max(0.24, m.out * 0.7);
  tl.to(el, { autoAlpha: 0, y: -px, scale: 0.97, filter: "blur(8px)", duration: d, ease: m.exit }, dur - d);
};

/** A creator's measured entrance or exit (style.json graphics.entrances[] / exits[]; plan.py deals one per card
 *  into props.enter / props.exit). ease: a GSAP name as fitted. dur: seconds (0: a hard cut). dir: the side it
 *  comes from (enter) or goes to (exit). dist: % of the frame's short side. scale: the size it starts (ends) at. */
export type Fit = { kind: "cut" | "slide" | "scale" | "fade" | "mask"; ease?: string; dur?: number;
  dir?: "left" | "right" | "top" | "bottom"; dist?: number; fade?: boolean; scale?: number };
const away = (f: Fit, U: number): gsap.TweenVars => {
  const d = (f.dist ?? 5) * U;
  if (f.kind === "slide") return { x: f.dir === "left" ? -d : f.dir === "right" ? d : 0, y: f.dir === "top" ? -d : f.dir === "bottom" ? d : 0 };
  if (f.kind === "scale") return { scale: f.scale ?? 0.85 };
  if (f.kind === "mask") return { clipPath: { left: "inset(0% 100% 0% 0%)", right: "inset(0% 0% 0% 100%)", top: "inset(0% 0% 100% 0%)" }[f.dir as string]
    ?? "inset(100% 0% 0% 0%)" };
  return {};
};
const rest = (f: Fit): gsap.TweenVars => (f.kind === "mask" ? { clipPath: "inset(0% 0% 0% 0%)" } : f.kind === "scale" ? { scale: 1 } : { x: 0, y: 0 });

/** The measured entrance, ending on `at` (the word): a hard cut shows the card on it. Hidden until it starts. */
export const fitIn = (tl: gsap.core.Timeline, el: Element | undefined, at: Pos, f: Fit, U: number) => {
  if (!el) return;
  tl.set(el, { autoAlpha: 0 }, 0);
  const d = f.dur ?? 0;
  if (f.kind === "cut" || d <= 0) { tl.set(el, { autoAlpha: 1 }, at); return; }
  const start = typeof at === "number" ? Math.max(0, at - d) : `${at}-=${+d.toFixed(3)}`;
  tl.fromTo(el, { autoAlpha: f.fade || f.kind === "fade" ? 0 : 1, ...away(f, U) },
    { autoAlpha: 1, ...rest(f), duration: d, ease: f.ease ?? "none", immediateRender: false }, start);
};

/** The measured exit, ending as the card's time runs out. A hard cut hides it on its last frame. */
export const fitOut = (tl: gsap.core.Timeline, el: Element | undefined, dur: number, f: Fit, U: number) => {
  if (!el) return;
  const d = Math.min(f.dur ?? 0, dur / 3);
  if (f.kind !== "cut" && d > 0)
    tl.to(el, { ...away(f, U), ...(f.fade || f.kind === "fade" ? { autoAlpha: 0 } : {}), duration: d, ease: f.ease ?? "none" }, dur - d);
  tl.set(el, { autoAlpha: 0 }, dur);
};

/** The whole life of an overlay card on its word-labelled timeline: the camera pushes underneath, `.cv-in`
 *  drops in just before the card's word, `.cv-hit` punches on every hit word, `.cv-in` leaves upward.
 *  hits: prop objects or times (marks, messages, items). U: 1% of the frame's short side. */
export const cardLife = (timeline: gsap.core.Timeline, q: Q, root: Element, p: Record<string, any>, m: Motion, dur: number, u: number,
  U: number, hits: (object | number | undefined)[] = []) => {
  const land = landAt(p, m);
  const { tl, L } = wordTl(timeline, p, land, m);
  camera(tl, q, root, m, dur, u, p.ambient);
  // the creator's measured entrance and exit (props.enter / exit) replace the default drop and lift
  if (p.enter) fitIn(tl, q(".cv-in")[0], L("in"), p.enter, U);
  else dropIn(tl, q(".cv-in")[0], L("in", -0.3 * m.k), m, U * 6.5);
  for (const x of hits) if (x !== undefined) punch(tl, q(".cv-hit")[0], L(x));
  if (p.exit) fitOut(tl, q(".cv-in")[0], dur, p.exit, U);
  else exitUp(tl, q(".cv-in")[0], m, dur, U * 4.6);
  return { tl, L, land };
};

/** The standard exit at the end of a card: everything leaves together, slightly up. */
export const exit = (tl: gsap.core.Timeline, root: Element, m: Motion, dur: number, u: number) => {
  if (dur <= m.out * 2) return;
  tl.to(root, { autoAlpha: 0, yPercent: -3, duration: m.out, ease: m.exit }, dur - m.out);
};
