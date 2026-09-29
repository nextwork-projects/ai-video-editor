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
import { Anim, AnimCard } from "./Anims";

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

const AnimView: React.FC<{ card: Card; t: number; font?: string }> = ({ card, t, font }) => {
  const { width, height } = useVideoConfig();
  const family = useGoogleFont(font, 700);
  const [, , w, h] = card.box;
  return <AnimCard anim={card.anim!} t={t - card.start} w={(w / 100) * width} h={(h / 100) * height} family={family} />;
};

const CardView: React.FC<{ card: Card; t: number; font?: string }> = ({ card, t, font }) => {
  const { fps, height } = useVideoConfig();
  const f = Math.round((t - card.start) * fps);
  const s = spring({ frame: f, fps, config: { damping: 13, stiffness: 180, mass: 0.7 } });
  const ease = interpolate(t - card.start, [0, 0.3], [0, 1], {
    easing: Easing.out(Easing.cubic),
    extrapolateRight: "clamp",
  });
  const out = interpolate(t, [card.end - 0.15, card.end], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const enter = {
    pop: { transform: `scale(${interpolate(s, [0, 1], [0.6, 1])})`, opacity: Math.min(1, s * 2) },
    slide: { transform: `translateY(${interpolate(s, [0, 1], [height * 0.25, 0])}px)`, opacity: 1 },
    fade: { transform: "none", opacity: ease },
    scale: { transform: `scale(${interpolate(ease, [0, 1], [0.88, 1])})`, opacity: ease },
  }[card.entrance] ?? { transform: "none", opacity: 1 };
  const [x, y, w, h] = card.box;
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
        transform: enter.transform,
        opacity: enter.opacity * out,
      }}
    >
      {card.anim ? (
        <AnimView card={card} t={t} font={font} />
      ) : card.src!.endsWith(".json") ? (
        <LottieCard src={card.src!} />
      ) : (
        <Img
          src={staticFile(card.src!)}
          style={{
            maxWidth: "100%",
            maxHeight: "100%",
            objectFit: "contain",
            borderRadius: height * 0.012,
            boxShadow: `0 ${height * 0.01}px ${height * 0.035}px rgba(0,0,0,0.45)`,
          }}
        />
      )}
    </div>
  );
};

export const StyleEdit: React.FC<Plan> = ({ video, captions, zooms, cards }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      <AbsoluteFill style={{ transform: `scale(${zoomScale(t, zooms)})`, transformOrigin: ZOOM_ORIGIN }}>
        {video ? <OffthreadVideo src={staticFile(video)} style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : null}
      </AbsoluteFill>
      {cards
        .filter((c) => t >= c.start && t < c.end)
        .map((c) => (
          <CardView key={`${c.src ?? c.anim?.type}${c.start}`} card={c} t={t} font={captions.style.font_match} />
        ))}
      <Captions style={captions.style} chunks={captions.chunks} t={t} />
    </AbsoluteFill>
  );
};
