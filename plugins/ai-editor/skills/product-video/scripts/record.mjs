// Records real click-throughs of a website: headless Chrome does the clicks, the typing, the scrolls and
// the hovers, and the screen is captured as it really animates (CDP Page.startScreencast), with a real
// arrow cursor drawn in the page that turns into a hand over links, exactly as the page's own CSS says.
//
//   node record.mjs <dir> [flows.json] [--only <id>] [--cookies cookies.json]
//
// <dir>/flows.json (written by Claude from use-cases.md; references/story.md "Flows"):
//   {"viewport": [1440, 900], "flows": [{"id": "pick-project", "url": "https://...", "steps": [
//     {"wait": 0.6}, {"move": "text=Projects"}, {"click": "text=Build a Second Brain"}, {"scroll": 500},
//     {"type": "input[placeholder*=Search]", "text": "claude"}, {"key": "Enter"}, {"hover": "css or text=..."},
//     {"key": "Meta+k"}, {"write": "github"}, {"goto": "https://..."}]}]}
// A target is "text=<words on the page>" (the smallest visible element holding them, links and buttons
// first) or a CSS selector. Writes <dir>/flows/<id>.mp4 (30 fps, 2x) and <id>.json: the cursor path, every
// step's time and the rect it acted on (viewport px), which the camera follows.
// Public pages only by default; a logged-in page only with the user's own cookies file.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const { findBinary, SHELLS, DISMISS } = await import(path.join(HERE, "../../style-edit/scripts/capture.mjs"));
const { chromeBinary, hasProfile, profileFor, FLAGS } = await import(path.join(HERE, "login.mjs"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const args = process.argv.slice(2);
const flag = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const [dir, flowsArg] = args.filter((a, i) => !a.startsWith("--") && !args[i - 1]?.startsWith("--"));
if (!dir) { console.error("usage: node record.mjs <dir> [flows.json] [--only id] [--cookies file]"); process.exit(2); }
const spec = JSON.parse(fs.readFileSync(flowsArg || path.join(dir, "flows.json"), "utf8"));
// --mobile: the same flows on the site's real phone layout (430x932 @3x), for 9:16 films; files get "-m"
const MOBILE = args.includes("--mobile");
const [W, H] = MOBILE ? [430, 932] : spec.viewport || [1440, 900];
// --states: no screencast. Each step's UI state is captured as a still at 3x (before, after, the typed field,
// the page down to where a scroll goes) and the film animates between them, so every frame is rendered.
const STATES = args.includes("--states");
const DSF = MOBILE || STATES ? 3 : 2, FPS = 30, SUFFIX = MOBILE ? "-m" : "";

// A DevTools client over the pipe that also hands every event to listeners (screencast frames).
// A logged-in profile (login.mjs) is used when one exists for the domain: the installed Chrome, headless,
// on that profile, which is never deleted here. Otherwise the headless shell on a throwaway profile.
function chrome(bin, logged) {
  const profile = logged || fs.mkdtempSync(path.join(os.tmpdir(), "ai-editor-record-"));
  const proc = spawn(logged ? chromeBinary() : bin, ["--remote-debugging-pipe", "--no-first-run", "--hide-scrollbars", "--mute-audio",
    ...(logged ? [...FLAGS, "--headless=new"] : []),
    ...(process.platform === "linux" ? ["--no-sandbox", "--disable-dev-shm-usage"] : []), `--user-data-dir=${profile}`, "about:blank"],
    { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
  let id = 0, buf = "";
  const waiting = new Map(), listeners = new Set();
  proc.stdio[4].on("data", (d) => {
    buf += d.toString();
    for (let i; (i = buf.indexOf("\0")) >= 0;) {
      const m = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1);
      if (m.id && waiting.has(m.id)) { const [ok, fail] = waiting.get(m.id); waiting.delete(m.id); m.error ? fail(new Error(m.error.message)) : ok(m.result); }
      else for (const l of listeners) l(m);
    }
  });
  const send = (method, params = {}, sessionId) => new Promise((ok, fail) => {
    waiting.set(++id, [ok, fail]); proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0"); });
  const close = () => { proc.kill(); if (!logged) try { fs.rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 }); } catch {} };
  return { send, listeners, close };
}

// The cursor, in the page: macOS arrow, a hand where the page sets cursor: pointer, a soft press on click.
// It follows real mouse events, so hover states and the cursor always agree.
const CURSOR = `(() => {
  if (window.__aiCursor) return; window.__aiCursor = true;
  const TOUCH = ${MOBILE};
  const make = () => {
    if (!document.body) return requestAnimationFrame(make);
    const c = document.createElement('div');
    c.style.cssText = 'position:fixed;left:0;top:0;width:28px;height:40px;z-index:2147483647;pointer-events:none;transform-origin:3px 2px;transition:transform 90ms ease-out;will-change:left,top';
    const arrow = '<svg width="28" height="40" viewBox="0 0 28 40" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))"><path d="M3 2 L3 31 L10 24.5 L14.6 35.2 L19.4 33.2 L14.8 22.6 L24 22.6 Z" fill="#111" stroke="#fff" stroke-width="2.2" stroke-linejoin="round"/></svg>';
    const hand = '<svg width="28" height="40" viewBox="-2 0 30 36" style="filter:drop-shadow(0 2px 3px rgba(0,0,0,.35))"><path d="M9 3.5c0-1.4 1-2.5 2.3-2.5S13.6 2.1 13.6 3.5V13l.6-.2c1.3-.4 2.6.3 2.9 1.5l.2.6.5-.2c1.3-.4 2.6.3 2.9 1.5l.1.5.4-.1c1.3-.3 2.6.5 2.8 1.8l.8 6c.3 2.4-.4 4.8-1.9 6.7L21 33H10.2l-5.3-8.6c-.7-1.2-.4-2.7.7-3.4 1.1-.7 2.5-.4 3.3.6L9 22V3.5z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    // on a phone there is no arrow: a soft fingertip that presses
    const finger = '<div style="width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;background:rgba(120,120,120,.28);border:2px solid rgba(255,255,255,.85);box-shadow:0 2px 10px rgba(0,0,0,.25)"></div>';
    c.innerHTML = TOUCH ? finger : arrow; c.dataset.k = TOUCH ? 'finger' : 'arrow'; c.style.left = '-60px'; document.documentElement.appendChild(c);
    const at = (e) => { c.style.left = (e.clientX - (c.dataset.k === 'hand' ? 9 : 3)) + 'px'; c.style.top = (e.clientY - 2) + 'px';
      if (TOUCH) { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; return; }
      const t = document.elementFromPoint(e.clientX, e.clientY); const k = t && getComputedStyle(t).cursor === 'pointer' ? 'hand' : 'arrow';
      if (k !== c.dataset.k) { c.innerHTML = k === 'hand' ? hand : arrow; c.dataset.k = k; } };
    addEventListener('mousemove', at, true);
    // a fingertip shows only while it touches; an arrow is always there
    if (TOUCH) { c.style.opacity = '0'; c.style.transition = 'opacity 160ms ease-out, transform 90ms ease-out'; }
    addEventListener('mousedown', () => { c.style.transform = 'scale(0.86)'; if (TOUCH) c.style.opacity = '1'; }, true);
    addEventListener('mouseup', () => { c.style.transform = 'scale(1)'; if (TOUCH) setTimeout(() => { c.style.opacity = '0'; }, 260); }, true);
  };
  make();
})()`;

// Never pressed while recording, whatever a flow says, unless the step carries "allow": true (which the
// skill sets only after asking the user): anything that creates, deletes, pays, upgrades, publishes or invites.
const DENY = /\b(create|delete|remove|destroy|erase|pay|purchase|buy|checkout|upgrade|subscribe|billing|cancel (plan|subscription)|publish|send invites?|invite|transfer|deactivate|close account|log ?out|sign ?out)\b/i;

// Personal data blurred in the page itself, before the frame is captured: email addresses, the names
// and words the flow lists, avatars, billing panels, email fields. window.__aiBlurHits says what.
const BLUR = (cfg) => `(() => {
  const cfg = ${JSON.stringify(cfg)};
  const email = /[\\w.+-]+@[\\w-]+\\.[\\w.]+/;
  window.__aiBlurHits = window.__aiBlurHits || [];
  // strong enough for the size: a big heading or a large avatar stays unreadable even zoomed in on a 3x capture
  const hit = (el, why) => { if (!el || el.dataset.aiBlur) return; el.dataset.aiBlur = '1';
    const r = el.getBoundingClientRect(), fs = parseFloat(getComputedStyle(el).fontSize) || 14;
    el.style.filter = 'blur(' + Math.round(Math.max(8, fs * 0.55, Math.min(r.width, r.height) * 0.22)) + 'px)'; window.__aiBlurHits.push(why.slice(0, 60)); };
  const run = () => {
    const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const words = cfg.text.filter(Boolean).map((x) => x.toLowerCase());
    for (let n; (n = w.nextNode());) { const t = n.nodeValue || '', tl = t.toLowerCase();
      if (email.test(t)) hit(n.parentElement, 'email: ' + t.trim());
      else for (const x of words) if (tl.includes(x)) { hit(n.parentElement, 'listed: ' + x); break; } }
    for (const sel of cfg.selectors) for (const el of document.querySelectorAll(sel)) hit(el, 'selector ' + sel);
    for (const el of document.querySelectorAll('input')) if (email.test(el.value || '')) hit(el, 'email field');
    // avatars: any round picture of a person-sized box (a profile photo, a stack of completer faces)
    for (const el of document.querySelectorAll('img, [style*=background-image]')) { const r = el.getBoundingClientRect();
      if (r.width >= 16 && r.width <= 240 && Math.abs(r.width - r.height) < 4 && parseFloat(getComputedStyle(el).borderRadius) >= r.width * 0.4) hit(el, 'round avatar'); }
    for (const el of document.querySelectorAll('img[alt]')) if (words.some((x) => el.alt.toLowerCase().includes(x))) hit(el, 'avatar alt');
    // a portfolio or profile page: its owner's name heading, unless the user chose to show names
    // (a profile root: /portfolio/<handle>, /u/<handle>/library, /@handle; not the deeper pages people publish under it)
    if (!cfg.show_names && /^\\/((portfolio|profile|users?|u|people|members?)\\/[^/]+(\\/[a-z-]{1,20})?|@[^/]+)\\/?$/i.test(location.pathname)) {
      const el = [...document.querySelectorAll('h1, h2')].find((e) => e.getBoundingClientRect().top < innerHeight * 0.6);
      if (el && /^[A-Z][\\w'.-]+( [A-Z][\\w'.-]+){0,3}$/.test((el.innerText || '').trim())) hit(el, 'profile name'); }
  };
  if (!window.__aiBlurObs) { window.__aiBlurObs = new MutationObserver(() => { clearTimeout(window.__aiBlurT); window.__aiBlurT = setTimeout(run, 30); });
    const go = () => document.body ? (run(), window.__aiBlurObs.observe(document.body, { childList: true, subtree: true, characterData: true })) : requestAnimationFrame(go); go(); }
  else run();
  return window.__aiBlurHits;
})()`;

// The element a target names, scrolled into view smoothly when it is off screen; its viewport rect.
const FINDEL = (target) => `(async () => {
  const want = ${JSON.stringify(target)};
  const vis = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  // off to the side counts only inside a strip that scrolls sideways (a row of tabs on a phone)
  const side = (e) => { const r = e.getBoundingClientRect(); return r.right <= 0 || r.left >= innerWidth; };
  const strip = (e) => { for (let p = e.parentElement; p; p = p.parentElement) if (p.scrollWidth > p.clientWidth + 8 && /auto|scroll/.test(getComputedStyle(p).overflowX)) return true; return false; };
  let el = null;
  if (want.startsWith('text=')) {
    const t = want.slice(5).replace(/\\s+/g, ' ').trim().toLowerCase();
    const all = [...document.querySelectorAll('a, button, [role], input, textarea, summary, label, h1, h2, h3, h4, li, p, span, div')]
      .filter((e) => vis(e) && (!side(e) || strip(e)) && (e.innerText || e.placeholder || e.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().toLowerCase().includes(t));
    const rank = (e) => (/^(A|BUTTON|INPUT|TEXTAREA|SUMMARY)$/.test(e.tagName) || e.getAttribute('role') ? 0 : 1);
    const said = (e) => (e.innerText || e.placeholder || e.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    // the exact words first (a "Create" button before "Create a Docker Container"), then controls, then the shortest
    // with a dialog open, what a person clicks is in the dialog
    const modal = (e) => (e.closest('[role=dialog], [aria-modal=true], dialog[open], [role=listbox]') ? 0 : 1);
    all.sort((a, b) => side(a) - side(b) || modal(a) - modal(b) || (said(a) !== t) - (said(b) !== t) || rank(a) - rank(b) || (a.innerText || '').length - (b.innerText || '').length);
    el = all[0] || null;
  } else el = [...document.querySelectorAll(want)].find((e) => vis(e) && !side(e)) || [...document.querySelectorAll(want)].find((e) => vis(e) && strip(e)) || null;
  if (!el) return null;
  let r = el.getBoundingClientRect();
  if (r.top < 70 || r.bottom > innerHeight - 40 || r.left < 0 || r.right > innerWidth) {
    // the page's own scroller, whichever element it is, scrolled smoothly (sideways too: a strip of tabs)
    const r0 = r;
    el.scrollIntoView({ behavior: 'smooth', block: r.top < 70 || r.bottom > innerHeight - 40 ? 'center' : 'nearest', inline: 'center' });
    await new Promise((d) => setTimeout(d, 1100));
    r = el.getBoundingClientRect();
    window.__aiMoved = Math.abs(r.left - r0.left) + Math.abs(r.top - r0.top) > 2;
  }
  return [r.left, r.top, r.width, r.height].map(Math.round);
})()`;

// Who is logged in: the profile link (labelled "your library / profile / account", or wrapping an avatar), its
// URL's own segment as the handle, and that page's name heading or the avatar's alt text as the name.
const WHO = `(() => {
  const lab = /\\b(your|my)\\s+(library|profile|account|portfolio|page)\\b|^(profile|account|me)$/i;
  // the account's own control: one labelled as yours first, else a link wrapping an avatar; names come only from it
  const all = [...document.querySelectorAll('a[href], button, [role=button]')];
  const label = (a) => (a.getAttribute('aria-label') || a.title || a.innerText || '').trim();
  const me = all.find((a) => lab.test(label(a))) || all.find((a) => { const img = a.querySelector('img');
    return img && /avatar|profile|user/i.test(img.className + ' ' + a.className); });
  let profile = null, button = false; const names = [];
  if (me) {
    if (me.href) profile = me.href; else { button = true; me.dataset.aiMe = '1'; }
    const img = me.querySelector('img');
    if (img && img.alt && !/avatar|profile|user|logo|picture|photo/i.test(img.alt)) names.push(img.alt.trim());
  }
  for (const el of document.querySelectorAll('[class*=username i], [class*=user-name i], [class*=display-name i], [class*=displayname i], [class*=profile-name i]')) {
    if (el.closest('header, nav, [role=banner]')) { const t = (el.innerText || '').trim(); if (t && t.length < 40) names.push(t); } }
  return { profile, button, names };
})()`;
const HEADNAME = `(() => [...document.querySelectorAll('h1, h2')].map((e) => (e.innerText || '').trim())
  .find((t) => /^[A-Z][\\w'.-]+( [A-Z][\\w'.-]+){0,3}$/.test(t)) || null)()`;
const STOP = new Set(["portfolio", "profile", "user", "users", "u", "library", "account", "settings", "me", "people", "members", "member", "home", "dashboard", "app"]);
export async function whoami(cdp, url) {
  const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
  const ev = async (expression) => (await cdp.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true }, sessionId)).result.value;
  const go = async (u) => { await cdp.send("Page.navigate", { url: u }, sessionId); await sleep(5000); };
  try {
    await cdp.send("Page.enable", {}, sessionId);
    await go(url);
    const w = (await ev(WHO)) || { names: [] };
    let handle = null, head = null;
    if (!w.profile && w.button) {   // a profile button with no link (a menu or a client-side route): press it, read where it went
      await ev("document.querySelector('[data-ai-me]').click(), true"); await sleep(4000);
      const at = await ev("location.href");
      if (at && at !== url && new URL(at).pathname !== new URL(url).pathname) w.profile = at;
    }
    if (w.profile) {
      handle = new URL(w.profile).pathname.split("/").map((x) => decodeURIComponent(x).replace(/^@/, "")).find((x) => x && !STOP.has(x.toLowerCase()) && !/^[0-9a-f-]{16,}$/i.test(x)) || null;
      await go(w.profile);
      head = await ev(HEADNAME);
    }
    const names = [...new Set([...w.names, head].filter(Boolean))];
    const tokens = [...new Set([...names, ...names.flatMap((n) => n.split(/\s+/).filter((x) => x.length >= 3)), ...(handle ? [handle] : [])])];
    return { names, handle, tokens };
  } finally { await cdp.send("Target.closeTarget", { targetId }).catch(() => {}); }
}

// A key or a chord: "Enter", "Escape", "ArrowDown", "Meta+k", "Control+Shift+p" (modifiers held, as a hand does).
async function pressKey(s, chord) {
  const parts = chord.split("+"), key = parts.pop();
  const MOD = { Alt: 1, Control: 2, Meta: 4, Shift: 8 };
  const mods = parts.reduce((m, k) => m | (MOD[k] || 0), 0);
  const VK = { Enter: 13, Escape: 27, Tab: 9, ArrowDown: 40, ArrowUp: 38, Backspace: 8 };
  const code = key.length === 1 ? `Key${key.toUpperCase()}` : key;
  const vk = VK[key] || (key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0);
  for (const k of parts) await s("Input.dispatchKeyEvent", { type: "rawKeyDown", key: k, code: k + "Left", modifiers: mods, windowsVirtualKeyCode: { Alt: 18, Control: 17, Meta: 91, Shift: 16 }[k] });
  await sleep(parts.length ? 120 : 0);
  await s("Input.dispatchKeyEvent", { type: "rawKeyDown", key, code, modifiers: mods, windowsVirtualKeyCode: vk });
  if (!mods && (key === "Enter" || key.length === 1)) await s("Input.dispatchKeyEvent", { type: "char", key, text: key === "Enter" ? "\r" : key, modifiers: 0 });
  await s("Input.dispatchKeyEvent", { type: "keyUp", key, code, modifiers: mods, windowsVirtualKeyCode: vk });
  for (const k of parts.reverse()) await s("Input.dispatchKeyEvent", { type: "keyUp", key: k, code: k + "Left", modifiers: 0 });
}

// Where each typed character leaves the caret in the focused field (wrapping like a textarea), measured
// with the field's own font: the film reveals the real typed text up to it, frame by frame.
const CARET = (text) => `(() => {
  const e = document.activeElement; if (!e) return null;
  const cs = getComputedStyle(e), r = e.getBoundingClientRect(), n = (v) => parseFloat(v) || 0;
  const c = document.createElement('canvas').getContext('2d');
  c.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
  const text = ${JSON.stringify(text)};
  const left = r.left + n(cs.paddingLeft) + n(cs.borderLeftWidth), top = r.top + n(cs.paddingTop) + n(cs.borderTopWidth);
  const width = r.width - n(cs.paddingLeft) - n(cs.paddingRight) - n(cs.borderLeftWidth) - n(cs.borderRightWidth);
  const lh = n(cs.lineHeight) || n(cs.fontSize) * 1.25;
  const multi = e.tagName === 'TEXTAREA' || e.isContentEditable;
  const pos = [[0, 0]]; let ls = 0, line = 0;
  for (let i = 1; i <= text.length; i++) {
    let w = c.measureText(text.slice(ls, i)).width;
    if (multi && w > width) { const sp = text.lastIndexOf(' ', i - 1); if (sp > ls) { ls = sp + 1; line++; w = c.measureText(text.slice(ls, i)).width; } }
    pos.push([Math.round(w * 10) / 10, line]);
  }
  // a single-line field centres its text vertically
  const y = multi ? top : r.top + (r.height - lh) / 2;
  return { left, top: y, width, lh, pos, color: cs.color, size: n(cs.fontSize) };
})()`;

// The element that really scrolls: the document, or an app shell's inner scroller.
const SCROLLER = `([...document.querySelectorAll('main, div, section, article')].find((e) => e.scrollHeight > e.clientHeight + 40
  && /auto|scroll/.test(getComputedStyle(e).overflowY) && e.clientHeight > innerHeight * 0.5) || document.scrollingElement)`;
const EXPAND = `(() => {
  const el = ${SCROLLER};
  if (el === document.scrollingElement) return null;
  const s0 = el.scrollTop, kid = el.firstElementChild; window.__aiExp = [];
  for (let e = el; e; e = e.parentElement) { window.__aiExp.push([e, e.getAttribute('style')]);
    e.style.overflow = 'visible'; e.style.height = 'auto'; e.style.maxHeight = 'none'; }
  if (kid) { window.__aiExp.push([kid, kid.getAttribute('style')]); kid.style.marginTop = (-s0) + 'px'; }
  return s0;
})()`;
const RESTORE = `(() => { for (const [e, st] of (window.__aiExp || []).reverse()) { if (st == null) e.removeAttribute('style'); else e.setAttribute('style', st); }
  window.__aiExp = null; return true; })()`;

// Is the view finished loading? Pictures in view decoded, no skeleton placeholders, the text no longer changing.
const READY = `(() => {
  const inView = (e) => { const r = e.getBoundingClientRect(); return r.width > 4 && r.height > 4 && r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth; };
  const pending = [...document.images].filter((i) => inView(i) && (!i.complete || i.naturalWidth === 0) && i.loading !== 'lazy-hidden').length;
  const skel = [...document.querySelectorAll('[class*=skeleton i], [class*=animate-pulse], [class*=shimmer i], [aria-busy=true]')].some(inView);
  return { pending, skel, text: (document.body.innerText || '').length };
})()`;

// The flow as UI states, for the rendered (not recorded) film. Writes flows/<id>.states.json:
//   plates: one per page the flow visits (its URL); states: stills at 3x placed on a plate at a scroll
//   offset y; steps: what the hand did, the rect it acted on (plate px), and the state before and after.
async function captureStates(flow, s, ev, waitFor, settle, bcfg, out) {
  const sdir = path.join(out, "states");
  fs.mkdirSync(sdir, { recursive: true });
  const id = flow.id + SUFFIX;
  // this take's old stills only (a desktop take never deletes the phone take's, "<id>-m-...")
  for (const f of fs.readdirSync(sdir)) if (new RegExp(`^${id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}-\\d\\d-`).test(f)) fs.rmSync(path.join(sdir, f));
  const st = { id, url: flow.url, viewport: [W, H], dsf: DSF, mobile: MOBILE, plates: [], states: [], steps: [] };
  let plate = 0, off = 0, n = 0, cur;
  const sy = () => ev("Math.round(document.scrollingElement ? document.scrollingElement.scrollTop : scrollY)");
  const shoot = async (file, clip) => {
    const { data } = await s("Page.captureScreenshot", { format: "jpeg", quality: 92, ...(clip ? { clip: { ...clip, scale: 1 }, captureBeyondViewport: true } : {}) });
    fs.writeFileSync(path.join(sdir, file), Buffer.from(data, "base64"));
  };
  const snap = async (tag, size = [W, H], clip) => {
    await ready();
    const f = `${id}-${String(n++).padStart(2, "0")}-${tag}.jpg`;
    if (bcfg) await ev(BLUR(bcfg));
    await shoot(f, clip);
    st.states.push({ src: `flows/states/${f}`, plate, y: off, size, tag });
    return st.states.length - 1;
  };
  // a state is taken only once the view has finished loading (at most 8 s)
  const ready = async () => {
    let last = -1, same = 0;
    for (let i = 0; i < 32; i++) {
      const r = await ev(READY);
      same = r.text === last ? same + 1 : 0; last = r.text;
      if (!r.pending && !r.skel && same >= 2) return;
      await sleep(250);
    }
    console.error(`  WARN ${flow.id}: the view was still loading after 8 s; captured as it was`);
  };
  const newPlate = async () => { st.plates.push({ url: await ev("location.href") }); plate = st.plates.length - 1; off = 0; };
  const rectOf = async (t) => {
    const y0 = await sy();
    await ev("window.__aiMoved = false");
    const r = await ev(FINDEL(t));
    if (!r) throw new Error(`flow ${flow.id}: nothing on the page matches ${JSON.stringify(t)}`);
    const dy = (await sy()) - y0;
    if (dy || await ev("window.__aiMoved")) {
      const from = cur; off += dy; cur = await snap("into-view");
      st.steps.push({ kind: "scroll", dy, from, to: cur, auto: true });
    }
    return [r[0], r[1] + off, r[2], r[3]];
  };
  await newPlate();
  cur = await snap("start");
  // the page's own headline (an h1, else the biggest type in view): the film's opening never crops it
  st.headline = await ev(`(() => { const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 10 && r.top >= 0 && r.bottom <= innerHeight; };
    let el = [...document.querySelectorAll('h1')].find(vis);
    if (!el) el = [...document.querySelectorAll('h2, p, span, div')].filter((e) => vis(e) && e.children.length === 0 && (e.innerText || '').trim().length > 8)
      .sort((a, b) => parseFloat(getComputedStyle(b).fontSize) - parseFloat(getComputedStyle(a).fontSize))[0];
    if (!el) return null; const r = el.getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(Math.round); })()`);
  for (const step of flow.steps) {
    if (step.wait != null) continue;
    if (step.goto) {
      const l = waitFor("Page.loadEventFired", 30000); await s("Page.navigate", { url: step.goto }); await l; await settle();
      await newPlate(); const to = await snap("goto"); st.steps.push({ kind: "goto", from: cur, to, navigates: true }); cur = to; continue;
    }
    if (step.scroll) {
      // one tall still from here down by the scroll; the camera travels down it. A page that scrolls an inner
      // element (an app shell) is laid out tall for the shot, its content lifted to where it was, then restored.
      const y0 = await sy(), h = H + Math.abs(step.scroll);
      const inner = await ev(EXPAND);
      const tall = await snap("tall", [W, h], { x: 0, y: inner == null ? y0 : 0, width: W, height: h });
      if (inner != null) await ev(RESTORE);
      await sleep(300);
      await ev(`(() => { const el = ${SCROLLER}; el.scrollBy(0, ${step.scroll}); return true; })()`);
      await sleep(900);
      const dy = Math.round(step.scroll);
      st.states[tall].y = off;
      off += dy;
      st.steps.push({ kind: "scroll", dy, from: cur, to: tall }); cur = tall; continue;
    }
    if (step.key) {
      const u0 = await ev("location.pathname");
      await pressKey(s, step.key);
      await sleep((step.hold ?? 1.8) * 1000);
      const nav = (await ev("location.pathname")) !== u0;   // a new query on the same page is a state of it
      if (nav) { await settle(); await newPlate(); }
      const to = await snap("key");
      st.steps.push({ kind: "key", label: step.key, from: cur, to, navigates: nav }); cur = to; continue;
    }
    if (step.write) {
      // typing into whatever has focus (a search box a shortcut or a button just opened): no click first
      await ev(`(() => { const e = document.activeElement; if (!e) return false; e.setAttribute('placeholder', ''); e.style.caretColor = 'transparent';
        const st = document.createElement('style');
        st.textContent = ':focus::placeholder, :focus *::placeholder { color: transparent !important } :focus::before, :focus *::before, :focus::after, :focus *::after { opacity: 0 !important }';
        document.head.appendChild(st); return true; })()`);
      await sleep(250);
      const empty = await snap("focused");
      for (const ch of step.write) { await s("Input.insertText", { text: ch }); await sleep(25); }
      await sleep((step.hold ?? 1.2) * 1000);
      const caret = await ev(CARET(step.write));
      const r = await ev(`(() => { const r = document.activeElement.getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(Math.round); })()`);
      const typed = await snap("typed");
      if (caret) caret.top += off;
      st.steps.push({ kind: "write", rect: [r[0], r[1] + off, r[2], r[3]], text: step.write, from: cur, empty, to: typed, caret });
      cur = typed; continue;
    }
    const t = step.click || step.move || step.hover || step.type;
    const r = await rectOf(t);
    const cx = r[0] + Math.min(r[2] / 2, 60 + r[2] * 0.2), cy = r[1] - off + r[3] / 2;
    await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: cx, y: cy });
    if (step.move || step.hover) {
      await sleep((step.hold ?? 0.8) * 1000);
      const to = await snap("hover");
      st.steps.push({ kind: "hover", rect: r, label: t, at: [cx, cy + off], from: cur, to }); cur = to; continue;
    }
    const label = await ev(`(document.elementFromPoint(${cx}, ${cy})?.closest('a, button, [role=button], input') || {}).innerText || ''`);
    if (!step.allow && !step.type && (DENY.test(t) || DENY.test(label || ""))) throw new Error(`flow ${flow.id}: refused to press ${JSON.stringify(label || t)} (creates, deletes, pays, publishes or invites). Ask the user; then "allow": true on the step.`);
    const u0 = await ev("location.pathname");
    // a link that opens a new tab opens in this one: the flow follows the click, as the film must
    await ev(`(() => { const a = document.elementFromPoint(${cx}, ${cy})?.closest('a[target]'); if (a) a.removeAttribute('target'); return true; })()`);
    await s("Input.dispatchMouseEvent", { type: "mousePressed", x: cx, y: cy, button: "left", clickCount: 1 });
    await sleep(90);
    await s("Input.dispatchMouseEvent", { type: "mouseReleased", x: cx, y: cy, button: "left", clickCount: 1 });
    if (step.type) {
      await sleep(400);
      // the focused field with no placeholder and no caret: the film draws the caret and reveals the text
      await ev(`(() => { const e = document.activeElement; if (!e) return false; e.setAttribute('placeholder', ''); e.style.caretColor = 'transparent';
        const st = document.createElement('style');   // editors draw their placeholder with ::before
        st.textContent = ':focus::placeholder, :focus *::placeholder { color: transparent !important } :focus::before, :focus *::before, :focus::after, :focus *::after { opacity: 0 !important }';
        document.head.appendChild(st); return true; })()`);
      await sleep(250);
      const empty = await snap("focused");
      for (const ch of step.text) { await s("Input.insertText", { text: ch }); await sleep(25); }
      await sleep(500);
      const caret = await ev(CARET(step.text));
      const typed = await snap("typed");
      if (caret) caret.top += off;
      st.steps.push({ kind: "type", rect: r, text: step.text, at: [cx, cy + off], from: cur, empty, to: typed, caret });
      cur = typed; continue;
    }
    if (step.navigates) {
      await Promise.race([waitFor("Page.loadEventFired", 6000), waitFor("Page.navigatedWithinDocument", 6000)]);
      await sleep(600); await settle();
    } else await sleep((step.hold ?? 1.2) * 1000);
    const nav = !!step.navigates || (await ev("location.pathname")) !== u0;
    if (nav) await newPlate();
    const to = await snap(nav ? "page" : "click");
    st.steps.push({ kind: "click", rect: r, label: t, at: [cx, cy + off], from: cur, to, navigates: nav }); cur = to;
  }
  if (bcfg) {
    st.blurred = [...new Set((await ev("window.__aiBlurHits || []")) || [])];
    await ev(`for (const e of document.querySelectorAll('[data-ai-blur]')) e.style.outline = '3px solid #E5484D'; true`);
    const { data } = await s("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync(path.join(out, `${id}-blurred.png`), Buffer.from(data, "base64"));
  }
  st.end_url = await ev("location.href");
  st.copy = await ev(`[...new Set([...document.querySelectorAll('h1, h2, h3, h4, button, [role=tab], label, a, textarea, input')]
    .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.bottom > 0 && r.top < innerHeight && !e.closest('[data-ai-blur]'); })
    .map((e) => (e.innerText || e.placeholder || '').replace(/\\s+/g, ' ').trim()).filter((t) => t && t.length < 120))].slice(0, 80)`);
  fs.writeFileSync(path.join(out, `${id}.states.json`), JSON.stringify(st));
  console.log(`flows/${id}.states.json: ${st.plates.length} pages, ${st.states.length} states, ${st.steps.length} steps`);
}

