// The product video: a website's real UI and its recorded click-throughs, its own fonts, colours and logo,
// moved by a camera. plan.json comes from skills/product-video/scripts/product.py; nothing here invents
// copy or colour.
//
// Style families (kit.tsx STYLES, measured in references/style.md) share every shot and differ in camera
// language: linear (default: tilted plane, drift, blur-dissolves, small low-left words), apple (straight-on
// window, eased push, cursor click, big words above), stripe (flat, still camera, big words low-left),
// arc (flat and large, hard cuts, small lowercase words with a bounce), raycast (flat, slow drift and push,
// dissolves, tiny monospace caps). Shot kinds: page, lift, media, flow, keys, end here; macro, stack, push,
// split, orbit, whip, grid, type in Shots.tsx.
// Coordinates: "page px" are the site's CSS px (crawl.mjs); a flow's are its recorded viewport's.
import React, { useEffect, useState } from "react";
import { AbsoluteFill, Audio, CalculateMetadataFunction, Img, OffthreadVideo, Sequence, continueRender, delayRender, interpolate,
  staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { ease, prog } from "../motion";
import { loadFamily } from "../look";
import { camAt, clamp01, Fams, FlowVideo, frameOn, Key, lerp, lerpR, Page, ProductPlan, Rect, Shot, Stage, STYLES, Words, wordsBox } from "./kit";
import { Grid, Keycaps, Macro, Orbit, Push, Split, Stack, Type, Whip } from "./Shots";

export type { ProductPlan, Shot } from "./kit";

export const productMeta: CalculateMetadataFunction<ProductPlan> = ({ props }) => ({
  width: props.width, height: props.height, fps: props.fps, durationInFrames: Math.max(1, props.durationInFrames),
});

// ---------- fonts: the site's own files first, then the same family from Google Fonts, then the system ----------
const useSiteFonts = (b: ProductPlan["brand"]) => {
  const [fam, setFam] = useState<{ ready: boolean } & Fams>({ ready: false, display: "system-ui", body: "system-ui" });
  const [h] = useState(() => delayRender("site fonts"));
  useEffect(() => {
    const own = async (family: string) => {
      const faces = b.fonts.filter((f) => f.family === family);
      if (!faces.length) {
        const g = await loadFamily(family.replace(/ Variable$/, ""), [b.display.weight, b.body.weight, 400]);
        return g.startsWith("system-ui") ? `'${family}', system-ui, -apple-system, sans-serif` : g;
      }
      const name = `site-${family.replace(/\W+/g, "")}`;
      await Promise.all(faces.map(async (f) => {
        const face = new FontFace(name, `url(${staticFile(f.src)})`, { weight: f.weight, style: f.style });
        await face.load();
        document.fonts.add(face);
      }));
      return `'${name}', system-ui, sans-serif`;
    };
    Promise.all([own(b.display.family), own(b.body.family)])
      .then(([display, body]) => setFam({ ready: true, display, body }))
      .catch(() => setFam({ ready: true, display: "system-ui", body: "system-ui" }))
      .finally(() => continueRender(h));
  }, [b, h]);
  return fam;
};

// The macOS arrow, drawn at a constant screen size (page shots; flows carry their own recorded cursor).
const Cursor: React.FC<{ x: number; y: number; s: number; press: number }> = ({ x, y, s, press }) => (
  <svg width={28 * s} height={40 * s} viewBox="0 0 28 40" style={{ position: "absolute", left: x - 3 * s, top: y - 2 * s,
    transform: `scale(${1 - 0.16 * press})`, transformOrigin: "3px 2px", filter: `drop-shadow(0 ${2 * s}px ${4 * s}px rgba(0,0,0,0.35))` }}>
    <path d="M3 2 L3 31 L10 24.5 L14.6 35.2 L19.4 33.2 L14.8 22.6 L24 22.6 Z" fill="#111" stroke="#fff" strokeWidth={2.2} strokeLinejoin="round" />
  </svg>
);

const Logo: React.FC<{ plan: ProductPlan; t: number; fams: Fams; W: number; H: number }> = ({ plan, t, fams, W, H }) => {
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

// ---------- one shot ----------
const ShotView: React.FC<{ plan: ProductPlan; shot: Shot; t: number; fams: Fams }> = ({ plan, shot, t, fams }) => {
  const { width: W, height: H, fps } = useVideoConfig();
  const S = Math.min(W, H) / 1080;
  const st = STYLES[plan.variant] ?? STYLES.linear;
  const above = st.words.pos === "above";
  const dur = shot.end - shot.start;
  const vertical = H > W * 1.2, square = !vertical && H > W * 0.8;
  const band = above ? (vertical ? 0.17 : square ? 0.18 : 0.17) * H : 0;
  // a dark-mode recording on a light site (or the reverse): its words and scrim take the recording's tone
  const sg = shot.tone === "dark" ? "#0C0C0D" : shot.tone === "light" ? "#F7F7F7" : plan.brand.ground;
  const ink = shot.tone === "dark" ? "#F4F4F4" : shot.tone === "light" ? "#111111" : undefined;
  const words = shot.text && shot.kind !== "type"
    ? <Words text={shot.text} t={t} dur={dur} plan={plan} fam={fams.display} box={wordsBox(plan, W, H, vertical, band)} S={S} vertical={vertical} ink={ink} /> : null;
  const scrim = shot.text && !above && shot.kind !== "type"
    ? <AbsoluteFill style={{ background: `linear-gradient(to top, ${sg} 0%, ${sg}D9 24%, ${sg}00 52%)` }} /> : null;

  if (shot.kind === "end") return <Logo plan={plan} t={t} fams={fams} W={W} H={H} />;
  const lib: Record<string, React.FC<any>> = { macro: Macro, stack: Stack, push: Push, split: Split, orbit: Orbit, whip: Whip, grid: Grid, type: Type };
  if (lib[shot.kind]) {
    const C = lib[shot.kind];
    return <AbsoluteFill><C plan={plan} shot={shot} t={t} fams={fams} />{scrim}{words}</AbsoluteFill>;
  }

  const flow = shot.flow;
  const vw = flow ? flow.viewport[0] : plan.page.vw;
  // a vertical frame shows a taller window of a page: about two screens, cropped at the sides
  const vh = flow ? flow.viewport[1] : vertical ? Math.round(plan.page.vh * 1.9) : plan.page.vh;
  const winW = vw, winH = vh;
  const stage: Stage = above ? { x: W * 0.05, y: band + H * 0.015, w: W * 0.9, h: H - band + H * 0.06 }
    : st.tilt ? { x: -W * 0.02, y: -H * 0.02, w: W * 1.04, h: H * 1.04 }
    // arc: the UI large and cropped off an edge (measured 60-90% of the frame); the rest framed whole
    : plan.variant === "arc" ? { x: -W * 0.03, y: H * 0.03, w: W * 1.1, h: H * 1.1 } : { x: W * 0.05, y: H * 0.06, w: W * 0.9, h: H * 0.88 };
  const radius = Math.max(10, Math.min(28, plan.brand.radius_px * 1.6));

  let body: React.ReactNode;
  if (shot.kind === "media" && shot.media) {
    const [mw, mh] = shot.media.size ?? [16, 9];
    const f = Math.min((stage.w * 0.92) / mw, (stage.h * 0.92) / mh);
    const push = 1 + 0.035 * prog(t, 0, dur, "sine.inOut");
    body = <div style={{ position: "absolute", left: stage.x + (stage.w - mw * f) / 2, top: stage.y + (stage.h - mh * f) / 2, width: mw * f, height: mh * f,
      borderRadius: radius * S, overflow: "hidden", transform: `scale(${push})`, boxShadow: `0 ${30 * S}px ${90 * S}px rgba(0,0,0,${plan.brand.dark ? 0.6 : 0.22})` }}>
      <OffthreadVideo src={staticFile(shot.media.src)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </div>;
  } else {
    const keys = (flow ? flow.keys : shot.keys) ?? [{ t: 0, scroll: 0, rect: [0, 0, vw, vh] as Rect }];
    const cam = camAt(keys as Key[], t, plan.camera === "linear" ? "power2.inOut" : st.move, plan.camera === "linear");
    const scroll = flow ? 0 : Math.min(cam.scroll, Math.max(0, plan.page.height - vh));
    const toWin = (r: Rect): Rect => [r[0], r[1] - scroll, r[2], r[3]];
    // a phone-layout recording on a tall frame fills it edge to edge: cover, then zoom onto the hand (never ground beside it)
    const phone = !!flow && vh > vw && vertical;
    const fr = phone ? (() => {
      const r = cam.rect, z0 = Math.max(W / vw, H / vh) * Math.min(1.6, Math.max(1, vw / r[2]));
      const cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2;
      return { z: z0, tx: Math.min(0, Math.max(W - vw * z0, W / 2 - cx * z0)), ty: Math.min(0, Math.max(H - vh * z0, H / 2 - cy * z0)) };
    })() : frameOn(toWin(cam.rect), winW, winH, stage, W, H, st.fill, st.maxZ, above);
    const z = fr.z * (1 + st.push * clamp01(t / Math.max(1, dur))), tx = fr.tx - (z - fr.z) * winW * 0.5, ty = fr.ty - (z - fr.z) * winH * (phone ? 0.5 : 0.4);
    const tilt = shot.tilt ? lerp(shot.tilt[0], shot.tilt[1], ease("power2.inOut")(Math.min(1, t / Math.max(1, dur)))) : 0;
    const lift = shot.lift;
    const lp = lift ? prog(t, lift.at, above ? 0.9 : 1.0, above ? "power3.inOut" : "power2.inOut") : 0;
    const drift = phone ? 0 : (t / Math.max(1, dur) - 0.5) * W * st.drift;
    const worldStyle: React.CSSProperties = { position: "absolute", left: 0, top: 0, width: winW, height: winH, transformOrigin: "0 0",
      transform: `translate(${tx + drift}px, ${ty}px) scale(${z})`, willChange: "transform", borderRadius: radius, overflow: "hidden",
      boxShadow: st.shadow ? `0 ${24 / z}px ${80 / z}px rgba(0,0,0,${(plan.brand.dark ? 0.55 : 0.18) * st.shadow}), 0 0 0 ${1 / z}px rgba(${plan.brand.dark ? "255,255,255,0.08" : "0,0,0,0.06"})`
        : `0 0 0 ${1 / z}px rgba(${plan.brand.dark ? "255,255,255,0.10" : "0,0,0,0.08"})`,
      filter: lp > 0 ? `blur(${lp * 10}px) brightness(${plan.brand.dark ? 1 - lp * 0.45 : 1 + lp * 0.04})` : undefined,
      opacity: lift ? 1 - lp * 0.6 : 1 };
    const content = flow ? <FlowVideo flow={flow} fps={fps} /> : <Page plan={plan} scroll={scroll} vh={vh} />;
    let hover: React.ReactNode = null, cursor: React.ReactNode = null;
    if (shot.cursor && !flow) {
      const c = shot.cursor;
      const mp = prog(t, c.move_at, Math.max(0.3, c.click_at - c.move_at - 0.05), "power3.inOut");
      const arc = Math.sin(mp * Math.PI) * 40;
      const px = lerp(c.from[0], c.to[0], mp), py = lerp(c.from[1], c.to[1], mp) - arc;
      const press = Math.max(0, 1 - Math.abs(t - c.click_at) / 0.12);
      const sx = tx + drift + px * z, sy = ty + (py - scroll) * z;
      const show = interpolate(t, [c.move_at - 0.2, c.move_at], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
      cursor = <div style={{ opacity: show }}><Cursor x={sx} y={sy} s={S * 1.25} press={press} /></div>;
      if (c.el?.hover_src && t > c.click_at - 0.35) {
        const [x, y, w, h] = c.el.crop;
        hover = <Img src={staticFile(c.el.hover_src)} style={{ position: "absolute", left: x, top: y - scroll, width: w, height: h, transform: `scale(${1 - 0.04 * press})` }} />;
      }
    }
    // linear: the page's own light, a blurred copy of what is on screen behind the plane
    const glow = st.tilt && !flow ? <div style={{ ...worldStyle, boxShadow: undefined, filter: `blur(70px) saturate(1.4)`, opacity: plan.brand.dark ? 0.55 : 0.35,
      transform: `translate(${tx + drift}px, ${ty}px) scale(${z * 1.02})` }}>{content}</div> : null;
    const plane = (
      <div style={{ position: "absolute", inset: 0, perspective: 2200 * S, perspectiveOrigin: "50% 30%" }}>
        <div style={{ position: "absolute", inset: 0, transformStyle: "preserve-3d", transformOrigin: "50% 50%",
          transform: tilt ? `rotateX(${tilt * 26}deg) rotateY(${-tilt * 10}deg) rotateZ(${tilt * 9}deg) scale(${1 + tilt * 0.22})` : undefined }}>
          {glow}
          <div style={worldStyle}>{content}{hover}</div>
        </div>
      </div>
    );
    let lifted: React.ReactNode = null;
    if (lift && lp > 0) {
      const [x, y, w, h] = lift.crop;
      const from: Rect = [tx + drift + x * z, ty + (y - scroll) * z, w * z, h * z];
      const area: Stage = above ? stage : { x: W * 0.1, y: H * 0.06, w: W * 0.8, h: H * 0.8 };
      const f = Math.min((area.w * 0.78) / w, (area.h * 0.78) / h);
      const to: Rect = [area.x + (area.w - w * f) / 2, area.y + (area.h - h * f) / 2, w * f, h * f];
      const r = lerpR(from, to, lp);
      const hold = prog(t, lift.at + 0.9, Math.max(0.5, dur - lift.at - 0.9), "sine.inOut");
      lifted = <Img src={staticFile(lift.src)} style={{ position: "absolute", left: r[0], top: r[1], width: r[2], height: r[3],
        borderRadius: Math.min(radius, plan.brand.radius_px) * (r[2] / w),
        boxShadow: `0 ${40 * S * lp}px ${110 * S * lp}px rgba(0,0,0,${plan.brand.dark ? 0.7 : 0.25}), 0 ${6 * S * lp}px ${18 * S * lp}px rgba(0,0,0,0.12)`
          + (plan.brand.dark ? `, 0 0 0 ${Math.max(1, S)}px rgba(255,255,255,${0.14 * lp})` : ""),
        transform: `${st.tilt ? `perspective(${1800 * S}px) rotateX(${(1 - lp) * 14}deg) rotateZ(${(1 - lp) * 4}deg) ` : ""}scale(${1 + 0.06 * hold})` }} />;
    }
    const cut = above && shot.text ? `linear-gradient(to bottom, transparent ${(band / H) * 100}%, black ${(band / H) * 100 + 2.5}%)` : undefined;
    body = <><div style={{ position: "absolute", inset: 0, WebkitMaskImage: cut, maskImage: cut }}>{plane}</div>{lifted}{cursor}
      {flow?.keycaps ? <Keycaps plan={plan} caps={flow.keycaps} t={t} fams={fams} /> : null}</>;
  }
  return <AbsoluteFill>{body}{scrim}{words}</AbsoluteFill>;
};

// ---------- the video ----------
export const ProductVideo: React.FC<ProductPlan> = (plan) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fams = useSiteFonts(plan.brand);
  const t = frame / fps;
  const i = Math.max(0, plan.shots.findIndex((s) => t >= s.start && t < s.end));
  const shot = plan.shots[i] ?? plan.shots[plan.shots.length - 1];
  const local = t - (shot?.start ?? 0);
  // a dip through the ground's blur between shots that do not continue one camera move
  const blurIn = shot?.cut_in === "blur" ? 1 - prog(local, 0, 0.45, "power2.out") : 0;
  const next = plan.shots[i + 1];
  const blurOut = next?.cut_in === "blur" ? prog(t, next.start - 0.3, 0.3, "power2.in") : 0;
  const b = Math.max(blurIn, blurOut);
  const intro = i === 0 ? prog(t, 0, 0.8, "power2.out") : 1;
  const a = plan.audio ?? {};
  const total = plan.durationInFrames / fps;
  return (
    <AbsoluteFill style={{ background: plan.brand.ground, overflow: "hidden" }}>
      {fams.ready && shot ? (
        <AbsoluteFill style={{ filter: b > 0.01 ? `blur(${b * 18}px)` : undefined, opacity: Math.min(intro, 1 - b * 0.8),
          transform: i === 0 && plan.variant === "apple" ? `translateY(${(1 - intro) * 40}px)` : undefined }}>
          {/* a Sequence per shot, so a recording plays from its own start, not the film's */}
          <Sequence key={i} from={Math.round(shot.start * fps)} durationInFrames={Math.max(1, Math.round((shot.end - shot.start) * fps) + 1)} layout="none">
            <ShotView plan={plan} shot={shot} t={local} fams={fams} />
          </Sequence>
        </AbsoluteFill>
      ) : null}
      {/* the whole soundtrack, mixed and mastered by sound.py: plays at unity */}
      {a.mix ? <Audio src={staticFile(a.mix)} /> : null}
      {a.music && !a.mix ? <Audio src={staticFile(a.music)} volume={(f) => (a.music_volume ?? 0.35) * Math.min(1, f / (fps * 0.4))
        * Math.min(1, Math.max(0, (total - f / fps) / 1.6))} /> : null}
      {a.vo && !a.mix ? <Audio src={staticFile(a.vo)} /> : null}
      {(a.mix ? [] : a.sfx ?? []).map((c) => <Sequence key={`${c.src}${c.t}`} from={Math.round(c.t * fps)} layout="none"><Audio src={staticFile(c.src)} /></Sequence>)}
    </AbsoluteFill>
  );
};
