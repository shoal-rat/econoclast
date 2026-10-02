# The world of Econoclast

One lexicon drives the agent's orders, the stage and the reports (`src/econoclast/world.py`; the app
reads it from the engine at start-up). This page is generated from it by `tools/dev/world_doc.py`.

Ravenna, an autumn afternoon. A traveller stands under the gold of San Vitale and the mosaic moves. A
hooded figure assembles itself out of loose tesserae: the Sicarius. It walks the old procession route from
the port of Classis to the Palatium and tests the Emperor's decree, a paper's headline claim, for the
place where it bleeds.

## The walk

| # | Station | | 中文 | What happens |
|---|---|---|---|---|
| 1 | **Classis** | The Port | 克拉塞港 | Fetch the paper: the decree arrives by ship. |
| 2 | **Scriptorium** | The Scriptorium | 缮写室 | Read the paper and examine the parchment: its claim, its numbers, its earlier versions, any forgery or rouge. |
| 3 | **Forum** | The Forum | 广场 | Learn the field: the real actors, institutions and theory the decree claims to describe. |
| 4 | **Horreum** | The Warehouse | 仓廪 | Find the data: replication packages, public sources, or the traveller's help. |
| 5 | **Fabrica** | The Arms Forge | 兵器工坊 | Build the local quant workshop and reproduce the headline number. |
| 6 | **Palatium** | The Palace Gate | 宫门 | The seven method blades: each line of attack against the paper's defences. |
| 7 | **Aula** | The Throne Hall | 王座厅 | A thousand roads: re-run the result across every defensible specification. |
| 8 | **Curia** | The Tribunal | 元老院 | The verdict: how badly the decree is wounded. |

## The blades

Each blade ends in one or more wounds or a parry.

| Blade | | 中文 | Hunts for | Where it is swung |
|---|---|---|---|---|
| **Labyrinthus** | The Labyrinth | 迷宫之刃 | Specification search: the garden of forking paths, a headline spec picked from many. | Palatium |
| **Canistrum** | The Fruit Basket | 果篮之刃 | Cherry-picking: convenient samples, windows, subgroups, outcomes, dropped data. | Palatium |
| **Persona** | The Mask | 面具之刃 | Identification: is the causal face real, or a mask over correlation? | Palatium |
| **Inversio** | The Inversion | 倒置之刃 | Reverse causality: the outcome driving the cause, simultaneity, timing that runs backwards. | Forum |
| **Theoria** | The Theory | 理论之刃 | Theory misused: a model whose assumptions fail here, or that predicts something else. | Forum |
| **Novacula** | Occam's Razor | 剃刀之刃 | Needless theory: mechanisms, assumptions and parameters that explain nothing a simpler account does not, or that are bolted on to explain away contradicting facts. | Forum |
| **Mundus** | The World | 现实之刃 | Reality: a mechanism real people would not follow, institutions that do not work that way, magnitudes the world cannot produce. | Forum |
| **Scutum** | The Shield | 盾牌之刃 | Robustness: which standard checks are present and which are conveniently missing. | Palatium |
| **Augur** | The Augur | 占卜之刃 | HARKing: hypotheses and mechanisms written after the results were known. | Palatium |
| **Tuba** | The Herald's Horn | 号角之刃 | Over-claiming: the abstract promises more than the design can deliver. | Palatium |
| **Bibliotheca** | The Library | 书库之刃 | Literature: novelty claims, contradicted findings, citations that do not resolve or do not say what the paper claims they say. | Palatium |
| **Falsum** | The Forgery | 伪造之刃 | Fabrication: numbers and data that carry the fingerprints of being made up or doctored. | Scriptorium (paper), Fabrica (data) |
| **Palimpsestus** | The Palimpsest | 改写之刃 | Rewriting: outcomes, samples or hypotheses quietly changed between versions or against the pre-registration. | Scriptorium |
| **Fucus** | The Rouge | 粉饰之刃 | Spin: abstract numbers the tables never show, buried nulls, 'marginal' significance, misleading figures and framings. | Scriptorium |
| **Abacus** | The Abacus | 算盘之刃 | Arithmetic: reported coefficients, errors, stars and p-values that cannot all be true. | Scriptorium |
| **Speculum** | The Mirror | 铜镜之刃 | Reproduction: re-running the paper's own specification on its own data, and reading the authors' code for undisclosed drops, filters and recodes. | Fabrica |
| **Mille Viae** | A Thousand Roads | 千径之刃 | Multiverse: how often the result survives across every defensible specification. | Aula |

## The verdict

The fragility score (0-100) is read as the Emperor's fate:

| Score below | Verdict | | 中文 | The Emperor on the wall |
|---|---|---|---|---|
| 15 | **Imperator stat** | The Emperor stands | 皇帝屹立 | defiant |
| 35 | **Laesus** | Grazed | 擦伤 | idle |
| 60 | **Vulneratus** | Wounded | 负伤 | wounded |
| 80 | **Moribundus** | Mortally wounded | 重伤垂危 | kneeling |
| 100 | **Cecidit** | Fallen | 倒下 | fallen |

## The seal

Integrity is judged apart from fragility. The integrity blades (abacus, falsum, speculum, palimpsestus, fucus) set the seal on the decree:

| Seal | | 中文 | Meaning |
|---|---|---|---|
| **Sigillum integrum** | Seal intact | 封印完好 | No sign of fabricated numbers, rewritten versions, undisclosed data steps or spin. |
| **Sigillum dubium** | Seal questioned | 封印存疑 | Some integrity flags deserve a human look; each may have an innocent explanation. |
| **Sigillum fractum** | Seal broken | 封印破损 | Serious integrity flags: numbers that cannot be true, data or versions bent toward the conclusion. A hypothesis to verify with the authors, not an accusation. |

## The figures on the wall

| Figure | Is |
|---|---|
| The Emperor | the paper, holding its decree; cracks open in his portrait as wounds land |
| The Sicarius | the agent (Claude Code or Codex) |
| Conspirators | subagents the Sicarius sends to work a blade in parallel (re-glazed in porphyry) |
| The traveller | you, when the agent needs a file it cannot reach |
| The palace guards | the paper's methodological defences, one per method blade |
| The people of the Forum | the real actors the theory describes: the baker (Inversio), the philosopher (Theoria), the market woman (Mundus), the labourer with his plain explanation (Novacula) |
| The decree's parchment | in the Scriptorium, stamped in red for every integrity wound, green for every integrity parry |
| The tribunal | the verdict |
