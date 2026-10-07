// Crawls one website into what a product video is built from: the real UI, the site's own brand and
// its own words. No API keys, no paid services: the Chrome Headless Shell Remotion installs, over the
// DevTools pipe, through style-edit's capture.mjs helpers.
//
//   node crawl.mjs <url> <outDir> [--app <url>] [--cookies cookies.json] [--max-tiles 9]
//
// <outDir>/site.json, plus images/ (page tiles, hero, element crops, logo), fonts/ (the site's own
// font files) and media/ (product videos the page itself plays). All rects are page CSS px.
//   --app      a second URL (a logged-in app page): shot as images/app.png, its copy added
//   --cookies  [{name, value, domain}] set before loading, for that logged-in page
//   --pages    how many inner pages to read for use cases (default 20, 0 = home page only): the site's nav
//              and sitemap.xml, ranked features > pricing > customers > templates > docs > changelog > blog;
//              each one's words, controls, media and a screenshot into site.json "pages" and pages/
//   --include  url,url: pages the user's brief names, read first (kind "brief")
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
// What the crawl line says about the logo: its file, else the wordmark it is drawn as (a text logo has no file).
const logoNote = (l) => (!l ? "none" : l.src || (l.word ? `text "${l.word}"` : "none"));
const { launch, findBinary, SHELLS, DISMISS, pool, TABS } = await import(pathToFileURL(path.join(HERE, "../../style-edit/scripts/capture.mjs")).href);

const W = 1440, H = 900, DSF = 2;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const args = process.argv.slice(2);
const flag = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
const [url, outDir] = args.filter((a, i) => !a.startsWith("--") && !args[i - 1]?.startsWith("--"));
if (!url || !outDir) { console.error("usage: node crawl.mjs <url> <outDir> [--app url] [--cookies file] [--max-tiles N] [--pages N]"); process.exit(2); }
const MAX_TILES = Number(flag("--max-tiles", 9));
const MAX_PAGES = Number(flag("--pages", 20));
for (const d of ["images", "fonts", "media"]) fs.mkdirSync(path.join(outDir, d), { recursive: true });
const save = (rel, buf) => { fs.writeFileSync(path.join(outDir, rel), buf); return rel; };
const pngSize = (b) => [b.readUInt32BE(16), b.readUInt32BE(20)];

// ---------- in-page readers ----------
// Brand: colours from the computed styles of what the page actually paints, fonts of its headings and
// body, the radius of its buttons and cards, and the stylesheets that hold its @font-face rules.
const BRAND = `(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const clear = (c) => !c || /rgba\\(0, 0, 0, 0\\)|transparent/.test(c);
  const bgOf = (e) => { for (; e; e = e.parentElement) { const c = getComputedStyle(e).backgroundColor; if (!clear(c)) return c; } return 'rgb(255, 255, 255)'; };
  const first = (sel) => [...document.querySelectorAll(sel)].find(vis);
  const h1 = first('h1') || first('h2') || document.body, body = first('p') || document.body;
  const fam = (e) => getComputedStyle(e).fontFamily;
  const btns = [...document.querySelectorAll('a, button')].filter(vis).filter((b) => {
    const r = b.getBoundingClientRect(), t = (b.innerText || '').trim();
    return t && t.split(/\\s+/).length <= 5 && r.width < 420 && r.height < 90 && !clear(getComputedStyle(b).backgroundColor);
  });
  const radii = [...btns, ...document.querySelectorAll('img, video, section > div')].filter(vis)
    .map((e) => parseFloat(getComputedStyle(e).borderTopLeftRadius)).filter((r) => r > 0 && r < 80).sort((a, b) => a - b);
  const sheets = [...document.styleSheets].map((s) => { try { return { href: s.href, text: [...s.cssRules].map((r) => r.cssText).join('\\n') }; }
    catch { return { href: s.href, text: null }; } });
  const vars = {};
  const rs = getComputedStyle(document.documentElement);
  for (const s of sheets) for (const m of (s.text || '').matchAll(/(--[\\w-]+)\\s*:/g)) if (Object.keys(vars).length < 400) vars[m[1]] = rs.getPropertyValue(m[1]).trim();
  const hs = getComputedStyle(h1), bs = getComputedStyle(body);
  return {
    bg: bgOf(h1), page_bg: bgOf(document.body), ink: hs.color, body_ink: bs.color, page_ink: getComputedStyle(document.body).color,
    // grounds of full-width bands, at any depth (builders like Framer nest them deep)
    sections: [...new Set([...document.querySelectorAll('body *')].filter((e) => { const r = e.getBoundingClientRect();
      return r.height > 300 && r.width > innerWidth * 0.8; }).map((e) => getComputedStyle(e).backgroundColor).filter((c) => !clear(c)))].slice(0, 40),
    buttons: btns.slice(0, 12).map((b) => ({ text: b.innerText.trim(), bg: getComputedStyle(b).backgroundColor, color: getComputedStyle(b).color })),
    links: [...document.querySelectorAll('main a, section a')].filter(vis).slice(0, 30).map((a) => getComputedStyle(a).color),
    radius_px: radii.length ? radii[Math.floor(radii.length / 2)] : 8,
    display: { family: fam(h1), weight: +hs.fontWeight, letter_spacing: hs.letterSpacing, size_px: parseFloat(hs.fontSize), line_height: hs.lineHeight },
    body: { family: fam(body), weight: +bs.fontWeight },
    sheets, vars,
  };
})()`;

