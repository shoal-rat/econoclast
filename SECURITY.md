# Security policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue. Use GitHub's
[private vulnerability reporting](https://github.com/shoal-rat/econoclast/security/advisories/new),
or email zwk@outlook.sg. You can expect an acknowledgement within a few days.

## Scope worth flagging

Econoclast reads untrusted documents and can fetch remote datasets, so the areas most worth scrutiny are:

- Manuscript parsing and the prompt-injection defenses in `ingest/sanitize.py`.
- Dataset download and unzip in `replication/acquire.py` (path traversal, zip bombs, size limits).
- The replication-package runner in `replication/runner.py`, which executes untrusted author code. It
  is off by default, is not a real sandbox, and should only be used inside a container or a throwaway
  VM. Treat any way to trigger it without the explicit opt-in as a vulnerability.
- The subprocess LLM backends (`llm/providers/cli.py`), which shell out to local CLIs.
