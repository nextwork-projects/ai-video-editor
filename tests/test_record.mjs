// record.mjs safety, tested on its own source: the deny list (never press what deletes, pays, publishes or
// invites) and the blur (personal data, the logged-in account's own name) run on a synthetic page in the
// Chrome Headless Shell the renderer installs.
//
//   node tests/test_record.mjs              the deny list always; the blur when the shell is installed
//   node tests/test_record.mjs --require-chrome   CI after setup: a missing shell fails instead of skipping
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import assert from "node:assert/strict";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCRIPTS = path.join(ROOT, "plugins/ai-editor/skills");
const src = fs.readFileSync(path.join(SCRIPTS, "product-video/scripts/record.mjs"), "utf8");

// record.mjs runs on import, so its two constants are read from the source. A rename fails here, loudly.
const deny = src.match(/^const DENY = (\/.*\/[a-z]*);$/m);
assert.ok(deny, "record.mjs has no `const DENY = /.../;` line");
const DENY = eval(deny[1]);
// crawl.mjs's summary line names a text logo by its word, never "logo undefined".
const crawlSrc = fs.readFileSync(path.join(SCRIPTS, "product-video/scripts/crawl.mjs"), "utf8");
const note = crawlSrc.match(/^const logoNote = (.*);$/m);
assert.ok(note, "crawl.mjs has no `const logoNote = ...;` line");
const logoNote = eval(note[1]);
assert.equal(logoNote({ word: "Acme", rect: [0, 0, 10, 10] }), 'text "Acme"');
assert.equal(logoNote({ src: "images/logo.svg" }), "images/logo.svg");
assert.equal(logoNote(null), "none");
const blurAt = src.indexOf("const BLUR = (cfg) => `");
const blurEnd = src.indexOf("})()`;", blurAt);
assert.ok(blurAt >= 0 && blurEnd > blurAt, "record.mjs has no `const BLUR = (cfg) => \\`...\\`` block");
const BLUR = eval(src.slice(blurAt + "const BLUR = ".length, blurEnd + "})()`".length));

for (const t of ["Create a project", "Delete project", "Remove member", "Pay now", "Buy credits", "Checkout", "Upgrade to Pro", "Subscribe",
  "Billing", "Cancel subscription", "Publish", "Invite teammates", "Send invite", "Transfer ownership", "Deactivate",
  "Close account", "Log out", "Sign out"]) assert.ok(DENY.test(t), `DENY lets through ${JSON.stringify(t)}`);
for (const t of ["Start free", "Projects", "Search", "Open roadmap", "Next step", "Library"])
  assert.ok(!DENY.test(t), `DENY blocks the harmless ${JSON.stringify(t)}`);
console.log("deny list ok");

// snapClip: a shot whose edge crosses a line of text grows to take the line whole; one past the page drops it
{
  const { snapClip: snap } = await import(pathToFileURL(path.join(SCRIPTS, "style-edit/scripts/capture.mjs")).href);
  const ln = [[20, 90, 300, 20], [20, 300, 900, 20]];
  const cuts = (c) => ln.filter(([x, y, w, h]) => x < c[0] + c[2] && x + w > c[0] && y < c[1] + c[3] && y + h > c[1]
    && !(x >= c[0] && y >= c[1] && x + w <= c[0] + c[2] && y + h <= c[1] + c[3])).length;
  const naive = [0, 0, 600, 100];
  assert.equal(cuts(naive), 1, "the naive clip cuts the first line");
  assert.equal(cuts(snap(naive, ln)), 0, JSON.stringify(snap(naive, ln)));
  assert.equal(cuts(snap([0, 200, 600, 120], ln, [600, 1000])), 0, "a line wider than the page is left out whole");
  console.log("snapClip ok");
}

// pool: capture.mjs, crawl.mjs and record.mjs --states run pages a few at a time; results keep the input order
{
  const { pool } = await import(pathToFileURL(path.join(SCRIPTS, "style-edit/scripts/capture.mjs")).href);
  let live = 0, peak = 0;
  const got = await pool([30, 5, 20, 1, 10], 2, async (ms, i) => {
    peak = Math.max(peak, ++live);
    await new Promise((r) => setTimeout(r, ms));
    live--;
    return i;
  });
  assert.deepEqual(got, [0, 1, 2, 3, 4], "results out of order");
  assert.equal(peak, 2, `ran ${peak} at once, asked for 2`);
  assert.deepEqual(await pool([], 4, async () => 1), []);
  console.log("pool ok");
}

