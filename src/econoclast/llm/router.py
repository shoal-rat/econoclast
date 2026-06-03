"""The model router: resolve a *role* to a concrete model, with fallbacks.

Attacks never name a model directly. They ask for a role ("attacker",
"extractor", "referee") and the router picks the configured model, retries on
transient failure, falls back to the next model in the list, and accumulates
token cost across the whole run.
"""

from __future__ import annotations

import threading

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from econoclast.config import ModelRef, Settings
from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage
from econoclast.llm.cost import estimate_cost
from econoclast.llm.providers import (
    AnthropicProvider,
    ClaudeCodeProvider,
    CodexProvider,
    GoogleProvider,
    MockProvider,
    OpenAICompatibleProvider,
)
from econoclast.logging import get_logger

log = get_logger("router")


class ModelRouter:
    def __init__(self, settings: Settings, *, force_mock: bool = False) -> None:
        self.settings = settings
        self.force_mock = force_mock or settings.offline
        self._providers: dict[str, LLMProvider] = {}
        self._lock = threading.Lock()
        self.total_usage = Usage()
        self.total_cost_usd = 0.0
        self.call_count = 0
        self._pricing_overrides = _parse_pricing(settings.raw.get("pricing", {}))

    # ------------------------------------------------------------------ api
    def is_live(self) -> bool:
        """True if at least one configured model can actually be called."""
        if self.force_mock:
            return False
        return self.settings.has_live_models()

    def complete(
        self,
        role: str,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        refs = self._candidate_refs(role)
        errors: list[str] = []
        for ref in refs:
            try:
                resp = self._complete_one(
                    ref,
                    messages,
                    response_format=response_format,
                    temperature=ref.temperature if temperature is None else temperature,
                    max_tokens=ref.max_tokens if max_tokens is None else max_tokens,
                    stop=stop,
                )
                self._account(resp)
                return resp
            except Exception as exc:  # noqa: BLE001 — fall back to next model
                errors.append(f"{ref.provider}:{ref.model} -> {exc}")
                log.warning("model %s:%s failed, falling back: %s", ref.provider, ref.model, exc)
        raise LLMError(f"all models failed for role '{role}': " + " | ".join(errors))

    # -------------------------------------------------------------- internal
    def _candidate_refs(self, role: str) -> list[ModelRef]:
        if self.force_mock:
            return [ModelRef(provider="mock", model="mock")]
        refs = [r for r in self.settings.models_for(role) if r.is_usable()]
        if not refs:
            log.warning("no usable model for role '%s'; using mock provider", role)
            return [ModelRef(provider="mock", model="mock")]
        return refs

    def _complete_one(self, ref: ModelRef, messages, **kw) -> LLMResponse:
        provider = self._provider_for(ref)
        timeout = self.settings.request_timeout

        @retry(
            retry=retry_if_exception_type(LLMError),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            reraise=True,
        )
        def _call() -> LLMResponse:
            return provider.complete(messages, model=ref.model, timeout=timeout, **kw)

        return _call()

    def _provider_for(self, ref: ModelRef) -> LLMProvider:
        cache_key = f"{ref.provider}:{ref.resolved_base_url()}"
        with self._lock:
            if cache_key in self._providers:
                return self._providers[cache_key]
            provider = _build_provider(ref)
            self._providers[cache_key] = provider
            return provider

    def _account(self, resp: LLMResponse) -> None:
        # CLI backends (Claude Code) report the real dollar cost; keep it.
        if not resp.cost_usd:
            resp.cost_usd = estimate_cost(resp.model, resp.usage, self._pricing_overrides)
        with self._lock:
            self.total_usage = self.total_usage + resp.usage
            self.total_cost_usd += resp.cost_usd
            self.call_count += 1

    def summary(self) -> dict:
        return {
            "calls": self.call_count,
            "prompt_tokens": self.total_usage.prompt_tokens,
            "completion_tokens": self.total_usage.completion_tokens,
            "total_tokens": self.total_usage.total_tokens,
            "est_cost_usd": round(self.total_cost_usd, 4),
        }


def _build_provider(ref: ModelRef) -> LLMProvider:
    if ref.provider == "mock":
        return MockProvider()
    if ref.provider == "anthropic":
        return AnthropicProvider(api_key=ref.resolved_api_key())
    if ref.provider == "google":
        return GoogleProvider(api_key=ref.resolved_api_key())
    if ref.provider == "litellm":
        from econoclast.llm.providers.litellm_provider import LiteLLMProvider

        return LiteLLMProvider(api_key=ref.resolved_api_key(), base_url=ref.resolved_base_url())
    if ref.provider in ("claude_cli", "claude_code"):
        return ClaudeCodeProvider(binary=ref.binary or "claude", extra_args=ref.extra_args)
    if ref.provider in ("codex_cli", "codex"):
        return CodexProvider(binary=ref.binary or "codex", extra_args=ref.extra_args)
    # Everything else is treated as OpenAI-compatible.
    return OpenAICompatibleProvider(
        name=ref.provider,
        base_url=ref.resolved_base_url() or "https://api.openai.com/v1",
        api_key=ref.resolved_api_key(),
    )


def _parse_pricing(raw: dict) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for model, val in (raw or {}).items():
        if isinstance(val, (list, tuple)) and len(val) == 2:
            out[model] = (float(val[0]), float(val[1]))
    return out
