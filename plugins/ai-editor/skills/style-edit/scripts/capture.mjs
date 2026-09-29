// Screenshots the "capture" beats of edits/NAME/visuals.json into edits/NAME/images/ and lists them
// in edits/NAME/images.json, so plan.py places them like any other card image.
//
//   node capture.mjs edits/NAME
//
// No dependencies: drives the Chrome Headless Shell that Remotion installs under
// ~/.ai-video-editor/remotion (AI_EDITOR_HOME overrides) over the DevTools pipe.
// Per beat, optional: "clip": [x, y, w, h] in page px, or "selector": "css" (the element, padded),
// "width" (viewport px, default 1000), "height" (default 700), "wait_ms" (default 2500),
// "box", "hold_s", "entrance" (passed on to the card).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const HOME = process.env.AI_EDITOR_HOME || path.join(os.homedir(), ".ai-video-editor");
const SHELLS = path.join(HOME, "remotion", "node_modules", ".remotion", "chrome-headless-shell");
const PREFIX = "images/capture-";

const findBinary = (dir) => {
  if (!fs.existsSync(dir)) return null;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isFile() && /^chrome-headless-shell(\.exe)?$/.test(e.name)) return p;
    if (e.isDirectory()) {
      const hit = findBinary(p);
      if (hit) return hit;
    }
  }
  return null;
};

