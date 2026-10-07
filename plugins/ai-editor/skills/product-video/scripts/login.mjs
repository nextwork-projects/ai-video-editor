// A logged-in product, without ever touching a password: a visible browser window on a profile of its own,
// the user logs in by hand, and the recorder then reuses that profile for that one domain.
//
//   node login.mjs login  <login url> [--check <url that needs a login>]   open the window; verify when it closes
//   node login.mjs check  <url that needs a login>                           is the profile still logged in?
//   node login.mjs logout <domain>                                           delete the profile (the login with it)
//   node login.mjs where  <domain>                                           print the profile folder
//
// The profile: ~/.ai-video-editor/browser/<domain>/ (AI_EDITOR_HOME overrides the root). Never the user's
// own Chrome profile, never their cookie database. It holds a live login on this computer only: it is
// outside every repo, never uploaded (Modal, Lambda and GitHub renders get rendered captures only), and
// `logout` deletes it. Use a demo or test account where there is one.
// Browser: the installed Google Chrome (or Chrome for Testing), the same binary headed here and headless in
// record.mjs, with --use-mock-keychain so the profile's cookies read back the same way both times.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const HOME = process.env.AI_EDITOR_HOME || path.join(os.homedir(), ".ai-video-editor");
const CHROMES = {
  darwin: ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"],
  linux: ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/usr/bin/chromium", "/usr/bin/chromium-browser"],
  win32: [path.join(process.env.PROGRAMFILES || "C:\\Program Files", "Google\\Chrome\\Application\\chrome.exe"),
    path.join(process.env.LOCALAPPDATA || "", "Google\\Chrome\\Application\\chrome.exe")],
}[process.platform] || [];

export const chromeBinary = () => CHROMES.find((p) => p && fs.existsSync(p)) || null;
// A hostname and nothing else: dot-separated labels of letters, digits and inner hyphens. "..", "/", "", "a/b",
// an absolute path or a drive letter is null, so no input can name a folder outside <home>/browser/.
const HOSTNAME = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/;
export const domainOf = (u) => {
  const s = String(u ?? "").trim();
  let host;
  if (/^https?:\/\//i.test(s)) { try { host = new URL(s).hostname; } catch { return null; } }
  else host = s.replace(/:\d+$/, "");        // a bare name: no scheme, so no path, slash or backslash allowed
  host = host.toLowerCase().replace(/^www\./, "");
  return HOSTNAME.test(host) ? host : null;
};
// <home>/browser/<domain>, or an Error: the folder must sit directly inside <home>/browser/.
export const profileFor = (u) => {
  const d = domainOf(u);
  const root = path.resolve(HOME, "browser");
  const dir = d && path.resolve(root, d);
  if (!dir || path.dirname(dir) !== root) throw new Error(`not a website name: ${JSON.stringify(String(u ?? ""))}`);
  return dir;
};
export const hasProfile = (u) => { try { return fs.existsSync(path.join(profileFor(u), "Default")); } catch { return false; } };
export const FLAGS = ["--no-first-run", "--no-default-browser-check", "--use-mock-keychain", "--password-store=basic"];

// Is this page asking for a login? A redirect to a login path, or a visible password field.
const LOGGED_OUT = `(() => /(^|\\/)(login|log-in|signin|sign-in|auth|sso)(\\/|$|\\?)/i.test(location.pathname)
  || [...document.querySelectorAll('input[type=password]')].some((e) => e.getBoundingClientRect().width > 0)
  || [...document.querySelectorAll('a, button')].some((e) => e.getBoundingClientRect().width > 0 && /^(log ?in|sign ?in)$/i.test((e.innerText || '').trim())))()`;

async function check(url) {
  const bin = chromeBinary();
  if (!hasProfile(url)) return { ok: false, why: `no profile for ${domainOf(url) || url}: run login first` };
  const dir = profileFor(url);
  // headless, on the same profile, over the DevTools pipe
  const proc = spawn(bin, [...FLAGS, "--headless=new", "--remote-debugging-pipe", `--user-data-dir=${dir}`, "about:blank"],
    { stdio: ["ignore", "ignore", "ignore", "pipe", "pipe"] });
  let id = 0, buf = "";
  const waiting = new Map(), events = [];
  proc.stdio[4].on("data", (d) => { buf += d; for (let i; (i = buf.indexOf("\0")) >= 0;) { const m = JSON.parse(buf.slice(0, i)); buf = buf.slice(i + 1);
    if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } else events.push(m); } });
  const send = (method, params = {}, sessionId) => new Promise((ok) => { waiting.set(++id, ok); proc.stdio[3].write(JSON.stringify({ id, method, params, sessionId }) + "\0"); });
  try {
    const { result: { targetId } } = await send("Target.createTarget", { url: "about:blank" });
    const { result: { sessionId } } = await send("Target.attachToTarget", { targetId, flatten: true });
    await send("Page.enable", {}, sessionId);
    await send("Page.navigate", { url }, sessionId);
    await new Promise((r) => setTimeout(r, 6000));
    const r = await send("Runtime.evaluate", { expression: `({ out: ${LOGGED_OUT}, at: location.href, title: document.title })`, returnByValue: true }, sessionId);
    const v = r.result.result.value;
    return { ok: !v.out, at: v.at, title: v.title, why: v.out ? "the page asked for a login" : "logged in" };
  } finally { proc.kill(); }
}

