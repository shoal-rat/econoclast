// The director turns the hunt's events into choreography on the mosaic wall.
// Every event is played in order; when the agent outpaces the animation, the backlog is
// applied instantly so the wall never falls behind the truth.

import { attemptLabel, bandFor, bladeName, getLang, regionLabel, sevWeight, stationName, t } from "./i18n.js";
import { clamp, rand } from "./stage.js";
import { plain } from "./md.js";
import { sfx } from "./sfx.js";

const GLYPH = (n) => (n.includes("/") ? `assets/${n}.png` : `assets/res/${n}.png`);
const FAMILY_GLYPH = { read: "scroll", write: "codex", web: "navis", search: "lamp", browser: "navis",
  spawn: "sica", plan: "codex", mcp: "lamp" };
const ARSENAL_GLYPH = { fetch_paper: "navis", read_paper: "scroll", mark_target: "scroll", verify_quote: "codex",
  abacus: "codex", search_literature: "lamp", check_references: "codex", find_data_links: "amphora",
  fetch_dataset: "amphora", public_series: "amphora", inspect_dataset: "amphora", fabrica_build: "sica",
  fabrica_run: "sica", reproduce: "libra", mille_viae: "libra", plea: "scroll", pronounce_verdict: "libra",
  field_notes: "res2/map", novacula: "res2/weights", forensics_paper: "res2/weights", forensics_data: "res2/weights",
  compare_versions: "res2/map", audit_code: "codex" };
const FORENSIC_BLADES = ["abacus", "falsum", "fucus", "palimpsestus"];

// Where things stand on each wall (1600x900 stage coordinates; y is the feet line).
export const LAYOUT = {
  ravenna: { ground: 885 },
  classis: { ground: 845, sic: [330, 845], ship: 470 },
  scriptorium: { ground: 855, sic: [560, 855] },
  forum: { ground: 862, sic: [560, 866], statue: [808, 502, 0.8],
    people: { theoria: ["sage", 255, true], inversio: ["baker", 1105, false], mundus: ["woman", 1290, false],
      novacula: ["worker", 1470, false] } },
  horreum: { ground: 850, sic: [420, 850], stack: [1010, 1110, 1210, 1310, 1410, 1060, 1160, 1260, 1360] },
  fabrica: { ground: 865, sic: [640, 865], anvil: [792, 700] },
  palatium: { ground: 812, sic: [105, 860], emp: [800, 640, 0.95],
    guards: { labyrinthus: 265, canistrum: 425, persona: 585, scutum: 1020, augur: 1180, tuba: 1340, bibliotheca: 1500 } },
  aula: { ground: 860, sic: [270, 860], emp: [792, 655, 1.0] },
  curia: { ground: 870, sic: [230, 870], emp: [800, 875, 1.18], sen: [[536, 548], [800, 538], [1057, 548]] },
};
const TEXT_BLADES = ["labyrinthus", "canistrum", "persona", "scutum", "augur", "tuba", "bibliotheca"];
// The milestones behind the clepsydra's water level: every one is something the agent must finish.
export const STEPS = {
  classis: ["paper"], scriptorium: ["read", "target", "abacus", "falsum", "fucus", "palimpsestus"],
  forum: ["field", "inversio", "theoria", "novacula", "mundus"], horreum: ["data"], fabrica: ["forge", "speculum"],
  palatium: TEXT_BLADES, aula: ["mille_viae"], curia: ["verdict"],
};
const STEP_STATION = Object.fromEntries(Object.entries(STEPS).flatMap(([st, xs]) => xs.map((x) => [x, st])));
const VERB = { read: "act_read", write: "act_write", shell: "act_run", web: "act_fetch", search: "act_search",
  browser: "act_browse", spawn: "act_spawn", plan: "act_plan", mcp: "act_tool", other: "act_tool", arsenal: "act_tool" };
