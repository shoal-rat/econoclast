"""Econoclast command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path

# Make Unicode (≥, ✅, emoji) render on legacy Windows code pages.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from econoclast.logging import setup_logging
from econoclast.version import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Econoclast — an adversarial AI referee that red-teams empirical-economics papers.",
)
console = Console()

_BAND_STYLE = {
    "Robust": "bold green",
    "Minor concerns": "yellow",
    "Material concerns": "dark_orange3",
    "Fragile": "bold red",
    "Severe": "bold white on red",
}
_SEV_STYLE = {"critical": "bold white on red", "high": "bold red", "medium": "dark_orange3",
              "low": "blue", "info": "dim"}


@app.command()
def review(
    paper: Path = typer.Argument(..., help="Path to the paper (.pdf, .tex, or .txt)."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output directory for the report files."),
    fmt: str = typer.Option("all", "--format", "-f", help="md | json | html | all"),
    backend: str = typer.Option("auto", "--backend", "-b",
                                help="LLM backend: auto | claude | codex | mock (claude/codex need no API key)."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Deterministic forensics only (no model calls)."),
    no_literature: bool = typer.Option(False, "--no-literature", help="Skip online literature retrieval."),
    no_blind: bool = typer.Option(False, "--no-blind", help="Don't blind author identity (not recommended)."),
    offline: bool = typer.Option(False, "--offline", help="Force the offline mock model."),
    attacks: str | None = typer.Option(None, "--attacks", help="Comma-separated subset of attack names."),
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to an econoclast.yaml."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the full adversarial review on a paper."""
    setup_logging("DEBUG" if verbose else "INFO")
    from econoclast.agent.harness import Econoclast
    from econoclast.config import Settings, cli_routes
    from econoclast.report import render_html, render_markdown

    if not paper.exists():
        console.print(f"[red]File not found:[/red] {paper}")
        raise typer.Exit(1)

    names = [a.strip() for a in attacks.split(",")] if attacks else None
    settings = Settings.load(str(config) if config else None)
    if backend == "claude":
        settings.routes = cli_routes("claude_cli")
    elif backend == "codex":
        settings.routes = cli_routes("codex_cli")
    eco = Econoclast(settings=settings, force_mock=offline or backend == "mock")
    workers = 3 if backend in ("claude", "codex") else 6

    with console.status("[bold]Reviewing…[/bold]", spinner="dots") as status:
        report = eco.review(
            paper,
            attack_names=names,
            use_llm=not no_llm,
            use_literature=not no_literature,
            blind=not no_blind,
            max_workers=workers,
            progress=lambda m: status.update(f"[bold]Reviewing…[/bold] {m}"),
        )

    _print_summary(report)

    out_dir = out or Path(f"econoclast-{Path(paper).stem}")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    if fmt in ("json", "all"):
        p = out_dir / "report.json"
        p.write_text(report.to_json(), encoding="utf-8")
        written.append(p)
    if fmt in ("md", "all"):
        p = out_dir / "report.md"
        p.write_text(render_markdown(report), encoding="utf-8")
        written.append(p)
    if fmt in ("html", "all"):
        p = out_dir / "report.html"
        p.write_text(render_html(report), encoding="utf-8")
        written.append(p)
    console.print("\n[dim]Wrote:[/dim] " + ", ".join(str(p) for p in written))


