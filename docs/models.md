# Configuring the model

Econoclast is a native-LLM tool. It does not ship a model, an API client, or any offline fallback. It
runs on the intelligence of the agent you already have: it drives the `claude` (Claude Code) or
`codex` CLI as a subprocess and uses that CLI's own subscription auth. There is no API key to set. If
neither CLI is on your PATH, Econoclast stops with a clear message rather than degrading to something
weaker.

## Pick a backend

The only model setting is the backend: which of the two CLIs to drive.

| Backend | Value | Notes |
|---|---|---|
| Auto | `auto` | tries Claude Code first, then Codex (the default) |
| Claude Code | `claude` | drives the `claude` CLI |
| Codex | `codex` | drives the `codex` CLI |

Set it in `econoclast.yaml` (see [`econoclast.example.yaml`](../econoclast.example.yaml)):

```yaml
backend: auto    # auto | claude | codex
```

Or per run with the flag:

```bash
econoclast verify "paper.pdf" --backend claude
```

The flag wins over the config file. With no setting at all, the default is `auto`.

## Check what it sees

```bash
econoclast backend
```

This prints which CLIs are on your PATH and which one Econoclast will use. If neither `claude` nor
`codex` is found, it tells you to install one and log in.

## Optional overrides

A few extra keys, all optional:

```yaml
model: ""              # pass a specific model string through to the CLI ("" = the CLI's default)
backend_args: []       # extra arguments forwarded to the CLI on every call
claude_binary: claude  # path or name of the Claude Code CLI
codex_binary: codex    # path or name of the Codex CLI
request_timeout: 240   # seconds per call
```

`model` is handed straight to the chosen CLI; leave it empty to take that CLI's default. `backend_args`
is appended to every invocation, which is useful for CLI flags you always want set.

## Roles

Attacks ask the backend for a *role*: `extractor`, `attacker`, or `referee`. There is one model behind
every role, so the role only changes the temperature (light extraction runs cool, the adversarial
attacks run a little warmer, the referee sits in between). You do not configure roles separately.
