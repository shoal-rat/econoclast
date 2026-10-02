// Record the app in headless Chromium for README media and films.
//
//   node tools/dev/capture.mjs <query> <out.webm> <seconds> [captions.json]
//   node tools/dev/capture.mjs <query> <out.png> <seconds>        (a still, taken after <seconds>)
//
// <query> is appended to http://127.0.0.1:7777/?bridge=http& (run `econoclast app --browser --no-open`).
// captions.json: [{"at": 2.5, "k": "KICKER", "t": "line", "until": 6}, {"at": 0, "card": "<html>", "until": 4},
//                 {"on": "station:forum", "after": 1.5, "dur": 5, "t": "..."}, {"on": "verdict", "dur": 6, "t": "..."},
//                 {"on": "end", "card": "<html>", "dur": 5}]   (event-triggered; "end" fires after the verdict)
// Needs playwright-core (NODE_PATH or a local install) and a Chromium (PW_CHROMIUM or the playwright cache).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { dirname } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");
const [query, out, seconds, captionsFile] = process.argv.slice(2);
const captions = captionsFile ? JSON.parse(readFileSync(captionsFile, "utf8")) : [];
const exe = process.env.PW_CHROMIUM ||
  `${homedir()}/Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell`;

const still = out.endsWith(".png");
const browser = await chromium.launch({ executablePath: exe, headless: true });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: still ? 2 : 1,
  ...(still ? {} : { recordVideo: { dir: dirname(out), size: { width: 1440, height: 900 } } }) });
const page = await ctx.newPage();
await page.goto(`http://127.0.0.1:7777/?bridge=http&${query}`);
await page.addStyleTag({ content: `
  #film-card{position:fixed;inset:0;z-index:99;display:grid;place-items:center;background:#0b1430;color:#f0d58a;
    text-align:center;font:600 34px Cinzel,serif;letter-spacing:.08em;transition:opacity .6s}
  #film-card small{display:block;margin-top:14px;font:italic 500 26px "Cormorant Garamond","Songti SC",serif;color:#efe7d6;letter-spacing:0}
  #film-sub{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:100;max-width:1100px;text-align:center;
    padding:10px 26px;background:rgba(6,9,22,.78);color:#fff;font:500 24px/1.35 "Cormorant Garamond","Songti SC",serif;
    border-top:2px solid #c9a23a;opacity:0;transition:opacity .4s}
  #film-sub b{display:block;font:700 15px Cinzel,serif;letter-spacing:.3em;color:#f0d58a}` });
if (still) {
  await page.waitForTimeout(Number(seconds) * 1000);
  await page.screenshot({ path: out });
  await browser.close();
  console.log(out);
  process.exit(0);
}
const t0 = Date.now();
const shown = new Set();
const fired = {};  // trigger -> time it first became true
let endAt = Infinity;
while ((Date.now() - t0) / 1000 < Math.min(Number(seconds), endAt)) {
  const now = (Date.now() - t0) / 1000;
  const state = await page.evaluate(() => ({
    station: document.querySelector(".station.now")?.dataset.k || "",
    verdict: !!document.querySelector(".medallion"),
  }));
  if (state.station && fired[`station:${state.station}`] === undefined) fired[`station:${state.station}`] = now;
  if (state.verdict && fired.verdict === undefined) fired.verdict = now;
  for (const c of captions) {
    if (!c.on) continue;
    const base = c.on === "end" ? (fired.verdict === undefined ? undefined : fired.verdict + 9) : fired[c.on];
    if (base !== undefined && c.at === undefined) { c.at = base + (c.after || 0); c.until = c.at + (c.dur || 5); }
    if (c.on === "end" && c.at !== undefined) endAt = c.until + 0.5;
  }
  for (const [i, c] of captions.entries()) {
    if (c.at === undefined) continue;
    const on = now >= c.at && now < (c.until ?? c.at + 4);
    if (on === shown.has(i)) continue;
    if (on) shown.add(i); else shown.delete(i);
    await page.evaluate(([c, on, i]) => {
      const id = c.card ? "film-card" : "film-sub";
      let el = document.getElementById(id);
      if (!el) { el = document.createElement("div"); el.id = id; document.body.appendChild(el); }
      if (on) { el.innerHTML = c.card || `${c.k ? `<b>${c.k}</b>` : ""}${c.t}`; el.style.opacity = 1; el.dataset.i = i; }
      else if (el.dataset.i === String(i)) el.style.opacity = 0;
    }, [c, on, i]);
  }
  await page.waitForTimeout(100);
}
const video = page.video();
await ctx.close();
await browser.close();
const path = await video.path();
const { renameSync } = await import("node:fs");
renameSync(path, out);
console.log(out);
