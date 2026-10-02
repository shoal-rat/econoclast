"""The Sicarius runner: stream parsing, command wiring, and a whole hunt with a fake agent."""

from __future__ import annotations

import asyncio
import json
import sys
import textwrap
import time

from econoclast.case import Case
from econoclast.config import Settings
from econoclast.sicarius import Hunt, launch_detached, reap_orphans
from econoclast.sicarius.streams import ClaudeStream, CodexStream, tool_family


def test_tool_families():
    assert tool_family("Read") == "read"
    assert tool_family("Bash", {"command": "curl -L https://x.org/a.pdf -o a.pdf"}) == "web"
    assert tool_family("Bash", {"command": "python code/reproduce.py"}) == "shell"
    assert tool_family("mcp__arsenal__inflict_wound") == "arsenal:inflict_wound"
    assert tool_family("mcp__playwright__browser_navigate") == "browser"
    assert tool_family("Task") == "spawn"


def test_claude_stream_maps_to_events():
    s = ClaudeStream()
    evs = s.feed({"type": "system", "subtype": "init", "model": "claude-opus-5-5", "session_id": "abc",
                  "mcp_servers": [{"name": "arsenal", "status": "connected"}], "tools": ["Read", "Bash"]})
    assert evs[0]["kind"] == "session" and evs[0]["mcp"][0]["name"] == "arsenal"
    evs = s.feed({"type": "assistant", "parent_tool_use_id": None, "message": {"content": [
        {"type": "text", "text": "I will fetch the paper first."},
        {"type": "tool_use", "id": "t1", "name": "WebFetch", "input": {"url": "https://arxiv.org/abs/1"}},
        {"type": "tool_use", "id": "t2", "name": "Task", "input": {"description": "work the persona blade"}},
    ]}})
    kinds = [e["kind"] for e in evs]
    assert kinds == ["narrate", "tool", "tool", "spawn"]
    assert evs[1]["family"] == "web" and evs[3]["who"] == "conspirator-1"
    evs = s.feed({"type": "assistant", "parent_tool_use_id": "t2", "message": {"content": [
        {"type": "text", "text": "Checking pre-trends."}]}})
    assert evs[0]["who"] == "conspirator-1"
    evs = s.feed({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "403 Forbidden"}]}})
    assert evs[0] == {"kind": "tool.done", "id": "t1", "ok": False, "family": "web", "who": "sicarius",
                      "error": "403 Forbidden"}
    evs = s.feed({"type": "result", "subtype": "success", "result": "Done.", "total_cost_usd": 1.5,
                  "num_turns": 40, "duration_ms": 60000, "usage": {"input_tokens": 10, "output_tokens": 5}})
    assert evs[0]["kind"] == "usage" and evs[1] == {"kind": "final", "text": "Done."}


def test_thinking_becomes_throttled_pulses():
    s = ClaudeStream()
    tick = {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 50}
    assert s.feed(tick) == [{"kind": "pulse", "what": "thinking"}]
    assert s.feed(tick) == []  # at most one pulse every few seconds


def test_claude_heartbeats_become_busy_events():
    s = ClaudeStream()
    beat = {"type": "tool_progress", "tool_use_id": "t9-heartbeat-4", "tool_name": "Bash",
            "parent_tool_use_id": "t9", "elapsed_time_seconds": 120, "heartbeat": True}
    assert s.feed(beat) == [{"kind": "busy", "id": "t9", "tool": "Bash", "seconds": 120, "who": "sicarius"}]
    assert s.feed({**beat, "elapsed_time_seconds": 90}) == []


