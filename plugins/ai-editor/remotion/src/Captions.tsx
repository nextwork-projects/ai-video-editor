// Captions with per-word effects, keyed from style.json "captions". Sizes are measured with
// @remotion/layout-utils against the loaded font, so a long chunk shrinks to fit instead of overflowing.
import React, { useEffect, useState } from "react";
import { continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { createTikTokStyleCaptions } from "@remotion/captions";
import { fitTextOnNLines } from "@remotion/layout-utils";
import { Motion, ease, prog } from "./motion";
import { loadFamily } from "./look";

export type Word = { text: string; start: number; end: number; emph?: boolean };
export type Chunk = { text: string; start: number; end: number; words: Word[] };
export type CaptionStyle = {
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
  /** Legacy name of `effect`. */
  animation?: "pop" | "slide" | "word_highlight" | "none";
  /** pop | slide | word_highlight | karaoke | reveal | lift | none. Default: `animation`, else pop. */
  effect?: string;
  /** Active word scale (1 = off). Default 1.08 for lift/pop, 1 otherwise. */
  active_scale?: number;
  /** Active word lift, % of the font size. Default 8 for lift. */
  active_lift?: number;
  /** Colour and scale of words marked "emph": true. */
  emphasis_color?: string;
  emphasis_scale?: number;
  /** Opacity of words not yet said (karaoke, reveal). Default 0.45 karaoke. */
  inactive_opacity?: number;
  max_lines?: number;
  width_pct?: number;
  /** false: no drop shadow (set while a scene is up: dark ink on a flat ground). */
  shadow?: boolean;
};

export const useFamily = (name: string | undefined, weight: number) => {
  const [family, setFamily] = useState<string | null>(name ? null : "system-ui, sans-serif");
  const [handle] = useState(() => delayRender(`font ${name}`));
  useEffect(() => {
    (name ? loadFamily(name, [weight]) : Promise.resolve("system-ui, sans-serif"))
      .then(async (f) => { await document.fonts.ready; setFamily(f); })
      .finally(() => continueRender(handle));
  }, [name, weight, handle]);
  return family;
};

const casing = (s: string, c?: string) => (c === "lower" ? s.toLowerCase() : c === "upper" ? s.toUpperCase() : s);

/** One caption page at time t (seconds on the same clock as the chunk). */
export const CaptionLine: React.FC<{ style: CaptionStyle; chunk: Chunk; t: number; family: string; m: Motion; boxW: number; maxSize: number }> =
  ({ style, chunk, t, family, m, boxW, maxSize }) => {
    const weight = style.weight ?? 800;
    const color = style.color ?? "#FFFFFF";
    const hi = style.highlight_color ?? color;
    const fx = style.effect ?? style.animation ?? "pop";
    const words = chunk.words.map((w) => ({ ...w, text: casing(w.text, style.case) }));
    const { fontSize } = fitTextOnNLines({ text: words.map((w) => w.text).join(" "), maxLines: style.max_lines ?? 2, maxBoxWidth: boxW,
      fontFamily: family, fontWeight: weight, maxFontSize: maxSize });
    const size = fontSize * 0.96;
    const lt = t - chunk.start;
    const enter = ease(m.pop)(Math.min(1, Math.max(0, lt / (0.38 * m.k))));
    const pageT = fx === "pop" ? `scale(${0.8 + 0.2 * enter})` : fx === "slide" ? `translateY(${(1 - prog(lt, 0, 0.35 * m.k, m.enter)) * size * 0.6}px)` : "none";
    const pageO = fx === "slide" ? prog(lt, 0, 0.2, "power1.out") : 1;
    const activeScale = style.active_scale ?? (fx === "lift" || fx === "pop" ? 1.08 : fx === "karaoke" ? 1.12 : 1);
    const lift = ((style.active_lift ?? (fx === "lift" ? 8 : 0)) / 100) * size;
    const dimmed = style.inactive_opacity ?? (fx === "karaoke" ? 0.35 : fx === "reveal" ? 0 : 1);
    return (
      <div style={{ transform: pageT, opacity: pageO, textAlign: "center", fontFamily: family, fontWeight: weight, fontSize: size,
        lineHeight: 1.14, color, padding: style.box ? `${size * 0.12}px ${size * 0.3}px` : 0, borderRadius: size * 0.2,
        background: style.box ? "rgba(0,0,0,0.72)" : "transparent", maxWidth: boxW }}>
        {words.map((w, i) => {
          const next = words[i + 1]?.start ?? chunk.end;
          const on = t >= w.start && t < next, said = t >= w.start;
          // active word: springs up on its start, eases back as the next word starts
          const a = prog(t, w.start - 0.03, 0.22 * m.k, m.pop) * (1 - prog(t, next - 0.03, 0.2, "power2.out"));
          const em = w.emph ? (style.emphasis_scale ?? 1.15) : 1;
          const sc = (1 + (activeScale - 1) * a) * em;
          const fill = fx === "karaoke" ? Math.min(1, Math.max(0, (t - w.start) / Math.max(0.08, w.end - w.start))) : 0;
          const rev = fx === "reveal" ? prog(t, w.start - 0.04, 0.24 * m.k, m.enter) : 1;
          const op = fx === "karaoke" ? (said ? 1 : dimmed) : fx === "reveal" ? dimmed + (1 - dimmed) * rev : 1;
          const pill = fx === "word_highlight" && on;
          const pillP = pill ? ease("back.out(2)")(Math.min(1, (t - w.start) / 0.18)) : 0;
          const base = w.emph ? style.emphasis_color ?? hi : color;
          const textColor = fx === "karaoke" ? undefined : on && !pill && fx !== "reveal" ? hi : base;
          const stroke = style.stroke && !pill ? `${Math.max(2, size * 0.1)}px #000` : undefined;
          return (
            <React.Fragment key={i}>
              {i ? " " : null}
              <span style={{ display: "inline-block", position: "relative", transform: `translateY(${-lift * a + (1 - rev) * size * 0.35}px) scale(${sc})`,
                margin: `0 ${(sc - 1) * 0.5 * size * Math.max(1, w.text.length * 0.5)}px`,
                opacity: op, color: textColor ?? base, WebkitTextStroke: stroke, paintOrder: "stroke fill",
                textShadow: style.box || style.stroke || style.shadow === false ? undefined : `0 ${size * 0.04}px ${size * 0.18}px rgba(0,0,0,0.5)` }}>
                {pill ? <span style={{ position: "absolute", left: -size * 0.12, right: -size * 0.12,
                  top: size * 0.02, bottom: 0, background: hi, borderRadius: size * 0.16, transform: `scale(${0.6 + 0.4 * pillP})`, opacity: pillP, zIndex: -1 }} /> : null}
                <span style={{ position: "relative", color: pill ? "#111" : undefined, WebkitTextStroke: pill ? "0px" : undefined }}>{w.text}</span>
                {fx === "karaoke" && on && fill > 0 ? (
                  // the said part of the word in the highlight colour, a copy clipped to the fill
                  <span style={{ position: "absolute", left: 0, top: 0, color: hi, clipPath: `inset(-20% ${(1 - fill) * 100}% -20% -5%)` }}>{w.text}</span>
                ) : null}
              </span>
            </React.Fragment>
          );
        })}
      </div>
    );
  };

/** The plan's captions over the whole cut. */
export const Captions: React.FC<{ style: CaptionStyle; chunks: Chunk[]; t: number; m: Motion }> = ({ style, chunks, t, m }) => {
  const { width, height } = useVideoConfig();
  const family = useFamily(style.font_match, style.weight ?? 800);
  const chunk = chunks.find((c) => t >= c.start && t < c.end);
  if (!family || !chunk || style.present === false) return null;
  // size_pct is measured on vertical video, where height is the long side; the long side keeps a 16:9
  // render as readable on a phone as a vertical one.
  const size = ((style.size_pct ?? 6) / 100) * Math.max(width, height);
  const boxW = ((style.width_pct ?? 86) / 100) * width;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: `${style.y_pct ?? 70}%`, transform: "translateY(-50%)", display: "flex", justifyContent: "center" }}>
      <CaptionLine style={style} chunk={chunk} t={t} family={family} m={m} boxW={boxW} maxSize={size} />
    </div>
  );
};

