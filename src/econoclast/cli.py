"""Econoclast's command line. With no arguments it opens the app."""

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
from rich.markup import escape
from rich.table import Table

from econoclast.version import __version__

app = typer.Typer(add_completion=False, invoke_without_command=True,
                  help="Econoclast: an assassin from the Ravenna mosaics that tests empirical papers.")
console = Console()

_FAMILY_GLYPH = {"read": "📜", "write": "✒", "shell": "⚒", "web": "⛵", "search": "🔭", "browser": "🌐",
                 "spawn": "🗡", "plan": "📋", "mcp": "◆", "other": "·"}


@app.callback()
def _root(ctx: typer.Context,
          version: bool = typer.Option(False, "--version", help="Print the version and exit.")) -> None:
    if version:
        console.print(f"econoclast {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        from econoclast.app import run

        run()


@app.command("app")
def app_cmd(browser: bool = typer.Option(False, "--browser", help="Developer preview in a browser."),
            port: int = typer.Option(7777, "--port"),
            no_open: bool = typer.Option(False, "--no-open", help="With --browser: do not open a browser."),
            debug: bool = typer.Option(False, "--debug", help="Open the web inspector.")) -> None:
    """Open the Econoclast app."""
    if browser:
        from econoclast.app.devserver import serve

        serve(port, open_browser=not no_open)
        return
    from econoclast.app import run

    run(debug=debug)


@app.command()
def hunt(
    paper: str = typer.Argument("", help="URL, DOI, arXiv id, title, or a local file."),
    data: str = typer.Option("", "--data", "-d", help="A dataset or replication package you already have."),
    claim: str = typer.Option("", "--claim", "-c", help="The claim to test (default: the headline result)."),
    lang: str = typer.Option("en", "--lang", "-l", help="Narration language: en | zh."),
    backend: str = typer.Option("auto", "--backend", "-b", help="auto | claude | codex."),
    depth: str = typer.Option("thorough", "--depth", help="thorough | swift."),
    case_dir: str = typer.Option("", "--case", help="Run an existing case folder (used by the app)."),
) -> None:
    """Unleash the Sicarius on a paper, here in the terminal."""
    import signal
    import threading
    import time

    from econoclast.case.store import Case
    from econoclast.sicarius import Hunt, NoAgent

    if case_dir:
        case = Case(case_dir)
        try:
            h = Hunt(case)
        except NoAgent as exc:
            case.update_meta(status="failed", error=str(exc))
            case.emit("case.closed", status="failed", error=str(exc))
            raise typer.Exit(1) from exc
        signal.signal(signal.SIGTERM, lambda *_: h.abort())
        h.run()
        return

    if not paper:
        console.print("[red]Name a paper:[/] econoclast hunt https://arxiv.org/abs/... (or a file path)")
        raise typer.Exit(2)
    local = Path(paper).expanduser()
    case = Case.create(paper=str(local.name if local.exists() else paper), claim=claim, lang=lang,
                       backend=backend, depth=depth)
    if local.exists():
        import shutil

        shutil.copy2(local, case.path("paper", local.name))
        case.update_meta(paper_input=f"paper/{local.name} (a local file the traveller provided)")
    if data:
        src = Path(data).expanduser()
        if src.exists():
            import shutil

            (shutil.copytree if src.is_dir() else shutil.copy2)(src, case.path("offerings", src.name))
            case.update_meta(data_input=f"offerings/{src.name}")
        else:
            case.update_meta(data_input=data)
    try:
        h = Hunt(case)
    except NoAgent as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    console.print(f"[bold #c9a23a]ECONOCLAST[/] · case [dim]{case.root}[/] · agent [bold]{h.label}[/]")
    t = threading.Thread(target=h.run, daemon=True)
    t.start()
    seen = 0
    try:
        while t.is_alive() or seen < len(case.events()):
            for ev in case.events(seen):
                seen = ev["seq"] + 1
                _print_event(case, ev)
            time.sleep(0.4)
    except KeyboardInterrupt:
        console.print("[yellow]Calling off the hunt…[/]")
        h.abort()
        t.join(timeout=15)
    v = case.verdict()
    if v:
        f = v["fragility"]
        console.print(f"\n[bold #c9a23a]{f['band_latin']}[/] · {f['band_en']} · fragility "
                      f"[bold]{f['score']}[/]/100\nReport: {case.path('tabula.html')}")


def _print_event(case, ev: dict) -> None:  # noqa: ANN001
    from econoclast.world import station

    k = ev.get("kind")
    if k == "station":
        s = station(ev.get("station", ""))
        name = f"{s.latin} · {s.en}" if s else ev.get("station")
        console.rule(f"[bold #c9a23a]{name}[/]" + (f" [dim]{escape(ev.get('note', ''))}[/]" if ev.get("note") else ""))
    elif k == "narrate":
        who = "" if ev.get("who") == "sicarius" else f"[dim]{ev.get('who')}[/] "
        console.print(f"  {who}[italic]{escape(ev.get('text', ''))[:600]}[/]")
    elif k == "tool":
        fam = ev.get("family", "other").split(":")[0]
        if fam == "arsenal":
            return
        console.print(f"  [dim]{_FAMILY_GLYPH.get(fam, '·')} {escape(ev.get('summary', ''))}[/]")
    elif k == "wound":
        w = ev["wound"]
        console.print(f"  [bold red]✖ {ev.get('blade_latin')}[/] [{w['severity']}] {escape(w['title'])}")
    elif k == "parry":
        p = ev["parry"]
        console.print(f"  [green]⛨ {p['blade']}[/] {escape(p['note'][:200])}")
    elif k == "plea":
        from rich.prompt import Prompt

        console.print(f"\n[bold yellow]The Sicarius asks for your help:[/] {escape(ev.get('what', ''))}\n"
                      f"  {escape(ev.get('why', ''))}" + (f"\n  where: {ev.get('where')}" if ev.get("where") else ""))
        ans = Prompt.ask("  Path or URL (blank = I can't)", default="")
        if ans.strip():
            p = Path(ans.strip()).expanduser()
            if p.exists():
                import shutil

                dst = case.path("offerings", p.name)
                (shutil.copytree if p.is_dir() else shutil.copy2)(p, dst)
                case.answer_plea(ev["plea_id"], files=[str(dst)])
            else:
                case.answer_plea(ev["plea_id"], url=ans.strip())
        else:
            case.answer_plea(ev["plea_id"], declined=True)
    elif k == "case.closed":
        style = "green" if ev.get("status") == "done" else "red"
        console.print(f"[{style}]Hunt {ev.get('status')}[/]" + (f": {escape(str(ev.get('error')))}" if ev.get("error") else ""))


@app.command()
def arsenal(case_dir: str = typer.Option("", "--case", help="The case folder to serve (default: a new one).")) -> None:
    """Run the arsenal MCP server (stdio). Hunts start it for their agent; you can also attach it to your
    own Claude Code or Codex session: `claude mcp add econoclast -- econoclast arsenal`."""
    from econoclast.arsenal.server import main

    if not case_dir:
        from econoclast.case.store import Case

        case = Case.create(paper="(attached to an interactive agent session)", note="mcp")
        case.update_meta(status="attached")
        case_dir = str(case.root)
    main(case_dir)


@app.command()
def fabrica(extra: list[str] = typer.Argument(None, help="Extra packages to install.")) -> None:
    """Build (or extend) the local quant workshop."""
    from econoclast import fabrica as fab

    with console.status("Forging the workshop…"):
        res = fab.build(extra or [])
    console.print(f"Workshop python: [bold]{res['python']}[/] ({res['seconds']}s)")
    if res["missing"]:
        console.print(f"[yellow]Could not install:[/] {', '.join(res['missing'])}")


@app.command()
def doctor() -> None:
    """Check what the Sicarius can use on this machine."""
    import shutil

    from econoclast import fabrica as fab
    from econoclast.config import Settings

    s = Settings.load()
    t = Table(show_header=False, box=None)
    picked = s.pick_backend()
    t.add_row("agent", f"[bold]{picked[0]}[/] {picked[1]}" if picked else "[red]none: install Claude Code or Codex[/]")
    t.add_row("claude", s.claude_path() or "[dim]not found[/]")
    t.add_row("codex", s.codex_path() or "[dim]not found[/]")
    t.add_row("permissions", s.permissions)
    t.add_row("browser (npx)", shutil.which("npx") or "[dim]not found: no Playwright MCP[/]")
    st = fab.status()
    t.add_row("workshop", st["python"] or "[dim]not built yet (econoclast fabrica)[/]")
    t.add_row("uv", st["uv"] or "[dim]not found (pip will be used)[/]")
    t.add_row("Rscript", st["rscript"] or "[dim]not found[/]")
    console.print(t)


@app.command()
def cases() -> None:
    """List past hunts."""
    from econoclast.case.store import list_cases

    t = Table("case", "status", "score", "title")
    for c in list_cases(40):
        t.add_row(c["id"], str(c.get("status")), "" if c.get("score") is None else str(c["score"]),
                  escape(str(c.get("title") or ""))[:70])
    console.print(t)


@app.command()
def pack(case_id: str = typer.Argument("", help="Case id; omit with --all."),
         all_: bool = typer.Option(False, "--all", help="Pack every finished case.")) -> None:
    """Pack a finished hunt's data and big outputs into its vault (done automatically after each hunt)."""
    from econoclast.case.store import Case, cases_root
    from econoclast.case.vault import pack as do_pack

    roots = [p for p in cases_root().iterdir() if (p / "case.json").exists()] if all_ else [Case.load(case_id).root]
    for r in roots:
        c = Case(r)
        if c.meta().get("status") in ("running", "starting"):
            continue
        res = do_pack(c)
        if res["packed"] or res.get("removed"):
            gone = ", ".join(r["path"] for r in res.get("removed", []))
            console.print(f"{c.id}: {res['packed']} files packed, {res['before_bytes'] / 1e6:.1f} MB → "
                          f"{res['after_bytes'] / 1e6:.1f} MB" + (f"; removed {gone}" if gone else ""))


@app.command()
def unpack(case_id: str = typer.Argument(..., help="Case id.")) -> None:
    """Restore a case's packed files from its vault."""
    from econoclast.case.store import Case
    from econoclast.case.vault import unpack as do_unpack

    console.print(f"Restored {do_unpack(Case.load(case_id))} files.")


@app.command()
def clean(fabrica_too: bool = typer.Option(False, "--fabrica", help="Also delete the shared quant workshop "
                                           "(rebuilt automatically on the next hunt)."),
          trash: bool = typer.Option(True, "--trash/--keep-trash", help="Empty ~/.econoclast/.trash.")) -> None:
    """Reclaim disk space: pack finished hunts, prune the uv cache, empty the trash."""
    import shutil
    import subprocess

    from econoclast import fabrica as fab
    from econoclast.case.store import Case, cases_root, home
    from econoclast.case.vault import pack as do_pack

    freed = 0
    for r in cases_root().iterdir():
        c = Case(r)
        if (r / "case.json").exists() and c.meta().get("status") not in ("running", "starting"):
            res = do_pack(c)
            freed += res["before_bytes"] - res["after_bytes"]
    if trash and (home() / ".trash").exists():
        freed += sum(f.stat().st_size for f in (home() / ".trash").rglob("*") if f.is_file())
        shutil.rmtree(home() / ".trash")
    if fabrica_too and fab.venv_dir().exists():
        freed += sum(f.stat().st_size for f in fab.venv_dir().rglob("*") if f.is_file())
        shutil.rmtree(fab.venv_dir())
    if shutil.which("uv"):
        subprocess.run(["uv", "cache", "prune"], capture_output=True)
    console.print(f"Freed about {freed / 1e6:.0f} MB (plus whatever `uv cache prune` released).")


@app.command("install-app")
def install_app(system: bool = typer.Option(False, "--system", help="Install into /Applications.")) -> None:
    """Install Econoclast.app (macOS) so it lives in the Dock and Launchpad."""
    from econoclast.app.macos import install

    path = install(system=system)
    console.print(f"Installed [bold]{path}[/]. Open it from Launchpad or Spotlight.")


@app.command()
def replicate(spec: str = typer.Argument(..., help="A spec YAML (data, outcome, treatment, ...)."),
              out: str = typer.Option("viae_out", "--out", "-o")) -> None:
    """Run the thousand roads (specification curve + design checks) from a spec file."""
    import json

    from econoclast.viae import SpecConfig, run_replication, viae_wounds
    from econoclast.viae.models import SpecCurve
    from econoclast.viae.plot import plot_spec_curve

    res = run_replication(SpecConfig.from_yaml(spec))
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "viae.json").write_text(json.dumps(res, indent=1, default=str))
    plot_spec_curve(SpecCurve.from_dict(res["spec_curve"]), str(o / "spec_curve.png"))
    s = res["spec_curve"]["summary"]
    console.print(f"{s['n_specs_run']} roads · significant in the expected direction on "
                  f"[bold]{s['share_significant_expected_sign']:.0%}[/]")
    for w in viae_wounds(res):
        console.print(f"  [red]✖[/] [{w.severity}] {w.title}")


