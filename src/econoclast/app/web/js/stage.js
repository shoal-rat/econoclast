// The living mosaic. A 1600x900 canvas composited every frame from real mosaic art:
// figures step on the tile grid, change pose by reshuffling their tesserae, lose tiles
// to wounds (exposing the mortar bed), and the gold catches a moving light.

export const W = 1600, H = 900;
const SNAP = 5;           // figures move in tessera-sized steps
const BLOCK = 10;         // tile size used when a figure reshuffles between poses
const MORTAR = "#cbbd9c";

const rand = (a = 1, b) => (b === undefined ? Math.random() * a : a + Math.random() * (b - a));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const ease = {
  linear: (t) => t,
  out: (t) => 1 - Math.pow(1 - t, 3),
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  back: (t) => { const c = 1.7; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
};
function hash(x, y, s = 0) {
  let h = (x * 374761393 + y * 668265263 + s * 2147483647) | 0;
  h = (h ^ (h >>> 13)) * 1274126177;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

export class Assets {
  constructor() { this.img = {}; this.sprites = {}; this.scenes = {}; this.pixels = new Map(); }
  async load(base = "assets/") {
    const man = await (await fetch(base + "manifest.json")).json();
    const jobs = [];
    const add = (key, src) => jobs.push(new Promise((res) => {
      const im = new Image();
      im.onload = () => { this.img[key] = im; res(); };
      im.onerror = () => res();
      im.src = src;
    }));
    for (const [sheet, frames] of Object.entries(man.sprites)) {
      this.sprites[sheet] = frames;
      for (const fr of Object.keys(frames)) add(`${sheet}/${fr}`, `${base}${sheet}/${fr}.png`);
    }
    for (const [name, info] of Object.entries(man.scenes)) {
      this.scenes[name] = info;
      add(`scene/${name}`, `${base}scenes/${name}.jpg`);
    }
    await Promise.all(jobs);
    this.tintConspirator();
    return this;
  }
  frame(sheet, fr) { return { im: this.img[`${sheet}/${fr}`], meta: (this.sprites[sheet] || {})[fr] }; }
  // pixel access for sampling tesserae out of a sprite
  data(key) {
    if (this.pixels.has(key)) return this.pixels.get(key);
    const im = this.img[key];
    if (!im) return null;
    const c = document.createElement("canvas");
    c.width = im.width; c.height = im.height;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.drawImage(im, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height);
    this.pixels.set(key, d);
    return d;
  }
  // a conspirator: the Sicarius re-glazed in porphyry instead of lapis
  tintConspirator() {
    const frames = this.sprites.sicarius || {};
    this.sprites.conspirator = frames;
    for (const fr of Object.keys(frames)) {
      const im = this.img[`sicarius/${fr}`];
      if (!im) continue;
      const c = document.createElement("canvas");
      c.width = im.width; c.height = im.height;
      const g = c.getContext("2d", { willReadFrequently: true });
      g.drawImage(im, 0, 0);
      const d = g.getImageData(0, 0, c.width, c.height);
      const p = d.data;
      for (let i = 0; i < p.length; i += 4) {
        const r = p[i], gg = p[i + 1], b = p[i + 2];
        if (b > r + 12 && b > gg) { p[i] = Math.min(255, b * 0.95); p[i + 1] = gg * 0.55; p[i + 2] = r * 0.9 + 20; }
        else if (gg > r && gg > b) { p[i] = gg * 0.85; p[i + 1] = r * 0.8; p[i + 2] = b * 0.7; }
      }
      g.putImageData(d, 0, 0);
      this.img[`conspirator/${fr}`] = c;
    }
  }
}

class Actor {
  constructor(id, o) {
    Object.assign(this, { id, sheet: "sicarius", frame: "idle", x: 0, y: 0, scale: 1, flip: false, alpha: 1,
      z: 0, visible: true, holes: [], prev: null, dissolve: 1, bob: 0, shake: 0, lift: 0 }, o);
    this.cache = null;
  }
}

export class Stage {
  constructor(canvas, overlay, assets) {
    this.cv = canvas; this.g = canvas.getContext("2d");
    this.ov = overlay; this.as = assets;
    this.actors = new Map();
    this.tweens = [];
    this.parts = [];
    this.glints = [];
    this.fx = [];
    this.scene = null; this.prevScene = null; this.flipT = 1; this.flipOrigin = [0, H / 2];
    this.goldPts = []; this.light = { x: 0, y: 300, mx: null, my: null };
    this.ground = 830;
    this.dim = 0; this.dimTo = 0; this.flash = 0; this.flashColor = "255,240,200"; this.shakeT = 0;
    this.t = 0; this.last = performance.now(); this.paused = false;
    this.onFrame = null;
    canvas.addEventListener("mousemove", (e) => {
      const r = canvas.getBoundingClientRect();
      this.light.mx = ((e.clientX - r.left) / r.width) * W; this.light.my = ((e.clientY - r.top) / r.height) * H;
    });
    canvas.addEventListener("mouseleave", () => { this.light.mx = null; });
    requestAnimationFrame((n) => this.loop(n));
  }

  // ------------------------------------------------------------ scenes
  setScene(name, { flip = true, origin } = {}) {
    if (name === this.scene) return;
    this.prevScene = flip ? this.scene : null;
    this.scene = name;
    this.flipT = this.prevScene ? 0 : 1;
    this.flipOrigin = origin || [rand() < 0.5 ? 0 : W, rand(H)];
    this.goldPts = this.findGold(`scene/${name}`, 6);
  }
  findGold(key, step = 6) {
    const d = this.as.data(key);
    if (!d) return [];
    const pts = [];
    const sx = W / d.width, sy = H / d.height;
    for (let y = 0; y < d.height; y += step) for (let x = 0; x < d.width; x += step) {
      const i = (y * d.width + x) * 4, r = d.data[i], g = d.data[i + 1], b = d.data[i + 2];
      if (r > 150 && g > 105 && b < 120 && r >= g && g > b && r - b > 70) pts.push([x * sx, y * sy]);
    }
    return pts;
  }

  // ------------------------------------------------------------ actors
  actor(id, o = {}) {
    let a = this.actors.get(id);
    if (!a) { a = new Actor(id, o); this.actors.set(id, a); }
    else Object.assign(a, o);
    return a;
  }
  get(id) { return this.actors.get(id); }
  remove(id) { this.actors.delete(id); }
  clearActors(keep = []) { for (const id of [...this.actors.keys()]) if (!keep.includes(id)) this.actors.delete(id); }
  pose(id, frame, { dissolve = true } = {}) {
    const a = this.actors.get(id);
    if (!a || a.frame === frame) return;
    a.prev = dissolve ? { sheet: a.sheet, frame: a.frame } : null;
    a.frame = frame; a.dissolve = dissolve ? 0 : 1; a.cache = null;
  }
  move(id, x, y, ms = 800, e = "inOut") {
    const a = this.actors.get(id);
    if (!a) return Promise.resolve();
    return this.tween(a, { x, y: y ?? a.y }, ms, e);
  }
  tween(obj, to, ms, e = "inOut") {
    return new Promise((resolve) => {
      const from = {};
      for (const k of Object.keys(to)) from[k] = obj[k];
      this.tweens = this.tweens.filter((tw) => !(tw.obj === obj && Object.keys(to).some((k) => k in tw.to)));
      this.tweens.push({ obj, from, to, ms, t: 0, e: ease[e] || ease.inOut, resolve });
    });
  }
  async walk(id, x, { ms, sheet } = {}) {
    const a = this.actors.get(id);
    if (!a) return;
    const dist = Math.abs(x - a.x);
    if (dist < 4) return;
    a.flip = x < a.x;
    const dur = ms || clamp(dist * 2.4, 350, 2600);
    const base = a.frame;
    let step = 0;
    const timer = setInterval(() => { this.pose(id, step++ % 2 ? "walk1" : "walk2", { dissolve: false }); }, 190);
    await this.move(id, x, a.y, dur, "linear");
    clearInterval(timer);
    a.flip = false;
    this.pose(id, sheet || (base.startsWith("walk") ? "idle" : base));
  }

  // ---------------------------------------------------------- particles
  burst(x, y, { n = 40, colors = ["#b3261e", "#7d1a14", "#d9a679", "#efe7d6"], power = 1, from, up = 1 } = {}) {
    let cols = colors;
    if (from) {
      const s = this.sampleActor(from, 60);
      if (s.length) cols = s.map((p) => p.c);
    }
    for (let i = 0; i < n; i++) {
      const sz = rand(5, 10);
      this.parts.push({ x: x + rand(-14, 14), y: y + rand(-24, 24), vx: rand(-260, 260) * power,
        vy: rand(-420, -80) * power * up, r: rand(6.28), vr: rand(-9, 9), s: sz, c: cols[i % cols.length],
        life: rand(2.6, 4.2), age: 0, ground: this.ground + rand(-8, 26) });
    }
  }
  sparks(x, y, n = 18, color = "#ffd27a") {
    for (let i = 0; i < n; i++) {
      this.parts.push({ x, y, vx: rand(-300, 300), vy: rand(-380, -60), r: 0, vr: 0, s: rand(3, 6), c: color,
        life: rand(0.5, 1.1), age: 0, ground: this.ground + 30, glow: true });
    }
  }
  sampleActor(id, max = 400, step = 9) {
    const a = this.actors.get(id);
    if (!a) return [];
    const key = `${a.sheet}/${a.frame}`;
    const d = this.as.data(key);
    const { meta } = this.as.frame(a.sheet, a.frame);
    if (!d || !meta) return [];
    const out = [];
    for (let y = step / 2; y < d.height; y += step) for (let x = step / 2; x < d.width; x += step) {
      const i = ((y | 0) * d.width + (x | 0)) * 4;
      if (d.data[i + 3] > 160) {
        const sx = a.flip ? meta.w - x : x;
        out.push({ x: a.x + (sx - meta.ax) * a.scale, y: a.y + (y - meta.ay) * a.scale,
          c: `rgb(${d.data[i]},${d.data[i + 1]},${d.data[i + 2]})` });
      }
    }
    if (out.length > max) {
      const k = out.length / max;
      return Array.from({ length: max }, (_, i) => out[Math.floor(i * k)]);
    }
    return out;
  }
  // tesserae fly in from everywhere and settle into the figure
  assemble(id, ms = 1600, from = "scatter") {
    const a = this.actors.get(id);
    if (!a) return Promise.resolve();
    a.visible = false;
    const pts = this.sampleActor(id, 650, 7);
    const t0 = this.t;
    for (const p of pts) {
      const sx = from === "above" ? p.x + rand(-300, 300) : rand(W);
      const sy = from === "above" ? rand(-300, 0) : (rand() < 0.5 ? rand(-100, H * 0.3) : rand(H * 0.7, H + 100));
      this.parts.push({ x: sx, y: sy, tx: p.x, ty: p.y, sx, sy, r: rand(6.28), vr: 0, s: 6.5, c: p.c,
        t0: t0 + rand(0, ms * 0.35) / 1000, dur: ms / 1000 * rand(0.55, 0.65), homing: true, age: 0, life: 99 });
    }
    return new Promise((res) => setTimeout(() => { a.visible = true; a.dissolve = 1; this.flashAt(0.15); res(); }, ms + 60));
  }
  scatter(id) {
    const a = this.actors.get(id);
    if (!a) return;
    const pts = this.sampleActor(id, 500, 8);
    a.visible = false;
    for (const p of pts) {
      this.parts.push({ x: p.x, y: p.y, vx: rand(-180, 180), vy: rand(-260, 40), r: 0, vr: rand(-6, 6), s: 6.5, c: p.c,
        life: rand(1.6, 3), age: 0, ground: this.ground + rand(0, 40) });
    }
  }

  // --------------------------------------------------------------- fx
  flashAt(a = 0.4, color = "255,240,200") { this.flash = a; this.flashColor = color; }
  shake(ms = 260) { this.shakeT = ms / 1000; }
  setDim(v) { this.dimTo = v; }
  addFx(f) { f.t0 = this.t; this.fx.push(f); return f; }
  clearFx() { this.fx = []; }

  // ----------------------------------------------------------- overlay
  pos(el, x, y) { el.style.left = `${(x / W) * 100}%`; el.style.top = `${(y / H) * 100}%`; }
  say(id, text, who, ms = 5200) {
    const a = this.actors.get(id);
    if (!a) return;
    const old = this.ov.querySelector(`.say[data-for="${id}"]`);
    if (old) old.remove();
    const el = document.createElement("div");
    el.className = "say"; el.dataset.for = id;
    if (who) { const w = document.createElement("span"); w.className = "who"; w.textContent = who; el.appendChild(w); }
    const body = document.createElement("span");
    el.appendChild(body);
    const { meta } = this.as.frame(a.sheet, a.frame);
    const top = a.y - (meta ? meta.ay * a.scale : 380) - 18;
    const x = clamp(a.x, 300, W - 300);
    this.pos(el, x, Math.max(top, 160));
    this.ov.appendChild(el);
    requestAnimationFrame(() => el.classList.add("show"));
    const full = text.length > 240 ? text.slice(0, 237) + "…" : text;
    let i = 0;
    const tick = setInterval(() => { i += 2; body.textContent = full.slice(0, i); if (i >= full.length) clearInterval(tick); }, 22);
    setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 400); }, ms + full.length * 22);
  }
  float(x, y, text, color = "gold") {
    const el = document.createElement("div");
    el.className = `float ${color}`; el.textContent = text;
    this.pos(el, x, y); this.ov.appendChild(el);
    setTimeout(() => el.remove(), 2700);
  }
  glyph(x, y, src) {
    const el = document.createElement("div");
    el.className = "glyph";
    el.innerHTML = `<img src="${src}" alt="">`;
    this.pos(el, x, y); this.ov.appendChild(el);
    setTimeout(() => el.remove(), 1500);
  }
  tag(key, x, y, text, cls = "") {
    let el = this.ov.querySelector(`.tag[data-k="${key}"]`);
    if (!el) { el = document.createElement("div"); el.className = "tag"; el.dataset.k = key; this.ov.appendChild(el); }
    el.className = `tag ${cls}`; el.textContent = text; this.pos(el, x, y);
    return el;
  }
  tablet(key, x, y, html, ms = 0) {
    let el = this.ov.querySelector(`.tablet[data-k="${key}"]`);
    if (!el) { el = document.createElement("div"); el.className = "tablet"; el.dataset.k = key; this.ov.appendChild(el); }
    el.innerHTML = html; this.pos(el, x, y);
    if (ms) setTimeout(() => el.remove(), ms);
    return el;
  }
  clearOverlay(sel = "*") { this.ov.querySelectorAll(sel).forEach((e) => e.remove()); }

  // -------------------------------------------------------------- loop
  loop(now) {
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    if (!this.paused) {
      this.t += dt;
      this.update(dt);
      this.draw();
      if (this.onFrame) this.onFrame(dt);
    }
    requestAnimationFrame((n) => this.loop(n));
  }
  update(dt) {
    for (const tw of this.tweens) {
      tw.t = Math.min(1, tw.t + (dt * 1000) / tw.ms);
      const k = tw.e(tw.t);
      for (const key of Object.keys(tw.to)) tw.obj[key] = tw.from[key] + (tw.to[key] - tw.from[key]) * k;
    }
    for (const tw of this.tweens.filter((x) => x.t >= 1)) tw.resolve();
    this.tweens = this.tweens.filter((x) => x.t < 1);
    if (this.flipT < 1) this.flipT = Math.min(1, this.flipT + dt / 1.25);
    for (const a of this.actors.values()) if (a.dissolve < 1) { a.dissolve = Math.min(1, a.dissolve + dt / 0.28); if (a.dissolve >= 1) a.prev = null; }
    this.flash = Math.max(0, this.flash - dt * 1.6);
    this.dim += (this.dimTo - this.dim) * Math.min(1, dt * 2);
    this.shakeT = Math.max(0, this.shakeT - dt);
    for (const p of this.parts) {
      p.age += dt;
      if (p.homing) {
        const k = clamp((this.t - p.t0) / p.dur, 0, 1), e = ease.out(k);
        p.x = p.sx + (p.tx - p.sx) * e; p.y = p.sy + (p.ty - p.sy) * e - Math.sin(k * Math.PI) * 60;
        p.r *= 0.9;
        if (k >= 1) p.life = 0;
        continue;
      }
      p.vy += 900 * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.r += p.vr * dt;
      if (p.y > p.ground) { p.y = p.ground; p.vy *= -0.28; p.vx *= 0.6; p.vr *= 0.5; if (Math.abs(p.vy) < 30) { p.vy = 0; p.vx *= 0.8; } }
    }
    this.parts = this.parts.filter((p) => p.age < p.life);
    // light sweeps across the gold like a slow procession of candles
    this.light.x = ((this.t * 70) % (W + 600)) - 300;
    this.spawnGlints(dt);
  }
  spawnGlints(dt) {
    const pts = this.goldPts;
    if (pts.length) {
      const n = Math.min(12, Math.floor(rand(0, 5.5) + dt * 140));
      for (let i = 0; i < n; i++) {
        const p = pts[(Math.random() * pts.length) | 0];
        const near = Math.abs(p[0] - this.light.x) < 240 || (this.light.mx !== null &&
          Math.hypot(p[0] - this.light.mx, p[1] - this.light.my) < 180);
        if (near || Math.random() < 0.18) this.glints.push({ x: p[0], y: p[1], age: 0, life: rand(0.35, 1.1), s: rand(3, 6) });
      }
    }
    for (const a of this.actors.values()) {
      if (!a.visible || !a.gold) continue;
      if (Math.random() < dt * 8) {
        const g = a.gold[(Math.random() * a.gold.length) | 0];
        if (g) this.glints.push({ x: a.x + (g[0] - a.goldMeta.ax) * a.scale, y: a.y + (g[1] - a.goldMeta.ay) * a.scale, age: 0, life: rand(0.3, 0.8), s: rand(3, 5) });
      }
    }
    for (const gl of this.glints) gl.age += dt;
    this.glints = this.glints.filter((gl) => gl.age < gl.life).slice(-260);
  }

  draw() {
    const g = this.g;
    g.save();
    if (this.shakeT > 0) g.translate(rand(-6, 6) * this.shakeT * 4, rand(-4, 4) * this.shakeT * 4);
    this.drawScene(g);
    for (const f of this.fx) if (f.under) f.draw(g, this.t - f.t0, this);
    const list = [...this.actors.values()].filter((a) => a.visible).sort((a, b) => (a.z || a.y) - (b.z || b.y));
    for (const a of list) this.drawActor(g, a);
    for (const f of this.fx) if (!f.under) f.draw(g, this.t - f.t0, this);
    this.fx = this.fx.filter((f) => !f.done);
    this.drawParts(g);
    this.drawGlints(g);
    g.restore();
    // vignette and lighting
    const v = g.createRadialGradient(W / 2, H * 0.45, H * 0.35, W / 2, H * 0.5, H * 0.95);
    v.addColorStop(0, "rgba(0,0,0,0)"); v.addColorStop(1, "rgba(5,6,18,0.5)");
    g.fillStyle = v; g.fillRect(0, 0, W, H);
    if (this.dim > 0.01) { g.fillStyle = `rgba(5,8,20,${this.dim})`; g.fillRect(0, 0, W, H); }
    if (this.flash > 0.01) { g.fillStyle = `rgba(${this.flashColor},${this.flash})`; g.fillRect(0, 0, W, H); }
  }
  drawScene(g) {
    const cur = this.as.img[`scene/${this.scene}`];
    const prev = this.prevScene && this.as.img[`scene/${this.prevScene}`];
    if (!cur) { g.fillStyle = "#0b1430"; g.fillRect(0, 0, W, H); return; }
    if (this.flipT >= 1 || !prev) { g.drawImage(cur, 0, 0, W, H); return; }
    // tile-flip: each 40px tile turns over from the old wall to the new one, sweeping from an edge
    const B = 40, cols = W / B, rows = Math.ceil(H / B);
    const sxs = cur.width / W, sys = cur.height / H, pxs = prev.width / W, pys = prev.height / H;
    const [ox, oy] = this.flipOrigin, maxD = Math.hypot(W, H);
    g.fillStyle = "#2b241d"; g.fillRect(0, 0, W, H);
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
      const x = c * B, y = r * B;
      const d = Math.hypot(x - ox, y - oy) / maxD;
      const k = clamp((this.flipT * 1.6 - d * 0.9 - hash(c, r) * 0.25) / 0.3, 0, 1);
      const useNew = k > 0.5;
      const sq = Math.abs(Math.cos(k * Math.PI));
      const h = B * Math.max(0.04, sq);
      const img = useNew ? cur : prev, sx = useNew ? sxs : pxs, sy = useNew ? sys : pys;
      g.drawImage(img, x * sx, y * sy, B * sx, B * sy, x, y + (B - h) / 2, B, h);
    }
  }
  drawActor(g, a) {
    const { im, meta } = this.as.frame(a.sheet, a.frame);
    if (!im || !meta) return;
    if (!a.gold || a.goldKey !== `${a.sheet}/${a.frame}`) {
      a.goldKey = `${a.sheet}/${a.frame}`;
      a.goldMeta = meta;
      const d = this.as.data(a.goldKey);
      a.gold = [];
      if (d) for (let y = 0; y < d.height; y += 5) for (let x = 0; x < d.width; x += 5) {
        const i = (y * d.width + x) * 4;
        if (d.data[i + 3] > 200 && d.data[i] > 170 && d.data[i + 1] > 125 && d.data[i + 2] < 110 && d.data[i] - d.data[i + 2] > 80) a.gold.push([x, y]);
      }
    }
    const sx = Math.round(a.x / SNAP) * SNAP + (a.shake ? rand(-a.shake, a.shake) : 0);
    const sy = Math.round((a.y - a.lift + Math.sin(this.t * 2 + a.x) * a.bob) / SNAP) * SNAP;
    g.save();
    g.globalAlpha = a.alpha;
    g.translate(sx, sy);
    if (a.flip) g.scale(-1, 1);
    g.scale(a.scale, a.scale);
    // soft contact shadow on the pavement
    if (a.shadow !== false) {
      g.fillStyle = "rgba(20,12,6,0.28)";
      g.beginPath(); g.ellipse(0, -2, meta.w * 0.32, 9, 0, 0, Math.PI * 2); g.fill();
    }
    if (a.prev && a.dissolve < 1) this.drawDissolve(g, a, im, meta);
    else g.drawImage(this.withHoles(a, im, meta), -meta.ax, -meta.ay);
    g.restore();
  }
  withHoles(a, im, meta) {
    if (!a.holes.length) return im;
    const key = `${a.sheet}/${a.frame}/${a.holes.length}`;
    if (a.cache && a.cache.key === key) return a.cache.c;
    const c = document.createElement("canvas");
    c.width = meta.w; c.height = meta.h;
    const g = c.getContext("2d");
    g.drawImage(im, 0, 0);
    g.globalCompositeOperation = "source-atop";
    for (const m of a.holes) paintScar(g, m.u * meta.w, m.v * meta.h, m.size, m.seed);
    a.cache = { key, c };
    return c;
  }
  drawDissolve(g, a, im, meta) {
    const old = this.as.frame(a.prev.sheet, a.prev.frame);
    const newImg = this.withHoles(a, im, meta);
    const L = Math.min(-meta.ax, old.meta ? -old.meta.ax : 0), T = Math.min(-meta.ay, old.meta ? -old.meta.ay : 0);
    const R = Math.max(meta.w - meta.ax, old.meta ? old.meta.w - old.meta.ax : 0);
    const Bt = Math.max(meta.h - meta.ay, old.meta ? old.meta.h - old.meta.ay : 0);
    for (let y = T; y < Bt; y += BLOCK) for (let x = L; x < R; x += BLOCK) {
      const useNew = hash(x, y, 3) < a.dissolve;
      const f = useNew ? { im: newImg, meta } : old;
      if (!f.im || !f.meta) continue;
      const fx = x + f.meta.ax, fy = y + f.meta.ay;
      if (fx + BLOCK <= 0 || fy + BLOCK <= 0 || fx >= f.meta.w || fy >= f.meta.h) continue;
      const cx = Math.max(0, fx), cy = Math.max(0, fy);
      const cw = Math.min(f.meta.w, fx + BLOCK) - cx, ch = Math.min(f.meta.h, fy + BLOCK) - cy;
      if (cw > 0 && ch > 0) g.drawImage(f.im, cx, cy, cw, ch, cx - f.meta.ax, cy - f.meta.ay, cw, ch);
    }
  }
  drawParts(g) {
    for (const p of this.parts) {
      const fade = p.homing ? 1 : clamp((p.life - p.age) / 0.6, 0, 1);
      g.globalAlpha = fade;
      if (p.glow) {
        g.globalCompositeOperation = "lighter";
        g.fillStyle = p.c; g.fillRect(p.x - p.s / 2, p.y - p.s / 2, p.s, p.s);
        g.globalCompositeOperation = "source-over";
        continue;
      }
      g.save(); g.translate(p.x, p.y); g.rotate(p.r);
      g.fillStyle = "rgba(30,22,14,.55)"; g.fillRect(-p.s / 2 - 1, -p.s / 2 - 1, p.s + 2, p.s + 2);
      g.fillStyle = p.c; g.fillRect(-p.s / 2, -p.s / 2, p.s, p.s);
      g.fillStyle = "rgba(255,255,255,.18)"; g.fillRect(-p.s / 2, -p.s / 2, p.s, 1.5);
      g.restore();
    }
    g.globalAlpha = 1;
  }
  drawGlints(g) {
    g.globalCompositeOperation = "lighter";
    for (const gl of this.glints) {
      const k = Math.sin((gl.age / gl.life) * Math.PI);
      g.fillStyle = `rgba(255,236,170,${0.55 * k})`;
      g.fillRect(gl.x - gl.s / 2, gl.y - gl.s / 2, gl.s, gl.s);
      if (gl.s > 4.6) { g.fillStyle = `rgba(255,250,225,${0.35 * k})`; g.fillRect(gl.x - 0.5, gl.y - gl.s * 1.2, 1, gl.s * 2.4); }
    }
    g.globalCompositeOperation = "source-over";
  }
}

