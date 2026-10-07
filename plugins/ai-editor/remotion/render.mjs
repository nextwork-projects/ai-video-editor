// Renders a plan.json with the StyleEdit composition (or the one its "composition" key names). Called by skills/style-edit/scripts/edit.py.
//
//   node render.mjs stills <publicDir> <plan.json> <outDir> name=frame ...
//   node render.mjs bench  <publicDir> <plan.json>            -> JSON: laptop seconds per frame
//   node render.mjs local  <publicDir> <plan.json> <out.mp4> [--draft] [--concurrency=N]
//   node render.mjs chunk  <publicDir> <plan.json> <out.mkv> <from> <to> [--concurrency=N]   frames from..to inclusive
//   node render.mjs bundle <publicDir> <outDir>               a bundle folder another machine renders from (Modal)
//
// <publicDir> can also be a bundle folder made by `bundle` (it holds bundle.js): nothing is bundled again.
// --draft renders at 2/3 size (1080x1920 -> 720x1280), on a Mac with its hardware H.264 encoder.
//   node render.mjs lambda-estimate <plan.json>               -> JSON: Lambda cost + time guess
//   node render.mjs lambda <publicDir> <plan.json> <out.mp4> <siteName>
//
// Lambda uses the user's own AWS credentials: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY,
// or AWS_PROFILE (REMOTION_AWS_* variants work too). Region: REMOTION_AWS_REGION, AWS_REGION, else us-east-1.
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { renderMedia, renderStill, selectComposition } from "@remotion/renderer";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ENTRY = path.join(HERE, "src", "index.ts");
const ID = "StyleEdit";
const [cmd, ...args] = process.argv.slice(2);
const readPlan = (p) => JSON.parse(fs.readFileSync(p, "utf8"));

// Lambda sizing. New AWS accounts can run about 10 Lambdas at once, so split into at most 9.
const REGION = process.env.REMOTION_AWS_REGION || process.env.AWS_REGION || "us-east-1";
const MEMORY_MB = 2048;
const DISK_MB = 2048;
const MAX_LAMBDAS = 9;
// A guess until a real render is measured: Lambda seconds spent per 1080p frame.
const LAMBDA_S_PER_FRAME = 0.3;
const framesPerLambda = (frames) => Math.max(150, Math.ceil(frames / MAX_LAMBDAS));

// Flags after the positional args: --draft, --concurrency=N.
const flags = Object.fromEntries(args.filter((a) => a.startsWith("--"))
  .map((a) => { const [k, v] = a.slice(2).split("="); return [k, v ?? true]; }));
const pos = args.filter((a) => !a.startsWith("--"));
// Measured on an M4 Pro (14 cores) rendering the sample take: see skills/style-edit/references/render.md.
const CORES = typeof os.availableParallelism === "function" ? os.availableParallelism() : os.cpus().length;
// A busy machine (load over 70% of the cores) gets half the tabs: a starved tab misses its
// delayRender deadline while it fetches the video. Windows reports no load average (0).
const concurrency = () => Number(flags.concurrency) ||
  (os.loadavg()[0] > CORES * 0.7 ? Math.max(1, Math.floor(CORES / 2)) : CORES);
// Every delayRender (the video frame, fonts, Lottie) may take this long; Remotion's default is 30 s,
// which a still fetching cut.mp4 under heavy load once missed.
const TIMEOUT_MS = 120000;
// Drafts on a Mac encode with VideoToolbox (hardware). It takes a bitrate, not a quality level:
// 12 Mbit/s at 1080p, scaled with the pixel count. Finals stay on x264, the encoder Modal and GitHub
// use, so a final looks the same wherever it renders.
const hwOpts = (composition, scale) => (flags.draft && process.platform === "darwin")
  ? { hardwareAcceleration: "if-possible", crf: null,
      videoBitrate: `${Math.round(12 * (composition.width * composition.height * scale * scale) / (1080 * 1920))}M` }
  : {};

async function prepare(publicDir, planPath) {
  const inputProps = readPlan(planPath);
  const t0 = Date.now();
  let serveUrl = path.resolve(publicDir);
  if (!fs.existsSync(path.join(serveUrl, "bundle.js"))) {
    serveUrl = await bundle({ entryPoint: ENTRY, publicDir: serveUrl });
    // The bundle is a temp folder holding a copy of the video and images (150 MB+ per render) that
    // Remotion never deletes; left alone, a few dozen renders fill the disk.
    process.on("exit", () => { try { fs.rmSync(serveUrl, { recursive: true, force: true }); } catch {} });
  }
  const composition = await selectComposition({ serveUrl, id: inputProps.composition || ID, inputProps });
  return { serveUrl, composition, inputProps, bundleS: (Date.now() - t0) / 1000 };
}

async function stills(publicDir, planPath, outDir, ...pairs) {
  const { serveUrl, composition, inputProps } = await prepare(publicDir, planPath);
  fs.mkdirSync(outDir, { recursive: true });
  for (const pair of pairs) {
    const [name, frame] = pair.split("=");
    const output = path.join(outDir, `${name}.png`);
    const once = () => renderStill({ serveUrl, composition, inputProps, output, frame: Number(frame),
      timeoutInMilliseconds: TIMEOUT_MS });
    try {
      await once();
    } catch (e) {
      if (!/timeout|timed out|delayRender/i.test(String(e?.message ?? e))) throw e;
      console.error(`still ${name}: ${String(e?.message ?? e).split("\n")[0]}; trying once more`);
      await once();
    }
    console.log(output);
  }
}