@app.command()
def forensics(
    paper: Path = typer.Argument(..., help="Path to the paper."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run ONLY the deterministic statistical forensics (offline, no keys)."""
    setup_logging("DEBUG" if verbose else "WARNING")
    from econoclast.forensics import run_forensics
    from econoclast.ingest.paper import load_paper

    if not paper.exists():
        console.print(f"[red]File not found:[/red] {paper}")
        raise typer.Exit(1)

    p = load_paper(paper)
    console.print(f"[bold]{p.title}[/bold]  [dim]({len(p.claims)} claims extracted)[/dim]\n")
    results = run_forensics(p)
    table = Table(show_lines=False, header_style="bold")
    for col in ("Test", "Verdict", "N", "Summary"):
        table.add_column(col)
    for r in results:
        vstyle = {"suspicious": "bold red", "clean": "green", "inconclusive": "yellow"}.get(r.verdict, "dim")
        table.add_row(r.name, Text(r.verdict, style=vstyle), str(r.n_inputs), r.summary)
    console.print(table)


@app.command()
def claims(
    paper: Path = typer.Argument(..., help="Path to the paper."),
    limit: int = typer.Option(60, "--limit", "-n"),
) -> None:
    """Dump the statistical claims Econoclast extracted (for debugging extraction)."""
    setup_logging("WARNING")
    from econoclast.ingest.paper import load_paper

    p = load_paper(paper)
    table = Table(title=f"{len(p.claims)} claims — {p.title[:60]}", header_style="bold")
    for col in ("loc", "coef", "se", "stat", "p", "mean/sd", "n"):
        table.add_column(col)
    for c in p.claims[:limit]:
        stat = f"{c.test_type}={c.stat_value}" if c.stat_value is not None else ""
        pv = f"{c.p_comparator}{c.p_value}" if c.p_value is not None else ""
        msd = f"{c.mean}/{c.sd}" if c.mean is not None else ""
        table.add_row((c.table or c.section or "")[:24], _s(c.coef), _s(c.se), stat, pv, msd, _s(c.n))
    console.print(table)


@app.command("attacks")
def list_attacks() -> None:
    """List every available attack."""
    from econoclast.attacks.registry import all_attacks

    table = Table(title="Econoclast attacks", header_style="bold")
    for col in ("name", "kind", "category", "needs LLM", "what it does"):
        table.add_column(col)
    for a in all_attacks():
        table.add_row(a.name, a.kind, a.category, "yes" if a.requires_llm else "—", a.description)
    console.print(table)


@app.command()
def models(config: Path | None = typer.Option(None, "--config", "-c")) -> None:
    """Show the configured model routing and which API keys are detected."""
    from econoclast.config import Settings

    s = Settings.load(str(config) if config else None)
    table = Table(title="Model routing", header_style="bold")
    for col in ("role", "provider:model", "usable"):
        table.add_column(col)
    for role in ("extractor", "attacker", "referee"):
        for ref in s.models_for(role):
            ok = "[green]yes[/green]" if ref.is_usable() else "[red]no key[/red]"
            table.add_row(role, f"{ref.provider}:{ref.model}", ok)
    console.print(table)
    console.print(f"\nLive models available: [bold]{'yes' if s.has_live_models() else 'no (mock only)'}[/bold]")


@app.command()
def ui() -> None:
    """Launch the Streamlit web UI (requires `pip install econoclast[ui]`)."""
    import subprocess
    from pathlib import Path as _P

    try:
        import streamlit  # noqa: F401
    except ImportError:
        console.print("[red]Streamlit is not installed.[/red] Run: pip install econoclast[ui]")
        raise typer.Exit(1) from None
    app_path = _P(__file__).parent / "ui" / "app.py"
    console.print("[bold]Launching Econoclast UI…[/bold] (Ctrl-C to stop)")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)])


@app.command()
def mcp() -> None:
    """Run the Econoclast MCP server (stdio) so Claude Code / Codex can call it as a tool."""
    from econoclast.mcp_server import main as mcp_main

    mcp_main()


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"econoclast {__version__}")


# --------------------------------------------------------------------------- #
def _s(x) -> str:
    return "" if x is None else str(x)


def _print_summary(report) -> None:
    frag = report.fragility
    band = frag.get("band", "Unknown")
    style = _BAND_STYLE.get(band, "bold")
    head = Text()
    head.append(f"Fragility {frag.get('score', 0)}/100  ", style=style)
    head.append(band, style=style)
    body = Text(f"\n{frag.get('band_blurb','')}\n", style="dim")
    if frag.get("integrity_violation"):
        body.append("\n⚠ Integrity flag: a reported statistic is internally impossible/inconsistent.\n", style="bold yellow")
    console.print(Panel(Text.assemble(head, body), title=report.paper_title[:70],
                        subtitle=f"{', '.join(report.designs) or 'design unclear'}", border_style=style))

    if report.referee.get("headline"):
        console.print(f"[bold]Referee:[/bold] {report.referee['headline']}")
        if report.referee.get("assessment"):
            console.print(f"[dim]{report.referee['assessment']}[/dim]\n")

    top = report.findings_sorted()[:10]
    if top:
        table = Table(title=f"Top findings ({len(report.findings)} total)", header_style="bold", show_lines=False)
        for col in ("severity", "conf", "category", "finding", "attack"):
            table.add_column(col)
        for f in top:
            table.add_row(
                Text(f.severity, style=_SEV_STYLE.get(f.severity, "")),
                f"{f.confidence*100:.0f}%", f.category, f.title[:60], f.attack,
            )
        console.print(table)
    else:
        console.print("[green]No findings raised.[/green]")

    susp = [r for r in report.forensic_results if r["verdict"] == "suspicious"]
    if susp:
        console.print("\n[bold]Forensic flags:[/bold] " + ", ".join(r["name"] for r in susp))


if __name__ == "__main__":
    app()
