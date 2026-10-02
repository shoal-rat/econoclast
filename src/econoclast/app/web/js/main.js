// Econoclast · the app controller: views, the hunt loop, demos and the archive.

import { api, connect, isNative } from "./bridge.js";
import { Director, LAYOUT, escapeHtml } from "./director.js";
import { bandFor, getLang, setLang, setWorld, t } from "./i18n.js";
import { prologue } from "./prologue.js";
import { sfx } from "./sfx.js";
import { Assets, Stage } from "./stage.js";
import { renderTabula } from "./tabula.js";
import { Chronicle, Clepsydra, Frieze, Hud, Plea, medallion, sealFor, toB64, toast } from "./ui.js";

const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const app = {
  view: "boot", caseId: null, since: 0, poll: null, demo: false, hello: null,
  offer: { paperFile: null, paperUpload: null, dataFile: null, dataUpload: null, backend: "auto", depth: "thorough" },
};

function setView(v) {
  app.view = v;
  $("#app").dataset.view = v;
  fit();
}

// keep the 1600x900 wall at 16:9: letterboxed in the theatre, cropped to cover elsewhere
function fit() {
  const box = $("#stage-box"), inner = $("#stage-inner");
  const r = box.getBoundingClientRect();
  const cover = app.view === "prologue" || app.view === "atrium";
  const s = cover ? Math.max(r.width / 1600, r.height / 900) : Math.min(r.width / 1600, r.height / 900);
  inner.style.transform = `translate(${(r.width - 1600 * s) / 2}px, ${(r.height - 900 * s) / 2}px) scale(${s})`;
}
new ResizeObserver(fit).observe(document.body);

// ------------------------------------------------------------------- boot
async function boot() {
  await connect();
  const hello = await api.hello();
  app.hello = hello;
  setWorld(hello.world);
  setLang(new URLSearchParams(location.search).get("lang") || (hello.prefs && hello.prefs.lang) || hello.lang);
  sfx.set(!(hello.prefs && hello.prefs.sound === false));
  $("#btn-sound").classList.toggle("off", !sfx.on);
  doctorGem(hello.doctor);

  app.assets = await new Assets().load();
  app.stage = new Stage($("#stage"), $("#overlay"), app.assets);
  app.frieze = new Frieze($("#frieze"));
  app.chronicle = new Chronicle($("#chron-list"), $("#chron-meta"));
  app.hudView = new Hud();
  app.plea = new Plea(app);
  app.director = new Director(app.stage, {
    chronicle: app.chronicle, frieze: app.frieze,
    setTitle: () => {},
    setDecree: (txt) => { $("#decree-text").textContent = txt || "—"; },
    hud: (w, p, s) => app.hudView.set(w, p, s),
    seal: (wounds, f) => app.hudView.seal((f && f.seal) || sealFor(wounds)),
    openPlea: (ev) => app.plea.open(ev),
    closePlea: (id) => app.plea.close(id),
    medallion: (f, instant) => medallion(app.stage, f, instant),
    closed: (ev, instant) => onClosed(ev, instant),
  });
  app.clepsydra = new Clepsydra($("#clepsydra"), app.director);
  wireChrome();
  wireOffer();
  window.__nativeDrop = nativeDrop;

  // developer deep links (screenshots, debugging): ?view=atrium | ?case=<id>[&view=tabula][&at=<seq>]
  const q = new URLSearchParams(location.search);
  if (q.get("case")) return openMoment(q.get("case"), q.get("view"), q.get("at"),
    { replay: q.get("replay"), from: q.get("from"), speed: Number(q.get("speed") || 1) });
  if (q.get("view") === "atrium") return atrium();
  if (q.get("view") === "prologue") return runPrologue();
  const seen = hello.prefs && hello.prefs.seen_prologue;
  if (!seen) await runPrologue();
  else atrium();
}

async function openMoment(id, view, at, { replay, from, speed = 1 } = {}) {
  if (view === "tabula") return openTabula(id);
  const r = await api.events(id, 0);
  if (replay) {
    const start = Number(from || 0);
    return playRecorded(r.events, { caseId: id, speed, skipTo: start });
  }
  const evs = at ? r.events.filter((e) => e.seq <= Number(at)) : r.events;
  app.caseId = id; app.demo = true;
  resetTheatre();
  $("#btn-abort").hidden = true;
  setView("theatre");
  await app.director.fastForward(evs.slice(0, -3));
  app.director.enqueue(evs.slice(-3));
}

function doctorGem(d) {
  const gem = $("#agent-gem");
  gem.className = `gem ${d.backend ? "ok" : "bad"}`;
  gem.title = d.backend ? `${t("agent_ok")}: ${d.backend}` : t("agent_missing");
}

