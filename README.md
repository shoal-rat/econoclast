<div align="center">

# 🪓 Econoclast

### An adversarial AI referee that red-teams empirical-economics papers.

*Hunts p-hacking, cherry-picking, specification search, and reporting errors — with a battery of
deterministic statistical forensics and multi-model LLM critiques.*

[![CI](https://github.com/OWNER/econoclast/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/econoclast/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)

</div>

---

> Most empirical papers are, structurally, a search problem: pick a sample, a window, a set of
> controls, a specification, and a clustering — then keep what is significant and write the story
> around it. **Econoclast automates the *other* side of that game**: it re-derives the numbers, hunts
> the forking paths, checks the result against the literature, and tells you how fragile the headline
> claim really is.

It runs at two levels:

1. **Deterministic forensics** — `statcheck`, GRIM, GRIMMER, p-curve, z-statistic bunching (caliper),
   TIVA / R-index, Benford and terminal-digit tests. **No API key, no network, fully reproducible.**
2. **Multi-model adversarial agent** — reads the paper + related literature and runs LLM "attacks"
   for specification search, cherry-picking, identification flaws, missing robustness, HARKing, and
   over-claiming — then a referee model synthesises a verdict and a **fragility score**.

You can run level 1 alone (offline, instant) or add level 2 with any provider — OpenAI, Anthropic,
Google, OpenRouter, or a **local model via Ollama**.

---

## ⚡ Quickstart

```bash
pip install econoclast            # or: pip install "econoclast[all]"
```

**Offline forensics in 5 seconds — no keys required:**

```bash
econoclast forensics examples/demo_paper.txt
```

```text
                              Minimum Wages and Teen Employment (synthetic)
 Test       Verdict      N   Summary
 statcheck  suspicious   2   2/2 reported p-values disagree with the recomputed value, 2 flipping
                             significance at .05.
 grim       suspicious   1   1/1 reported means are mathematically impossible for integer data of that N.
 grimmer    suspicious   1   1/1 (mean, SD, N) triples are impossible for integer data.
 p-curve    suspicious   6   p-curve is flat/left-skewed: consistent with p-hacking.
 caliper    suspicious  18   Test statistics bunch just above conventional significance thresholds.
```

**Full adversarial review (add a key for the LLM attacks):**

```bash
export ANTHROPIC_API_KEY=...        # or OPENAI_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY
econoclast review path/to/paper.pdf -o report/
# -> report/report.md, report.json, report.html
```

**Or click around in the web UI:**

```bash
pip install "econoclast[ui]"
econoclast ui
```

---

## 🧪 What it produces

A single **fragility score (0–100)** with a verdict band, an itemised list of **findings** (each with
severity, confidence, a verbatim quote, and a concrete fix), the full **deterministic forensic
battery**, and an LLM **referee summary** of what would change the verdict — rendered as Markdown,
JSON, or a self-contained HTML page.

```text
┌── Minimum Wages and Teen Employment ───────────────────────────────┐
│ Fragility 77.9/100  Fragile                                        │
│ The central claim looks fragile to plausible alternative choices.  │
│ ⚠ Integrity flag: a reported statistic is internally impossible.   │
└──────────────────────────── did, panel_fe ────────────────────────┘
```

---

## 🔬 The attack catalog

Every check returns the same `Finding` type, so the report and fragility score treat statistics and
LLM reasoning uniformly. Deterministic checks need no key; LLM checks are *grounded* (every finding
must quote the paper) and **design-gated** (the RDD critique only fires on an RDD paper).

| Attack | Kind | Catches | Needs LLM? |
|---|---|---|---|
| **statcheck** | deterministic | reported p ≠ p recomputed from the test statistic (esp. significance flips) | – |
| **GRIM** | deterministic | means that are impossible for integer data of that N | – |
| **GRIMMER** | deterministic | impossible (mean, SD, N) triples | – |
| **p-curve** | deterministic | flat/left-skewed significant-p distribution (p-hacking vs evidential value) | – |
| **caliper / bunching** | deterministic | test statistics piled up just above 1.96 / 1.645 / 2.576 | – |
| **TIVA + R-index** | deterministic | z-scores "too consistent" to be independent; inflated success rate | – |
| **Benford** | deterministic | first-digit anomalies across reported numbers | – |
| **terminal-digit** | deterministic | rounding / heaping on 0 and 5 | – |
| **specification-search** | LLM | the garden of forking paths; fragile headline specs | ✅ |
| **cherry-picking** | LLM | selective samples, windows, subgroups, outcomes, dropped data | ✅ |
| **identification-critique** | LLM | DiD parallel trends, RDD manipulation, IV exclusion/weak instruments… | ✅ |
| **robustness-coverage** | LLM | which standard robustness checks are conveniently missing | ✅ |
| **HARKing** | LLM | hypotheses/mechanisms that look invented after the results | ✅ |
| **over-claiming** | LLM | abstract/conclusion claims the evidence does not earn | ✅ |
| **literature-contradiction** | LLM | novelty/positioning claims vs retrieved related work | ✅ |

Run `econoclast attacks` to list them, or `--attacks statcheck,caliper` to run a subset.
See [docs/attacks.md](docs/attacks.md) for the algorithms and references behind each one.

---

## 🧠 How it works

```
  paper.pdf / .tex / .txt
          │
          ▼
   ┌──────────────┐   PyMuPDF / pypdf / LaTeX parse + section segmentation
   │   ingest     │   + regex harvest of (coef, se, t/z, p, mean, sd, N, stars)
   └──────┬───────┘
          ▼
   ┌──────────────┐   keyword-detect design: DiD / RDD / IV / matching / RCT / structural
   │ design gate  │
   └──────┬───────┘
          ▼
   ┌──────────────┐   OpenAlex · Semantic Scholar · arXiv · Crossref  (+ your local corpus)
   │ literature   │
   └──────┬───────┘
          ▼
   ┌──────────────┐   deterministic forensics (offline)  ┐
   │   attacks    │   LLM critiques (concurrent, grounded)├─► Finding[]
   └──────┬───────┘                                       ┘
          ▼
   ┌──────────────┐   referee model meta-review + saturating fragility score
   │   report     │   → Markdown / JSON / HTML
   └──────────────┘
```

The orchestration is a **bounded, reproducible pipeline** (not an open-ended agent loop): a fixed,
design-gated attack set, every LLM finding grounded in a quote, and a separate referee model for the
final synthesis. Architecture notes in [docs/architecture.md](docs/architecture.md).

### Multi-model by design

Attacks ask for a *role* (`extractor`, `attacker`, `referee`); the router resolves it to a model with
automatic fallback and cost accounting. Configure it in `econoclast.yaml`:

```yaml
models:
  extractor: anthropic:claude-haiku-4-5-20251001     # cheap & fast
  attacker:                                           # strong reasoning, with a fallback
    - anthropic:claude-opus-4-8
    - openai:gpt-4o
  referee: anthropic:claude-opus-4-8
literature:
  enabled: true
  sources: [openalex, arxiv, semantic_scholar]
  local_dirs: ["~/papers/io-reading-list"]            # your own corpus
```

Point a role at a local model with no key:

```yaml
models:
  attacker: { provider: ollama, model: "llama3.1:70b" }
```

…or hand everything to [LiteLLM](https://github.com/BerriAI/litellm) for 100+ providers:
`{ provider: litellm, model: "gemini/gemini-1.5-pro" }`. More in [docs/models.md](docs/models.md).

---

## 🆚 How it's different

`statcheck` checks p-values. `specr` / multiverse packages run specification curves *if you have the
data*. AI "reviewer" tools write prose. Econoclast is the first open tool to put **statistical
forensics, literature grounding, and a multi-model adversarial referee in one pipeline** that runs
from the **PDF alone** — and degrades gracefully to pure-offline forensics when you have no keys.

It stands on the shoulders of (and credits) `statcheck`, the GRIM/GRIMMER/SPRITE data-forensics
suite, p-curve, the Brodeur et al. test-statistic-bunching work, and agent harnesses like
gpt-researcher, PaperQA2, the AI-Scientist, and smolagents.

---

## ⚖️ Limitations & ethics

**Econoclast is a screening tool, not a verdict machine.** Read [docs/interpreting-reports.md](docs/interpreting-reports.md)
before quoting any finding.

- A statistical *inconsistency* (statcheck/GRIM) can be an honest typo, not fabrication.
- Distribution tests (p-curve, caliper, TIVA, Benford) are weak on small samples and assume conditions
  a single paper may not meet — they are flagged with caveats and capped at low confidence.
- LLM findings can be wrong or over-confident; every one carries a quote so **you can verify it**.
- Do not use this to harass authors. Use it to make your own work bulletproof, to referee more
  thoroughly, or to teach students what robustness actually requires.

---

## 🗺️ Roadmap

- [ ] Replication mode: sandboxed re-execution of authors' code + automatic specification curves
- [ ] RDD density (McCrary / Cattaneo-Jansson-Ma) and staggered-DiD (Callaway-Sant'Anna) re-estimation
- [ ] SPRITE / DEBIT reconstructions; PET-PEESE & Andrews-Kasy selection models for meta-analyses
- [ ] GROBID / `marker` ingestion for hard PDF layouts
- [ ] Batch mode over a folder / a journal issue

---

## 🤝 Contributing

New attacks are easy to add — subclass `Attack`, return `Finding`s, register it. See
[CONTRIBUTING.md](CONTRIBUTING.md). Issues and PRs welcome.

```bash
git clone https://github.com/OWNER/econoclast && cd econoclast
pip install -e ".[dev,pdf]"
pytest && ruff check src tests
```

## 📜 Citation

```bibtex
@software{econoclast,
  title  = {Econoclast: an adversarial AI referee for empirical economics},
  year   = {2026},
  url    = {https://github.com/OWNER/econoclast}
}
```

## License

MIT — see [LICENSE](LICENSE). Built with ❤️ for honest empirical work.
