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

A hunt survives a bad network: when the agent's run ends without a verdict the runner
classifies why, waits out a dropped connection or an overloaded service and resumes the
same agent session (``--resume`` / ``codex exec resume``), and nudges an agent that simply
stopped early. Anything it should not retry on its own (a usage limit, a login, a refusal,
a crash) closes the case as resumable, and ``run(resume="manual")`` takes it up again.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

from econoclast.arsenal.doctrine import CONSPIRATOR_PROMPT, brief, doctrine, resume_brief
from econoclast.case.store import Case, home
from econoclast.config import Settings
from econoclast.log import get_logger
from econoclast.sicarius.region import RegionGuard, lookup_country, region_name
from econoclast.sicarius.streams import ClaudeStream, CodexStream

log = get_logger("sicarius")


class NoAgent(RuntimeError):
    """Neither Claude Code nor Codex is installed."""


# Why an agent run ended without a verdict, checked in this order against the error the agent reported.
# Connection trouble comes before "refused" (a dead local proxy says "connection refused"), and a rate
# limit is network weather, while a usage limit waits for the traveller.
_FAILURES = (
    ("auth", re.compile(r"invalid api key|/login|not logged in|log ?in again|authenticat|unauthori[sz]ed|"
                        r"\b401\b|oauth token", re.I)),
    ("limit", re.compile(r"usage limit|usage_limit|hit your (?:usage )?limit|\d+-hour limit|weekly limit|"
                         r"credit balance|out of credits|quota exceeded|insufficient (?:credit|quota)", re.I)),
    ("network", re.compile(r"connection (?:error|reset|refused|closed)|econnreset|econnrefused|etimedout|enotfound|"
                           r"eai_again|socket hang up|fetch failed|network (?:error|is unreachable)|"
                           r"unable to connect|tcp connect error|os error 6[01]|"
                           r"request timed out|operation timed out|overloaded|\b(?:429|500|502|503|504|529)\b|"
                           r"rate.?limit|too many requests|internal server error|bad gateway|service unavailable|"
                           r"stream disconnected|error sending request|temporarily unavailable", re.I)),
    ("refused", re.compile(r"usage policy|unable to respond to this request|declined to|refus(?:al|e to)", re.I)),
    ("background", re.compile(r"background tasks still running", re.I)),
)


def classify(text: str, rc: int) -> str:
    """network: retried on its own after a wait. unfinished/background: nudged once or twice.
    auth, refused, limit, crash: left for the traveller (the case stays resumable)."""
    for kind, pattern in _FAILURES:
        if pattern.search(text or ""):
            return kind
    return "unfinished" if rc == 0 else "crash"