// A wound in a mosaic: a fracture that runs along the grout and branches, with tesserae
// chipped out at the point of impact. size ~1 for a medium wound; seed keeps it stable.
export function paintScar(g, x, y, size = 1, seed = 1) {
  const R = (k) => hash(seed, k);
  const branches = 3 + Math.floor(R(1) * 3);
  g.lineCap = "round"; g.lineJoin = "round";
  for (let b = 0; b < branches; b++) {
    let ang = (b / branches) * Math.PI * 2 + R(10 + b) * 1.2;
    let px = x, py = y;
    const steps = 2 + Math.floor(R(20 + b) * 3 * size);
    const pts = [[px, py]];
    for (let k = 0; k < steps; k++) {
      ang += (R(30 + b * 7 + k) - 0.5) * 1.1;
      const len = (4 + R(40 + b * 5 + k) * 5) * size;
      px += Math.cos(ang) * len; py += Math.sin(ang) * len;
      pts.push([px, py]);
    }
    const w = Math.max(1, 1.9 * size * (1 - b * 0.08));
    g.strokeStyle = "rgba(245,232,200,.55)"; g.lineWidth = w + 1.2;
    g.beginPath(); pts.forEach(([u, v], i) => (i ? g.lineTo(u + 0.8, v + 0.8) : g.moveTo(u + 0.8, v + 0.8))); g.stroke();
    g.strokeStyle = "rgba(24,15,8,.92)"; g.lineWidth = w;
    g.beginPath(); pts.forEach(([u, v], i) => (i ? g.lineTo(u, v) : g.moveTo(u, v))); g.stroke();
  }
  // the chipped tesserae: dark, irregular cavities where pieces fell out
  const chips = 2 + Math.floor(R(2) * 4 * size);
  for (let i = 0; i < chips; i++) {
    const cx = x + (R(50 + i) - 0.5) * 12 * size, cy = y + (R(60 + i) - 0.5) * 12 * size;
    const r = (2 + R(70 + i) * 2.2) * Math.max(0.8, size);
    g.save(); g.translate(cx, cy); g.rotate(R(80 + i) * 1.5);
    g.fillStyle = "rgba(20,12,6,.9)";
    g.beginPath(); g.moveTo(-r, -r * 0.8); g.lineTo(r * 0.9, -r); g.lineTo(r, r * 0.7); g.lineTo(-r * 0.7, r); g.closePath(); g.fill();
    g.fillStyle = "rgba(120,98,70,.75)";
    g.fillRect(-r * 0.4, -r * 0.3, r * 0.7, r * 0.6);
    g.restore();
  }
}

export { rand, clamp, ease, hash };
