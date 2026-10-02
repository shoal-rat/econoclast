"""Translate the agents' live JSON streams into Econoclast events.

Claude Code (``--output-format stream-json``) and Codex (``exec --json``) narrate very
different shapes; both become the same small vocabulary the stage understands:

- ``session``   the agent woke up (model, tools, MCP servers)
- ``narrate``   something it said (``who`` = sicarius or conspirator-N)
- ``tool``      it picked up a tool (``family`` decides the gesture on the stage)
- ``tool.done`` the tool came back (``ok``)
- ``spawn``     it sent a conspirator (a subagent)
- ``usage``     tokens / cost / turns
- ``final``     its last message to the traveller
"""

from __future__ import annotations

import json
import os
from typing import Any

Event = dict[str, Any]

_READ = {"Read", "Glob", "Grep", "LS", "NotebookRead"}
_WRITE = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_SHELL = {"Bash", "BashOutput", "KillShell", "KillBash"}
_SPAWN = {"Task", "Agent"}


def tool_family(name: str, args: dict[str, Any] | None = None) -> str:
    args = args or {}
    if name.startswith("mcp__"):
        parts = name.split("__")
        server = parts[1] if len(parts) > 1 else ""
        tool = parts[-1]
        return _server_family(server, tool)
    if name in _READ:
        return "read"
    if name in _WRITE:
        return "write"
    if name in _SHELL:
        cmd = str(args.get("command", ""))
        return "web" if _is_download(cmd) else "shell"
    if name == "WebFetch":
        return "web"
    if name == "WebSearch":
        return "search"
    if name in _SPAWN:
        return "spawn"
    if name in ("TodoWrite", "TaskCreate", "TaskUpdate", "ToolSearch"):
        return "plan"
    return "other"


def _server_family(server: str, tool: str) -> str:
    s = server.lower()
    if "arsenal" in s or "econoclast" in s:
        return f"arsenal:{tool}"
    if "playwright" in s or "browser" in s or "chrome" in s:
        return "browser"
    return "mcp"


def _is_download(cmd: str) -> bool:
    c = cmd.strip().lower()
    return any(c.startswith(k) or f" {k} " in f" {c} " for k in ("curl", "wget", "aria2c", "gh release download"))


def summarize(name: str, args: dict[str, Any]) -> str:
    """One short line the chronicle can show for a tool call."""
    a = args or {}
    if name in _READ:
        target = a.get("file_path") or a.get("path") or a.get("pattern") or ""
        return _short(f"{_base(target)}" + (f"  /{a['pattern']}/" if name == "Grep" and a.get("pattern") else ""))
    if name in _WRITE:
        return _short(_base(a.get("file_path") or a.get("notebook_path") or ""))
    if name in _SHELL:
        return _short(a.get("description") or a.get("command") or "")
    if name == "WebFetch":
        return _short(_host_path(a.get("url", "")))
    if name == "WebSearch":
        return _short(a.get("query", ""))
    if name in _SPAWN:
        return _short(a.get("description") or a.get("prompt", "")[:80])
    if name.startswith("mcp__"):
        tool = name.split("__")[-1]
        key = next((str(a[k]) for k in ("station", "title", "query", "url_or_doi", "url", "path", "script",
                                        "what", "blade", "series", "headline") if a.get(k)), "")
        return _short(f"{tool} {key}".strip())
    return _short(name)


def _short(s: str, n: int = 140) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _base(p: str) -> str:
    return os.path.basename(str(p).rstrip("/")) or str(p)


def _host_path(url: str) -> str:
    u = url.split("://", 1)[-1]
    return u[:120]


# --------------------------------------------------------------------- claude
PULSE_EVERY = 15.0  # seconds between "still thinking" pulses written to the log


