# Changelog

All notable changes to Econoclast are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [0.1.0] — 2026-06-04

First public release.

### Added
- **Ingest:** PDF (PyMuPDF with pypdf fallback), LaTeX (with one-level `\input` resolution), and
  plain-text loaders; section segmentation; conservative regex harvest of statistical claims
  (coefficients, standard errors, t/F/r/z/χ² statistics, p-values, means/SDs, stars, N).
- **Deterministic forensics:** statcheck, GRIM, GRIMMER, p-curve, caliper/z-bunching, TIVA + R-index,
  Benford, terminal-digit — all offline, all unit-tested.
- **Multi-model LLM layer:** provider-agnostic router with fallbacks and cost accounting; OpenAI-
  compatible, Anthropic, Google Gemini, Ollama/local, and LiteLLM passthrough providers; an offline
  mock provider.
- **LLM attacks:** specification-search, cherry-picking, identification-critique (design-gated),
  robustness-coverage, HARKing, over-claiming, literature-contradiction — all quote-grounded.
- **Literature:** keyless OpenAlex / Semantic Scholar / arXiv / Crossref search + local corpus + keyword ranking.
- **Agent & report:** bounded orchestration, referee meta-review synthesis, saturating fragility score
  with an integrity override, and Markdown / JSON / HTML rendering.
- **Interfaces:** Typer CLI (`review`, `forensics`, `claims`, `attacks`, `models`, `ui`, `version`)
  and an optional Streamlit web UI.
- Docs, a synthetic demo paper with planted issues, and a test suite that runs fully offline.

[0.1.0]: https://github.com/OWNER/econoclast/releases/tag/v0.1.0
