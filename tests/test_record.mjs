// record.mjs safety, tested on its own source: the deny list (never press what deletes, pays, publishes or
// invites) and the blur (personal data, the logged-in account's own name) run on a synthetic page in the
// Chrome Headless Shell the renderer installs.
//
//   node tests/test_record.mjs              the deny list always; the blur when the shell is installed
//   node tests/test_record.mjs --require-chrome   CI after setup: a missing shell fails instead of skipping
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SCRIPTS = path.join(ROOT, "plugins/ai-editor/skills");
const src = fs.readFileSync(path.join(SCRIPTS, "product-video/scripts/record.mjs"), "utf8");

// record.mjs runs on import, so its two constants are read from the source. A rename fails here, loudly.
const deny = src.match(/^const DENY = (\/.*\/[a-z]*);$/m);
assert.ok(deny, "record.mjs has no `const DENY = /.../;` line");
const DENY = eval(deny[1]);
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

const { launch, findBinary, SHELLS } = await import(path.join(SCRIPTS, "style-edit/scripts/capture.mjs"));
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
} finally {
  cdp.close();
}