// -------------------------------------------------------------- prologue
async function runPrologue() {
  setView("prologue");
  let skip;
  const skipSignal = new Promise((r) => { skip = r; });
  $("#skip").onclick = () => skip();
  await prologue(app.stage, { skipSignal });
  api.set_pref("seen_prologue", true);
  atrium();
}

// ---------------------------------------------------------------- atrium
async function atrium() {
  stopPolling();
  app.demo = false; app.caseId = null;
  setView("atrium");
  const st = app.stage;
  st.setDim(0); st.clearFx(); st.clearOverlay(); st.clearActors();
  st.setScene("palatium", { flip: true, origin: [1600, 450] });
  const L = LAYOUT.palatium;
  st.ground = L.ground;
  st.actor("emp", { sheet: "imperator", frame: "idle", x: 1000, y: 640, scale: 0.84 });
  ["a", "b", "a"].forEach((s, i) => st.actor(`g${i}`, { sheet: "custodes", frame: `${s}_idle`, x: 1180 + i * 150,
    y: L.ground - (i % 2) * 14, scale: 0.78, z: L.ground }));
  st.actor("sic", { sheet: "sicarius", frame: "sneak", x: 820, y: 860, scale: 1, flip: false });
  idleLoop();
  renderRecent();
}

let idleTimer = null;
function idleLoop() {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (app.view !== "atrium") return;
    const st = app.stage, r = Math.random();
    if (r < 0.3) { st.pose("emp", "decree"); setTimeout(() => app.view === "atrium" && st.pose("emp", "idle"), 2600); }
    else if (r < 0.55) { st.pose("sic", "idle"); setTimeout(() => app.view === "atrium" && st.pose("sic", "sneak"), 2200); }
    else if (r < 0.75) { const g = `g${Math.floor(Math.random() * 3)}`; const a = st.get(g);
      if (a) { const s = a.frame[0]; st.pose(g, `${s}_block`); setTimeout(() => app.view === "atrium" && st.pose(g, `${s}_idle`), 1600); } }
    idleLoop();
  }, 3800 + Math.random() * 2500);
}

