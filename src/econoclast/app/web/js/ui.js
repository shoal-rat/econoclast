// The chrome around the wall: the procession frieze, the chronicle, the HUD and the plea.

import { api, isNative } from "./bridge.js";
import { escapeHtml } from "./director.js";
import { bandFor, bandText, blurb, bladeName, getLang, getWorld, stationName, t } from "./i18n.js";

const getLangText = (x) => (getLang() === "zh" ? x.zh : x.en);

// The seal follows the integrity blades exactly as the engine's score does.
export function sealFor(wounds) {
  const w = getWorld();
  const blades = (w && w.integrity_blades) || [];
  const integ = wounds.filter((x) => blades.includes(x.blade));
  if (integ.some((x) => ["high", "critical"].includes(x.severity) && (x.effective_confidence ?? x.confidence) >= 0.6)) return "fractum";
  if (integ.some((x) => x.severity !== "info")) return "dubium";
  return "integrum";
}
import { md } from "./md.js";
import { sfx } from "./sfx.js";

const $ = (s) => document.querySelector(s);
const STATION_ICON = { classis: "res/navis", scriptorium: "res/codex", forum: "res2/denarius", horreum: "res/amphora",
  fabrica: "res2/anvil", palatium: "res2/shield", aula: "res2/star", curia: "res/libra" };
const FAMILY_ICON = { read: "scroll", write: "codex", web: "navis", search: "lamp", browser: "navis", spawn: "sica",
  plan: "codex", mcp: "lamp", shell: "sica", arsenal: "libra", other: "lamp" };

export function toast(msg, ms = 3200) {
  const el = $("#toast");
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toast.t); toast.t = setTimeout(() => el.classList.remove("show"), ms);
}

// ---------------------------------------------------------------- frieze
export class Frieze {
  constructor(el) { this.el = el; this.cur = null; this.seen = new Set(); this.render(); }
  render() {
    const w = getWorld();
    if (!w) return;
    this.el.innerHTML = w.stations.map((s) => `
      <div class="station" data-k="${s.key}" title="">
        <div class="medal"><img src="assets/${STATION_ICON[s.key] || "res/scroll"}.png" alt=""></div>
        <div class="nm">${s.latin}</div>
      </div>`).join("");
    this.refresh();
  }
  reset() { this.cur = null; this.seen.clear(); this.refresh(); }
  set(key, note) {
    if (this.cur) this.seen.add(this.cur);
    this.cur = key;
    this.note = note;
    this.refresh();
  }
  refresh() {
    const w = getWorld();
    if (!w) return;
    const order = w.stations.map((s) => s.key);
    const ci = order.indexOf(this.cur);
    this.el.querySelectorAll(".station").forEach((el) => {
      const k = el.dataset.k, i = order.indexOf(k);
      el.classList.toggle("now", k === this.cur);
      el.classList.toggle("done", this.seen.has(k) || (ci > i && i >= 0));
      const n = stationName(k);
      el.title = `${n.latin} · ${n.tr}\n${n.act}`;
    });
  }
}