class Hunt:
    def __init__(self, case: Case, settings: Settings | None = None) -> None:
        self.case = case
        self.settings = settings or Settings.load()
        meta = case.meta()
        # A resumed hunt goes back to the agent that holds its session.
        picked = self.settings.pick_backend(meta.get("backend_used") or meta.get("backend") or None)
        if picked is None:
            raise NoAgent("Econoclast runs on Claude Code or Codex, and neither `claude` nor `codex` was "
                          "found. Install one, log in, and try again.")
        self.label, self.binary = picked
        self.proc: subprocess.Popen | None = None
        self.aborted = False
        self.thread: threading.Thread | None = None
        self._stopped = threading.Event()
        self.guard = RegionGuard(self.settings.blocked_regions, lookup=lambda: lookup_country(backend=self.label)) \
            if self.settings.region_guard and self.settings.blocked_regions else None
        self._frozen_since: float | None = None  # the region guard has the agent paused
        self._frozen_total = 0.0
        self._deadline = float("inf")
        self._timed_out = False

    # -------------------------------------------------------------- wiring
    def _mcp_servers(self) -> dict[str, dict]:
        arsenal = _self_cmd("arsenal", "--case", str(self.case.root))
        servers: dict[str, dict] = {
            "arsenal": {
                "command": arsenal[0],
                "args": arsenal[1:],
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

    def command(self, *, session: str | None = None, prompt: str | None = None) -> tuple[list[str], str, dict[str, str]]:
        """The agent command, its stdin and environment. ``session`` resumes that agent session;
        ``prompt`` (a resume brief) replaces the opening brief."""
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
            if session:
                cmd += ["--resume", session]
            cmd += list(self.settings.backend_args)
            env.update({"MCP_TOOL_TIMEOUT": str(2 * 3600 * 1000), "MCP_TIMEOUT": "120000",
                        "BASH_DEFAULT_TIMEOUT_MS": "600000", "BASH_MAX_TIMEOUT_MS": "3600000",
                        # Headless Claude Code wakes the Sicarius when a background conspirator reports, but
                        # only waits 10 minutes for one by default; a long data hunt needs the whole budget.
                        "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": str(self._budget_ms())})
            if session:
                return cmd, prompt or br, env
            return cmd, br + (f"\n\n{prompt}" if prompt else ""), env

        if session:  # `codex exec resume` keeps the session's folder; it takes no -C/--add-dir/-s
            cmd = [self.binary, "exec", "resume", session, "--json", "--skip-git-repo-check"]
        else:
            cmd = [self.binary, "exec", "--json", "--skip-git-repo-check", "-C", str(self.case.root),
                   "--add-dir", workshop]
        if full:
            cmd += ["--dangerously-bypass-approvals-and-sandbox"]
        elif session:
            cmd += ["-c", 'sandbox_mode="workspace-write"', "-c", "sandbox_workspace_write.network_access=true",
                    "-c", f"sandbox_workspace_write.writable_roots={json.dumps([workshop])}",
                    "-c", 'approval_policy="never"']
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
        if session:
            return cmd, prompt or br, env
        return cmd, doc + "\n\n# This case\n\n" + br + (f"\n\n{prompt}" if prompt else ""), env

    def _budget_ms(self) -> int:
        return int(self.settings.time_limit_min * 60 * 1000 * 1.5)

    # ---------------------------------------------------------------- run
    def start(self) -> threading.Thread:
        self.thread = threading.Thread(target=self.run, name=f"hunt-{self.case.id}", daemon=True)
        self.thread.start()
        return self.thread

    def run(self, *, resume: str = "") -> str:
        """Run the hunt to its verdict. ``resume`` takes up a stopped hunt again ("manual": the traveller
        pressed Resume); the runner also resumes by itself after a dropped connection. One run has one time
        budget (time held by the region guard is given back); a manual resume starts a new one."""
        case = self.case
        meta = case.meta()
        # a case from before resumes existed has no counter: its first run was attempt 1
        attempt = int(meta.get("attempt") or (1 if meta.get("started") else 0)) + 1
        self._deadline = time.time() + self._budget_ms() / 1000
        self._frozen_total, self._timed_out = 0.0, False
        prompt: str | None = None
        session: str | None = None
        if resume:
            restored = self._unpack()
            session = case.meta().get("session_id")
            case.update_meta(status="running", backend_used=self.label, attempt=attempt, failure=None, error=None,
                             resumable=None, paused=None)
            case.emit("case.resumed", reason=resume, attempt=attempt, backend=self.label, restored=restored)
            prompt = resume_brief(case, reason=resume, backend=self.label)
        else:
            meta = case.update_meta(status="running", backend_used=self.label, started=time.time(), attempt=attempt)
            case.emit("case.opened", backend=self.label, paper=meta.get("paper_input"), lang=meta.get("lang"),
                      depth=meta.get("depth"), claim=meta.get("claim"))
        retries, nudges, fresh = 0, 0, False
        backoff = list(self.settings.resume_backoff) or [30]
        while True:
            rc, err_tail, failure, announced, errors = self._attempt(session, prompt)
            if self.aborted or failure is None:
                break
            if session and announced is None and rc != 0 and not fresh:
                failure = "lost_session"  # the agent no longer has that session: start over from the case files
                session, fresh = None, True
            elif time.time() > self._deadline + self._frozen_total:
                break  # out of time: leave it to the traveller's Resume
            elif failure == "network" and retries < self.settings.auto_resume:
                wait = backoff[min(retries, len(backoff) - 1)]
                retries += 1
                case.emit("retry.wait", seconds=wait, reason=failure, attempt=attempt + 1)
                if self._stopped.wait(wait):
                    break
            elif failure in ("unfinished", "background") and nudges < 2:
                nudges += 1
            else:
                break
            if self._stopped.is_set():
                break
            attempt += 1
            session = session if failure == "lost_session" else (case.meta().get("session_id") or session)
            case.update_meta(attempt=attempt)
            case.emit("case.resumed", reason=failure, attempt=attempt, backend=self.label, restored=0)
            prompt = resume_brief(case, reason=failure, backend=self.label)
        return self._close(rc, err_tail, failure, errors)

    def _attempt(self, session: str | None,
                 prompt: str | None) -> tuple[int, list[str], str | None, str | None, list[str]]:
        """One run of the agent CLI. Returns its exit code, the stderr tail, why it ended without a verdict
        (None when the verdict is in), the session it announced (None if none), and its error messages."""
        case = self.case
        if not self._await_safe_region():
            return 143, [], "aborted", None, []
        cmd, stdin_text, env = self.command(session=session, prompt=prompt)
        if self._stopped.is_set():  # called off while the region was checked or the brief was written
            return 143, [], "aborted", None, []
        parser = ClaudeStream() if self.label == "claude" else CodexStream()
        raw = open(case.path("agent.log"), "a", encoding="utf-8")  # noqa: SIM115
        err_tail: list[str] = []
        errors: list[str] = []
        announced: str | None = None
        try:
            proc = self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(case.root), env=env, text=True, encoding="utf-8", errors="replace", bufsize=1,
                start_new_session=True)
        except OSError as exc:
            raw.close()
            return 127, [str(exc)], "crash", None, []
        if self._stopped.is_set():  # called off in the instant the agent started
            self.abort()
        case.update_meta(pid=proc.pid)
        done = threading.Event()  # ends this attempt's watchdog and region watch
        threading.Thread(target=self._feed_stdin, args=(stdin_text,), daemon=True).start()
        threading.Thread(target=self._drain_stderr, args=(err_tail,), daemon=True).start()
        threading.Thread(target=self._watchdog, args=(proc, done), daemon=True).start()
        if self.guard:
            threading.Thread(target=self._region_watch, args=(proc, done), daemon=True).start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
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
                        announced = ev["session_id"]
                        if session and announced != session:
                            log.warning("hunt %s asked for session %s and got %s", case.id, session, announced)
                        case.update_meta(session_id=announced, model=ev.get("model"))
                    elif kind == "agent.error" and ev.get("text"):
                        errors.append(ev["text"])
                    case.emit(kind, **ev)
            rc = proc.wait()
        finally:
            done.set()
            raw.close()
        time.sleep(0.05)  # let the stderr reader catch the last lines
        if case.verdict() is not None:
            return rc, err_tail, None, announced, errors
        text = "\n".join(errors[-3:] + err_tail[-15:])
        return rc, err_tail, classify(text, rc), announced, errors

    def _unpack(self) -> int:
        """A closed hunt packed its data into the vault; a resumed one needs it back."""
        try:
            from econoclast.case.vault import unpack

            return unpack(self.case)
        except Exception as exc:  # noqa: BLE001 - the agent can still re-download what it needs
            log.warning("could not unpack %s: %s", self.case.id, exc)
            return 0

    def _close(self, rc: int, err_tail: list[str], failure: str | None = None,
               errors: list[str] | None = None) -> str:
        case = self.case
        verdict = case.verdict()
        if verdict is not None:  # the verdict is in: whatever stopped the agent afterwards does not matter
            status, failure = "done", None
        elif self._timed_out:
            status, failure = "failed", "time_limit"
        elif self.aborted:
            status, failure = "aborted", "aborted"
        else:
            status, failure = "failed", failure or "crash"
        error = ""
        if status == "failed":
            error = "\n".join(errors[-2:]) if errors else _tail_lines(err_tail, 1500)
            error = error or f"the agent exited with code {rc} before the verdict"
            if case.wounds():  # leave a provisional report behind
                from econoclast.case.tabula import write_tabula

                write_tabula(case)
        ended = time.time()
        if self.settings.pack_after:
            try:
                from econoclast.case.vault import pack

                pack(case)
            except Exception as exc:  # noqa: BLE001 - packing must never lose the verdict
                log.warning("could not pack %s: %s", case.id, exc)
        resumable = verdict is None
        case.emit("case.closed", status=status, returncode=rc, error=error[-600:] if error else None,
                  failure=failure, resumable=resumable)
        # Last: the window stops polling once the status is final and no events are left, so the final
        # status must never be visible before case.closed is (packing a big vault takes a while).
        case.update_meta(status=status, ended=ended, returncode=rc, error=error or None, waiting_plea=None,
                         failure=failure, resumable=resumable, paused=None)
        log.info("hunt %s closed: %s (rc=%s, %s)", case.id, status, rc, failure)
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

    # ---------------------------------------------------------- the region guard
    def _check_region(self) -> tuple[bool, str | None]:
        assert self.guard is not None
        try:
            return self.guard.check()
        except Exception as exc:  # noqa: BLE001 - a broken lookup counts as an unverified region
            log.warning("region check failed: %s", exc)
            return False, None

    def _await_safe_region(self) -> bool:
        """Before an agent run: hold while the connection is in a blocked region. False if called off."""
        if not self.guard:
            return not self._stopped.is_set()
        safe, code = self._check_region()
        if not safe:
            self._paused(code, during=False)
            while not safe:
                if self._stopped.wait(self.settings.region_check_s):
                    return False
                safe, code = self._check_region()
        if self.case.meta().get("paused"):  # a pause from before (or from the last attempt) has lifted
            self._cleared(code)
        return not self._stopped.is_set()

    def _region_watch(self, proc: subprocess.Popen, done: threading.Event) -> None:
        """During one agent run: freeze its whole process group while the connection is in a blocked region."""
        frozen_since: float | None = None
        try:
            while not done.wait(self.settings.region_check_s):
                if proc.poll() is not None:
                    break
                safe, code = self._check_region()
                if done.is_set() or proc.poll() is not None:
                    break  # the agent finished while the lookup ran: nothing to pause any more
                if not safe and frozen_since is None:
                    self._signal_group(proc, signal.SIGSTOP)
                    frozen_since = self._frozen_since = time.time()
                    self._paused(code, during=True)
                elif safe and frozen_since is not None:
                    self._signal_group(proc, signal.SIGCONT)
                    self._frozen_total += time.time() - frozen_since
                    frozen_since = self._frozen_since = None
                    self._cleared(code)
        finally:
            if frozen_since is not None:  # never leave a process frozen behind
                self._frozen_total += time.time() - frozen_since
                self._frozen_since = None
                self._signal_group(proc, signal.SIGCONT)

    @staticmethod
    def _signal_group(proc: subprocess.Popen, sig: int) -> None:
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass

    def _paused(self, code: str | None, *, during: bool) -> None:
        self.case.update_meta(paused="region", region=code)
        self.case.emit("region.paused", region=code, name=region_name(code), during=during)
        log.warning("hunt %s paused: connection in %s", self.case.id, region_name(code))

    def _cleared(self, code: str | None) -> None:
        self.case.update_meta(paused=None, region=code)
        self.case.emit("region.cleared", region=code, name=region_name(code))

    def _watchdog(self, proc: subprocess.Popen, done: threading.Event) -> None:
        """The run's time budget, for this attempt's process only. Time held by the region guard is given back."""
        while not done.wait(2):
            if proc.poll() is not None:
                return
            if self._frozen_since is not None:
                continue
            if time.time() > self._deadline + self._frozen_total:
                self._timed_out = True
                self.case.emit("narrate", who="econoclast", text="Time limit reached; calling off the hunt.")
                self.abort()
                return

    def abort(self) -> None:
        self.aborted = True
        self._stopped.set()  # ends a wait for the network or for a safe region, and keeps new agents from starting
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                os.killpg(self.proc.pid, signal.SIGCONT)  # a frozen agent has to wake up to exit cleanly
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
        status = meta.get("status")
        if status not in ("running", "starting"):
            continue
        if any(_alive(meta.get(k)) for k in ("runner_pid", "pid")):
            continue
        if status == "starting" and not meta.get("runner_pid") and time.time() - (meta.get("claimed") or 0) < 60:
            continue  # claimed by a Resume a moment ago; its runner is about to start
        case.emit("case.closed", status="interrupted", failure="interrupted", resumable=case.verdict() is None)
        case.update_meta(status="interrupted", waiting_plea=None, failure="interrupted",
                         resumable=case.verdict() is None, paused=None)
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


def _tail_lines(lines: list[str], limit: int) -> str:
    """The last lines that fit in ``limit`` characters, cut on line boundaries."""
    out: list[str] = []
    size = 0
    for line in reversed([x for x in lines if x.strip()]):
        if size + len(line) + 1 > limit:
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(reversed(out))


def _self_cmd(*args: str) -> list[str]:
    """Start more of Econoclast on the interpreter running now. Inside the macOS app bundle, pin isolation
    in the arguments too (no user site-packages, no bytecode writes into the signed bundle, no cwd on the
    path): an agent host may hand its MCP servers only an allowlisted environment."""
    flags = ["-s", "-B", "-P"] if os.environ.get("ECONOCLAST_BUNDLE") else []
    return [sys.executable, *flags, "-m", "econoclast", *args]


def launch_detached(case: Case, *, resume: bool = False) -> int:
    """Run the hunt in its own process so it outlives the app window; returns the runner pid.
    ``resume`` takes up a stopped hunt where it ended."""
    log_path = case.path("runner.log")
    args = ["hunt", "--case", str(case.root)] + (["--resume"] if resume else [])
    with open(log_path, "a", encoding="utf-8") as fh:
        proc = subprocess.Popen(_self_cmd(*args),
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
        case.emit("case.closed", status="aborted")
        case.update_meta(status="aborted")
    return False
