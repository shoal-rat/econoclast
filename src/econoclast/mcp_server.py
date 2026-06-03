"""Econoclast as an MCP server.

This is the "use it from inside Codex / Claude Code" path. It exposes
Econoclast's deterministic forensics and full review as MCP tools, so the agent
you're already talking to can call them directly:

    econoclast mcp            # run the stdio server

Register it with Claude Code:
    claude mcp add econoclast -- econoclast mcp

or Codex (~/.codex/config.toml):
    [mcp_servers.econoclast]
    command = "econoclast"
    args = ["mcp"]

The `forensics` tool needs no API key and is free — the host agent supplies the
reasoning, Econoclast supplies the statistics.
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
    def econoclast_forensics(path: str) -> dict:
        """Run Econoclast's deterministic statistical forensics on a paper.

        Offline and free (no API key). Recomputes p-values (statcheck), checks
        GRIM/GRIMMER, p-curve, z-statistic bunching (caliper), TIVA, Benford and
        terminal-digit tests on the numbers in the paper.

        Args:
            path: path to a .pdf, .tex, or .txt paper.
        Returns:
            extracted designs, claim count, and one result per forensic test.
        """
        from econoclast.attacks.designs import detect_designs
        from econoclast.forensics import run_forensics
        from econoclast.ingest.paper import load_paper

        paper = load_paper(path)
        results = run_forensics(paper)
        return {
            "title": paper.title,
            "designs": sorted(detect_designs(paper.text)),
            "n_claims": len(paper.claims),
            "injection_warnings": paper.meta.get("injection_warnings", []),
            "forensics": [r.to_dict() for r in results],
            "flagged": [r.name for r in results if r.verdict == "suspicious"],
        }

    @mcp.tool()
    def econoclast_review(path: str, use_llm: bool = False, backend: str = "auto") -> dict:
        """Run a full Econoclast adversarial review and return the structured report.

        Args:
            path: path to a .pdf, .tex, or .txt paper.
            use_llm: also run the LLM-reasoning attacks (specification search,
                cherry-picking, identification critique, ...). Default False so the
                call is free and fast; set True to use the configured/backend model.
            backend: "auto" | "claude" | "codex" | "mock". Note: calling an LLM
                backend from inside another agent works but nests model calls —
                prefer use_llm=False and let THIS agent do the reasoning over the
                returned forensics.
        Returns:
            the full Econoclast report dict (fragility score, findings, forensics).
        """
        from econoclast.agent.harness import Econoclast
        from econoclast.config import Settings, cli_routes

        settings = Settings.load()
        if backend == "claude":
            settings.routes = cli_routes("claude_cli")
        elif backend == "codex":
            settings.routes = cli_routes("codex_cli")
        eco = Econoclast(settings=settings, force_mock=(backend == "mock"))
        report = eco.review(Path(path), use_llm=use_llm, use_literature=use_llm)
        return report.to_dict()

    @mcp.tool()
    def econoclast_list_attacks() -> list[dict]:
        """List every available Econoclast attack (deterministic + LLM)."""
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
