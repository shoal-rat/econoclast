// The Tabula: the verdict, every wound with its quote, the parries, and the thousand roads.

import { api } from "./bridge.js";
import { escapeHtml } from "./director.js";
import { bandFor, bandText, blurb, bladeName, getLang, getWorld, t } from "./i18n.js";
import { md } from "./md.js";
import { hash, paintScar } from "./stage.js";
import { sevDots } from "./ui.js";

export function renderTabula(root, d, { assets, onBack, onReplay, demo } = {}) {
  const f = d.fragility || { score: 0 };
  const v = d.verdict || {};
  const band = bandFor(f.score || 0);
  const meta = d.meta || {};
  const wounds = d.wounds || [];
  const parries = d.parries || [];
  const dur = meta.ended && meta.started ? Math.round((meta.ended - meta.started) / 60) : null;
  root.innerHTML = `
  <div class="tab-grid">
    <div class="tab-side">
      <canvas id="tab-medal" width="720" height="720"></canvas>
      <div class="tab-score"><div class="n">${Math.round(f.score || 0)}</div>
        <div class="l">${band ? band.latin : ""}</div><div class="tr">${escapeHtml(bandText(band))}</div></div>
      <div class="meta">${escapeHtml(blurb(band))}<br><br>
        ${escapeHtml(d.backend || "")}${dur ? ` · ${dur} min` : ""}${demo ? ` · ${t("demo_banner")}` : ""}<br>
        ${wounds.length} ${t("wounds").toLowerCase()} · ${parries.length} ⛨</div>
      <div class="btns">
        ${demo ? "" : `<button class="ghost" id="tb-html">${t("open_html")}</button>
        <button class="ghost" id="tb-folder">${t("reveal")}</button>`}
        <button class="ghost" id="tb-replay">${t("replay")}</button>
        <button class="tessera" id="tb-back">${t("new_hunt")}</button>
      </div>
    </div>
    <article class="tab-main">
      <h1>${escapeHtml(d.title || "")}</h1>
      ${v.headline ? `<p class="headline">${escapeHtml(v.headline)}</p>` : ""}
      ${v.assessment ? `<p>${escapeHtml(v.assessment)}</p>` : ""}
      ${integrityPanel(f, wounds)}
      ${d.target && d.target.claim ? `<h2>${t("the_decree")}</h2><p>${escapeHtml(d.target.claim)}</p>
        <p style="color:#7a6a58;font-size:15px">${[d.target.design, d.target.table, d.target.estimator, d.target.sample]
          .filter(Boolean).map(escapeHtml).join(" · ")}</p>` : ""}
      ${fieldSection(d.field)}
      <h2>${t("w_title")} (${wounds.length})</h2>
      ${wounds.length ? wounds.map(woundCard).join("") : `<p>${t("none_yet")}</p>`}
      ${parries.length ? `<h2>${t("p_title")}</h2>${parries.map((p) =>
        `<div class="pcard"><b>${bladeName(p.blade).latin}</b>${escapeHtml(p.note)}</div>`).join("")}` : ""}
      ${d.viae && d.viae.summary ? `<h2>${t("viae_title")}</h2><canvas id="viae-chart" width="1400" height="420"></canvas>
        <p>${d.viae.summary.n_specs_run} ${t("roads")} · ${Math.round((d.viae.summary.share_significant_expected_sign || 0) * 100)}% ${t("sig_share")}</p>` : ""}
      ${(d.speculum || []).length ? `<h2>${t("spec_title")}</h2>${d.speculum.map((s) =>
        `<p><b>${escapeHtml(s.what)}</b>: ${t("paper_val")} ${s.paper_value} · ${t("ours")} ${s.reproduced_value} — ${t(s.verdict)}${s.note ? ` (${escapeHtml(s.note)})` : ""}</p>`).join("")}` : ""}
      ${v.change_my_mind ? `<h2>${t("change")}</h2><p>${escapeHtml(v.change_my_mind)}</p>` : ""}
      ${(v.survived || []).length ? `<h2>${t("survived")}</h2><ul>${v.survived.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>` : ""}
      ${d.final ? `<h2>${t("final_msg")}</h2><div class="final-msg md">${md(d.final)}</div>` : ""}
    </article>
  </div>`;
  const $ = (s) => root.querySelector(s);
  $("#tb-back").onclick = onBack;
  $("#tb-replay").onclick = onReplay;
  if (!demo) {
    $("#tb-html").onclick = () => api.open_external(d.id, "tabula.html");
    $("#tb-folder").onclick = () => api.reveal(d.id, "");
    root.querySelectorAll(".art").forEach((el) => { el.onclick = () => api.reveal(d.id, el.dataset.p); });
  }
  drawMedal($("#tab-medal"), f, assets, wounds);
  if (d.viae && d.viae.summary) drawViae($("#viae-chart"), d.viae, d.viae_points);
  root.scrollTop = 0;
}

function integrityPanel(f, wounds) {
  const w = getWorld();
  const key = f.seal || "integrum";
  const sl = (w.seals || []).find((x) => x.key === key) || {};
  const zh = getLang() === "zh";
  const marks = wounds.filter((x) => (w.integrity_blades || []).includes(x.blade));
  return `<div class="integrity ${key}"><div class="seal-ind ${key}"><i></i></div>
    <div><b>${escapeHtml(sl.latin || "")} · ${escapeHtml(zh ? sl.zh : sl.en)}</b>
    <div>${escapeHtml(zh ? sl.blurb_zh : sl.blurb_en)}</div>
    ${marks.length ? `<div style="margin-top:6px">${marks.map((m) => `<span class="stamp" style="margin:3px 6px 0 0;font-size:13px">
      <b style="font-size:12px">${escapeHtml(bladeName(m.blade).latin.toUpperCase())}</b>${escapeHtml(m.title)}</span>`).join("")}</div>` : ""}
    <div style="margin-top:6px;font-size:14px;color:#7a6a58;font-style:italic">${t("integrity_note")}</div></div></div>`;
}

function fieldSection(fld) {
  if (!fld || !(fld.real_mechanism || fld.setting)) return "";
  const row = (k, label) => (fld[k] ? `<dt>${t(label)}</dt><dd>${escapeHtml(fld[k])}</dd>` : "");
  const list = (k, label) => ((fld[k] || []).length ? `<dt>${t(label)}</dt><dd><ul style="margin:0;padding-left:18px">${fld[k]
    .map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul></dd>` : "");
  return `<h2>${t("real_world")} · Forum</h2><div class="field"><p><b>${escapeHtml(fld.field || "")}</b> — ${escapeHtml(fld.setting || "")}</p>
    <dl>${row("claimed_mechanism", "claimed")}${row("real_mechanism", "real")}${row("institutions", "institutions")}
    ${row("magnitudes", "magnitudes")}${row("theory", "theory")}${list("rival_explanations", "rivals")}${list("sources", "sources")}</dl></div>`;
}

function woundCard(w) {
  const b = bladeName(w.blade);
  return `<div class="wcard ${w.severity}">
    <h3>${escapeHtml(w.title)}</h3>
    <div class="m">${b.latin} · ${escapeHtml(b.tr)} ${sevDots(w.severity)} · ${t("conf")} ${Math.round((w.effective_confidence ?? w.confidence) * 100)}%
      ${w.verified === false ? ` · <span class="unv">${t("quote_unverified")}</span>` : ""}</div>
    ${w.quote ? `<blockquote>${escapeHtml(w.quote)}</blockquote>` : ""}
    ${w.detail ? `<p>${escapeHtml(w.detail)}</p>` : ""}
    ${(w.artifacts || []).length ? `<p>${t("artifacts")}: ${w.artifacts.map((a) => `<span class="art" data-p="${escapeHtml(a)}">${escapeHtml(a)}</span>`).join(", ")}</p>` : ""}
    ${w.remedy ? `<p class="rem"><b>${t("remedy")}:</b> ${escapeHtml(w.remedy)}</p>` : ""}
  </div>`;
}

// The emperor as he ends: a roundel of gold with his final pose and the tiles he lost.
function drawMedal(cv, f, assets, wounds) {
  if (!cv || !assets) return;
  const g = cv.getContext("2d");
  const S = cv.width;
  const gold = assets.img["scene/ravenna"];
  g.save();
  g.beginPath(); g.arc(S / 2, S / 2, S / 2, 0, Math.PI * 2); g.clip();
  if (gold) g.drawImage(gold, 640, 300, 320, 320, 0, 0, S, S);
  else { g.fillStyle = "#c9a23a"; g.fillRect(0, 0, S, S); }
  const band = bandFor(f.score || 0);
  const pose = { defiant: "defiant", idle: "idle", wounded: "wounded", kneeling: "kneeling", fallen: "fallen" }[band ? band.pose : "idle"] || "idle";
  const { im, meta } = assets.frame("imperator", pose);
  if (im && meta) {
    const sc = (S * 0.82) / Math.max(meta.h, meta.w * 0.9);
    const x = S / 2 - meta.ax * sc, y = S * 0.93 - meta.ay * sc;
    g.drawImage(im, x, y, meta.w * sc, meta.h * sc);
    // one fracture per wound, as deep as the wound
    g.globalCompositeOperation = "source-atop";
    const depth = { critical: 1.7, high: 1.3, medium: 0.95, low: 0.65, info: 0.4 };
    (wounds || []).forEach((w, i) => {
      const u = 0.3 + hash(i, 1) * 0.4, v = 0.18 + hash(i, 2) * 0.62;
      paintScar(g, x + u * meta.w * sc, y + v * meta.h * sc, (depth[w.severity] || 0.9) * sc, 1 + i * 7919);
    });
    g.globalCompositeOperation = "source-over";
  }
  g.restore();
}

// The specification curve drawn as tesserae: one column per road, gold when it reaches
// significance in the paper's direction.
function drawViae(cv, viae, points) {
  if (!cv) return;
  const pts = (points || viae.points || []).slice().sort((a, b) => a.c - b.c);
  const g = cv.getContext("2d");
  const W = cv.width, H = cv.height, pad = 40;
  g.fillStyle = "#0d1838"; g.fillRect(0, 0, W, H);
  if (!pts.length) {
    g.fillStyle = "#c9a23a"; g.font = "28px Cinzel";
    const s = viae.summary || {};
    g.fillText(`${Math.round((s.share_significant_expected_sign || 0) * 100)}%`, W / 2 - 40, H / 2);
    return;
  }
  const lo = Math.min(0, ...pts.map((p) => p.c - 1.96 * (p.se || 0)));
  const hi = Math.max(0, ...pts.map((p) => p.c + 1.96 * (p.se || 0)));
  const y = (v) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - 2 * pad);
  const pref = (viae.summary || {}).preferred_sign || 1;
  const cw = (W - 2 * pad) / pts.length;
  g.strokeStyle = "rgba(240,213,138,.5)"; g.lineWidth = 2;
  g.beginPath(); g.moveTo(pad, y(0)); g.lineTo(W - pad, y(0)); g.stroke();
  pts.forEach((p, i) => {
    const x = pad + i * cw;
    const sig = p.p < 0.05, same = Math.sign(p.c) === pref;
    const col = sig && same ? "#e8c35a" : sig ? "#c0392b" : "#7d8597";
    g.fillStyle = col; g.globalAlpha = 0.35;
    g.fillRect(x + cw * 0.2, y(p.c + 1.96 * (p.se || 0)), Math.max(1, cw * 0.6), Math.max(1, y(p.c - 1.96 * (p.se || 0)) - y(p.c + 1.96 * (p.se || 0))));
    g.globalAlpha = 1;
    const s = Math.max(3, Math.min(9, cw * 0.9));
    g.fillRect(x + cw / 2 - s / 2, y(p.c) - s / 2, s, s);
  });
  g.fillStyle = "#e8cf7a"; g.font = "20px Cinzel";
  g.fillText(getLang() === "zh" ? "按系数排序的设定" : "specifications, sorted by estimate", pad, H - 10);
}
