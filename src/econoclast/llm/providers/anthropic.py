"""Anthropic Messages API provider."""

from __future__ import annotations

import httpx

from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, *, api_key: str | None = None, base_url: str = "https://api.anthropic.com") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

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
        if not self.api_key:
            raise LLMError("anthropic: ANTHROPIC_API_KEY is not set")

        system_parts = [m.content for m in messages if m.role == "system"]
        convo = [m for m in messages if m.role != "system"]
        payload_msgs = [
            {"role": ("assistant" if m.role == "assistant" else "user"), "content": m.content}
            for m in convo
        ]
        # Anthropic requires the first message to be from the user.
        if not payload_msgs or payload_msgs[0]["role"] != "user":
            payload_msgs.insert(0, {"role": "user", "content": "(continue)"})

        body: dict = {
            "model": model,
            "messages": payload_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if stop:
            body["stop_sequences"] = stop

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        try:
            resp = httpx.post(f"{self.base_url}/v1/messages", json=body, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"anthropic request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"anthropic {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        text = "".join(
            block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"
        )
        usage_raw = data.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("input_tokens", 0)),
            completion_tokens=int(usage_raw.get("output_tokens", 0)),
        )
        return LLMResponse(text=text, model=model, provider=self.name, usage=usage, raw=data)
