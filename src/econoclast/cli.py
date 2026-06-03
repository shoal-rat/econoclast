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
    paper: str = typer.Argument(..., help="Path OR URL to the paper (.pdf/.tex/.txt, arXiv, or a webpage)."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output directory for the report files."),
    fmt: str = typer.Option("all", "--format", "-f", help="md | json | html | all"),
    backend: str = typer.Option("auto", "--backend", "-b",
                                help="LLM backend: auto | claude | codex | mock (claude/codex need no API key)."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Deterministic forensics only (no model calls)."),
    no_literature: bool = typer.Option(False, "--no-literature", help="Skip online literature retrieval."),
    no_blind: bool = typer.Option(False, "--no-blind", help="Don't blind author identity (not recommended)."),
    offline: bool = typer.Option(False, "--offline", help="Force the offline mock model."),
    attacks: str | None = typer.Option(None, "--attacks", help="Comma-separated subset of attack names."),
    replicate: Path | None = typer.Option(None, "--replicate",
                                          help="Replication spec config (YAML) → run a specification curve."),
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to an econoclast.yaml."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the full adversarial review on a paper (local path or URL)."""
    setup_logging("DEBUG" if verbose else "INFO")
    from econoclast.agent.harness import Econoclast
    from econoclast.config import Settings, cli_routes
    from econoclast.ingest.fetch import is_url
    from econoclast.report import render_html, render_markdown

    if not is_url(paper) and not Path(paper).exists():
        console.print(f"[red]Not found:[/red] {paper}")
        raise typer.Exit(1)
    paper_stem = "paper" if is_url(paper) else Path(paper).stem

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
            replication_config=str(replicate) if replicate else None,
            max_workers=workers,
            progress=lambda m: status.update(f"[bold]Reviewing…[/bold] {m}"),
        )

    _print_summary(report)

    out_dir = out or Path(f"econoclast-{paper_stem}")
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
    paper: str = typer.Argument(..., help="Path OR URL to the paper."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run ONLY the deterministic statistical forensics (offline, no keys)."""
    setup_logging("DEBUG" if verbose else "WARNING")
    from econoclast.forensics import run_forensics
    from econoclast.ingest.fetch import is_url
    from econoclast.ingest.paper import load_paper

    if not is_url(paper) and not Path(paper).exists():
        console.print(f"[red]Not found:[/red] {paper}")
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
    paper: str = typer.Argument(..., help="Path OR URL to the paper."),
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
def replicate(
    config: Path | None = typer.Argument(None, help="Replication spec config (YAML)."),
    init: Path | None = typer.Option(None, "--init", help="Generate a template config from this dataset."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output dir (review) or config path (--init)."),
    no_plot: bool = typer.Option(False, "--no-plot", help="Skip the specification-curve plot."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run a specification-curve / multiverse replication (needs the dataset)."""
    setup_logging("DEBUG" if verbose else "INFO")
    import json as _json

    from econoclast.replication import (
        SpecConfig,
        replication_findings,
        run_replication,
        template_config,
    )

    if init is not None:
        cfg = template_config(str(init))
        dest = out or Path("econoclast-spec.yaml")
        Path(dest).write_text(cfg.to_yaml(), encoding="utf-8")
        console.print(f"[green]Wrote template config:[/green] {dest}")
        console.print("[dim]Fill in outcome/treatment/controls_pool (and RDD/DiD fields), then "
                      "run `econoclast replicate " + str(dest) + "`.[/dim]")
        return

    if config is None or not Path(config).exists():
        console.print("[red]Provide a spec config YAML, or use --init <data> to generate one.[/red]")
        raise typer.Exit(1)

    spec = SpecConfig.from_yaml(config)
    with console.status("[bold]Running the multiverse…[/bold]"):
        result = run_replication(spec)

    summ = result.get("spec_curve", {}).get("summary", {})
    share = summ.get("share_significant_expected_sign", 0)
    style = "bold red" if share < 0.5 else ("yellow" if share < 0.8 else "green")
    console.print(Panel(
        Text(f"{summ.get('n_specs_run', 0)} specifications · "
             f"{share:.0%} significant in the expected direction\n"
             f"coef median {summ.get('median_coef')}  range [{summ.get('min_coef')}, {summ.get('max_coef')}]",
             style=style),
        title="Specification curve", border_style=style))
    for f in replication_findings(result):
        console.print(f"  [{_SEV_STYLE.get(f.severity,'')}]{f.severity}[/]: {f.title}")

    out_dir = out or Path("econoclast-replication")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "replication.json").write_text(_json.dumps(result, indent=2), encoding="utf-8")
    written = [out_dir / "replication.json"]
    if not no_plot:
        from econoclast.replication.models import SpecCurve
        from econoclast.replication.plot import plot_spec_curve

        curve = SpecCurve.from_dict(result.get("spec_curve", {}))
        p = plot_spec_curve(curve, str(out_dir / "spec_curve.png"))
        if p:
            written.append(Path(p))
    console.print("\n[dim]Wrote:[/dim] " + ", ".join(str(p) for p in written))


@app.command()
def setup(
    backend: str = typer.Option("auto", "--backend", "-b", help="auto | claude | codex | api | none"),
    no_blind: bool = typer.Option(False, "--no-blind", help="Don't blind author identity."),
    no_literature: bool = typer.Option(False, "--no-literature", help="Disable online literature retrieval."),
    corpus: Path | None = typer.Option(None, "--corpus", help="Folder of your own papers to ground reviews."),
    install_mcp: bool = typer.Option(True, "--mcp/--no-mcp", help="Register Econoclast with Claude Code / Codex."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: accept defaults/flags (for agents)."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Where to write econoclast.yaml."),
) -> None:
    """One-time setup: detect backends, write config, and register the MCP tool."""
    setup_logging("WARNING")
    from econoclast.setup_wizard import detect_environment, run_setup

    env = detect_environment()
    keys = ", ".join(k for k, v in env["api_keys"].items() if v) or "none"
    console.print(Panel(
        f"API keys: [bold]{keys}[/bold]\n"
        f"Claude Code CLI: [bold]{'✅' if env['claude'] else '—'}[/bold]   "
        f"Codex CLI: [bold]{'✅' if env['codex'] else '—'}[/bold]\n"
        f"Recommended backend: [bold]{env['recommended_backend']}[/bold]",
        title="Detected environment"))

    blind, literature = not no_blind, not no_literature
    interactive = not yes and sys.stdin.isatty()
    if interactive:
        backend = typer.prompt("Backend (auto/claude/codex/api/none)",
                               default=backend if backend != "auto" else env["recommended_backend"])
        blind = typer.confirm("Blind author identity during LLM review? (recommended)", default=True)
        literature = typer.confirm("Retrieve related literature online?", default=True)
        c = typer.prompt("Folder of your own papers to ground reviews (blank = none)", default="")
        corpus = Path(c) if c.strip() else None
        if env["claude"] or env["codex"]:
            install_mcp = typer.confirm("Register Econoclast as a tool in Claude Code / Codex?", default=True)

    res = run_setup(backend=backend, blind=blind, literature=literature,
                    corpus=str(corpus) if corpus else None, install_mcp=install_mcp,
                    out=str(out) if out else None)

    console.print(f"\n[green]Backend:[/green] {res['backend']}")
    for a in res["actions"]:
        console.print(f"  ✓ {a}")
    console.print("\n[bold]Next:[/bold]")
    for s in res["next_steps"]:
        console.print(f"  • {s}")


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