class ClaudeStream:
    def __init__(self) -> None:
        self.conspirators: dict[str, str] = {}  # Task tool_use_id -> conspirator-N
        self.pending: dict[str, str] = {}  # tool_use_id -> family
        self.last_pulse = 0.0

    def pulse(self, what: str) -> list[Event]:
        import time

        now = time.time()
        if now - self.last_pulse < PULSE_EVERY:
            return []
        self.last_pulse = now
        return [{"kind": "pulse", "what": what}]

    def who(self, parent: str | None) -> str:
        if not parent:
            return "sicarius"
        return self.conspirators.get(parent, "conspirator")

    def feed(self, obj: dict[str, Any]) -> list[Event]:
        t = obj.get("type")
        if t == "system" and obj.get("subtype") == "init":
            return [{"kind": "session", "backend": "claude", "model": obj.get("model"),
                     "session_id": obj.get("session_id"),
                     "mcp": [{"name": m.get("name"), "status": m.get("status")} for m in obj.get("mcp_servers", [])],
                     "n_tools": len(obj.get("tools") or [])}]
        if t == "assistant":
            msg = obj.get("message") or {}
            if obj.get("error") or obj.get("is_api_error_message") or msg.get("model") == "<synthetic>":
                return []  # Claude Code's own "API Error: ..." text; the result reports it as agent.error
            who = self.who(obj.get("parent_tool_use_id"))
            out: list[Event] = []
            for block in (obj.get("message") or {}).get("content") or []:
                bt = block.get("type")
                if bt == "text" and block.get("text", "").strip():
                    out.append({"kind": "narrate", "who": who, "text": block["text"].strip()[:4000]})
                elif bt == "tool_use":
                    name = block.get("name", "")
                    args = block.get("input") or {}
                    fam = tool_family(name, args)
                    self.pending[block.get("id", "")] = fam
                    ev = {"kind": "tool", "id": block.get("id"), "who": who, "name": name, "family": fam,
                          "summary": summarize(name, args)}
                    out.append(ev)
                    if name in _SPAWN:
                        n = len(self.conspirators) + 1
                        self.conspirators[block.get("id", "")] = f"conspirator-{n}"
                        out.append({"kind": "spawn", "id": block.get("id"), "who": f"conspirator-{n}",
                                    "task": _short(args.get("description") or args.get("prompt", ""), 200)})
            return out
        if t == "user":
            out = []
            content = (obj.get("message") or {}).get("content")
            if isinstance(content, list):
                for block in content:
                    if block.get("type") == "tool_result":
                        tid = block.get("tool_use_id", "")
                        ok = not block.get("is_error")
                        ev: Event = {"kind": "tool.done", "id": tid, "ok": ok,
                                     "family": self.pending.pop(tid, "other"),
                                     "who": self.who(obj.get("parent_tool_use_id"))}
                        if not ok:
                            ev["error"] = _short(_text_of(block.get("content")), 300)
                        out.append(ev)
            return out
        if t == "system" and obj.get("subtype") == "thinking_tokens":
            return self.pulse("thinking")
        if t == "stream_event":
            return self.pulse("writing")
        if t == "tool_progress" and obj.get("heartbeat"):
            tid = str(obj.get("tool_use_id", "")).split("-heartbeat")[0]
            secs = int(obj.get("elapsed_time_seconds") or 0)
            if secs and secs % 60 == 0:  # one "still working" event a minute is plenty
                return [{"kind": "busy", "id": tid, "tool": obj.get("tool_name"), "seconds": secs,
                         "who": self.who(obj.get("parent_tool_use_id") if obj.get("parent_tool_use_id") != tid else None)}]
            return []
        if t == "result":
            u = obj.get("usage") or {}
            out = [{"kind": "usage", "cost_usd": obj.get("total_cost_usd"), "turns": obj.get("num_turns"),
                    "duration_s": round((obj.get("duration_ms") or 0) / 1000, 1),
                    "input_tokens": (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0)
                    + (u.get("cache_creation_input_tokens") or 0),
                    "output_tokens": u.get("output_tokens") or 0,
                    "subtype": obj.get("subtype"), "is_error": bool(obj.get("is_error"))}]
            if obj.get("result") and obj.get("is_error"):  # e.g. "API Error: ..." is not the Sicarius's report
                out.append({"kind": "agent.error", "text": _short(str(obj["result"]), 400)})
            elif obj.get("result"):
                out.append({"kind": "final", "text": str(obj["result"])[:12000]})
            return out
        return []


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return json.dumps(content)[:300] if content else ""


