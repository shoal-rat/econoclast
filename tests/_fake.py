"""Shared test fixtures.

Econoclast has no offline mode in production: it runs on Claude Code or Codex.
For tests we inject a tiny in-process ``FakeBackend`` that mimics the backend's
``complete(role, ...)`` contract with canned responses, so the pipeline runs
without spawning a real CLI.
"""

from __future__ import annotations

from econoclast.llm.base import LLMResponse


class FakeBackend:
    """A stand-in for econoclast.llm.backend.Backend used in tests."""

    label = "fake"

    def __init__(self, *, responses: dict | None = None, default: str = "[]") -> None:
        self.responses = responses or {}
        self.default = default
        self.calls: list[str] = []

    def complete(self, role, messages, *, response_format=None,  # noqa: ANN001
                 temperature=None, max_tokens=4096, stop=None) -> LLMResponse:
        self.calls.append(role)
        r = self.responses.get(role, self._default_for(role))
        text = r(messages) if callable(r) else r
        return LLMResponse(text=text, model="fake", provider="fake")

    def _default_for(self, role: str) -> str:
        if role == "referee":
            return '{"headline":"Fake verdict","assessment":"a","what_would_change_my_mind":"b"}'
        if role == "extractor":
            return "{}"
        return self.default

    def summary(self) -> dict:
        return {"backend": self.label, "model": "fake", "calls": len(self.calls)}
