// The preview page: the real StyleEdit composition in a <Player>, with a timeline, caption words, card
// placement and sound levels. Every change goes to the server (skills/style-edit/scripts/preview.py),
// which writes overrides.json and sends back the plan with the overrides applied.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Player, PlayerRef } from "@remotion/player";
import { StyleEdit } from "../src/StyleEdit";
import { cues } from "./Sfx";

type Box = [number, number, number, number];
type Card = {
  _key: string; _regions: Box[]; _head: Box | null; start: number; end: number; trigger_word?: string; src?: string;
  format?: string; anim?: { type: string; props?: Record<string, unknown> }; box: Box; layout?: string; size?: [number, number];
  props?: Record<string, unknown>;
};
type Word = { text: string; start: number; end: number };
type Cue = { t: number; src: string; event?: number; gain_db?: number; override?: string };
type Plan = { width: number; height: number; fps: number; durationInFrames: number; cards: Card[]; sfx?: Cue[];
  captions: { chunks: { words: Word[] }[] } };
type State = { name: string; planName: string; plan: Plan; images: string[]; face: { step_s?: number; heads: { t: number; box: Box | null }[] } | null;
  overrides: { words?: Record<string, string> }; overrideCount: number; sessionChanges: number };
type Change = { kind: "card" | "word" | "sfx"; key: string; action: string; text: string; set?: object; to?: unknown; from?: unknown };

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const r1 = (v: number) => Math.round(v * 10) / 10;
const r3 = (v: number) => Math.round(v * 1000) / 1000;
const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, "0")}`;
const kind = (c: Card) => c.format ?? c.anim?.type ?? "image";
const label = (c: Card) => `${c.trigger_word ?? ""} ${kind(c)}`.trim();
const movable = (c: Card) => c.layout !== "scene" && c.anim?.type !== "logo_cluster" && c.box[2] < 100;
const cueName = (c: Cue) => c.src.split("/").pop()!.replace(/(\.g[+-][\d.]+)?\.wav$/, "");
const cueKey = (c: Cue) => c.override ?? (c.event ?? c.t).toFixed(3);

/** The free region nearest the dropped box's centre. The box keeps its size when it fits, else takes the region. */
const snap = (b: Box, regions: Box[]): Box | null => {
  const cx = b[0] + b[2] / 2, cy = b[1] + b[3] / 2;
  let best: Box | null = null, bd = Infinity;
  for (const r of regions) {
    const dx = Math.max(r[0] - cx, 0, cx - (r[0] + r[2])), dy = Math.max(r[1] - cy, 0, cy - (r[1] + r[3]));
    if (dx * dx + dy * dy < bd) { bd = dx * dx + dy * dy; best = r; }
  }
  if (!best) return null;
  if (b[2] <= best[2] && b[3] <= best[3])
    return [r1(clamp(b[0], best[0], best[0] + best[2] - b[2])), r1(clamp(b[1], best[1], best[1] + best[3] - b[3])), b[2], b[3]];
  return best.map(r1) as Box;
};

/** A callback ref and the element's width: the timeline mounts only once the plan has loaded. */
const useWidth = () => {
  const [w, setW] = useState(1);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: HTMLDivElement | null) => {
    ro.current?.disconnect();
    if (!el) return;
    ro.current = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.current.observe(el);
  }, []);
  return [ref, w] as const;
};

const App: React.FC = () => {
  const [st, setSt] = useState<State | null>(null);
  const [err, setErr] = useState("");
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const [selCue, setSelCue] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ key: string; start: number; end: number } | null>(null);
  const [boxDraft, setBoxDraft] = useState<{ key: string; box: Box } | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const player = useRef<PlayerRef>(null);
  const frameEl = useRef<HTMLDivElement>(null);
  const [tlRef, tlW] = useWidth();

  useEffect(() => { fetch("/api/state").then((r) => r.json()).then(setSt).catch((e) => setErr(String(e))); }, []);
  useEffect(() => {
    const p = player.current;
    if (!p) return;
    const f = (e: { detail: { frame: number } }) => setFrame(e.detail.frame);
    const on = () => setPlaying(true), off = () => setPlaying(false);
    p.addEventListener("frameupdate", f); p.addEventListener("play", on); p.addEventListener("pause", off);
    return () => { p.removeEventListener("frameupdate", f); p.removeEventListener("play", on); p.removeEventListener("pause", off); };
  }, [st !== null]);

  const send = useCallback(async (ch: Change) => {
    const r = await fetch("/api/change", { method: "POST", body: JSON.stringify(ch) });
    if (!r.ok) { setErr(`Save failed: ${r.status} ${await r.text()}`); return; }
    setSt(await r.json());
  }, []);

  const typing = () => document.activeElement?.tagName === "INPUT";
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (typing()) return;
      if (e.code === "Space") { e.preventDefault(); player.current?.toggle(); }
      if ((e.key === "Delete" || e.key === "Backspace") && sel) delCard();
    };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  });

  if (err) return <div className="err">{err}</div>;
  if (!st) return <div className="err muted">Loading the edit...</div>;
  const { plan } = st;
  const dur = plan.durationInFrames / plan.fps;
  const t = frame / plan.fps;
  const seek = (s: number) => player.current?.seekTo(Math.round(clamp(s, 0, dur) * plan.fps));
  const card = plan.cards.find((c) => c._key === sel) ?? null;
  // what the player shows: the server's plan, plus a block being dragged on the timeline
  const shown = draft ? { ...plan, cards: plan.cards.map((c) => (c._key === draft.key ? { ...c, start: draft.start, end: draft.end } : c)) } : plan;
  cues.current = plan.sfx ?? [];

  function delCard() {
    if (!card) return;
    send({ kind: "card", key: card._key, action: "delete", set: { deleted: true }, from: { start: card.start, end: card.end },
      text: `deleted the '${label(card)}' card at ${card.start.toFixed(2)} s` });
    setSel(null);
  }

  const pps = tlW / dur;
  const dragBlock = (e: React.PointerEvent, c: Card, mode: "move" | "l" | "r") => {
    e.stopPropagation(); e.preventDefault();
    setSel(c._key);
    const x0 = e.clientX, s0 = c.start, e0 = c.end;
    let cur = { key: c._key, start: s0, end: e0 };
    const move = (ev: PointerEvent) => {
      const d = (ev.clientX - x0) / pps;
      if (mode === "move") { const dd = clamp(d, -s0, dur - e0); cur = { ...cur, start: r3(s0 + dd), end: r3(e0 + dd) }; }
      else if (mode === "l") cur = { ...cur, start: r3(clamp(s0 + d, 0, e0 - 0.3)) };
      else cur = { ...cur, end: r3(clamp(e0 + d, s0 + 0.3, dur)) };
      setDraft(cur);
    };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      if (Math.abs(cur.start - s0) < 0.01 && Math.abs(cur.end - e0) < 0.01) { setDraft(null); seek(c.start + 0.3); return; }
      const action = mode === "move" ? "move" : "trim";
      send({ kind: "card", key: c._key, action, set: { start: cur.start, end: cur.end }, from: { start: s0, end: e0 },
        text: `${action === "move" ? "moved" : "trimmed"} the '${label(c)}' card ${s0.toFixed(2)}-${e0.toFixed(2)} s -> ${cur.start.toFixed(2)}-${cur.end.toFixed(2)} s` })
        .then(() => setDraft(null));
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const dragBox = (e: React.PointerEvent, c: Card) => {
    e.stopPropagation(); e.preventDefault();
    if (sel !== c._key) { setSel(c._key); return; }
    const rect = frameEl.current!.getBoundingClientRect();
    const x0 = e.clientX, y0 = e.clientY, b0 = c.box;
    let cur: Box = b0, moved = false;
    const move = (ev: PointerEvent) => {
      moved ||= Math.abs(ev.clientX - x0) + Math.abs(ev.clientY - y0) > 3;
      cur = [b0[0] + ((ev.clientX - x0) / rect.width) * 100, b0[1] + ((ev.clientY - y0) / rect.height) * 100, b0[2], b0[3]];
      setBoxDraft({ key: c._key, box: cur });
    };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      const to = snap(cur, c._regions);
      setBoxDraft(null);
      if (!moved || !to || to.every((v, i) => Math.abs(v - b0[i]) < 0.05)) return;
      send({ kind: "card", key: c._key, action: "position", set: { box: to }, from: b0,
        text: `placed the '${label(c)}' card at [${to.join(", ")}] (was [${b0.join(", ")}])` });
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const swap = (c: Card, src: string) => {
    const img = new Image();
    img.onload = () => {
      const { crop, ...props } = (c.props ?? {}) as Record<string, unknown>;
      send({ kind: "card", key: c._key, action: "swap", from: c.src, text: `swapped the '${label(c)}' card's image ${c.src} -> ${src}`,
        set: { src, size: [img.naturalWidth || 1000, img.naturalHeight || 1000], marks: null, highlight: null, xh: null, props } });
    };
    img.src = `/media/${src}`;
  };

  const head = st.face?.heads[Math.round(t / (st.face.step_s ?? 0.5))]?.box;
  const dragging = boxDraft ? plan.cards.find((c) => c._key === boxDraft.key) : null;
  const words = plan.captions.chunks.flatMap((ch) => ch.words);
  const fixed = st.overrides.words ?? {};
  const playerProps = shown as unknown as Record<string, unknown>;

  return (
    <div className="app">
      <header>
        <span className="name">{st.name}</span>
        <span className="meta">{st.planName}, {plan.width}x{plan.height}, {dur.toFixed(1)} s</span>
        <span className="grow" />
        <span className="meta">{st.overrideCount ? `${st.overrideCount} override${st.overrideCount > 1 ? "s" : ""} in overrides.json` : "No changes yet"}</span>
        <button className="primary" onClick={async () => {
          const r = await fetch("/api/done", { method: "POST", body: "{}" });
          const j = await r.json();
          setDone(`${j.changes} change${j.changes === 1 ? "" : "s"} saved. Claude picks up preview-done.json and asks where to render. You can close this tab.`);
        }}>Render</button>
      </header>

      <div className="stage">
        <div className="frame" ref={frameEl} style={{ aspectRatio: `${plan.width} / ${plan.height}` }}>
          <Player ref={player} component={StyleEdit as unknown as React.FC<Record<string, unknown>>} inputProps={playerProps}
            durationInFrames={plan.durationInFrames} compositionWidth={plan.width} compositionHeight={plan.height} fps={plan.fps}
            style={{ width: "100%", height: "100%" }} clickToPlay={false} />
          <div className="overlay">
            {dragging ? dragging._regions.map((r, i) => (
              <div key={i} className="region" style={{ left: `${r[0]}%`, top: `${r[1]}%`, width: `${r[2]}%`, height: `${r[3]}%` }}><span>drop here</span></div>
            )) : null}
            {(dragging?._head ?? (card && head)) ? (() => { const h = (dragging?._head ?? head)!; return (
              <div className="head" style={{ left: `${h[0]}%`, top: `${h[1]}%`, width: `${h[2]}%`, height: `${h[3]}%` }}><span>face</span></div>); })() : null}
            {shown.cards.filter((c) => movable(c) && ((t >= c.start && t < c.end) || c._key === sel)).map((c) => {
              const b = boxDraft?.key === c._key ? boxDraft.box : c.box;
              return <div key={c._key} className={`box${c._key === sel ? " sel" : ""}`} title={label(c)}
                style={{ left: `${b[0]}%`, top: `${b[1]}%`, width: `${b[2]}%`, height: `${b[3]}%` }}
                onPointerDown={(e) => dragBox(e, c)} />;
            })}
          </div>
        </div>
        <div className="transport">
          <button onClick={() => player.current?.toggle()}>{playing ? "Pause" : "Play"}</button>
          <span>{fmt(t)} / {fmt(dur)}</span>
          <span>Space plays. Drag a card on the frame to place it.</span>
        </div>
      </div>

      <aside>
        <section>
          <h3>Card</h3>
          {card ? (
            <>
              <div><b>{label(card)}</b></div>
              <div className="muted">{card.start.toFixed(2)} s to {card.end.toFixed(2)} s{movable(card) ? `, box [${card.box.map(r1).join(", ")}]` : ", full frame"}</div>
              {card.src ? (
                <>
                  <div className="muted" style={{ marginTop: 10 }}>Swap the picture</div>
                  <div className="thumbs">
                    {st.images.map((src) => (
                      <button key={src} className={src === card.src ? "on" : ""} title={src} onClick={() => src !== card.src && swap(card, src)}>
                        <img src={`/media/${src}`} loading="lazy" alt={src} />
                      </button>
                    ))}
                  </div>
                </>
              ) : null}
              <div className="row" style={{ marginTop: 10 }}><button className="danger" onClick={delCard}>Delete card</button></div>
            </>
          ) : <div className="muted">Pick a card on the timeline or on the frame. Drag it to move, drag its edges to trim.</div>}
        </section>
        <section>
          <h3>Sound cues</h3>
          {(plan.sfx ?? []).length ? (plan.sfx ?? []).map((c) => {
            const k = cueKey(c), db = c.gain_db ?? 0;
            const nudge = (d: number) => send({ kind: "sfx", key: k, action: "level", from: db, to: clamp(db + d, -20, 10),
              text: `${cueName(c)} at ${(c.event ?? c.t).toFixed(2)} s: ${db} dB -> ${clamp(db + d, -20, 10)} dB` });
            return (
              <div key={k} className="cue" style={{ color: selCue === k ? "var(--accent)" : undefined }}>
                <span className="muted" onClick={() => seek(c.t)} style={{ cursor: "pointer" }}>{(c.event ?? c.t).toFixed(2)} s</span>
                <span>{cueName(c)}</span>
                <span className="row">
                  <button onClick={() => nudge(-1)} aria-label="quieter">-</button>
                  <span className="db">{db > 0 ? "+" : ""}{db} dB</span>
                  <button onClick={() => nudge(1)} aria-label="louder">+</button>
                </span>
              </div>);
          }) : <div className="muted">No sound cues in this plan.</div>}
        </section>
        <section>
          <h3>Caption words</h3>
          <div className="muted" style={{ marginBottom: 6 }}>Click a word to fix it. Empty it to remove it.</div>
          <div className="words">
            {words.map((w) => {
              const k = w.start.toFixed(3);
              return <input key={`${k}${w.text}`} defaultValue={w.text} size={Math.max(1, w.text.length)}
                className={`${t >= w.start && t < w.end ? "now" : ""}${k in fixed ? " fixed" : ""}`}
                onFocus={(e) => { e.currentTarget.select(); seek(w.start); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                  if (e.key === "Escape") { e.currentTarget.value = w.text; e.currentTarget.blur(); }
                }}
                onBlur={(e) => {
                  const v = e.currentTarget.value.trim();
                  if (v !== w.text) send({ kind: "word", key: k, action: "fix", from: w.text, to: v,
                    text: v ? `caption '${w.text}' -> '${v}' at ${w.start.toFixed(2)} s` : `removed caption word '${w.text}' at ${w.start.toFixed(2)} s` });
                }} />;
            })}
          </div>
        </section>
      </aside>

      <footer>
        <span className="lane-label" style={{ top: 40 }}>Cards</span>
        <span className="lane-label" style={{ top: 80 }}>Sound</span>
        <span className="lane-label" style={{ top: 106 }}>Words</span>
        <div className="tl" ref={tlRef}>
          <div className="ruler" onPointerDown={(e) => {
            const x0 = (e.currentTarget as HTMLElement).getBoundingClientRect().left;
            const go = (ev: PointerEvent | React.PointerEvent) => seek((ev.clientX - x0) / pps);
            go(e);
            const up = () => { window.removeEventListener("pointermove", go); window.removeEventListener("pointerup", up); };
            window.addEventListener("pointermove", go); window.addEventListener("pointerup", up);
          }}>
            {Array.from({ length: Math.floor(dur / 5) + 1 }, (_, i) => i * 5).map((s) => (
              <span key={s} className="tick" style={{ left: s * pps }}>{fmt(s).replace(/\.00$/, "")}</span>))}
          </div>
          {shown.cards.map((c) => (
            <div key={c._key} className={`block${c._key === sel ? " sel" : ""}`} title={label(c)}
              style={{ left: c.start * pps, width: Math.max(8, (c.end - c.start) * pps), top: 30 }}
              onPointerDown={(e) => dragBlock(e, c, "move")}>
              <span className="h l" onPointerDown={(e) => dragBlock(e, c, "l")} />
              {label(c)}
              <span className="h r" onPointerDown={(e) => dragBlock(e, c, "r")} />
            </div>))}
          {(plan.sfx ?? []).map((c) => (
            <div key={cueKey(c)} className={`cuemark${selCue === cueKey(c) ? " sel" : ""}`} title={`${cueName(c)} ${c.gain_db ?? 0} dB`}
              style={{ left: (c.event ?? c.t) * pps, top: 78 }} onClick={() => { setSelCue(cueKey(c)); seek(c.t); }} />))}
          {words.map((w) => (
            <div key={w.start} className="wordmark" style={{ left: w.start * pps, width: Math.max(2, (w.end - w.start) * pps), top: 104 }}
              title={w.text} onClick={() => seek(w.start)}>{w.text}</div>))}
          <div className="playhead" style={{ left: t * pps }} />
        </div>
      </footer>
      {done ? <div className="modal"><div>{done}</div></div> : null}
    </div>
  );
};

createRoot(document.getElementById("root")!).render(<App />);
