// A capture (screenshot) card with marks drawn on it, timed with GSAP. Every mark is registered in the
// capture's own pixel space inside the layer that scrolls and pushes, so marks ride the page.
// Motion is asymmetric on purpose: lines (ring, bracket, underline, leader) DRAW along their length;
// boxes, pills and the dim FADE AND SCALE; a highlight sweeps like a marker.
import React from "react";
import { Img, staticFile } from "remotion";
import { Motion, useTl } from "./motion";
import { Look, shadowOf } from "./look";

export type Mark = {
  kind: "box" | "ring" | "dim" | "bracket" | "pill" | "underline" | "highlight";
  rect: [number, number, number, number]; // capture px
  rects?: [number, number, number, number][]; // a highlight's line boxes (capture.mjs), capture px: one band per line
  at?: number; // seconds after the card lands (plan.py fills it from at_word; at_s is the same, given directly)
  at_s?: number;
  label?: string; // pill text; a bracket with a label runs a leader to a pill
  side?: "left" | "right"; // bracket side, default right
};

const DIM = "rgba(8,8,8,0.72)";

/** A highlight's bands, one per line: each line box (else the mark's rect) trimmed to the line pitch, so
 *  bands on consecutive lines never overlap (a font's content box is taller than a tight line-height). */
export const lineBands = (k: Mark): Mark["rect"][] => {
  const rs = k.rects?.length ? k.rects : [k.rect];
  const ys = rs.map((r) => r[1] + r[3] / 2);
  const pitch = Math.min(...ys.slice(1).map((y, j) => y - ys[j]).filter((d) => d > 0), Infinity);
  return rs.map((r) => {
    const bh = Math.min(r[3], pitch) * (rs.length > 1 ? 0.9 : 0.86);
    return [r[0], r[1] + r[3] / 2 - bh / 2, r[2], bh] as Mark["rect"];
  });
};

