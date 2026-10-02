"""Settings: which agent to unleash, how much rope to give it, which tools it carries.

Precedence (lowest to highest): built-in defaults -> ``~/.econoclast/config.yaml`` ->
``./econoclast.yaml`` -> environment variables.

Econoclast is a native-agent tool. The Sicarius *is* Claude Code or Codex, run as a
full autonomous agent with network access, a shell, a browser and Econoclast's own MCP
arsenal. There is no API key to manage and no offline mode.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from econoclast.log import get_logger

log = get_logger("config")

# Where the Codex CLI hides when it ships inside the ChatGPT desktop app.
_CODEX_FALLBACKS = (
    "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
    "/Applications/ChatGPT.app/Contents/Resources/codex",
    "/Applications/Codex.app/Contents/Resources/codex",
)
_CLAUDE_FALLBACKS = (
    str(Path.home() / ".claude" / "local" / "claude"),
    str(Path.home() / ".local" / "bin" / "claude"),
)


@dataclass
class LiteratureConfig:
    enabled: bool = True
    max_results: int = 12
    sources: list[str] = field(default_factory=lambda: ["openalex", "semantic_scholar", "arxiv", "crossref"])
    local_dirs: list[str] = field(default_factory=list)


@dataclass
class Settings:
    backend: str = "auto"  # auto | claude | codex
    model: str = ""  # "" = the CLI's default model
    claude_binary: str = "claude"
    codex_binary: str = "codex"
    backend_args: list[str] = field(default_factory=list)
    # "full": no permission prompts, no sandbox, network on (the default; the agent works
    # inside the case folder). "guarded": edits and shell stay inside the case folder.
    permissions: str = "full"
    browser_mcp: bool = True  # attach the Playwright MCP so blocked downloads can be browsed
    extra_mcp: dict[str, Any] = field(default_factory=dict)  # more MCP servers for the agent
    subagents: bool = True  # let Claude Code fan out conspirators (parallel subagents)
    time_limit_min: int = 90
    pack_after: bool = True  # pack data, downloads and big outputs into the case vault when a hunt ends
    host: str = "127.0.0.1"
    port: int = 7777
    lang: str = "auto"  # auto | en | zh
    contact_email: str | None = None
    literature: LiteratureConfig = field(default_factory=LiteratureConfig)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | os.PathLike[str] | None = None) -> Settings:
        data: dict[str, Any] = {}
        for cfg in _config_files(path):
            try:
                with open(cfg, encoding="utf-8") as fh:
                    data.update(yaml.safe_load(fh) or {})
            except OSError as exc:
                log.warning("could not read %s: %s", cfg, exc)

        lit = data.get("literature", {}) or {}
        s = cls(
            backend=str(os.getenv("ECONOCLAST_BACKEND") or data.get("backend") or "auto").lower(),
            model=str(os.getenv("ECONOCLAST_MODEL") or data.get("model") or ""),
            claude_binary=str(data.get("claude_binary", "claude")),
            codex_binary=str(data.get("codex_binary", "codex")),
            backend_args=list(data.get("backend_args", []) or []),
            permissions=str(os.getenv("ECONOCLAST_PERMISSIONS") or data.get("permissions") or "full"),
            browser_mcp=bool(data.get("browser_mcp", True)),
            extra_mcp=dict(data.get("extra_mcp", {}) or {}),
            subagents=bool(data.get("subagents", True)),
            time_limit_min=int(data.get("time_limit_min", 90)),
            pack_after=bool(data.get("pack_after", True)),
            host=str(data.get("host", "127.0.0.1")),
            port=int(os.getenv("ECONOCLAST_PORT") or data.get("port", 7777)),
            lang=str(data.get("lang", "auto")),
            contact_email=data.get("contact_email") or os.getenv("ECONOCLAST_CONTACT_EMAIL") or None,
            literature=LiteratureConfig(
                enabled=bool(lit.get("enabled", True)),
                max_results=int(lit.get("max_results", 12)),
                sources=list(lit.get("sources", LiteratureConfig().sources)),
                local_dirs=list(lit.get("local_dirs", [])),
            ),
            raw=data,
        )
        if s.backend not in ("auto", "claude", "codex"):
            s.backend = "auto"
        if s.permissions not in ("full", "guarded"):
            s.permissions = "full"
        return s

    # ----------------------------------------------------------- agents
    def claude_path(self) -> str | None:
        return _find(self.claude_binary, _CLAUDE_FALLBACKS)

    def codex_path(self) -> str | None:
        return _find(self.codex_binary, _CODEX_FALLBACKS)

    def pick_backend(self, prefer: str | None = None) -> tuple[str, str] | None:
        """Return (label, binary path) for the agent to run, or None if neither exists."""
        pref = (prefer or self.backend or "auto").lower()
        order = {"claude": ["claude", "codex"], "codex": ["codex", "claude"]}.get(pref, ["claude", "codex"])
        for which in order:
            path = self.claude_path() if which == "claude" else self.codex_path()
            if path:
                return which, path
        return None


def _find(name: str, fallbacks: tuple[str, ...]) -> str | None:
    hit = shutil.which(name)
    if hit:
        return hit
    if os.path.isabs(name) and os.access(name, os.X_OK):
        return name
    for fb in fallbacks:
        if os.access(fb, os.X_OK):
            return fb
    return None


def _config_files(path: str | os.PathLike[str] | None) -> list[Path]:
    if path:
        p = Path(path)
        return [p] if p.exists() else []
    from econoclast.case.store import home

    out = []
    user = home() / "config.yaml"
    if user.exists():
        out.append(user)
    for name in ("econoclast.yaml", "econoclast.yml"):
        p = Path.cwd() / name
        if p.exists():
            out.append(p)
            break
    return out
