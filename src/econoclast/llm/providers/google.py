"""Google Gemini (Generative Language API) provider."""

from __future__ import annotations

import httpx

from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage


class GoogleProvider(LLMProvider):
    name = "google"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
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
            raise LLMError("google: GOOGLE_API_KEY is not set")

        system_parts = [m.content for m in messages if m.role == "system"]
        contents = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.content}]})

        gen_cfg: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if response_format == "json":
            gen_cfg["responseMimeType"] = "application/json"
        if stop:
            gen_cfg["stopSequences"] = stop

        body: dict = {"contents": contents, "generationConfig": gen_cfg}
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        try:
            resp = httpx.post(url, json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"google request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"google {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            text = ""
        meta = data.get("usageMetadata") or {}
        usage = Usage(
            prompt_tokens=int(meta.get("promptTokenCount", 0)),
            completion_tokens=int(meta.get("candidatesTokenCount", 0)),
        )
        return LLMResponse(text=text, model=model, provider=self.name, usage=usage, raw=data)
