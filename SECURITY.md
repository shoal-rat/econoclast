# Security policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue. Use GitHub's
[private vulnerability reporting](https://github.com/shoal-rat/econoclast/security/advisories/new),
or email zwk@outlook.sg. You can expect an acknowledgement within a few days.

## Scope worth flagging

Econoclast runs an autonomous agent with a shell and network access on the user's machine (by default with no
permission prompts and no sandbox) and feeds it untrusted documents and web pages. The areas most worth
scrutiny are:

- **Instruction injection.** Any way for a manuscript, a dataset or a fetched web page to make the agent act
  outside its case folder or against the user. The defences are the doctrine (`arsenal/doctrine.py`), the
  reader's sanitising (`tesserae/sanitize.py`), and `permissions: guarded` (see `docs/autonomy.md`).
- **Downloads and archives** in `bibliotheca/acquire.py` (path traversal is refused; size limits apply).
- **The app bridge** (`app/api.py`): every method that touches a path must stay inside the case folder.
- **The developer preview server** (`app/devserver.py`) must bind to 127.0.0.1 only.
- **The arsenal** (`arsenal/tools.py`), which resolves agent-supplied paths and runs scripts in the workshop.
