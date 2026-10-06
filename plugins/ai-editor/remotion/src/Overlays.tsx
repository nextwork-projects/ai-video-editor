// Overlay formats: real pictures floating over the footage, never covering the face. Each is a template
// (JSON props, real assets only) that draws its own neutral chrome: a white card or the real app's
// surface, a soft realistic shadow, depth. Text on any card is a label of a few words at most; the
// picture carries the beat. Every format runs one word-labelled GSAP timeline (motion.ts wordTl): it
// drops in blurred just before its word, punches on each hit word, rides a slow push and leaves upward
// on a faster .in ease (cardLife). Shared primitives: cursor + click ripple, zoom into a region (Capture's `zoom`).
import React from "react";
import { Img, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Motion, cardLife, dropIn, exitUp, fitIn, fitOut, gsap, prog, punch, rng, useTl, wordTl, landAt, camera } from "./motion";
import { Look } from "./look";
import { Capture, Mark } from "./Capture";
import type { TP } from "./Templates";

const src_ = (s?: string) => (!s ? undefined : /^(https?:|data:)/.test(s) ? s : staticFile(s));
const fill: React.CSSProperties = { position: "absolute", inset: 0 };
const center: React.CSSProperties = { ...fill, display: "flex", alignItems: "center", justifyContent: "center" };
const MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, 'DejaVu Sans Mono', monospace";
const useT = () => { const f = useCurrentFrame(); const { fps } = useVideoConfig(); return f / fps; };
/** 1% of the frame's short side, and the scale against a 1080 frame (type sizes are set for phones). */
const useFrame = () => { const { width, height } = useVideoConfig(); const U = Math.min(width, height) / 100; return { U, s: U / 10.8 }; };

/** A soft realistic shadow: contact, mid and a long ambient one. */
export const depth = (u: number) =>
  `0 ${u * 0.15}px ${u * 0.4}px rgba(0,0,0,0.22), 0 ${u * 1.4}px ${u * 3}px -${u * 0.6}px rgba(0,0,0,0.32), 0 ${u * 4}px ${u * 9}px -${u * 2}px rgba(0,0,0,0.38)`;

/** The card size that fits an image of `size` in w x h. */
const fitBox = (size: [number, number] | undefined, w: number, h: number, ratio = 16 / 10) => {
  const r = size ? size[0] / size[1] : ratio;
  return r > w / h ? [w, w / r] : [h * r, h];
};

/** A small dark label pill, a few words only. */
const Tag: React.FC<{ text?: string; u: number; look: Look; font: string; cls?: string; style?: React.CSSProperties }> = ({ text, u, look, font, cls, style }) =>
  text ? <div className={cls} style={{ position: "absolute", padding: `${u * 0.9}px ${u * 2}px`, borderRadius: u * 5, background: look.ink, color: look.ground,
    fontFamily: font, fontWeight: 600, fontSize: Math.max(26, u * 4.6), whiteSpace: "nowrap", boxShadow: depth(u * 0.5), ...style }}>{text}</div> : null;

/** The cursor primitive: a real arrow that travels to (x, y), clicks with a ripple at `at`. */
const Cursor: React.FC<{ s: number }> = ({ s }) => (
  <>
    <div className="cur-ripple" style={{ position: "absolute", left: -s * 0.9, top: -s * 0.9, width: s * 1.8, height: s * 1.8, borderRadius: "50%",
      border: `${Math.max(2, s * 0.08)}px solid rgba(255,255,255,0.95)`, boxShadow: "0 0 0 2px rgba(0,0,0,0.25)", opacity: 0 }} />
    <svg width={s} height={s * 1.3} viewBox="0 0 20 26" className="cur-arrow" style={{ position: "absolute", left: 0, top: 0, overflow: "visible",
      filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.35))" }}>
      <path d="M1 1 L1 20 L6 15.5 L9.5 23.5 L13 22 L9.6 14.2 L16 14.2 Z" fill="#fff" stroke="#111" strokeWidth={1.4} strokeLinejoin="round" />
    </svg>
  </>
);
const cursorTo = (tl: gsap.core.Timeline, q: (s: string) => Element[], from: [number, number], to: [number, number], at: number, m: Motion) => {
  const c = q(".cursor")[0];
  if (!c) return;
  tl.fromTo(c, { x: from[0], y: from[1], autoAlpha: 0 }, { autoAlpha: 1, duration: 0.2 }, Math.max(0, at - 1.0));
  tl.fromTo(c, { x: from[0], y: from[1] }, { x: to[0], y: to[1], duration: 0.8 * m.k, ease: "power2.inOut", immediateRender: false }, Math.max(0, at - 1.0));
  tl.to(q(".cur-arrow")[0], { scale: 0.86, duration: 0.08, yoyo: true, repeat: 1, transformOrigin: "0 0" }, at - 0.04);
  tl.fromTo(q(".cur-ripple")[0], { scale: 0.2, opacity: 0.9 }, { scale: 1.4, opacity: 0, duration: 0.5, ease: "power2.out" }, at);
};