// The captions keep the leaving scene's ink until its ground is gone from under them (ground.ts): halfway
// through an iris out (the old switch, 0.31 s early) the paper still covers a caption at 75%, near the end it does not
{
  const { groundCovers } = await import(pathToFileURL(path.join(ROOT, "plugins/ai-editor/remotion/src/ground.ts")).href);
  const at = (kind, p, ph = 0.31) => groundCovers(kind, true, p, ph, 0.62, 1080, 1920, [50, 30], 540, 0.75 * 1920);
  assert.equal(at("iris", 0.5), true, "iris out halfway: the ground is still under the captions");
  assert.equal(at("iris", 0.2), false, "iris nearly closed on the face: the captions are on the footage");
  assert.equal(at("match", 0.9), true);
  assert.equal(at("match", 0.5), false, "a match out uncovers a low caption before halfway");
  assert.equal(at("push", 0.6), true);
  assert.equal(at("push", 0.4), false);
  assert.equal(at("wipe", 0.6), true);
  assert.equal(at("block", 1, 0.2), true);
  assert.equal(at("block", 1, 0.4), false);
  console.log("scene ink until the ground leaves ok");
}

// login.mjs finds Chrome off its fixed paths too: PATH on Linux (snap, a distro chromium), Edge on Windows
{
  const { chromeBinary } = await import(pathToFileURL(path.join(SCRIPTS, "product-video/scripts/login.mjs")).href);
  const only = (want) => (p) => p === want;
  assert.equal(chromeBinary("linux", { PATH: "/opt/x/bin:/home/u/.local/bin" }, only("/home/u/.local/bin/chromium")), "/home/u/.local/bin/chromium");
  assert.equal(chromeBinary("linux", { PATH: "/usr/bin" }, only("/snap/bin/chromium")), "/snap/bin/chromium");
  const edge = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
  assert.equal(chromeBinary("win32", { PROGRAMFILES: "C:\\Program Files", "PROGRAMFILES(X86)": "C:\\Program Files (x86)", Path: "C:\\Windows" }, only(edge)), edge);
  assert.equal(chromeBinary("win32", { Path: "C:\\Windows;D:\\Tools\\Chrome" }, only("D:\\Tools\\Chrome\\chrome.exe")), "D:\\Tools\\Chrome\\chrome.exe");
  assert.equal(chromeBinary("linux", { PATH: "/usr/bin" }, () => false), null);
  console.log("chrome lookup ok");
}

// login.mjs logout deletes only <home>/browser/<one hostname>: never the home, never every saved login
{
  const { spawnSync } = await import("node:child_process");
  const os = await import("node:os");
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "ave-login-test-"));
  try {
    for (const d of ["browser/example.com/Default", "browser/other.org/Default", "venv"]) fs.mkdirSync(path.join(home, d), { recursive: true });
    const login = path.join(SCRIPTS, "product-video/scripts/login.mjs");
    const run = (...a) => spawnSync(process.execPath, [login, ...a], { env: { ...process.env, AI_EDITOR_HOME: home }, encoding: "utf8" });
    for (const bad of ["..", "/", "", ".", "a/b", "../..", "example.com/..", "C:\\x", "..\\..", "%2e%2e", "https://", "-rf"]) {
      const r = run("logout", bad);
      assert.notEqual(r.status, 0, `logout ${JSON.stringify(bad)} exited 0: ${r.stdout}`);
      for (const d of ["venv", "browser/example.com/Default", "browser/other.org/Default"])
        assert.ok(fs.existsSync(path.join(home, d)), `logout ${JSON.stringify(bad)} deleted ${d}`);
    }
    assert.notEqual(run("where", "..").status, 0, "where .. names a folder");
    const r = run("logout", "https://www.example.com/settings");
    assert.equal(r.status, 0, r.stderr);
    assert.ok(!fs.existsSync(path.join(home, "browser/example.com")), "logout example.com left the profile");
    assert.ok(fs.existsSync(path.join(home, "browser/other.org/Default")) && fs.existsSync(path.join(home, "venv")));
    console.log("logout ok");
  } finally {
    fs.rmSync(home, { recursive: true, force: true });
  }
}