// ------------------------------------------------------------- chronicle
export class Chronicle {
  constructor(list, meta) { this.list = list; this.meta = meta; this.stick = true; this.lastTool = null;
    list.addEventListener("scroll", () => { this.stick = list.scrollTop + list.clientHeight > list.scrollHeight - 40; }); }
  reset() { this.list.innerHTML = ""; this.meta.textContent = ""; this.t0 = null; }
  li(cls, html) {
    const li = document.createElement("li");
    li.className = cls; li.innerHTML = html;
    this.list.appendChild(li);
    if (this.list.children.length > 900) this.list.firstChild.remove();
    if (this.stick) this.list.scrollTop = this.list.scrollHeight;
    return li;
  }
  clock(ev) {
    if (!this.t0) this.t0 = ev.ts;
    const s = Math.max(0, Math.round(ev.ts - this.t0));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }
  add(ev) {
    const k = ev.kind;
    const time = this.clock(ev);
    if (k === "station") {
      const n = stationName(ev.station);
      this.li("c-st", `${n.latin} <small>${escapeHtml(n.tr)} · ${time}${ev.note ? " · " + escapeHtml(ev.note) : ""}</small>`);
    } else if (k === "narrate") {
      const who = ev.who && ev.who !== "sicarius" ? `<span class="who">${ev.who === "econoclast" ? "ECONOCLAST" : t("conspirator")}</span>` : "";
      this.li("c-say md", who + md(ev.text));
    } else if (k === "tool") {
      if (ev.name === "ToolSearch" || ev.name === "TodoWrite") return;
      const fam = (ev.family || "other").split(":")[0];
      const icon = FAMILY_ICON[fam] || "lamp";
      const text = fam === "arsenal" ? ev.summary : ev.summary || ev.name;
      const last = this.list.lastElementChild;
      if (last && last === this.lastTool && last.dataset.text === text) {
        const n = Number(last.dataset.n || 1) + 1;
        last.dataset.n = n;
        last.querySelector("b")?.remove();
        last.insertAdjacentHTML("beforeend", `<b class="times">×${n}</b>`);
        last.dataset.id = ev.id || "";
        return;
      }
      this.lastTool = this.li("c-tool", `<img src="assets/res/${icon}.png" alt=""><span>${escapeHtml(text)}</span>`);
      this.lastTool.dataset.id = ev.id || "";
      this.lastTool.dataset.text = text;
    } else if (k === "tool.done" && !ev.ok) {
      const el = [...this.list.querySelectorAll(".c-tool")].reverse().find((x) => x.dataset.id === String(ev.id));
      if (el) { el.classList.add("err"); if (ev.error) el.title = ev.error; }
    } else if (k === "wound") {
      const w = ev.wound, b = bladeName(w.blade);
      const dots = sevDots(w.severity);
      this.li("c-card", `<div class="k">${b.latin} · ${escapeHtml(b.tr)} ${dots}</div><div class="t">${escapeHtml(w.title)}</div>
        ${w.quote ? `<q>${escapeHtml(w.quote.slice(0, 220))}</q>` : ""}`);
    } else if (k === "parry") {
      const b = bladeName(ev.parry.blade);
      this.li("c-card parry", `<div class="k">${b.latin} · ⛨</div><div class="t">${escapeHtml(ev.parry.note)}</div>`);
    } else if (k === "plea") {
      this.li("c-card plea", `<div class="k">${t("plea_card")}</div><div class="t">${escapeHtml(ev.what)}</div><q>${escapeHtml(ev.why)}</q>`);
    } else if (k === "plea.answered") {
      this.li("c-tool", `<span>${ev.declined || ev.timeout ? t("plea_declined") : t("plea_answered")}${(ev.files || []).length ? ": " + escapeHtml(ev.files.join(", ")) : ""}</span>`);
    } else if (k === "speculum") {
      this.li("c-card info", `<div class="k">Speculum · ${t(ev.verdict)}</div><div class="t">${escapeHtml(ev.what)}: ${t("paper_val")} ${ev.paper_value} · ${t("ours")} ${ev.reproduced_value}</div>`);
    } else if (k === "viae" && ev.status === "done") {
      const s = ev.summary || {};
      this.li("c-card info", `<div class="k">Mille Viae</div><div class="t">${s.n_specs_run} ${t("roads")} · ${Math.round((s.share_significant_expected_sign || 0) * 100)}% ${t("sig_share")}</div>`);
    } else if (k === "intel" && ev.about === "field") {
      this.li("c-card info", `<div class="k">Forum · ${t("field_brief")}</div><div class="t">${escapeHtml(ev.field || "")}</div>
        <q>${escapeHtml(ev.setting || "")}</q>`);
    } else if (k === "intel" && ["forensics", "versions", "code"].includes(ev.about)) {
      const head = ev.about === "forensics" ? `Falsum · ${ev.scope === "data" ? t("data_screen") : t("paper_screen")}`
        : ev.about === "versions" ? `Palimpsestus · ${escapeHtml(ev.earlier)} → ${escapeHtml(ev.later)}` : `Codex · ${t("code_audit")}`;
      const body = ev.about === "forensics" ? `${ev.n_flags} ${t("flags")}${(ev.tests || []).length ? ": " + escapeHtml(ev.tests.join(", ")) : ""}`
        : ev.about === "versions" ? `${ev.rewritten} ${t("rewritten")} · ${ev.removed} ${t("removed")} · ${ev.added} ${t("added")}`
          : `${ev.n_steps} ${t("data_steps")} · ${ev.n_files} ${t("files")}`;
      this.li("c-card info", `<div class="k">${head}</div><div class="t">${body}</div>`);
    } else if (k === "intel" && ev.about === "paper") {
      this.li("c-card info", `<div class="k">${t("the_decree")}</div><div class="t">${escapeHtml(ev.title)}</div>`);
    } else if (k === "intel" && ev.about === "target") {
      this.li("c-card info", `<div class="k">${t("decree")}</div><div class="t">${escapeHtml(ev.claim)}</div>`);
    } else if (k === "spawn") {
      this.li("c-tool", `<img src="assets/res/sica.png" alt=""><span>${t("conspirator")}: ${escapeHtml(ev.task || "")}</span>`);
    } else if (k === "busy") {
      const el = [...this.list.querySelectorAll(".c-tool")].reverse().find((x) => x.dataset.id === String(ev.id));
      const mins = Math.round(ev.seconds / 60);
      if (el) {
        el.querySelector(".busy")?.remove();
        el.insertAdjacentHTML("beforeend", `<b class="times busy">${t("still_running")} · ${mins} min</b>`);
      }
    } else if (k === "packed") {
      this.li("c-tool", `<img src="assets/res/amphora.png" alt=""><span>${t("vault")}: ${ev.files} · ${ev.before_mb} MB → ${ev.after_mb} MB</span>`);
    } else if (k === "usage") {
      const bits = [];
      if (ev.cost_usd) bits.push(`$${Number(ev.cost_usd).toFixed(2)}`);
      if (ev.turns) bits.push(`${ev.turns} ${t("turns")}`);
      if (ev.input_tokens) bits.push(`${Math.round((ev.input_tokens + (ev.output_tokens || 0)) / 1000)}k ${t("tokens")}`);
      this.meta.textContent = bits.join(" · ");
    } else if (k === "final") {
      this.li("c-card final md", `<div class="k">${t("final_msg")}</div>${md(ev.text)}`);
    } else if (k === "case.closed" && ev.status !== "done") {
      this.li("c-card", `<div class="k">${t(ev.status)}</div><div class="t">${escapeHtml(ev.error || (ev.status === "aborted" ? t("hunt_aborted") : t("hunt_failed")))}</div>`);
    }
  }
}

