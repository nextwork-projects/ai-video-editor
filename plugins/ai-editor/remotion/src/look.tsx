// The look: colours, type, radius, shadow and texture every template draws with. Filled from the user's
// brand kit and the copied creator's measured palette and fonts (plan.json "look"). The default is a
// restrained editorial look: warm paper, near-black ink, one vermilion accent, a grotesk that does the
// work and a serif for the odd italic word. Real logos and real images carry the visuals.
import React, { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender, useCurrentFrame } from "remotion";
import { getAvailableFonts } from "@remotion/google-fonts";

export type Look = {
  preset: string;
  ground: string; // the colour cards sit on (split ground, card surface)
  ink: string; // text and line art
  muted: string; // secondary text
  accent: string; // ONE accent: marks, the winning bar, the active word
  accent_ink: string; // text on the accent
  line: string; // hairlines, tracks, grid
  surface: "none" | "card" | "glass"; // overlay cards: a flat card of `ground`, legacy glass, or nothing
  radius: number; // corner radius, % of the card's short side
  shadow: "none" | "soft" | "hard"; // hard = an offset flat shadow, print style
  font: string; // Google Font for body text and labels
  font_display: string; // Google Font for the odd heading (a serif; never a default grotesk)
  font_serif: string; // Google Font for the italic emphasis word ("" = none)
  weight: number; // body weight
  weight_display: number;
  tracking: number; // display letter-spacing, em
  case: "as_is" | "lower" | "upper";
  texture: "none" | "grain" | "paper" | "print";
  texture_amount: number; // 0..1
  decor: "none" | "blocks"; // scenes: flat colour blocks on their own parallax layer
  mark: string; // highlighter colour on captures and quoted phrases
  ring: string; // ring / box / underline stroke on captures (drawn over a dark outline, readable on anything)
};

const EDITORIAL: Look = {
  preset: "editorial", ground: "#F2EEE6", ink: "#141414", muted: "#6E6A63", accent: "#E5482C", accent_ink: "#FFFFFF",
  line: "rgba(20,20,20,0.14)", surface: "card", radius: 3, shadow: "soft", font: "IBM Plex Sans", font_display: "Newsreader",
  font_serif: "Instrument Serif", weight: 600, weight_display: 600, tracking: -0.022, case: "as_is", texture: "grain",
  texture_amount: 0.55, decor: "none", mark: "#FFE14D", ring: "#FFFFFF",
};

// Display faces are never a default geometric / neo grotesk (Archivo, Geist, Inter-likes): a heading set in
// one reads as AI-made. Headings get a serif (Newsreader) or the source's own type; UI labels use IBM Plex Sans, not a default grotesk (Geist, Inter, Archivo read as AI-made too).
// The default: neutral chrome. White cards (or the real app's own surface), near-black text, a soft
// realistic shadow, no coloured grounds, no accent bars. Colour comes from the real content.
const NEUTRAL: Look = {
  ...EDITORIAL, preset: "neutral", ground: "#FFFFFF", ink: "#0D0D0D", muted: "#5F6368", accent: "#0D0D0D", accent_ink: "#FFFFFF",
  line: "rgba(0,0,0,0.1)", surface: "none", radius: 2.4, shadow: "soft", font: "IBM Plex Sans", font_display: "Newsreader", font_serif: "",
  weight: 500, weight_display: 600, tracking: -0.02, texture: "none", texture_amount: 0, decor: "none",
  mark: "#FFE14D", ring: "#FFFFFF",
};

