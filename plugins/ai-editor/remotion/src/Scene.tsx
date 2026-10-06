// Full-frame scenes: an explaining beat cuts away from the speaker to the look's flat ground, the type
// filling the frame, and cuts back. The cut in and out is a designed transition, never a hard cut:
//   match  a dot of the scene's ground grows from the focus point (the face) to become the whole frame
//   iris   a circle opens from the focus point
//   push   the scene pushes the footage off the frame, motion-blurred along x
//   block  two colour blocks sweep across and the scene is under the second
//   wipe   a hard edge crosses from the right; fade: a plain dissolve
// Inside, the camera drifts and flat colour blocks sit on their own parallax layer.
import React from "react";
import { Sequence, useVideoConfig } from "remotion";
import { Motion, prog } from "./motion";
import { Fonts, Ground, Look, Texture, onGround } from "./look";
import { Anim, AnimCard } from "./Anims";
import { Capture, Mark } from "./Capture";

export type Transition = "match" | "iris" | "push" | "block" | "wipe" | "fade";
export type SceneCard = { anim?: Anim; src?: string; size?: [number, number]; marks?: Mark[];
  highlight?: { rects: [number, number, number, number][] }; start: number; end: number; layout?: "scene" | "box";
  transition_in?: Transition; transition_out?: Transition; focus?: [number, number]; ground?: Ground;
  box: [number, number, number, number] };

/** Which of the look's colours each scene sits on: the card's own `ground`, else ground, ink, accent in turn. */
export const sceneGrounds = (cards: SceneCard[]) => {
  const out = new Map<SceneCard, Ground>();
  const order: Ground[] = ["ground", "ink", "accent"];
  cards.filter((c) => c.layout === "scene").sort((a, b) => a.start - b.start).forEach((c, i) => out.set(c, c.ground ?? order[i % 3]));
  return out;
};

const EASE: Record<Transition, string> = { match: "expo.inOut", iris: "power3.inOut", push: "power4.inOut", block: "power3.inOut",
  wipe: "power3.inOut", fade: "sine.inOut" };
const TR_S = 0.62; // seconds a transition takes at k = 1

/** Where a scene's type lives, % of the frame: clear of the app's top bar and the captions under it. */
export const sceneBox = (w: number, h: number): [number, number, number, number] => (h > w ? [6, 13, 88, 52] : [6, 9, 88, 70]);

const phases = (c: SceneCard, t: number, m: Motion) => {
  const T = TR_S * m.k;
  const tin = c.transition_in ?? "match", tout = c.transition_out ?? (tin === "block" || tin === "push" ? tin : "iris");
  return { T, tin, tout, pi: prog(t - c.start, 0, T, EASE[tin]), po: prog(t, c.end - T, T, EASE[tout]) };
};

/** The footage's x offset while a push scene is entering or leaving (it is pushed off, then back). */
export const footageX = (t: number, cards: SceneCard[], width: number, m: Motion) => {
  for (const c of cards) {
    if (c.layout !== "scene" || t < c.start || t > c.end) continue;
    const { tin, tout, pi, po } = phases(c, t, m);
    if (tout === "push" && po > 0) return (1 - po) * width;
    if (tin === "push") return -pi * width;
  }
  return 0;
};

/** Flat colour blocks on their own layer, drifting against the content (parallax). */
const Decor: React.FC<{ look: Look; w: number; h: number; lt: number; dur: number }> = ({ look, w, h, lt, dur }) => {
  if (look.decor === "none") return null;
  const d = prog(lt, 0, Math.max(1, dur), "sine.inOut");
  const poster = look.preset.startsWith("poster");
  const s = Math.min(w, h);
  return (
    <>
      <div style={{ position: "absolute", left: -s * 0.12 + d * s * 0.05, top: h * (h > w ? 0.9 : 0.86) - d * s * 0.02, width: s * 0.62, height: s * 0.07,
        background: look.accent, opacity: poster ? 1 : 0.9 }} />
      <div style={{ position: "absolute", right: -s * 0.22 - d * s * 0.04, top: -s * 0.2 + d * s * 0.03, width: s * 0.62, height: s * 0.62,
        borderRadius: "50%", background: poster ? look.ink : look.line, opacity: poster ? 0.12 : 0.6 }} />
    </>
  );
};