/** caption_page template: word-timed karaoke paging built on createTikTokStyleCaptions.
 *  props: words: [{text, start, end, emph?}] (seconds after the card lands), combine_ms? (1200),
 *  style?: a captions style block (effect defaults to karaoke). */
export const CaptionPage: React.FC<{ p: Record<string, any>; w: number; h: number; m: Motion; font: string }> = ({ p, w, h, m, font }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const style: CaptionStyle = { effect: "karaoke", weight: 800, ...(p.style ?? {}) };
  const family = useFamily(style.font_match ?? font, style.weight ?? 800);
  const words: Word[] = p.words ?? [];
  const { pages } = createTikTokStyleCaptions({ combineTokensWithinMilliseconds: Number(p.combine_ms ?? 1200),
    captions: words.map((x, i) => ({ text: `${i ? " " : ""}${x.text}`, startMs: x.start * 1000, endMs: x.end * 1000, timestampMs: null, confidence: null })) });
  const page = [...pages].reverse().find((pg) => t * 1000 >= pg.startMs);
  if (!family || !page) return null;
  let wi = words.findIndex((x) => Math.abs(x.start * 1000 - page.startMs) < 1);
  const chunk: Chunk = { text: page.text, start: page.startMs / 1000, end: (page.startMs + page.durationMs) / 1000,
    words: page.tokens.map((tk) => ({ text: tk.text.trim(), start: tk.fromMs / 1000, end: tk.toMs / 1000, emph: words[wi++]?.emph })) };
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <CaptionLine style={style} chunk={chunk} t={t} family={family} m={m} boxW={w * 0.94} maxSize={Math.min(h * 0.62, w * 0.2)} />
    </div>
  );
};
