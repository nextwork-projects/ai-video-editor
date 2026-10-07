// Where a scene's ground still is while it cuts in or out: the shapes Scene.tsx draws, as one pure
// function with no imports, so tests/test_record.mjs checks it without a render.
export type Kind = "match" | "iris" | "push" | "block" | "wipe" | "fade";

/** Does the scene's ground cover the point (x, y) px? p: how much of the scene shows (0-1, eased, as
 *  Scene.tsx's p); ph: seconds into the transition; T: its length; focus: % of the frame match and iris
 *  open from and close to. */
export const groundCovers = (kind: Kind, leaving: boolean, p: number, ph: number, T: number, W: number, H: number,
  focus: [number, number], x: number, y: number): boolean => {
  const FX = (focus[0] / 100) * W, FY = (focus[1] / 100) * H;
  // CSS circle(r%): r is a share of the frame's diagonal over the square root of 2
  if (kind === "iris") return Math.hypot(x - FX, y - FY) <= (p * 1.5 * Math.hypot(W, H)) / Math.SQRT2;
  if (kind === "match") {
    const s0 = Math.min(W, H) * 0.07;
    return x >= (FX - s0 / 2) * (1 - p) && x <= W - (W - FX - s0 / 2) * (1 - p)
      && y >= (FY - s0 / 2) * (1 - p) && y <= H - (H - FY - s0 / 2) * (1 - p);
  }
  if (kind === "push") { const off = leaving ? -(1 - p) * W : (1 - p) * W; return x >= off && x <= off + W; }
  if (kind === "wipe") return leaving ? x <= p * W : x >= (1 - p) * W;
  if (kind === "block") return leaving ? ph < T * 0.5 : ph >= T * 0.5;
  return p >= 0.5; // fade: the ground is the stronger half
};
