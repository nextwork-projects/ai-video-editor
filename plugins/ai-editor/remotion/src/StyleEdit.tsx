import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  CalculateMetadataFunction,
  Easing,
  Img,
  OffthreadVideo,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { getAvailableFonts } from "@remotion/google-fonts";
import { Lottie, LottieAnimationData } from "@remotion/lottie";
import { Anim, AnimCard, pop } from "./Anims";
import { Sfx } from "./Sfx";

// Shapes follow docs/CONTRACTS.md "plan.json". Times are seconds on the cut's timeline.
type Word = { text: string; start: number; end: number };
type Chunk = { text: string; start: number; end: number; words: Word[] };
type CaptionStyle = {
  present?: boolean;
  y_pct?: number;
  size_pct?: number;
  case?: string;
  font_match?: string;
  weight?: number;
  color?: string;
  highlight_color?: string;
  stroke?: boolean;
  box?: boolean;
  animation?: "pop" | "slide" | "word_highlight" | "none";
};
type Zoom = { start: number; end: number; scale: number; kind: "punch" | "push"; ease_s: number };
type Card = {
  src?: string; // an image or Lottie file, or
  anim?: Anim; // a built animation (Anims.tsx)
  start: number;
  end: number;
  trigger_word?: string;
  entrance: "pop" | "slide" | "fade" | "scale";
  box: [number, number, number, number];
  lane?: string; // "logo": the logo tiles' own lane
  size?: [number, number]; // image px (capture.mjs writes it), so a capture fits at its own ratio
  highlight?: { rects: [number, number, number, number][] }; // the sentence's lines, fractions of the image
};
// "split": the visual in a top panel on `ground`, the speaker in a window under the seam. Percent of the frame.
type Layout = {
  mode: "overlay" | "split";
  ground: string;
  seam: number;
  art: [number, number, number, number];
  speaker: { scale: number; x: number; y: number; origin: [number, number] };
  caption_full_y: number;
};
export type Plan = {
  video: string;
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  captions: { style: CaptionStyle; chunks: Chunk[] };
  zooms: Zoom[];
  cards: Card[];
  layout?: Layout;
};

export const calculateMetadata: CalculateMetadataFunction<Plan> = ({ props }) => ({
  width: props.width,
  height: props.height,
  fps: props.fps,
  durationInFrames: props.durationInFrames,
});

// Faces sit in the upper middle of a talking-head frame, so zooms grow from there
// and the head stays in shot.
const ZOOM_ORIGIN = "50% 30%";

