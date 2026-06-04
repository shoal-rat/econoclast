---
description: One-time Econoclast setup: install, detect backends, and register the tool.
allowed-tools: Bash(pip:*), Bash(econoclast:*), Bash(claude:*)
---

Set up **Econoclast** for this user with as little friction as possible.

1. **Install if needed.** Check `econoclast version`. If it's missing, install it:
   ```bash
   pip install "econoclast[all] @ git+https://github.com/shoal-rat/econoclast"
   ```

2. **Detect the environment** and show the user what's available:
   ```bash
   econoclast setup --yes --no-mcp -o econoclast.yaml
   ```
   (This prints whether the Claude Code or Codex CLI is on PATH and writes a default config.)

3. **Ask the user at most three short questions**, then re-run setup with their answers:
   - *Backend?* (default: the recommended one. Econoclast runs on your Claude Code or Codex CLI, so there is no API key.)
   - *Blind author identity during review?* (default **yes**, reduces prestige bias)
   - *Any folder of your own papers to ground reviews against?* (optional)

   Then run, filling in their choices:
   ```bash
   econoclast setup --yes --backend <auto|claude|codex> --mcp [--no-blind] [--no-literature] [--corpus <dir>]
   ```
   The `--mcp` flag registers Econoclast as a tool inside Claude Code / Codex. Setup also installs the
   Playwright browser MCP so the agent can get past blocked downloads; add `--no-browser-mcp` to skip it.

4. **Confirm** and tell the user the payoff in one line:
   > Setup done. From now on just say: **"review &lt;file path or paper URL&gt;"** and I'll run Econoclast on it.

Keep it conversational and brief; the user should not need to learn any commands.
