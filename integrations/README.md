# Using Econoclast inside Claude Code & Codex

Econoclast is built to be talked to. A non-technical user says "check this paper for me" with a link,
and the agent works out what it needs, asks for anything missing in plain words, runs the whole check,
and explains the result in plain language. The `econoclast_intake` MCP tool turns a free-text request
into a short list of questions to ask; `econoclast_verify` then does everything in one call.

There are three ways to wire it up.

---

## 1. MCP server (recommended — works in both)

Exposes `econoclast_forensics`, `econoclast_review`, and `econoclast_list_attacks` as tools.

```bash
pip install "econoclast[mcp,pdf]"
```

**Claude Code:**
```bash
claude mcp add econoclast -- econoclast mcp
```

**Codex** — add to `~/.codex/config.toml` (see [`codex/config-snippet.toml`](codex/config-snippet.toml)):
```toml
[mcp_servers.econoclast]
command = "econoclast"
args = ["mcp"]
```

Now just ask: *"Use econoclast to red-team paper.pdf."* The agent calls `econoclast_forensics`
(arithmetic facts: statcheck, GRIM, p-curve, z-bunching…) and reasons over the result.

---

## 2. Claude Code plugin (slash command + skill)

One-click install via the bundled marketplace:

```text
/plugin marketplace add shoal-rat/econoclast
/plugin install econoclast@econoclast
```

Then in any Claude Code session:

```text
/econoclast path/to/paper.pdf
```

The plugin also ships a **skill** (`econoclast-review`) that triggers automatically when you ask
Claude to "referee / red-team / stress-test" an economics paper.

*Prefer not to install a plugin?* Copy [`claude-code/commands/econoclast.md`](claude-code/commands/econoclast.md)
into your project's `.claude/commands/` and [`claude-code/skills/`](claude-code/skills/) into `.claude/skills/`.

---

## 3. Codex custom prompt

Copy [`codex/prompts/econoclast.md`](codex/prompts/econoclast.md) into `~/.codex/prompts/`, then in Codex:

```text
/econoclast path/to/paper.pdf
```

---

## Or: the CLI through your subscription (no API key)

If you have either CLI installed and logged in, Econoclast can drive it as the model backend — no
separate API key:

```bash
econoclast review paper.pdf --backend claude    # uses your Claude Code login
econoclast review paper.pdf --backend codex     # uses your Codex/ChatGPT login
```

It also auto-detects: with no API key set but `claude` (or `codex`) on PATH, `econoclast review`
uses it automatically. See the main [README](../README.md#-one-click--no-api-key-setup).