@app.command()
def tabula(case_id: str = typer.Argument(..., help="Case id (see `econoclast cases`).")) -> None:
    """Rewrite a case's report files."""
    from econoclast.case.store import Case
    from econoclast.case.tabula import write_tabula

    case = Case.load(case_id)
    files = write_tabula(case)
    console.print(f"Wrote {', '.join(str(case.path(f)) for f in files.values())}")


@app.command("demo-export", hidden=True)
def demo_export(case_id: str, out: str = typer.Option("", "--out")) -> None:
    """Export a case's event log as the app's built-in demonstration (developer tool)."""
    import json

    from econoclast.app.api import WEB
    from econoclast.case.store import Case
    from econoclast.case.tabula import tabula_data

    case = Case.load(case_id)
    evs = case.events()
    t0 = evs[0]["ts"] if evs else 0
    for e in evs:
        e["ts"] = round(e["ts"] - t0, 2)
    payload = {"meta": {k: case.meta().get(k) for k in ("title", "paper_input", "lang", "backend_used")},
               "events": evs, "tabula": tabula_data(case)}
    dest = Path(out) if out else WEB / "demo" / f"card-krueger.{case.meta().get('lang', 'en')}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    console.print(f"Demo written to {dest} ({len(evs)} events)")


if __name__ == "__main__":
    app()