export const LOOKS: Record<string, Look> = {
  neutral: NEUTRAL,
  editorial: EDITORIAL,
  "editorial-dark": { ...EDITORIAL, preset: "editorial-dark", ground: "#151413", ink: "#F2EEE6", muted: "#A39E95",
    line: "rgba(242,238,230,0.16)", accent: "#FF5A36" },
  // Bold flat poster looks: one saturated ground, ink, one contrasting accent. No gradients.
  "poster-red": { ...EDITORIAL, preset: "poster-red", ground: "#E2321B", ink: "#111111", muted: "rgba(17,17,17,0.62)",
    accent: "#F7D23B", accent_ink: "#111111", line: "rgba(17,17,17,0.2)", shadow: "hard", texture: "print", texture_amount: 1,
    font_display: "Anton", weight_display: 400, tracking: 0, case: "upper" },
  "poster-green": { ...EDITORIAL, preset: "poster-green", ground: "#1E4A2C", ink: "#F4EFE2", muted: "rgba(244,239,226,0.66)",
    accent: "#F5D63D", accent_ink: "#1E4A2C", line: "rgba(244,239,226,0.2)", shadow: "none", texture: "print", texture_amount: 1 },
  "poster-blue": { ...EDITORIAL, preset: "poster-blue", ground: "#1F3FD1", ink: "#F4EFE2", muted: "rgba(244,239,226,0.7)",
    accent: "#FF7A59", accent_ink: "#111111", line: "rgba(244,239,226,0.22)", shadow: "none", texture: "grain", texture_amount: 1 },
  mono: { ...EDITORIAL, preset: "mono", ground: "#FFFFFF", ink: "#0A0A0A", muted: "#777777", accent: "#0A0A0A",
    accent_ink: "#FFFFFF", line: "rgba(0,0,0,0.12)", texture: "none", decor: "none", font: "IBM Plex Sans", font_display: "IBM Plex Mono" },
  // Kept only for styles that explicitly ask for it: the old dark glass panel and mint accent.
  glass: { ...EDITORIAL, preset: "glass", ground: "rgba(14,15,19,0.78)", ink: "#F5F5F2", muted: "rgba(245,245,242,0.62)",
    accent: "#7CF2B0", accent_ink: "#0B1A12", line: "rgba(255,255,255,0.16)", surface: "glass", radius: 12,
    texture: "none", decor: "none", font: "Montserrat", font_display: "Montserrat", font_serif: "" },
};

const hexA = (c: string, a: number) => {
  const m = c.match(/^#([0-9a-f]{6})$/i);
  if (!m) return c;
  const n = parseInt(m[1], 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
};
export type Ground = "ground" | "ink" | "accent";
/** The same look on another of its own colours, so consecutive scenes do not all sit on one ground. */
export const onGround = (look: Look, g: Ground): Look =>
  g === "ink" ? { ...look, ground: look.ink, ink: look.ground, muted: hexA(look.ground, 0.62), line: hexA(look.ground, 0.18) }
    : g === "accent" ? { ...look, ground: look.accent, ink: look.ink, muted: hexA(look.ink, 0.62), line: hexA(look.ink, 0.18),
      accent: look.ground, accent_ink: look.ink }
      : look;

/** plan.json "look" may name a preset and override any key. */
export const resolveLook = (look?: Partial<Look> & { preset?: string }): Look =>
  ({ ...(LOOKS[look?.preset ?? "neutral"] ?? NEUTRAL), ...(look ?? {}) }) as Look;

export const textCase = (s: string, look: Look) =>
  look.case === "lower" ? s.toLowerCase() : look.case === "upper" ? s.toUpperCase() : s;

export const shadowOf = (look: Look, u: number) =>
  look.shadow === "hard" ? `${u * 1.1}px ${u * 1.1}px 0 ${look.ink}`
    : look.shadow === "soft" ? `0 ${u * 1.2}px ${u * 4}px rgba(0,0,0,0.22), 0 ${u * 0.2}px ${u * 0.5}px rgba(0,0,0,0.12)`
      : "none";

// ---------- fonts ----------
// No font named, or one Google Fonts does not have: Inter. system-ui is SF Pro on a Mac and another
// font on the Linux render machines, so the stills and a cloud render would differ. check.py names a font
// Google Fonts does not have (font_findings). A font that is there but fails to load stops the render with
// its name: drawing system-ui, or no captions, in its place would pass unseen.
const FALLBACK = "Inter";
const cache = new Map<string, Promise<string>>();
export const loadFamily = (name: string | undefined, weights: number[]): Promise<string> => {
  const key = `${name}:${weights.join(",")}`;
  if (!cache.has(key)) {
    const fonts = getAvailableFonts();
    const entry = fonts.find((f) => f.fontFamily === name) ?? fonts.find((f) => f.fontFamily === FALLBACK)!;
    cache.set(key, entry.load().then(async (font) => {
      const have = Object.keys(font.getInfo().fonts.normal ?? {}).map(Number);
      const near = (w: number) => (have.length ? have.reduce((a, b) => (Math.abs(b - w) < Math.abs(a - w) ? b : a)) : w);
      const loaded = font.loadFont("normal", { weights: [...new Set(weights.map((w) => String(near(w))))], subsets: ["latin"] });
      await loaded.waitUntilDone();
      return `'${loaded.fontFamily}', system-ui, sans-serif`;
    }).catch((e) => {
      cancelRender(new Error(`font '${entry.fontFamily}' did not load: ${e?.message ?? e}`));
      throw e;
    }));
  }
  return cache.get(key)!;
};

export type Fonts = { ready: boolean; body: string; display: string; serif: string };

/** Loads the look's three families. Templates mount only once `ready`, so SplitText and measureText
 *  always see the real glyphs. */
export const useFonts = (look: Look): Fonts => {
  const [f, setF] = useState<Fonts>({ ready: false, body: "system-ui", display: "system-ui", serif: "serif" });
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    Promise.all([
      loadFamily(look.font, [look.weight, 500, 700]),
      loadFamily(look.font_display, [look.weight_display]),
      look.font_serif ? loadFamily(look.font_serif, [400]) : Promise.resolve("serif"),
    ])
      .then(async ([body, display, serif]) => {
        await document.fonts.ready;
        setF({ ready: true, body, display, serif });
      })
      .finally(() => continueRender(handle));
  }, [look.font, look.font_display, look.font_serif, look.weight, look.weight_display, handle]);
  return f;
};

