// Small synthesised sounds: tesserae ticking, blades, bronze shields, the gong of the verdict.
// No audio files; everything is built from oscillators and filtered noise.

let ctx = null;
let enabled = true;

function ac() {
  if (!ctx) {
    try { ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch { ctx = null; }
  }
  if (ctx && ctx.state === "suspended") ctx.resume();
  return ctx;
}

function noise(c, dur) {
  const b = c.createBuffer(1, Math.max(1, c.sampleRate * dur), c.sampleRate);
  const d = b.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const s = c.createBufferSource();
  s.buffer = b;
  return s;
}

function env(c, node, t0, a, peak, d) {
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(peak, t0 + a);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + a + d);
  node.connect(g);
  g.connect(c.destination);
  return g;
}

function tone(c, freq, t0, dur, peak = 0.12, type = "sine") {
  const o = c.createOscillator();
  o.type = type; o.frequency.setValueAtTime(freq, t0);
  env(c, o, t0, 0.005, peak, dur);
  o.start(t0); o.stop(t0 + dur + 0.05);
  return o;
}

function filtered(c, t0, dur, freq, q, peak, type = "bandpass") {
  const n = noise(c, dur + 0.05);
  const f = c.createBiquadFilter();
  f.type = type; f.frequency.value = freq; f.Q.value = q;
  n.connect(f);
  env(c, f, t0, 0.004, peak, dur);
  n.start(t0); n.stop(t0 + dur + 0.05);
}

const SOUNDS = {
  tick(c, t) { filtered(c, t, 0.05, 3200 + Math.random() * 1500, 6, 0.05); },
  flip(c, t) { for (let i = 0; i < 9; i++) filtered(c, t + i * 0.05 + Math.random() * 0.03, 0.04, 2400 + Math.random() * 2000, 5, 0.04); },
  scroll(c, t) { filtered(c, t, 0.35, 1800, 0.8, 0.05, "highpass"); },
  strike(c, t) {
    filtered(c, t, 0.18, 900, 0.7, 0.22, "lowpass");
    tone(c, 90, t, 0.35, 0.25, "sine");
    for (let i = 0; i < 8; i++) filtered(c, t + 0.08 + i * 0.045, 0.05, 2600 + Math.random() * 2400, 5, 0.06);
  },
  clang(c, t) { tone(c, 620, t, 0.9, 0.08, "triangle"); tone(c, 931, t, 0.7, 0.05, "sine"); tone(c, 1475, t, 0.4, 0.03, "sine"); filtered(c, t, 0.08, 4000, 1, 0.08); },
  anvil(c, t) { tone(c, 1040, t, 0.35, 0.06, "triangle"); tone(c, 1560, t, 0.25, 0.03, "sine"); filtered(c, t, 0.04, 5000, 1, 0.05); },
  thud(c, t) { tone(c, 70, t, 0.3, 0.2); filtered(c, t, 0.1, 400, 1, 0.08, "lowpass"); },
  crack(c, t) { for (let i = 0; i < 6; i++) filtered(c, t + i * 0.03, 0.05, 1500 + Math.random() * 3000, 3, 0.08); },
  bell(c, t) { tone(c, 784, t, 1.6, 0.06); tone(c, 1176, t, 1.2, 0.03); tone(c, 1568, t + 0.01, 0.9, 0.02); },
  gong(c, t) { tone(c, 110, t, 3.2, 0.22); tone(c, 165, t, 2.6, 0.08); tone(c, 223, t, 2.2, 0.05); filtered(c, t, 0.5, 300, 0.7, 0.08, "lowpass"); },
  assemble(c, t) { for (let i = 0; i < 18; i++) filtered(c, t + i * 0.035, 0.04, 2000 + i * 120, 5, 0.035); tone(c, 523, t + 0.6, 0.8, 0.04); },
};

export const sfx = {
  play(name) {
    if (!enabled) return;
    const c = ac();
    if (!c || !SOUNDS[name]) return;
    try { SOUNDS[name](c, c.currentTime + 0.01); } catch { /* audio is decoration */ }
  },
  set(on) { enabled = !!on; },
  get on() { return enabled; },
  unlock() { ac(); },
};
