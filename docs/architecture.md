# Architecture

Econoclast is a **bounded, reproducible pipeline**, not an open-ended agent loop. The attack set is
fixed and design-gated, every LLM finding is grounded in a quote, and a separate referee model does
the final synthesis. This trades some autonomy for auditability — the right trade for a tool whose
whole job is rigour.

```
econoclast/
├── ingest/        PDF (PyMuPDF/pypdf) + LaTeX parsing, section segmentation, claim harvesting
├── forensics/     deterministic statistical tests (statcheck, GRIM, GRIMMER, p-curve, caliper, …)
├── literature/    keyless search (OpenAlex, S2, arXiv, Crossref) + local corpus + keyword ranking
├── llm/           provider-agnostic router (OpenAI-compatible, Anthropic, Google, Ollama, LiteLLM)
├── attacks/       the unified Attack/Finding model: forensic wrappers + LLM critiques + design gating
├── agent/         the orchestrator + referee synthesis
├── report/        fragility score + Markdown/JSON/HTML rendering
├── ui/            optional Streamlit app
└── cli.py         Typer CLI
```

## The pipeline

1. **Ingest.** Load PDF/LaTeX/text -> `Paper` (title, abstract, sections, tables). A conservative regex
   pass harvests every `StatClaim` it can: `(coef, se)`, t/F/r/z/χ² statistics with df, p-values,
   means/SDs, stars, and N.
2. **Detect design.** Keyword detection tags the paper with `did / rdd / iv / matching / rct / panel_fe
   / structural`. This *gates* design-specific attacks and tailors prompts.
3. **Literature.** Build a query from the title + abstract, search the keyless sources (and any local
   corpus), rank by keyword overlap + citation count. Used to ground the referee and the
   literature-contradiction attack.
4. **Attack.** Forensics run first (fast, offline, ordered). LLM attacks run **concurrently** in a
   thread pool — the router is thread-safe and accumulates cost. Each attack is gated, and one
   attack failing never kills the run.
5. **Synthesise.** A `fragility` score aggregates findings by `severity × confidence` (saturating,
   with an integrity override). The referee model writes a meta-review: a one-line verdict, a
   specific assessment, and the single most decisive test that would change its mind.
6. **Report.** Render to Markdown, JSON, and a self-contained HTML page.

## Design choices worth knowing

- **Roles, not models.** Attacks request `extractor` / `attacker` / `referee`; the router picks the
  model and falls back on failure. Cheap work goes to a cheap model.
- **ReAct-style JSON, not native tool-calling.** The LLM layer uses a portable JSON contract so that
  local Ollama models (which lack native function calling) behave exactly like frontier APIs.
- **Grounding.** Every LLM finding must include a verbatim quote; ungrounded findings are capped at
  low confidence. This is the main defence against hallucinated problems.
- **Graceful degradation.** No keys -> forensics-only report via the mock provider. A literature source
  down -> it returns `[]` and the run continues.
- **Reproducibility.** Deterministic forensics are pure functions of the extracted numbers; the same
  paper yields the same battery every time.
