"""`econoclast setup` — detect the environment and wire everything up.

The goal: a user runs one command (or an agent runs it for them after a couple of
questions), and afterwards they can just hand Econoclast a path or a URL. This
writes ``econoclast.yaml`` and, optionally, registers the MCP server with Claude
Code / Codex so the agent can call Econoclast as a tool.

Econoclast runs on Claude Code or Codex; there are no API keys to configure.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

from econoclast.logging import get_logger

log = get_logger("setup")


def detect_environment() -> dict:
    claude = shutil.which("claude") is not None
    codex = shutil.which("codex") is not None
    recommended = "claude" if claude else ("codex" if codex else "none")
    return {"claude": claude, "codex": codex, "recommended_backend": recommended}


def build_config(backend: str, *, blind: bool, literature: bool, corpus: str | None) -> dict:
    cfg: dict = {}
    if backend in ("claude", "codex"):
        cfg["backend"] = backend
    # backend "auto"/"none": leave it unset so detection picks at run time.
    cfg["literature"] = {"enabled": literature}
    if corpus:
        cfg["literature"]["local_dirs"] = [str(corpus)]
    cfg["blind_default"] = blind
    return cfg


def run_setup(
    *,
    backend: str = "auto",
    blind: bool = True,
    literature: bool = True,
    corpus: str | None = None,
    install_mcp: bool = False,
    out: str | None = None,
) -> dict:
    env = detect_environment()
    if backend == "auto":
        backend = env["recommended_backend"]

    cfg = build_config(backend, blind=blind, literature=literature, corpus=corpus)
    config_path = Path(out) if out else Path("econoclast.yaml")
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    actions: list[str] = [f"Wrote {config_path}"]
    if install_mcp:
        actions += _install_mcp(env)

    next_steps = _next_steps(backend, env, install_mcp)
    return {"backend": backend, "env": env, "config_path": str(config_path),
            "actions": actions, "next_steps": next_steps}


def _install_mcp(env: dict) -> list[str]:
    actions = []
    if env["claude"]:
        try:
            exe = shutil.which("claude")
            proc = subprocess.run(
                [exe, "mcp", "add", "econoclast", "--", "econoclast", "mcp"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode == 0:
                actions.append("Registered the MCP server with Claude Code (`claude mcp add econoclast`).")
            else:
                actions.append(f"Claude MCP registration skipped: {proc.stderr.strip()[:120]}")
        except Exception as exc:  # noqa: BLE001
            actions.append(f"Claude MCP registration failed: {exc}")
    if env["codex"]:
        actions.append(_install_codex_mcp())
    return actions


def _install_codex_mcp() -> str:
    cfg = Path.home() / ".codex" / "config.toml"
    block = '\n[mcp_servers.econoclast]\ncommand = "econoclast"\nargs = ["mcp"]\n'
    try:
        cfg.parent.mkdir(parents=True, exist_ok=True)
        existing = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
        if "mcp_servers.econoclast" in existing:
            return "Codex MCP server already configured in ~/.codex/config.toml."
        cfg.write_text(existing + block, encoding="utf-8")
        return "Added the MCP server to ~/.codex/config.toml ([mcp_servers.econoclast])."
    except Exception as exc:  # noqa: BLE001
        return f"Codex MCP config skipped: {exc}"


def _next_steps(backend: str, env: dict, mcp: bool) -> list[str]:
    steps = []
    if backend == "none":
        steps.append("No agent backend found. Econoclast runs on Claude Code or Codex: install one "
                     "(and log in), then re-run `econoclast setup`.")
        return steps
    if mcp and (env["claude"] or env["codex"]):
        steps.append("Restart your agent, then just say: \"use econoclast to verify <path or URL>\".")
    steps.append("Try it now: econoclast verify examples/demo_paper.txt")
    return steps