async function bench(publicDir, planPath) {
  const { serveUrl, composition, inputProps, bundleS } = await prepare(publicDir, planPath);
  const n = Math.min(composition.durationInFrames, composition.fps * 2);
  const from = Math.max(0, Math.floor(composition.durationInFrames / 2 - n / 2));
  const out = path.join(HERE, "out", "bench.mp4");
  const t0 = Date.now();
  await renderMedia({ serveUrl, composition, inputProps, codec: "h264", outputLocation: out,
    frameRange: [from, from + n - 1], concurrency: concurrency(), timeoutInMilliseconds: TIMEOUT_MS });
  const s = (Date.now() - t0) / 1000;
  console.log(JSON.stringify({ bundle_s: bundleS, bench_frames: n, bench_s: s,
    s_per_frame: s / n, frames: composition.durationInFrames }));
}

async function local(publicDir, planPath, out) {
  const { serveUrl, composition, inputProps } = await prepare(publicDir, planPath);
  const t0 = Date.now();
  const scale = flags.draft ? 2 / 3 : 1;
  let last = -1;
  // Rendering straight to mp4 puts the AAC encoder's start-up padding in front of the sound, so the
  // audio lands 43 ms after the picture. Render PCM audio in an mkv, then encode AAC once, trimmed
  // to the video: the same path the GitHub join takes, sample-aligned with the cut.
  const tmp = out.replace(/\.mp4$/i, "") + ".tmp.mkv";
  await renderMedia({ serveUrl, composition, inputProps, codec: "h264-mkv", outputLocation: tmp,
    enforceAudioTrack: true, concurrency: concurrency(), scale, ...hwOpts(composition, scale), timeoutInMilliseconds: TIMEOUT_MS,
    onProgress: ({ progress }) => {
      const p = Math.floor(progress * 10);
      if (p !== last) { last = p; process.stdout.write(`${p * 10}% `); }
    } });
  const r = spawnSync("ffmpeg", ["-v", "error", "-y", "-i", tmp, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
    "-shortest", "-movflags", "+faststart", out], { stdio: "inherit" });
  fs.rmSync(tmp, { force: true });
  if (r.status !== 0) throw new Error(`ffmpeg could not write ${out}`);
  console.log(`\nrendered ${out} in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
}

// One slice of the video, for the GitHub workflow's parallel render. The join step concatenates them.
async function chunk(publicDir, planPath, out, from, to) {
  const { serveUrl, composition, inputProps } = await prepare(publicDir, planPath);
  const t0 = Date.now();
  // h264-mkv carries PCM audio: sample-exact to the frame, no AAC padding, so pieces join without a
  // gap. The join encodes the audio to AAC once.
  await renderMedia({ serveUrl, composition, inputProps, codec: "h264-mkv", outputLocation: out,
    frameRange: [Number(from), Number(to)], enforceAudioTrack: true, concurrency: concurrency(),
    timeoutInMilliseconds: TIMEOUT_MS });
  console.log(`rendered ${out} (frames ${from}-${to}) in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
}

async function bundleTo(publicDir, outDir) {
  fs.rmSync(outDir, { recursive: true, force: true });
  await bundle({ entryPoint: ENTRY, publicDir: path.resolve(publicDir), outDir: path.resolve(outDir) });
  console.log(outDir);
}

async function lambdaEstimate(planPath) {
  const { estimatePrice } = await import("@remotion/lambda");
  const frames = readPlan(planPath).durationInFrames;
  const fpl = framesPerLambda(frames);
  const lambdas = Math.ceil(frames / fpl);
  const usd = estimatePrice({ region: REGION, memorySizeInMb: MEMORY_MB, diskSizeInMb: DISK_MB,
    lambdasInvoked: lambdas + 1, durationInMilliseconds: frames * LAMBDA_S_PER_FRAME * 1000 });
  console.log(JSON.stringify({ region: REGION, lambdas, usd,
    wall_s: Math.round(fpl * LAMBDA_S_PER_FRAME + 25) }));
}

async function lambda(publicDir, planPath, out, siteName) {
  const L = await import("@remotion/lambda");
  const inputProps = readPlan(planPath);
  console.log(`region ${REGION}: deploying function (skipped if it exists)`);
  const { functionName } = await L.deployFunction({ region: REGION, timeoutInSeconds: 240,
    memorySizeInMb: MEMORY_MB, diskSizeInMb: DISK_MB, createCloudWatchLogGroup: true });
  const { bucketName } = await L.getOrCreateBucket({ region: REGION });
  console.log(`uploading site ${siteName} (only changed files)`);
  const { serveUrl } = await L.deploySite({ entryPoint: ENTRY, bucketName, region: REGION, siteName,
    options: { publicDir: path.resolve(publicDir) } });
  const t0 = Date.now();
  const { renderId } = await L.renderMediaOnLambda({ region: REGION, functionName, serveUrl,
    composition: inputProps.composition || ID, inputProps, codec: "h264", privacy: "private", maxRetries: 2,
    framesPerLambda: framesPerLambda(inputProps.durationInFrames) });
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    const p = await L.getRenderProgress({ renderId, bucketName, functionName, region: REGION });
    if (p.fatalErrorEncountered) throw new Error(p.errors.map((e) => e.message).join("\n"));
    process.stdout.write(`${Math.round(p.overallProgress * 100)}% `);
    if (p.done) {
      await L.downloadMedia({ region: REGION, bucketName, renderId, outPath: out });
      console.log(`\nrendered ${out} in ${((Date.now() - t0) / 1000).toFixed(1)} s, ` +
        `AWS cost ${p.costs.displayCost}`);
      return;
    }
  }
}

const cmds = { stills, bench, local, chunk, bundle: bundleTo, "lambda-estimate": lambdaEstimate, lambda };
if (!cmds[cmd]) {
  console.error(`usage: node render.mjs ${Object.keys(cmds).join("|")} ...`);
  process.exit(2);
}
await cmds[cmd](...pos);