// The logo: the header link to the home page holding an svg or img. An svg is cloned with every
// computed fill and stroke written in, so it draws the same outside the page.
const LOGO = `(() => {
  const home = (a) => { try { const u = new URL(a.href, location.href); return u.host === location.host && /^\\/?$/.test(u.pathname); } catch { return false; } };
  const scope = document.querySelector('header, nav, [class*=header i], [class*=nav i]') || document.body;
  const cands = [...scope.querySelectorAll('a')].filter(home).concat([...document.querySelectorAll('[class*=logo i], [aria-label*=logo i]')]);
  // else the leftmost svg or img in the top bar (a logo that is not a link)
  const bar = [...document.querySelectorAll('svg, img')].filter((g) => { const r = g.getBoundingClientRect();
    return r.top + scrollY < 110 && r.left < 520 && r.width >= 14 && r.height >= 10 && r.height < 90; }).sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
  for (const a of [...cands, ...bar]) {
    const g = a.matches('svg, img') ? a : a.querySelector('svg, img');
    if (!g) {
      // a wordmark set in text: kept as text in the page's own font
      const t = (a.innerText || '').trim(), r = a.getBoundingClientRect();
      if (a.tagName === 'A' && t && t.length < 30 && r.top + scrollY < 110) return { kind: 'text', word: t, rect: [r.left + scrollX, r.top + scrollY, r.width, r.height],
        word_font: getComputedStyle(a).fontFamily, word_weight: getComputedStyle(a).fontWeight, word_size: parseFloat(getComputedStyle(a).fontSize) };
      continue;
    }
    const r = g.getBoundingClientRect();
    if (r.width < 12 || r.height < 8) continue;
    if (g.tagName.toLowerCase() === 'img') return { kind: 'img', src: g.currentSrc || g.src, rect: [r.left + scrollX, r.top + scrollY, r.width, r.height], word: ((g.closest('a') || g.parentElement).innerText || '').trim() };
    const clone = g.cloneNode(true), src = [g, ...g.querySelectorAll('*')], dst = [clone, ...clone.querySelectorAll('*')];
    src.forEach((e, i) => { const s = getComputedStyle(e);
      for (const k of ['fill', 'stroke', 'stroke-width', 'opacity', 'fill-rule', 'color']) dst[i].style.setProperty(k, s.getPropertyValue(k)); });
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    if (!clone.getAttribute('viewBox')) clone.setAttribute('viewBox', '0 0 ' + r.width + ' ' + r.height);
    clone.setAttribute('width', r.width); clone.setAttribute('height', r.height);
    // a wordmark next to the mark (text in the same link) is kept as text in the page's own font
    const host = a.closest('a') || g.parentElement;
    const word = (host.innerText || '').trim();
    return { kind: 'svg', svg: clone.outerHTML, rect: [r.left + scrollX, r.top + scrollY, r.width, r.height], word,
      word_font: getComputedStyle(host).fontFamily, word_weight: getComputedStyle(host).fontWeight };
  }
  return null;
})()`;

