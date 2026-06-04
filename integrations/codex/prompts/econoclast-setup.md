Set up Econoclast for me with minimal friction.

1. If `econoclast version` fails, install it: `pip install "econoclast[all] @ git+https://github.com/shoal-rat/econoclast"`.
2. Run `econoclast setup --yes --no-mcp -o econoclast.yaml` and show me the detected backends (Claude Code CLI / Codex CLI). Econoclast runs on whichever of those you already have, using its subscription; there is no API key.
3. Ask me at most three short questions: which backend (default = recommended, auto-detected), blind author identity during review (default yes), and an optional folder of my own papers to ground reviews.
4. Re-run with my answers: `econoclast setup --yes --backend <auto|claude|codex> --mcp [--no-blind] [--corpus <dir>]`. The `--mcp` flag registers Econoclast as a Codex tool, and setup also installs the Playwright browser MCP so you can get past blocked downloads (`--no-browser-mcp` to skip).
5. Confirm, then tell me in one line: from now on I can just say "review <file path or paper URL>" and you'll run Econoclast on it.

Be conversational and brief. I should not have to learn any commands.