async function login(url, checkUrl) {
  const bin = chromeBinary();
  if (!bin) { console.error("ERROR: no Google Chrome found. Install it, or Chrome for Testing (npx @puppeteer/browsers install chrome@stable)."); process.exit(1); }
  let dir;
  try { dir = profileFor(url); } catch (e) { console.error(`ERROR: ${e.message}`); process.exit(2); }
  fs.mkdirSync(dir, { recursive: true });
  console.log(`A Chrome window is opening on its own profile (${dir}).\nLog in to ${domainOf(url)} there by hand, then close the window.`);
  // headed, the user's hands only; this process waits for the window to close
  const r = spawnSync(bin, [...FLAGS, `--user-data-dir=${dir}`, "--new-window", url], { stdio: "ignore" });
  if (r.error) { console.error(r.error.message); process.exit(1); }
  const v = await check(checkUrl || url);
  console.log(v.ok ? `logged in: ${v.at} (${v.title})` : `NOT logged in: ${v.why} (${v.at}). Run login again.`);
  process.exit(v.ok ? 0 : 1);
}

const [cmd, arg] = process.argv.slice(2);
const flag = (k) => { const a = process.argv, i = a.indexOf(k); return i >= 0 ? a[i + 1] : undefined; };
if ((process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) || process.argv[1]?.endsWith("login.mjs")) {
  if (cmd === "login" && arg) await login(arg, flag("--check"));
  else if (cmd === "check" && arg) { const v = await check(arg); console.log(JSON.stringify(v)); process.exit(v.ok ? 0 : 1); }
  else if (cmd === "logout" && arg) {
    let dir;
    try { dir = profileFor(arg); } catch (e) { console.error(`ERROR: ${e.message}. Give the site, e.g. example.com.`); process.exit(2); }
    if (!fs.existsSync(dir)) { console.log(`no saved login for ${domainOf(arg)}: nothing to delete`); process.exit(0); }
    fs.rmSync(dir, { recursive: true, force: true });
    console.log(`deleted ${dir}: logged out of ${domainOf(arg)} on this computer`);
  }
  else if (cmd === "where" && arg) { try { console.log(profileFor(arg)); } catch (e) { console.error(`ERROR: ${e.message}`); process.exit(2); } }
  else { console.error("usage: node login.mjs login <url> [--check <url>] | check <url> | logout <domain> | where <domain>"); process.exit(2); }
}
