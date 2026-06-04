#!/usr/bin/env bash
# One-command install for Econoclast.
# Installs the package, then detects your backend and registers the agent tool.
set -euo pipefail

PKG='econoclast[all] @ git+https://github.com/shoal-rat/econoclast'

echo "Installing Econoclast..."
if command -v pipx >/dev/null 2>&1; then
  pipx install "$PKG" || pip install "$PKG"
else
  pip install "$PKG"
fi

echo
echo "Detecting your setup (API keys, Claude Code, Codex) and writing config..."
econoclast setup --yes || true

cat <<'EOF'

Done.

Use it from the terminal:
    econoclast verify <paper path or URL>

Or inside Claude Code / Codex, just say:
    verify <paper link or file>

No API key needed if you have a Claude Code or Codex subscription.
EOF