// ---------- texture ----------
const lum = (c: string) => {
  const m = c.match(/^#([0-9a-f]{6})$/i);
  if (!m) return 0.5;
  const n = parseInt(m[1], 16);
  return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
};

/** Film grain (re-seeded every 2 frames), paper fibre, or print (grain + halftone). Overlay blend, so it
 *  shows on light and dark grounds alike; strong enough on poster looks to read at phone size. SVG
 *  feTurbulence is a pure function of its seed, so it renders the same in every process. */
export const Texture: React.FC<{ look: Look; w: number; h: number; id: string }> = ({ look, w, h, id }) => {
  const frame = useCurrentFrame();
  if (look.texture === "none" || look.texture_amount <= 0) return null;
  const a = Math.min(1, look.texture_amount);
  const paper = look.texture === "paper";
  const seed = paper ? 7 : Math.floor(frame / 2) % 24;
  const dark = lum(look.ground) < 0.45;
  // grain is rendered at a fixed scale so a 1080 frame and a 4K frame grain alike
  return (
    <svg width={w} height={h} style={{ position: "absolute", inset: 0, pointerEvents: "none", mixBlendMode: "overlay" }}>
      <filter id={`tx-${id}`} x="0" y="0" width="100%" height="100%">
        <feTurbulence type="fractalNoise" baseFrequency={paper ? 0.012 : 0.72} numOctaves={paper ? 5 : 2} seed={seed} stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
        <feComponentTransfer>
          <feFuncR type="linear" slope={paper ? 2.2 : 2.6} intercept={paper ? -0.6 : -0.8} />
          <feFuncG type="linear" slope={paper ? 2.2 : 2.6} intercept={paper ? -0.6 : -0.8} />
          <feFuncB type="linear" slope={paper ? 2.2 : 2.6} intercept={paper ? -0.6 : -0.8} />
        </feComponentTransfer>
      </filter>
      <rect width={w} height={h} filter={`url(#tx-${id})`} opacity={(paper ? 0.5 : dark ? 0.55 : 0.45) * a} />
      {look.texture === "print" ? (
        <>
          <pattern id={`ht-${id}`} width={7} height={7} patternUnits="userSpaceOnUse" patternTransform="rotate(18)">
            <circle cx={3.5} cy={3.5} r={1.15} fill={dark ? "#fff" : "#000"} />
          </pattern>
          <rect width={w} height={h} fill={`url(#ht-${id})`} opacity={0.22 * a} />
        </>
      ) : null}
    </svg>
  );
};
