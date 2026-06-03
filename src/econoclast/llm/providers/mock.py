"""Offline mock provider.

Lets the entire pipeline run with no API keys (great for tests, demos and
dry-runs). Returns deterministic, parseable output. Optionally accepts a list
of scripted responses that are popped in order.
"""

from __future__ import annotations

from econoclast.llm.base import LLMProvider, LLMResponse, Message, Usage


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, responses: list[str] | None = None) -> None:
        self._scripted = list(responses or [])

    def complete(
        self,
        messages: list[Message],
        *,
        model: str = "mock",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: str | None = None,
        stop: list[str] | None = None,
        timeout: float = 120.0,
    ) -> LLMResponse:
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        snippet = last_user.strip().replace("\n", " ")[:120]

        if self._scripted:
            text = self._scripted.pop(0)
        elif response_format == "json":
            text = (
                '{"findings": [], "summary": "Mock provider active — no live LLM '
                'configured; only deterministic statistical forensics ran.", '
                f'"echo": {snippet!r}}}'
            )
        else:
            text = (
                "[mock LLM] No live model is configured, so this is a placeholder "
                "response. Configure a provider in econoclast.yaml or set an API "
                f"key to enable LLM attacks. (prompt echo: {snippet})"
            )

        prompt_tokens = sum(len(m.content.split()) for m in messages)
        usage = Usage(prompt_tokens=prompt_tokens, completion_tokens=len(text.split()))
        return LLMResponse(text=text, model=model, provider=self.name, usage=usage)
