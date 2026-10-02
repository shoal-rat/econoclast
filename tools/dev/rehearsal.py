#!/usr/bin/env python3
"""A scripted hunt for working on the stage: no agent, real arsenal calls, real pauses.

  .venv/bin/python tools/dev/rehearsal.py <paper.pdf> <data.csv> [--lang zh] [--speed 1]

Walks every station and swings every blade so each animation can be watched in the app
(`econoclast app --browser`, then open the case from Recent hunts).
"""
from __future__ import annotations

import argparse
import os
import shutil
import time
from pathlib import Path

from econoclast.arsenal.tools import Arsenal
from econoclast.case import Case


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("paper")
    ap.add_argument("data")
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--speed", type=float, default=1.0)
    a = ap.parse_args()
    zh = a.lang == "zh"
    case = Case.create(paper="(rehearsal) " + Path(a.paper).name, lang=a.lang, note="rehearsal")
    case.update_meta(status="running", started=time.time(), backend_used="rehearsal", runner_pid=os.getpid())
    ars = Arsenal(case)
    say = lambda en, cn: case.emit("narrate", who="sicarius", text=cn if zh else en)  # noqa: E731
    tool = lambda name, fam, summ: case.emit("tool", id=str(time.time()), who="sicarius", name=name, family=fam, summary=summ)  # noqa: E731
    pause = lambda s: time.sleep(s / a.speed)  # noqa: E731

    case.emit("case.opened", backend="rehearsal", paper=a.paper, lang=a.lang)
    pause(2)
    ars.proclaim("classis", "fetch the paper")
    say("I'll bring the paper into port first.", "先把论文运进港口。")
    tool("WebFetch", "web", "nber.org/papers/w4509")
    pause(2)
    shutil.copy(a.paper, case.path("paper", Path(a.paper).name))
    case.emit("acquired", what="paper", ok=True, file=f"paper/{Path(a.paper).name}", filetype="pdf")
    pause(2)
    ars.proclaim("scriptorium", "read and examine the parchment")
    say("Reading the paper and checking every number on it.", "通读论文，逐个核对上面的数字。")
    ars.read_paper(str(case.path("paper", Path(a.paper).name)))
    pause(2)
    ars.mark_target("Raising NJ's minimum wage did not reduce fast-food employment; NJ stores gained 2.76 FTE.",
                    design="difference-in-differences", table="Table 3", coefficient=2.76, std_error=1.36,
                    paper_title="Minimum Wages and Employment")
    pause(2)
    tool("mcp__arsenal__forensics_paper", "arsenal:forensics_paper", "forensics_paper")
    ars.forensics_paper()
    pause(2)
    ars.inflict_wound("fucus", "摘要宣传13%的就业增长，正文主表只支持“没有就业损失”" if zh else
                      "The abstract sells a 13% rise the main table only supports as 'no loss'", "medium",
                      "detail", confidence=0.7, quote="Our empirical findings challenge the prediction")
    pause(2)
    ars.parry("palimpsestus", "未找到改写过的旧版本" if zh else "No rewritten earlier version found")
    pause(1)
    ars.parry("abacus", "数字彼此一致" if zh else "The reported numbers are consistent")
    pause(2)
    ars.proclaim("forum", "learn how fast-food owners really respond")
    say("To the forum: how do franchise owners actually react to a wage floor?",
        "去广场：真实的加盟店老板面对最低工资会怎么做？")
    tool("WebSearch", "search", "fast food franchise response minimum wage survey managers")
    pause(2)
    ars.field_notes("劳动经济学：最低工资" if zh else "Labour economics: minimum wages",
                    "1992 NJ/PA fast food", actors=["franchise owners", "teen workers", "customers"],
                    claimed_mechanism="monopsony", real_mechanism="price pass-through and fewer hours",
                    theory="competitive vs monopsony labour market", sources=["https://example.org/survey"],
                    rival_explanations=["PA-specific downturn"])
    pause(3)
    ars.inflict_wound("inversio", "工资上调的时机可能跟随了预期的需求" if zh else "Timing may follow expected demand",
                      "medium", "detail", confidence=0.55, quote="Our empirical findings challenge the prediction")
    pause(2)
    ars.parry("theoria", "垄断买方模型的假设在快餐业可以成立" if zh else "Monopsony assumptions are plausible here")
    pause(2)
    ars.inflict_wound("mundus", "老板们主要靠涨价消化成本，与“雇得更多”的机制不符" if zh else
                      "Owners passed costs into prices, not more hiring", "high", "detail", confidence=0.7,
                      quote="Our empirical findings challenge the prediction")
    pause(2)
    ars.proclaim("horreum", "Card's public data")
    case.emit("acquired", what="data", ok=True, url="https://davidcard.berkeley.edu/data_sets/njmin.zip",
              n_files=3, tables=["data/njmin.csv"])
    shutil.copy(a.data, case.path("data", "njmin.csv"))
    ars.inspect_dataset("data/njmin.csv")
    pause(2)
    ars.proclaim("fabrica", "reproduce Table 3")
    tool("Bash", "shell", "python code/reproduce.py")
    pause(2)
    ars.reproduce("Table 3 DiD in FTE", 2.76, 2.754, 1.36, 1.342, "code/reproduce.py")
    pause(2)
    ars.forensics_data("data/njmin.csv")
    pause(2)
    ars.parry("falsum", "数据没有伪造的指纹" if zh else "No fabrication fingerprints in the data")
    ars.parry("speculum", "完全复现" if zh else "Reproduces exactly")
    pause(2)
    ars.proclaim("palatium", "the method blades")
    for b, ok in (("labyrinthus", False), ("canistrum", True), ("persona", False), ("scutum", False),
                  ("augur", True), ("tuba", False), ("bibliotheca", False)):
        if ok:
            ars.parry(b, "防线成立" if zh else "The defence holds")
        else:
            ars.inflict_wound(b, f"{b} 伤口" if zh else f"A {b} wound", "medium", "detail", confidence=0.6,
                              quote="Our empirical findings challenge the prediction")
        pause(2.2)
    ars.proclaim("aula", "a thousand roads")
    cols = [c for c in ("chain", "co_owned", "centralj", "southj") if c]
    res = ars.mille_viae({"data": "data/njmin.csv", "outcome": "demp", "treatment": "state", "controls_pool": cols,
                          "preferred_sign": 1})
    print("viae", res.get("ok"), res.get("message"))
    pause(4)
    ars.proclaim("curia", "the verdict")
    pause(2)
    ars.pronounce_verdict("诏书伤得不轻。" if zh else "The decree is badly hurt.", "assessment", "change", ["data"])
    case.emit("final", text="## Verdict\n\n- **one**\n- two")
    case.update_meta(status="done", ended=time.time())
    case.emit("case.closed", status="done")
    print(case.id)


if __name__ == "__main__":
    main()
