"""Subprocess-backed providers that drive a local AI CLI.

These let a user run Econoclast's LLM attacks through **Claude Code** (`claude`)
or **Codex** (`codex`) with **no separate API key** — the CLI's own
subscription auth is used. They are slower and carry the CLI's own system-prompt
overhead, but they make Econoclast "one-stop": if you already have one of these
agents installed and logged in, the adversarial review just works.

We invoke each CLI in its non-interactive / headless mode, pass the prompt on
stdin, and capture the final message.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage
from econoclast.logging import get_logger

log = get_logger("llm.cli")


def resolve_binary(name: str) -> str | None:
    """Full path to a CLI (handles Windows .cmd/.exe shims), or None."""
    return shutil.which(name)


def _messages_to_prompt(messages: list[Message]) -> tuple[str, str]:
    """Split into (system_text, user_text)."""
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    convo = [m for m in messages if m.role != "system"]
    if len(convo) == 1:
        user = convo[0].content
    else:
        user = "\n\n".join(
            (m.content if m.role == "user" else f"[{m.role}]\n{m.content}") for m in convo
        )
    return system, user or "(no input)"


# --------------------------------------------------------------------------- #
# Claude Code
# --------------------------------------------------------------------------- #
class ClaudeCodeProvider(LLMProvider):
    name = "claude_cli"

    def __init__(self, *, binary: str = "claude", extra_args: list[str] | None = None) -> None:
        self.binary = binary or "claude"
        self.extra_args = extra_args or []

    def available(self) -> bool:
        return resolve_binary(self.binary) is not None

    def complete(
        self,
        messages: list[Message],
        *,
        model: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: str | None = None,
        stop: list[str] | None = None,
        timeout: float = 180.0,
    ) -> LLMResponse:
        exe = resolve_binary(self.binary)
        if exe is None:
            raise LLMError(f"'{self.binary}' (Claude Code) is not on PATH. Install it or set a different backend.")
        system, user = _messages_to_prompt(messages)
        cmd = [exe, "-p", "--output-format", "json"]
        if model and model not in ("default", ""):
            cmd += ["--model", model]
        if system:
            cmd += ["--append-system-prompt", system]
        cmd += self.extra_args
        out = _run(cmd, user, timeout, "claude")
        return _parse_claude(out, model, self.name)

    def run_task(self, prompt: str, *, work_dir: str, timeout: float = 300.0,
                 allow: str = "Bash,Read,Edit,Write,WebFetch,WebSearch") -> str:
        """Run an action task with tools enabled, non-interactively, inside work_dir.

        Unlike :meth:`complete` (read-only reasoning), this lets the agent act: run
        shell commands, fetch the web, drive a browser MCP if one is configured, and
        write files. The listed tools are pre-approved so nothing prompts.
        """
        exe = resolve_binary(self.binary)
        if exe is None:
            raise LLMError(f"'{self.binary}' (Claude Code) is not on PATH.")
        cmd = [exe, "-p", "--output-format", "json", "--allowedTools", allow]
        cmd += self.extra_args
        proc = _run_raw(cmd, prompt, timeout, cwd=work_dir)
        try:
            return _parse_claude(proc.stdout or "", "", self.name).text
        except LLMError:
            return (proc.stdout or "") + (proc.stderr or "")


def _parse_claude(stdout: str, model: str, name: str) -> LLMResponse:
    try:
        data = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else {}
    except (json.JSONDecodeError, IndexError):
        from econoclast.llm.base import extract_json

        data = extract_json(stdout) or {}
    if not data:
        raise LLMError(f"Could not parse Claude Code output: {stdout[:300]}")
    if data.get("is_error"):
        raise LLMError(f"Claude Code error: {data.get('result') or data.get('api_error_status')}")
    text = data.get("result", "")
    u = data.get("usage") or {}
    usage = Usage(
        prompt_tokens=int(u.get("input_tokens", 0))
        + int(u.get("cache_read_input_tokens", 0))
        + int(u.get("cache_creation_input_tokens", 0)),
        completion_tokens=int(u.get("output_tokens", 0)),
    )
    real_model = next(iter((data.get("modelUsage") or {}).keys()), None) or model or "claude"
    resp = LLMResponse(text=text, model=real_model, provider=name, usage=usage, raw=data)
    # Claude Code reports the true dollar cost; preserve it (the router keeps a
    # provider-reported cost instead of re-estimating).
    resp.cost_usd = float(data.get("total_cost_usd", 0) or 0)
    return resp


# --------------------------------------------------------------------------- #
# Codex
# --------------------------------------------------------------------------- #
class CodexProvider(LLMProvider):
    name = "codex_cli"

    def __init__(self, *, binary: str = "codex", extra_args: list[str] | None = None) -> None:
        self.binary = binary or "codex"
        self.extra_args = extra_args or []

    def available(self) -> bool:
        return resolve_binary(self.binary) is not None

    def complete(
        self,
        messages: list[Message],
        *,
        model: str = "",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        response_format: str | None = None,
        stop: list[str] | None = None,
        timeout: float = 240.0,
    ) -> LLMResponse:
        exe = resolve_binary(self.binary)
        if exe is None:
            raise LLMError(f"'{self.binary}' (Codex) is not on PATH. Install it or set a different backend.")
        system, user = _messages_to_prompt(messages)
        prompt = f"SYSTEM INSTRUCTIONS:\n{system}\n\nTASK:\n{user}" if system else user

        out_file = tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False, encoding="utf-8")
        out_file.close()
        cmd = [
            exe, "exec",
            "--skip-git-repo-check", "--ephemeral",
            "-s", "read-only", "-a", "never",  # read-only sandbox + never ask: zero side effects
            "--color", "never",
            "-o", out_file.name,
        ]
        if model and model not in ("default", ""):
            cmd += ["-m", model]
        cmd += self.extra_args
        cmd += ["-"]  # read the prompt from stdin
        try:
            proc = _run_raw(cmd, prompt, timeout)
            try:
                with open(out_file.name, encoding="utf-8") as fh:
                    text = fh.read().strip()
            except OSError:
                text = ""
            if not text:
                if proc.returncode != 0 or "error" in (proc.stderr or "").lower():
                    raise LLMError(f"Codex failed: {_codex_error(proc.stderr)}")
                text = (proc.stdout or "").strip()
            if not text:
                raise LLMError(f"Codex returned no output: {_codex_error(proc.stderr)}")
        finally:
            try:
                os.unlink(out_file.name)
            except OSError:
                pass

        # Codex (ChatGPT auth) doesn't surface token counts here; estimate, cost 0.
        usage = Usage(prompt_tokens=len(prompt.split()), completion_tokens=len(text.split()))
        return LLMResponse(text=text, model=model or "codex", provider=self.name, usage=usage)

    def run_task(self, prompt: str, *, work_dir: str, timeout: float = 300.0) -> str:
        """Run an action task with tools + network, non-interactively, inside work_dir.

        Uses the workspace-write sandbox with network access turned on, so the agent
        can download files (and drive a browser MCP if configured) and write them into
        work_dir, with no approval prompts.
        """
        exe = resolve_binary(self.binary)
        if exe is None:
            raise LLMError(f"'{self.binary}' (Codex) is not on PATH.")
        cmd = [exe, "exec", "--skip-git-repo-check",
               "-s", "workspace-write", "-a", "never",
               "-c", "sandbox_workspace_write.network_access=true",
               "--color", "never", "-C", work_dir]
        cmd += self.extra_args
        cmd += ["-"]  # read the prompt from stdin
        proc = _run_raw(cmd, prompt, timeout, cwd=work_dir)
        return (proc.stdout or "")


def _codex_error(stderr: str | None) -> str:
    if not stderr:
        return "(no stderr)"
    for line in reversed(stderr.strip().splitlines()):
        if "error" in line.lower():
            return line[:300]
    return stderr.strip()[-300:]


# --------------------------------------------------------------------------- #
def _run(cmd: list[str], stdin_text: str, timeout: float, label: str) -> str:
    proc = _run_raw(cmd, stdin_text, timeout)
    if proc.returncode != 0 and not (proc.stdout or "").strip():
        raise LLMError(f"{label} CLI failed ({proc.returncode}): {(proc.stderr or '')[:400]}")
    return proc.stdout or ""


def _run_raw(cmd: list[str], stdin_text: str, timeout: float,
             cwd: str | None = None) -> subprocess.CompletedProcess:
    # On Windows a resolved .cmd/.bat shim must go through the shell launcher.
    use_shell = sys.platform == "win32" and cmd[0].lower().endswith((".cmd", ".bat"))
    try:
        return subprocess.run(
            cmd,
            input=stdin_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=use_shell,
            cwd=cwd,
        )
    except FileNotFoundError as exc:
        raise LLMError(f"CLI not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LLMError(f"CLI timed out after {timeout}s: {cmd[0]}") from exc
