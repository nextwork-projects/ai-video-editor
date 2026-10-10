// The diagram: how work moves between real things, built from the HyperFrames talking-head-recut router
// (p2 of the same-prompt test) on one word-labelled GSAP timeline (motion.ts wordTl).
// - Nodes are white cards holding the real logo and a label (a readable surface over any footage), on a
//   soft dark veil. Labels are at least 40 px on a 1080 frame, measured, never guessed.
// - Wires draw along their length. A packet (a dot riding a hot wire) runs the wire and LANDS on the
//   spoken word: the destination's ring pops, the card punches, its name takes the accent, the other
//   branches dim. Between beats the board resets.
// - A task chip ("small task") pops on its word left of the source; a heavy one slams in. The chip is
//   swallowed by the node it feeds, the node pulses, then the packet leaves.
// Shapes: a chain of 1-6 nodes (sequential steps, each landing on its word; 4+ wrap to two rows) and,
// optionally, 2-4 branches off the last node (the options a router picks between).
// props (type "flow"): nodes: [Part], split?: [Part], tasks?: [{text, at, heavy?}], accent?: "#hex", tag?: {text, at}
// Part: {src?, label? (string, or [{text, at}] swapping on words), lines?: [{text, at}] (stacked names,
// each lighting on its word), at? (the landing), off_at? (dims)}. plan.py turns each word into at.
import React from "react";
import { Img, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { measureText } from "@remotion/layout-utils";
import { camera, exitUp, fitOut, landAt, punch, useTl, wordTl } from "./motion";
import type { TP } from "./Templates";

type Line = { text: string; at?: number; word?: string };
type Part = { src?: string; label?: string | Line[]; lines?: Line[]; at?: number; off_at?: number; word?: string };
type Task = { text: string; at?: number; word?: string; heavy?: boolean };

const src_ = (s?: string) => (!s ? undefined : /^(https?:|data:)/.test(s) ? s : staticFile(s));
const labelNow = (lab: Part["label"], t: number): string =>
  typeof lab === "string" || !lab ? lab ?? "" : [...lab].reverse().find((l) => (l.at ?? 0) <= t)?.text ?? lab[0]?.text ?? "";
const labelMax = (lab: Part["label"]): string =>
  typeof lab === "string" || !lab ? lab ?? "" : lab.reduce((a, l) => (l.text.length > a.length ? l.text : a), "");
const luminance = (c: string) => {
  const m = c.match(/^#([0-9a-f]{6})$/i);
  if (!m) return 0.5;
  const n = parseInt(m[1], 16);
  return (0.2126 * (n >> 16) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;
};

type Box = { x: number; y: number; w: number; h: number };
const mid = (b: Box) => [b.x + b.w / 2, b.y + b.h / 2] as const;

export const Diagram: React.FC<TP> = ({ p, w, h, look, m, fonts, dur }) => {
  const { width: FW, height: FH, fps } = useVideoConfig();
  const t = useCurrentFrame() / fps;
  const U = Math.min(FW, FH) / 100, s = U / 10.8, u = Math.min(w, h) / 100;
  const LAB = 40 * s;
  // a full-frame scene sits on the look's own ground: no veil, ink wires (overlay boxes are never this big)
  const scene = w > FW * 0.65 && h > FH * 0.45; // the vertical scene box is 72% wide (Scene.tsx sceneBox)
  const chain: Part[] = (p.nodes ?? []).slice(0, 6);
  const branches: Part[] = (p.split ?? []).slice(0, Math.max(0, Math.min(4, 6 - chain.length)));
  const tasks: Task[] = (p.tasks ?? []).filter((x: Task) => x?.text).slice(0, 4);
  if (!chain.length) return null;
  const accent: string = p.accent ?? (luminance(look.accent) < 0.3 ? look.mark : look.accent);
  // a name takes the accent only where it stays readable on the white card; the ring always does
  const nameHot = luminance(accent) < 0.62 ? accent : "#141414";
  const F = fonts.body;
  const tw = (text: string, fs: number, wt = 700) => (measureText({ text: text || " ", fontFamily: F, fontWeight: wt, fontSize: 100 }).width * fs) / 100;
  const n = chain.length, k = branches.length;

  // ---------- layout (box px). Shrinks pictures and gaps to fit, never type under LAB. ----------
  const P = Math.min(w, h) * 0.03;
  const chipFs = Math.max(LAB, Math.min(44 * s, h * 0.11)), chipH = chipFs * 2.15;
  const chipW = (x: Task) => tw(x.text, chipFs, 800) + chipFs * (x.heavy ? 2.3 : 1.6) + chipFs * 1.3;
  // a portrait box (a vertical scene or the split panel) has no width to spare for a lane of chips left of
  // the source: the chips stack over it instead, and the cards get the whole width
  const stack = w < h;
  const laneW = k && tasks.length && !stack ? Math.max(...tasks.map(chipW)) + 28 * s : 0;
  const rows = !k && n >= 4 ? 2 : 1;
  const perRow = Math.ceil(n / rows);
  const rowGap = Math.max(16 * s, h * (rows > 1 ? 0.08 : 0.05));
  let f = 1, nodes: Box[] = [], bx: Box[] = [], nFs = LAB, bFs: number[] = [], logoN = 0, logoB = 0, ox = 0;
  for (; f >= 0.45; f -= 0.05) {
    const rowH = (h - 2 * P - (rows - 1) * rowGap) / rows;
    // a portrait box is a phone's whole frame: the cards may grow past the overlay size to fill it
    const S = Math.min(rowH * (rows > 1 ? 0.94 : 1), (k ? h * 0.6 : rowH) * f, (stack ? 340 : 240) * s * f);
    nFs = Math.max(LAB, Math.min(46 * s, S * 0.23));
    logoN = S * 0.46;
    const nw = chain.map((x) => Math.max(S * 0.92, tw(labelMax(x.label), nFs) + 40 * s));
    // branches: one row each, stacked; a branch card is its logo, then its name (or stacked names)
    const rh = k ? Math.min(h * 0.46, 190 * s, (h - 2 * P - rowGap * (k - 1)) / k) : 0;
    logoB = Math.min(rh * 0.5, 70 * s * Math.max(f, 0.8));
    const names = (x: Part) => (x.lines?.length ? x.lines.map((l) => l.text) : [labelMax(x.label)]);
    bFs = branches.map((x) => Math.max(LAB, Math.min(58 * s, (rh * 0.8) / (names(x).length * 1.08))));
    const bW = k ? Math.max(...branches.map((x, j) => logoB + 22 * s + Math.max(...names(x).map((l) => tw(l, bFs[j], 800))) + 56 * s)) : 0;
    const wireMin = 56 * s * f, wireB = 120 * s * f;
    const rowW = (i0: number, i1: number) => nw.slice(i0, i1).reduce((a, b) => a + b, 0) + Math.max(0, i1 - i0 - 1) * wireMin;
    const need = laneW + rowW(0, perRow) + (k ? wireB + bW : 0) + 2 * P;
    if (need > w && f > 0.5) continue;
    // spread the spare width into the wires (capped), centre the rest
    const spare = Math.max(0, w - need);
    const nWires = Math.max(0, perRow - 1) + (k ? 1.6 : 0);
    const add = nWires ? Math.min(spare / nWires, 90 * s) : 0;
    const gN = wireMin + add, gB = wireB + add * 1.6;
    // the cards centred on the box (the chips are swallowed before the board settles); the lane, if any, left of them
    const core = rowW(0, perRow) + Math.max(0, perRow - 1) * add + (k ? gB + bW : 0);
    ox = Math.max(P, (w - core) / 2 - laneW);
    nodes = [];
    for (let i = 0; i < n; i++) {
      const r = Math.floor(i / perRow), c = i % perRow;
      // two rows run as a snake: the second row comes back right to left under the first
      const col = r ? perRow - 1 - c : c;
      let x = ox + laneW;
      for (let j = 0; j < col; j++) x += nw[j] + gN;
      const cy = rows === 1 ? h / 2 : P + rowH / 2 + r * (rowH + rowGap);
      nodes.push({ x, y: cy - S / 2, w: nw[i], h: S });
    }
    const bx0 = nodes[n - 1].x + nodes[n - 1].w + gB;
    bx = branches.map((_, j) => ({ x: bx0, y: h / 2 + (j - (k - 1) / 2) * (rh + rowGap) - rh / 2, w: bW, h: rh }));
    break;
  }
  // wires: chain links (straight, or down between rows), then a curve from the last node to each branch
  type Wire = { d: string; from: number; to: number; branch: boolean };
  const wires: Wire[] = [];
  for (let i = 1; i < n; i++) {
    const a = nodes[i - 1], b = nodes[i];
    const same = Math.abs(a.y - b.y) < 1;
    const d = same
      ? (b.x > a.x ? `M${a.x + a.w} ${a.y + a.h / 2} L${b.x} ${b.y + b.h / 2}` : `M${a.x} ${a.y + a.h / 2} L${b.x + b.w} ${b.y + b.h / 2}`)
      : `M${mid(a)[0]} ${a.y + a.h} L${mid(b)[0]} ${b.y}`;
    wires.push({ d, from: i - 1, to: i, branch: false });
  }
  const last = nodes[n - 1];
  branches.forEach((_, j) => {
    const x1 = last.x + last.w, y1 = last.y + last.h / 2, x2 = bx[j].x, y2 = bx[j].y + bx[j].h / 2, dx = (x2 - x1) * 0.55;
    wires.push({ d: `M${x1} ${y1} C${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`, from: n - 1, to: j, branch: true });
  });

  // ---------- timing: every move placed off a spoken word ----------
  const land = chain[0].at ?? landAt(p, m, false);
  const chainAt = chain.reduce<number[]>((acc, x, i) => [...acc, x.at ?? (i ? acc[i - 1] + 0.6 * m.k : land)], []);
  const bAt = branches.map((x) => x.at ?? x.lines?.[0]?.at);
  // a landing: a packet runs a wire and lands on its node's word
  type Landing = { wire: number; at: number; target: number; branch: boolean; travel: number; chip?: number };
  const landings: Landing[] = [];
  if (k) bAt.forEach((a, j) => a !== undefined && landings.push({ wire: n - 1 + j, at: a, target: j, branch: true, travel: 0.62 * m.k }));
  else chainAt.forEach((a, i) => i > 0 && chain[i].at !== undefined && landings.push({ wire: i - 1, at: a, target: i, branch: false,
    travel: Math.max(0.25, Math.min(0.62 * m.k, a - chainAt[i - 1] - 0.15)) }));
  landings.sort((a, b) => a.at - b.at);
  // each chip feeds the first landing after it
  [...tasks].map((x, i) => ({ x, i })).filter(({ x }) => x.at !== undefined).sort((a, b) => a.x.at! - b.x.at!).forEach(({ x, i }) => {
    const l = landings.find((l) => l.chip === undefined && l.at > x.at! + 0.3);
    if (l) { l.chip = i; l.travel = Math.max(0.3, Math.min(0.65, l.at - x.at! - 0.55)); }
  });
  const reveal = Math.max(0.05, Math.min(chainAt[n - 1] + 0.35, (landings[0]?.at ?? Infinity) - 1.0));
  const sw = 4 * s, hot = 7 * s;

  const ref = useTl((timeline, q, root) => {
    const { tl, L } = wordTl(timeline, p, land, m);
    camera(tl, q, root, m, dur, u, p.ambient);
    const el = (c: string) => q(c)[0];
    const veil = el(".dg-veil");   // none on a scene's own ground: no tween, so GSAP warns of no missing target
    if (veil) tl.fromTo(veil, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.5, ease: "sine.out" }, Math.max(0, land - 0.3));
    // the chain: the first node spins up on its word, the others pop as their packet lands
    chain.forEach((x, i) => {
      const at = i === 0 || x.at === undefined || k ? L(x.at === undefined ? chainAt[i] : x, -0.15) : L(x, -0.22);
      tl.fromTo(el(`.dg-n-${i}`), { autoAlpha: 0, scale: i ? 0.6 : 0.4, rotate: i ? 0 : -60 },
        { autoAlpha: 1, scale: 1, rotate: 0, duration: 0.55 * m.k, ease: "back.out(1.7)" }, at);
      const lab = el(`.dg-nl-${i}`);
      if (lab) tl.fromTo(lab, { autoAlpha: 0, y: 12 * s }, { autoAlpha: 1, y: 0, duration: 0.35, ease: "power3.out" }, typeof at === "number" ? at + 0.18 : `${at}+=0.18`);
      if (x.off_at !== undefined) tl.to(el(`.dg-n-${i}`), { opacity: 0.45, duration: 0.3, ease: "sine.inOut" }, L(x.off_at));
    });
    // chain links draw as the next node is reached (no packet: a straight draw ahead of the pop)
    wires.forEach((wi, j) => {
      const path = el(`.dg-w-${j}`);
      const at = wi.branch ? reveal + 0.3 + wi.to * 0.1 : Math.max(0, chainAt[wi.to] - 0.45 * m.k);
      tl.fromTo(path, { drawSVG: "0%", opacity: 1 }, { drawSVG: "100%", duration: 0.5 * m.k, ease: "power2.inOut" }, at);
    });
    // the branches slide in from the right, staggered, once the source is up
    branches.forEach((_, j) => tl.fromTo(el(`.dg-b-${j}`), { autoAlpha: 0, x: 90 * s }, { autoAlpha: 1, x: 0, duration: 0.55 * m.k, ease: "expo.out" }, reveal + j * 0.12));
    // tasks: a light chip pops on its word, a heavy one slams in; each is swallowed by the node it feeds
    tasks.forEach((x, c) => {
      const chip = el(`.dg-chip-${c}`);
      if (x.at === undefined) return;
      tl.fromTo(chip, x.heavy ? { autoAlpha: 0, scale: 1.35, y: -24 * s } : { autoAlpha: 0, scale: 0.6, x: -30 * s },
        { autoAlpha: 1, scale: 1, y: 0, x: 0, duration: x.heavy ? 0.3 : 0.4, ease: x.heavy ? "power4.out" : "back.out(1.7)" }, L(x, x.heavy ? -0.04 : -0.08));
    });
    landings.forEach((l, li) => {
      const depart = l.at - l.travel;
      const wire = wires[l.wire];
      const src = nodes[wire.from];
      // the chip flies into its node, which pulses, then the packet leaves
      if (l.chip !== undefined) {
        const x = tasks[l.chip], chip = el(`.dg-chip-${l.chip}`);
        const go = Math.max(x.at! + 0.28, depart - 0.38);
        tl.to(chip, stack ? { y: src.h / 2 + chipH * 0.6, scale: 0.2, autoAlpha: 0, duration: Math.max(0.2, depart - go), ease: "power3.in" }
          : { x: src.x + src.w / 2 - (ox + chipW(x) / 2), scale: 0.2, autoAlpha: 0, duration: Math.max(0.2, depart - go), ease: "power3.in" }, go);
      }
      tl.fromTo(el(`.dg-pulse-${wire.from}`), { opacity: 0.9, scale: 1 }, { opacity: 0, scale: 1.5, duration: 0.5, ease: "power2.out", immediateRender: false }, depart);
      punch(tl, el(`.dg-nh-${wire.from}`), depart, 1.1);
      // the others dim while this one is chosen
      if (l.branch) branches.forEach((_, j) => tl.to(el(`.dg-b-${j}`), { opacity: j === l.target ? 1 : 0.45, duration: 0.3, ease: "sine.inOut" }, depart));
      const hotPath = el(`.dg-h-${l.wire}`), dot = el(`.dg-d-${l.wire}`);
      tl.fromTo(hotPath, { drawSVG: "0%", opacity: 1 }, { drawSVG: "100%", duration: l.travel, ease: "power2.inOut", immediateRender: false }, depart);
      tl.set(dot, { opacity: 1 }, depart);
      tl.fromTo(dot, { motionPath: { path: hotPath as SVGPathElement, align: hotPath as SVGPathElement, alignOrigin: [0.5, 0.5], start: 0, end: 0 } },
        { motionPath: { path: hotPath as SVGPathElement, align: hotPath as SVGPathElement, alignOrigin: [0.5, 0.5], start: 0, end: 1 },
          duration: l.travel, ease: "power2.inOut", immediateRender: false }, depart);
      tl.to(dot, { opacity: 0, duration: 0.12, ease: "power1.in" }, l.at);
      // the landing, on the word: ring pops, the card punches, the name takes the accent
      const tgt = l.branch ? `b-${l.target}` : `n-${l.target}`;
      const lp = l.branch ? L(branches[l.target].at !== undefined ? branches[l.target] : branches[l.target].lines?.[0]) : L(chain[l.target]);
      tl.fromTo(el(`.dg-ring-${tgt}`), { opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.25, ease: "power3.out", immediateRender: false }, lp);
      punch(tl, el(`.dg-hit-${tgt}`), lp, 1.08);
      tl.to(el(`.dg-name-${tgt}-0`), { color: nameHot, duration: 0.15, ease: "none" }, lp);
      // reset before the next beat: the hot wire and the ring fade, the board comes back
      const next = landings[li + 1];
      if (next) {
        const nextChip = next.chip !== undefined ? tasks[next.chip].at! : next.at - next.travel;
        const rs = Math.max(l.at + 0.45, Math.min(l.at + 0.8, nextChip - 0.3));
        tl.to(hotPath, { opacity: 0, duration: 0.3, ease: "power1.in" }, rs);
        tl.to(el(`.dg-ring-${tgt}`), { opacity: 0, duration: 0.25, ease: "power1.in" }, rs);
        tl.to(el(`.dg-name-${tgt}-0`), { color: "#141414", duration: 0.2, ease: "none" }, rs);
        if (l.branch) branches.forEach((_, j) => tl.to(el(`.dg-b-${j}`), { opacity: 1, duration: 0.3, ease: "sine.inOut" }, rs));
      }
    });
    // stacked names: each later name lights on its own word
    branches.forEach((x, j) => (x.lines ?? []).forEach((ln, i) => {
      if (i === 0 || ln.at === undefined) return;
      tl.to(el(`.dg-name-b-${j}-${i}`), { color: nameHot, duration: 0.12, ease: "none" }, L(ln));
      tl.fromTo(el(`.dg-name-b-${j}-${i}`), { scale: 1.18 }, { scale: 1, duration: 0.4, ease: "back.out(2.2)", immediateRender: false }, L(ln));
    }));
    if (p.tag?.text) tl.fromTo(el(".dg-tag"), { scale: 0, rotate: -8 }, { scale: 1, rotate: 0, duration: 0.5, ease: m.pop }, L(p.tag, 0));
    if (p.exit) fitOut(tl, el(".dg-all"), dur, p.exit, U);   // the creator's measured exit
    else exitUp(tl, el(".dg-all"), m, dur, U * 4.6);
    if (veil && dur > m.out * 2) tl.to(veil, { autoAlpha: 0, duration: 0.35, ease: "power1.in" }, dur - 0.35);
  }, [JSON.stringify([chain, branches, tasks, p.tag, p.accent]), w, h, dur, m.name, JSON.stringify([p.enter, p.exit, p.ambient, p.word_at])]);

  const shadow = `0 ${1.2 * U}px ${3 * U}px -${0.8 * U}px rgba(0,0,0,0.55), 0 ${0.15 * U}px ${0.4 * U}px rgba(0,0,0,0.25)`;
  const ring = (cls: string, r: number): React.ReactNode => (
    <div className={cls} style={{ position: "absolute", inset: -6 * s, borderRadius: r + 6 * s, border: `${6 * s}px solid ${accent}`, opacity: 0 }} />
  );
  const logo = (src: string | undefined, size: number, letter: string) => src
    ? <Img src={src_(src)!} style={{ width: size, height: size, objectFit: "contain", flexShrink: 0 }} />
    : <div style={{ width: size, height: size, borderRadius: size * 0.22, background: "#141414", color: "#fff", display: "flex", alignItems: "center",
      justifyContent: "center", fontFamily: F, fontWeight: 800, fontSize: size * 0.5, flexShrink: 0 }}>{letter}</div>;
  return (
    <div ref={ref} style={{ position: "absolute", inset: 0 }}>
      {/* a soft veil: separates the board from a busy wall without a panel (not on a scene's own ground) */}
      {scene ? null : <div className="dg-veil" style={{ position: "absolute", left: -w * 0.08, right: -w * 0.08, top: -h * 0.35, bottom: -h * 0.3, opacity: 0,
        background: "radial-gradient(ellipse 60% 55% at 50% 50%, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0.26) 55%, rgba(0,0,0,0) 100%)" }} />}
      <div className="dg-all" style={{ position: "absolute", inset: 0 }}>
        <svg width={w} height={h} style={{ position: "absolute", inset: 0, overflow: "visible", filter: `drop-shadow(0 ${2 * s}px ${4 * s}px rgba(0,0,0,0.45))` }}>
          {wires.map((wi, j) => <path key={j} className={`dg-w-${j}`} d={wi.d} fill="none" stroke={scene ? "rgba(20,20,20,0.32)" : "rgba(255,255,255,0.78)"} strokeWidth={sw} strokeLinecap="round" opacity={0} />)}
          {wires.map((wi, j) => <path key={j} className={`dg-h-${j}`} d={wi.d} fill="none" stroke={accent} strokeWidth={hot} strokeLinecap="round" opacity={0} />)}
          {wires.map((_, j) => <circle key={j} className={`dg-d-${j}`} r={12 * s} cx={0} cy={0} fill="#fff" stroke={accent} strokeWidth={5 * s} opacity={0} />)}
        </svg>
        {chain.map((x, i) => {
          const b = nodes[i], r = b.h * 0.22, lab = labelNow(x.label, t);
          return (
            <div key={i} className={`dg-n-${i}`} style={{ position: "absolute", left: b.x, top: b.y, width: b.w, height: b.h, opacity: 0 }}>
              <div className={`dg-pulse-${i}`} style={{ position: "absolute", inset: 0, borderRadius: r, border: `${6 * s}px solid ${accent}`, opacity: 0 }} />
              <div className={`dg-nh-${i}`} style={{ position: "absolute", inset: 0 }}><div className={`dg-hit-n-${i}`} style={{ position: "absolute", inset: 0 }}>
                {ring(`dg-ring-n-${i}`, r)}
                <div style={{ position: "absolute", inset: 0, borderRadius: r, background: "#fff", boxShadow: shadow, display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center", gap: b.h * 0.05 }}>
                  {logo(x.src, lab ? logoN : logoN * 1.4, lab.slice(0, 1))}
                  {lab ? <div className={`dg-nl-${i}`} style={{ fontFamily: F, fontWeight: 700, fontSize: nFs, lineHeight: 1.05, color: "#141414",
                    whiteSpace: "nowrap" }}><span className={`dg-name-n-${i}-0`}>{lab}</span></div> : null}
                </div>
              </div></div>
            </div>
          );
        })}
        {branches.map((x, j) => {
          const b = bx[j], r = Math.min(30 * s, b.h * 0.24);
          const names = x.lines?.length ? x.lines.map((l) => l.text) : [labelNow(x.label, t)];
          return (
            <div key={j} className={`dg-b-${j}`} style={{ position: "absolute", left: b.x, top: b.y, width: b.w, height: b.h, opacity: 0 }}>
              <div className={`dg-hit-b-${j}`} style={{ position: "absolute", inset: 0 }}>
                {ring(`dg-ring-b-${j}`, r)}
                <div style={{ position: "absolute", inset: 0, borderRadius: r, background: "#fff", boxShadow: shadow, display: "flex", alignItems: "center",
                  gap: 22 * s, padding: `0 ${28 * s}px` }}>
                  {logo(x.src, logoB, names[0]?.slice(0, 1) ?? "")}
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 * s }}>
                    {names.map((nm, i) => <span key={i} className={`dg-name-b-${j}-${i}`} style={{ fontFamily: F, fontWeight: 800, fontSize: bFs[j],
                      lineHeight: 1.05, letterSpacing: "-0.02em", color: "#141414", whiteSpace: "nowrap", display: "inline-block", transformOrigin: "0 50%" }}>{nm}</span>)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        {k ? tasks.map((x, c) => {
          const cy = stack ? nodes[0].y - chipH * 0.6 : nodes[0].y + nodes[0].h / 2;
          const left = stack ? Math.max(P, nodes[0].x + nodes[0].w / 2 - chipW(x) / 2) : ox;
          return (
            <div key={c} className={`dg-chip-${c}`} style={{ position: "absolute", left, top: cy - chipH / 2, height: chipH, padding: `0 ${chipFs * 0.65}px`,
              display: "flex", alignItems: "center", gap: chipFs * 0.3, borderRadius: chipH / 2, whiteSpace: "nowrap", opacity: 0,
              background: x.heavy ? "#141414" : "#fff", color: x.heavy ? "#fff" : "#141414", border: x.heavy ? `${3 * s}px solid rgba(255,255,255,0.85)` : "none",
              fontFamily: F, fontWeight: 800, fontSize: chipFs, letterSpacing: "-0.02em", boxShadow: shadow, boxSizing: "border-box" }}>
              {(x.heavy ? [0.5, 0.75, 1] : [0.5]).map((v, i) => <span key={i} style={{ width: chipFs * 0.3, height: chipFs * v, borderRadius: 4 * s,
                background: "currentColor", display: "inline-block" }} />)}
              {x.text}
            </div>
          );
        }) : null}
        {p.tag?.text ? <div className="dg-tag" style={{ position: "absolute", right: 0, top: 0, padding: `${0.6 * chipFs}px ${chipFs}px`, background: accent,
          color: luminance(accent) > 0.6 ? "#141414" : "#fff", fontFamily: F, fontWeight: 800, fontSize: chipFs, borderRadius: chipFs, transformOrigin: "100% 0",
          boxShadow: shadow }}>{p.tag.text}</div> : null}
      </div>
    </div>
  );
};
