"""Optional LiteLLM passthrough provider.

If you'd rather lean on LiteLLM's 100+ provider support, routing and cost map,
set ``provider: litellm`` in your config and use a LiteLLM model string such as
``anthropic/claude-sonnet-4-6``, ``gemini/gemini-1.5-pro`` or
``ollama_chat/llama3.1``. Install with ``pip install econoclast[litellm]``.
"""

from __future__ import annotations

from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage


class LiteLLMProvider(LLMProvider):
    name = "litellm"

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url

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
        try:
            import litellm  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "litellm is not installed. Run `pip install econoclast[litellm]`."
            ) from exc

        kwargs: dict = {
            "model": model,
            "messages": [m.to_openai() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "timeout": timeout,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["api_base"] = self.base_url
        if stop:
            kwargs["stop"] = stop
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            resp = litellm.completion(**kwargs)
        except Exception as exc:  # noqa: BLE001 — surface as our error type
            raise LLMError(f"litellm error: {exc}") from exc

        text = resp["choices"][0]["message"]["content"] or ""
        usage_raw = resp.get("usage") or {}
        usage = Usage(
            prompt_tokens=int(usage_raw.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage_raw.get("completion_tokens", 0) or 0),
        )
        return LLMResponse(text=text, model=model, provider=self.name, usage=usage, raw=dict(resp))