const zoomScale = (t: number, zooms: Zoom[]) => {
  const z = zooms.find((z) => t >= z.start && t < z.end);
  if (!z) return 1;
  if (z.kind === "punch" || z.ease_s <= 0) return z.scale;
  const e = Math.min(z.ease_s, (z.end - z.start) / 2);
  return interpolate(t, [z.start, z.start + e, z.end - e, z.end], [1, z.scale, z.scale, 1], {
    easing: Easing.inOut(Easing.cubic),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
};

/** Loads the style's Google Font once. Falls back to a system sans if the name is unknown. */
const useGoogleFont = (name: string | undefined, weight: number) => {
  const [family, setFamily] = useState("system-ui, sans-serif");
  const [handle] = useState(() => delayRender(`font ${name}`));
  useEffect(() => {
    const entry = getAvailableFonts().find((f) => f.fontFamily === name);
    if (!entry) {
      continueRender(handle);
      return;
    }
    entry
      .load()
      .then(async (font) => {
        const have = Object.keys(font.getInfo().fonts.normal ?? {}).map(Number);
        const w = have.length ? have.reduce((a, b) => (Math.abs(b - weight) < Math.abs(a - weight) ? b : a)) : weight;
        const loaded = font.loadFont("normal", { weights: [String(w)], subsets: ["latin"] });
        await loaded.waitUntilDone();
        setFamily(`'${loaded.fontFamily}', system-ui, sans-serif`);
      })
      .finally(() => continueRender(handle));
  }, [name, weight, handle]);
  return family;
};

const Captions: React.FC<{ style: CaptionStyle; chunks: Chunk[]; t: number }> = ({ style, chunks, t }) => {
  const { fps, width, height } = useVideoConfig();
  const weight = style.weight ?? 800;
  const family = useGoogleFont(style.font_match, weight);
  const chunk = chunks.find((c) => t >= c.start && t < c.end);
  if (!chunk || style.present === false) return null;

  // size_pct is measured on vertical video, where height is the long side. Using the long
  // side keeps a 16:9 render's captions as readable on a phone as the vertical ones.
  const size = ((style.size_pct ?? 6) / 100) * Math.max(width, height);
  const color = style.color ?? "#FFFFFF";
  const hi = style.highlight_color ?? color;
  const anim = style.animation ?? "pop";
  const f = Math.round((t - chunk.start) * fps);
  const s = spring({ frame: f, fps, config: { damping: 14, stiffness: 220, mass: 0.6 } });
  const transform =
    anim === "pop"
      ? `scale(${interpolate(s, [0, 1], [0.82, 1])})`
      : anim === "slide"
        ? `translateY(${interpolate(s, [0, 1], [size * 0.6, 0])}px)`
        : "none";
  const opacity = anim === "slide" ? s : 1;
  // Active word: the one being said, held until the next one starts.
  const active = chunk.words.findIndex((w, i) => t >= w.start && t < (chunk.words[i + 1]?.start ?? chunk.end));

  return (
    <div
      style={{
        position: "absolute",
        left: "7%",
        right: "7%",
        top: `${style.y_pct ?? 70}%`,
        transform: "translateY(-50%)",
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          transform,
          opacity,
          textAlign: "center",
          fontFamily: family,
          fontWeight: weight,
          fontSize: size,
          lineHeight: 1.12,
          color,
          padding: style.box ? `${size * 0.12}px ${size * 0.3}px` : 0,
          borderRadius: size * 0.2,
          background: style.box ? "rgba(0,0,0,0.72)" : "transparent",
          WebkitTextStroke: style.stroke ? `${Math.max(2, size * 0.1)}px #000` : undefined,
          paintOrder: "stroke fill",
          textShadow: style.box ? undefined : `0 ${size * 0.04}px ${size * 0.18}px rgba(0,0,0,0.55)`,
        }}
      >
        {chunk.words.map((w, i) => {
          const on = i === active;
          const pill = anim === "word_highlight" && on;
          return (
            <React.Fragment key={i}>
            {i ? " " : null}
            <span
              style={{
                color: on && !pill ? hi : color,
                background: pill ? hi : "transparent",
                borderRadius: size * 0.15,
                padding: pill ? `0 ${size * 0.12}px` : 0,
                WebkitTextStroke: pill ? "0px" : undefined,
              }}
            >
              {w.text}
            </span>
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
};

const LottieCard: React.FC<{ src: string }> = ({ src }) => {
  const [data, setData] = useState<LottieAnimationData | null>(null);
  const [handle] = useState(() => delayRender(`lottie ${src}`));
  useEffect(() => {
    fetch(staticFile(src))
      .then((r) => r.json())
      .then(setData)
      .finally(() => continueRender(handle));
  }, [src, handle]);
  return data ? <Lottie animationData={data} style={{ width: "100%", height: "100%" }} /> : null;
};

const AnimView: React.FC<{ card: Card; t: number; font?: string; light: boolean }> = ({ card, t, font, light }) => {
  const { width, height } = useVideoConfig();
  const family = useGoogleFont(font, 700);
  const [, , w, h] = card.box;
  return <AnimCard anim={card.anim!} t={t - card.start} w={(w / 100) * width} h={(h / 100) * height} family={family}
    theme={light ? "light" : "dark"} dur={card.end - card.start} />;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const inOut = (t: number, a: number, b: number) => interpolate(t, [a, b], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });

// A capture scrolls (a highlighted sentence, or a page taller than its box) or pushes in: never a still.
const SCROLL = [0.45, 1.55]; // seconds after the card lands: travel to the highlighted sentence
const SWEEP_S = 0.35; // one highlighter stroke per line
const MARKER = "rgba(255, 213, 0, 0.45)";

/** An image card. Fitted at its own ratio as big as the box allows. A highlight (capture.mjs) or a tall
 *  page fits the box's width and travels down inside it; the highlight's lines then get a marker sweep. */
const ImageView: React.FC<{ card: Card; t: number; bw: number; bh: number; light: boolean }> = ({ card, t, bw, bh, light }) => {
  const { height } = useVideoConfig();
  const lt = t - card.start, dur = Math.max(1, card.end - card.start);
  const radius = height * (light ? 0.014 : 0.012);
  const shadow = light ? `0 ${height * 0.008}px ${height * 0.03}px rgba(20,20,30,0.16), 0 0 0 1.5px rgba(20,20,30,0.08)`
    : `0 ${height * 0.01}px ${height * 0.035}px rgba(0,0,0,0.45)`;
  const push = 1 + 0.06 * inOut(lt, 0, dur + 0.5);
  const [iw, ih] = card.size ?? [0, 0];
  if (!iw || !ih) {
    return <Img src={staticFile(card.src!)} style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain",
      borderRadius: radius, boxShadow: shadow, transform: `scale(${push})` }} />;
  }
  const rects = card.highlight?.rects ?? [];
  // Only a page much taller than its box scrolls; a banner a little taller just fits whole.
  const tall = ih / iw > (bh / bw) * 1.6;
  const f = rects.length || tall ? bw / iw : Math.min(bw / iw, bh / ih);
  const dw = iw * f, dh = ih * f, wh = Math.min(bh, dh);
  let off = 0;
  let focus = [0.5, 0.5];
  if (rects.length) {
    const cy = rects.reduce((a, r) => a + r[1] + r[3] / 2, 0) / rects.length;
    const cx = rects.reduce((a, r) => a + r[0] + r[2] / 2, 0) / rects.length;
    off = Math.min(Math.max(0, cy * dh - wh * 0.45), dh - wh) * inOut(lt, SCROLL[0], SCROLL[1]);
    focus = [cx, cy];
  } else if (tall) {
    off = (dh - wh) * inOut(lt, 0.3, dur);
  }
  return (
    <div style={{ width: dw, height: wh, overflow: "hidden", borderRadius: radius, boxShadow: shadow, background: "#fff",
      position: "relative" }}>
      <div style={{ position: "absolute", left: 0, top: -off, width: dw, height: dh, transform: `scale(${rects.length || tall ? 1 + 0.04 * inOut(lt, 0, dur + 0.5) : push})`,
        transformOrigin: `${focus[0] * 100}% ${focus[1] * 100}%` }}>
        <Img src={staticFile(card.src!)} style={{ width: dw, height: dh, display: "block" }} />
        {rects.map(([x, y, w, h], i) => {
          const p = inOut(lt, SCROLL[1] + i * SWEEP_S * 0.8, SCROLL[1] + i * SWEEP_S * 0.8 + SWEEP_S);
          const pad = h * dh * 0.12;
          return p > 0 ? (
            <div key={i} style={{ position: "absolute", left: x * dw - pad, top: y * dh - pad * 0.5, width: w * dw + pad * 2,
              height: h * dh + pad, background: MARKER, mixBlendMode: "multiply", borderRadius: pad,
              transform: `scaleX(${p})`, transformOrigin: "0 50%" }} />
          ) : null;
        })}
      </div>
    </div>
  );
};

// Timing of the layout's moves, seconds.
const PANEL_T = 0.3; // the split panel opens (and closes) over 2 x this, centred on the card's start (end)
const SWAP_S = 0.5; // overlay: a card landing this soon after the last one leaves swaps in (slide across)
const BRIDGE_S = 1.2; // split: the panel stays open across a gap this short, and the cards swap inside it
const EXIT_S = 0.4;

/** One card with its entrance, a slide-across swap with its neighbours in the same lane, and its exit.
 *  prev / next: the neighbouring cards when they swap with this one. covered: split, the panel closes over it. */
const CardView: React.FC<{ card: Card; t: number; font?: string; prev?: Card; next?: Card; covered: boolean; light: boolean }> =
  ({ card, t, font, prev, next, covered, light }) => {
  const { fps, width, height } = useVideoConfig();
  const f = Math.max(0, Math.round((t - card.start) * fps));
  const s = spring({ frame: f, fps, config: { damping: 13, stiffness: 180, mass: 0.7 } });
  const ease = interpolate(t - card.start, [0, 0.3], [0, 1], { easing: Easing.out(Easing.cubic), ...clamp });
  const [x, y, w, h] = card.box;
  const shift = (w / 100) * width * 0.3;
  const enter = prev
    ? (() => { const p = pop(t, card.start); return { transform: `translateX(${(1 - p) * shift}px)`, opacity: Math.min(1, p * 1.6) }; })()
    : light
      ? (() => { const p = pop(t, card.start - 0.1); return { transform: `scale(${0.9 + 0.1 * p})`, opacity: Math.min(1, p * 1.6) }; })()
      : ({
          pop: { transform: `scale(${interpolate(s, [0, 1], [0.6, 1])})`, opacity: Math.min(1, s * 2) },
          slide: { transform: `translateY(${interpolate(s, [0, 1], [height * 0.25, 0])}px)`, opacity: 1 },
          fade: { transform: "none", opacity: ease },
          scale: { transform: `scale(${interpolate(ease, [0, 1], [0.88, 1])})`, opacity: ease },
        }[card.entrance] ?? { transform: "none", opacity: 1 });
  // Swapping out: held until the next card lands, then slides off to the left as it slides in from the right.
  const out = next ? next.start : card.end;
  const q = covered ? 0 : inOut(t, out - EXIT_S / 2, out + EXIT_S / 2);
  const exit = next ? `translateX(${-q * shift}px)` : `scale(${1 - 0.08 * q})`;
  return (
    <div
      style={{
        position: "absolute",
        left: `${x}%`,
        top: `${y}%`,
        width: `${w}%`,
        height: `${h}%`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        transform: `${exit} ${enter.transform}`,
        opacity: enter.opacity * (1 - q),
      }}
    >
      {card.anim ? (
        <AnimView card={card} t={t} font={font} light={light} />
      ) : card.src!.endsWith(".json") ? (
        <LottieCard src={card.src!} />
      ) : (
        <ImageView card={card} t={t} bw={(w / 100) * width} bh={(h / 100) * height} light={light} />
      )}
    </div>
  );
};

type Slot = { card: Card; prev?: Card; next?: Card; from: number; to: number; covered: boolean };

/** When each card is on screen and which neighbours it swaps with. Split: cards closer than BRIDGE_S share
 *  one open panel; the last card of a run stays until the panel has closed over it. */
const slots = (cards: Card[], split: boolean): Slot[] => {
  const gap = split ? BRIDGE_S : SWAP_S;
  const lanes = new Map<string, Card[]>();
  for (const c of cards) lanes.set(c.lane ?? "", [...(lanes.get(c.lane ?? "") ?? []), c]);
  const out: Slot[] = [];
  for (const lane of lanes.values()) {
    lane.sort((a, b) => a.start - b.start);
    lane.forEach((c, i) => {
      const prev = i > 0 && c.start - lane[i - 1].end < gap ? lane[i - 1] : undefined;
      const next = i + 1 < lane.length && lane[i + 1].start - c.end < gap ? lane[i + 1] : undefined;
      const covered = split && !next;
      const to = next ? next.start + EXIT_S / 2 : c.end + (covered ? PANEL_T : EXIT_S / 2);
      out.push({ card: c, prev, next, covered, from: c.start - (split && !prev ? PANEL_T : 0), to });
    });
  }
  return out;
};

/** How far the split panel is open, 0 (speaker full frame) to 1 (split), from the runs of cards. */
const panelOpen = (t: number, cards: Card[]) => {
  const runs: [number, number][] = [];
  for (const c of [...cards].sort((a, b) => a.start - b.start)) {
    const last = runs[runs.length - 1];
    if (last && c.start - last[1] < BRIDGE_S) last[1] = Math.max(last[1], c.end);
    else runs.push([c.start, c.end]);
  }
  return Math.max(0, ...runs.map(([a, b]) => Math.min(inOut(t, a - PANEL_T, a + PANEL_T), 1 - inOut(t, b - PANEL_T, b + PANEL_T))));
};

export const StyleEdit: React.FC<Plan> = ({ video, captions, zooms, cards, layout }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;
  const split = layout?.mode === "split";
  const up = slots(cards, split).filter((s) => t >= s.from && t < s.to);
  const cardViews = up.map((s) => (
    <CardView key={`${s.card.src ?? s.card.anim?.type}${s.card.start}`} card={s.card} t={t} font={captions.style.font_match}
      prev={s.prev} next={s.next} covered={s.covered} light={split} />
  ));
  if (!split || !layout) {
    return (
      <AbsoluteFill style={{ backgroundColor: "#000" }}>
        <AbsoluteFill style={{ transform: `scale(${zoomScale(t, zooms)})`, transformOrigin: ZOOM_ORIGIN }}>
          {video ? <OffthreadVideo src={staticFile(video)} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : null}
        </AbsoluteFill>
        {cardViews}
        <Captions style={captions.style} chunks={captions.chunks} t={t} />
        <Sfx />
      </AbsoluteFill>
    );
  }
  // Split. The art sits still on the ground; the speaker's window slides down to uncover it and back up
  // to cover it, one move on one curve. The video inside moves with it so the head stays framed.
  const o = panelOpen(t, cards);
  const { scale, x, y, origin } = layout.speaker;
  const top = (layout.seam / 100) * height * o;
  const k = 1 + (scale - 1) * o;
  const r = height * 0.03 * Math.min(1, top / 40);
  const capY = interpolate(o, [0, 1], [layout.caption_full_y, captions.style.y_pct ?? layout.seam + 4.5]);
  return (
    <AbsoluteFill style={{ backgroundColor: layout.ground }}>
      {cardViews}
      <div style={{ position: "absolute", left: 0, top, width, height: height - top, overflow: "hidden",
        borderRadius: `${r}px ${r}px 0 0`, boxShadow: o > 0 ? `0 ${-height * 0.004}px ${height * 0.02}px rgba(0,0,0,${0.12 * o})` : undefined }}>
        <div style={{ position: "absolute", left: -(x / 100) * width * o, top: -(y / 100) * height * o, width: width * k,
          height: height * k, transform: `scale(${zoomScale(t, zooms)})`, transformOrigin: `${origin[0]}% ${origin[1]}%` }}>
          {video ? <OffthreadVideo src={staticFile(video)} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : null}
        </div>
      </div>
      <Captions style={{ ...captions.style, y_pct: capY }} chunks={captions.chunks} t={t} />
      <Sfx />
    </AbsoluteFill>
  );
};
