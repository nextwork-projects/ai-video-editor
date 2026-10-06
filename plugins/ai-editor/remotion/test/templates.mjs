// Renders every case in a cases file as stills (4 points) and a short mp4, plus a 1 fps strip per clip.
//   node test/templates.mjs <publicDir> <cases.json> <outDir> [only-name-substring] [--no-video]
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const [publicDir, casesPath, outDir, only, flag] = process.argv.slice(2);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8")).filter((c) => !only || only === "-" || c.name.includes(only));
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.join(HERE, "..", "src", "index.ts"), publicDir: path.resolve(publicDir) });
for (const c of cases) {
  const inputProps = { width: 1080, height: 1920, dur: 4, ...c, card: { start: 0, end: c.dur ?? 4, entrance: "pop", ...c.card } };
  const composition = await selectComposition({ serveUrl, id: "Preview", inputProps });
  const n = composition.durationInFrames;
  for (const [i, f] of [0.12, 0.3, 0.55, 0.85].entries()) {
    await renderStill({ serveUrl, composition, inputProps, output: path.join(outDir, "stills", `${c.name}-${i}.png`), frame: Math.floor(n * f) });
  }
  if (flag !== "--no-video") {
    const mp4 = path.join(outDir, `${c.name}.mp4`);
    await renderMedia({ serveUrl, composition, inputProps, codec: "h264", outputLocation: mp4, crf: 18 });
    spawnSync("ffmpeg", ["-v", "error", "-y", "-i", mp4, "-vf", `fps=4,scale=${c.width > c.height ? 480 : 270}:-1,tile=8x${Math.ceil((n / 30) * 4 / 8)}`,
      "-frames:v", "1", path.join(outDir, "strips", `${c.name}.png`)]);
  }
  console.log("done", c.name);
}
fs.rmSync(serveUrl, { recursive: true, force: true });
