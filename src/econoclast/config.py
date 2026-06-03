"""Configuration: model routing, API-key resolution and run settings.

Precedence (lowest to highest):
    built-in defaults  ->  YAML config file  ->  environment variables

Everything statistical works with no configuration at all. Model routing only
matters once you enable the LLM-powered attacks.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from econoclast.logging import get_logger

log = get_logger("config")

# Providers that shell out to a local AI CLI (no API key; subscription auth).
CLI_BINARIES = {
    "claude_cli": "claude",
    "claude_code": "claude",
    "codex_cli": "codex",
    "codex": "codex",
}

# Roles let us send cheap work to a cheap model and hard reasoning to a strong
# one. An attack asks the router for a role; the router resolves it to a model.
ROLES = ("extractor", "attacker", "referee")

# Environment variable that names the api key for each provider.
PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": "OLLAMA_API_KEY",  # usually unset / not required
    "mock": "",
}

# Default base URLs for OpenAI-compatible providers.
PROVIDER_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}


@dataclass
class ModelRef:
    """A concrete model plus how to reach it."""

    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    temperature: float = 0.2
    max_tokens: int = 4096
    binary: str | None = None  # for CLI providers (claude_cli / codex_cli)
    extra_args: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, spec: str | dict[str, Any]) -> ModelRef:
        """Accept either ``"provider:model"`` strings or full dicts."""
        if isinstance(spec, str):
            provider, _, model = spec.partition(":")
            if not model:
                provider, model = "openai", provider
            return cls(provider=provider.strip(), model=model.strip())
        d = dict(spec)
        return cls(
            provider=d["provider"],
            model=d.get("model", ""),
            base_url=d.get("base_url"),
            api_key_env=d.get("api_key_env"),
            temperature=float(d.get("temperature", 0.2)),
            max_tokens=int(d.get("max_tokens", 4096)),
            binary=d.get("binary"),
            extra_args=list(d.get("args", []) or d.get("extra_args", [])),
        )

    def resolved_base_url(self) -> str | None:
        if self.base_url:
            return self.base_url
        return PROVIDER_BASE_URL.get(self.provider)

    def resolved_api_key(self) -> str | None:
        env = self.api_key_env or PROVIDER_KEY_ENV.get(self.provider, "")
        if not env:
            return None
        return os.getenv(env)

    def is_usable(self) -> bool:
        """A model is usable if it needs no key, or its key/CLI is present."""
        if self.provider in ("mock", "ollama"):
            return True
        if self.provider in CLI_BINARIES:
            return shutil.which(self.binary or CLI_BINARIES[self.provider]) is not None
        return bool(self.resolved_api_key())


@dataclass
class LiteratureConfig:
    enabled: bool = True
    max_results: int = 12
    sources: list[str] = field(default_factory=lambda: ["openalex", "arxiv", "semantic_scholar"])
    local_dirs: list[str] = field(default_factory=list)


@dataclass
class Settings:
    routes: dict[str, list[ModelRef]] = field(default_factory=dict)
    literature: LiteratureConfig = field(default_factory=LiteratureConfig)
    contact_email: str | None = None
    cache_dir: str = ".econoclast_cache"
    offline: bool = False
    max_claims: int = 400
    request_timeout: float = 120.0
    raw: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Settings:
        load_dotenv(override=False)
        data: dict[str, Any] = {}
        cfg_path = _find_config(path)
        if cfg_path is not None:
            log.debug("Loading config from %s", cfg_path)
            with open(cfg_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}

        routes = _parse_routes(data.get("models") or data.get("routes") or {})
        if not routes:
            routes = default_routes()

        lit_raw = data.get("literature", {}) or {}
        literature = LiteratureConfig(
            enabled=lit_raw.get("enabled", True),
            max_results=int(lit_raw.get("max_results", 12)),
            sources=list(lit_raw.get("sources", ["openalex", "arxiv", "semantic_scholar"])),
            local_dirs=list(lit_raw.get("local_dirs", [])),
        )

        contact = (
            data.get("contact_email")
            or os.getenv("ECONOCLAST_CONTACT_EMAIL")
            or None
        )
        offline = bool(data.get("offline", False)) or _env_flag("ECONOCLAST_OFFLINE")

        return cls(
            routes=routes,
            literature=literature,
            contact_email=contact,
            cache_dir=data.get("cache_dir", ".econoclast_cache"),
            offline=offline,
            max_claims=int(data.get("max_claims", 400)),
            request_timeout=float(data.get("request_timeout", 120.0)),
            raw=data,
        )

    # --------------------------------------------------------------- helpers
    def models_for(self, role: str) -> list[ModelRef]:
        if role in self.routes and self.routes[role]:
            return self.routes[role]
        # Fall back across roles so a partial config still works.
        for alt in ("attacker", "referee", "extractor"):
            if self.routes.get(alt):
                return self.routes[alt]
        return [ModelRef(provider="mock", model="mock")]

    def has_live_models(self) -> bool:
        for refs in self.routes.values():
            for ref in refs:
                if ref.provider != "mock" and ref.is_usable():
                    return True
        return False

    def cache_path(self) -> Path:
        p = Path(self.cache_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


def _parse_routes(raw: dict[str, Any]) -> dict[str, list[ModelRef]]:
    routes: dict[str, list[ModelRef]] = {}
    for role, spec in raw.items():
        if isinstance(spec, list):
            routes[role] = [ModelRef.parse(s) for s in spec]
        else:
            routes[role] = [ModelRef.parse(spec)]
    return routes


def default_routes() -> dict[str, list[ModelRef]]:
    """Pick sensible defaults from whichever API keys are present.

    The first provider with a usable key wins. Falls back to the offline mock
    provider so the pipeline always runs.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        strong = ModelRef("anthropic", "claude-opus-4-8", max_tokens=8192)
        mid = ModelRef("anthropic", "claude-sonnet-4-6", max_tokens=8192)
        fast = ModelRef("anthropic", "claude-haiku-4-5-20251001", max_tokens=4096)
    elif os.getenv("OPENAI_API_KEY"):
        strong = ModelRef("openai", "gpt-4o", max_tokens=8192)
        mid = ModelRef("openai", "gpt-4o", max_tokens=8192)
        fast = ModelRef("openai", "gpt-4o-mini", max_tokens=4096)
    elif os.getenv("OPENROUTER_API_KEY"):
        strong = ModelRef("openrouter", "anthropic/claude-sonnet-4", max_tokens=8192)
        mid = strong
        fast = ModelRef("openrouter", "openai/gpt-4o-mini", max_tokens=4096)
    elif os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
        strong = ModelRef("google", "gemini-1.5-pro", max_tokens=8192)
        mid = strong
        fast = ModelRef("google", "gemini-1.5-flash", max_tokens=4096)
    elif shutil.which("claude"):
        # No API key, but Claude Code is installed -> use it (subscription auth).
        log.info("No API key found; routing through the Claude Code CLI.")
        return cli_routes("claude_cli")
    elif shutil.which("codex"):
        log.info("No API key found; routing through the Codex CLI.")
        return cli_routes("codex_cli")
    else:
        mock = ModelRef("mock", "mock")
        return {"extractor": [mock], "attacker": [mock], "referee": [mock]}

    return {
        "extractor": [fast, mid],
        "attacker": [strong, mid],
        "referee": [strong, mid],
    }


def cli_routes(provider: str) -> dict[str, list[ModelRef]]:
    """Routing that sends every role through a local AI CLI (no API key)."""
    if provider in ("claude_cli", "claude_code"):
        return {
            "extractor": [ModelRef("claude_cli", "sonnet")],
            "attacker": [ModelRef("claude_cli", "opus"), ModelRef("claude_cli", "sonnet")],
            "referee": [ModelRef("claude_cli", "opus"), ModelRef("claude_cli", "sonnet")],
        }
    # Codex: leave the model empty so the user's configured default is used.
    ref = ModelRef("codex_cli", "")
    return {"extractor": [ref], "attacker": [ref], "referee": [ref]}


def _find_config(path: str | os.PathLike[str] | None) -> Path | None:
    if path:
        p = Path(path)
        return p if p.exists() else None
    for name in ("econoclast.local.yaml", "econoclast.yaml", "econoclast.yml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return None


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")
