#!/usr/bin/env python3
"""Regenerate docs/world.md from the lexicon in src/econoclast/world.py."""
from __future__ import annotations

from pathlib import Path

from econoclast import world

WHERE = {"labyrinthus": "Palatium", "canistrum": "Palatium", "persona": "Palatium", "scutum": "Palatium",
         "augur": "Palatium", "tuba": "Palatium", "bibliotheca": "Palatium", "inversio": "Forum",
         "theoria": "Forum", "novacula": "Forum", "mundus": "Forum", "falsum": "Scriptorium (paper), Fabrica (data)",
         "palimpsestus": "Scriptorium", "fucus": "Scriptorium", "abacus": "Scriptorium", "speculum": "Fabrica",
         "mille_viae": "Aula"}


def render() -> str:
    L = ["# The world of Econoclast", "",
         "One lexicon drives the agent's orders, the stage and the reports (`src/econoclast/world.py`; the app",
         "reads it from the engine at start-up). This page is generated from it by `tools/dev/world_doc.py`.", "",
         "Ravenna, an autumn afternoon. A traveller stands under the gold of San Vitale and the mosaic moves. A",
         "hooded figure assembles itself out of loose tesserae: the Sicarius. It walks the old procession route from",
         "the port of Classis to the Palatium and tests the Emperor's decree, a paper's headline claim, for the",
         "place where it bleeds.", "", "## The walk", "",
         "| # | Station | | 中文 | What happens |", "|---|---|---|---|---|"]
    for i, s in enumerate(world.STATIONS, 1):
        L.append(f"| {i} | **{s.latin}** | {s.en} | {s.zh} | {s.act_en} |")
    L += ["", "## The blades", "", "Each blade ends in one or more wounds or a parry.", "",
          "| Blade | | 中文 | Hunts for | Where it is swung |", "|---|---|---|---|---|"]
    for b in world.BLADES:
        L.append(f"| **{b.latin}** | {b.en} | {b.zh} | {b.hunts_en} | {WHERE.get(b.key, '')} |")
    L += ["", "## The verdict", "", "The fragility score (0-100) is read as the Emperor's fate:", "",
          "| Score below | Verdict | | 中文 | The Emperor on the wall |", "|---|---|---|---|---|"]
    for b in world.BANDS:
        L.append(f"| {b.ceiling if b.ceiling <= 100 else '100'} | **{b.latin}** | {b.en} | {b.zh} | {b.pose} |")
    L += ["", "## The seal", "",
          "Integrity is judged apart from fragility. The integrity blades (" + ", ".join(world.INTEGRITY_BLADES)
          + ") set the seal on the decree:", "", "| Seal | | 中文 | Meaning |", "|---|---|---|---|"]
    for x in world.SEALS:
        L.append(f"| **{x.latin}** | {x.en} | {x.zh} | {x.blurb_en} |")
    L += ["", "## The figures on the wall", "", "| Figure | Is |", "|---|---|",
          "| The Emperor | the paper, holding its decree; cracks open in his portrait as wounds land |",
          "| The Sicarius | the agent (Claude Code or Codex) |",
          "| Conspirators | subagents the Sicarius sends to work a blade in parallel (re-glazed in porphyry) |",
          "| The traveller | you, when the agent needs a file it cannot reach |",
          "| The palace guards | the paper's methodological defences, one per method blade |",
          "| The people of the Forum | the real actors the theory describes: the baker (Inversio), the philosopher"
          " (Theoria), the market woman (Mundus), the labourer with his plain explanation (Novacula) |",
          "| The decree's parchment | in the Scriptorium, stamped in red for every integrity wound, green for every"
          " integrity parry |",
          "| The tribunal | the verdict |", ""]
    return "\n".join(L)


if __name__ == "__main__":
    Path(__file__).resolve().parents[2].joinpath("docs", "world.md").write_text(render(), encoding="utf-8")
