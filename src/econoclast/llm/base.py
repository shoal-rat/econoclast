"""Provider-agnostic LLM primitives.

We deliberately keep the surface small: a `Message`, an `LLMResponse`, and a
`LLMProvider.complete()` method. Tool use is implemented one layer up as a
ReAct-style JSON protocol (see ``econoclast.agent``) so that *every* backend —
including local Ollama models that lack native function calling — behaves the
same way.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class Message:
    role: Role
    content: str
    name: str | None = None

    def to_openai(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.prompt_tokens + other.prompt_tokens,
            self.completion_tokens + other.completion_tokens,
        )


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

    def json(self, *, strict: bool = False) -> Any:
        """Best-effort parse of a JSON object/array from the response text."""
        return extract_json(self.text, strict=strict)


class LLMError(RuntimeError):
    """Raised when a provider call fails irrecoverably."""


class LLMProvider:
    """Abstract base. Subclasses implement :meth:`complete`."""

    name: str = "base"

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: str | None = None,  # "json" | None
        stop: list[str] | None = None,
        timeout: float = 120.0,
    ) -> LLMResponse:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Robust JSON extraction (models love to wrap JSON in prose / code fences).
# --------------------------------------------------------------------------- #
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str, *, strict: bool = False) -> Any:
    """Pull the first valid JSON object or array out of ``text``.

    Tries, in order: the whole string, fenced code blocks, then a brace/bracket
    scan. Returns ``None`` when nothing parses unless ``strict`` is set, in
    which case it raises ``ValueError``.
    """
    text = (text or "").strip()
    if not text:
        if strict:
            raise ValueError("empty response")
        return None

    for candidate in _json_candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    if strict:
        raise ValueError("no parseable JSON found in response")
    return None


def _json_candidates(text: str):
    yield text
    for m in _FENCE.finditer(text):
        yield m.group(1).strip()
    # Greedy scan for the outermost {...} or [...].
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if 0 <= start < end:
            yield text[start : end + 1]
