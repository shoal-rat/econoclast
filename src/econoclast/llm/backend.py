"""The model backend: one live LLM, reached through Claude Code or Codex.

Econoclast is a native-LLM tool. It does not ship a model, an API client, or any
offline fallback; it borrows the intelligence of the agent you already run. At
startup it finds the ``claude`` or ``codex`` CLI on PATH and sends every prompt
through it, using that CLI's own subscription auth (no API key).

Attacks ask for a *role* ("extractor", "attacker", "referee") only so the backend
can pick a temperature. There is a single model behind every role.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from econoclast.config import Settings
from econoclast.llm.base import LLMError, LLMProvider, LLMResponse, Message, Usage
from econoclast.llm.providers import ClaudeCodeProvider, CodexProvider
from econoclast.logging import get_logger

log = get_logger("backend")

_ROLE_TEMPERATURE = {"extractor": 0.1, "attacker": 0.3, "referee": 0.2}


def _fetch_order(work_dir: str, *, url: str, what: str) -> str:
    """The work order Econoclast hands the agent to download a blocked file."""
    target = f"the resource at this URL:\n  {url}\n\n" if url else ""
    desc = f'The resource is: "{what}".\n' if what else ""
    return (
        "You are a download worker for an automated tool. Do exactly this task and nothing else.\n\n"
        f"TASK: Download {target}and save the actual file into this directory:\n  {work_dir}\n\n"
        f"{desc}"
        "The plain HTTP download was blocked, most likely by an anti-crawler defence (a 403, a "
        "Cloudflare or JavaScript challenge, or a cookie wall). Get past it with whatever tools you "
        "have: drive a browser if you have one (a Playwright or Chrome MCP, or the Chrome extension), "
        "or use curl/wget with a real browser User-Agent and the site's cookies.\n\n"
        "If you have no browser tool, equip yourself: you may install one. For next time, add the "
        "Playwright MCP (`claude mcp add playwright -- npx -y @playwright/mcp@latest`, or the equivalent "
        "`[mcp_servers.playwright]` block in ~/.codex/config.toml). For THIS task, you can script a "
        "headless browser right now, for example with `npx -y playwright` or `pip install playwright "
        "&& playwright install chromium`, and use it to fetch the file.\n\n"
        "If that exact URL is dead or wrong and you were given a description, search the web for it, "
        "find the official source (the publisher or author page, or a data repository such as Zenodo, "
        "Dataverse, OSF, or ICPSR), and download the correct file from there.\n\n"
        "Save the real file (a PDF, CSV, DTA, XLSX, or ZIP, not an HTML page) into the directory above. "
        "Do not edit, delete, or touch anything else. When finished, print the saved filename on its "
        "own line, or print FAILED if you could not get the file."
    )


class Backend:
    """A single live LLM, driven through a local AI CLI."""

    def __init__(self, provider: LLMProvider, label: str, *, model: str = "", timeout: float = 240.0) -> None:
        self.provider = provider
        self.label = label  # "claude" or "codex"
        self.model = model
        self.timeout = timeout
        self._lock = threading.Lock()
        self.total_usage = Usage()
        self.total_cost_usd = 0.0
        self.call_count = 0

    def complete(
        self,
        role: str,
        messages: list[Message],
        *,
        response_format: str | None = None,
        temperature: float | None = None,
        max_tokens: int = 4096,
        stop: list[str] | None = None,
        json_schema: dict | None = None,
    ) -> LLMResponse:
        temp = _ROLE_TEMPERATURE.get(role, 0.2) if temperature is None else temperature
        resp = self.provider.complete(
            messages,
            model=self.model,
            temperature=temp,
            max_tokens=max_tokens,
            response_format=response_format,
            stop=stop,
            timeout=self.timeout,
            json_schema=json_schema,
        )
        with self._lock:
            self.total_usage = self.total_usage + resp.usage
            self.total_cost_usd += resp.cost_usd or 0.0
            self.call_count += 1
        return resp

    def summary(self) -> dict:
        return {
            "backend": self.label,
            "model": self.model or "default",
            "calls": self.call_count,
            "prompt_tokens": self.total_usage.prompt_tokens,
            "completion_tokens": self.total_usage.completion_tokens,
            "total_tokens": self.total_usage.total_tokens,
            "est_cost_usd": round(self.total_cost_usd, 4),
        }

    def fetch_into(self, work_dir, *, url: str = "", what: str = "",  # noqa: ANN001
                   timeout: float = 300.0) -> list[Path]:
        """Direct the agent to download a blocked file into ``work_dir``.

        This is the boss-to-employee handoff: when the plain download is blocked,
        Econoclast hands the agent a work order and lets it use its own tools (a
        browser, curl with cookies, a web search) to get the file. Returns the files
        that appeared in ``work_dir`` as a result.
        """
        work = Path(work_dir)
        work.mkdir(parents=True, exist_ok=True)
        before = {p: p.stat().st_mtime for p in work.rglob("*") if p.is_file()}
        order = _fetch_order(str(work), url=url, what=what)
        try:
            self.provider.run_task(order, work_dir=str(work), timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            log.warning("agent download task failed: %s", exc)
        new = [p for p in work.rglob("*")
               if p.is_file() and (p not in before or p.stat().st_mtime > before[p])]
        if new:
            log.info("Agent downloaded %d file(s) into %s", len(new), work)
        return new


def detect_backend(settings: Settings) -> Backend:
    """Find Claude Code or Codex on PATH and wrap it as the backend.

    Honours ``settings.backend`` ("auto" | "claude" | "codex"). Raises if neither
    CLI is available: Econoclast has no offline mode by design.
    """
    pref = (settings.backend or "auto").lower()
    order = {"claude": ["claude"], "codex": ["codex"]}.get(pref, ["claude", "codex"])
    for which in order:
        if which == "claude" and shutil.which(settings.claude_binary):
            return Backend(
                ClaudeCodeProvider(binary=settings.claude_binary, extra_args=settings.backend_args),
                "claude", model=settings.model, timeout=settings.request_timeout,
            )
        if which == "codex" and shutil.which(settings.codex_binary):
            return Backend(
                CodexProvider(binary=settings.codex_binary, extra_args=settings.backend_args),
                "codex", model=settings.model, timeout=settings.request_timeout,
            )
    raise LLMError(
        "Econoclast runs on the intelligence of Claude Code or Codex, but neither `claude` nor "
        "`codex` was found on PATH. Install one and log in, then run Econoclast again."
    )
