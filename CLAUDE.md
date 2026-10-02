# Econoclast

Econoclast is a desktop app in which an autonomous agent (Claude Code or Codex) tests an empirical paper's
headline claim while the user watches the hunt on a living Ravenna mosaic. The agent fetches the paper and its
data, learns the real-world setting, builds a local quant workshop, reproduces and attacks the result, screens
for fabrication and spin, re-runs it across every defensible specification, and writes a verdict.

## Layout

- `src/econoclast/world.py`: the lexicon (stations, blades, verdict bands, seals). Change names here only.
- `case/`: case folder, append-only event log, wounds, the score and seal, the Tabula.
- `arsenal/`: the MCP server the agent uses (`server.py` wraps the plain functions in `tools.py`) and the
  doctrine (`doctrine.py`: standing orders plus per-station orders handed out by `proclaim`).
- `sicarius/`: builds the agent command and parses Claude / Codex JSON streams into events.
- `tesserae/` reading and paper forensics; `bibliotheca/` literature, data, code audit; `viae/` estimators and
  data forensics; `fabrica/` the shared quant venv; `app/` the window, the bridge `Api`, and `web/` (stage,
  director, UI; buildless ES modules).
- `tools/art/` regenerates the mosaic art with Codex (`gen_art.py`) and packs it (`build_art.py`);
  `tools/dev/rehearsal.py` plays a scripted hunt without an agent for stage work.

## Rules for changes

- Wounds stay grounded: text wounds quote the paper (checked by `verify_quote`), computation wounds cite
  artifacts that exist. Integrity wounds describe observations, never accusations.
- New statistical screens and estimators need known-answer tests on synthetic data with a known truth, and a
  false-positive check on realistic honest data.
- The doctrine is written as positive, opinionated rules for the agent, not lists of prohibitions.
- Every event the arsenal emits should mean something on the wall; when you add one, give it choreography in
  `web/js/director.js` and a line in `web/js/ui.js`'s chronicle.
- Tests never spawn a real agent (`tests/test_hunt.py` uses a fake `claude`).

## Development

```bash
uv venv && uv pip install -e ".[dev,pdf]"
pytest && ruff check src tests tools
econoclast app --browser          # UI in a browser (developer preview)
```
