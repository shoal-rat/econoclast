# Contributing to Econoclast

Thanks for helping make empirical work harder to fake. New attacks, better extraction, and more
forensics are all very welcome.

## Setup

```bash
git clone https://github.com/OWNER/econoclast && cd econoclast
pip install -e ".[dev,pdf]"
pytest                 # all tests run offline (mock model)
ruff check src tests
```

## Adding a new attack

Every attack — deterministic, LLM, or replication — subclasses `Attack` and returns `Finding`s.

### A deterministic forensic

1. Write the maths in `src/econoclast/forensics/yourtest.py` returning a `ForensicResult`.
2. Add a known-answer test in `tests/test_forensics.py` (this is required — forensics must be
   verifiable).
3. Register it in `src/econoclast/attacks/forensic.py::build_forensic_attacks()` with a confidence.

### An LLM critique

Subclass `LLMAttack` in `src/econoclast/attacks/llm.py`:

```python
class MyAttack(LLMAttack):
    name = "my-attack"
    category = "specification_search"   # one of attacks.base.CATEGORIES
    description = "One line for `econoclast attacks`."
    system_prompt = "You are a referee who…"

    def gate(self, ctx):                # optional design gating
        return "rdd" in ctx.designs

    def build_user_prompt(self, ctx):
        return "Your grounded instruction…\n\n" + _paper_brief(ctx)
```

Then add it to `build_llm_attacks()`. The JSON contract and quote-grounding are handled by the base
class — keep prompts adversarial **but** require a verbatim quote and allow an empty result.

## Principles

- **Ground everything.** A finding the user can't verify against the paper is noise.
- **Caveat honestly.** If a test is weak on small samples, say so and cap its confidence. This tool
  loses all value if it cries wolf.
- **Deterministic = tested.** Any statistical test needs a known-answer unit test.
- **No new heavy deps** in the core. Put extras behind an optional-dependency group.

## Style

`ruff` (config in `pyproject.toml`), type hints encouraged, comments explain *why*. Run
`ruff check src tests` and `pytest` before opening a PR.