async function renderRecent() {
  const cases = await api.list_cases();
  const box = $("#recent");
  if (!cases.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<h3>${t("recent")}</h3>` + cases.slice(0, 3).map(caseCard).join("");
  box.querySelectorAll(".case-card").forEach((el) => { el.onclick = () => openCase(el.dataset.id); });
}

function caseCard(c) {
  const run = ["running", "starting"].includes(c.status);
  const fail = ["failed", "aborted", "interrupted"].includes(c.status);
  const b = c.score !== null && c.score !== undefined ? bandFor(c.score) : null;
  const seal = run ? "…" : c.score !== null && c.score !== undefined ? Math.round(c.score) : "—";
  return `<div class="case-card" data-id="${escapeHtml(c.id)}">
    <div class="seal ${run ? "run" : fail ? "fail" : ""}">${seal}</div>
    <div><div class="tt">${escapeHtml(c.title || c.paper_input || c.id)}</div>
    <div class="st">${t(c.status || "new")}${b ? ` · ${b.latin}` : ""}</div></div></div>`;
}

// ------------------------------------------------------------- the offer
function wireOffer() {
  const segAgent = $("#seg-agent"), segDepth = $("#seg-depth");
  const d = app.hello.doctor;
  const agents = [["auto", t("auto"), !!d.backend], ["claude", "Claude Code", !!d.claude], ["codex", "Codex", !!d.codex]];
  segAgent.innerHTML = `<span class="lab">${t("agent")}</span>` + agents.map(([k, l, ok]) =>
    `<button type="button" data-k="${k}" ${ok ? "" : "disabled"} class="${k === app.offer.backend ? "on" : ""}">${l}</button>`).join("");
  segDepth.innerHTML = `<span class="lab">${t("depth")}</span>` + [["thorough", t("thorough")], ["swift", t("swift")]].map(([k, l]) =>
    `<button type="button" data-k="${k}" class="${k === app.offer.depth ? "on" : ""}">${l}</button>`).join("");
  segAgent.onclick = (e) => { const b = e.target.closest("button"); if (!b || b.disabled) return; app.offer.backend = b.dataset.k; wireOffer(); };
  segDepth.onclick = (e) => { const b = e.target.closest("button"); if (!b) return; app.offer.depth = b.dataset.k; wireOffer(); };
  $("#pick-paper").onclick = () => pickInto("paper");
  $("#pick-data").onclick = () => pickInto("data");
  $("#offer").onsubmit = (e) => { e.preventDefault(); unleash(); };
  $("#demo").onclick = () => runDemo();
}

async function pickInto(kind) {
  if (isNative()) {
    const p = await api.pick_file(kind);
    if (p) setPicked(kind, p, null);
    return;
  }
  const inp = $("#file-fallback");
  inp.onchange = async () => { const f = inp.files[0]; if (f) setPicked(kind, null, { name: f.name, b64: await toB64(f) }); inp.value = ""; };
  inp.click();
}
function setPicked(kind, path, upload) {
  const name = path ? path.split("/").pop() : upload.name;
  if (kind === "paper") { app.offer.paperFile = path; app.offer.paperUpload = upload; $("#paper-picked").textContent = name; }
  else { app.offer.dataFile = path; app.offer.dataUpload = upload; $("#data-picked").textContent = name; $("#more").open = true; }
}
const DATA_EXT = /\.(csv|dta|xlsx?|parquet|tsv|zip|sav|rds|feather)$/i;
function nativeDrop(paths) {
  if (!$("#plea").hidden) { app.plea.files.push(...paths); $("#plea-picked").textContent = app.plea.files.map((f) => f.split("/").pop()).join(", "); return; }
  if (app.view !== "atrium") return;
  for (const p of paths) setPicked(DATA_EXT.test(p) ? "data" : "paper", p, null);
}
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", async (e) => {
  e.preventDefault();
  if (isNative() || !$("#plea").hidden || app.view !== "atrium") return;
  for (const f of e.dataTransfer.files) setPicked(DATA_EXT.test(f.name) ? "data" : "paper", null, { name: f.name, b64: await toB64(f) });
});

async function unleash() {
  sfx.unlock();
  const paper = $("#in-paper").value.trim();
  const o = app.offer;
  if (!paper && !o.paperFile && !o.paperUpload) { $("#offer-note").textContent = t("no_paper"); return; }
  $("#go").disabled = true; $("#offer-note").textContent = "";
  try {
    const res = await api.begin({ paper, paper_file: o.paperFile, paper_upload: o.paperUpload, data_file: o.dataFile,
      data_upload: o.dataUpload, claim: $("#in-claim").value.trim(), lang: getLang(), backend: o.backend, depth: o.depth });
    if (!res.ok) { $("#offer-note").textContent = t(res.error); return; }
    $("#in-paper").value = ""; $("#in-claim").value = "";
    Object.assign(o, { paperFile: null, paperUpload: null, dataFile: null, dataUpload: null });
    $("#paper-picked").textContent = ""; $("#data-picked").textContent = "";
    startTheatre(res.case_id, []);
  } finally { $("#go").disabled = false; }
}

// --------------------------------------------------------------- theatre
function resetTheatre() {
  const d = app.director;
  d.reset(); d.speed = 1; d.live = !app.demo;
  app.chronicle.reset(); app.hudView.reset(); app.frieze.reset();
  app.stage.clearActors(); app.stage.clearOverlay(); app.stage.clearFx(); app.stage.setDim(0);
  $("#btn-abort").hidden = false;
  document.querySelectorAll(".read-tabula").forEach((e) => e.remove());
}

async function startTheatre(caseId, existing) {
  stopPolling();
  clearTimeout(idleTimer);
  app.caseId = caseId; app.demo = false; app.since = 0;
  resetTheatre();
  setView("theatre");
  if (existing.length) {
    await app.director.fastForward(existing);
    app.since = existing[existing.length - 1].seq + 1;
  }
  app.poll = setInterval(pollOnce, 700);
  pollOnce();
}
function stopPolling() { if (app.poll) clearInterval(app.poll); app.poll = null; }
async function pollOnce() {
  if (!app.caseId || app.demo) return;
  if (pollOnce.busy) return;
  pollOnce.busy = true;
  try {
    const r = await api.events(app.caseId, app.since);
    if (r.events.length) { app.since = r.events[r.events.length - 1].seq + 1; app.director.enqueue(r.events); }
    if (["done", "failed", "aborted", "interrupted"].includes(r.status) && !r.events.length && !app.director.running) stopPolling();
  } catch (e) { console.warn(e); }
  finally { pollOnce.busy = false; }
}

function onClosed(ev, instant) {
  $("#btn-abort").hidden = true;
  if (ev.status === "done" || app.demo) {
    setTimeout(() => showReadButton(), instant ? 0 : 3500);
  } else {
    toast(ev.status === "aborted" ? t("hunt_aborted") : t("hunt_failed"), 6000);
    showReadButton(true);
  }
}
function showReadButton(failed = false) {
  if (document.querySelector(".read-tabula")) return;
  const b = document.createElement("button");
  b.className = "tessera read-tabula";
  b.textContent = failed ? t("back") : t("read_tabula");
  b.style.cssText = "position:absolute;right:40px;bottom:36px;z-index:6";
  b.onclick = () => (failed && !app.demo ? (app.caseId ? openTabula(app.caseId) : atrium()) : app.demo ? openDemoTabula() : openTabula(app.caseId));
  $("#stage-box").appendChild(b);
}

// ------------------------------------------------------------- archive
async function openCase(id) {
  const data = await api.open_case(id);
  if (["running", "starting"].includes(data.status)) {
    const r = await api.events(id, 0);
    return startTheatre(id, r.events);
  }
  if (data.verdict || (data.wounds || []).length) return openTabula(id, data);
  const r = await api.events(id, 0);
  startTheatre(id, r.events);
}
async function openTabula(id, data) {
  stopPolling();
  const d = data || (await api.open_case(id));
  setView("tabula");
  renderTabula($("#tabula"), d, { assets: app.assets, onBack: atrium, onReplay: () => replayCase(id) });
}
async function replayCase(id) {
  const r = await api.events(id, 0);
  playRecorded(r.events, { caseId: id });
}
async function openArchive() {
  stopPolling();
  setView("archive");
  const cases = await api.list_cases();
  $("#archive").innerHTML = `<div class="arch-list"><h1>${t("archive_title")}</h1>${cases.length ? cases.map(caseCard).join("") : `<p>${t("empty_archive")}</p>`}</div>`;
  $("#archive").querySelectorAll(".case-card").forEach((el) => { el.onclick = () => openCase(el.dataset.id); });
}

// ---------------------------------------------------------------- demos
async function runDemo() {
  sfx.unlock();
  const demo = await api.demo(getLang());
  if (!demo.events || !demo.events.length) { toast("No demonstration recorded."); return; }
  app.demoData = demo;
  playRecorded(demo.events, { demo: true });
}
async function playRecorded(events, { demo = false, caseId = null, speed = 1, skipTo = 0 } = {}) {
  stopPolling();
  clearTimeout(idleTimer);
  app.demo = true; app.caseId = caseId;
  resetTheatre();
  $("#btn-abort").hidden = true;
  setView("theatre");
  if (demo) toast(t("demo_banner"), 4000);
  const token = (app.playToken = Symbol("play"));
  app.director.speed = speed;
  if (skipTo) await app.director.fastForward(events.filter((e) => e.seq < skipTo));
  const rest = skipTo ? events.filter((e) => e.seq >= skipTo) : events;
  const t0 = rest.length ? rest[0].ts : 0;
  let prev = t0;
  for (const ev of rest) {
    if (app.playToken !== token || app.view !== "theatre") return;
    const gap = Math.max(0, ev.ts - prev);
    prev = ev.ts;
    const wait = Math.min(2600, 120 + Math.sqrt(gap) * 260) / speed;
    if (["narrate", "wound", "parry", "station", "verdict", "viae", "speculum", "plea"].includes(ev.kind)) await sleep(wait);
    else await sleep(Math.min(500, wait / 3));
    app.director.enqueue([ev]);
    while (app.director.running && app.director.queue.length > 2) await sleep(80);
  }
}
function openDemoTabula() {
  if (!app.demoData) return atrium();
  const d = { ...app.demoData.tabula, meta: app.demoData.meta };
  setView("tabula");
  renderTabula($("#tabula"), d, { assets: app.assets, onBack: atrium, onReplay: runDemo, demo: true });
}

// ------------------------------------------------------------- chrome
function wireChrome() {
  document.querySelectorAll("[data-go=atrium]").forEach((el) => { el.onclick = () => { app.playToken = null; atrium(); }; });
  $("#btn-archive").onclick = () => { app.playToken = null; openArchive(); };
  $("#btn-prologue").onclick = () => { app.playToken = null; stopPolling(); runPrologue(); };
  $("#btn-lang").onclick = () => {
    const l = getLang() === "zh" ? "en" : "zh";
    setLang(l); api.set_pref("lang", l); $("#btn-lang").textContent = l === "zh" ? "EN" : "中";
    app.frieze.render(); wireOffer();
    if (app.view === "atrium") renderRecent();
  };
  $("#btn-lang").textContent = getLang() === "zh" ? "EN" : "中";
  $("#btn-sound").onclick = () => { sfx.set(!sfx.on); api.set_pref("sound", sfx.on); $("#btn-sound").classList.toggle("off", !sfx.on); };
  $("#btn-abort").onclick = async () => {
    if (!app.caseId || app.demo) return;
    if (!confirm(t("confirm_abort"))) return;
    await api.abort(app.caseId);
  };
}

boot().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML("beforeend", `<pre style="position:fixed;left:20px;bottom:20px;color:#f88;z-index:99">${escapeHtml(e.stack || e)}</pre>`);
});