// Minimal DevTools Protocol client over --remote-debugging-pipe (fd 3 in, fd 4 out, \0-framed JSON).
function launch(bin) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "ai-editor-capture-"));
  const proc = spawn(bin, ["--remote-debugging-pipe", "--no-first-run", "--hide-scrollbars", "--mute-audio",
    `--user-data-dir=${profile}`, "about:blank"], { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
  let id = 0, buf = "";
  const waiting = new Map(), listeners = [];
  proc.stdio[4].on("data", (d) => {
    buf += d.toString();
    let i;
    while ((i = buf.indexOf("\0")) >= 0) {
      const msg = JSON.parse(buf.slice(0, i));
      buf = buf.slice(i + 1);
      if (msg.id && waiting.has(msg.id)) {
        const [ok, fail] = waiting.get(msg.id);
        waiting.delete(msg.id);
        msg.error ? fail(new Error(msg.error.message)) : ok(msg.result);
      } else listeners.forEach((l) => l(msg));
    }
  });
  const send = (method, params = {}, sessionId) => new Promise((ok, fail) => {
    waiting.set(++id, [ok, fail]);
    proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0");
  });
  const once = (method, sessionId, ms) => new Promise((ok) => {
    const l = (m) => { if (m.method === method && m.sessionId === sessionId) done(true); };
    const timer = setTimeout(() => done(false), ms);
    const done = (v) => { clearTimeout(timer); listeners.splice(listeners.indexOf(l), 1); ok(v); };
    listeners.push(l);
  });
  const close = () => { proc.kill(); fs.rmSync(profile, { recursive: true, force: true }); };
  return { send, once, close };
}

// Accept the cookie banner if there is an obvious button, then hide whatever fixed overlay still says cookie/consent.
const DISMISS = `(() => {
  const btn = [...document.querySelectorAll('button, a, [role=button]')]
    .find((b) => /^(accept( all)?( cookies)?|agree|allow all|i agree|got it|ok)$/i.test((b.innerText || '').trim()));
  if (btn) btn.click();
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if ((s.position === 'fixed' || s.position === 'sticky') && /cookie|consent|gdpr|privacy/i.test(el.innerText || '')
        && el.innerText.length < 2000) el.remove();
  }
})()`;

async function shoot(cdp, beat, out) {
  const width = beat.width || 1000, height = beat.height || 700;
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, p) => cdp.send(m, p, sessionId);
  try {
    await s("Page.enable");
    await s("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 2, mobile: false });
    const loaded = cdp.once("Page.loadEventFired", sessionId, 30000);
    await s("Page.navigate", { url: beat.url });
    if (!(await loaded)) console.error(`  ${beat.url}: no load event after 30 s, shooting anyway`);
    await new Promise((r) => setTimeout(r, beat.wait_ms ?? 2500));
    await s("Runtime.evaluate", { expression: DISMISS });
    await new Promise((r) => setTimeout(r, 600));
    let clip = { x: 0, y: 0, width, height };
    if (beat.clip) {
      const [x, y, w, h] = beat.clip;
      clip = { x, y, width: w, height: h };
    } else if (beat.selector) {
      const { result } = await s("Runtime.evaluate", { returnByValue: true, expression: `(() => {
        const el = document.querySelector(${JSON.stringify(beat.selector)});
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height };
      })()` });
      if (result.value) {
        const pad = 16, r = result.value;
        clip = { x: Math.max(0, r.x - pad), y: Math.max(0, r.y - pad), width: r.width + pad * 2, height: r.height + pad * 2 };
      } else console.error(`  ${beat.url}: selector ${beat.selector} not found, shooting the viewport`);
    }
    const { data } = await s("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { ...clip, scale: 1 } });
    fs.writeFileSync(out, Buffer.from(data, "base64"));
  } finally {
    await cdp.send("Target.closeTarget", { targetId });
  }
}

const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "beat";

// Logos: Simple Icons first (CC0, brand-coloured SVG, thousands of brands), then the
// site's own icon via Google's favicon service. Written to images/logo-<brand>.<ext>,
// the path plan.py expects. A logo the user already put there is kept.
const logoPath = (brand, ext) => `images/logo-${slug(brand)}.${ext}`;

async function fetchLogos(edit, beats) {
  let failed = 0;
  for (const b of beats) {
    const brand = b.brand || b.word;
    if (["svg", "png"].some((e) => fs.existsSync(path.join(edit, logoPath(brand, e))))) continue;
    const tries = [[`https://cdn.simpleicons.org/${slug(brand).replace(/-/g, "")}`, "svg"]];
    if (b.domain) tries.push([`https://www.google.com/s2/favicons?domain=${b.domain}&sz=256`, "png"]);
    let ok = false;
    for (const [url, ext] of tries) {
      const r = await fetch(url).catch(() => null);
      if (!r || !r.ok) continue;
      fs.writeFileSync(path.join(edit, logoPath(brand, ext)), Buffer.from(await r.arrayBuffer()));
      console.log(`${logoPath(brand, ext)}  <- ${url}`);
      ok = true;
      break;
    }
    if (!ok) {
      failed++;
      console.error(`  no logo for '${brand}'${b.domain ? "" : ' (add "domain" to fall back to the site icon)'}`);
    }
  }
  return failed;
}

// Icons for scenes: Lucide (ISC licence), one SVG per name, into images/icon-<name>.svg.
async function fetchIcons(edit, names) {
  let failed = 0;
  for (const name of new Set(names)) {
    const out = path.join(edit, `images/icon-${slug(name)}.svg`);
    if (fs.existsSync(out)) continue;
    const url = `https://cdn.jsdelivr.net/npm/lucide-static@latest/icons/${slug(name)}.svg`;
    const r = await fetch(url).catch(() => null);
    if (!r || !r.ok) {
      failed++;
      console.error(`  no icon '${name}' (names: lucide.dev/icons)`);
      continue;
    }
    fs.writeFileSync(out, Buffer.from(await r.arrayBuffer()));
    console.log(`images/icon-${slug(name)}.svg  <- ${url}`);
  }
  return failed;
}

// Every {"icon": ...} and {"logo": ..., "domain"?: ...} nested anywhere in the anim beats' props.
const sceneRefs = (node, icons = [], logos = []) => {
  if (Array.isArray(node)) node.forEach((x) => sceneRefs(x, icons, logos));
  else if (node && typeof node === "object") {
    if (typeof node.icon === "string") icons.push(node.icon);
    if (typeof node.logo === "string") logos.push({ brand: node.logo, domain: node.domain });
    Object.values(node).forEach((x) => sceneRefs(x, icons, logos));
  }
  return { icons, logos };
};

async function main() {
  const edit = process.argv[2];
  if (!edit) {
    console.error("usage: node capture.mjs edits/NAME");
    process.exit(2);
  }
  const visuals = JSON.parse(fs.readFileSync(path.join(edit, "visuals.json"), "utf8"));
  fs.mkdirSync(path.join(edit, "images"), { recursive: true });
  const refs = sceneRefs(visuals.filter((v) => v.kind === "anim").map((v) => v.props));
  let failed = await fetchLogos(edit, [...visuals.filter((v) => v.kind === "logo"), ...refs.logos]);
  failed += await fetchIcons(edit, refs.icons);
  const beats = visuals.filter((v) => v.kind === "capture");
  if (!beats.length) process.exit(failed ? 1 : 0);
  const bin = findBinary(SHELLS);
  if (!bin) {
    console.error(`ERROR: no Chrome Headless Shell under ${SHELLS}. Run edit.py stills once (it installs the renderer).`);
    process.exit(1);
  }
  const listPath = path.join(edit, "images.json");
  // Keep the user's own images; replace captures from an earlier run.
  const images = (fs.existsSync(listPath) ? JSON.parse(fs.readFileSync(listPath, "utf8")) : [])
    .filter((im) => !im.src.startsWith(PREFIX));
  const cdp = launch(bin);
  try {
    for (const [i, b] of beats.entries()) {
      const src = `${PREFIX}${i + 1}-${slug(b.word)}.png`;
      try {
        await shoot(cdp, b, path.join(edit, src));
      } catch (e) {
        failed++;
        console.error(`  failed ${b.url}: ${e.message}`);
        continue;
      }
      const im = { src, word: b.word };
      for (const k of ["nth", "box", "hold_s", "entrance"]) if (b[k] !== undefined) im[k] = b[k];
      images.push(im);
      console.log(`${src}  <- ${b.url}`);
    }
  } finally {
    cdp.close();
  }
  fs.writeFileSync(listPath, JSON.stringify(images, null, 1));
  console.log(`${listPath}: captures and logos done, ${failed} failed`);
  if (failed) process.exit(1);
}

await main();