/** The source row on a white evidence card: the site's real logo and its name (props logo_src, label).
 *  Sizes are for a phone: 36 px type on a 1080 frame. */
const sourceRow = (s: number) => ({ h: 48 * s, gap: 12 * s, pad: 22 * s, fs: 36 * s });
const Source: React.FC<{ p: Record<string, any>; s: number; font: string }> = ({ p, s, font }) => {
  const r = sourceRow(s);
  return (
    <div className="cv-src" style={{ display: "flex", alignItems: "center", gap: 14 * s, height: r.h, marginBottom: r.gap }}>
      {p.logo_src ? <Img className="cv-src-logo" src={src_(p.logo_src)!} style={{ width: r.h * 0.92, height: r.h * 0.92, objectFit: "contain", borderRadius: "50%" }} /> : null}
      {p.label ? <div className="cv-src-name" style={{ fontFamily: font, fontWeight: 600, fontSize: r.fs, color: "#1B1B1F", letterSpacing: "-0.01em", whiteSpace: "nowrap" }}>{p.label}</div> : null}
      <div className="cv-rule" style={{ flex: 1, height: 2 * s, background: "#ECECEF", marginLeft: 10 * s, transformOrigin: "0 50%" }} />
    </div>
  );
};
/** The source row follows the card in: the logo spins up, the name slides, the rule draws (follow-through). */
const sourceIn = (tl: gsap.core.Timeline, q: (s: string) => Element[], at: number) => {
  const logo = q(".cv-src-logo")[0], name = q(".cv-src-name")[0], rule = q(".cv-rule")[0];
  if (logo) tl.fromTo(logo, { scale: 0, rotate: -90 }, { scale: 1, rotate: 0, duration: 0.45, ease: "back.out(2)" }, at + 0.2);
  if (name) tl.fromTo(name, { autoAlpha: 0, x: -16 }, { autoAlpha: 1, x: 0, duration: 0.35, ease: "power3.out" }, at + 0.26);
  if (rule) tl.fromTo(rule, { scaleX: 0 }, { scaleX: 1, duration: 0.7, ease: "power2.inOut" }, at + 0.32);
};
const headed = (p: Record<string, any>) => !!(p.label || p.logo_src);
/** Hits: the marks' landings (a highlight's too), so the card punches as the marked word is said. */
const markHits = (p: Record<string, any>) => [...(p.marks ?? []), ...(p.highlight?.rects?.length ? [1.6] : [])].slice(0, 3);

