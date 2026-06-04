# Changelog

All notable changes to Econoclast are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [Unreleased]

### Added (self-equipping + schema-validated reads)
- `econoclast setup` now installs a browser for the agent: it adds the Playwright MCP to Claude Code
  (`claude mcp add playwright --scope user`) and to `~/.codex/config.toml`, idempotently. The MCP
  auto-installs its own browser binary on first use. Turn it off with `--no-browser-mcp`. The blocked
  download work order also tells the agent to install a browser itself if it still has none.
- Schema-validated structured output: when the backend is Claude Code, the paper-comprehension and
  intake reads pass `--json-schema`, so the model returns a guaranteed-shape object in
  `structured_output` instead of JSON parsed out of prose. Codex keeps the prompt contract. A new
  `json_schema` argument threads through `Backend.complete` and the providers.

### Added (agent-delegated downloads for blocked sites)
- Econoclast acts as the boss and the agent does the work. When the plain HTTP download is blocked by
  an anti-crawler defence (a 403, Cloudflare, a JavaScript gate, a cookie wall), Econoclast hands the
  agent a work order instead of carrying its own browser: `Backend.fetch_into` runs `claude -p` (with a
  `Bash,Read,Edit,Write,WebFetch,WebSearch` allowlist) or `codex exec` (workspace-write with network),
  so the agent gets past the wall with its own tools, a browser MCP, curl with cookies, or a web search,
  and saves the file into the cache. Applies to paper fetching (`ingest/fetch.py`) and dataset
  acquisition (`replication/acquire.py`), with a search-only last resort by paper title. New provider
  method `run_task`; gated by `agent_download` (default on). Replaces the bundled Playwright fallback
  (the `browser` extra and `ingest/browser.py` are removed).

### Changed (native-LLM only: Claude Code or Codex)
- Econoclast is now a pure native-LLM tool. Removed the deterministic forensics entirely (statcheck,
  GRIM/GRIMMER, p-curve, caliper, TIVA, Benford, terminal-digit) and the whole offline path. The
  verdict now comes from the grounded model critique, the research-then-verify pass, and the
  specification-curve replication.
- Removed the multi-model router and every API/local provider (OpenAI, Anthropic, Google, OpenRouter,
  Ollama, LiteLLM) and the offline mock. The only backends are the Claude Code and Codex CLIs, driven
  by subprocess with their own subscription auth. A new `llm/backend.py` replaces `llm/router.py`; if
  neither CLI is on PATH, Econoclast stops with a clear message instead of degrading.
- `config.py` lost model routing, API keys, and the `offline` flag; it now carries only the backend
  choice (auto | claude | codex). Removed the `econoclast forensics` and `econoclast models` commands
  (added `econoclast backend`), the `--offline` / `--no-llm` flags, and the `econoclast_forensics` MCP
  tool. The report no longer has a forensic battery; the fragility integrity override now keys off a
  high-confidence reporting-inconsistency finding. Tests inject a fake backend; nothing spawns a CLI.

### Added (talk once, let the AI decide)
- Interaction redesign for non-technical users: intake now returns a one-line `plan` and a single
  `blocking_question` so the agent states what it will do and proceeds, instead of opening a question
  round. The data and the claim default on their own; only the paper is ever required. The skill,
  command, and Codex prompt add feedforward before the run, graceful degradation when no data is found,
  and refine-without-restart. The whole flow and the friction it removes is documented with before/after
  sequence diagrams in `docs/interaction-design.md`, and the new interaction diagram is in the README.
- Conversational intake: `agent/intake.py` + the `econoclast_intake` MCP tool turn a free-text request
  into a structured understanding plus a short list of plain-language questions, so a non-technical
  user can be served in one message.
- AI comprehension: `agent/comprehend.py` reads the paper with the model and decides the design,
  methods, headline claim and direction, variables, and dataset links, then drives design-gating,
  dataset discovery, and the critique. Keyword detection is the fallback when no model is configured.
- The Claude Code skill/command and the Codex prompt are rewritten as a one-shot playbook: ask only
  what is missing, run `econoclast verify`, and explain the result in plain language.
- Project structure to match the maintainer's agent projects: a root `CLAUDE.md`, an `install.sh`
  one-command setup, and `schemas/` (intake, comprehension, finding, report). README roadmap removed;
  authorship set to shoal-rat.

### Added (research-then-verify, instead of hardcoding every method)
- The agent now researches methods it does not cover. `detect_methods` + `method_coverage` split a
  paper's estimators into built-in checks vs ones that need research; for the latter, Econoclast
  retrieves the method's assumptions and diagnostics from the literature and audits the paper against
  them (`methodology-audit` attack). Validated live on a synthetic-control paper.
- Every model prompt carries an epistemic rule: do not guess, lean on retrieved sources, mark
  unverified points and give them low confidence; the referee discounts unverified findings.
- `--deep`: branch-and-merge. Run several verification strategies for a hard question and let a judge
  keep the best-supported, dropping duplicates and weak points.
