# Architecture

Econoclast is three small programs that talk only through files.

```
Econoclast.app (pywebview window)                 the hunt runner                     the agent
┌─────────────────────────────┐   spawns    ┌──────────────────────────┐ spawns ┌─────────────────────────┐
│ web/ (stage, chronicle, UI)  │ ─────────▶ │ python -m econoclast hunt │ ─────▶ │ claude -p --output-format│
│   ▲ window.pywebview.api     │            │   --case <dir>            │        │   stream-json  (or        │
│ app/api.py  (the bridge)     │            │ parses the JSON stream    │        │   codex exec --json)      │
└──────────────┬──────────────┘            └────────────┬─────────────┘        │ full autonomy, network   │
               │ polls                                   │ appends               └──────────┬──────────────┘
               ▼                                         ▼                                  │ MCP (stdio)
        ~/.econoclast/cases/<id>/events.jsonl  ◀──────── appends ── econoclast arsenal ◀───┤
        case.json  MANDATE.md  mcp.json                                                     ├─▶ Playwright MCP
        paper/ data/ code/ out/ notes/ offerings/                                           └─▶ your MCP servers
        verdict.json  tabula.html|md|json
```

## The case folder

Every hunt owns `~/.econoclast/cases/<id>/`. The agent's working directory is that folder, and everything it
produces stays there: the paper (`paper/`), downloads and replication packages (`data/`), its own scripts
(`code/`), outputs and forensic artifacts (`out/`), the field brief (`notes/`), files you hand over
(`offerings/`), and the reports. `MANDATE.md` holds the exact orders the agent received; `agent.log` holds its
raw stream.

## The event log

`events.jsonl` is append-only; each line is one event with a `kind` and a timestamp. Three writers append
under an exclusive file lock:

- the **runner** translates the agent's stream (`sicarius/streams.py`): `session`, `narrate`, `tool`,
  `tool.done`, `spawn`, `usage`, `final`, `case.opened`, `case.closed`;
- the **arsenal** MCP server, called by the agent, records structure: `station`, `intel`, `acquired`, `forge`,
  `speculum`, `viae`, `wound`, `parry`, `plea`, `verdict`;
- the **app** records your answers: `plea.answered`.

The app never talks to the agent. It polls the log and feeds new events to the director (`web/js/director.js`),
which turns each into choreography on the wall. Because the log is the only source of truth, the window can
close and reopen mid-hunt, and a finished hunt can be replayed exactly.

## Processes

`econoclast` opens the window (`app/__init__.py`). Starting a hunt calls `Api.begin`, which creates the case and
launches `python -m econoclast hunt --case <dir>` in its own session (`sicarius.launch_detached`), so the hunt
outlives the window. The runner builds the agent's command (`Hunt.command`): the doctrine as appended system
prompt (Claude) or prompt preamble (Codex), the case brief on stdin, the MCP servers (`mcp.json` for Claude,
`-c mcp_servers.*` overrides for Codex), full permissions, and for Claude a `conspirator` subagent. Calling off
a hunt sends SIGTERM to the runner, which terminates the agent's process group and closes the case as
`aborted`. If the app finds a case still marked running whose processes are gone, it marks it `interrupted`.

## The engine's packages

| Package | Role |
|---|---|
| `world.py` | the lexicon: stations, blades, verdict bands, seals |
| `case/` | the case folder, the event log, wounds and parries, the score and the seal, the Tabula |
| `arsenal/` | the MCP server and the doctrine (standing orders and per-station orders) |
| `sicarius/` | the runner: agent commands and stream parsers |
| `tesserae/` | reading papers: PDF/LaTeX/HTML, statistics extraction, sanitising, the Abacus, paper forensics, version diffs |
| `bibliotheca/` | literature search, dataset links and downloads, public data (FRED, World Bank), the code audit |
| `fabrica/` | the shared local quant workshop (a lean uv/venv Python with the econometrics stack; extras on demand) |
| `viae/` | the specification curve, McCrary, Callaway-Sant'Anna, Sun-Abraham, Goodman-Bacon, data forensics |
| `app/` | the window, the bridge API, the developer preview server, the macOS installer, and `web/` |

## The stage

`web/js/stage.js` composites a 1600x900 canvas every frame from real mosaic art: scenes as backgrounds,
figures as cut-outs anchored at their feet. The living-mosaic effects are all in that file: figures step on a
tessera grid, change pose by reshuffling 10-pixel tiles between the two frames, burst into tesserae when hit,
crack when wounded (`paintScar`), assemble out of flying tiles, and catch glints on their gold. Scene changes
turn the wall over tile by tile. `director.js` holds the layout of every wall and the choreography for every
event; `ui.js`, `tabula.js` and `prologue.js` hold the chrome, the report and the opening.