// =====================================================================================================
// shot: a real capture drops in just before its word, the camera pushes into the marked region as the
// mark lands, the card punches on that word, then it leaves upward. A label / logo_src puts the source
// row on a white card above the capture. props: src, size, marks?, highlight?, zoom? (1.45), label?, logo_src?
const Shot: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100;
  const { U, s } = useFrame();
  const r = sourceRow(s), head = headed(p);
  const [cw, ch] = head ? fitBox(p.size, w * 0.98 - 2 * r.pad, h * 0.98 - 2 * r.pad - r.h - r.gap) : fitBox(p.size, w * 0.96, h * 0.92);
  const ref = useTl((tl, q, root) => {
    const { land } = cardLife(tl, q, root, p, m, dur, u, U, markHits(p));
    sourceIn(tl, q, Math.max(0, land - 0.3 * m.k));
  }, [p.src, w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  const cap = <Capture src={p.src} size={p.size} marks={p.marks} highlight={p.highlight} bw={cw} bh={ch} dur={dur} look={look} m={m} font={fonts.body}
    light zoom={p.zoom ?? 1.45} chrome={false} />;
  return (
    <div ref={ref} style={center}>
      <div className="cv-in" style={{ opacity: 0 }}><div className="cv-hit">
        {head ? (
          <div style={{ background: "#fff", borderRadius: 30 * s, padding: r.pad, boxShadow: depth(U * 0.8) }}>
            <Source p={p} s={s} font={fonts.body} />
            <div style={{ position: "relative", width: cw, height: ch, overflow: "hidden", borderRadius: 8 * s }}>{cap}</div>
          </div>
        ) : (
          <div style={{ position: "relative", width: cw, height: ch, borderRadius: (look.radius / 100) * Math.min(w, h), boxShadow: depth(u) }}>{cap}</div>
        )}
      </div></div>
    </div>
  );
};

// =====================================================================================================
// browser: the real page inside a browser window, scrolling to the marked sentence while a cursor
// travels there and clicks as the highlight lands. props: src, size, url, marks?, highlight?, cursor? (true)
const Browser: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100;
  const { U } = useFrame();
  const bar = Math.max(28, h * 0.09);
  const cw = Math.min(w * 0.96, (h * 0.94 - bar) * 1.7), ch = h * 0.94;
  const vh = ch - bar;
  const iw = p.size?.[0] ?? 1, f = cw / iw;
  const marks: Mark[] = p.marks ?? [];
  const first = marks[0] ?? (p.highlight?.rects?.[0] ? { rect: [p.highlight.rects[0][0] * iw, p.highlight.rects[0][1] * (p.size?.[1] ?? 1),
    p.highlight.rects[0][2] * iw, p.highlight.rects[0][3] * (p.size?.[1] ?? 1)], at: 1.6 } as any : undefined);
  const dh = (p.size?.[1] ?? 0) * f;
  const target: [number, number] | undefined = first ? [(first.rect[0] + first.rect[2] * 0.7) * f,
    bar + Math.min((first.rect[1] + first.rect[3] / 2) * f, dh > vh ? vh * 0.45 : (first.rect[1] + first.rect[3] / 2) * f)] : undefined;
  const ref = useTl((timeline, q, root) => {
    const { tl } = cardLife(timeline, q, root, p, m, dur, u, U, markHits(p));
    if (target && p.cursor !== false) {
      const at = first.at ?? first.at_s ?? 0.8;
      cursorTo(tl, q, [cw * 0.82, ch * 0.96], target, at, m);
      // after the click the hand rests and drifts along the line it clicked, as a reader's does
      if (dur - at > 1.2) tl.to(q(".cursor")[0], { x: target[0] + u * 5, y: target[1] + u * 1.2, duration: dur - at - 0.6, ease: "sine.inOut" }, at + 0.5);
    }
  }, [p.src, p.url, w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  const host = String(p.url ?? "").replace(/^https?:\/\//, "").replace(/\/$/, "");
  return (
    <div ref={ref} style={center}>
      <div className="cv-in" style={{ opacity: 0 }}><div className="cv-hit">
      <div className="br-win" style={{ position: "relative", width: cw, height: ch, borderRadius: u * 2.2, overflow: "hidden", background: "#fff",
        boxShadow: depth(u) }}>
        <div style={{ height: bar, background: "#F1F2F4", borderBottom: "1px solid rgba(0,0,0,0.08)", display: "flex", alignItems: "center", gap: bar * 0.18,
          padding: `0 ${bar * 0.4}px` }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => <div key={c} style={{ width: bar * 0.26, height: bar * 0.26, borderRadius: "50%", background: c }} />)}
          <div style={{ flex: 1, marginLeft: bar * 0.4, height: bar * 0.58, borderRadius: bar * 0.3, background: "#fff", border: "1px solid rgba(0,0,0,0.08)",
            display: "flex", alignItems: "center", padding: `0 ${bar * 0.35}px`, fontFamily: fonts.body, fontSize: bar * 0.32, color: "#3C4043",
            overflow: "hidden", whiteSpace: "nowrap" }}>{host}</div>
        </div>
        <div style={{ position: "relative", width: cw, height: vh }}>
          <Capture src={p.src} size={p.size} marks={marks} highlight={p.highlight} bw={cw} bh={vh} dur={dur} look={look} m={m} font={fonts.body}
            light chrome={false} zoom={p.zoom ?? 1} />
        </div>
        {target && p.cursor !== false ? <div className="cursor" style={{ position: "absolute", left: 0, top: 0, opacity: 0 }}><Cursor s={Math.max(22, u * 4)} /></div> : null}
      </div>
      </div></div>
    </div>
  );
};

// =====================================================================================================
// sticker: the screenshot cropped to the evidence on a white card, the source row (logo_src, label) on
// top, dropped in just before its word, punched as the marked word is said, out upward.
// props: src, size, crop? [x, y, w, h] image px, rotate? (0), marks? (image px), label?, logo_src?
const Sticker: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100;
  const { U, s } = useFrame();
  // capture.mjs sets the sentence on white with 0.7 em of padding; the card has its own, so trim most of it
  const [W0, H0] = [p.size?.[0] ?? 1, p.size?.[1] ?? 1], trim = p.crop ? 0 : Math.round(Math.min(H0 * 0.08, W0 * 0.035));
  const [ix, iy, iw, ih] = p.crop ?? [trim, trim, W0 - 2 * trim, H0 - 2 * trim];
  const r = sourceRow(s), head = headed(p);
  const edge = head ? r.pad : Math.max(12 * s, u * 1.6);
  const [cw, ch] = fitBox([iw, ih], w * 0.98 - edge * 2, h * 0.98 - edge * 2 - (head ? r.h + r.gap : 0));
  const f = cw / iw;
  const rot = Number(p.rotate ?? 0);
  const ref = useTl((tl, q, root) => {
    const { land } = cardLife(tl, q, root, p, m, dur, u, U, markHits(p));
    sourceIn(tl, q, Math.max(0, land - 0.3 * m.k));
  }, [p.src, JSON.stringify(p.crop), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={center}>
      <div className="cv-in" style={{ opacity: 0 }}><div className="cv-hit">
        <div style={{ position: "relative", padding: edge, background: "#fff", borderRadius: 30 * s, boxShadow: depth(U * 0.8), transform: rot ? `rotate(${rot}deg)` : undefined }}>
          {head ? <Source p={p} s={s} font={fonts.body} /> : null}
          <div style={{ position: "relative", width: cw, height: ch, overflow: "hidden", borderRadius: 8 * s }}>
            <div style={{ position: "absolute", left: -ix * f, top: -iy * f }}>
              <Capture src={p.src} size={p.size} marks={p.marks}
                bw={(p.size?.[0] ?? iw) * f} bh={(p.size?.[1] ?? ih) * f} dur={dur} look={look} m={m} font={fonts.body} light chrome={false} />
            </div>
          </div>
        </div>
      </div></div>
    </div>
  );
};

// =====================================================================================================
// chat: an app's chat thread recreated from its real parts (name, logo): the user's message pops, the
// app types its reply. props: app, logo? (src), model? (subtitle), messages: [{from: user|app, text, at?}]
const Chat: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100, t = useT();
  const msgs: { from: string; text: string; at?: number }[] = (p.messages ?? []).slice(0, 4);
  const head = Math.max(34, Math.min(h * 0.17, w * 0.08));
  // a message is its line (1.3) + padding (0.64) + the gap (0.3): tight, so the words stay phone-sized
  const fs = Math.max(22, Math.min(w * 0.05, (h * 0.94 - head) / (msgs.length * 2.24 + 1.2)));
  const cw = Math.min(w * 0.96, Math.max(w * 0.6, h * 1.9));
  const chH = Math.min(h * 0.98, head + msgs.length * fs * 2.24 + fs * 1.2);
  const at = (x: { at?: number }, i: number) => x.at ?? 0.5 + i * 1.1;
  const { U } = useFrame();
  const ref = useTl((timeline, q, root) => {
    const { tl } = cardLife(timeline, q, root, p, m, dur, u, U, msgs.filter((x) => x.from !== "user").map((x) => x.at).slice(0, 3));
    msgs.forEach((x, i) => tl.fromTo(q(`.ch-m-${i}`)[0], { autoAlpha: 0, y: fs * 0.8, scale: 0.92 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.4 * m.k,
      ease: m.pop, transformOrigin: x.from === "user" ? "100% 100%" : "0% 100%" }, at(x, i) - (x.from === "user" ? 0 : 0.45)));
  }, [JSON.stringify(msgs), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={center}>
      <div className="cv-in" style={{ opacity: 0 }}><div className="cv-hit">
      <div className="ch-win" style={{ width: cw, height: chH, borderRadius: u * 2.6, background: "#fff", boxShadow: depth(u), overflow: "hidden",
        fontFamily: fonts.body, display: "flex", flexDirection: "column" }}>
        <div style={{ height: head, display: "flex", alignItems: "center", gap: head * 0.25, padding: `0 ${head * 0.35}px`, borderBottom: "1px solid rgba(0,0,0,0.07)" }}>
          {p.logo ? <Img src={src_(p.logo)!} style={{ height: head * 0.56, width: head * 0.56, objectFit: "contain" }} /> : null}
          <div style={{ fontWeight: 700, fontSize: head * 0.36, color: "#111" }}>{p.app}</div>
          {p.model ? <div style={{ fontSize: head * 0.3, color: "#6B6F76", marginLeft: "auto" }}>{p.model}</div> : null}
        </div>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: fs * 0.3, padding: fs * 0.6 }}>
          {msgs.map((x, i) => {
            const user = x.from === "user";
            const a = at(x, i);
            const typed = user ? x.text : x.text.slice(0, Math.max(0, Math.floor((t - a) * 42)));
            const thinking = !user && t < a;
            return (
              <div key={i} className={`ch-m-${i}`} style={{ alignSelf: user ? "flex-end" : "flex-start", maxWidth: "82%", padding: `${fs * 0.32}px ${fs * 0.65}px`,
                borderRadius: fs * 0.9, background: user ? "#111" : "#F1F2F4", color: user ? "#fff" : "#111", fontSize: fs, lineHeight: 1.3, opacity: 0 }}>
                {thinking ? <span style={{ letterSpacing: fs * 0.15, color: "#8A8F98" }}>{"•••".slice(0, 1 + (Math.floor(t * 4) % 3))}</span>
                  : <>{typed}<span style={{ opacity: typed.length < x.text.length ? 1 : 0 }}>▍</span></>}
              </div>
            );
          })}
        </div>
      </div>
      </div></div>
    </div>
  );
};

