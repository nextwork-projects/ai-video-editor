import React from "react";
import { useTl, Motion } from "./motion";
import { Fonts, Look, Texture, shadowOf } from "./look";
import { FLOATING as TYPE_FLOATING, TEMPLATES as TYPE_TEMPLATES } from "./Templates";
import { OVERLAYS } from "./Overlays";

const TEMPLATES = { ...TYPE_TEMPLATES, ...OVERLAYS };
// Overlay formats draw their own chrome over the footage; they never sit on a surface card.
const FLOATING = new Set([...TYPE_FLOATING, ...Object.keys(OVERLAYS), "social_post"]);
import { CaptionPage } from "./Captions";

// The card host. One idea per card, drawn by a template (Templates.tsx) on the look's surface.
// Shapes: skills/style-edit/references/contracts.md "visuals.json" and skills/style-edit/references/motion.md.
// Of the eight original types, logo and flow still work; the type cards were removed (plan.py skips them).
export type Anim = { type: string; props: Record<string, any> };
export type Theme = "dark" | "light";

/** Old type -> template + props. */
const legacy = (a: Anim): Anim => {
  const p = a.props ?? {};
  switch (a.type) {
    case "logo": return { type: "logo_sting", props: p };
    default: return a;
  }
};
export const TEMPLATE_TYPES = [...Object.keys(TEMPLATES), "caption_page"];
export const LEGACY_TYPES = ["logo", "flow"];

/** The flat card under a template (overlay layout): opens with a clip reveal, carries the texture. */
const Surface: React.FC<{ w: number; h: number; look: Look; m: Motion; dur: number; id: string; children: React.ReactNode }> =
  ({ w, h, look, m, dur, id, children }) => {
    const r = (look.radius / 100) * Math.min(w, h);
    const ref = useTl((tl, q, root) => {
      const R = `round ${r}px`;
      tl.fromTo(root, { clipPath: `inset(10% 6% 10% 6% ${R})`, autoAlpha: 0, y: Math.min(w, h) * 0.04 },
        { clipPath: `inset(0% 0% 0% 0% ${R})`, autoAlpha: 1, y: 0, duration: 0.5 * m.k, ease: m.move === "sine.inOut" ? "power3.out" : m.enter }, 0);
      if (dur > m.out * 2) tl.to(root, { autoAlpha: 0, y: -Math.min(w, h) * 0.03, duration: m.out, ease: m.exit }, dur - m.out * 0.8);
    }, [w, h, dur, m.name, look.preset]);
    const glass = look.surface === "glass";
    return (
      <div ref={ref} style={{ position: "relative", width: w, height: h, borderRadius: r, overflow: "hidden",
        background: look.ground, boxShadow: glass ? `0 ${h * 0.04}px ${h * 0.14}px rgba(0,0,0,0.45)` : shadowOf(look, Math.min(w, h) / 100),
        ...(glass ? { backdropFilter: "blur(22px)", border: `1.5px solid ${look.line}` } : {}) }}>
        <Texture look={look} w={w} h={h} id={id} />
        {children}
      </div>
    );
  };

/** w, h: the card box in px. dur: how long the card is up. light: split layout, drawn straight on the
 *  ground. Must sit inside a <Sequence> that starts when the card lands (the timelines read its frame). */
export const AnimCard: React.FC<{ anim: Anim; w: number; h: number; look: Look; m: Motion; fonts: Fonts; dur: number; light: boolean; id: string }> =
  ({ anim, w, h, look, m, fonts, dur, light, id }) => {
    const a = legacy(anim);
    if (!fonts.ready) return null;
    if (a.type === "caption_page") return <CaptionPage p={a.props} w={w} h={h} m={m} font={look.font} />;
    const View = TEMPLATES[a.type];
    if (!View) return null;
    const floating = FLOATING.has(a.type) || light || look.surface === "none";
    const pad = floating ? 0 : Math.min(w, h) * 0.07;
    const inner = <View p={a.props ?? {}} w={w - pad * 2} h={h - pad * 2} look={look} m={m} fonts={fonts} dur={dur} id={id} />;
    if (floating) return <div style={{ position: "relative", width: w, height: h }}>{inner}</div>;
    return (
      <Surface w={w} h={h} look={look} m={m} dur={dur} id={id}>
        <div style={{ position: "absolute", left: pad, top: pad, width: w - pad * 2, height: h - pad * 2 }}>{inner}</div>
      </Surface>
    );
  };
