// Screenshots the "capture" beats of edits/NAME/visuals.json into edits/NAME/images/ and lists them
// in edits/NAME/images.json, so plan.py places them like any other card image.
//
//   node capture.mjs edits/NAME
//
// No dependencies: drives the Chrome Headless Shell that Remotion installs under
// ~/.ai-video-editor/remotion (AI_EDITOR_HOME overrides) over the DevTools pipe.
// Per beat, optional: "clip": [x, y, w, h] in page px, or "selector": "css" (the element, padded),
// "width" (viewport px, default 1000), "height" (default 700), "wait_ms" (default 2500),
// "box", "hold_s", "entrance" (passed on to the card), "highlight": "an exact sentence on the page"
// (the shot runs from the clip down past that sentence, and images.json gets the sentence's line boxes
// so the card scrolls to it and sweeps a highlighter over it), "marks": [{"kind", "find": "text on the
// page", "at_word"}] (rect measured from the text, in the PNG's px), "page_text": true (writes the page's
// text blocks to capture-N.text.json for route.py highlight). A "format": "sticker" beat with marks and no
// "props.crop" is cut to the one sentence that holds the first mark: that sentence is re-set on its own in
// the page's own font, size and colour, at the width that reads largest in the sticker's box ("fit":
// [w, h] display px, default [900, 340], the free band above the head on vertical), on white (the page's
// own ground with "keep_ground": true, or when the page's text is light), shot at 3x. images.json gets
// "xh" (the font's x-height in PNG px) so plan.py can warn when it renders too small to read on a phone.
// Free sources, no keys: "kind": "post" (X post via the public embed endpoint, text verified, fields
// into images/post-<id>.json for a social_post card), "app" (App Store lookup: icon as the logo, first
// screenshot as a card), "youtube" (the video's thumbnail), "github" (the repo's social card).
// Cookie banners: a bundled list of consent-manager selectors is hidden and a reject/accept button clicked.
import { spawn, spawnSync } from "node:child_process";
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

// Chrome's sandbox stays on. Linux only: some systems block the unprivileged namespaces it needs (Ubuntu 23.10+
// AppArmor, many containers) or run as root, and Chrome then dies on start. A probe launch with the sandbox
// decides; only when its error names the sandbox are pages opened without it, and the run says so.
const noSandbox = (platform, probe) => platform === "linux" && probe.status !== 0
  && /sandbox|namespace/i.test(probe.stderr || "");
const probed = new Map();
function sandboxFlags(bin) {
  if (process.platform !== "linux") return [];
  if (!probed.has(bin)) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ai-editor-probe-"));
    const r = spawnSync(bin, ["--headless", "--no-first-run", `--user-data-dir=${dir}`, "--dump-dom", "about:blank"],
      { encoding: "utf8", timeout: 30000 });
    try { fs.rmSync(dir, { recursive: true, force: true }); } catch {}
    const off = noSandbox(process.platform, { status: r.status, stderr: r.stderr });
    if (off) console.error("note: Chrome's sandbox cannot start on this computer (" +
      ((r.stderr || "").split("\n").find((l) => /sandbox|namespace/i.test(l)) || "").trim().slice(0, 160) +
      "), so pages open without it. Allow unprivileged user namespaces, or don't run as root, to keep it on.");
    probed.set(bin, off);
  }
  return [...(probed.get(bin) ? ["--no-sandbox"] : []), "--disable-dev-shm-usage"];
}

// Minimal DevTools Protocol client over --remote-debugging-pipe (fd 3 in, fd 4 out, \0-framed JSON).
function launch(bin) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "ai-editor-capture-"));
  const flags = ["--remote-debugging-pipe", "--no-first-run", "--hide-scrollbars", "--mute-audio", ...sandboxFlags(bin)];
  const proc = spawn(bin, [...flags, `--user-data-dir=${profile}`, "about:blank"],
    { stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] });
  let id = 0, buf = "", errTail = "";
  const waiting = new Map(), listeners = [];
  proc.stdio[2].on("data", (d) => { errTail = (errTail + d.toString()).slice(-600); });
  // If Chrome dies, fail every pending call with its last words instead of crashing on the pipe.
  const died = (why) => {
    for (const [, fail] of waiting.values()) fail(new Error(`Chrome stopped (${why}). ${errTail.trim().split("\n").pop() || ""}`));
    waiting.clear();
  };
  proc.on("exit", (code, sig) => died(`exit ${code ?? sig}`));
  proc.stdio[3].on("error", (e) => died(e.code || e.message));
  proc.stdio[4].on("error", (e) => died(e.code || e.message));
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
  // Chrome keeps writing its profile for a moment after the kill; retry, and never fail a capture
  // run over a temp folder the OS cleans up anyway.
  const close = () => {
    proc.kill();
    try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); } catch {}
  };
  return { send, once, close };
}