// =====================================================================================================
// terminal: a real terminal window; commands type in with a caret, their output lands under them.
// props: title?, lines: [{text, kind: cmd|out, at?}]
const Terminal: React.FC<TP> = ({ p, w, h, m, dur }) => {
  const u = Math.min(w, h) / 100, t = useT();
  const lines: { text: string; kind?: string; at?: number }[] = (p.lines ?? []).slice(0, 8);
  const bar = Math.max(26, h * 0.1);
  const cw = Math.min(w * 0.96, h * 1.9), ch = h * 0.94;
  const longest = Math.max(...lines.map((l) => l.text.length + 2), 10);
  const fs0 = Math.max(18, Math.min((ch - bar) / (lines.length * 1.6 + 1), (cw * 0.9) / (longest * 0.66)));
  const fs = fs0;
  const tH = Math.min(ch, bar + lines.length * fs * 1.55 + fs * 1.6);
  let clock = 0.5;
  const times = lines.map((l) => {
    const a = l.at ?? clock;
    clock = a + (l.kind === "out" ? 0.25 : l.text.length / 30 + 0.35);
    return a;
  });
  const { U } = useFrame();
  const ref = useTl((timeline, q, root) => {
    // the hit: each command's output landing
    cardLife(timeline, q, root, p, m, dur, u, U, lines.map((l, i) => (l.kind === "out" ? times[i] : undefined)).slice(0, 3));
  }, [JSON.stringify(lines), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={center}>
      <div className="cv-in" style={{ opacity: 0 }}><div className="cv-hit">
      <div className="tm-win" style={{ width: cw, height: tH, borderRadius: u * 2, background: "#0E0F12", boxShadow: depth(u), overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.08)" }}>
        <div style={{ height: bar, display: "flex", alignItems: "center", gap: bar * 0.2, padding: `0 ${bar * 0.4}px`, background: "#1A1B1F" }}>
          {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => <div key={c} style={{ width: bar * 0.28, height: bar * 0.28, borderRadius: "50%", background: c }} />)}
          <div style={{ flex: 1, textAlign: "center", color: "#8B8E97", fontFamily: MONO, fontSize: bar * 0.36 }}>{p.title ?? ""}</div>
        </div>
        <div style={{ padding: fs * 0.7, fontFamily: MONO, fontSize: fs, lineHeight: 1.55, color: "#E6E6E6", whiteSpace: "pre" }}>
          {lines.map((l, i) => {
            const a = times[i];
            if (t < a) return null;
            const cmd = l.kind !== "out";
            const shown = cmd ? l.text.slice(0, Math.floor((t - a) * 30)) : l.text;
            const live = cmd && shown.length < l.text.length;
            return <div key={i} style={{ color: cmd ? "#F2F2F2" : "#9DA3AE", opacity: cmd ? 1 : prog(t, a, 0.2, "power1.out") }}>
              {cmd ? <span style={{ color: "#5FD68A" }}>$ </span> : null}{shown}
              {live || (cmd && i === lines.length - 1 && Math.floor(t * 2) % 2 === 0) ? <span style={{ background: "#E6E6E6", color: "#0E0F12" }}> </span> : null}
            </div>;
          })}
        </div>
      </div>
      </div></div>
    </div>
  );
};

// =====================================================================================================
// toasts: real notifications (the app's own logo and name) slide in from the top and stack.
// props: items: [{app, src, title, body?, at?}]
const Toasts: React.FC<TP> = ({ p, w, h, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100;
  const items: { app: string; src?: string; title: string; body?: string; at?: number }[] = (p.items ?? []).slice(0, 3);
  const th = Math.min(h / (items.length + 0.4), w * 0.24), cw = Math.min(w * 0.94, th * 4.6);
  const at = (x: { at?: number }, i: number) => x.at ?? 0.3 + i * 0.7;
  const { U } = useFrame();
  const ref = useTl((timeline, q, root) => {
    const { tl, L } = wordTl(timeline, p, landAt(p, m), m);
    camera(tl, q, root, m, dur, u, p.ambient);
    items.forEach((x, i) => {
      // each drops in from above just before its word, blurred; the older ones are pushed down a slot on it
      const pos = x.at === undefined ? at(x, i) : L(x, -0.3 * m.k);
      if (p.enter) fitIn(tl, q(`.to-${i}`)[0], x.at === undefined ? at(x, i) : L(x), p.enter, U);   // the creator's measured entrance
      else dropIn(tl, q(`.to-${i}`)[0], pos, m, th * 0.9);
      for (let j = 0; j < i; j++) tl.to(q(`.to-${j}`)[0], { y: (i - j) * th * 1.08, duration: 0.5 * m.k, ease: "power3.out" }, pos);
    });
    if (p.exit) fitOut(tl, q(".to-all")[0], dur, p.exit, U);
    else exitUp(tl, q(".to-all")[0], m, dur, U * 4.6);
  }, [JSON.stringify(items), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={{ ...fill, display: "flex", justifyContent: "center" }}>
      <div className="to-all" style={{ position: "relative", width: cw, height: h }}>
        {items.map((x, i) => (
          <div key={i} className={`to-${i}`} style={{ position: "absolute", left: 0, top: h * 0.03, width: cw, height: th, borderRadius: th * 0.24,
            background: "rgba(250,250,252,0.97)", boxShadow: depth(u * 0.8), display: "flex", alignItems: "center", gap: th * 0.16, padding: `0 ${th * 0.18}px`,
            fontFamily: fonts.body, boxSizing: "border-box", opacity: 0 }}>
            {x.src ? <Img src={src_(x.src)!} style={{ width: th * 0.46, height: th * 0.46, objectFit: "contain", borderRadius: th * 0.1 }} /> : null}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: "flex", fontSize: th * 0.15, color: "#6B6F76", fontWeight: 600, letterSpacing: "0.02em" }}>
                <span style={{ textTransform: "uppercase" }}>{x.app}</span><span style={{ marginLeft: "auto" }}>now</span></div>
              <div style={{ fontSize: th * 0.21, fontWeight: 700, color: "#111", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{x.title}</div>
              {x.body ? <div style={{ fontSize: th * 0.18, color: "#3C4043", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{x.body}</div> : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// =====================================================================================================
// logo_cluster: real logos pop around the speaker's head, bare with a soft shadow, staggered, bobbing.
// props: logos: [{src, at?}], head? [x, y, w, h] % of the card box (plan.py fills it from face.json)
const LogoCluster: React.FC<TP> = ({ p, w, h, m, dur }) => {
  const u = Math.min(w, h) / 100;
  const logos: { src: string; at?: number }[] = (p.logos ?? []).slice(0, 6);
  const [hx, hy, hw, hh] = p.head ?? [32, 33, 28, 23];
  const cx = ((hx + hw / 2) / 100) * w, cy = ((hy + hh / 2) / 100) * h;
  const R = Math.max((hw / 100) * w, (hh / 100) * h) * 0.92;
  const S = Math.min(w * 0.15, R * 0.62);
  const n = logos.length;
  const r = rng(Number(p.seed ?? 3));
  // spread over the upper arc, from left of the head over the top to the right
  const spots = logos.map((_, i) => {
    const a = (-180 + 20 + (n === 1 ? 70 : (i * 140) / Math.max(1, n - 1))) * (Math.PI / 180);
    const x = Math.min(w * 0.84 - S / 2, Math.max(S * 0.6, cx + Math.cos(a) * R * 1.15)); // clear of the frame edge and the app rail
    return [x, Math.max(h * 0.12 + S / 2, cy + Math.sin(a) * R * 1.05), (r() - 0.5) * 16, r() * 6.28];
  });
  const { U } = useFrame();
  const ref = useTl((timeline, q) => {
    const { tl, L } = wordTl(timeline, p, landAt(p, m), m);
    q(".lc-logo").forEach((el, i) => {
      const a = logos[i].at ?? 0.15 + i * 0.16;
      // drops in blurred just before its word, lands with a spring, punches on the word, bobs, leaves upward
      if (p.enter) fitIn(tl, el, L(logos[i]), p.enter, U);   // the creator's measured entrance
      else tl.fromTo(el, { scale: 0.6, y: -U * 4, rotate: spots[i][2] - 12, autoAlpha: 0, filter: "blur(8px)" },
        { scale: 1, y: 0, rotate: spots[i][2], autoAlpha: 1, filter: "blur(0px)", duration: 0.5 * m.k, ease: "back.out(1.7)" }, L(logos[i], -0.25 * m.k));
      punch(tl, q(`.lc-hit-${i}`)[0], L(logos[i]), 1.08);
      if (dur > 1.5) tl.fromTo(q(`.lc-bob-${i}`)[0], { y: 0 }, { y: -u * 1.4, duration: 1.1 + (i % 3) * 0.2, ease: "sine.inOut", yoyo: true,
        repeat: Math.max(0, Math.floor((dur - a - 0.6) / 1.2)) }, a + 0.5);
      if (p.exit) fitOut(tl, el, dur, p.exit, U);
      else if (dur > m.out * 3) tl.to(el, { y: -U * 4, autoAlpha: 0, filter: "blur(6px)", duration: Math.max(0.24, m.out * 0.7), ease: m.exit }, dur - m.out + i * 0.03);
    });
  }, [JSON.stringify(logos), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={fill}>
      {logos.map((l, i) => (
        <div key={i} className="lc-logo" style={{ position: "absolute", left: spots[i][0] - S / 2, top: spots[i][1] - S / 2, width: S, height: S, opacity: 0 }}>
          <div className={`lc-bob-${i}`} style={fill}><div className={`lc-hit-${i}`} style={fill}>
            <Img src={src_(l.src)!} style={{ width: "100%", height: "100%", objectFit: "contain", filter: `drop-shadow(0 0 ${u * 1.4}px rgba(255,255,255,0.6)) drop-shadow(0 ${u * 0.8}px ${u * 1.6}px rgba(0,0,0,0.35))` }} />
          </div></div>
        </div>
      ))}
    </div>
  );
};

// =====================================================================================================
// side_by_side: two real screenshots slide in from both edges over the footage and settle tilted
// toward each other. props: a: {src, size, crop?, label?, marks?}, b: {...}
const SideBySide: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100;
  const gap = w * 0.04, colW = (w - gap) / 2;
  const sides = [p.a ?? {}, p.b ?? {}];
  // each card at its own ratio, the pair centred as one group (a wide and a tall shot stay balanced)
  // a side may crop its capture to the evidence: crop [x, y, w, h] in image px
  const fits = sides.map((x) => fitBox(x.crop ? [x.crop[2], x.crop[3]] : x.size, colW, h * 0.8));
  const { U } = useFrame();
  const ref = useTl((timeline, q, root) => {
    const { tl, L } = wordTl(timeline, p, landAt(p, m), m);
    camera(tl, q, root, m, dur, u, p.ambient);
    sides.forEach((x, i) => {
      const el = q(`.sb-${i}`)[0];
      // a then b drop in just before the word, each settling a little toward the other; marks punch their side
      if (p.enter) fitIn(tl, el, L("in", i * 0.14), p.enter, U);   // the creator's measured entrance
      else dropIn(tl, el, L("in", -0.3 * m.k + i * 0.14), m, U * 6.5);
      (x.marks ?? []).slice(0, 2).forEach((mk: object) => punch(tl, q(`.sb-hit-${i}`)[0], L(mk)));
      const tag = q(`.sb-tag-${i}`)[0];
      if (tag) tl.fromTo(tag, { autoAlpha: 0, y: u * 2 }, { autoAlpha: 1, y: 0, duration: 0.4, ease: m.pop }, L("in", 0.15 + i * 0.14));
      if (p.exit) fitOut(tl, el, dur, p.exit, U);
      else exitUp(tl, el, m, dur, U * 4.6);
    });
  }, [JSON.stringify(sides.map((x) => x.src)), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={{ ...fill, display: "flex", alignItems: "center", justifyContent: "center", gap }}>
      {sides.map((x, i) => {
        const [cw, ch] = fits[i];
        return (
          <div key={i} style={{ width: cw, display: "flex", justifyContent: "center" }}>
            <div className={`sb-${i}`} style={{ opacity: 0 }}><div className={`sb-hit-${i}`}>
            <div style={{ position: "relative", width: cw, height: ch, borderRadius: u * 2, boxShadow: depth(u), transform: `rotate(${i ? 1.2 : -1.2}deg)` }}>
              {x.src && x.crop ? (() => {
                const f = cw / x.crop[2];
                return <div style={{ ...fill, overflow: "hidden", borderRadius: u * 2, background: "#fff" }}>
                  <div style={{ position: "absolute", left: -x.crop[0] * f, top: -x.crop[1] * f }}>
                    <Capture src={x.src} size={x.size} marks={x.marks} bw={x.size[0] * f} bh={x.size[1] * f} dur={dur} look={look} m={m} font={fonts.body} light chrome={false} />
                  </div></div>;
              })() : x.src ? <Capture src={x.src} size={x.size} marks={x.marks} bw={cw} bh={ch} dur={dur} look={look} m={m} font={fonts.body} light chrome={false} /> : null}
              <Tag cls={`sb-tag-${i}`} text={x.label} u={u} look={look} font={fonts.body} style={{ left: u * 1.5, top: -u * 3.5 }} />
            </div>
            </div></div>
          </div>
        );
      })}
    </div>
  );
};

// =====================================================================================================
// video_card: a short real clip (the user's own, or a recorded page) in a rounded card over the
// footage. props: src (a video in images/), size? [w, h], start_s? (0), label?, rate? (1)
const VideoCard: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const u = Math.min(w, h) / 100;
  const { fps } = useVideoConfig();
  const [cw, ch] = fitBox(p.size, w * 0.96, h * 0.92, 16 / 9);
  const { U } = useFrame();
  const ref = useTl((timeline, q, root) => {
    const { tl, L } = cardLife(timeline, q, root, p, m, dur, u, U);
    const tag = q(".vc-tag")[0];
    if (tag) tl.fromTo(tag, { autoAlpha: 0, y: u * 2 }, { autoAlpha: 1, y: 0, duration: 0.4, ease: m.pop }, L("in", 0.1));
  }, [p.src, w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);
  return (
    <div ref={ref} style={center}>
      <div className="cv-in" style={{ opacity: 0 }}><div className="cv-hit">
      <div className="vc-card" style={{ position: "relative", width: cw, height: ch, borderRadius: u * 2.4, boxShadow: depth(u) }}>
        <div style={{ ...fill, borderRadius: u * 2.4, overflow: "hidden", background: "#000" }}>
          {p.src ? <OffthreadVideo src={src_(p.src)!} muted startFrom={Math.round(Number(p.start_s ?? 0) * fps)} playbackRate={Number(p.rate ?? 1)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : null}
        </div>
        <Tag cls="vc-tag" text={p.label} u={u} look={look} font={fonts.body} style={{ left: u * 2, top: -u * 3.5 }} />
      </div>
      </div></div>
    </div>
  );
};

export const OVERLAYS: Record<string, React.FC<TP>> = {
  shot: Shot, browser: Browser, sticker: Sticker, chat: Chat, terminal: Terminal, toasts: Toasts, logo_cluster: LogoCluster,
  side_by_side: SideBySide, video_card: VideoCard,
};