export function sevDots(sev) {
  const n = { info: 0, low: 1, medium: 2, high: 3, critical: 4 }[sev] || 0;
  return `<span class="sev">${[0, 1, 2, 3].map((i) => `<i class="${i < n ? "" : "o"}"></i>`).join("")}</span>`;
}

// ------------------------------------------------------------------- hud
export class Hud {
  constructor() { this.tiles = $("#wound-tiles"); this.fill = $("#halo-fill"); this.num = $("#halo-num"); this.decree = $("#decree-text");
    this.sealEl = $("#seal"); }
  reset() { this.tiles.innerHTML = ""; this.set([], [], 0); this.decree.textContent = "—"; this.seal("integrum"); }
  seal(key) {
    const w = getWorld();
    const s = ((w && w.seals) || []).find((x) => x.key === key) || { latin: "", en: "", zh: "" };
    this.sealEl.className = `seal-ind ${key}`;
    this.sealEl.title = `${s.latin} · ${getLangText(s)}`;
    this.sealEl.querySelector("span").textContent = getLangText(s);
  }
  set(wounds, parries, score) {
    this.tiles.innerHTML = wounds.map((w) => `<i class="${w.severity}" title="${escapeHtml(w.title)}"></i>`).join("") +
      parries.map((p) => `<i class="parry" title="${escapeHtml(p.note)}"></i>`).join("");
    this.fill.style.width = `${Math.min(100, score)}%`;
    this.num.textContent = Math.round(score);
  }
}

// ------------------------------------------------------------------ plea
export class Plea {
  constructor(app) {
    this.app = app; this.el = $("#plea"); this.cur = null; this.files = []; this.uploads = [];
    $("#plea-pick").onclick = () => this.pick();
    $("#plea-send").onclick = () => this.send(false);
    $("#plea-decline").onclick = () => this.send(true);
    const drop = $("#plea-drop");
    drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", async (e) => {
      e.preventDefault(); drop.classList.remove("over");
      for (const f of e.dataTransfer.files) await this.take(f);
    });
  }
  open(ev) {
    if (this.app.demo) return;
    this.cur = ev; this.files = []; this.uploads = [];
    $("#plea-what").textContent = ev.what; $("#plea-why").textContent = ev.why;
    $("#plea-where").textContent = ev.where || ""; $("#plea-picked").textContent = ""; $("#plea-url").value = "";
    this.el.hidden = false;
    sfx.play("bell");
  }
  close(id) { if (!this.cur || !id || this.cur.plea_id === id) { this.el.hidden = true; this.cur = null; } }
  async pick() {
    if (isNative()) {
      const p = await api.pick_file("any");
      if (p) { this.files.push(p); $("#plea-picked").textContent = this.files.map((f) => f.split("/").pop()).join(", "); }
      return;
    }
    const inp = $("#file-fallback");
    inp.onchange = async () => { for (const f of inp.files) await this.take(f); inp.value = ""; };
    inp.click();
  }
  async take(file) {
    if (file.pywebviewFullPath) this.files.push(file.pywebviewFullPath);
    else this.uploads.push({ name: file.name, b64: await toB64(file) });
    $("#plea-picked").textContent = [...this.files.map((f) => f.split("/").pop()), ...this.uploads.map((u) => u.name)].join(", ");
  }
  async send(declined) {
    if (!this.cur) return;
    const url = $("#plea-url").value.trim();
    if (!declined && !this.files.length && !this.uploads.length && !url) { toast(t("no_paper")); return; }
    await api.answer_plea(this.app.caseId, this.cur.plea_id, { files: this.files, uploads: this.uploads, url, declined });
    this.close();
  }
}