# ---------------------------------------------------------------------- codex
class CodexStream:
    def __init__(self) -> None:
        self.started: set[str] = set()
        self.last_message = ""
        self.spawned = 0
        self.last_pulse = 0.0

    pulse = ClaudeStream.pulse

    def feed(self, obj: dict[str, Any]) -> list[Event]:
        t = obj.get("type", "")
        if t == "thread.started":
            return [{"kind": "session", "backend": "codex", "session_id": obj.get("thread_id")}]
        if t == "turn.completed":
            u = obj.get("usage") or {}
            out = [{"kind": "usage", "input_tokens": u.get("input_tokens", 0),
                    "output_tokens": u.get("output_tokens", 0), "cost_usd": None}]
            if self.last_message:
                out.append({"kind": "final", "text": self.last_message[:12000]})
            return out
        if t in ("turn.failed", "error"):
            err = obj.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or obj.get("message") or ""
            return [{"kind": "agent.error", "text": _short(str(msg), 400)}] if msg else []
        if not t.startswith("item."):
            return []
        item = obj.get("item") or {}
        iid = str(item.get("id", ""))
        it = item.get("type") or item.get("item_type") or ""
        phase = t.split(".", 1)[1]  # started | updated | completed
        if it in ("agent_message", "assistant_message"):
            if phase == "completed" and item.get("text", "").strip():
                self.last_message = item["text"].strip()
                return [{"kind": "narrate", "who": "sicarius", "text": self.last_message[:4000]}]
            return []
        if it == "reasoning":
            return self.pulse("thinking")
        fam, name, summary = _codex_tool(item)
        if fam is None:
            return []
        out = []
        if iid not in self.started and phase in ("started", "completed"):
            self.started.add(iid)
            out.append({"kind": "tool", "id": iid, "who": "sicarius", "name": name, "family": fam,
                        "summary": summary})
            if fam == "spawn":
                self.spawned += 1
                out.append({"kind": "spawn", "id": iid, "who": f"conspirator-{self.spawned}", "task": summary})
        if phase == "completed":
            status = str(item.get("status", "completed"))
            ok = status not in ("failed", "declined", "error") and not item.get("error")
            if it == "command_execution" and item.get("exit_code") not in (None, 0):
                ok = False
            ev: Event = {"kind": "tool.done", "id": iid, "ok": ok, "family": fam, "who": "sicarius"}
            if not ok:
                ev["error"] = _short(str(item.get("error") or item.get("aggregated_output", ""))[-300:], 300)
            out.append(ev)
        return out


def _codex_tool(item: dict[str, Any]) -> tuple[str | None, str, str]:
    it = item.get("type") or ""
    if it == "command_execution":
        cmd = str(item.get("command", ""))
        if cmd.startswith(("bash -lc ", "/bin/bash -lc ", "zsh -lc ", "/bin/zsh -lc ")):
            cmd = cmd.split(" ", 2)[-1].strip("'\"")
        return ("web" if _is_download(cmd) else "shell"), "shell", _short(cmd)
    if it == "file_change":
        changes = item.get("changes") or []
        paths = ", ".join(_base(c.get("path", "")) for c in changes[:3])
        return "write", "edit", _short(paths or "files")
    if it == "mcp_tool_call":
        server, tool = str(item.get("server", "")), str(item.get("tool", ""))
        args = item.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        return _server_family(server, tool), f"mcp__{server}__{tool}", summarize(f"mcp__{server}__{tool}", args)
    if it == "web_search":
        return "search", "web_search", _short(item.get("query", ""))
    if it == "todo_list":
        return "plan", "todo", "plan"
    if "collab" in it or "agent" in it:
        return "spawn", it, _short(item.get("prompt") or item.get("description") or it)
    return None, "", ""