def test_codex_stream_maps_to_events():
    s = CodexStream()
    assert s.feed({"type": "thread.started", "thread_id": "th"})[0]["kind"] == "session"
    evs = s.feed({"type": "item.started", "item": {"id": "i1", "type": "command_execution",
                                                    "command": "bash -lc 'curl -L https://x/a.pdf'",
                                                    "status": "in_progress"}})
    assert evs[0]["family"] == "web"
    evs = s.feed({"type": "item.completed", "item": {"id": "i1", "type": "command_execution",
                                                      "command": "curl", "exit_code": 22, "status": "failed",
                                                      "aggregated_output": "403"}})
    assert evs[-1]["kind"] == "tool.done" and evs[-1]["ok"] is False
    evs = s.feed({"type": "item.completed", "item": {"id": "i2", "type": "mcp_tool_call",
                                                      "server": "arsenal", "tool": "proclaim",
                                                      "arguments": {"station": "classis"}, "status": "completed"}})
    assert evs[0]["family"] == "arsenal:proclaim" and evs[1]["ok"] is True
    s.feed({"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "All done."}})
    evs = s.feed({"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 2}})
    assert evs[-1] == {"kind": "final", "text": "All done."}


def _fake_agent(tmp_path, *, finish: bool = True):
    """A stand-in `claude` that streams JSON and records a verdict like the real agent would."""
    script = tmp_path / "fake-claude"
    script.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import json, os, sys
        brief = sys.stdin.read()
        assert "--permission-mode" in sys.argv and "bypassPermissions" in sys.argv
        mcp = json.load(open(sys.argv[sys.argv.index("--mcp-config") + 1]))
        assert "arsenal" in mcp["mcpServers"]
        def out(o): print(json.dumps(o), flush=True)
        out({{"type": "system", "subtype": "init", "model": "fake", "session_id": "s1", "tools": [],
             "mcp_servers": [{{"name": "arsenal", "status": "connected"}}]}})
        out({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "Arriving at Classis."}}]}}}})
        if {finish!r}:
            from econoclast.arsenal.tools import Arsenal
            from econoclast.case import Case
            a = Arsenal(Case(os.environ["ECONOCLAST_CASE"]))
            a.proclaim("classis")
            a.parry("tuba", "modest claims")
            a.pronounce_verdict("Stands.", "Nothing landed.", "n/a", [])
        out({{"type": "result", "subtype": "success", "result": "Bye", "total_cost_usd": 0, "num_turns": 1,
             "duration_ms": 10, "usage": {{}}}})
        """))
    script.chmod(0o755)
    return script


def _settings(binary) -> Settings:
    s = Settings()
    s.claude_binary = str(binary)
    s.codex_binary = "/nonexistent/codex"
    s.browser_mcp = False
    s.backend = "claude"
    return s


def test_whole_hunt_with_fake_agent(tmp_path):
    case = Case.create(paper="https://arxiv.org/abs/2401.00001", lang="en")
    status = Hunt(case, _settings(_fake_agent(tmp_path))).run()
    assert status == "done"
    kinds = [e["kind"] for e in case.events()]
    for k in ("case.opened", "session", "narrate", "station", "parry", "verdict", "usage", "final",
              "case.closed"):
        assert k in kinds, k
    assert case.meta()["status"] == "done" and case.meta()["session_id"] == "s1"
    assert "The decree to test: https://arxiv.org/abs/2401.00001" in case.path("MANDATE.md").read_text()


def test_hunt_without_verdict_is_failed(tmp_path):
    case = Case.create(paper="p")
    assert Hunt(case, _settings(_fake_agent(tmp_path, finish=False))).run() == "failed"
    assert case.events()[-1]["kind"] == "case.closed"


def test_codex_command_wiring(tmp_path):
    fake = tmp_path / "codex"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    s = Settings()
    s.codex_binary, s.claude_binary, s.backend, s.browser_mcp = str(fake), "/nonexistent", "codex", False
    case = Case.create(paper="p", backend="codex")
    cmd, stdin, _ = Hunt(case, s).command()
    assert cmd[:3] == [str(fake), "exec", "--json"] and cmd[-1] == "-"
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert any(c.startswith("mcp_servers.arsenal.args=") for c in cmd)
    assert "# You are the Sicarius" in stdin and "The decree to test: p" in stdin


def test_reap_orphans_marks_dead_runs():
    case = Case.create(paper="p")
    case.update_meta(status="running", runner_pid=999999, pid=999998)
    assert case.id in reap_orphans()
    assert case.meta()["status"] == "interrupted"


def test_mcp_server_exposes_the_arsenal():
    from econoclast.arsenal.server import build_server

    case = Case.create(paper="p")
    tools = asyncio.run(build_server(str(case.root)).list_tools())
    names = {t.name for t in tools}
    for n in ("proclaim", "field_notes", "novacula", "fetch_paper", "read_paper", "mark_target", "verify_quote", "abacus",
              "search_literature", "fetch_dataset", "public_series", "inspect_dataset", "fabrica_build",
              "fabrica_run", "reproduce", "mille_viae", "inflict_wound", "parry", "plea", "pronounce_verdict"):
        assert n in names, n
    assert json.dumps([getattr(t, "input_schema", None) or t.inputSchema for t in tools])


def test_detached_hunt_runs_its_own_process_and_arsenal(tmp_path):
    """The app's real path: a runner process (`-m econoclast hunt`) whose agent starts the arsenal MCP
    server exactly as mcp.json says, on the same interpreter."""
    fake = tmp_path / "fake-claude"
    fake.write_text(textwrap.dedent(f"""\
        #!{sys.executable}
        import asyncio, json, os, sys
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        sys.stdin.read()
        spec = json.load(open(sys.argv[sys.argv.index("--mcp-config") + 1]))["mcpServers"]["arsenal"]
        async def probe():
            params = StdioServerParameters(command=spec["command"], args=spec["args"],
                                           env={{**os.environ, **spec.get("env", {{}})}})
            async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
                await s.initialize()
                await s.call_tool("proclaim", {{"station": "classis"}})
                await s.call_tool("parry", {{"blade": "tuba", "note": "modest claims"}})
                await s.call_tool("pronounce_verdict", {{"headline": "Stands.", "assessment": "Nothing landed.",
                                                        "change_my_mind": "n/a", "survived": []}})
                return len((await s.list_tools()).tools)
        n = asyncio.run(probe())
        print(json.dumps({{"type": "system", "subtype": "init", "model": "fake", "session_id": "d1"}}), flush=True)
        print(json.dumps({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": f"{{n}} tools"}}]}}}}))
        print(json.dumps({{"type": "result", "subtype": "success", "result": "Bye", "total_cost_usd": 0,
                          "num_turns": 1, "duration_ms": 10, "usage": {{}}}}), flush=True)
        """))
    fake.chmod(0o755)
    from econoclast.case.store import home

    (home() / "config.yaml").write_text(f"backend: claude\nclaude_binary: {fake}\nbrowser_mcp: false\n")
    case = Case.create(paper="https://arxiv.org/abs/2401.00001", lang="en")
    pid = launch_detached(case)
    deadline = time.time() + 90
    while case.meta().get("status") not in ("done", "failed", "aborted") and time.time() < deadline:
        time.sleep(0.25)
    log = case.path("runner.log").read_text(errors="replace") if case.path("runner.log").exists() else ""
    assert case.meta().get("status") == "done", log[-2000:]
    assert case.meta().get("runner_pid") == pid
    kinds = [e["kind"] for e in case.events()]
    assert {"station", "parry", "verdict", "case.closed"} <= set(kinds)
    assert any("tools" in (e.get("text") or "") for e in case.events() if e["kind"] == "narrate")