const REAL_BLADES = ["inversio", "theoria", "novacula", "mundus"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class Director {
  constructor(stage, ui) {
    this.st = stage; this.ui = ui;
    this.queue = []; this.running = false; this.speed = 1;
    this.reset();
  }
  reset() {
    this.station = null; this.score = 0; this.wounds = []; this.parries = []; this.guards = {};
    this.amphorae = 0; this.conspirators = []; this.holes = []; this.target = ""; this.closed = null;
    this.forum = {}; this.stamps = [];
    this.done = new Set(); this.activity = ""; this.activityAt = 0; this.lastSignal = 0; this.busySecs = 0; this.held = null;
    this.busyAt = 0; this.t0 = null; this.lastTs = null; this.lastArrival = 0; this.closedState = null;
    this.viae = null; this.verdict = null; this.busy = false; this.lastSay = 0;
    this.queue = [];
  }

  // ------------------------------------------------------------ queue
  enqueue(events) {
    this.queue.push(...events);
    if (!this.running) this.drain();
  }
  async drain() {
    this.running = true;
    while (this.queue.length) {
      const ev = this.queue.shift();
      const instant = this.queue.length > 24 || this.speed > 8;
      try { await this.play(ev, instant); } catch (e) { console.error(e, ev); }
    }
    this.running = false;
  }
  async fastForward(events) {
    for (const ev of events) await this.play(ev, true);
  }

  // ------------------------------------------------------------- play
  // ----------------------------------------------------- the clepsydra
  mark(step) {
    const st = STEP_STATION[step];
    if (st) this.done.add(`${st}.${step}`);
  }
  signal(ev) {
    const now = performance.now();
    this.lastSignal = now; this.lastArrival = now;
    if (ev.ts) { if (this.t0 === null) this.t0 = ev.ts; this.lastTs = ev.ts; }
    const k = ev.kind;
    if (k === "tool") {
      const fam = (ev.family || "other").split(":");
      const verb = t(VERB[fam[0]] || "act_tool");
      const what = fam[0] === "arsenal" ? t(`tool_${fam[1]}`) : "";
      this.activity = what && !what.startsWith("tool_") ? what : `${verb}: ${ev.summary || ev.name}`;
      this.activityAt = now; this.busySecs = 0;
    } else if (k === "busy") { this.busySecs = ev.seconds; this.busyAt = now; }
    else if (k === "station") {
      const order = Object.keys(STEPS);
      for (const st of order.slice(0, order.indexOf(ev.station))) STEPS[st].forEach((x) => this.done.add(`${st}.${x}`));
    } else if (k === "acquired" && ev.ok) this.mark(ev.what === "paper" ? "paper" : "data");
    else if (k === "intel") {
      if (ev.about === "paper") this.mark("read");
      if (ev.about === "target") this.mark("target");
      if (ev.about === "field") this.mark("field");
      if (ev.about === "dataset") this.mark("data");
    } else if (k === "forge" && ev.status === "done") this.mark("forge");
    else if (k === "wound") this.mark(ev.wound.blade);
    else if (k === "parry") this.mark(ev.parry.blade);
    else if (k === "verdict") { this.mark("verdict"); this.activity = t("act_verdict"); }
    else if (k === "case.closed") {
      this.closedState = ev.status; this.held = null;
      if (ev.status !== "done") { this.activity = ev.failure ? t(`fail_${ev.failure}`) : t("hunt_failed"); this.activityAt = now; }
    }
    else if (k === "case.resumed") { this.closedState = null; this.held = null; this.activity = t("act_resume"); this.activityAt = now; }
    else if (k === "retry.wait") { this.held = "network"; this.activity = `${t("act_wait")} · ${ev.seconds}s`; this.activityAt = now; }
    else if (k === "region.paused") { this.held = "region"; this.activity = `${t("act_paused")} ${regionLabel(ev.region)}`; this.activityAt = now; }
    else if (k === "region.cleared") { this.held = null; this.activity = t("region_ok"); this.activityAt = now; }
  }
  snapshot() {
    const total = Object.values(STEPS).reduce((a, xs) => a + xs.length, 0);
    const st = this.station || "classis";
    const here = STEPS[st] || [];
    const doneHere = here.filter((x) => this.done.has(`${st}.${x}`)).length;
    const now = performance.now();
    const live = this.live && !this.closedState;
    const elapsed = this.t0 === null ? 0 : (this.lastTs - this.t0) + (live ? (now - this.lastArrival) / 1000 : 0);
    return { station: st, doneHere, totalHere: here.length, overall: this.closedState === "done" ? 1 : this.done.size / total,
      activity: this.activity, activityFor: this.activityAt ? (now - this.activityAt) / 1000 : 0,
      quiet: this.lastSignal ? (now - this.lastSignal) / 1000 : 0, busySecs: this.busySecs,
      busyFresh: this.busyAt && (now - this.busyAt) / 1000 < 90, elapsed, closed: this.closedState, live, held: this.held };
  }

  async play(ev, instant) {
    const k = ev.kind;
    this.signal(ev);
    if (k === "pulse") return;
    this.ui.chronicle.add(ev);
    switch (k) {
      case "case.opened": return this.opened(ev, instant);
      case "station": return this.enter(ev.station, ev.note, instant);
      case "narrate": return this.narrate(ev, instant);
      case "tool": return this.gesture(ev, instant);
      case "busy": if (!instant) { const sc = this.sic(); this.st.float(sc.x + 70, sc.y - 420, `⏳ ${Math.round(ev.seconds / 60)} min`, "white"); } return;
      case "tool.done": if (!ev.ok && !instant) this.st.float(this.sic().x, this.sic().y - 400, "✕", "red"); return;
      case "spawn": return this.spawn(ev, instant);
      case "intel": return this.intel(ev, instant);
      case "acquired": return this.acquired(ev, instant);
      case "forge": return this.forge(ev, instant);
      case "speculum": return this.speculum(ev, instant);
      case "viae": return this.viaeEv(ev, instant);
      case "wound": return this.wound(ev, instant);
      case "parry": return this.parry(ev, instant);
      case "plea": return this.plea(ev, instant);
      case "plea.answered": return this.pleaAnswered(ev, instant);
      case "verdict": return this.verdictEv(ev, instant);
      case "case.closed": return this.closedEv(ev, instant);
      case "case.resumed": return this.resumedEv(ev, instant);
      case "retry.wait": return this.waitEv(ev, instant);
      case "agent.error": if (!instant) this.st.float(this.sic().x, this.sic().y - 400, "✕", "red"); return;
      case "region.paused": case "region.cleared": return this.regionEv(ev, instant);
      default: return;
    }
  }

  sic() { return this.st.get("sic") || { x: 300, y: 850 }; }
  emp() { return this.st.get("emp"); }

  async opened(ev, instant) {
    if (!this.station) await this.enter("classis", "", instant, true);
  }

  // ------------------------------------------------------------ stations
  async enter(key, note, instant, first = false) {
    if (!LAYOUT[key]) return;
    const prev = this.station;
    this.station = key;
    this.ui.frieze.set(key, note);
    if (prev === key && !first) return;
    const L = LAYOUT[key];
    this.st.ground = L.ground;
    this.st.clearFx();
    this.st.clearOverlay(".tag,.tablet,.say,.medallion");
    this.st.setScene(key, { flip: !instant });
    this.st.clearActors(["sic", ...this.conspirators.map((c) => c.id)]);
    const sic = this.st.actor("sic", { sheet: "sicarius", frame: "idle", scale: 1, z: 0 });
    sic.visible = true;
    // conspirators follow the Sicarius from wall to wall
    this.conspirators.forEach((c, i) => {
      const a = this.st.get(c.id);
      if (a) { a.x = (L.sic ? L.sic[0] : 300) - 120 - i * 95; a.y = (L.sic ? L.sic[1] : L.ground) - 18; a.scale = 0.9; }
    });
    this.setupWall(key, instant);
    const [sx, sy] = L.sic || [300, L.ground];
    if (instant || first) { sic.x = sx; sic.y = sy; sic.flip = false; if (first && !instant) await this.st.assemble("sic", 1500); }
    else {
      sic.x = -120; sic.y = sy;
      await sleep(500 / this.speed);
      await this.st.walk("sic", sx, { ms: 1300 / this.speed });
    }
    if (!instant) {
      const n = stationName(key);
      this.st.float(800, 120, `${n.latin} · ${n.tr}`, "gold");
      sfx.play("flip");
    }
  }

  setupWall(key, instant) {
    const L = LAYOUT[key];
    const st = this.st;
    if (key === "classis") {
      st.actor("ship", { sheet: "res", frame: "navis", x: this.target ? 860 : -160, y: L.ship, scale: 1.25, shadow: false, z: -1, bob: 3 });
      if (!instant && !this.target) st.move("ship", 860, L.ship, 5200 / this.speed, "out");
    }
    if (key === "scriptorium") {
      st.actor("lamp", { sheet: "res", frame: "lamp", x: 1180, y: 600, scale: 0.55, shadow: false, z: -1 });
      if (this.stamps.length) this.drawParchment();
    }
    if (key === "forum") {
      const [x, y, sc] = L.statue;
      this.placeEmperor([x, y, sc], "idle");
      const e = st.get("emp"); e.shadow = false; e.z = 400;
      for (const [blade, [who, px, flip]] of Object.entries(L.people)) {
        const state = this.forum[blade];
        st.actor(`p_${blade}`, { sheet: "plebs", frame: `${who}_${state === "fell" ? "dissent" : "speak"}`, x: px,
          y: L.ground, scale: 0.8, flip, z: L.ground });
        const label = bladeName(blade).latin;
        if (label) st.tag(`p_${blade}`, px, L.ground - 338, label, state === "fell" ? "fell" : state === "held" ? "held" : "");
      }
    }
    if (key === "horreum") {
      for (let i = 0; i < Math.min(this.amphorae, L.stack.length); i++) this.placeAmphora(i, true);
    }
    if (key === "fabrica") {
      this.forgeFx = st.addFx({ under: true, draw: (g, tt) => {
        const k = 0.5 + 0.5 * Math.sin(tt * 7) * Math.sin(tt * 3.1);
        const gr = g.createRadialGradient(150, 560, 10, 150, 560, 340);
        gr.addColorStop(0, `rgba(255,150,40,${0.18 + 0.12 * k})`); gr.addColorStop(1, "rgba(255,120,30,0)");
        g.fillStyle = gr; g.fillRect(0, 200, 600, 700);
      } });
    }
    if (key === "palatium") {
      this.placeEmperor(L.emp, "idle");
      for (const b of TEXT_BLADES) this.placeGuard(b, instant);
    }
    if (key === "aula") {
      this.placeEmperor(L.emp, "throne");
      if (this.viae) this.drawRoads(true);
    }
    if (key === "curia") {
      L.sen.forEach(([x, y], i) => st.actor(`sen${i}`, { sheet: "senatus", frame: i === 1 ? "old_idle" : i === 0 ? "young_tablet" : "young_read",
        x, y, scale: 0.56, z: -5 }));
      this.placeEmperor([L.emp[0], L.emp[1], L.emp[2]], "idle");
    }
  }
  placeEmperor([x, y, s], frame) {
    const e = this.st.actor("emp", { sheet: "imperator", frame, x, y, scale: s, z: y - 1 });
    e.visible = true; e.holes = this.holes.slice(); e.cache = null; e.prev = null; e.dissolve = 1;
    this.st.tag("emp", x, y + 8, this.target ? t("decree") : "IMPERATOR");
    return e;
  }
  placeGuard(blade, instant) {
    const L = LAYOUT.palatium;
    const x = L.guards[blade];
    const i = TEXT_BLADES.indexOf(blade);
    const side = i % 2 ? "b" : "a";
    const state = this.guards[blade];
    const frame = state === "fell" ? `${side}_fallen` : state === "held" ? `${side}_block` : `${side}_idle`;
    const g = this.st.actor(`g_${blade}`, { sheet: "custodes", frame, x, y: L.ground - (i % 2) * 14, scale: 0.78,
      flip: x > 800 ? false : true, z: L.ground });
    g.prev = null; g.dissolve = 1;
    const n = bladeName(blade);
    this.st.tag(`g_${blade}`, x, L.ground + 18, n.latin, state === "fell" ? "fell" : state === "held" ? "held" : "");
    return g;
  }
  placeAmphora(i, instant) {
    const L = LAYOUT.horreum;
    const x = L.stack[i % L.stack.length];
    const y = i < 5 ? 845 : 780;
    const a = this.st.actor(`amph${i}`, { sheet: "res", frame: "amphora", x, y: instant ? y : -100, scale: 0.42, z: y - (i < 5 ? 0 : 60) });
    if (!instant) this.st.move(`amph${i}`, x, y, 700, "back");
    return a;
  }

  // ------------------------------------------------------------ narration
  async narrate(ev, instant) {
    if (instant) return;
    const id = ev.who && ev.who.startsWith("conspirator") ? (this.conspirators.find((c) => c.who === ev.who) || {}).id : "sic";
    if (!id || !this.st.get(id)) return;
    const flat = plain(ev.text);
    const first = (flat.match(/^.{0,220}?(?:[.!?](?=\s|$)|[。！？])/) || [flat.slice(0, 200)])[0].trim();
    const who = id === "sic" ? t("sicarius") : t("conspirator");
    this.st.say(id, first, who, 3800);
    this.lastSay = performance.now();
    await sleep(Math.min(2400, 500 + first.length * 18) / this.speed);
  }

  async gesture(ev, instant) {
    if (instant || this.busy) return;
    const fam = (ev.family || "other").split(":");
    const tool = fam[1];
    const sic = this.st.get("sic");
    if (!sic) return;
    const g = fam[0] === "arsenal" ? ARSENAL_GLYPH[tool] : FAMILY_GLYPH[fam[0]];
    if (g) this.st.glyph(sic.x + 30, sic.y - 400, GLYPH(g));
    sfx.play("tick");
    let pose = null;
    if (fam[0] === "read" || fam[0] === "write" || tool === "read_paper" || tool === "verify_quote") pose = "read";
    else if (fam[0] === "shell" || tool === "fabrica_run" || tool === "fabrica_build") pose = "forge";
    else if (fam[0] === "web" || fam[0] === "search" || fam[0] === "browser" || tool === "search_literature") pose = "sneak";
    if (pose) {
      this.st.pose("sic", pose);
      if (pose === "forge") this.hammer();
      clearTimeout(this.restT);
      this.restT = setTimeout(() => { if (!this.busy) this.st.pose("sic", "idle"); }, 1700);
    }
    await sleep(160 / this.speed);
  }
  hammer() {
    const L = LAYOUT.fabrica;
    if (this.station !== "fabrica") { this.st.sparks(this.sic().x + 60, this.sic().y - 260, 8); return; }
    for (let i = 0; i < 3; i++) setTimeout(() => {
      this.st.sparks(L.anvil[0], L.anvil[1], 16); sfx.play("anvil");
      const s = this.st.get("sic"); if (s) s.lift = i % 2 ? 0 : 4;
    }, i * 280);
  }

  async spawn(ev, instant) {
    if (this.conspirators.length >= 3) return;
    const id = `con${this.conspirators.length + 1}`;
    this.conspirators.push({ id, who: ev.who });
    const sic = this.sic();
    const a = this.st.actor(id, { sheet: "conspirator", frame: "idle", x: sic.x - 120 - (this.conspirators.length - 1) * 95,
      y: sic.y - 18, scale: 0.9, z: sic.y - 20 });
    if (!instant) { await this.st.assemble(id, 1100); sfx.play("assemble"); }
    else a.visible = true;
  }

  // ---------------------------------------------------------------- intel
  async intel(ev, instant) {
    if (ev.about === "paper") {
      this.ui.setTitle(ev.title);
      if (!instant) {
        const sic = this.sic();
        this.st.pose("sic", "read");
        this.st.float(sic.x, sic.y - 450, `${(ev.n_stats || 0).toLocaleString()} ${t("tesserae_counted")}`, "gold");
        sfx.play("scroll");
        await sleep(900 / this.speed);
      }
    } else if (ev.about === "target") {
      this.target = ev.claim || this.target;
      this.ui.setDecree(this.target);
      if (!instant && this.emp()) { this.st.pose("emp", "decree"); setTimeout(() => this.st.pose("emp", this.station === "aula" ? "throne" : "idle"), 2600); }
      if (!instant) this.st.float(800, 230, t("decree").toUpperCase(), "gold");
    } else if (ev.about === "field") {
      if (instant || this.station !== "forum") return;
      const L = LAYOUT.forum;
      this.st.tablet("field", 808, 200, `<b>FORUM</b><div>${escapeHtml(ev.field || "")}</div>
        <div style="font-size:.85em;opacity:.8">${escapeHtml((ev.setting || "").slice(0, 120))}</div>
        <div style="font-size:.85em">${(ev.actors || []).length} · ${ev.n_sources || 0} ⟡</div>`, 8000);
      for (const [blade, [who]] of Object.entries(L.people)) {
        if (this.forum[blade]) continue;
        this.st.pose(`p_${blade}`, `${who}_speak`);
        this.st.float(L.people[blade][1], L.ground - 380, "…", "white");
        await sleep(350 / this.speed);
      }
      sfx.play("scroll");
    } else if (ev.about === "razor" && !instant) {
      const sic = this.sic();
      this.st.float(sic.x + 120, sic.y - 450, `NOVACULA · ${ev.verdict}`, ev.verdict === "shave" ? "red" : "green");
    } else if (["forensics", "versions", "code"].includes(ev.about) && !instant) {
      const sic = this.sic();
      const txt = ev.about === "forensics" ? `FALSUM · ${ev.n_flags} ${t("flags")}`
        : ev.about === "versions" ? `PALIMPSESTUS · ${ev.rewritten + ev.removed} ${t("changed")}`
          : `CODEX · ${ev.n_steps} ${t("data_steps")}`;
      this.st.float(sic.x + 120, sic.y - 450, txt, (ev.n_flags || ev.removed || ev.rewritten) ? "red" : "green");
      this.st.pose("sic", "read");
    } else if (ev.about === "abacus" && !instant) {
      this.st.float(this.sic().x, this.sic().y - 450, `ABACUS · ${ev.n_flags} ${t("flags")}`, ev.n_flags ? "red" : "green");
    } else if (ev.about === "dataset" && !instant) {
      this.st.float(this.sic().x + 200, this.sic().y - 430, `${ev.rows?.toLocaleString()} ${t("rows")} × ${ev.cols} ${t("cols")}`, "white");
    }
  }

  async acquired(ev, instant) {
    if (ev.what === "paper") {
      if (instant) return;
      if (ev.ok) {
        this.st.float(860, 470, t("paper_in"), "gold");
        if (this.st.get("ship")) await this.st.move("ship", 860, LAYOUT.classis.ship, 900);
      } else {
        this.st.float(860, 470, t("paper_fail"), "red");
        sfx.play("thud");
      }
      return;
    }
    if (ev.what === "data") {
      if (ev.ok) {
        const n = Math.max(1, Math.min(3, (ev.tables || []).length || 1));
        for (let i = 0; i < n; i++) {
          if (this.station === "horreum") this.placeAmphora(this.amphorae, instant);
          this.amphorae++;
        }
        if (!instant) { this.st.float(1200, 600, t("data_in"), "gold"); sfx.play("thud"); await sleep(600 / this.speed); }
      } else if (!instant) {
        this.st.burst(this.sic().x + 120, this.sic().y - 80, { n: 26, colors: ["#b5683a", "#8c4a26", "#d9a679"], power: 0.7 });
        this.st.float(this.sic().x + 120, this.sic().y - 300, t("data_fail"), "red");
        sfx.play("crack");
      }
    }
  }

  async forge(ev, instant) {
    if (instant) return;
    if (ev.status === "start") { this.st.pose("sic", "forge"); this.hammer(); return; }
    if (ev.step === "build") {
      this.st.flashAt(0.18);
      this.st.float(800, 420, t("forge_ready"), ev.ok ? "gold" : "red");
    } else {
      const L = LAYOUT.fabrica;
      this.st.sparks(L.anvil[0], L.anvil[1], ev.ok ? 26 : 12, ev.ok ? "#ffd27a" : "#ff6b4a");
    }
    setTimeout(() => this.st.pose("sic", "idle"), 900);
  }

  async speculum(ev, instant) {
    if (instant) return;
    const v = ev.verdict;
    const col = v === "match" ? "#2e7d4f" : v === "close" ? "#9a6b18" : "#b3261e";
    const fmt = (x) => (x === null || x === undefined ? "—" : Number(x).toPrecision(4));
    this.st.tablet("speculum", 1180, 330,
      `<b>SPECULUM</b><div>${escapeHtml(ev.what || "")}</div>
       <div class="big">${fmt(ev.paper_value)} · ${fmt(ev.reproduced_value)}</div>
       <div>${t("paper_val")} · ${t("ours")} — <span style="color:${col};font-weight:700">${t(v)}</span></div>`, 7000);
    sfx.play(v === "mismatch" ? "crack" : "bell");
    this.st.flashAt(0.12, v === "mismatch" ? "255,90,70" : "255,240,200");
    await sleep(1400 / this.speed);
  }

  async viaeEv(ev, instant) {
    if (ev.status !== "done") return;
    this.viae = ev;
    if (this.station !== "aula") return;
    this.drawRoads(instant);
    if (!instant) {
      await sleep(2600 / this.speed);
      const s = ev.summary || {};
      const share = s.share_significant_expected_sign ?? 0;
      this.st.tablet("viae", 1240, 300, `<b>MILLE VIAE</b><div class="big">${Math.round(share * 100)}%</div>
        <div>${s.n_specs_run} ${t("roads")} · ${t("sig_share")}</div>`, 9000);
      await sleep(800 / this.speed);
      await this.strikeEmperor(share < 0.5 ? (share < 0.25 ? 10 : 6) : 0, share >= 0.8);
    }
  }
  drawRoads(instant) {
    const pts = (this.viae && this.viae.points) || [];
    if (!pts.length) return;
    const N = Math.min(pts.length, 140), step = pts.length / N;
    const sel = Array.from({ length: N }, (_, i) => pts[Math.floor(i * step)]);
    const pref = (this.viae.summary || {}).preferred_sign || 1;
    const sic = this.sic(), emp = this.emp() || { x: 790, y: 650 };
    const sx = sic.x + 50, sy = sic.y - 210, ex = emp.x - 30, ey = emp.y - 170;
    this.st.addFx({ under: false, draw: (g, tt) => {
      const T = instant ? 99 : tt * this.speed;
      for (let i = 0; i < N; i++) {
        const p = sel[i];
        const k = clamp((T - i * 0.012) / 0.9, 0, 1);
        if (k <= 0) continue;
        const sig = p.p < 0.05, same = Math.sign(p.c) === pref;
        g.fillStyle = sig && same ? "rgba(240,205,110,.85)" : sig ? "rgba(200,60,50,.8)" : "rgba(150,160,185,.55)";
        const cy = sy + (i / N - 0.5) * 520;
        const cx = (sx + ex) / 2;
        const n = Math.floor(40 * k);
        for (let j = 0; j <= n; j += 2) {
          const u = j / 40;
          const x = (1 - u) * (1 - u) * sx + 2 * (1 - u) * u * cx + u * u * ex;
          const y = (1 - u) * (1 - u) * sy + 2 * (1 - u) * u * cy + u * u * ey;
          g.fillRect(x - 2.5, y - 2.5, 5, 5);
        }
      }
    } });
  }

  // ------------------------------------------------------------ wounds
  async wound(ev, instant) {
    const w = ev.wound;
    this.wounds.push(w);
    this.score = fragility(this.wounds);
    this.ui.hud(this.wounds, this.parries, this.score);
    const deep = { critical: 9, high: 6, medium: 3, low: 1, info: 0 }[w.severity] || 2;
    if (this.station === "palatium" && TEXT_BLADES.includes(w.blade) && this.guards[w.blade] !== "fell") {
      this.guards[w.blade] = "fell";
      if (instant) { this.placeGuard(w.blade, true); this.addHoles(Math.ceil(deep / 2)); return; }
      await this.strikeGuard(w.blade, true, w.title);
      this.addHoles(Math.ceil(deep / 2));
      return;
    }
    if (TEXT_BLADES.includes(w.blade)) this.guards[w.blade] = "fell";
    this.ui.seal(this.wounds);
    if (FORENSIC_BLADES.includes(w.blade)) {
      this.stamp(w.blade, w.title, false);
      if (this.station === "scriptorium" && !instant) {
        this.st.pose("sic", "read");
        sfx.play("crack");
        this.st.flashAt(0.12, "255,80,60");
        this.addHoles(deep);
        await sleep(1100 / this.speed);
        return;
      }
    }
    if (REAL_BLADES.includes(w.blade)) {
      this.forum[w.blade] = "fell";
      if (this.station === "forum") {
        if (instant) { this.addHoles(deep); this.setupPeople(); return; }
        await this.citizensObject(w.blade, true, w.title);
        await this.strikeEmperor(deep, false, "");
        return;
      }
    }
    if (instant) { this.addHoles(deep); return; }
    await this.strikeEmperor(deep, false, w.title);
  }
  async parry(ev, instant) {
    const p = ev.parry;
    this.parries.push(p);
    this.ui.hud(this.wounds, this.parries, this.score);
    if (TEXT_BLADES.includes(p.blade) && !this.guards[p.blade]) this.guards[p.blade] = "held";
    if (FORENSIC_BLADES.includes(p.blade)) this.stamp(p.blade, p.note, true);
    if (REAL_BLADES.includes(p.blade) && !this.forum[p.blade]) {
      this.forum[p.blade] = "held";
      if (this.station === "forum") {
        if (instant) { this.setupPeople(); return; }
        await this.citizensObject(p.blade, false, p.note);
        return;
      }
    }
    if (instant) { if (this.station === "palatium" && TEXT_BLADES.includes(p.blade)) this.placeGuard(p.blade, true); return; }
    if (this.station === "palatium" && TEXT_BLADES.includes(p.blade)) await this.strikeGuard(p.blade, false, p.note);
    else {
      const sic = this.sic();
      this.st.float(sic.x, sic.y - 430, `${bladeName(p.blade).latin} · ⛨`, "green");
      sfx.play("clang");
      await sleep(700 / this.speed);
    }
  }
  // The decree on the scriptorium desk: every forensic finding is stamped on it in red wax.
  drawParchment(flash) {
    const items = this.stamps.slice(-6).map((m, i) => {
      const rot = ((i * 37) % 13) - 6;
      return `<span class="stamp ${m.ok ? "ok" : ""} ${flash && i === Math.min(5, this.stamps.length - 1) ? "new" : ""}"
        style="transform:rotate(${rot}deg)"><b>${escapeHtml(m.latin)}</b>${escapeHtml(truncate(m.text, 46))}</span>`;
    }).join("");
    this.st.tablet("parchment", 1170, 330, `<b>${t("decree").toUpperCase()}</b>
      <div class="parch-claim">${escapeHtml(truncate(this.target || "", 120))}</div><div class="stamps">${items}</div>`);
  }
  stamp(blade, text, ok) {
    this.stamps.push({ latin: bladeName(blade).latin.toUpperCase(), text, ok });
    if (this.station === "scriptorium") this.drawParchment(true);
  }
  setupPeople() {
    const L = LAYOUT.forum;
    for (const [blade, [who, px]] of Object.entries(L.people)) {
      const state = this.forum[blade];
      this.st.pose(`p_${blade}`, `${who}_${state === "fell" ? "dissent" : "speak"}`, { dissolve: false });
      this.st.tag(`p_${blade}`, px, L.ground - 338, bladeName(blade).latin, state === "fell" ? "fell" : state === "held" ? "held" : "");
    }
  }
  // The people of the forum testify: they point at the statue when the decree misreads their world,
  // and explain calmly when it gets it right.
  async citizensObject(blade, objects, label) {
    const L = LAYOUT.forum;
    const ids = [blade];
    for (const b of ids) {
      const [who, px] = L.people[b];
      this.st.pose(`p_${b}`, `${who}_${objects ? "dissent" : "speak"}`);
      this.st.tag(`p_${b}`, px, L.ground - 338, bladeName(b).latin, objects ? "fell" : "held");
    }
    const [, px] = L.people[blade];
    this.st.float(px, L.ground - 390, objects ? truncate(label, 54) : `⛨ ${truncate(label, 50)}`, objects ? "red" : "green");
    sfx.play(objects ? "crack" : "bell");
    await sleep(900 / this.speed);
  }
  async strikeGuard(blade, landed, label) {
    this.busy = true;
    const L = LAYOUT.palatium;
    const gx = L.guards[blade];
    const side = TEXT_BLADES.indexOf(blade) % 2 ? "b" : "a";
    const from = gx > 800 ? gx - 175 : gx + 175;
    const sic = this.st.get("sic");
    await this.st.walk("sic", from, { ms: clamp(Math.abs(from - sic.x) * 1.6, 300, 1500) / this.speed });
    sic.flip = gx < sic.x;
    this.st.pose("sic", "strike");
    this.st.pose(`g_${blade}`, `${side}_block`);
    await this.st.tween(sic, { x: from + (gx > from ? 50 : -50) }, 180, "out");
    const g = this.st.get(`g_${blade}`);
    if (landed) {
      sfx.play("strike");
      this.st.shake(280);
      this.st.burst(gx, L.ground - 160, { n: 46, from: `g_${blade}`, power: 1.1 });
      this.st.burst(gx, L.ground - 160, { n: 14, colors: ["#b3261e", "#7d1a14"], power: 0.9 });
      this.st.pose(`g_${blade}`, `${side}_stagger`);
      await sleep(420 / this.speed);
      this.st.pose(`g_${blade}`, `${side}_fallen`);
      if (g) g.shake = 0;
      this.st.tag(`g_${blade}`, gx, L.ground + 18, bladeName(blade).latin, "fell");
      this.st.float(gx, L.ground - 360, truncate(label, 54), "red");
      if (this.emp()) { this.st.pose("emp", "alarmed"); setTimeout(() => this.st.pose("emp", "idle"), 1800); }
    } else {
      sfx.play("clang");
      this.st.sparks(gx + (gx > from ? -40 : 40), L.ground - 190, 22, "#fff0b0");
      await this.st.tween(sic, { x: from + (gx > from ? -40 : 40) }, 260, "out");
      this.st.tag(`g_${blade}`, gx, L.ground + 18, bladeName(blade).latin, "held");
      this.st.float(gx, L.ground - 360, `⛨ ${truncate(label, 50)}`, "green");
    }
    await sleep(650 / this.speed);
    this.st.pose("sic", "idle");
    sic.flip = false;
    this.busy = false;
  }
  async strikeEmperor(deep, held = false, label = "") {
    const emp = this.emp();
    const sic = this.st.get("sic");
    if (!emp || !sic) {
      if (deep) { this.addHoles(deep); if (sic) this.st.burst(sic.x + 160, sic.y - 220, { n: 18, power: 0.6 }); }
      if (label && sic) this.st.float(sic.x + 160, sic.y - 420, truncate(label, 54), "red");
      if (deep) sfx.play("strike");
      return;
    }
    this.busy = true;
    const home = sic.x;
    const to = emp.x - 230 * (emp.scale || 1);
    await this.st.walk("sic", to, { ms: clamp(Math.abs(to - sic.x) * 1.3, 300, 1400) / this.speed });
    this.st.pose("sic", "strike");
    await this.st.tween(sic, { x: to + 60 }, 160, "out");
    if (deep && !held) {
      sfx.play("strike");
      this.st.shake(320);
      this.st.burst(emp.x, emp.y - 200 * emp.scale, { n: 30 + deep * 6, from: "emp", power: 1 });
      this.st.burst(emp.x, emp.y - 200 * emp.scale, { n: 10 + deep, colors: ["#b3261e", "#6d0f0b"], power: 0.8 });
      this.addHoles(deep);
      this.st.pose("emp", this.score > 60 ? "wounded" : "alarmed");
      if (label) this.st.float(emp.x, emp.y - 430 * emp.scale, truncate(label, 54), "red");
    } else {
      sfx.play("clang");
      this.st.sparks(emp.x - 60, emp.y - 220 * emp.scale, 26, "#fff0b0");
      this.st.pose("emp", this.station === "aula" ? "throne" : "defiant");
      if (held) this.st.float(emp.x, emp.y - 430 * emp.scale, "IMPERATOR STAT", "green");
    }
    await sleep(900 / this.speed);
    this.st.pose("sic", "idle");
    await this.st.walk("sic", home, { ms: 900 / this.speed });
    this.st.pose("emp", this.station === "aula" ? "throne" : "idle");
    this.busy = false;
  }
  addHoles(n) {
    if (!n) return;
    // each wound cracks the portrait; deeper wounds crack it wider
    const size = Math.min(1.8, 0.45 + n * 0.14);
    this.holes.push({ u: 0.3 + rand(0.4), v: 0.18 + rand(0.62), size, seed: 1 + Math.floor(rand(1e6)) });
    const emp = this.emp();
    if (emp) { emp.holes = this.holes.slice(); emp.cache = null; }
  }

  // ------------------------------------------------------------- plea
  async plea(ev, instant) {
    this.ui.openPlea(ev);
    if (instant) return;
    const L = LAYOUT[this.station] || { ground: 850 };
    const isData = /data|dataset|package|replication|数据|复现/i.test(`${ev.what} ${ev.why}`);
    this.st.actor("trav", { sheet: "peregrinus", frame: "walk", x: -140, y: L.ground, scale: 0.92, z: L.ground + 5 });
    sfx.play("bell");
    await this.st.walk("trav", 180, { ms: 1400 });
    this.st.pose("trav", isData ? "offer_amphora" : "offer_scroll");
  }
  async pleaAnswered(ev, instant) {
    this.ui.closePlea(ev.plea_id);
    if (instant || !this.st.get("trav")) { this.st.remove("trav"); return; }
    if (ev.declined || ev.timeout) {
      this.st.pose("trav", "amazed");
      await sleep(900);
    } else {
      const sic = this.sic();
      await this.st.walk("trav", sic.x - 130, { ms: 900 });
      this.st.flashAt(0.15);
      sfx.play("scroll");
      await sleep(500);
    }
    const tr = this.st.get("trav");
    if (tr) { tr.flip = true; await this.st.walk("trav", -160, { ms: 1300 }); }
    this.st.remove("trav");
  }

  // ------------------------------------------------------------- verdict
  async verdictEv(ev, instant) {
    const v = ev.verdict;
    this.verdict = v;
    const f = v.fragility;
    this.score = f.score;
    this.ui.hud(this.wounds, this.parries, this.score);
    if (this.station !== "curia") await this.enter("curia", "", instant);
    const band = bandFor(f.score);
    const pose = { defiant: "defiant", idle: "idle", wounded: "wounded", kneeling: "kneeling", fallen: "fallen" }[band.pose] || "idle";
    const thumbs = f.score >= 60 ? "old_down" : f.score < 35 ? "old_up" : "old_libra";
    this.ui.seal(this.wounds, f);
    if (instant) {
      this.st.pose("emp", pose, { dissolve: false });
      this.st.pose("sen1", thumbs, { dissolve: false });
      this.ui.medallion(f, true);
      return;
    }
    await sleep(800);
    this.st.pose("sen0", "young_read"); this.st.pose("sen2", "young_point");
    await sleep(900);
    this.st.pose("sen1", thumbs);
    sfx.play(f.score >= 60 ? "strike" : "bell");
    await sleep(700);
    if (pose === "fallen") { this.st.burst(800, 700, { n: 90, from: "emp", power: 1.2 }); this.st.shake(500); }
    this.st.pose("emp", pose);
    if (pose === "defiant") {
      this.st.actor("wreath", { sheet: "res", frame: "laurel", x: 800, y: 300, scale: 0.6, shadow: false, z: 2000 });
      this.st.flashAt(0.3);
    }
    await sleep(900);
    this.ui.medallion(f, false);
    sfx.play("gong");
  }
  async closedEv(ev, instant) {
    this.closed = ev.status;
    this.ui.closed(ev, instant);
    if (instant) { this.st.setDim(0); return; }  // like every other fast-forwarded close, a pause dim included
    if (ev.status === "aborted" || ev.status === "failed" || ev.status === "interrupted") {
      if (this.st.get("sic")) this.st.scatter("sic");
      this.st.setDim(0.45);
    }
  }
  // the scattered Sicarius gathers its tesserae again and steps back into the walk
  async resumedEv(ev, instant) {
    this.closed = null;
    this.ui.resumed(ev, instant);
    this.st.setDim(0);
    const sic = this.st.get("sic");
    if (instant) { if (sic) sic.visible = true; return; }
    if (sic) await this.st.assemble("sic", 1500);
    const s = this.sic();
    this.st.float(s.x, s.y - 420, `⚔ ${attemptLabel(ev.attempt)}`, "gold");
    sfx.play("bell");
  }
  async waitEv(ev, instant) {
    if (instant) return;
    const s = this.sic();
    this.st.float(s.x + 60, s.y - 420, `⏳ ${ev.seconds}s`, "white");
  }
  // the region guard: the wall dims and holds still while nothing may be sent
  async regionEv(ev, instant) {
    const paused = ev.kind === "region.paused";
    this.ui.region(ev, instant);
    this.st.setDim(paused ? 0.35 : 0);
    if (instant) return;
    const s = this.sic();
    this.st.float(s.x, s.y - 420, paused ? `⏸ ${regionLabel(ev.region)}` : "▶", paused ? "white" : "gold");
  }
}

export function fragility(wounds) {
  let raw = 0;
  let integrity = false;
  for (const w of wounds) {
    const c = w.effective_confidence ?? w.confidence ?? 0.6;
    raw += sevWeight(w.severity) * c;
    if (["abacus", "speculum"].includes(w.blade) && ["high", "critical"].includes(w.severity) && c >= 0.6) integrity = true;
  }
  let s = Math.round(1000 * (1 - Math.exp(-raw / 12))) / 10;
  if (integrity) s = Math.max(s, 45);
  return s;
}
function truncate(s, n) { s = String(s || ""); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
export { getLang };