/** A scene card: ground + decor + the template in the scene box, cut in and out by its transitions. */
export const SceneView: React.FC<{ card: SceneCard; t: number; look: Look; m: Motion; fonts: Fonts; covered: boolean; ground?: Ground }> =
  ({ card, t, look: base, m, fonts, covered, ground }) => {
    const look = onGround(base, ground ?? card.ground ?? "ground");
    const { fps, width: W, height: H } = useVideoConfig();
    const { T, tin, tout, pi, po } = phases(card, t, m);
    const lt = t - card.start, dur = card.end - card.start;
    const [fx, fy] = card.focus ?? [50, 30];
    const FX = (fx / 100) * W, FY = (fy / 100) * H;
    const leaving = !covered && po > 0;
    const kind = leaving ? tout : tin;
    const p = leaving ? 1 - po : pi; // how much of the scene shows
    let clipPath: string | undefined, transform = "none", opacity = 1, blur = 0, inner = 1;
    if (kind === "iris") clipPath = `circle(${p * 150}% at ${fx}% ${fy}%)`;
    if (kind === "match") {
      const s0 = Math.min(W, H) * 0.07, r = (s0 / 2) * (1 - p);
      clipPath = `inset(${(FY - s0 / 2) * (1 - p)}px ${(W - FX - s0 / 2) * (1 - p)}px ${(H - FY - s0 / 2) * (1 - p)}px ${(FX - s0 / 2) * (1 - p)}px round ${r}px)`;
      inner = 1 + 0.12 * (1 - p); // the content settles as the ground grows: depth in the cut
    }
    if (kind === "push") {
      transform = `translateX(${leaving ? -(1 - p) * W : (1 - p) * W}px)`;
      blur = Math.sin(p * Math.PI) * W * 0.018;
    }
    if (kind === "wipe") clipPath = leaving ? `inset(0% ${(1 - p) * 100}% 0% 0%)` : `inset(0% 0% 0% ${(1 - p) * 100}%)`;
    if (kind === "fade") opacity = p;
    // colour blocks: cover on the first half, uncover on the second; the scene switches under them
    let blocks: React.ReactNode = null;
    if (kind === "block") {
      const ph = leaving ? t - (card.end - T) : lt;
      const bx = (lag: number) => {
        const a = prog(ph, lag, T * 0.48, "power3.inOut"), b = prog(ph, T * 0.52 + lag, T * 0.45, "power3.inOut");
        return (-1 + a + b) * W;
      };
      const mid = ph >= T * 0.5;
      opacity = leaving ? (mid ? 0 : 1) : mid ? 1 : 0;
      if (ph > 0 && ph < T + 0.1) {
        blocks = <>
          <div style={{ position: "absolute", inset: 0, transform: `translateX(${bx(0)}px)`, background: look.accent }} />
          <div style={{ position: "absolute", inset: 0, transform: `translateX(${bx(0.07)}px)`, background: look.ink }} />
        </>;
      }
    }
    const [bx, by, bw, bh] = card.box[2] === 100 && card.box[3] === 100 ? sceneBox(W, H) : card.box;
    const id = `sc${card.start}`;
    // the scene keeps moving after its entrance: a slow push and pan over its whole life
    const life = prog(lt, 0, Math.max(1, dur), "sine.inOut");
    const cam = `translate(${(0.5 - life) * W * 0.03}px, ${(0.5 - life) * H * 0.008}px) scale(${inner * (1 + 0.045 * life)})`;
    return (
      <>
        <div style={{ position: "absolute", inset: 0, overflow: "hidden", background: look.ground, clipPath, transform, opacity,
          filter: blur > 0.5 ? `url(#mb-${id})` : undefined }}>
          <svg width={0} height={0} style={{ position: "absolute" }}><filter id={`mb-${id}`} x="-5%" width="110%">
            <feGaussianBlur stdDeviation={`${blur} 0`} /></filter></svg>
          <Decor look={look} w={W} h={H} lt={lt} dur={dur} />
          <Texture look={look} w={W} h={H} id={id} />
          <div style={{ position: "absolute", left: `${bx}%`, top: `${by}%`, width: `${bw}%`, height: `${bh}%`, transform: cam,
            display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Sequence from={Math.round(card.start * fps)} layout="none">
              {card.anim ? <AnimCard anim={card.anim} w={(bw / 100) * W} h={(bh / 100) * H} look={look} m={m} fonts={fonts} dur={dur + 0.6}
                light id={id} /> : card.src ? <Capture src={card.src} size={card.size} marks={card.marks} highlight={card.highlight}
                bw={(bw / 100) * W} bh={(bh / 100) * H} dur={dur} look={look} m={m} font={fonts.body} light /> : null}
            </Sequence>
          </div>
        </div>
        {blocks}
      </>
    );
  };