// Everything worth showing, in page px: headings, short buttons, big media, card-like boxes, and every
// visible phrase of copy in reading order.
const ELEMENTS = `(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left + scrollX, r.top + scrollY, r.width, r.height].map(Math.round); };
  const txt = (e) => (e.innerText || '').replace(/\\s+/g, ' ').trim();
  const out = [], copy = [], seen = new Set();
  for (const e of document.querySelectorAll('h1, h2, h3, h4, p, li, blockquote, figcaption, button, a, span, dt, dd, label')) {
    if (!vis(e)) continue;
    const t = txt(e);
    if (t.length < 2 || t.length > 220 || seen.has(t)) continue;
    // a span or link only when it is a leaf of text (not a wrapper around a heading)
    if (/^(SPAN|A|LI)$/.test(e.tagName) && e.querySelector('h1,h2,h3,p,div')) continue;
    seen.add(t);
    copy.push({ text: t, tag: e.tagName.toLowerCase(), rect: R(e) });
  }
  // a search box's or field's own prompt is the site's words too ("Search NextWork")
  for (const e of document.querySelectorAll('input[placeholder], textarea[placeholder]')) if (vis(e) && e.placeholder.trim() && !seen.has(e.placeholder.trim())) {
    seen.add(e.placeholder.trim()); copy.push({ text: e.placeholder.trim(), tag: 'input', rect: R(e) }); }
  for (const e of document.querySelectorAll('h1, h2, h3')) if (vis(e) && txt(e).length > 2 && txt(e).length < 140)
    out.push({ kind: 'heading', tag: e.tagName.toLowerCase(), text: txt(e), rect: R(e) });
  for (const e of document.querySelectorAll('a, button')) {
    const t = txt(e), r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (!vis(e) || !t || t.split(' ').length > 5 || r.width > 420 || r.height > 90 || r.height < 24) continue;
    const filled = !/rgba\\(0, 0, 0, 0\\)|transparent/.test(s.backgroundColor) || parseFloat(s.borderTopWidth) > 0;
    if (filled) out.push({ kind: 'button', text: t, rect: R(e) });
  }
  for (const e of document.querySelectorAll('img, video, picture, canvas, iframe')) {
    const r = e.getBoundingClientRect();
    if (!vis(e) || r.width < 420 || r.height < 220) continue;
    out.push({ kind: 'media', tag: e.tagName.toLowerCase(), text: e.alt || e.title || '', rect: R(e),
      video: e.tagName === 'VIDEO' ? (e.currentSrc || e.querySelector('source')?.src || '') : undefined });
  }
  // cards: rounded boxes with their own ground, border or shadow, holding some text, phone to tablet sized
  for (const e of document.querySelectorAll('main div, section div, article, li')) {
    const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    if (!vis(e) || r.width < 220 || r.width > 900 || r.height < 120 || r.height > 760) continue;
    const boxed = parseFloat(s.borderTopLeftRadius) >= 6 && (!/rgba\\(0, 0, 0, 0\\)|transparent/.test(s.backgroundColor)
      || parseFloat(s.borderTopWidth) > 0 || s.boxShadow !== 'none');
    if (!boxed || txt(e).length < 8) continue;
    out.push({ kind: 'card', text: txt(e).slice(0, 160), rect: R(e), has_media: !!e.querySelector('img, video, svg, canvas') });
  }
  // the pricing block, when there is one
  const price = [...document.querySelectorAll('section, div')].find((e) => vis(e) && /pricing|plans/i.test(e.id + ' ' + e.className)
    && /\\$|€|£|\\/mo|month|free/i.test(txt(e)) && e.getBoundingClientRect().height > 200);
  if (price) out.push({ kind: 'pricing', text: txt(price).slice(0, 200), rect: R(price) });
  const meta = (n) => document.querySelector('meta[property="' + n + '"], meta[name="' + n + '"]')?.content || '';
  return { elements: out, copy, title: document.title, description: meta('description') || meta('og:description'),
    og_image: meta('og:image'), icon: (document.querySelector('link[rel="apple-touch-icon"]') || document.querySelector('link[rel*=icon]'))?.href || '',
    height: document.documentElement.scrollHeight,
    // same-site links, nav and footer first: where the site itself sends people
    links: [...new Set([...document.querySelectorAll('header a, nav a, footer a, a')].map((a) => a.href)
      .filter((h) => { try { return new URL(h).host.replace(/^www\\./, '').split('.').slice(-2).join('.') === location.host.replace(/^www\\./, '').split('.').slice(-2).join('.'); } catch { return false; } })
      .map((h) => h.split('#')[0]))].slice(0, 300) };
})()`;