// Cookie and consent banners, without an ad-block dependency: a bundled list of the common consent
// managers' containers, hidden by CSS, plus a click on a reject (else accept) button found by its text.
// Then any fixed overlay that still says cookie/consent is removed and floating widgets are hidden.
const CONSENT = ["#onetrust-consent-sdk", "#onetrust-banner-sdk", "#CybotCookiebotDialog", "#usercentrics-root",
  "#usercentrics-cmp-ui", ".qc-cmp2-container", "#qc-cmp2-container", ".fc-consent-root", "#didomi-host", "#truste-consent-track",
  "#truste-consent-content", ".truste_overlay", "#trustarc-banner-overlay", ".cc-window", ".cc-banner", "#cookie-law-info-bar",
  ".osano-cm-window", "#hs-eu-cookie-confirmation", ".cky-consent-container", ".cky-overlay", "#cmplz-cookiebanner-container",
  ".iubenda-cs-container", "#iubenda-cs-banner", ".klaro", "#ccc", ".evidon-banner", "#sp_message_container",
  "[id^=sp_message_container]", "#consent-banner", "#cookie-banner", "#cookieBanner", ".cookie-banner", ".cookie-consent",
  "#cookie-consent", ".gdpr-banner", "#gdpr-cookie-message", "[aria-label*=cookie i][role=dialog]",
  "[aria-label*=consent i][role=dialog]", "[data-testid*=cookie i]", "[class*=CookieBanner]", "[class*=cookieBanner]",
  "[class*=cookie-notice]", "[id*=cookie-notice]"];
const DISMISS = `(() => {
  const css = document.createElement('style');
  css.textContent = ${JSON.stringify(CONSENT.join(","))} + '{display:none!important}'
    + 'html,body{overflow:auto!important;position:static!important}';
  document.head && document.head.appendChild(css);
  const say = (b) => (b.innerText || b.value || b.getAttribute('aria-label') || '').trim().toLowerCase();
  const btns = [...document.querySelectorAll('button, a, [role=button], input[type=button], input[type=submit]')];
  const reject = /^(reject( all)?( cookies)?|decline( all)?|deny( all)?|only (strictly )?necessary|necessary (cookies )?only|use necessary cookies only|refuse( all)?|continue without accepting)$/;
  const accept = /^(accept( all)?( cookies)?|agree( to all)?|allow all( cookies)?|i agree|i accept|got it|ok|okay|accept and continue)$/;
  const btn = btns.find((b) => reject.test(say(b))) || btns.find((b) => accept.test(say(b)));
  if (btn) btn.click();
  for (const el of document.querySelectorAll('body *')) {
    const s = getComputedStyle(el);
    if ((s.position === 'fixed' || s.position === 'sticky') && /cookie|consent|gdpr|privacy/i.test(el.innerText || '')
        && el.innerText.length < 2000) el.remove();
    // Floating widgets (chat and "ask" buttons, bottom bars): fixed, and not the header at the top.
    else if (s.position === 'fixed' && el.getBoundingClientRect().top > 40) el.style.visibility = 'hidden';
  }
  return !!btn;
})()`;

// The line boxes of the first place `target` appears in the page's visible text, in page px.
// Whitespace and case are ignored, and the text may run across links and inline tags.
const FIND = (target) => `(() => {
  const want = ${JSON.stringify(target)}.replace(/\\s+/g, ' ').trim().toLowerCase();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let text = '', map = [], space = true;
  for (let n; (n = walker.nextNode());) {
    if (!n.parentElement || !n.parentElement.offsetParent) continue;
    const s = n.nodeValue;
    for (let i = 0; i < s.length; i++) {
      const sp = /\\s/.test(s[i]);
      if (sp && space) continue;
      text += sp ? ' ' : s[i].toLowerCase();
      map.push([n, i]);
      space = sp;
    }
  }
  // every place it appears, so the caller can prefer the one inside its clip
  const all = [];
  for (let at = text.indexOf(want); at >= 0 && all.length < 20; at = text.indexOf(want, at + 1)) {
    const r = document.createRange();
    r.setStart(...map[at]);
    const [en, eo] = map[at + want.length - 1];
    r.setEnd(en, eo + 1);
    const rs = [...r.getClientRects()].filter((q) => q.width > 2 && q.height > 2)
      .map((q) => [q.left + scrollX, q.top + scrollY, q.width, q.height]);
    if (rs.length) all.push(rs);
  }
  return all.length ? all : null;
})()`;

