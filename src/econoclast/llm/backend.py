"""The model backend: one live LLM, reached through Claude Code or Codex.

Econoclast is a native-LLM tool. It does not ship a model, an API client, or any
offline fallback; it borrows the intelligence of the agent you already run. At
startup it finds the ``claude`` or ``codex`` CLI on PATH and sends every prompt
through it, using that CLI's own subscription auth (no API key).

Attacks ask for a *role* ("extractor", "attacker", "referee") only so the backend
can pick a temperature. There is a single model behind every role.
"""

from __future__ import annotations

import shutil
import threading

from econoclast.config import Settings
from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage
from econoclast.llm.providers import ClaudeCodeProvider, CodexProvider
from econoclast.logging import get_logger

log = get_logger("backend")

_ROLE_TEMPERATURE = {"extractor": 0.1, "attacker": 0.3, "referee": 0.2}


class Backend:
    """A single live LLM, driven through a local AI CLI."""

    def __init__(self, provider: LLMProvider, label: str, *, model: str = "", timeout: float = 240.0) -> None:
        self.provider = provider
        self.label = label  # "claude" or "codex"
        self.model = model
        self.timeout = timeout
        self._lock = threading.Lock()
        self.total_usage = Usage()
        self.total_cost_usd = 0.0
        self.call_count = 0

    def complete(
        self,
        role: str,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
    ) -> LLMResponse:
        temp = _ROLE_TEMPERATURE.get(role, 0.2) if temperature is None else temperature
        resp = self.provider.complete(
            messages,
            model=self.model,
            temperature=temp,
            max_tokens=max_tokens,
            response_format=response_format,
            stop=stop,
            timeout=self.timeout,
        )
        with self._lock:
            self.total_usage = self.total_usage + resp.usage
            self.total_cost_usd += resp.cost_usd or 0.0
            self.call_count += 1
        return resp

    def summary(self) -> dict:
        return {
            "backend": self.label,
            "model": self.model or "default",
            "calls": self.call_count,
            "prompt_tokens": self.total_usage.prompt_tokens,
            "completion_tokens": self.total_usage.completion_tokens,
            "total_tokens": self.total_usage.total_tokens,
            "est_cost_usd": round(self.total_cost_usd, 4),
        }


def detect_backend(settings: Settings) -> Backend:
    """Find Claude Code or Codex on PATH and wrap it as the backend.

    Honours ``settings.backend`` ("auto" | "claude" | "codex"). Raises if neither
    CLI is available: Econoclast has no offline mode by design.
    """
    pref = (settings.backend or "auto").lower()
    order = {"claude": ["claude"], "codex": ["codex"]}.get(pref, ["claude", "codex"])
    for which in order:
        if which == "claude" and shutil.which(settings.claude_binary):
            return Backend(
                ClaudeCodeProvider(binary=settings.claude_binary, extra_args=settings.backend_args),
                "claude", model=settings.model, timeout=settings.request_timeout,
            )
        if which == "codex" and shutil.which(settings.codex_binary):
            return Backend(
                CodexProvider(binary=settings.codex_binary, extra_args=settings.backend_args),
                "codex", model=settings.model, timeout=settings.request_timeout,
            )
    raise LLMError(
        "Econoclast runs on the intelligence of Claude Code or Codex, but neither `claude` nor "
        "`codex` was found on PATH. Install one and log in, then run Econoclast again."
    )
