import React from "react";
import { prog } from "./motion";
import { useFamily } from "./Captions";

// The card edit's words on screen besides the captions (plan.json "texts", plan.py text_items). Seconds on the cut,
// boxes in % of the frame, all inside the reels safe zone (plan.py keeps them there).
//   title: the hook's title: one plain white box, black bold type, tight to the words (emoji kept), no border or shadow,
//          centred on the lower chest; it pops in, breathes while up and leaves on a quick fade
//   cta:   the ask near the end: a black pill, a small label over the big quoted word, white type, above the head
//   list:  a running numbered list; each line lands on its word and stays until the list ends
//   stamp: a red circled X drawn over the card that is up, when the speaker says it does not apply
//   onscreen: a b-roll reel's text, copied from the reference reel (broll-reel reel.py): its words, place, size and
//          colour; on its own solid box when the reel had one, else with a dark stroke. It cuts in and out like the reel's.
export type TextItem =
  | { kind: "onscreen"; text: string; start: number; end: number; box: [number, number, number, number]; size_pct: number;
      color: string; box_color?: string | null }
  | { kind: "title"; text: string; start: number; end: number; y_pct: number; size_pct: number }
  | { kind: "cta"; text: string; label?: string; start: number; end: number; y_pct: number; size_pct: number }
  | { kind: "list"; items: { text: string; at: number }[]; start: number; end: number; x_pct: number; y_pct: number; size_pct: number }
  | { kind: "stamp"; start: number; end: number; box: [number, number, number, number] };

const POP_S = 0.18;

export const Texts: React.FC<{ items: TextItem[]; t: number; width: number; height: number; font?: string }> = ({ items, t, width, height, font }) => {
  const family = useFamily(font ?? "TikTok Sans", 700) ?? "sans-serif";
  return (
    <>
      {items.filter((x) => t >= x.start && t < x.end).map((x, i) => {
        if (x.kind === "onscreen") {
          const fs = (x.size_pct / 100) * height, [bx, by, bw, bh] = x.box;
          return (
            <div key={i} style={{ position: "absolute", left: `${bx + bw / 2 - 45}%`, width: "90%", top: `${by + bh / 2}%`, transform: "translateY(-50%)",
              display: "flex", justifyContent: "center" }}>
              <div style={{ fontFamily: `${family}, "Apple Color Emoji", "Noto Color Emoji"`, fontWeight: 700, fontSize: fs, lineHeight: 1.2,
                color: x.color, textAlign: "center", whiteSpace: "pre-line",
                ...(x.box_color ? { background: x.box_color, padding: `${fs * 0.2}px ${fs * 0.35}px`, borderRadius: fs * 0.25 }
                  : { WebkitTextStroke: `${fs * 0.08}px #000`, paintOrder: "stroke fill" }) } as React.CSSProperties}>{x.text}</div>
            </div>
          );
        }
        if (x.kind === "title" || x.kind === "cta") {
          const fs = (x.size_pct / 100) * height;
          const p = prog(t, x.start, POP_S * 1.6, "power3.out"), out = 1 - prog(t, x.end - 0.18, 0.18, "power1.in");
          const breathe = 1 + 0.015 * Math.sin((t - x.start) * 2.4);
          const cta = x.kind === "cta";
          return (
            <div key={i} style={{ position: "absolute", left: "13%", width: "74%", top: `${x.y_pct}%`, display: "flex", justifyContent: "center",
              opacity: Math.min(prog(t, x.start, POP_S, "power1.out"), out), transform: `scale(${(0.86 + 0.14 * p) * breathe})`, transformOrigin: "50% 50%" }}>
              {cta ? (
                <div style={{ background: "#0B0B0C", color: "#FFFFFF", fontFamily: family, fontWeight: 800, borderRadius: fs * 0.26, textAlign: "center",
                  padding: `${fs * 0.12}px ${fs * 0.34}px ${fs * 0.08}px`, lineHeight: 1.05 }}>
                  {x.label ? <div style={{ fontSize: fs * 0.32, fontWeight: 700 }}>{x.label}</div> : null}
                  <div style={{ fontSize: fs }}>{x.text}</div>
                </div>
              ) : (
                <div style={{ background: "#FFFFFF", color: "#000000", fontFamily: `${family}, "Apple Color Emoji", "Noto Color Emoji"`, fontWeight: 800,
                  fontSize: fs, lineHeight: 1.15, padding: `${fs * 0.25}px ${fs * 0.3}px`, borderRadius: fs * 0.16, textAlign: "center", whiteSpace: "pre-line" }}>{x.text}</div>
              )}
            </div>
          );
        }
        if (x.kind === "list") {
          const fs = (x.size_pct / 100) * height;
          return (
            <div key={i} style={{ position: "absolute", left: `${x.x_pct}%`, top: `${x.y_pct}%`, maxWidth: "60%" }}>
              {x.items.filter((it) => t >= it.at).map((it, j) => {
                const p = prog(t, it.at, POP_S, "power2.out");
                return (
                  <div key={j} style={{ fontFamily: family, fontWeight: 700, fontSize: fs, lineHeight: 1.3, color: "#FFFFFF", whiteSpace: "nowrap",
                    WebkitTextStroke: `${fs * 0.06}px #000`, paintOrder: "stroke fill", textShadow: "0 2px 10px rgba(0,0,0,.35)",
                    opacity: p, transform: `translateY(${(1 - p) * fs * 0.4}px)` } as React.CSSProperties}>{`${j + 1}. ${it.text}`}</div>
                );
              })}
            </div>
          );
        }
        const [bx, by, bw, bh] = x.box;
        const d = Math.min((bw / 100) * width, (bh / 100) * height) * 0.62;
        const p = prog(t, x.start, POP_S * 1.6, "power2.out");
        const len = d * Math.SQRT2 * 0.5;
        return (
          <svg key={i} width={d} height={d} viewBox={`0 0 ${d} ${d}`} style={{ position: "absolute", left: (bx + bw / 2) / 100 * width - d / 2,
            top: (by + bh / 2) / 100 * height - d / 2 }}>
            <circle cx={d / 2} cy={d / 2} r={d * 0.44} fill="none" stroke="#E5322D" strokeWidth={d * 0.06}
              strokeDasharray={Math.PI * d * 0.88} strokeDashoffset={(1 - p) * Math.PI * d * 0.88} />
            {[[0.3, 0.3, 0.7, 0.7], [0.7, 0.3, 0.3, 0.7]].map(([a, b, c, e], k) => (
              <line key={k} x1={a * d} y1={b * d} x2={c * d} y2={e * d} stroke="#E5322D" strokeWidth={d * 0.06} strokeLinecap="round"
                strokeDasharray={len} strokeDashoffset={(1 - Math.min(1, Math.max(0, p * 2 - k))) * len} />
            ))}
          </svg>
        );
      })}
    </>
  );
};
