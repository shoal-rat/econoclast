# Architecture

Econoclast is a **bounded, reproducible pipeline**, not an open-ended agent loop. The attack set is
fixed and design-gated, every LLM finding is grounded in a quote, and a separate referee pass does
the final synthesis. This trades some autonomy for auditability, the right trade for a tool whose
whole job is rigour.

It is a native-LLM tool. It ships no model and no API client; it borrows the intelligence of the
agent you already run by driving the `claude` or `codex` CLI as a subprocess under that CLI's own
subscription auth. If neither CLI is on PATH it stops with a clear message rather than degrading to
something weaker.

```
econoclast/
├── ingest/        PDF (PyMuPDF/pypdf) + LaTeX parsing, section segmentation, claim harvesting,
│                  fetching (httpx, with a Playwright browser fallback for blocked sites)
├── literature/    keyless search (OpenAlex, S2, arXiv, Crossref) + local corpus + keyword ranking
├── llm/           the backend: drive the claude or codex CLI as a subprocess (backend.py)
├── attacks/       the unified Attack/Finding model: LLM critiques + methodology audit + design gating
├── replication/   specification-curve / multiverse re-estimation when the data is public
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
4. **Attack.** The grounded LLM critiques (specification-search, cherry-picking, identification,
   robustness-coverage, HARKing, over-claiming, literature-contradiction), a research-then-verify
   methodology audit for methods the tool does not cover, and a citation-check against Crossref run
   **concurrently** in a thread pool. The backend is thread-safe. Each attack is gated, and one
   attack failing never kills the run.
5. **Synthesise.** A `fragility` score aggregates findings by `severity × confidence` (saturating,
   with an integrity override). The referee pass writes a meta-review: a one-line verdict, a
   specific assessment, and the single most decisive test that would change its mind.
6. **Report.** Render to Markdown, JSON, and a self-contained HTML page.

## Design choices worth knowing

- **One backend, one model.** The only model setting is the backend: `backend: auto | claude | codex`
  (or `--backend`), with an optional `model:` override and `backend_args` passed through to the CLI.
  `econoclast backend` shows which agent it will drive. Attacks request a `role`
  (`extractor` / `attacker` / `referee`) only so the backend can pick a temperature; there is a single
  model behind every role. New code lives in `llm/backend.py` (the `Backend` class + `detect_backend`),
  replacing the deleted `llm/router.py`.
- **Grounding.** Every LLM finding must include a verbatim quote; ungrounded findings are capped at
  low confidence. This is the main defence against hallucinated problems.
- **Integrity override.** The fragility score forces a high band on a high-confidence
  reporting-inconsistency finding, so an internally contradictory reported number cannot hide behind
  an otherwise calm verdict.
- **Graceful degradation.** A literature source down -> it returns `[]` and the run continues. There is
  no offline mode: if neither `claude` nor `codex` is on PATH, the run stops with a clear message.
- **Downloads escalate.** Paper and dataset fetches try plain httpx first; if a site blocks it
  (403 / Cloudflare / JS gate), `ingest/browser.py` opens a real browser to get past the wall, and if
  the link is dead it searches the web and lets the model pick the source. The browser is the optional
  `browser` extra; without it the direct path stands.
- **No CLI in tests.** Tests inject a fake backend (`tests/_fake.py`), so the suite never spawns
  `claude` or `codex` and stays deterministic.
