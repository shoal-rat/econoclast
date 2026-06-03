"""Token-price accounting.

Prices are USD per 1M tokens (input, output). They drift constantly, so treat
these as estimates and override via the ``pricing`` block of your config if you
care about exact figures. Unknown models cost 0 and are flagged in the log.
"""

from __future__ import annotations

from econoclast.llm.base import Usage

# (input_per_1M, output_per_1M)
PRICE_TABLE: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-8": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    # OpenAI
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "o3": (10.0, 40.0),
    "o4-mini": (1.1, 4.4),
    # Google
    "gemini-1.5-pro": (1.25, 5.0),
    "gemini-1.5-flash": (0.075, 0.3),
    "gemini-2.0-flash": (0.1, 0.4),
    # Local / unknown
    "mock": (0.0, 0.0),
}


def estimate_cost(model: str, usage: Usage, overrides: dict[str, tuple[float, float]] | None = None) -> float:
    table = {**PRICE_TABLE, **(overrides or {})}
    key = _match(model, table)
    if key is None:
        return 0.0
    in_price, out_price = table[key]
    return (usage.prompt_tokens * in_price + usage.completion_tokens * out_price) / 1_000_000.0


def _match(model: str, table: dict[str, tuple[float, float]]) -> str | None:
    if model in table:
        return model
    # Provider-prefixed (e.g. "anthropic/claude-sonnet-4") or suffixed variants.
    base = model.split("/")[-1]
    if base in table:
        return base
    for key in table:
        if base.startswith(key) or key.startswith(base):
            return key
    return None
