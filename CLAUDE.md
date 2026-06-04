# Econoclast

Econoclast is an adversarial AI referee for empirical economics. It reads a paper, re-derives the
numbers, hunts for the choices that produced the result, researches any method it does not cover,
re-runs the data when the data is public, and reports how fragile the headline is.

When you are working in this repo, or when someone asks you to check a paper, follow these rules.

## When a user asks you to check or verify a paper

The user may not be technical. Finish the whole job from one request and ask as little as possible.

1. Work out what they gave you (a link, a file, a title, maybe a dataset). Use the `econoclast_intake`
   MCP tool to get the short list of plain-language questions for anything missing. Ask only what you
   must, in plain words. The dataset and the specific claim are optional; do not block on them.
2. Run `econoclast verify "<paper>"` (or the `econoclast_verify` MCP tool). One call does the
   forensics, the critique, the research-then-verify pass for uncovered methods, and the data
   re-run. Add `--deep` for a harder pass on a difficult method.
3. Explain the result in plain language. Lead with the fragility score in one sentence. For each
   serious finding, say what it means and why it matters, and quote the paper. Offer the full report.

## Core rules

- Ground every model finding in a verbatim quote from the paper.
- Do not guess about a method you are unsure of. The built-in checks are a fast path; for anything
  else, Econoclast retrieves the method's literature for you. Rely on that and say when something
  could not be verified.
- Review identity-blind. Judge the work, not the authors.
- A flagged result is a hypothesis to check, not an accusation. An impossible reported number is
  often an honest typo.

## Project layout

- `src/econoclast/` is the package: `ingest` (PDF/LaTeX/URL, claim extraction), `forensics`
  (statcheck, GRIM, p-curve, caliper, ...), `attacks` (the unified Attack/Finding model, the LLM
  critiques, the methodology audit), `replication` (specification curve, McCrary, Callaway-Sant'Anna),
  `agent` (orchestration, comprehension, intake, branch-and-merge, referee), `report`, and `llm`.
- `integrations/` holds the Claude Code and Codex skill, command, prompt, and MCP wiring.
- `docs/` covers the methods, the philosophy of researching what we don't hardcode, and how to read a
  report. `tests/` runs offline with `pytest`.

## Development

```bash
pip install -e ".[dev,pdf,replication]"
pytest && ruff check src tests
```

Any new statistical check needs a known-answer test validated against synthetic data with a known
truth. Any new model finding must stay grounded in a quote.