// What one inner page says and lets you do: its headings and lines (the site's own words about each job),
// the controls a click-through can use (tabs, buttons, links, search boxes) and any product video or GIF.
const PAGE = `(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const txt = (e) => (e.innerText || '').replace(/\\s+/g, ' ').trim();
  const R = (e) => { const r = e.getBoundingClientRect(); return [r.left + scrollX, r.top + scrollY, r.width, r.height].map(Math.round); };
  const seen = new Set(), lines = [];
  for (const e of document.querySelectorAll('h1, h2, h3, p, li, blockquote, figcaption, dt, dd')) {
    const t = txt(e);
    if (!vis(e) || t.length < 3 || t.length > 260 || seen.has(t) || e.closest('nav, footer')) continue;
    if (e.tagName === 'LI' && e.querySelector('p, h3, li')) continue;
    seen.add(t); lines.push({ tag: e.tagName.toLowerCase(), text: t, y: R(e)[1] });
  }
  const controls = [];
  for (const e of document.querySelectorAll('button, [role=tab], [role=button], a, input, textarea, select, summary, [aria-expanded]')) {
    if (!vis(e) || e.closest('footer')) continue;
    const r = R(e); const t = txt(e) || e.placeholder || e.getAttribute('aria-label') || '';
    if (!t || t.length > 60 || r[2] > 700) continue;
    controls.push({ kind: e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' ? 'input' : (e.getAttribute('role') || e.tagName.toLowerCase()),
      text: t, rect: r, href: e.href || undefined });
    if (controls.length >= 60) break;
  }
  const media = [...document.querySelectorAll('video, img')].filter((e) => vis(e) && e.getBoundingClientRect().width > 300)
    .map((e) => ({ tag: e.tagName.toLowerCase(), src: e.currentSrc || e.src || e.querySelector?.('source')?.src || '', rect: R(e) }))
    .filter((m) => m.tag === 'video' || /\\.gif(\\?|$)/i.test(m.src)).slice(0, 6);
  const meta = (n) => document.querySelector('meta[property="' + n + '"], meta[name="' + n + '"]')?.content || '';
  return { title: document.title, description: meta('description') || meta('og:description'), lines: lines.slice(0, 80), controls, media,
    height: document.documentElement.scrollHeight };
})()`;

// Which pages say what the product is for, scored on path words, a few per kind so twenty blog posts
// never crowd out the pricing page. [kind, path test, weight, cap]
const KINDS = [
  ["features", /\/(features?|product|platform|how-it-works|tour|solutions?|use-cases?|capabilities|agents?|ai)(\/|$)/i, 6, 5],
  ["pricing", /\/(pricing|plans)(\/|$)/i, 5, 1],
  ["customers", /\/(customers?|case-stud(y|ies)|stories|testimonials|showcase|wall-of-love)(\/|$)/i, 4, 3],
  ["templates", /\/(templates?|examples?|gallery|projects?|courses?|learn|library|integrations?|paths?)(\/|$)/i, 4, 4],
  ["docs", /\/(docs?|help|guides?|getting-started|quickstart|support)(\/|$)|^https?:\/\/(docs|help)\./i, 3, 3],
  ["changelog", /\/(changelog|releases?|whats-new|updates)(\/|$)/i, 3, 2],
  ["blog", /\/(blog|news|announcing|launch|now)(\/|$)/i, 2, 3],
];
const SKIP = /\/(login|log-in|signin|sign-in|signup|sign-up|register|careers?|jobs|legal|privacy|terms|cookies?|security|status|contact|press|brand|about|team|imprint|dpa|sitemap)(\/|$)|\.(pdf|zip|png|jpe?g|svg|xml)(\?|$)|[?&](utm_|ref=)/i;