- `--allow-code`: the agent writes and runs a diagnostic for an uncovered method when a dataset is
  available (opt-in, untrusted, denylist-guarded).
- See docs/philosophy.md.

### Added (roadmap completion)
- **McCrary (2008) density test** for RDD manipulation (log-density jump + standard error + bandwidth
  scan), replacing the binomial screening test. Validated against synthetic clean/manipulated data.
- **Staggered-DiD estimators**: Callaway and Sant'Anna (2021) group-time ATT with a clustered
  bootstrap, Sun and Abraham (2021) interaction-weighted event study, and a Goodman-Bacon style
  TWFE-vs-CS contrast that flags negative-weight bias. Validated against synthetic data with a known
  dynamic effect.
- **Citation verification** (`citation-check`): the bibliography is matched against Crossref to flag
  unresolved or fabricated references.
- **Ensemble voting** (`--ensemble N`): run each LLM attack N times and keep only findings that recur.
- **GROBID ingestion** for hard PDF layouts (set `ECONOCLAST_GROBID_URL`); falls back to PyMuPDF/pypdf.
- **`econoclast reproduce`**: run an author's replication package (opt-in, untrusted).
- **`econoclast batch`**: review a whole folder and rank papers by fragility.
- Project files: CITATION.cff, SECURITY.md, CODE_OF_CONDUCT.md, a pull-request template, and `py.typed`.

### Added
- **Autonomous `econoclast verify <path or URL>`**: one line in, full verdict out. Fetches the paper,
  runs forensics + critique, finds the dataset named in the paper (Zenodo, Dataverse, OSF, GitHub, or a
  direct file), downloads and unzips it, asks the model to map the paper's variables onto the dataset
  columns, and runs the specification curve. `--data` to use a local dataset. Also exposed as the
  `econoclast_verify` MCP tool so an agent can run it from a single instruction.
- New README with SVG banner and pipeline diagram; all emojis removed across the README, docs, and the
  CLI / report / UI output; prose de-AI-ed.

### Added (earlier in this cycle)
- **Replication mode** (`econoclast replicate`, `pip install econoclast[replication]`): specification-
  curve / multiverse analysis that re-estimates the headline coefficient across every defensible
  combination of controls × fixed effects × clustering × sample and reports the share that survive;
  RDD manipulation + bandwidth-sensitivity and DiD pre-trend screening checks; spec-curve plot; folds
  into `review` via `--replicate`. Re-estimated in-process (statsmodels) - never runs author code.
- **No-API-key backends**: drive Claude Code (`--backend claude`) or Codex (`--backend codex`) via
  subprocess; auto-detected when no API key is set.
- **MCP server** (`econoclast mcp`) exposing `econoclast_forensics` / `econoclast_review` /
  `econoclast_replicate` / `econoclast_list_attacks`; Claude Code plugin (slash command + skill +
  marketplace) and Codex prompts, incl. an agent-driven `/econoclast-setup`.
- **`econoclast setup`** wizard: detect backends, write config, and register the MCP tool.
- **URL ingestion**: `review` / `forensics` / MCP accept a local path **or** a URL (PDF, arXiv
  abstract page, or a journal/landing webpage - downloaded automatically).
- **Credibility controls**: mechanical quote-grounding gate, identity-blind review (default on),
  prompt-injection detection/stripping. See `docs/credibility.md`.

## [0.1.0] - 2026-06-04

First public release.

### Added
- **Ingest:** PDF (PyMuPDF with pypdf fallback), LaTeX (with one-level `\input` resolution), and
  plain-text loaders; section segmentation; conservative regex harvest of statistical claims
  (coefficients, standard errors, t/F/r/z/χ² statistics, p-values, means/SDs, stars, N).
- **Deterministic forensics:** statcheck, GRIM, GRIMMER, p-curve, caliper/z-bunching, TIVA + R-index,
  Benford, terminal-digit - all offline, all unit-tested.
- **Multi-model LLM layer:** provider-agnostic router with fallbacks and cost accounting; OpenAI-
  compatible, Anthropic, Google Gemini, Ollama/local, and LiteLLM passthrough providers; an offline
  mock provider.
- **LLM attacks:** specification-search, cherry-picking, identification-critique (design-gated),
  robustness-coverage, HARKing, over-claiming, literature-contradiction - all quote-grounded.
- **Literature:** keyless OpenAlex / Semantic Scholar / arXiv / Crossref search + local corpus + keyword ranking.
- **Agent & report:** bounded orchestration, referee meta-review synthesis, saturating fragility score
  with an integrity override, and Markdown / JSON / HTML rendering.
- **Interfaces:** Typer CLI (`review`, `forensics`, `claims`, `attacks`, `models`, `ui`, `version`)
  and an optional Streamlit web UI.
- Docs, a synthetic demo paper with planted issues, and a test suite that runs fully offline.

[0.1.0]: https://github.com/shoal-rat/econoclast/releases/tag/v0.1.0