// Lambda: after a downloaded render, the footage (the deployed site holds the public dir) and the render's
// objects leave the user's bucket. render.mjs imports Remotion on load, so the function is read from its source.
{
  const rsrc = fs.readFileSync(path.join(ROOT, "plugins/ai-editor/remotion/render.mjs"), "utf8");
  const m = rsrc.match(/^const cleanupLambda = (async \(L, o\) => \{[\s\S]*?\n\});$/m);
  assert.ok(m, "render.mjs has no `const cleanupLambda = async (L, o) => {...};` block");
  const cleanupLambda = eval(m[1]);
  const calls = [];
  const L = { deleteRender: async (a) => calls.push(["render", a]), deleteSite: async (a) => calls.push(["site", a]) };
  await cleanupLambda(L, { region: "us-east-1", bucketName: "remotionlambda-x", renderId: "r1", siteName: "ai-editor-take" });
  assert.deepEqual(calls, [["render", { region: "us-east-1", bucketName: "remotionlambda-x", renderId: "r1" }],
    ["site", { region: "us-east-1", bucketName: "remotionlambda-x", siteName: "ai-editor-take" }]]);
  assert.match(rsrc, /if \(flags\.cleanup\) await cleanupLambda\(L,/, "lambda() never calls cleanupLambda on --cleanup");
  assert.match(rsrc, /downloadMedia[\s\S]{0,400}if \(flags\.cleanup\)/, "cleanup must come after the download");
  console.log("lambda cleanup ok");
}

// --no-sandbox only on Linux, and only when a probe launch says the sandbox itself cannot start
{
  const { noSandbox } = await import(pathToFileURL(path.join(SCRIPTS, "style-edit/scripts/capture.mjs")).href);
  const dead = { status: 1, stderr: "FATAL:zygote_host_impl_linux.cc No usable sandbox! Update your kernel or see .../linux/suid_sandbox_development.md" };
  assert.equal(noSandbox("linux", { status: 0, stderr: "" }), false, "a working sandbox stays on");
  assert.equal(noSandbox("linux", dead), true, "a sandbox that cannot start is turned off");
  assert.equal(noSandbox("linux", { status: 1, stderr: "Running as root without --no-sandbox is not supported" }), true);
  assert.equal(noSandbox("linux", { status: 127, stderr: "error while loading shared libraries: libnss3.so" }), false, "an unrelated crash keeps the sandbox");
  assert.equal(noSandbox("darwin", dead), false);
  assert.equal(noSandbox("win32", dead), false);
  console.log("sandbox decision ok");
}

// a logo comes from the site's sharpest own icon (SVG, then apple-touch, then a large PNG) before the 256 px
// favicon service; a 32 px favicon is never preferred
{
  const { rankIcons } = await import(pathToFileURL(path.join(SCRIPTS, "style-edit/scripts/capture.mjs")).href);
  const page = `<link rel="icon" href="/favicon.ico" sizes="32x32"><link rel="apple-touch-icon" href="/apple.png">
    <link rel="icon" type="image/svg+xml" href="/logo.svg"><link rel="icon" href="/i-192.png" sizes="192x192"><link rel="stylesheet" href="/a.css">`;
  assert.deepEqual(rankIcons(page, "https://x.io/"), ["https://x.io/logo.svg", "https://x.io/apple.png", "https://x.io/i-192.png"]);
  assert.deepEqual(rankIcons(`<link rel="shortcut icon" href="/favicon.ico">`, "https://x.io/"), []);
  console.log("logo source order ok");
}

const { launch, findBinary, SHELLS, TEXT, STICKER } = await import(pathToFileURL(path.join(SCRIPTS, "style-edit/scripts/capture.mjs")).href);
const bin = findBinary(SHELLS);
if (!bin) {
  if (process.argv.includes("--require-chrome")) throw new Error(`no Chrome Headless Shell under ${SHELLS}`);
  console.log(`blur skipped: no Chrome Headless Shell under ${SHELLS} (setup.py remotion installs it)`);
  process.exit(0);
}

// A made-up logged-in page: the account name in the nav (from whoami, passed as blur.text), an email,
// an email field, a round avatar, and product copy that must stay sharp.
const page = `<!doctype html><html><body style="font:16px sans-serif">
  <nav><span id="me">Jordan Avery</span> <img id="av" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" style="width:40px;height:40px;border-radius:50%"></nav>
  <p id="mail">reach me at jordan@example.org</p><input id="field" value="jordan@example.org">
  <h1 id="copy">Build your first project</h1><p id="card">Owned by Jordan Avery</p></body></html>`;
const cdp = launch(bin);
try {
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const ev = async (expression) => (await cdp.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, sessionId)).result.value;
  const { frameTree } = await cdp.send("Page.getFrameTree", {}, sessionId);
  await cdp.send("Page.setDocumentContent", { frameId: frameTree.frame.id, html: page }, sessionId);
  const hits = await ev(BLUR({ text: ["Jordan Avery", "jordan"], selectors: [], show_names: false }));
  const blurred = await ev(`Object.fromEntries(["me", "av", "mail", "field", "copy", "card"].map((id) =>
    [id, /blur\\(\\d+px\\)/.test(document.getElementById(id).style.filter)]))`);
  assert.deepEqual(blurred, { me: true, av: true, mail: true, field: true, copy: false, card: true }, JSON.stringify({ blurred, hits }));
  assert.ok(hits.some((h) => h.startsWith("listed: ")) && hits.some((h) => h.startsWith("email")), JSON.stringify(hits));
  console.log("blur ok:", [...new Set(hits)].join(", "));
  // TEXT: one box per line, columns kept apart, text an overflow box clips away or a hidden one left out
  const page2 = `<!doctype html><html><body style="margin:0;font:20px/30px sans-serif">
    <div style="display:flex;gap:40px;width:900px"><p id="a" style="width:300px;margin:0">left column words that wrap onto two lines here</p>
    <p style="width:300px;margin:0">right column</p></div>
    <div style="width:120px;overflow:hidden;white-space:nowrap">clipped away after this long run of words</div>
    <p style="visibility:hidden">hidden words</p><p style="opacity:0">clear words</p></body></html>`;
  await cdp.send("Page.setDocumentContent", { frameId: frameTree.frame.id, html: page2 }, sessionId);
  const tx = await ev(TEXT([0, 0, 1000, 700]));
  const ls = tx.lines;
  assert.equal(ls.length, 4, JSON.stringify(ls));                       // two left lines, the right column, the clipped run
  assert.ok(ls.every(([x, , w]) => x + w <= 341 || x >= 339), "a line never spans both columns: " + JSON.stringify(ls));
  assert.ok(ls.some(([x, y, w]) => y > 60 && w <= 120.5), "the overflow box clips its line: " + JSON.stringify(ls));
  console.log("text lines ok");
  // STICKER: a headline set tight (line-height 0.85) with an emoji is re-set at leading 1.2 or more, emoji dropped
  const page3 = `<!doctype html><html><body style="margin:0"><h1 style="font:700 40px/0.85 sans-serif;width:420px">
    <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" style="width:30px"> \u{1F389} TypeSafe announces System One models and Jev, a new model for quick decisions.</h1></body></html>`;
  await cdp.send("Page.setDocumentContent", { frameId: frameTree.frame.id, html: page3 }, sessionId);
  const st = await ev(STICKER("System One", ["System One"], [900, 340], false));
  const lead = await ev(`(() => { const b = document.body.lastElementChild; return parseFloat(getComputedStyle(b).lineHeight) / parseFloat(getComputedStyle(b).fontSize); })()`);
  assert.ok(lead >= 1.1, `sticker leading ${lead}, under 1.1: its lines touch`);
  assert.ok(!/\p{Extended_Pictographic}/u.test(st.sentence) && !(await ev(`document.body.lastElementChild.querySelector("img") !== null`)),
    "sticker keeps the page's emoji: " + st.sentence);
  console.log("sticker leading ok:", lead.toFixed(2));
} finally {
  cdp.close();
}
