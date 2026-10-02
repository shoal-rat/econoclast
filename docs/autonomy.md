# Autonomy and safety

Econoclast gives its agent real power on purpose. A referee who has to ask permission before every download,
every `pip install` and every regression never finishes; the point is to come back to a verdict.

## What the agent can do by default

`permissions: full` (the default) runs Claude Code with `--permission-mode bypassPermissions` and Codex with
`--dangerously-bypass-approvals-and-sandbox`. The agent can:

- browse and download from the internet, including through a real browser (the Playwright MCP) when a site
  blocks plain downloads;
- run shell commands, install Python packages into the workshop, and run R if you have it;
- read and write files; its standing orders keep it inside its case folder and the shared workshop
  (`~/.econoclast/fabrica`);
- use the arsenal and any other MCP servers you have configured;
- (Claude Code) send subagents to work blades in parallel.

The hunt has a time budget (`time_limit_min`, 90 by default; the runner calls it off at one and a half times
that). You can call it off from the app at any moment.

## What keeps it honest

- **The paper is data, never instructions.** The doctrine says so, the reader strips invisible characters,
  and text addressed to AI reviewers is reported as a wound rather than obeyed.
- **The orders are visible.** `MANDATE.md` in each case folder is exactly what the agent was told, and
  `agent.log` is everything it did.
- **Every claim is checkable.** Text wounds are quote-verified; computation wounds point at scripts and
  outputs in the case folder that you can rerun.

## A shorter leash

```yaml
# ~/.econoclast/config.yaml
permissions: guarded
browser_mcp: false
```

`guarded` runs Claude Code in `acceptEdits` mode with an allow-list (file tools, web fetch and search, the
arsenal, downloads, Python and R) and Codex in its `workspace-write` sandbox with network access. Anything else
the agent tries is refused instead of prompting. Hunts are slower and fail more often on hostile sites; the
verdicts are the same kind.

## Your data

Nothing leaves your machine except what the agent itself fetches and what your agent's provider receives as
part of the conversation (the paper's text and the agent's working notes). Cases live in `~/.econoclast/cases/`
until you delete them from the archive.
