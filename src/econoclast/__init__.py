"""Econoclast — an adversarial AI referee for empirical-economics papers.

Econoclast reads a target paper (PDF or LaTeX) plus local and online
literature, then *attacks* it: it runs deterministic statistical forensics
(statcheck, GRIM/GRIMMER, p-curve, z-statistic bunching, Benford, ...) and
multi-model LLM critiques (specification search, cherry-picking, identification
flaws, missing robustness, HARKing) and synthesises an adversarial referee
report with a "fragility score".

The deterministic forensics need no API keys and run fully offline. The LLM
attacks are provider-agnostic (OpenAI, Anthropic, Google, OpenRouter, or a
local Ollama/vLLM model).
"""

from econoclast.version import __version__

__all__ = ["__version__"]
