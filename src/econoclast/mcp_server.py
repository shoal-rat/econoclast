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
            path: local path OR a URL (PDF, arXiv abstract page, or paper webpage).
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

        Give it a local path or a URL. It fetches the paper, runs the forensics +
        adversarial critique, then tries to find and download the dataset named in
        the paper and auto-run a specification curve. If you already have the data
        locally, pass its path as `data`.

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