// Sticker: the sentence holding `target`, re-set alone in a block of its own (the page's font, size,
// weight and colour, its bold and links kept), at the width whose text renders largest in a box of
// fit[0] x fit[1] display px. Returns the block's page rect, the marks' line boxes inside it and the
// font's x-height, all in page px.
const STICKER = (target, finds, fit, keepGround) => `(() => {
  const norm = (t) => t.replace(/\\s+/g, ' ').trim().toLowerCase();
  const want = norm(${JSON.stringify(target)});
  const blockOf = (n) => { let e = n.parentElement; while (e && e !== document.body && getComputedStyle(e).display.startsWith('inline')) e = e.parentElement; return e; };
  const walk = (root) => {
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let text = '', map = [], space = true;
    for (let n; (n = tw.nextNode());) {
      if (!n.parentElement || !n.parentElement.getClientRects().length) continue;
      const b = blockOf(n), s = n.nodeValue;
      for (let i = 0; i < s.length; i++) {
        const sp = /\\s/.test(s[i]);
        if (sp && space) continue;
        text += sp ? ' ' : s[i];
        map.push([n, i, b]);
        space = sp;
      }
    }
    return { text, map };
  };
  const { text, map } = walk(document.body);
  const at = text.toLowerCase().indexOf(want);
  if (at < 0) return null;
  const blk = map[at][2];
  // the sentence: out to . ! ? followed by a space, never past the block
  let a = at, b = at + want.length - 1;
  while (a > 0 && map[a - 1][2] === blk && !(text[a - 1] === ' ' && /[.!?]/.test(text[a - 2] || ''))) a--;
  while (b < text.length - 1 && map[b + 1][2] === blk && !(/[.!?]/.test(text[b]) && text[b + 1] === ' ')) b++;
  while (text[a] === ' ') a++;
  while (text[b] === ' ') b--;
  const r = document.createRange();
  r.setStart(map[a][0], map[a][1]);
  r.setEnd(map[b][0], map[b][1] + 1);
  const cs = getComputedStyle(blk);
  let bg = 'rgba(0, 0, 0, 0)';
  for (let e = blk; e && /rgba\\(0, 0, 0, 0\\)|transparent/.test(bg); e = e.parentElement) bg = getComputedStyle(e).backgroundColor;
  if (/rgba\\(0, 0, 0, 0\\)|transparent/.test(bg)) bg = getComputedStyle(document.body).backgroundColor;
  const rgb = (c) => (c.match(/[\\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
  const lum = (c) => { const [x, y, z] = rgb(c); return (0.299 * x + 0.587 * y + 0.114 * z) / 255; };
  const ground = ${keepGround} || lum(cs.color) > 0.5 ? bg : '#ffffff';
  // nothing fixed or sticky (a header bar) may sit over the block
  for (const e of document.querySelectorAll('body *')) {
    const p = getComputedStyle(e).position;
    if (p === 'fixed' || p === 'sticky') e.style.visibility = 'hidden';
  }
  const fs = parseFloat(cs.fontSize), pad = Math.round(fs * 0.7);
  const box = document.createElement('div');
  box.appendChild(r.cloneContents());
  for (const k of ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'color', 'lineHeight', 'letterSpacing', 'fontFeatureSettings', 'textTransform'])
    box.style[k] = cs[k];
  Object.assign(box.style, { position: 'absolute', left: '0px', top: '0px', zIndex: 2147483647, background: ground, padding: pad + 'px',
    margin: '0', boxSizing: 'content-box', whiteSpace: 'normal', textAlign: 'left', visibility: 'visible' });
  document.body.appendChild(box);
  // x-height of the font, page px
  const cv = document.createElement('canvas').getContext('2d');
  cv.font = cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
  const xh = cv.measureText('x').actualBoundingBoxAscent || fs * 0.52;
  // the width whose text is largest in the box, never narrower than about 12 characters a line
  let best = null;
  for (let w = Math.round(fs * 6); w <= Math.max(fs * 6, 900); w += 8) {
    box.style.width = w + 'px';
    const q = box.getBoundingClientRect();
    const s = Math.min(${fit[0]} / q.width, ${fit[1]} / q.height);
    if (!best || s > best.s + 1e-6) best = { w, s };
  }
  box.style.width = best.w + 'px';
  // shrink to the longest line, so the right padding matches the left
  const tr = document.createRange();
  tr.selectNodeContents(box);
  const right = Math.max(...[...tr.getClientRects()].map((q) => q.right));
  box.style.width = Math.ceil(right - box.getBoundingClientRect().left - pad) + 'px';
  const q = box.getBoundingClientRect();
  const inner = walk(box);
  const marks = ${JSON.stringify(finds)}.map((f) => {
    const i = inner.text.toLowerCase().indexOf(norm(f));
    if (i < 0) return null;
    const mr = document.createRange();
    mr.setStart(inner.map[i][0], inner.map[i][1]);
    const [en, eo] = inner.map[i + norm(f).length - 1];
    mr.setEnd(en, eo + 1);
    return [...mr.getClientRects()].filter((z) => z.width > 2 && z.height > 2).map((z) => [z.left + scrollX, z.top + scrollY, z.width, z.height]);
  });
  return { clip: [q.left + scrollX, q.top + scrollY, q.width, q.height], marks, xh, sentence: box.innerText, ground };
})()`;

