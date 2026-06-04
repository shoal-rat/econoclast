"""Econoclast — an adversarial AI referee for empirical-economics papers.

Econoclast reads a target paper (PDF or LaTeX) plus local and online literature,
then *attacks* it: grounded LLM critiques (specification search, cherry-picking,
identification flaws, missing robustness, HARKing, over-claiming), a
research-then-verify pass for methods it does not cover, and a specification-curve
replication when the data is public. It synthesises an adversarial referee report
with a "fragility score".

It is a native-LLM tool: it runs on the intelligence of Claude Code or Codex (no
API key, no offline mode).
"""

from econoclast.version import __version__

__all__ = ["__version__"]