export const Capture: React.FC<{ src: string; size?: [number, number]; marks?: Mark[]; highlight?: { rects: [number, number, number, number][] };
  bw: number; bh: number; dur: number; look: Look; m: Motion; font: string; light: boolean;
  /** Push into the first mark once it lands (shared zoom-into-region primitive): the scale reached, 1 = off. */
  zoom?: number; chrome?: boolean }> =
  ({ src, size, marks = [], highlight, bw, bh, dur, look, m, font, light, zoom = 1, chrome = true }) => {
    const [iw, ih] = size ?? [0, 0];
    const u = Math.min(bw, bh) / 100;
    const radius = (look.radius / 100) * Math.min(bw, bh) * 0.6;
    // A highlight from capture.mjs (fractions of the image) becomes highlight marks, one per line.
    const all: Mark[] = [...marks.map((k) => ({ ...k, at: k.at ?? k.at_s ?? 0.8 })),
      ...(highlight?.rects ?? []).map((r, i) => ({ kind: "highlight" as const, rect: [r[0] * iw, r[1] * ih, r[2] * iw, r[3] * ih] as Mark["rect"], at: 1.6 + i * 0.28 }))]
      .sort((a, b) => (a.at ?? 0) - (b.at ?? 0));
    const tall = iw && ih ? ih / iw > (bh / bw) * 1.6 : false;
    const f = iw && ih ? (all.length || tall ? bw / iw : Math.min(bw / iw, bh / ih)) : 1;
    const dw = iw * f, dh = ih * f, wh = Math.min(bh, dh);
    const offFor = (r: Mark["rect"]) => Math.min(Math.max(0, (r[1] + r[3] / 2) * f - wh * 0.45), Math.max(0, dh - wh));
    const ref = useTl((tl, q) => {
      const reg = q(".cap-reg")[0];
      // the camera: a slow push toward the marks, never a still
      const focus = all.length ? all[0].rect : [iw / 2, ih / 2, 0, 0];
      tl.fromTo(reg, { scale: 1 }, { scale: 1 + m.push * 1.3, duration: Math.max(1, dur), ease: "sine.inOut",
        transformOrigin: `${((focus[0] + focus[2] / 2) / (iw || 1)) * 100}% ${((focus[1] + focus[3] / 2) / (ih || 1)) * 100}%` }, 0);
      // travel: to each mark before it lands, or down a tall page
      let y = 0;
      if (all.length) {
        all.forEach((k) => {
          const to = -offFor(k.rect);
          if (Math.abs(to - y) > 2) {
            const d = Math.min(1.1, Math.max(0.5, Math.abs(to - y) / (wh * 1.2))) * m.k;
            tl.fromTo(reg, { y }, { y: to, duration: d, ease: m.move, immediateRender: false }, Math.max(0.2, (k.at ?? 0) - d - 0.1));
            y = to;
          }
        });
      } else if (tall) {
        tl.fromTo(reg, { y: 0 }, { y: -(dh - wh), duration: Math.max(1, dur - 0.3), ease: "sine.inOut" }, 0.3);
      }
      all.forEach((k, i) => {
        const at = k.at ?? 0;
        const el = q(`.mk-${i}`);
        if (!el.length && k.kind !== "highlight") return;
        if (k.kind === "box" || k.kind === "pill") {
          tl.fromTo(el, { autoAlpha: 0, scale: 1.14 }, { autoAlpha: 1, scale: 1, duration: 0.5 * m.k, ease: m.enter, transformOrigin: "50% 50%" }, at);
        } else if (k.kind === "dim") {
          tl.fromTo(el, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.55 * m.k, ease: "sine.inOut" }, at);
        } else if (k.kind === "highlight") {
          // a marker pass: line by line, each at the speed of the hand across it
          const ls = lineBands(k), total = ls.reduce((a, r) => a + r[2], 0) || 1;
          let t0 = at;
          ls.forEach((r, j) => {
            const d = Math.max(0.16, (0.55 * m.k * r[2]) / total);
            tl.fromTo(q(`.mk-${i}-l${j}`), { scaleX: 0 }, { scaleX: 1, duration: d, ease: j === ls.length - 1 ? "power2.out" : "none",
              transformOrigin: "0% 50%" }, t0);
            t0 += d;
          });
        } else {
          tl.set(el, { opacity: 1 }, at);
          tl.fromTo(el, { drawSVG: "0%" }, { drawSVG: "100%", duration: (k.kind === "ring" ? 0.8 : 0.55) * m.k, ease: m.draw }, at);
          const lead = q(`.mk-${i}-lead`);
          if (lead.length) {
            tl.set(lead, { opacity: 1 }, at + 0.5 * m.k);
            tl.fromTo(lead, { drawSVG: "0%" }, { drawSVG: "100%", duration: 0.28, ease: "sine.inOut" }, at + 0.5 * m.k);
          }
          const pill = q(`.mk-${i}-pill`)[0];
          if (pill) tl.fromTo(pill, { autoAlpha: 0, scale: 0.85 }, { autoAlpha: 1, scale: 1, duration: 0.4, ease: m.pop }, at + 0.7 * m.k);
        }
      });
      // zoom into the first mark's region once it has landed, and hold there
      if (zoom > 1 && all.length) {
        const k = all[0];
        // never so far that the marked region itself leaves the card
        const z = Math.max(1, Math.min(zoom, dw / (k.rect[2] * f * 1.12), wh / (k.rect[3] * f * 2.2)));
        tl.fromTo(q(".cap-zoom")[0], { scale: 1 }, { scale: z, duration: 0.9 * m.k, ease: "power3.inOut" }, (k.at ?? 0) + 0.45 * m.k);
      }
    }, [src, JSON.stringify(all), bw, bh, dur, m.name, zoom]);

    if (!iw || !ih) {
      return <div ref={ref} style={{ width: bw, height: bh, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div className="cap-reg"><Img src={staticFile(src)} style={{ maxWidth: bw, maxHeight: bh, objectFit: "contain", borderRadius: radius, boxShadow: shadowOf(look, u) }} /></div>
      </div>;
    }
    const sw = Math.max(2.5, 3 / f); // stroke, capture px, so it is ~3 display px
    const pillS = Math.max(26, u * 5);
    const pill = (k: Mark, i: number, x: number, y: number, cls: string, fromRight = false) => (
      <div key={`p${i}`} className={cls} style={{ position: "absolute", ...(fromRight ? { right: dw - x } : { left: x }), top: y, transform: "translateY(-50%)", padding: `${pillS * 0.22}px ${pillS * 0.55}px`,
        borderRadius: pillS, background: look.ink, color: look.ground, fontFamily: font, fontWeight: 700, fontSize: pillS, whiteSpace: "nowrap",
        boxShadow: "0 6px 22px rgba(0,0,0,0.35)", opacity: 0 }}>{k.label}</div>
    );
    return (
      <div ref={ref} style={{ width: dw, height: wh, overflow: "hidden", borderRadius: radius, boxShadow: chrome ? shadowOf(look, u) : undefined,
        background: "#fff", position: "relative" }}>
        <div className="cap-zoom" style={{ position: "absolute", inset: 0, transformOrigin: all.length
          ? `${(all[0].rect[0] + all[0].rect[2] / 2) * f}px ${(all[0].rect[1] + all[0].rect[3] / 2) * f - offFor(all[0].rect)}px` : "50% 50%" }}>
        <div className="cap-reg" style={{ position: "absolute", left: 0, top: 0, width: dw, height: dh }}>
          <Img src={staticFile(src)} style={{ width: dw, height: dh, display: "block" }} />
          {all.map((k, i) => {
            const [x, y, w, h] = k.rect;
            if (k.kind === "highlight") {
              // clean marker yellow multiplied over the text: white stays yellow, the ink stays ink
              return <React.Fragment key={i}>{lineBands(k).map(([bx, by, bw2, bh2], j) => {
                const pad = bh2 * f * 0.1;
                return <div key={j} className={`mk-${i}-l${j}`} style={{ position: "absolute", left: bx * f - pad, top: by * f, width: bw2 * f + pad * 2,
                  height: bh2 * f, background: look.mark, mixBlendMode: "multiply", borderRadius: pad * 0.8, transform: "scaleX(0)" }} />;
              })}</React.Fragment>;
            }
            if (k.kind === "dim") {
              // four plates round the bright region, not a second copy of the capture
              const R = [x * f, y * f, w * f, h * f];
              const plates: [number, number, number, number][] = [[0, 0, dw, R[1]], [0, R[1] + R[3], dw, dh - R[1] - R[3]], [0, R[1], R[0], R[3]],
                [R[0] + R[2], R[1], dw - R[0] - R[2], R[3]]];
              return <React.Fragment key={i}>{plates.map((pl, j) => <div key={j} className={`mk-${i}`} style={{ position: "absolute", left: pl[0], top: pl[1],
                width: pl[2], height: pl[3], background: DIM, opacity: 0 }} />)}</React.Fragment>;
            }
            if (k.kind === "pill") return pill(k, i, x * f, (y + h / 2) * f, `mk-${i}`);
            return null;
          })}
          <svg width={dw} height={dh} viewBox={`0 0 ${iw} ${ih}`} style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}>
            {all.map((k, i) => {
              const [x, y, w, h] = k.rect;
              const W = sw * (k.kind === "ring" ? 1.5 : k.kind === "underline" ? 1.5 : 1.2);
              const st = { fill: "none", strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
              // every line twice: a soft dark outline, then the light stroke over it
              const two = (cls: string, shape: (p: Record<string, unknown>) => React.ReactNode) => <React.Fragment key={cls}>
                {shape({ ...st, className: cls, stroke: "rgba(0,0,0,0.55)", strokeWidth: W * 2.2, opacity: 0 })}
                {shape({ ...st, className: cls, stroke: look.ring, strokeWidth: W, opacity: 0 })}
              </React.Fragment>;
              if (k.kind === "box") return two(`mk-${i}`, (p) => <rect {...p} x={x - sw * 2} y={y - sw * 2} width={w + sw * 4} height={h + sw * 4} rx={sw * 3} />);
              if (k.kind === "ring") {
                const cx = x + w / 2, cy = y + h / 2, rx = w / 2 + sw * 5, ry = h / 2 + sw * 5;
                return two(`mk-${i}`, (p) => <path {...p}
                  d={`M${cx + rx * 0.2} ${cy - ry} A${rx} ${ry} 0 1 1 ${cx - rx * 0.05} ${cy - ry * 1.02} L${cx + rx * 0.35} ${cy - ry * 0.95}`} />);
              }
              if (k.kind === "underline") return two(`mk-${i}`, (p) => <path {...p}
                d={`M${x} ${y + h + sw * 2} Q${x + w / 2} ${y + h + sw * 3.5} ${x + w} ${y + h + sw * 1.5}`} />);
              if (k.kind === "bracket") {
                const right = k.side !== "left", bx = right ? x + w + sw * 5 : x - sw * 5, tick = (right ? 1 : -1) * sw * 4;
                const midY = y + h / 2, lx = bx + (right ? 1 : -1) * sw * 14;
                return <React.Fragment key={i}>
                  {two(`mk-${i}`, (p) => <path {...p} d={`M${bx - tick} ${y} L${bx} ${y} L${bx} ${y + h} L${bx - tick} ${y + h}`} />)}
                  {k.label ? two(`mk-${i}-lead`, (p) => <path {...p} d={`M${bx} ${midY} L${lx} ${midY}`} />) : null}
                </React.Fragment>;
              }
              return null;
            })}
          </svg>
          {all.map((k, i) => {
            if (k.kind !== "bracket" || !k.label) return null;
            const [x, y, w, h] = k.rect, right = k.side !== "left";
            // a pill that would run off the card is pulled back inside its edge
            const pw = (k.label?.length ?? 0) * pillS * 0.62 + pillS * 1.2, edge = pillS * 0.4;
            const px = right ? Math.min((x + w + sw * 19) * f, dw - pw - edge) : Math.max((x - sw * 19) * f, pw + edge);
            return pill(k, i, px, (y + h / 2) * f, `mk-${i}-pill`, !right);
          })}
        </div>
        </div>
      </div>
    );
  };