async function sitemapUrls() {
  const out = [];
  const robots = (await get(new URL("/robots.txt", url).href))?.toString("utf8") || "";
  const maps = [...robots.matchAll(/^sitemap:\s*(\S+)/gim)].map((m) => m[1]);
  for (const m of (maps.length ? maps : [new URL("/sitemap.xml", url).href]).slice(0, 3)) {
    const xml = (await get(m))?.toString("utf8") || "";
    const locs = [...xml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((x) => x[1]);
    if (/<sitemapindex/.test(xml)) {
      // an index: one level down, sitemaps that sound like pages before posts
      for (const sm of locs.sort((a, b) => /page|main|static/.test(b) - /page|main|static/.test(a)).slice(0, 4)) {
        const x2 = (await get(sm))?.toString("utf8") || "";
        out.push(...[...x2.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((x) => x[1]).slice(0, 400));
      }
    } else out.push(...locs.slice(0, 800));
  }
  return out;
}

function rankPages(navLinks, mapLinks) {
  const root = (h) => h.replace(/^www\./, "").split(".").slice(-2).join(".");
  const host = root(new URL(url).host);
  const ok = (u) => { try { return root(new URL(u).host) === host; } catch { return false; } };
  const home = new URL(url).href.replace(/\/$/, "");
  const seen = new Set(), byKind = {}, out = [];
  for (const [u, nav] of [...navLinks.map((u) => [u, 2]), ...mapLinks.map((u) => [u, 0])]) {
    const clean = u.replace(/\/$/, "");
    if (!ok(u) || SKIP.test(u) || clean === home || seen.has(clean)) continue;
    seen.add(clean);
    const depth = new URL(u).pathname.split("/").filter(Boolean).length;
    const k = KINDS.find(([, re]) => re.test(u));
    if (k) out.push({ url: u, kind: k[0], score: k[2] + nav - Math.max(0, depth - 1) * (k[0] === "blog" ? 0.3 : 1.2), cap: k[3] });
  }
  out.sort((a, b) => b.score - a.score);
  return out.filter((p) => (byKind[p.kind] = (byKind[p.kind] || 0) + 1) <= p.cap).slice(0, MAX_PAGES);
}

// The inner pages, TABS at a time (AI_EDITOR_TABS, default 4), each in its own tab of the one Chrome.
async function crawlPages(openTab, navLinks) {
  // pages the user's brief names come first, whatever their path says
  const must = (flag("--include", "") || "").split(",").filter(Boolean).map((u) => ({ url: new URL(u, url).href, kind: "brief" }));
  const picked = [...must, ...rankPages(navLinks, await sitemapUrls().catch(() => [])).filter((p) => !must.some((m) => m.url === p.url))].slice(0, MAX_PAGES + must.length);
  fs.mkdirSync(path.join(outDir, "pages"), { recursive: true });
  return (await pool(picked, TABS, async (p, i) => {
    const { load, ev, shot, close } = await openTab();
    try {
      await load(p.url);
      for (let y = 0; y < H * 4; y += H * 0.7) { await ev(`scrollTo(0, ${y})`); await sleep(180); }
      await ev("scrollTo(0, 0)"); await sleep(500);
      const info = await ev(PAGE);
      const rel = `pages/page-${i}.jpg`;
      await shot(rel, { x: 0, y: 0, width: W, height: H }, 0.75, true);
      console.error(`  page ${i} ${p.kind.padEnd(9)} ${p.url}  ${info.lines.length} lines, ${info.controls.length} controls, ${info.media.length} media`);
      return { id: `page-${i}`, url: await ev("location.href"), kind: p.kind, shot: rel, ...info };
    } catch (err) { console.error(`  page ${p.url}: ${err.message}`); return null; }
    finally { await close(); }
  })).filter(Boolean);
}

// ---------- node side ----------
const get = async (u) => {
  const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0 (Macintosh) ai-video-editor" } }).catch(() => null);
  return r && r.ok ? Buffer.from(await r.arrayBuffer()) : null;
};
const firstFamily = (f) => (f || "").split(",")[0].trim().replace(/^["']|["']$/g, "");

// @font-face rules of the families the page uses, from readable sheets and by fetching the rest.
async function fonts(brand) {
  const want = new Set([firstFamily(brand.display.family), firstFamily(brand.body.family)].filter(Boolean));
  const faces = [];
  for (const s of brand.sheets) {
    let text = s.text;
    if (text == null && s.href) text = (await get(s.href))?.toString("utf8") ?? "";
    for (const m of (text || "").matchAll(/@font-face\s*\{([^}]*)\}/g)) {
      const body = m[1];
      const family = firstFamily(body.match(/font-family:\s*([^;]+)/)?.[1]);
      if (!want.has(family)) continue;
      const srcs = [...body.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)\s*format\(\s*["']?(woff2|woff|truetype|opentype)/g)];
      const pick = srcs.find((x) => x[2] === "woff2") || srcs[0] || [...body.matchAll(/url\(\s*["']?([^"')]+\.(woff2?|ttf|otf))/g)][0];
      if (!pick) continue;
      const weight = (body.match(/font-weight:\s*([^;]+)/)?.[1] || "400").trim();
      const style = (body.match(/font-style:\s*([^;]+)/)?.[1] || "normal").trim();
      const range = body.match(/unicode-range:\s*([^;]+)/)?.[1]?.trim();
      // latin subset only: skip faces whose range does not reach the basic letters
      if (range && !/U\+0000|U\+0?020|U\+0-|U\+0000-00FF|U\+0-FF/i.test(range)) continue;
      faces.push({ family, weight, style, url: new URL(pick[1], s.href || url).href });
    }
  }
  const out = [];
  for (const [i, f] of faces.slice(0, 12).entries()) {
    const ext = (f.url.match(/\.(woff2?|ttf|otf)(\?|$)/)?.[1]) || "woff2";
    const buf = await get(f.url);
    if (!buf) continue;
    out.push({ family: f.family, weight: f.weight, style: f.style, src: save(`fonts/font-${i}.${ext}`, buf) });
  }
  return out;
}

const rgb = (c) => (c?.match(/[\d.]+/g) || [0, 0, 0]).slice(0, 3).map(Number);
const hex = (c) => "#" + rgb(c).map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();
const sat = (c) => { const [r, g, b] = rgb(c).map((v) => v / 255); const mx = Math.max(r, g, b), mn = Math.min(r, g, b); return mx ? (mx - mn) / mx : 0; };
const lum = (c) => { const [r, g, b] = /^#/.test(c) ? [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16)) : rgb(c); return (0.299 * r + 0.587 * g + 0.114 * b) / 255; };

// The accent: the most common saturated button ground, else a saturated link colour, else the ink.
function accentOf(b) {
  const tally = new Map();
  for (const x of b.buttons) if (sat(x.bg) > 0.25) tally.set(hex(x.bg), (tally.get(hex(x.bg)) || 0) + 1);
  for (const c of b.links) if (sat(c) > 0.35) tally.set(hex(c), (tally.get(hex(c)) || 0) + 0.5);
  for (const c of b.sections) if (sat(c) > 0.25) tally.set(hex(c), (tally.get(hex(c)) || 0) + 1.5);
  const top = [...tally].sort((a, z) => z[1] - a[1])[0];
  return top ? top[0] : hex(b.ink);
}

async function main() {
  const bin = findBinary(SHELLS);
  if (!bin) { console.error(`ERROR: no Chrome Headless Shell under ${SHELLS}. Run the setup skill (setup.py remotion) once.`); process.exit(1); }
  const cdp = launch(bin);
  // One tab: its own session, loader and screenshot. The home page uses one; the inner pages one each.
  const openTab = async () => {
    const { targetId } = await cdp.send("Target.createTarget", { url: "about:blank" });
    const { sessionId } = await cdp.send("Target.attachToTarget", { targetId, flatten: true });
    const s = (m, p) => cdp.send(m, p, sessionId);
    await s("Page.enable");
    const ev = async (expression) => (await s("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;
    const shot = async (rel, clip, scale = 1, jpeg = false) => {
      const { data } = await s("Page.captureScreenshot", { format: jpeg ? "jpeg" : "png", quality: jpeg ? 90 : undefined,
        captureBeyondViewport: false, clip: { ...clip, scale } });
      const buf = Buffer.from(data, "base64");
      save(rel, buf);
      return jpeg ? [Math.round(clip.width * DSF * scale), Math.round(clip.height * DSF * scale)] : pngSize(buf);
    };
    const load = async (u, w = W, h = H, mobile = false) => {
      await s("Emulation.setDeviceMetricsOverride", { width: w, height: h, deviceScaleFactor: mobile ? 3 : DSF, mobile });
      await s("Emulation.setUserAgentOverride", { userAgent: mobile
        ? "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
        : "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36" });
      const loaded = cdp.once("Page.loadEventFired", sessionId, 30000);
      await s("Page.navigate", { url: u });
      if (!(await loaded)) console.error(`  ${u}: no load event after 30 s, going on`);
      await sleep(2500);
      for (let i = 0; i < 2; i++) { await ev(DISMISS); await sleep(600); }
      await ev("document.fonts.ready.then(() => true)");
    };
    const close = () => cdp.send("Target.closeTarget", { targetId }).catch(() => {});
    return { s, ev, shot, load, close };
  };
  const { s, ev, shot, load, close } = await openTab();
  // Scroll the whole page once, a viewport at a time, so lazy images load and scroll-in animations
  // fire (a single full-page capture shows them blank), then come back to the top.
  const prime = async () => {
    const hgt = await ev("document.documentElement.scrollHeight");
    for (let y = 0; y < Math.min(hgt, H * (MAX_TILES + 2)); y += H * 0.6) { await ev(`scrollTo(0, ${y})`); await sleep(260); }
    await ev("scrollTo(0, 0)"); await sleep(900);
  };

  try {
    await s("Network.enable");
    const cookieFile = flag("--cookies");
    if (cookieFile) await s("Network.setCookies", { cookies: JSON.parse(fs.readFileSync(cookieFile, "utf8")) });

    // ---- mobile first (a fresh load), then desktop
    await load(url, 390, 844, true);
    const mobile = { src: "images/mobile-hero.png", size: await shot("images/mobile-hero.png", { x: 0, y: 0, width: 390, height: 844 }), viewport: [390, 844] };

    await load(url);
    await prime();
    const brand = await ev(BRAND);
    const els = await ev(ELEMENTS);
    const logo = await ev(LOGO);
    // the rest of the site, in other tabs, while this one shoots the home page
    const pagesP = MAX_PAGES > 0 ? crawlPages(openTab, els.links) : Promise.resolve([]);

    // ---- the page, as viewport tiles. Not one full-page capture: that stretches every 100vh section.
    // Fixed and sticky bars are hidden after the first tile so the header does not repeat.
    const tiles = [];
    const hgt = Math.min(els.height, H * MAX_TILES);
    for (let y = 0, i = 0; y < hgt; y += H, i++) {
      await ev(`scrollTo(0, ${y})`); await sleep(1200);   // scroll-in animations finish before the shot
      const sy = await ev("scrollY");
      const rel = `images/tile-${i}.jpg`;
      const size = await shot(rel, { x: 0, y: sy, width: W, height: H }, 1, true);
      tiles.push({ src: rel, y: sy, size });
      if (i === 0) await ev(`for (const e of document.querySelectorAll('body *')) { const p = getComputedStyle(e).position;
        if (p === 'fixed' || p === 'sticky') e.style.visibility = 'hidden'; } true`);
      if (sy + H >= els.height) break;
    }
    await ev(`for (const e of document.querySelectorAll('body *')) if (e.style.visibility === 'hidden') e.style.visibility = ''; true`);
    await ev("scrollTo(0, 0)"); await sleep(600);
    const hero = { src: "images/hero.png", size: await shot("images/hero.png", { x: 0, y: 0, width: W, height: H }), viewport: [W, H] };

    // ---- element crops, each scrolled into view first (its own scroll-in animation has run)
    const pick = [];
    const add = (kind, n) => pick.push(...els.elements.filter((e) => e.kind === kind && e.rect[1] < hgt).slice(0, n));
    add("heading", 8); add("button", 4); add("media", 6); add("card", 10); add("pricing", 1);
    const elements = [];
    for (const [i, e] of pick.entries()) {
      const [x, y, w, h] = e.rect;
      const pad = e.kind === "button" ? 4 : e.kind === "heading" ? 12 : 0;
      await ev(`scrollTo(0, ${Math.max(0, y - 120)})`); await sleep(900);
      const clip = { x: Math.max(0, x - pad), y: Math.max(0, y - pad), width: Math.min(w + pad * 2, W), height: Math.min(h + pad * 2, 2400) };
      const rel = `images/el-${i}-${e.kind}.png`;
      try {
        const size = await shot(rel, clip, e.kind === "button" ? 2 : 1);
        const el = { ...e, id: `el-${i}`, src: rel, size, crop: [clip.x, clip.y, clip.width, clip.height] };
        if (e.kind === "button" && !elements.some((q) => q.hover_src)) {
          // the real hover state, for the click
          await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: x + w / 2, y: y + h / 2 - (await ev("scrollY")) });
          await sleep(350);
          el.hover_src = await (async () => { const r = `images/el-${i}-hover.png`; await shot(r, clip, 2); return r; })();
          await s("Input.dispatchMouseEvent", { type: "mouseMoved", x: 2, y: 2 });
        }
        elements.push(el);
      } catch (err) { console.error(`  crop ${e.kind} "${(e.text || "").slice(0, 30)}": ${err.message}`); }
    }

    // ---- the logo
    let logoOut = null;
    if (logo?.kind === "text") logoOut = { word: logo.word, word_font: logo.word_font, word_weight: logo.word_weight, word_size: logo.word_size, rect: logo.rect };
    else if (logo?.kind === "svg") logoOut = { src: save("images/logo.svg", logo.svg), rect: logo.rect, word: logo.word, word_font: logo.word_font, word_weight: logo.word_weight };
    else if (logo?.kind === "img") {
      let buf = await get(logo.src);
      // an svg file with no viewBox does not scale as an image: give it one from its own size
      const fixVb = (b) => { const t = b.toString("utf8"); if (/viewBox/.test(t)) return b;
        const w = t.match(/<svg[^>]*\swidth="([\d.]+)/)?.[1], h = t.match(/<svg[^>]*\sheight="([\d.]+)/)?.[1];
        return w && h ? Buffer.from(t.replace("<svg", `<svg viewBox="0 0 ${w} ${h}"`)) : b; };
      if (buf && /\.svg(\?|$)/.test(logo.src)) buf = fixVb(buf);
      if (buf) logoOut = { src: save(`images/logo.${/\.svg(\?|$)/.test(logo.src) ? "svg" : "png"}`, buf), rect: logo.rect, word: logo.word };
    }
    if (logo) {
      const [x, y, w, h] = logo.rect;
      await ev("scrollTo(0, 0)"); await sleep(300);
      logoOut = { ...(logoOut || {}), png: "images/logo-shot.png", png_size: await shot("images/logo-shot.png",
        { x: Math.max(0, x - 6), y: Math.max(0, y - 6), width: w + 12, height: h + 12 }, 2) };
      if (!logoOut.src && logo.kind !== "text") logoOut.src = logoOut.png;
    }
    const icon = els.icon ? await get(els.icon) : null;

    // ---- product videos the page plays
    const media = [];
    for (const e of els.elements.filter((x) => x.video && /^https?:/.test(x.video)).slice(0, 4)) {
      const buf = await get(e.video);
      if (!buf || buf.length > 60e6) continue;
      media.push({ src: save(`media/video-${media.length}.${/\.webm(\?|$)/.test(e.video) ? "webm" : "mp4"}`, buf), rect: e.rect, from: e.video });
    }

    // ---- an optional logged-in app page
    let app = null;
    const appUrl = flag("--app");
    if (appUrl) {
      await load(appUrl);
      const a = await ev(ELEMENTS);
      app = { url: appUrl, src: "images/app.png", size: await shot("images/app.png", { x: 0, y: 0, width: W, height: H }), viewport: [W, H],
        copy: a.copy.filter((c) => c.rect[1] < H) };
    }

    // ---- the rest of the site: features, pricing, docs, changelog, customers, templates, launch posts
    const pages = await pagesP;

    const fontFiles = await fonts(brand);
    const accent = accentOf(brand);
    const ground = hex(brand.page_bg);
    const site = {
      url, domain: new URL(url).host.replace(/^www\./, ""), title: els.title, description: els.description,
      brand: {
        ground, hero_ground: hex(brand.bg), ink: hex(brand.page_ink), heading_ink: hex(brand.ink), body_ink: hex(brand.body_ink), accent,
        accent_ink: lum(accent) > 0.6 ? "#0A0A0A" : "#FFFFFF", dark: lum(ground) < 0.4, radius_px: brand.radius_px,
        display: { ...brand.display, family: firstFamily(brand.display.family) }, body: { ...brand.body, family: firstFamily(brand.body.family) },
        fonts: fontFiles, vars: Object.fromEntries(Object.entries(brand.vars).filter(([k, v]) => v && /color|bg|background|accent|brand|primary|radius|font/i.test(k)).slice(0, 80)),
        buttons: brand.buttons, section_grounds: [...new Set(brand.sections.map(hex))],
      },
      logo: logoOut, icon: icon ? save("images/icon.png", icon) : null, og_image: els.og_image,
      viewport: [W, H], dsf: DSF, page_height: els.height, tiles, hero, mobile, elements, media, app,
      copy: els.copy, pages,
    };
    fs.writeFileSync(path.join(outDir, "site.json"), JSON.stringify(site, null, 1));
    console.log(`${path.join(outDir, "site.json")}: ${tiles.length} tiles, ${elements.length} element crops, ${media.length} videos, `
      + `${fontFiles.length} font files (${site.brand.display.family} / ${site.brand.body.family}), logo ${logoNote(logoOut)}, `
      + `ground ${ground} ink ${site.brand.ink} accent ${accent}`);
  } finally {
    await close();
    cdp.close();
  }
}

await main();
