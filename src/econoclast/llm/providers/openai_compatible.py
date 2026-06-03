"""OpenAI Chat Completions protocol.

One class serves OpenAI, OpenRouter, Together, Groq, vLLM, LM Studio and
Ollama (``/v1``) — anything that speaks the ``/chat/completions`` schema.
"""

from __future__ import annotations

import httpx

from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str = "openai",
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.extra_headers = extra_headers or {}

    def complete(
        self,
        messages: list[Message],
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: str | None = None,
        stop: list[str] | None = None,
        timeout: float = 120.0,
    ) -> LLMResponse:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.name == "openrouter":
            headers.setdefault("HTTP-Referer", "https://github.com/shoal-rat/econoclast")
            headers.setdefault("X-Title", "Econoclast")
        headers.update(self.extra_headers)

        body: dict = {
            "model": model,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if stop:
            body["stop"] = stop
        if response_format == "json":
            body["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:  # network-level
            raise LLMError(f"{self.name} request failed: {exc}") from exc

        if resp.status_code >= 400:
            # Retry once without response_format — some local backends reject it.
            if response_format == "json" and resp.status_code in (400, 422):
                body.pop("response_format", None)
                resp = httpx.post(url, json=body, headers=headers, timeout=timeout)
            if resp.status_code >= 400:
                raise LLMError(f"{self.name} {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{self.name} returned an unexpected body: {data}") from exc

        usage_raw = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0)),
            completion_tokens=int(usage_raw.get("completion_tokens", 0)),
        )
        return LLMResponse(text=text, model=model, provider=self.name, usage=usage, raw=data)
