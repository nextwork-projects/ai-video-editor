// Proves each GSAP plugin is deterministic under Remotion: the same frame rendered in two separate
// processes, and a still against the same frame inside a sequential (video) frame render, must be
// pixel-identical.   node test/determinism.mjs <outDir>
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderFrames, renderStill, selectComposition } from "@remotion/renderer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PLUGINS = ["drawsvg", "morphsvg", "motionpath", "customease", "customwiggle", "physics2d", "physics2d-friction", "splittext"];
const FRAME = 23;
const [mode, ...args] = process.argv.slice(2);

if (mode === "child") {
  const [serveUrl, plugin, out] = args;
  const inputProps = { plugin };
  const composition = await selectComposition({ serveUrl, id: "Proof", inputProps });
  await renderStill({ serveUrl, composition, inputProps, output: out, frame: FRAME });
  process.exit(0);
}

const outDir = path.resolve(mode ?? "out/determinism");
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(HERE, "..", "src", "index.ts") });
const same = (a, b) => {
  // decode both to raw RGBA and compare: PNG bytes can differ only by encoder metadata
  const raw = (f) => spawnSync("ffmpeg", ["-v", "error", "-i", f, "-f", "rawvideo", "-pix_fmt", "rgba", "-"], { maxBuffer: 1 << 28 }).stdout;
  return Buffer.compare(raw(a), raw(b)) === 0;
};
const results = {};
for (const plugin of PLUGINS) {
  const a = path.join(outDir, `${plugin}-a.png`), b = path.join(outDir, `${plugin}-b.png`);
  for (const f of [a, b]) {
    const r = spawnSync(process.execPath, [fileURLToPath(import.meta.url), "child", serveUrl, plugin, f], { stdio: "inherit" });
    if (r.status !== 0) throw new Error(`${plugin}: child render failed`);
  }
  const inputProps = { plugin };
  const composition = await selectComposition({ serveUrl, id: "Proof", inputProps });
  const seqDir = path.join(outDir, `${plugin}-seq`);
  fs.rmSync(seqDir, { recursive: true, force: true });
  await renderFrames({ serveUrl, composition, inputProps, outputDir: seqDir, imageFormat: "png", frameRange: [0, FRAME + 5],
    onStart: () => {}, onFrameUpdate: () => {}, concurrency: 1 });
  const seq = fs.readdirSync(seqDir).filter((f) => f.endsWith(".png")).sort()[FRAME];
  results[plugin] = { two_processes: same(a, b), still_vs_video_frame: same(a, path.join(seqDir, seq)) };
  console.log(plugin, JSON.stringify(results[plugin]));
}
fs.writeFileSync(path.join(outDir, "results.json"), JSON.stringify(results, null, 2));
fs.rmSync(serveUrl, { recursive: true, force: true });