async function main() {
  const bin = findBinary(SHELLS);
  if (!bin) { console.error(`ERROR: no Chrome Headless Shell under ${SHELLS}. Run the setup skill (setup.py remotion) once.`); process.exit(1); }
  const out = path.join(dir, "flows");
  fs.mkdirSync(out, { recursive: true });
  const only = flag("--only");
  const first = spec.flows.find((f) => !only || f.id === only);
  const logged = first && hasProfile(first.url) && chromeBinary() ? profileFor(first.url) : null;
  if (logged) console.error(`  logged in: using the profile ${logged} (login.mjs logout <domain> deletes it)`);
  const cdp = chrome(bin, logged);
  try {
    // the logged-in account's own name and handle, read from the session (its profile link and page), blurred
    // in every frame unless the flow file says "blur": {"show_names": true}. Kept in flows/whoami.json, local only.
    if (logged && spec.blur !== false && !spec.blur?.show_names) {
      const cached = path.join(out, "whoami.json");
      const me = fs.existsSync(cached) && Date.now() - fs.statSync(cached).mtimeMs < 6 * 3600e3 ? JSON.parse(fs.readFileSync(cached, "utf8"))
        : await whoami(cdp, new URL(first.url).origin + "/");
      if (me.tokens.length) {
        fs.writeFileSync(path.join(out, "whoami.json"), JSON.stringify(me));
        spec.blur = { ...(spec.blur || {}), text: [...new Set([...(spec.blur?.text || []), ...me.tokens])] };
        console.error(`  blurring the logged-in account's name and handle (${me.tokens.length} words, flows/whoami.json)`);
      } else console.error("  WARN: could not read the logged-in account's name; add it to flows.json blur.text");
    }
    // a flow may carry "mobile": {...} for the phone layout (other steps where the controls differ)
    for (const flow of spec.flows.filter((f) => !only || f.id === only).map((f) => (MOBILE && f.mobile ? { ...f, ...f.mobile } : f))) {
      const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
      const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
      const s = (m, p) => cdp.send(m, p, sessionId);
      const ev = async (expression) => (await s("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;
      const waitFor = (method, ms) => new Promise((ok) => { const l = (m) => { if (m.method === method && m.sessionId === sessionId) fin(true); };
        const timer = setTimeout(() => fin(false), ms); const fin = (v) => { clearTimeout(timer); cdp.listeners.delete(l); ok(v); }; cdp.listeners.add(l); });
      await s("Page.enable");
      await s("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: DSF, mobile: MOBILE });
      await s("Emulation.setUserAgentOverride", { userAgent: MOBILE
        ? "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
        : "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36" });
      const cookies = flag("--cookies");
      if (cookies) { await s("Network.enable"); await s("Network.setCookies", { cookies: JSON.parse(fs.readFileSync(cookies, "utf8")) }); }
      if (!STATES) await s("Page.addScriptToEvaluateOnNewDocument", { source: CURSOR });
      // blur: on for a logged-in profile unless the flow file says "blur": false; extra words and selectors from it
      const bcfg = spec.blur === false ? null : (logged || spec.blur) ? { text: spec.blur?.text || [], show_names: !!spec.blur?.show_names, selectors: spec.blur?.selectors
        || ["[class*=avatar i]", "[class*=billing i]", "[data-private]", "input[type=email]"] } : null;
      if (bcfg) await s("Page.addScriptToEvaluateOnNewDocument", { source: BLUR(bcfg) });
      const settle = async () => { await sleep(1800); for (let i = 0; i < 2; i++) { await ev(DISMISS); await sleep(400); }
        await ev("document.fonts.ready.then(() => true)"); if (!STATES) await ev(CURSOR); if (bcfg) await ev(BLUR(bcfg)); };
      const loaded = waitFor("Page.loadEventFired", 30000);
      await s("Page.navigate", { url: flow.url });
      await loaded; await settle();
      if (STATES) {
        await captureStates(flow, s, ev, waitFor, settle, bcfg, out);
        await cdp.send("Target.closeTarget", { targetId }).catch(() => {});
        continue;
      }

      // ---- the cursor starts low right, off the action, as a person's hand would be
      let mx = W * 0.82, my = H * 0.78;
      await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: mx, y: my });
      const frames = [], track = { cursor: [], steps: [] };
      const fdir = fs.mkdtempSync(path.join(os.tmpdir(), "ai-editor-frames-"));
      let t0 = null;
      const now = () => (Date.now() - t0) / 1000;
      const onFrame = (m) => {
        if (m.method !== "Page.screencastFrame" || m.sessionId !== sessionId) return;
        const f = path.join(fdir, `f${String(frames.length).padStart(5, "0")}.jpg`);
        fs.writeFileSync(f, Buffer.from(m.params.data, "base64"));
        frames.push({ f, t: m.params.metadata.timestamp });
        s("Page.screencastFrameAck", { sessionId: m.params.sessionId }).catch(() => {});
      };
      cdp.listeners.add(onFrame);
      await s("Page.startScreencast", { format: "jpeg", quality: 88, maxWidth: W * DSF, maxHeight: H * DSF, everyNthFrame: 1 });
      t0 = Date.now();
      const glide = async (x, y) => {
        // eased, on a slight arc, ~0.45-0.9 s by distance: a hand, not a robot
        const d = Math.hypot(x - mx, y - my), n = Math.round(Math.min(54, Math.max(26, d / 18))), bow = Math.min(60, d * 0.12);
        const x0 = mx, y0 = my;
        for (let i = 1; i <= n; i++) {
          const p = i / n, e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
          mx = x0 + (x - x0) * e; my = y0 + (y - y0) * e - Math.sin(e * Math.PI) * bow;
          await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: mx, y: my });
          track.cursor.push([+now().toFixed(3), Math.round(mx), Math.round(my)]);
          await sleep(16);
        }
      };
      const target = async (t) => {
        const r = await ev(FINDEL(t));
        if (!r) throw new Error(`flow ${flow.id}: nothing on the page matches ${JSON.stringify(t)}`);
        return r;
      };
      const mark = (kind, rect, label) => track.steps.push({ t: +now().toFixed(3), kind, rect, label });
      await sleep(700);
      for (const st of flow.steps) {
        if (st.wait != null) { await sleep(st.wait * 1000); continue; }
        if (st.goto) { const l = waitFor("Page.loadEventFired", 30000); await s("Page.navigate", { url: st.goto }); await l; await settle(); mark("goto", [0, 0, W, H], st.goto); continue; }
        if (st.scroll) {
          mark("scroll", [0, 0, W, H], String(st.scroll));
          if (MOBILE) {   // a phone scrolls by a swipe, not a wheel
            // eased like a flick, on whichever element really scrolls (a page or its inner scroller)
            await ev(`(async () => { const dy = ${st.scroll};
              const els = [document.scrollingElement, ...document.querySelectorAll('main, div, section')];
              const el = els.find((e) => e && e.scrollHeight > e.clientHeight + 40 && getComputedStyle(e).overflowY !== 'hidden'
                && (e === document.scrollingElement || /auto|scroll/.test(getComputedStyle(e).overflowY)) && e.clientHeight > innerHeight * 0.5);
              if (!el) return false; const y0 = el.scrollTop, t0 = performance.now();
              await new Promise((done) => { const step = () => { const p = Math.min(1, (performance.now() - t0) / 900);
                el.scrollTop = y0 + dy * (1 - Math.pow(1 - p, 3)); p < 1 ? requestAnimationFrame(step) : done(); }; step(); });
              return true; })()`);
            await sleep(400); continue;
          }
          const n = Math.max(12, Math.round(Math.abs(st.scroll) / 30));
          for (let i = 0; i < n; i++) { await s("Input.dispatchMouseEvent", { type: "mouseWheel", x: W / 2, y: H / 2, deltaX: 0, deltaY: st.scroll / n }); await sleep(22); }
          await sleep(500); continue;
        }
        if (st.key) {
          mark("key", null, st.key);
          await pressKey(s, st.key);
          await sleep((st.hold ?? 0.9) * 1000); continue;
        }
        if (st.write) {
          // typing into whatever has focus (a search box a shortcut just opened)
          mark("write", null, st.write);
          for (const ch of st.write) { await s("Input.insertText", { text: ch }); await sleep(1000 / (st.cps || 9)); }
          await sleep((st.hold ?? 1.2) * 1000); continue;
        }
        const t = st.click || st.move || st.hover || st.type;
        const r = await target(t);
        await glide(r[0] + Math.min(r[2] / 2, 60 + r[2] * 0.2), r[1] + r[3] / 2);
        if (st.move || st.hover) { mark(st.hover ? "hover" : "move", r, t); await sleep((st.hold ?? (st.hover ? 1.0 : 0.3)) * 1000); continue; }
        const label = await ev(`(document.elementFromPoint(${mx}, ${my})?.closest('a, button, [role=button], input') || {}).innerText || ''`);
        if (!st.allow && !st.type && (DENY.test(t) || DENY.test(label || ""))) throw new Error(`flow ${flow.id}: refused to press ${JSON.stringify(label || t)} (creates, deletes, pays, publishes or invites). Ask the user; then "allow": true on the step.`);
        mark(st.type ? "type" : "click", r, st.type ? st.text : t);
        await ev(`(() => { const a = document.elementFromPoint(${mx}, ${my})?.closest('a[target]'); if (a) a.removeAttribute('target'); return true; })()`);
        await sleep(160);
        await s("Input.dispatchMouseEvent", { type: "mousePressed", x: mx, y: my, button: "left", clickCount: 1 });
        await sleep(90);
        await s("Input.dispatchMouseEvent", { type: "mouseReleased", x: mx, y: my, button: "left", clickCount: 1 });
        if (st.type) {
          await sleep(350);
          for (const ch of st.text) { await s("Input.insertText", { text: ch }); await sleep(1000 / (st.cps || 9)); }
        }
        // "navigates": true, a click that loads a whole new page: wait for it (the frames keep coming, the load is real)
        if (st.navigates) { await Promise.race([waitFor("Page.loadEventFired", 6000), waitFor("Page.navigatedWithinDocument", 6000)]); await sleep(600); await ev(DISMISS); await ev(CURSOR);
          await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: mx, y: my }); }
        await sleep((st.hold ?? 1.2) * 1000);
      }
      await sleep(900);
      const end = now();
      const endUrl = await ev("location.href");
      // the words on screen at the end (headings, buttons, prompts): on-screen copy may quote them
      const seen = await ev(`[...new Set([...document.querySelectorAll('h1, h2, h3, h4, button, [role=tab], label, a, textarea, input')]
        .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.bottom > 0 && r.top < innerHeight && !e.closest('[data-ai-blur]'); })
        .map((e) => (e.innerText || e.placeholder || '').replace(/\\s+/g, ' ').trim()).filter((t) => t && t.length < 120))].slice(0, 80)`);
      await s("Page.stopScreencast");
      let blurred = [];
      if (bcfg) {
        // what was blurred, outlined in red, for the user to check before anything is shared
        blurred = (await ev("window.__aiBlurHits || []")) || [];
        await ev(`for (const e of document.querySelectorAll('[data-ai-blur]')) e.style.outline = '3px solid #E5484D'; true`);
        const { data } = await s("Page.captureScreenshot", { format: "png" });
        fs.writeFileSync(path.join(out, `${flow.id}${SUFFIX}-blurred.png`), Buffer.from(data, "base64"));
      }
      cdp.listeners.delete(onFrame);
      await cdp.send("Target.closeTarget", { targetId }).catch(() => {});
      if (frames.length < 2) throw new Error(`flow ${flow.id}: no frames recorded`);
      // frames arrive only when the page paints: hold each until the next, then a constant 30 fps
      const ts = frames.map((f) => f.t - frames[0].t);
      const lead = (frames[0].t * 1000 - t0) / 1000;   // screencast clock vs ours
      const list = frames.map((f, i) => `file '${f.f}'\nduration ${Math.max(0.001, (i + 1 < frames.length ? ts[i + 1] - ts[i] : Math.max(0.05, end - lead - ts[i]))).toFixed(4)}`).join("\n");
      fs.writeFileSync(path.join(fdir, "list.txt"), list + `\nfile '${frames[frames.length - 1].f}'\n`);
      const mp4 = path.join(out, `${flow.id}${SUFFIX}.mp4`);
      await new Promise((ok, fail) => spawn("ffmpeg", ["-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", path.join(fdir, "list.txt"),
        "-vf", `fps=${FPS},scale=${W * DSF}:${H * DSF}:flags=lanczos,format=yuv420p`, "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-g", "15", mp4],
      { stdio: "inherit" }).on("exit", (c) => (c ? fail(new Error(`ffmpeg ${c}`)) : ok())));
      // our clock -> video clock: the first frame is video t=0
      const shift = (x) => +(x - lead).toFixed(3);
      const meta = { id: flow.id + SUFFIX, url: flow.url, src: `flows/${flow.id}${SUFFIX}.mp4`, mobile: MOBILE, viewport: [W, H], size: [W * DSF, H * DSF], fps: FPS,
        duration: +(end - lead).toFixed(3), frames: frames.length, measured_fps: +(frames.length / Math.max(0.1, ts[ts.length - 1])).toFixed(1),
        logged_in: !!logged, end_url: endUrl, copy: seen, blurred: [...new Set(blurred)],
        cursor: track.cursor.map(([t, x, y]) => [shift(t), x, y]), steps: track.steps.map((x) => ({ ...x, t: shift(x.t) })) };
      fs.writeFileSync(path.join(out, `${flow.id}${SUFFIX}.json`), JSON.stringify(meta));
      fs.rmSync(fdir, { recursive: true, force: true });
      console.log(`${mp4}: ${meta.duration.toFixed(1)} s, ${meta.frames} painted frames (${meta.measured_fps} fps where the page moved), ${meta.steps.length} steps`);
    }
  } finally { cdp.close(); }
}

await main();
