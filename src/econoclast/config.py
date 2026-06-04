"""Configuration: which backend to drive and a few run settings.

Precedence (lowest to highest):
    built-in defaults  ->  YAML config file  ->  environment variables

Econoclast is a native-LLM tool. It runs on Claude Code or Codex; there are no
API keys, no model routing, and no offline mode to configure. The only model
choice is which of the two CLIs to use ("auto" tries Claude Code first).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from econoclast.logging import get_logger

log = get_logger("config")


@dataclass
class LiteratureConfig:
    enabled: bool = True
    max_results: int = 12
    sources: list[str] = field(default_factory=lambda: ["openalex", "arxiv", "semantic_scholar"])
    local_dirs: list[str] = field(default_factory=list)


@dataclass
class Settings:
    backend: str = "auto"  # auto | claude | codex
    model: str = ""  # optional model override passed to the CLI ("" = the CLI's default)
    claude_binary: str = "claude"
    codex_binary: str = "codex"
    backend_args: list[str] = field(default_factory=list)
    literature: LiteratureConfig = field(default_factory=LiteratureConfig)
    contact_email: str | None = None
    cache_dir: str = ".econoclast_cache"
    blind_default: bool = True
    # When a download is blocked, let the agent fetch it with its own tools (browser, curl, search).
    agent_download: bool = True
    max_claims: int = 400
    request_timeout: float = 240.0
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

        lit_raw = data.get("literature", {}) or {}
        literature = LiteratureConfig(
            enabled=lit_raw.get("enabled", True),
            max_results=int(lit_raw.get("max_results", 12)),
            sources=list(lit_raw.get("sources", ["openalex", "arxiv", "semantic_scholar"])),
            local_dirs=list(lit_raw.get("local_dirs", [])),
        )

        backend = (os.getenv("ECONOCLAST_BACKEND") or data.get("backend") or "auto").strip().lower()
        contact = data.get("contact_email") or os.getenv("ECONOCLAST_CONTACT_EMAIL") or None

        return cls(
            backend=backend if backend in ("auto", "claude", "codex") else "auto",
            model=str(os.getenv("ECONOCLAST_MODEL") or data.get("model", "")).strip(),
            claude_binary=str(data.get("claude_binary", "claude")),
            codex_binary=str(data.get("codex_binary", "codex")),
            backend_args=list(data.get("backend_args", []) or []),
            literature=literature,
            contact_email=contact,
            cache_dir=data.get("cache_dir", ".econoclast_cache"),
            blind_default=bool(data.get("blind_default", True)),
            agent_download=bool(data.get("agent_download", True)),
            max_claims=int(data.get("max_claims", 400)),
            request_timeout=float(data.get("request_timeout", 240.0)),
            raw=data,
        )

    # --------------------------------------------------------------- helpers
    def cache_path(self) -> Path:
        p = Path(self.cache_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


def _find_config(path: str | os.PathLike[str] | None) -> Path | None:
    if path:
        p = Path(path)
        return p if p.exists() else None
    for name in ("econoclast.local.yaml", "econoclast.yaml", "econoclast.yml"):
        p = Path.cwd() / name
        if p.exists():
            return p
    return None