export function toB64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result));
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}

// -------------------------------------------------------------- verdict
export function medallion(stage, f, instant) {
  const b = bandFor(f.score);
  const el = document.createElement("div");
  el.className = "medallion";
  const sealKey = f.seal || "integrum";
  const sl = ((getWorld() || {}).seals || []).find((x) => x.key === sealKey);
  el.innerHTML = `<div><div class="score">${Math.round(f.score)}</div><div class="latin">${b ? b.latin : ""}</div>
    <div class="tr">${escapeHtml(bandText(b))}</div>
    ${sl ? `<div class="seal-line ${sealKey}">${escapeHtml(sl.latin)} · ${escapeHtml(getLangText(sl))}</div>` : ""}</div>`;
  stage.ov.querySelectorAll(".medallion").forEach((x) => x.remove());
  stage.ov.appendChild(el);
  if (!instant) setTimeout(() => el.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 1200, fill: "forwards" }), 14000);
  return { band: b, blurb: blurb(b) };
}

// ------------------------------------------------------------- clepsydra
// The Roman water clock in the corner of the wall: how far the hunt has come, what the
// Sicarius is doing right now, and whether it is alive.
export class Clepsydra {
  constructor(el, director) {
    this.el = el; this.d = director;
    el.innerHTML = `<div class="vessel"><i class="water"></i><b class="drop"></b></div>
      <div class="cl-text"><div class="cl-head"><span class="cl-st"></span><span class="cl-steps"></span><span class="cl-pct"></span></div>
      <div class="cl-now"></div><div class="cl-live"><i class="dot"></i><span class="cl-state"></span><span class="cl-el"></span></div></div>`;
    this.lastSignal = 0;
    setInterval(() => this.render(), 1000);
  }
  render() {
    if (!this.el.offsetParent) return;
    const s = this.d.snapshot();
    const $q = (c) => this.el.querySelector(c);
    const n = stationName(s.station);
    $q(".cl-st").textContent = n.latin;
    $q(".cl-steps").textContent = s.totalHere ? `${s.doneHere}/${s.totalHere}` : "";
    $q(".cl-pct").textContent = `${Math.round(s.overall * 100)}%`;
    $q(".water").style.height = `${Math.max(4, s.overall * 100)}%`;
    $q(".cl-now").innerHTML = s.activity ? `${escapeHtml(s.activity)} <em>${fmt(s.activityFor)}</em>` : "…";
    let state, cls;
    if (s.closed) { state = t(s.closed === "done" ? "cl_done" : "cl_stopped"); cls = s.closed === "done" ? "done" : "stopped"; }
    else if (s.quiet < 20) { state = t("cl_working"); cls = "ok"; }
    else if (s.busyFresh) { state = `${t("cl_long")} · ${Math.round(s.busySecs / 60)} min`; cls = "wait"; }
    else if (s.quiet < 180) { state = t("cl_thinking"); cls = "wait"; }
    else { state = `${t("cl_quiet")} ${Math.round(s.quiet / 60)} min`; cls = "quiet"; }
    this.el.dataset.state = cls;
    $q(".cl-state").textContent = state;
    $q(".cl-el").textContent = ` · ${fmt(s.elapsed)}`;
    if (this.d.lastSignal !== this.lastSignal) {   // a drop falls for every sign of life
      this.lastSignal = this.d.lastSignal;
      const drop = $q(".drop");
      drop.classList.remove("fall"); void drop.offsetWidth; drop.classList.add("fall");
    }
  }
}

function fmt(sec) {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), x = sec % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
}
