"""Econoclast command-line interface."""

from __future__ import annotations

import sys
from pathlib import Path

# Make non-ASCII output render on legacy Windows code pages.
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
                                help="Which agent to use: auto | claude | codex (no API key needed)."),
    no_literature: bool = typer.Option(False, "--no-literature", help="Skip online literature retrieval."),
    no_blind: bool = typer.Option(False, "--no-blind", help="Don't blind author identity (not recommended)."),
    ensemble: int = typer.Option(1, "--ensemble", help="Run each LLM attack N times; keep findings that recur."),
    deep: bool = typer.Option(False, "--deep", help="Branch-and-merge: try several verification strategies for hard methods."),
    attacks: str | None = typer.Option(None, "--attacks", help="Comma-separated subset of attack names."),
    replicate: Path | None = typer.Option(None, "--replicate",
                                          help="Replication spec config (YAML) -> run a specification curve."),
    config: Path | None = typer.Option(None, "--config", "-c", help="Path to an econoclast.yaml."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the full adversarial review on a paper (local path or URL)."""
    setup_logging("DEBUG" if verbose else "INFO")
    from econoclast.ingest.fetch import is_url

    if not is_url(paper) and not Path(paper).exists():
        console.print(f"[red]Not found:[/red] {paper}")
        raise typer.Exit(1)
    paper_stem = "paper" if is_url(paper) else Path(paper).stem

    names = [a.strip() for a in attacks.split(",")] if attacks else None
    eco = _build(backend, config)

    with console.status("[bold]Reviewing…[/bold]", spinner="dots") as status:
        report = eco.review(
            paper,
            attack_names=names,
            use_literature=not no_literature,
            blind=not no_blind,
            ensemble=ensemble,
            deep=deep,
            replication_config=str(replicate) if replicate else None,
            max_workers=_WORKERS,
            progress=lambda m: status.update(f"[bold]Reviewing…[/bold] {m}"),
        )

    _print_summary(report)
    written = _write_report(report, out or Path(f"econoclast-{paper_stem}"), fmt)
    console.print("\n[dim]Wrote:[/dim] " + ", ".join(str(p) for p in written))


@app.command()
def verify(
    paper: str = typer.Argument(..., help="Paper path or URL. Econoclast fetches it, finds & downloads "
                                          "the dataset, and runs the whole review automatically."),
    data: Path | None = typer.Option(None, "--data", help="Local dataset (skip auto-download)."),
    out: Path | None = typer.Option(None, "--out", "-o"),
    fmt: str = typer.Option("all", "--format", "-f", help="md | json | html | all"),
    backend: str = typer.Option("auto", "--backend", "-b", help="auto | claude | codex"),
    no_literature: bool = typer.Option(False, "--no-literature"),
    no_blind: bool = typer.Option(False, "--no-blind"),
    deep: bool = typer.Option(False, "--deep", help="Branch-and-merge verification for hard methods."),
    allow_code: bool = typer.Option(False, "--allow-code", help="Let the agent write+run a check for an uncovered method (untrusted)."),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Autonomous end-to-end check: paper -> critique -> dataset -> specification curve."""
    setup_logging("DEBUG" if verbose else "INFO")
    from econoclast.ingest.fetch import is_url

    if not is_url(paper) and not Path(paper).exists():
        console.print(f"[red]Not found:[/red] {paper}")
        raise typer.Exit(1)

    eco = _build(backend, config)

    with console.status("[bold]Verifying...[/bold]", spinner="dots") as status:
        report = eco.verify(
            paper, data=str(data) if data else None,
            use_literature=not no_literature, blind=not no_blind, deep=deep, allow_code=allow_code,
            max_workers=_WORKERS,
            progress=lambda m: status.update(f"[bold]Verifying...[/bold] {m}"),
        )

    ds = report.meta.get("dataset", {})
    if ds.get("autoconfig"):
        console.print(f"[green]Dataset:[/green] auto-replicated from {ds.get('source')}")
    elif ds.get("note"):
        console.print(f"[yellow]Dataset:[/yellow] {ds['note']}")
    _print_summary(report)

    out_dir = out or Path(f"econoclast-{'paper' if is_url(paper) else Path(paper).stem}")
    written = _write_report(report, out_dir, fmt)
    console.print("\n[dim]Wrote:[/dim] " + ", ".join(str(p) for p in written))


@app.command()
def batch(
    path: str = typer.Argument(..., help="Folder or glob of papers (.pdf/.tex/.txt)."),
    out: Path = typer.Option(Path("econoclast-batch"), "--out", "-o"),
    full: bool = typer.Option(False, "--verify", help="Use full verify (fetch data + replicate) per paper."),
    backend: str = typer.Option("auto", "--backend", "-b"),
    config: Path | None = typer.Option(None, "--config", "-c"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Review a whole folder of papers and rank them by fragility."""
    setup_logging("DEBUG" if verbose else "WARNING")
    import glob as _glob

    papers = _find_papers(path, _glob)
    if not papers:
        console.print(f"[red]No papers found at:[/red] {path}")
        raise typer.Exit(1)
    console.print(f"[bold]{len(papers)} papers[/bold] to review.\n")

    eco = _build(backend, config)

    rows = []
    out.mkdir(parents=True, exist_ok=True)
    for i, pp in enumerate(papers, 1):
        stem = Path(pp).stem[:40]
        console.print(f"[dim]({i}/{len(papers)})[/dim] {stem}")
        try:
            if full:
                report = eco.verify(str(pp))
            else:
                report = eco.review(str(pp))
            _write_report(report, out / stem, "all")
            frag = report.fragility
            rows.append({"paper": stem, "title": report.paper_title[:70],
                         "fragility": frag.get("score", 0), "band": frag.get("band", ""),
                         "findings": len(report.findings),
                         "integrity": frag.get("integrity_violation", False)})
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]failed:[/red] {exc}")
            rows.append({"paper": stem, "title": "(failed)", "fragility": -1,
                         "band": "error", "findings": 0, "integrity": False})

    rows.sort(key=lambda r: r["fragility"], reverse=True)
    _write_batch_summary(rows, out)
    table = Table(title="Batch summary (most fragile first)", header_style="bold")
    for col in ("fragility", "band", "findings", "paper"):
        table.add_column(col)
    for r in rows:
        table.add_row(str(r["fragility"]), r["band"], str(r["findings"]), r["paper"])
    console.print(table)
    console.print(f"\n[dim]Wrote per-paper reports and summary to[/dim] {out}/")


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
def backend(config: Path | None = typer.Option(None, "--config", "-c")) -> None:
    """Show which agent backend Econoclast will use (Claude Code or Codex)."""
    import shutil

    from econoclast.config import Settings

    s = Settings.load(str(config) if config else None)
    claude = shutil.which(s.claude_binary)
    codex = shutil.which(s.codex_binary)
    table = Table(title="Backend", header_style="bold")
    for col in ("agent", "on PATH"):
        table.add_column(col)
    table.add_row("Claude Code", "[green]yes[/green]" if claude else "[red]no[/red]")
    table.add_row("Codex", "[green]yes[/green]" if codex else "[red]no[/red]")
    console.print(table)
    chosen = "none found" if not (claude or codex) else (
        s.backend if s.backend in ("claude", "codex") else ("claude" if claude else "codex"))
    console.print(f"\nPreference [bold]{s.backend}[/bold]; will use: [bold]{chosen}[/bold]")
    if not (claude or codex):
        console.print("[yellow]Install Claude Code or Codex (and log in) to run Econoclast.[/yellow]")


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
    backend: str = typer.Option("auto", "--backend", "-b", help="auto | claude | codex"),
    no_blind: bool = typer.Option(False, "--no-blind", help="Don't blind author identity."),
    no_literature: bool = typer.Option(False, "--no-literature", help="Disable online literature retrieval."),
    corpus: Path | None = typer.Option(None, "--corpus", help="Folder of your own papers to ground reviews."),
    install_mcp: bool = typer.Option(True, "--mcp/--no-mcp", help="Register Econoclast with Claude Code / Codex."),
    browser_mcp: bool = typer.Option(True, "--browser-mcp/--no-browser-mcp",
                                     help="Give the agent a browser (Playwright MCP) for blocked downloads."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Non-interactive: accept defaults/flags (for agents)."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Where to write econoclast.yaml."),
) -> None:
    """One-time setup: detect backends, write config, and register the MCP tool."""
    setup_logging("WARNING")
    from econoclast.setup_wizard import detect_environment, run_setup

    env = detect_environment()
    console.print(Panel(
        f"Claude Code CLI: [bold]{'yes' if env['claude'] else '—'}[/bold]   "
        f"Codex CLI: [bold]{'yes' if env['codex'] else '—'}[/bold]\n"
        f"Recommended backend: [bold]{env['recommended_backend']}[/bold]",
        title="Detected environment"))

    blind, literature = not no_blind, not no_literature
    interactive = not yes and sys.stdin.isatty()
    if interactive:
        backend = typer.prompt("Backend (auto/claude/codex)",
                               default=backend if backend != "auto" else env["recommended_backend"])
        blind = typer.confirm("Blind author identity during LLM review? (recommended)", default=True)
        literature = typer.confirm("Retrieve related literature online?", default=True)
        c = typer.prompt("Folder of your own papers to ground reviews (blank = none)", default="")
        corpus = Path(c) if c.strip() else None
        if env["claude"] or env["codex"]:
            install_mcp = typer.confirm("Register Econoclast as a tool in Claude Code / Codex?", default=True)

    res = run_setup(backend=backend, blind=blind, literature=literature,
                    corpus=str(corpus) if corpus else None, install_mcp=install_mcp,
                    browser_mcp=browser_mcp, out=str(out) if out else None)

    console.print(f"\n[green]Backend:[/green] {res['backend']}")
    for a in res["actions"]:
        console.print(f"  - {a}")
    console.print("\n[bold]Next:[/bold]")
    for s in res["next_steps"]:
        console.print(f"  - {s}")


@app.command()
def reproduce(
    package: Path = typer.Argument(..., help="Replication-package folder (or a single script)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Actually run the code (it is untrusted; off by default)."),
    timeout: int = typer.Option(900, "--timeout", help="Seconds before the run is killed."),
) -> None:
    """Run an author's replication package and report what it produced (opt-in, untrusted)."""
    setup_logging("INFO")
    from econoclast.replication.runner import run_replication_package

    if not yes:
        console.print("[yellow]This runs the authors' code, which is untrusted. It is NOT sandboxed.[/yellow]")
        console.print("Re-run with --yes (ideally inside a container or throwaway VM) to proceed.")
    res = run_replication_package(package, allow_code=yes, timeout=timeout)
    if not res.get("ran"):
        console.print(f"[dim]Did not run:[/dim] {res.get('reason')}")
        return
    status = "[green]succeeded[/green]" if res.get("succeeded") else f"[red]exit {res.get('returncode')}[/red]"
    console.print(f"Ran {res.get('entrypoint')} ({res.get('kind')}): {status}")
    if res.get("stdout_tail"):
        console.print("[dim]--- output tail ---[/dim]")
        console.print(res["stdout_tail"][-2000:])


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
_WORKERS = 3  # the backend is a subprocess CLI; keep concurrency modest


def _build(backend: str, config: Path | None):
    """Construct an Econoclast, or exit cleanly if no agent backend is available."""
    from econoclast.agent.harness import Econoclast
    from econoclast.config import Settings
    from econoclast.llm.base import LLMError

    settings = Settings.load(str(config) if config else None)
    if backend in ("claude", "codex"):
        settings.backend = backend
    try:
        return Econoclast(settings=settings)
    except LLMError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from None


def _s(x) -> str:
    return "" if x is None else str(x)


_PAPER_EXTS = (".pdf", ".tex", ".txt", ".md")


def _find_papers(path: str, glob_module) -> list[Path]:
    is_glob = ("*" in path) or ("?" in path)
    if is_glob:
        hits = [Path(p) for p in glob_module.glob(path, recursive=True)]
    elif Path(path).is_dir():
        hits = [p for p in Path(path).rglob("*") if p.is_file()]
    else:
        hits = [Path(path)] if Path(path).exists() else []
    return sorted(p for p in hits if p.suffix.lower() in _PAPER_EXTS)


def _write_batch_summary(rows, out_dir: Path) -> None:
    import csv

    with open(out_dir / "summary.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["fragility", "band", "findings", "integrity", "paper", "title"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    lines = ["# Econoclast batch summary", "",
             "| Fragility | Band | Findings | Paper |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['fragility']} | {r['band']} | {r['findings']} | {r['title']} |")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_report(report, out_dir, fmt: str):
    from econoclast.report import render_html, render_markdown

    out_dir = Path(out_dir)
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
    return written


def _print_summary(report) -> None:
    frag = report.fragility
    band = frag.get("band", "Unknown")
    style = _BAND_STYLE.get(band, "bold")
    head = Text()
    head.append(f"Fragility {frag.get('score', 0)}/100  ", style=style)
    head.append(band, style=style)
    body = Text(f"\n{frag.get('band_blurb','')}\n", style="dim")
    if frag.get("integrity_violation"):
        body.append("\n Integrity flag: a reported statistic is internally impossible/inconsistent.\n", style="bold yellow")
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


if __name__ == "__main__":
    app()
