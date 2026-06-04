"""Econoclast as an MCP server.

This is the "use it from inside Codex / Claude Code" path. It exposes Econoclast's
intake, review, verify, and replication as MCP tools, so the agent you are already
talking to can call them directly:

    econoclast mcp            # run the stdio server

Register it with Claude Code:
    claude mcp add econoclast -- econoclast mcp

or Codex (~/.codex/config.toml):
    [mcp_servers.econoclast]
    command = "econoclast"
    args = ["mcp"]
"""

from __future__ import annotations

from pathlib import Path

from econoclast.logging import get_logger

log = get_logger("mcp")


def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "The MCP SDK is not installed. Run `pip install \"econoclast[mcp]\"`."
        ) from exc

    mcp = FastMCP("econoclast")

    @mcp.tool()
    def econoclast_review(path: str, backend: str = "auto") -> dict:
        """Run a full Econoclast adversarial review and return the structured report.

        Reads the paper, runs the grounded critique (specification search,
        cherry-picking, identification, robustness, HARKing, over-claiming), and
        researches any method it does not cover. Note: this drives a Claude Code or
        Codex subprocess, so calling it from inside another agent nests model calls.

        Args:
            path: path to a .pdf, .tex, or .txt paper.
            backend: "auto" | "claude" | "codex".
        Returns:
            the full Econoclast report dict (fragility score, findings, referee).
        """
        from econoclast.agent.harness import Econoclast
        from econoclast.config import Settings

        settings = Settings.load()
        if backend in ("claude", "codex"):
            settings.backend = backend
        report = Econoclast(settings=settings).review(Path(path))
        return report.to_dict()

    @mcp.tool()
    def econoclast_intake(request: str) -> dict:
        """Understand a free-text request and return what to ask the user, if anything.

        Call this first when a non-technical user asks you to check a paper. It works out
        what they already gave (a paper link/path, a dataset, a specific claim).

        Only the paper is ever required. If `ready` is true, do NOT open a question round:
        state `plan` to the user in one line (what you will do and roughly how long) and go
        straight to econoclast_verify with the understood paper (and data, if any). Ask only
        `blocking_question` when it is non-empty (the paper itself is missing).

        Args:
            request: the user's message, verbatim.
        Returns:
            {understood: {paper, paper_kind, data, claim}, questions: [...],
             blocking_question: str, plan: str, ready: bool, next: str}
        """
        from econoclast.agent.intake import build_intake
        from econoclast.config import Settings

        return build_intake(request, Settings.load())

    @mcp.tool()
    def econoclast_verify(paper: str, data: str = "") -> dict:
        """Autonomous end-to-end verification of an empirical paper.

        Give it a local path or a URL. It fetches the paper, runs the adversarial
        critique, then tries to find and download the dataset named in the paper and
        auto-run a specification curve. If you already have the data locally, pass
        its path as `data`.

        Args:
            paper: local path OR URL to the paper.
            data: optional local dataset path (skips auto-download).
        Returns:
            the full report dict, with meta.dataset describing what was found.
        """
        from econoclast.agent.harness import Econoclast
        from econoclast.config import Settings

        eco = Econoclast(settings=Settings.load())
        report = eco.verify(paper, data=data or None, use_llm=True, use_literature=True)
        return report.to_dict()

    @mcp.tool()
    def econoclast_replicate(spec_config_path: str) -> dict:
        """Run a specification-curve / multiverse replication from a spec config (YAML).

        Needs the dataset. The config names the data file, outcome, treatment, and the
        pools of controls / fixed-effects / clustering / sample filters to vary; Econoclast
        runs every combination and reports how often the headline result survives. Generate
        a starter config with the CLI: `econoclast replicate --init <data.csv>`.

        Args:
            spec_config_path: path to a replication spec YAML.
        Returns:
            the spec-curve summary, any RDD/DiD checks, and derived findings.
        """
        from econoclast.replication import (
            SpecConfig,
            replication_findings,
            run_replication,
        )

        result = run_replication(SpecConfig.from_yaml(spec_config_path))
        result["findings"] = [f.to_dict() for f in replication_findings(result)]
        return result

    @mcp.tool()
    def econoclast_list_attacks() -> list[dict]:
        """List every available Econoclast attack."""
        from econoclast.attacks.registry import all_attacks

        return [
            {"name": a.name, "kind": a.kind, "category": a.category,
             "needs_llm": a.requires_llm, "description": a.description}
            for a in all_attacks()
        ]

    return mcp


def main() -> None:
    server = build_server()
    log.info("Starting Econoclast MCP server (stdio)…")
    server.run()


if __name__ == "__main__":
    main()