// Fragments on one line (a link inside the sentence) become one box per line.
const lines = (rects) => {
  const out = [];
  for (const [x, y, w, h] of rects.sort((a, b) => a[1] - b[1] || a[0] - b[0])) {
    const l = out.find((o) => Math.abs(o[1] - y) < h / 2);
    if (!l) { out.push([x, y, w, h]); continue; }
    const r = Math.max(l[0] + l[2], x + w), b = Math.max(l[1] + l[3], y + h);
    l[0] = Math.min(l[0], x); l[1] = Math.min(l[1], y); l[2] = r - l[0]; l[3] = b - l[1];
  }
  return out;
};

// Every line of text the page draws inside area [x, y, w, h] (document px), as document-px boxes, and the
// pictures there (img, canvas, video, svg: their text only OCR can read). Range.getClientRects per text node,
// exact and free. Fragments join into one line only inside one block and only when they touch, so two
// columns never read as one line. Text an overflow box clips away, or that is hidden or transparent, is left out.
const TEXT = (area) => `(() => {
  const [ax, ay, aw, ah] = ${JSON.stringify(area)};
  const sx = scrollX, sy = scrollY, cut = new Map();
  const clipOf = (e) => {
    if (!e || e === document.body || e === document.documentElement) return [-1e9, -1e9, 1e9, 1e9];
    if (cut.has(e)) return cut.get(e);
    let c = clipOf(e.parentElement);
    const cs = getComputedStyle(e);
    if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') {
      const r = e.getBoundingClientRect();
      c = [Math.max(c[0], r.left), Math.max(c[1], r.top), Math.min(c[2], r.right), Math.min(c[3], r.bottom)];
    }
    cut.set(e, c);
    return c;
  };
  const blockOf = (e) => { while (e && e !== document.body && getComputedStyle(e).display.startsWith('inline')) e = e.parentElement; return e; };
  const frags = [];
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n; (n = tw.nextNode());) {
    const p = n.parentElement;
    if (!p || !n.nodeValue.trim() || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(p.tagName)) continue;
    if (p.checkVisibility && !p.checkVisibility({ opacityProperty: true, visibilityProperty: true })) continue;
    const c = clipOf(p), b = blockOf(p), r = document.createRange();
    r.selectNodeContents(n);
    for (const q of r.getClientRects()) {
      const x0 = Math.max(q.left, c[0]), y0 = Math.max(q.top, c[1]), x1 = Math.min(q.right, c[2]), y1 = Math.min(q.bottom, c[3]);
      if (x1 - x0 < 2 || y1 - y0 < 4) continue;
      if (x1 + sx <= ax || x0 + sx >= ax + aw || y1 + sy <= ay || y0 + sy >= ay + ah) continue;
      frags.push({ b, r: [x0 + sx, y0 + sy, x1 + sx, y1 + sy] });
    }
  }
  const out = [];
  for (const f of frags.sort((a, b) => a.r[1] - b.r[1] || a.r[0] - b.r[0])) {
    const [x0, y0, x1, y1] = f.r, h = y1 - y0;
    const l = out.find((o) => o.b === f.b && Math.min(o.r[3], y1) - Math.max(o.r[1], y0) > h / 2 && x0 <= o.r[2] + h && x1 >= o.r[0] - h);
    if (l) l.r = [Math.min(l.r[0], x0), Math.min(l.r[1], y0), Math.max(l.r[2], x1), Math.max(l.r[3], y1)];
    else out.push({ b: f.b, r: [...f.r] });
  }
  // a logo's word mark is a picture too: anything from a small svg up
  const images = [...document.querySelectorAll('img, canvas, video, svg')].filter((e) => !e.parentElement?.closest('svg'))
    .filter((e) => !e.checkVisibility || e.checkVisibility({ opacityProperty: true, visibilityProperty: true }))
    .map((e) => e.getBoundingClientRect()).filter((q) => q.width >= 40 && q.height >= 12)
    .map((q) => [q.left + sx, q.top + sy, q.width, q.height]).filter((q) => q[0] < ax + aw && q[0] + q[2] > ax && q[1] < ay + ah && q[1] + q[3] > ay);
  return { lines: out.map((o) => [o.r[0], o.r[1], o.r[2] - o.r[0], o.r[3] - o.r[1]].map((v) => Math.round(v * 10) / 10)),
    images: images.map((q) => q.map(Math.round)) };
})()`;

