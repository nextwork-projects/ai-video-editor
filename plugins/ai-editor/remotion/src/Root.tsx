import React from "react";
import { AbsoluteFill, CalculateMetadataFunction, Composition, Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Card, CardView, Plan, StyleEdit, calculateMetadata } from "./StyleEdit";
import { resolveLook, useFonts } from "./look";
import { SplitText, pickMotion, useTl } from "./motion";
import { footageX } from "./Scene";
import { ProductVideo, ProductPlan, productMeta } from "./product/ProductVideo";

// Real values come from plan.json via --props; these only let the studio open.
const empty: Plan = {
  video: "",
  width: 1080,
  height: 1920,
  fps: 30,
  durationInFrames: 90,
  captions: { style: {}, chunks: [] },
  zooms: [],
  cards: [],
};

// Preview: one card over a backdrop, for template stills and clips (test/templates.mjs).
type PreviewProps = { width: number; height: number; dur: number; card: Card; look?: any; motion?: string; bg?: string; light?: boolean };
const Preview: React.FC<PreviewProps> = ({ card, look: l, motion, bg, light }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const look = resolveLook(l);
  const fonts = useFonts(look);
  const m = pickMotion(motion);
  const { width } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: bg && !bg.startsWith("images/") ? bg : light ? look.ground : "#111" }}>
      {bg?.startsWith("images/") ? <Img src={staticFile(bg)} style={{ width: "100%", height: "100%", objectFit: "cover",
        transform: `translateX(${footageX(frame / fps, [card], width, m)}px)` }} /> : null}
      {fonts.ready ? <CardView card={card} t={frame / fps} covered={false} light={!!light} look={look} m={m} fonts={fonts} /> : null}
    </AbsoluteFill>
  );
};
const previewMeta: CalculateMetadataFunction<PreviewProps> = ({ props }) => ({
  width: props.width, height: props.height, fps: 30, durationInFrames: Math.round(props.dur * 30),
});

// Proof: one GSAP plugin driving one element, for the determinism test (test/determinism.mjs).
const Proof: React.FC<{ plugin: string }> = ({ plugin }) => {
  const look = resolveLook();
  const fonts = useFonts(look);
  return <AbsoluteFill style={{ background: "#F2EEE6" }}>{fonts.ready ? <ProofInner plugin={plugin} family={fonts.display} /> : null}</AbsoluteFill>;
};
const ProofInner: React.FC<{ plugin: string; family: string }> = ({ plugin, family }) => {
  const ref = useTl((tl, q) => {
    const el = q(".el")[0], path = q(".path")[0] as SVGPathElement;
    if (plugin === "drawsvg") tl.fromTo(path, { drawSVG: "0%" }, { drawSVG: "100%", duration: 2, ease: "ink" }, 0);
    if (plugin === "morphsvg") tl.to(path, { morphSVG: "M100 300 C300 100 500 500 700 300 S900 100 900 300", duration: 2, ease: "power2.inOut" }, 0);
    if (plugin === "motionpath") tl.to(el, { motionPath: { path, align: path, alignOrigin: [0.5, 0.5] }, duration: 2, ease: "power1.inOut" }, 0);
    if (plugin === "customease") tl.fromTo(el, { x: 0 }, { x: 700, duration: 2, ease: "ink" }, 0);
    if (plugin === "customwiggle") tl.fromTo(el, { x: 300 }, { x: 360, duration: 2, ease: "impact" }, 0);
    if (plugin === "physics2d") tl.to(el, { physics2D: { velocity: 900, angle: -60, gravity: 900 }, duration: 2, ease: "none" }, 0);
    if (plugin === "physics2d-friction") tl.to(el, { physics2D: { velocity: 900, angle: -60, gravity: 900, friction: 0.08 }, duration: 2, ease: "none" }, 0);
    if (plugin === "splittext") {
      const s = SplitText.create(q(".txt")[0], { type: "lines,chars", mask: "lines" });
      tl.fromTo(s.chars, { yPercent: 110 }, { yPercent: 0, duration: 0.8, ease: "expo.out", stagger: 0.04 }, 0);
    }
  }, [plugin]);
  return (
    <div ref={ref} style={{ position: "absolute", inset: 0 }}>
      <svg width={1080} height={1080} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <path className="path" d="M100 600 C300 200 600 900 900 500" fill="none" stroke="#141414" strokeWidth={14} strokeLinecap="round" />
      </svg>
      <div className="el" style={{ position: "absolute", left: 100, top: 560, width: 80, height: 80, background: "#E5482C", borderRadius: 16 }} />
      <div className="txt" style={{ position: "absolute", left: 80, top: 120, width: 920, fontFamily: family, fontWeight: 800, fontSize: 120,
        lineHeight: 1, color: "#141414" }}>{plugin === "splittext" ? "Motion that lands on the word" : ""}</div>
    </div>
  );
};

export const Root: React.FC = () => (
  <>
    <Composition
      id="StyleEdit"
      component={StyleEdit}
      defaultProps={empty}
      calculateMetadata={calculateMetadata}
      width={1080}
      height={1920}
      fps={30}
      durationInFrames={90}
    />
    <Composition id="Preview" component={Preview} calculateMetadata={previewMeta} width={1080} height={1920} fps={30} durationInFrames={90}
      defaultProps={{ width: 1080, height: 1920, dur: 3, card: { anim: { type: "logo_sting", props: { src: "images/logo.svg" } }, start: 0, end: 3, entrance: "pop",
        box: [8, 20, 84, 30] } } as PreviewProps} />
    <Composition id="Proof" component={Proof} width={1080} height={1080} fps={30} durationInFrames={60} defaultProps={{ plugin: "drawsvg" }} />
    {/* product-video skill: a website's real UI as a launch video (plan from skills/product-video/scripts/product.py) */}
    <Composition id="ProductVideo" component={ProductVideo} calculateMetadata={productMeta} width={1920} height={1080} fps={30}
      durationInFrames={90} defaultProps={{ width: 1920, height: 1080, fps: 30, durationInFrames: 90, variant: "apple", url: "",
        brand: { ground: "#FFFFFF", ink: "#0A0A0A", muted: "#6B6B6B", accent: "#0A0A0A", dark: false, radius_px: 8,
          display: { family: "Inter", weight: 600, tracking_em: -0.02 }, body: { family: "Inter", weight: 400 }, fonts: [] },
        page: { vw: 1440, vh: 900, tiles: [], height: 900, domain: "" }, shots: [] } as ProductPlan} />
  </>
);
