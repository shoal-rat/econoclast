"""Unleash the Sicarius: run Claude Code or Codex as a full agent on one case.

The hunt launches the agent CLI inside the case folder with:

- the standing orders (the doctrine) and the case brief;
- full autonomy by default: no permission prompts, no sandbox, network on;
- Econoclast's arsenal MCP server bound to this case, the Playwright MCP (a real
  browser for blocked downloads), and any extra MCP servers from the config, on top of
  the user's own MCP servers;
- for Claude Code, a ``conspirator`` subagent it may fan out to.

It reads the agent's JSON stream line by line and appends every event to the case log,
which is what the app's stage animates. Closing the hunt always leaves a status, and a
report whenever any wound was recorded.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time

from econoclast.arsenal.doctrine import CONSPIRATOR_PROMPT, brief, doctrine
from econoclast.case.store import Case, home
from econoclast.config import Settings
from econoclast.log import get_logger
from econoclast.sicarius.streams import ClaudeStream, CodexStream

log = get_logger("sicarius")


class NoAgent(RuntimeError):
    """Neither Claude Code nor Codex is installed."""


class Hunt:
    def __init__(self, case: Case, settings: Settings | None = None) -> None:
        self.case = case
        self.settings = settings or Settings.load()
        meta = case.meta()
        picked = self.settings.pick_backend(meta.get("backend") or None)
        if picked is None:
            raise NoAgent("Econoclast runs on Claude Code or Codex, and neither `claude` nor `codex` was "
                          "found. Install one, log in, and try again.")
        self.label, self.binary = picked
        self.proc: subprocess.Popen | None = None
        self.aborted = False
        self.thread: threading.Thread | None = None

    # -------------------------------------------------------------- wiring
    def _mcp_servers(self) -> dict[str, dict]:
        servers: dict[str, dict] = {
            "arsenal": {
                "command": sys.executable,
                "args": ["-m", "econoclast", "arsenal", "--case", str(self.case.root)],
                "env": {"ECONOCLAST_HOME": str(home()), "PYTHONUNBUFFERED": "1"},
            }
        }
        npx = shutil.which("npx")
        if self.settings.browser_mcp and npx:
            servers["playwright"] = {
                "command": npx,
                "args": ["-y", "@playwright/mcp@latest", "--headless",
                         "--output-dir", str(self.case.path("out", "browser"))],
            }
        servers.update(self.settings.extra_mcp or {})
        return servers

    def _texts(self) -> tuple[str, str]:
        meta = self.case.meta()
        lang = meta.get("lang", "en")
        offerings = sorted(p.name for p in self.case.path("offerings").glob("*")
                           if p.is_file() and not p.name.endswith(".json"))
        subagents = self.label == "claude" and self.settings.subagents
        doc = doctrine(lang=lang, minutes=self.settings.time_limit_min, has_subagents=subagents)
        br = brief(paper=meta.get("paper_input", ""), data=meta.get("data_input", ""),
                   claim=meta.get("claim", ""), depth=meta.get("depth", "thorough"), offerings=offerings)
        self.case.path("MANDATE.md").write_text(doc + "\n\n# This case\n\n" + br + "\n", encoding="utf-8")
        return doc, br

    def command(self) -> tuple[list[str], str, dict[str, str]]:
        doc, br = self._texts()
        servers = self._mcp_servers()
        env = {**os.environ, "ECONOCLAST_HOME": str(home()), "ECONOCLAST_CASE": str(self.case.root)}
        full = self.settings.permissions == "full"
        from econoclast import fabrica

        workshop = str(fabrica.root())
        if self.label == "claude":
            mcp_path = self.case.path("mcp.json")
            mcp_path.write_text(json.dumps({"mcpServers": servers}, indent=1), encoding="utf-8")
            cmd = [self.binary, "-p", "--output-format", "stream-json", "--verbose",
                   "--append-system-prompt", doc, "--mcp-config", str(mcp_path), "--add-dir", workshop]
            if full:
                cmd += ["--permission-mode", "bypassPermissions"]
            else:
                allowed = ["Read", "Glob", "Grep", "Write", "Edit", "WebFetch", "WebSearch", "Task", "TodoWrite",
                           "mcp__arsenal", "mcp__playwright", "Bash(curl:*)", "Bash(wget:*)", "Bash(unzip:*)",
                           "Bash(ls:*)", "Bash(head:*)", "Bash(file:*)", "Bash(python3:*)", "Bash(Rscript:*)",
                           f"Bash({fabrica.python_path()}:*)"]
                cmd += ["--permission-mode", "acceptEdits", "--allowedTools", ",".join(allowed)]
            if self.settings.subagents:
                cmd += ["--agents", json.dumps({"conspirator": {
                    "description": "A second assassin for one blade or one data hunt on this paper; records "
                                   "wounds and parries with the arsenal tools.",
                    "prompt": CONSPIRATOR_PROMPT}})]
            if self.settings.model:
                cmd += ["--model", self.settings.model]
            cmd += list(self.settings.backend_args)
            env.update({"MCP_TOOL_TIMEOUT": str(2 * 3600 * 1000), "MCP_TIMEOUT": "120000",
                        "BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000"})
            return cmd, br, env

        cmd = [self.binary, "exec", "--json", "--skip-git-repo-check", "-C", str(self.case.root),
               "--add-dir", workshop]
        if full:
            cmd += ["--dangerously-bypass-approvals-and-sandbox"]
        else:
            cmd += ["-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true",
                    "-c", 'approval_policy="never"']
        cmd += ["-c", 'web_search="live"']
        for name, spec in servers.items():
            key = f"mcp_servers.{name}"
            cmd += ["-c", f"{key}.command={json.dumps(spec['command'])}",
                    "-c", f"{key}.args={json.dumps(spec.get('args', []))}",
                    "-c", f"{key}.tool_timeout_sec=7200", "-c", f"{key}.startup_timeout_sec=120"]
            for k, v in (spec.get("env") or {}).items():
                cmd += ["-c", f"{key}.env.{k}={json.dumps(v)}"]
        if self.settings.model:
            cmd += ["-m", self.settings.model]
        cmd += list(self.settings.backend_args)
        cmd += ["-"]
        return cmd, doc + "\n\n# This case\n\n" + br, env

    # ---------------------------------------------------------------- run
    def start(self) -> threading.Thread:
        self.thread = threading.Thread(target=self.run, name=f"hunt-{self.case.id}", daemon=True)
        self.thread.start()
        return self.thread

    def run(self) -> str:
        case = self.case
        cmd, stdin_text, env = self.command()
        meta = case.update_meta(status="running", backend_used=self.label, started=time.time())
        case.emit("case.opened", backend=self.label, paper=meta.get("paper_input"), lang=meta.get("lang"),
                  depth=meta.get("depth"), claim=meta.get("claim"))
        parser = ClaudeStream() if self.label == "claude" else CodexStream()
        raw = open(case.path("agent.log"), "a", encoding="utf-8")  # noqa: SIM115
        err_tail: list[str] = []
        try:
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(case.root), env=env, text=True, encoding="utf-8", errors="replace", bufsize=1,
                start_new_session=True)
        except OSError as exc:
            case.update_meta(status="failed", error=str(exc))
            case.emit("case.closed", status="failed", error=str(exc))
            raw.close()
            return "failed"
        case.update_meta(pid=self.proc.pid)
        threading.Thread(target=self._feed_stdin, args=(stdin_text,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(err_tail,), daemon=True).start()
        deadline = time.time() + self.settings.time_limit_min * 60 * 1.5
        threading.Thread(target=self._watchdog, args=(deadline,), daemon=True).start()

        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            raw.write(line)
            raw.flush()
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            for ev in parser.feed(obj):
                kind = ev.pop("kind")
                if kind == "session" and ev.get("session_id"):
                    case.update_meta(session_id=ev["session_id"], model=ev.get("model"))
                case.emit(kind, **ev)
        rc = self.proc.wait()
        raw.close()
        return self._close(rc, err_tail)

    def _close(self, rc: int, err_tail: list[str]) -> str:
        case = self.case
        verdict = case.verdict()
        if self.aborted:
            status = "aborted"
        elif verdict is not None:
            status = "done"
        else:
            status = "failed"
        error = ""
        if status == "failed":
            error = "\n".join(err_tail[-12:])[-1500:] or f"the agent exited with code {rc} before the verdict"
            if case.wounds():  # leave a provisional report behind
                from econoclast.case.tabula import write_tabula

                write_tabula(case)
        case.update_meta(status=status, ended=time.time(), returncode=rc, error=error or None, waiting_plea=None)
        if self.settings.pack_after:
            try:
                from econoclast.case.vault import pack

                pack(case)
            except Exception as exc:  # noqa: BLE001 - packing must never lose the verdict
                log.warning("could not pack %s: %s", case.id, exc)
        case.emit("case.closed", status=status, returncode=rc, error=error[-600:] if error else None)
        log.info("hunt %s closed: %s (rc=%s)", case.id, status, rc)
        return status

    def _feed_stdin(self, text: str) -> None:
        try:
            assert self.proc and self.proc.stdin
            self.proc.stdin.write(text)
            self.proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    def _drain_stderr(self, tail: list[str]) -> None:
        assert self.proc and self.proc.stderr
        with open(self.case.path("agent.stderr.log"), "a", encoding="utf-8") as fh:
            for line in self.proc.stderr:
                fh.write(line)
                tail.append(line.rstrip())
                del tail[:-40]

    def _watchdog(self, deadline: float) -> None:
        while self.proc and self.proc.poll() is None:
            if time.time() > deadline:
                self.case.emit("narrate", who="econoclast", text="Time limit reached; calling off the hunt.")
                self.abort()
                return
            time.sleep(5)

    def abort(self) -> None:
        self.aborted = True
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, AttributeError):
                self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError, AttributeError):
                    self.proc.kill()


def reap_orphans() -> list[str]:
    """Mark cases left 'running' by a previous app session (their agent is gone) as interrupted."""
    from econoclast.case.store import cases_root

    fixed = []
    for root in cases_root().iterdir():
        case = Case(root)
        meta = case.meta()
        if meta.get("status") != "running":
            continue
        if not any(_alive(meta.get(k)) for k in ("runner_pid", "pid")):
            case.update_meta(status="interrupted", waiting_plea=None)
            case.emit("case.closed", status="interrupted")
            fixed.append(case.id)
    return fixed


def _alive(pid) -> bool:  # noqa: ANN001
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def launch_detached(case: Case) -> int:
    """Run the hunt in its own process so it outlives the app window; returns the runner pid."""
    log_path = case.path("runner.log")
    with open(log_path, "a", encoding="utf-8") as fh:
        proc = subprocess.Popen([sys.executable, "-m", "econoclast", "hunt", "--case", str(case.root)],
                                stdin=subprocess.DEVNULL, stdout=fh, stderr=fh, cwd=str(case.root),
                                start_new_session=True, env={**os.environ, "ECONOCLAST_HOME": str(home())})
    case.update_meta(runner_pid=proc.pid, status="starting")
    return proc.pid


def stop(case: Case) -> bool:
    """Call off a detached hunt (the runner turns SIGTERM into a clean abort)."""
    meta = case.meta()
    pid = meta.get("runner_pid")
    if _alive(pid):
        try:
            os.kill(int(pid), signal.SIGTERM)
            return True
        except OSError:
            pass
    if _alive(meta.get("pid")):
        try:
            os.killpg(int(meta["pid"]), signal.SIGTERM)
        except OSError:
            pass
    if meta.get("status") in ("running", "starting"):
        case.update_meta(status="aborted")
        case.emit("case.closed", status="aborted")
    return False