// A clip [x, y, w, h] grown (or, where that runs off the page, shrunk) so no line of text crosses its edge:
// every line wholly in the shot or wholly out. lines: document-px boxes (TEXT); max: the page's [width, height].
const snapClip = (clip, lines, max = [1e9, 1e9], pad = 4) => {
  let [x0, y0, x1, y1] = [clip[0], clip[1], clip[0] + clip[2], clip[1] + clip[3]];
  for (let i = 0; i < 6; i++) {
    let moved = false;
    for (const [lx, ly, lw, lh] of lines) {
      const lx1 = lx + lw, ly1 = ly + lh;
      if (lx1 <= x0 || lx >= x1 || ly1 <= y0 || ly >= y1) continue;          // out of the shot
      if (lx >= x0 && lx1 <= x1 && ly >= y0 && ly1 <= y1) continue;          // wholly in it
      if (ly < y0) { y0 = ly - pad >= 0 ? ly - pad : ly1 + pad; moved = true; }
      if (ly1 > y1) { y1 = ly1 + pad <= max[1] ? ly1 + pad : ly - pad; moved = true; }
      if (lx < x0) { x0 = lx - pad >= 0 ? lx - pad : lx1 + pad; moved = true; }
      if (lx1 > x1) { x1 = lx1 + pad <= max[0] ? lx1 + pad : lx - pad; moved = true; }
    }
    if (!moved) break;
  }
  return [x0, y0, x1 - x0, y1 - y0];
};

// The sticker beat: the sentence holding the first mark, alone, shot at the page's own type.
async function shootSticker(s, beat, out) {
  const finds = beat.marks.filter((mk) => mk.find).map((mk) => mk.find);
  const { result } = await s("Runtime.evaluate", { returnByValue: true,
    expression: STICKER(finds[0], finds, beat.fit || [900, 340], !!beat.keep_ground) });
  const got = result.value;
  if (!got) throw new Error(`text not found on the page: "${finds[0]}"`);
  await new Promise((r) => setTimeout(r, 150));
  const [x, y, w, h] = got.clip;
  const { data } = await s("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
    clip: { x, y, width: w, height: h, scale: 1 } });
  fs.writeFileSync(out, Buffer.from(data, "base64"));
  const png = Buffer.from(data.slice(0, 64), "base64");
  const size = [png.readUInt32BE(16), png.readUInt32BE(20)];
  const k = size[0] / w;
  const px = (r) => [r[0] - x, r[1] - y, r[2], r[3]].map((v) => Math.round(v * k));
  let fi = 0;
  const marks = beat.marks.map((mk) => {
    if (!mk.find) return mk;
    const rs = got.marks[fi++];
    if (!rs?.length) throw new Error(`"${mk.find}" is not in the sticker's sentence: "${got.sentence}"`);
    const ls = lines(rs);
    const x0 = Math.min(...ls.map((r) => r[0])), y0 = Math.min(...ls.map((r) => r[1]));
    const x1 = Math.max(...ls.map((r) => r[0] + r[2])), y1 = Math.max(...ls.map((r) => r[1] + r[3]));
    return { ...mk, rect: px([x0, y0, x1 - x0, y1 - y0]), rects: ls.map(px) };
  });
  console.log(`  sticker: "${got.sentence.replace(/\s+/g, " ")}" (x-height ${Math.round(got.xh * k)} px in the PNG)`);
  const { result: tx } = await s("Runtime.evaluate", { returnByValue: true, expression: TEXT([x, y, w, h]) });
  const lns = (tx.value?.lines || []).filter(([a, b, c, d]) => a >= x - 1 && b >= y - 1 && a + c <= x + w + 1 && b + d <= y + h + 1).map(px);
  return { size, marks, xh: Math.round(got.xh * k * 10) / 10, lines: lns };
}

