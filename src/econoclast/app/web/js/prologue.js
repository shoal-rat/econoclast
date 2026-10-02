// The prologue: a traveller in San Vitale, and the gold that comes alive.

import { t } from "./i18n.js";
import { sfx } from "./sfx.js";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function prologue(stage, { skipSignal }) {
  const cap = document.querySelector("#caption");
  let skipped = false;
  skipSignal.then(() => { skipped = true; });
  const wait = async (ms) => { const end = performance.now() + ms; while (!skipped && performance.now() < end) await sleep(60); };
  const caption = async (k, text, ms) => {
    if (skipped) return;
    cap.innerHTML = `${k ? `<span class="k">${t(k)}</span>` : ""}<span class="t">${t(text)}</span>`;
    cap.classList.add("show");
    await wait(ms);
    cap.classList.remove("show");
    await wait(500);
  };

  stage.clearActors(); stage.clearOverlay(); stage.clearFx();
  stage.ground = 885;
  stage.setScene("ravenna", { flip: false });
  stage.flipT = 1;
  stage.dim = 1; stage.setDim(0);
  // the panel's figures exist but are still dead gold
  const emp = stage.actor("emp", { sheet: "imperator", frame: "idle", x: 812, y: 622, scale: 0.74, visible: false, shadow: false });
  const g1 = stage.actor("gA", { sheet: "custodes", frame: "a_idle", x: 985, y: 626, scale: 0.55, visible: false, shadow: false });
  const g2 = stage.actor("gB", { sheet: "custodes", frame: "b_idle", x: 1075, y: 628, scale: 0.55, visible: false, shadow: false, flip: false });
  const trav = stage.actor("trav", { sheet: "peregrinus", frame: "walk", x: -150, y: 890, scale: 0.95, z: 2000 });
  void emp; void g1; void g2;

  await wait(800);
  const walking = stage.walk("trav", 380, { ms: 3200 });
  await caption("pro1k", "pro1", 3600);
  await walking;
  stage.pose("trav", "awe");
  await caption("pro2k", "pro2", 3400);
  if (!skipped) { stage.pose("trav", "photo"); await wait(700); stage.flashAt(0.55, "255,255,255"); sfx.play("tick"); await wait(900); }
  // the gold wakes up
  if (!skipped) {
    stage.pose("trav", "amazed");
    stage.flipOrigin = [800, 420];
    stage.prevScene = "ravenna"; stage.flipT = 0; sfx.play("flip");
  }
  await caption("pro3k", "pro3", 2400);
  if (!skipped) {
    sfx.play("assemble");
    await Promise.all([stage.assemble("emp", 1600, "above"), stage.assemble("gA", 1500, "above"), stage.assemble("gB", 1500, "above")]);
  }
  if (!skipped) {
    stage.actor("sic", { sheet: "sicarius", frame: "idle", x: 640, y: 624, scale: 0.56, shadow: false });
    sfx.play("assemble");
    await stage.assemble("sic", 1900);
  }
  await caption("pro4k", "pro4", 3000);
  if (!skipped) {
    // the assassin steps down out of the wall, toward the traveller
    const sic = stage.get("sic");
    stage.pose("sic", "walk1");
    await stage.tween(sic, { x: 600, y: 860, scale: 0.98 }, 1600, "inOut");
    stage.pose("sic", "idle");
    sic.shadow = true;
    stage.say("sic", t("pro5"), t("sicarius"), 3200);
    await wait(4200);
  }
  await caption("pro6k", "pro6", 3200);
  cap.classList.remove("show");
}
