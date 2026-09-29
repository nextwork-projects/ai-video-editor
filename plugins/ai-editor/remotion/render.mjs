// Renders a plan.json with the StyleEdit composition. Called by skills/style-edit/scripts/edit.py.
//
//   node render.mjs stills <publicDir> <plan.json> <outDir> name=frame ...
//   node render.mjs bench  <publicDir> <plan.json>            -> JSON: laptop seconds per frame
//   node render.mjs local  <publicDir> <plan.json> <out.mp4>
//   node render.mjs lambda-estimate <plan.json>               -> JSON: Lambda cost + time guess
//   node render.mjs lambda <publicDir> <plan.json> <out.mp4> <siteName>
//
// Lambda uses the user's own AWS credentials: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY,
// or AWS_PROFILE (REMOTION_AWS_* variants work too). Region: REMOTION_AWS_REGION, AWS_REGION, else us-east-1.
import fs from "node:fs";
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

async function prepare(publicDir, planPath) {
  const inputProps = readPlan(planPath);
  const t0 = Date.now();
  const serveUrl = await bundle({ entryPoint: ENTRY, publicDir: path.resolve(publicDir) });
  const composition = await selectComposition({ serveUrl, id: ID, inputProps });
  return { serveUrl, composition, inputProps, bundleS: (Date.now() - t0) / 1000 };
}

async function stills(publicDir, planPath, outDir, ...pairs) {
  const { serveUrl, composition, inputProps } = await prepare(publicDir, planPath);
  fs.mkdirSync(outDir, { recursive: true });
  for (const pair of pairs) {
    const [name, frame] = pair.split("=");
    const output = path.join(outDir, `${name}.png`);
    await renderStill({ serveUrl, composition, inputProps, output, frame: Number(frame) });
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
    frameRange: [from, from + n - 1] });
  const s = (Date.now() - t0) / 1000;
  console.log(JSON.stringify({ bundle_s: bundleS, bench_frames: n, bench_s: s,
    s_per_frame: s / n, frames: composition.durationInFrames }));
}

async function local(publicDir, planPath, out) {
  const { serveUrl, composition, inputProps } = await prepare(publicDir, planPath);
  const t0 = Date.now();
  let last = -1;
  await renderMedia({ serveUrl, composition, inputProps, codec: "h264", outputLocation: out,
    onProgress: ({ progress }) => {
      const p = Math.floor(progress * 10);
      if (p !== last) { last = p; process.stdout.write(`${p * 10}% `); }
    } });
  console.log(`\nrendered ${out} in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
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
    composition: ID, inputProps, codec: "h264", privacy: "private", maxRetries: 2,
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

const cmds = { stills, bench, local, "lambda-estimate": lambdaEstimate, lambda };
if (!cmds[cmd]) {
  console.error(`usage: node render.mjs ${Object.keys(cmds).join("|")} ...`);
  process.exit(2);
}
await cmds[cmd](...args);