async function shoot(cdp, beat, out) {
  const width = beat.width || 1000, height = beat.height || 700;
  const sticker = beat.format === "sticker" && !beat.props?.crop && (beat.marks || []).some((mk) => mk.find);
  const dsf = beat.scale || (sticker ? 3 : 2);
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const s = (m, p) => cdp.send(m, p, sessionId);
  try {
    await s("Page.enable");
    await s("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: dsf, mobile: false });
    const loaded = cdp.once("Page.loadEventFired", sessionId, 30000);
    await s("Page.navigate", { url: beat.url });
    if (!(await loaded)) console.error(`  ${beat.url}: no load event after 30 s, shooting anyway`);
    await new Promise((r) => setTimeout(r, beat.wait_ms ?? 2500));
    // twice: some consent managers load after the page does
    for (let i = 0; i < 2; i++) {
      await s("Runtime.evaluate", { expression: DISMISS });
      await new Promise((r) => setTimeout(r, 700));
    }
    let clip = { x: 0, y: 0, width, height };
    if (sticker) return await shootSticker(s, beat, out);
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
    // The text's line boxes: the first place it appears at or below the clip's top (inside the clip
    // first), else the first place at all.
    const find = async (text) => {
      const { result } = await s("Runtime.evaluate", { returnByValue: true, expression: FIND(text) });
      if (!result.value?.length) throw new Error(`text not found on the page: "${text}"`);
      const top = (rs) => Math.min(...rs.map((r) => r[1]));
      const inClip = (rs) => top(rs) >= clip.y && top(rs) < clip.y + clip.height;
      const hit = result.value.find(inClip) || result.value.find((rs) => top(rs) >= clip.y) || result.value[0];
      return lines(hit);
    };
    // Marks given by "find": the text's line boxes on the page. The shot reaches down past the lowest.
    const marks = [];
    for (const mk of beat.marks || []) {
      if (!mk.find) { marks.push(mk); continue; }
      const rs = await find(mk.find);
      const x0 = Math.min(...rs.map((r) => r[0])), y0 = Math.min(...rs.map((r) => r[1]));
      const x1 = Math.max(...rs.map((r) => r[0] + r[2])), y1 = Math.max(...rs.map((r) => r[1] + r[3]));
      const pad = 6;
      marks.push({ ...mk, page_rect: [x0 - pad, y0 - pad, x1 - x0 + pad * 2, y1 - y0 + pad * 2], page_rects: rs });
      clip.height = Math.min(Math.max(clip.height, y1 + 140 - clip.y), 3200);
    }
    if (beat.page_text) {
      // the visible text, one line per block, for the planner's highlight pick (route.py highlight)
      const { result } = await s("Runtime.evaluate", { returnByValue: true, expression: `(() => [...document.querySelectorAll(
        'h1,h2,h3,h4,p,li,blockquote,td,dd')].map((e) => e.innerText.replace(/\\s+/g, ' ').trim())
        .filter((t) => t.length > 20 && t.length < 400).slice(0, 120))()` });
      fs.writeFileSync(out.replace(/\.png$/, ".text.json"), JSON.stringify(result.value || [], null, 1));
    }
    let highlight, hrs;
    if (beat.highlight) {
      hrs = await find(beat.highlight);
      const bottom = Math.max(...hrs.map((r) => r[1] + r[3]));
      // Shoot from the clip's top down past the sentence, so the card can travel to it. Capped: a
      // screenshot taller than this is mostly scroll nobody reads.
      clip.height = Math.min(Math.max(clip.height, bottom + 140 - clip.y), 3200);
    }
    // no line of text cut by the shot's edge: the clip grows to take a crossing line whole (or drops it)
    const ev = async (expression) => (await s("Runtime.evaluate", { returnByValue: true, expression })).result.value;
    const page = await ev("[document.documentElement.scrollWidth, document.documentElement.scrollHeight]");
    const near = await ev(TEXT([clip.x - 400, clip.y - 400, clip.width + 800, clip.height + 800]));
    [clip.x, clip.y, clip.width, clip.height] = snapClip([clip.x, clip.y, clip.width, clip.height], near?.lines || [], [page[0], Math.min(page[1], clip.y + 3300)]);
    if (hrs) {
      highlight = { rects: hrs.map(([x, y, w, h]) => [(x - clip.x) / clip.width, (y - clip.y) / clip.height,
        w / clip.width, h / clip.height].map((v) => Math.round(v * 10000) / 10000)) };
      if (hrs.some((r) => r[1] + r[3] > clip.y + clip.height)) console.error(`  ${beat.url}: highlight runs past 3200 px, cut off`);
    }
    const { data } = await s("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      clip: { ...clip, scale: 1 } });
    fs.writeFileSync(out, Buffer.from(data, "base64"));
    // The PNG's own size (IHDR), so the card can fit it at its own ratio.
    const png = Buffer.from(data.slice(0, 64), "base64");
    const size = [png.readUInt32BE(16), png.readUInt32BE(20)];
    // page px -> the PNG's own px (deviceScaleFactor), relative to the clip
    const k = size[0] / clip.width;
    for (const mk of marks) {
      if (!mk.page_rect) continue;
      const [x, y, w, h] = mk.page_rect;
      mk.rect = [x - clip.x, y - clip.y, w, h].map((v) => Math.round(v * k));
      // one box per line, so a highlight sits on the words and not on the block around them
      mk.rects = mk.page_rects.map(([a, b, c, d]) => [a - clip.x, b - clip.y, c, d].map((v) => Math.round(v * k)));
      delete mk.page_rect;
      delete mk.page_rects;
    }
    // the text's line boxes in the PNG's px: a card's crop keeps each line whole (plan.py whole_lines)
    const lns = (near?.lines || []).filter(([x, y, w, h]) => x >= clip.x && y >= clip.y && x + w <= clip.x + clip.width && y + h <= clip.y + clip.height)
      .map(([x, y, w, h]) => [x - clip.x, y - clip.y, w, h].map((v) => Math.round(v * k)));
    return { highlight, size, marks, lines: lns };
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
    const si = slug(brand).replace(/-/g, "");
    // cdn.simpleicons.org serves the brand colour but refuses some networks (cloud machines, some
    // offices); the same icon set on jsDelivr always answers, in black.
    const tries = [[`https://cdn.simpleicons.org/${si}`, "svg"],
      [`https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/${si}.svg`, "svg"]];
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

// ---------- free sources, no keys ----------
// The size of a PNG or JPEG from its header.
const imageSize = (b) => {
  if (b.readUInt32BE(0) === 0x89504e47) return [b.readUInt32BE(16), b.readUInt32BE(20)];
  for (let i = 2; i < b.length - 9;) {
    if (b[i] !== 0xff) { i++; continue; }
    const m = b[i + 1], len = b.readUInt16BE(i + 2);
    if (m >= 0xc0 && m <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(m)) return [b.readUInt16BE(i + 7), b.readUInt16BE(i + 5)];
    i += 2 + len;
  }
  return null;
};
const get = async (url, as = "buf") => {
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 ai-video-editor" } }).catch(() => null);
  if (!r || !r.ok) return null;
  return as === "json" ? r.json() : Buffer.from(await r.arrayBuffer());
};
const norm = (t) => (t || "").replace(/https:\/\/t\.co\/\w+/g, "").replace(/\s+/g, " ").trim().toLowerCase();
const short = (n) => n == null ? undefined : n >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${+(n / 1e3).toFixed(1)}K` : `${n}`;
// X's public embed endpoint: the token is derived from the id (as the embed widget does it).
const xToken = (id) => ((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\.)/g, "");

// One beat of a free source -> files in images/, and for image sources an images.json card.
async function source(edit, b) {
  const save = (rel, buf) => { fs.writeFileSync(path.join(edit, rel), buf); return rel; };
  if (b.kind === "post") {
    const id = b.id || (b.url || "").match(/status(?:es)?\/(\d+)/)?.[1];
    if (!id) throw new Error(`post beat '${b.word}': no status id in url`);
    let d = null;
    for (const token of [xToken(id), "a"]) {
      d = await get(`https://cdn.syndication.twimg.com/tweet-result?id=${id}&token=${token}&lang=en`, "json").catch(() => null);
      if (d?.text) break;
    }
    if (!d?.text) throw new Error(`X post ${id}: the embed endpoint returned nothing (deleted, private or rate limited)`);
    const text = d.text.replace(/\s*https:\/\/t\.co\/\w+\s*$/g, "").trim();
    for (const k of ["text", "highlight"]) {
      if (b[k] && !norm(text).includes(norm(b[k]))) throw new Error(`X post ${id}: "${b[k]}" is not in the post. It reads: "${text}"`);
    }
    const avatar = d.user?.profile_image_url_https && await get(d.user.profile_image_url_https.replace("_normal", "_400x400"));
    const post = { platform: "x", name: d.user?.name, handle: `@${d.user?.screen_name}`, text, likes: short(d.favorite_count),
      replies: short(d.conversation_count), time: d.created_at?.slice(0, 10), url: `https://x.com/${d.user?.screen_name}/status/${id}` };
    if (b.highlight) post.highlight = b.highlight;
    if (avatar) post.avatar = save(`images/avatar-${id}.jpg`, avatar);
    save(`images/post-${id}.json`, JSON.stringify(post, null, 1));
    console.log(`images/post-${id}.json  <- ${post.url} (text verified)`);
    return null;
  }
  if (b.kind === "app") {
    const id = b.app_id || (b.url || "").match(/id(\d+)/)?.[1];
    const d = id && await get(`https://itunes.apple.com/lookup?id=${id}`, "json");
    const app = d?.results?.[0];
    if (!app) throw new Error(`App Store id ${id}: not found`);
    const logo = logoPath(b.brand || b.word, "png");
    const icon = await get(app.artworkUrl512 || app.artworkUrl100);
    if (icon && !fs.existsSync(path.join(edit, logo))) console.log(`${save(logo, icon)}  <- App Store icon`);
    save(`images/app-${id}.json`, JSON.stringify({ name: app.trackName, seller: app.sellerName, rating: app.averageUserRating,
      ratings: app.userRatingCount, price: app.formattedPrice, url: app.trackViewUrl }, null, 1));
    const shot = (app.screenshotUrls || [])[b.screenshot ?? 0] || (app.ipadScreenshotUrls || [])[0];
    if (!shot) return null;
    // the lookup lists a 392 px thumbnail; the same path serves the full size
    const buf = await get(shot.replace(/\/\d+x\d+bb\.(png|jpg)$/, "/1290x0w.png")) || await get(shot);
    return buf && { src: save(`${PREFIX}app-${id}.${shot.endsWith(".png") ? "png" : "jpg"}`, buf), size: imageSize(buf), from: app.trackViewUrl };
  }
  if (b.kind === "youtube") {
    const id = b.id || (b.url || "").match(/(?:v=|youtu\.be\/|shorts\/|embed\/)([\w-]{11})/)?.[1];
    if (!id) throw new Error(`youtube beat '${b.word}': no video id`);
    for (const q of ["maxresdefault", "sddefault", "hqdefault"]) {
      const buf = await get(`https://i.ytimg.com/vi/${id}/${q}.jpg`);
      // a missing size comes back as a 120x90 grey placeholder
      if (buf && imageSize(buf)?.[0] > 120) return { src: save(`${PREFIX}yt-${id}.jpg`, buf), size: imageSize(buf), from: `i.ytimg.com ${q}` };
    }
    throw new Error(`YouTube ${id}: no thumbnail`);
  }
  if (b.kind === "github") {
    const repo = b.repo || (b.url || "").match(/github\.com\/([\w.-]+\/[\w.-]+)/)?.[1];
    if (!repo) throw new Error(`github beat '${b.word}': no owner/repo`);
    const buf = await get(`https://opengraph.githubassets.com/1/${repo}`);
    if (!buf) throw new Error(`GitHub ${repo}: no social card`);
    return { src: save(`${PREFIX}gh-${slug(repo)}.png`, buf), size: imageSize(buf), from: `github.com/${repo}` };
  }
  return null;
}
const SOURCES = ["post", "app", "youtube", "github"];

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
  const listPath = path.join(edit, "images.json");
  // Keep the user's own images; replace captures from an earlier run.
  const images = (fs.existsSync(listPath) ? JSON.parse(fs.readFileSync(listPath, "utf8")) : [])
    .filter((im) => !im.src.startsWith(PREFIX));
  for (const b of visuals.filter((v) => SOURCES.includes(v.kind))) {
    try {
      const got = await source(edit, b);
      if (!got) continue;
      const im = { src: got.src, word: b.word, size: got.size };
      for (const k of ["nth", "box", "hold_s", "entrance", "layout", "marks"]) if (b[k] !== undefined) im[k] = b[k];
      images.push(im);
      console.log(`${got.src}  <- ${got.from}`);
    } catch (e) {
      failed++;
      console.error(`  failed ${b.kind} '${b.word}': ${e.message}`);
    }
  }
  const beats = visuals.filter((v) => v.kind === "capture");
  if (!beats.length) {
    fs.writeFileSync(listPath, JSON.stringify(images, null, 1));
    process.exit(failed ? 1 : 0);
  }
  const bin = findBinary(SHELLS);
  if (!bin) {
    console.error(`ERROR: no Chrome Headless Shell under ${SHELLS}. Run edit.py stills once (it installs the renderer).`);
    process.exit(1);
  }
  const cdp = launch(bin);
  try {
    for (const [i, b] of beats.entries()) {
      const src = `${PREFIX}${i + 1}-${slug(b.word)}.png`;
      let shot;
      try {
        shot = await shoot(cdp, b, path.join(edit, src));
      } catch (e) {
        failed++;
        console.error(`  failed ${b.url}: ${e.message}`);
        continue;
      }
      const im = { src, word: b.word, size: shot.size };
      for (const k of ["nth", "box", "hold_s", "entrance", "layout"]) if (b[k] !== undefined) im[k] = b[k];
      if (shot.highlight) im.highlight = shot.highlight;
      if (shot.marks.length) im.marks = shot.marks;
      if (shot.xh) im.xh = shot.xh;
      if (shot.lines?.length) im.lines = shot.lines;
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

// Imported by product-video/scripts/crawl.mjs for the browser, banner and text-finding helpers.
export { launch, findBinary, SHELLS, DISMISS, FIND, lines, TEXT, snapClip, noSandbox, sandboxFlags };
if (path.basename(process.argv[1] || "") === "capture.mjs") await main();
