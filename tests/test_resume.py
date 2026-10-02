"""Hunts that stop before the verdict: classifying why, resuming the agent session on their own after a
dropped connection, the traveller's Resume, and the region guard. The agent is a scripted fake `claude`."""

from __future__ import annotations

import json
import sys
import textwrap
import threading
import time

import pytest

from econoclast.case import Case
from econoclast.config import Settings
from econoclast.sicarius import Hunt, classify
from econoclast.sicarius.region import RegionGuard

FAKE = textwrap.dedent(f"""\
    #!{sys.executable}
    # A scripted `claude`: invocation N follows plan[N] and every call is logged with its arguments.
    import json, os, pathlib, sys, time
    here = pathlib.Path(__file__).parent
    calls = here / "calls.jsonl"
    n = sum(1 for _ in open(calls)) if calls.exists() else 0
    plan = json.loads((here / "plan.json").read_text())
    step = plan[min(n, len(plan) - 1)]
    resumed = sys.argv[sys.argv.index("--resume") + 1] if "--resume" in sys.argv else None
    prompt = sys.stdin.read()
    with open(calls, "a") as fh:
        fh.write(json.dumps({{"resume": resumed, "prompt": prompt[:4000],
                             "data": (pathlib.Path(os.environ["ECONOCLAST_CASE"]) / "data" / "panel.csv").exists()}}) + "\\n")
    def out(o): print(json.dumps(o), flush=True)
    def result(text, error=False):
        out({{"type": "result", "subtype": "success", "is_error": error, "result": text, "num_turns": 1,
             "total_cost_usd": 0, "duration_ms": 5, "usage": {{}}}})
    if step == "lost_session" and resumed:
        print("No conversation found with session ID: " + resumed, file=sys.stderr)
        sys.exit(1)
    out({{"type": "system", "subtype": "init", "model": "fake", "session_id": "s1", "tools": [], "mcp_servers": []}})
    if step == "network":
        result("API Error: Connection error.", error=True)
        sys.exit(1)
    if step == "auth":
        result("Invalid API key · Please run /login", error=True)
        sys.exit(1)
    if step == "stop":
        result("I will wait for the conspirator.")
        sys.exit(0)
    if step == "slow":  # longer than a tiny time budget
        time.sleep(6)
    if step == "heartbeat":  # tick for a while so a pause shows up as a gap
        with open(here / "beats.txt", "a") as fh:
            for _ in range(60):
                fh.write(f"{{time.time()}}\\n"); fh.flush(); time.sleep(0.03)
    from econoclast.arsenal.tools import Arsenal
    from econoclast.case import Case
    a = Arsenal(Case(os.environ["ECONOCLAST_CASE"]))
    a.proclaim("classis")
    a.parry("tuba", "modest claims")
    a.pronounce_verdict("Stands.", "Nothing landed.", "n/a", [])
    result("Done.")
    """)


@pytest.fixture
def fake(tmp_path):  # noqa: ANN001, ANN201
    script = tmp_path / "claude"
    script.write_text(FAKE)
    script.chmod(0o755)

    def setup(plan: list[str]) -> Settings:
        (tmp_path / "plan.json").write_text(json.dumps(plan))
        s = Settings()
        s.claude_binary, s.codex_binary, s.backend = str(script), "/nonexistent/codex", "claude"
        s.browser_mcp, s.subagents, s.pack_after = False, False, False
        s.resume_backoff = [0]
        s.region_guard = False
        return s

    setup.calls = lambda: [json.loads(x) for x in (tmp_path / "calls.jsonl").read_text().splitlines()]
    setup.dir = tmp_path
    return setup


def kinds(case: Case) -> list[str]:
    return [e["kind"] for e in case.events()]


@pytest.mark.parametrize("text,rc,kind", [
    ("API Error: Connection error.", 1, "network"),
    ('API Error: 529 {"type":"error","error":{"type":"overloaded_error"}}', 1, "network"),
    ("stream disconnected before completion: error sending request", 1, "network"),
    ("Invalid API key · Please run /login", 1, "auth"),
    ("Claude AI usage limit reached|1790000000", 1, "limit"),
    ("You've hit your limit · resets 7pm", 1, "limit"),
    ("API Error: Claude Code is unable to respond to this request, which appears to violate our Usage Policy", 1,
     "refused"),
    ("Background tasks still running after 600s; terminating.", 0, "background"),
    ("", 0, "unfinished"),
    ("Segmentation fault", 139, "crash"),
    ("API Error: Connection refused — a firewall or proxy may be blocking it (ECONNREFUSED)", 1, "network"),
    ("API Error: Unable to connect to API (ECONNREFUSED)", 1, "network"),
    ("stream disconnected before completion: tcp connect error: Connection refused (os error 61)", 1, "network"),
    ("stream error: Rate limit reached for gpt-5 in organization org-x on tokens per min", 1, "network"),
    ("5-hour limit reached ∙ resets 3pm", 1, "limit"),
    ("I refuse to help with that.", 1, "refused"),
])
def test_classify(text, rc, kind):  # noqa: ANN001
    assert classify(text, rc) == kind


def test_resume_commands_reopen_the_session(tmp_path):
    case = Case.create(paper="p")
    s = Settings()
    s.claude_binary, s.backend, s.browser_mcp = "/bin/echo", "claude", False
    cmd, stdin, env = Hunt(case, s).command(session="abc", prompt="# Resume the hunt")
    assert cmd[cmd.index("--resume") + 1] == "abc" and stdin == "# Resume the hunt"
    assert int(env["CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"]) >= 60 * 60 * 1000  # the whole budget, not 10 min
    s.codex_binary, s.backend, s.claude_binary = "/bin/echo", "codex", "/nonexistent/claude"
    cmd, stdin, _ = Hunt(case, s).command(session="abc", prompt="# Resume the hunt")
    assert cmd[1:4] == ["exec", "resume", "abc"] and cmd[-1] == "-" and "-C" not in cmd


def test_dropped_connection_resumes_the_same_session(fake):
    case = Case.create(paper="p", lang="zh")
    assert Hunt(case, fake(["network", "verdict"])).run() == "done"
    calls = fake.calls()
    assert [c["resume"] for c in calls] == [None, "s1"]
    assert "# Resume the hunt" in calls[1]["prompt"] and "简体中文" in calls[1]["prompt"]
    ks = kinds(case)
    assert ks.index("retry.wait") < ks.index("case.resumed") < ks.index("verdict")
    assert case.meta()["attempt"] == 2 and case.meta()["status"] == "done"


def test_an_agent_that_stops_early_is_sent_back(fake):
    case = Case.create(paper="p")
    assert Hunt(case, fake(["stop", "verdict"])).run() == "done"
    resumed = [e for e in case.events() if e["kind"] == "case.resumed"]
    assert [e["reason"] for e in resumed] == ["unfinished"]


def test_a_login_problem_is_left_to_the_traveller(fake):
    case = Case.create(paper="p")
    assert Hunt(case, fake(["auth", "verdict"])).run() == "failed"
    assert len(fake.calls()) == 1
    meta = case.meta()
    assert meta["failure"] == "auth" and meta["resumable"] is True
    closed = case.events()[-1]
    assert closed["kind"] == "case.closed" and closed["failure"] == "auth" and closed["resumable"]


def test_retries_are_bounded(fake):
    case = Case.create(paper="p")
    s = fake(["network"])
    s.auto_resume = 2
    assert Hunt(case, s).run() == "failed"
    assert len(fake.calls()) == 3 and case.meta()["failure"] == "network"


def test_traveller_resume_restores_the_vault_and_the_session(fake):
    from econoclast.case.vault import pack

    case = Case.create(paper="p")
    case.path("data").mkdir(exist_ok=True)
    case.path("data", "panel.csv").write_text("id,y\n" + "\n".join(f"{i},{i * 2}" for i in range(20000)))
    pack(case, emit=False)
    assert not case.path("data", "panel.csv").exists()
    case.update_meta(status="failed", session_id="s9", backend_used="claude", attempt=1)
    case.emit("case.closed", status="failed", failure="limit", resumable=True)
    assert Hunt(case, fake(["verdict"])).run(resume="manual") == "done"
    call = fake.calls()[0]
    assert call["resume"] == "s9" and call["data"], "resumed without its session or its data"
    ev = next(e for e in case.events() if e["kind"] == "case.resumed")
    assert ev["reason"] == "manual" and ev["restored"] >= 1 and case.meta()["attempt"] == 2


def test_a_session_the_agent_lost_starts_fresh_from_the_case(fake):
    case = Case.create(paper="p")
    case.update_meta(status="failed", session_id="gone", backend_used="claude")
    assert Hunt(case, fake(["lost_session", "verdict"])).run(resume="manual") == "done"
    assert [c["resume"] for c in fake.calls()] == ["gone", None]
    assert [e["reason"] for e in case.events() if e["kind"] == "case.resumed"] == ["manual", "lost_session"]


def test_api_resume_refuses_running_and_finished_hunts():
    from econoclast.app.api import Api

    api = Api()
    case = Case.create(paper="p")
    case.update_meta(status="running")
    assert api.resume(case.id) == {"ok": False, "error": "running"}


# ------------------------------------------------------------------ the region guard
def scripted(answers: list[str | None]):  # noqa: ANN201
    """A lookup that walks through `answers` and then repeats the last one."""
    it = iter(answers)
    last = [answers[-1]]

    def lookup() -> str | None:
        try:
            last[0] = next(it)
        except StopIteration:
            pass
        return last[0]
    return lookup


def test_region_guard_counts_unknown_as_blocked_and_forgives_one_miss():
    g = RegionGuard(["CN", "HK"], lookup=scripted([None, "US", None, None, "HK", "JP"]))
    assert g.check() == (False, None)  # nothing known yet
    assert g.check() == (True, "US")
    assert g.check() == (True, "US")  # one failed lookup keeps the last answer
    assert g.check() == (False, None)  # two in a row do not
    assert g.check() == (False, "HK")
    assert g.check() == (True, "JP")


def _guarded(fake, plan: list[str], answers: list[str | None]):  # noqa: ANN001, ANN202
    s = fake(plan)
    s.region_guard, s.region_check_s = True, 0.05
    case = Case.create(paper="p")
    h = Hunt(case, s)
    h.guard = RegionGuard(["CN", "HK", "MO", "TW"], lookup=scripted(answers))
    return case, h


def test_no_agent_starts_while_the_connection_is_in_a_blocked_region(fake):
    case, h = _guarded(fake, ["verdict"], ["CN", None, "CN", "US"])
    assert h.run() == "done"
    ks = kinds(case)
    assert ks.index("region.paused") < ks.index("region.cleared") < ks.index("session")
    paused = next(e for e in case.events() if e["kind"] == "region.paused")
    assert paused["region"] == "CN" and paused["during"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX job control")
def test_a_running_agent_is_frozen_while_the_connection_is_blocked(fake):
    case, h = _guarded(fake, ["heartbeat"], ["US"])
    beats_file = fake.dir / "beats.txt"
    blocked = [0]

    def lookup() -> str:  # US until the agent is visibly working, then Taiwan for ten checks, then US
        if blocked[0] < 10 and beats_file.exists() and len(beats_file.read_text().split()) >= 5:
            blocked[0] += 1
            return "TW"
        return "US"
    h.guard.lookup = lookup
    assert h.run() == "done"
    paused = next(e for e in case.events() if e["kind"] == "region.paused")
    assert paused["during"] is True and paused["region"] == "TW"
    beats = [float(x) for x in (fake.dir / "beats.txt").read_text().split()]
    gap = max(b - a for a, b in zip(beats, beats[1:], strict=False))
    assert gap > 0.3, f"the agent kept running while paused (largest gap {gap:.2f}s)"
    assert "region.cleared" in kinds(case)


def test_calling_off_a_paused_hunt(fake):
    case, h = _guarded(fake, ["verdict"], ["HK"])
    threading.Timer(0.3, h.abort).start()
    t0 = time.time()
    assert h.run() == "aborted"
    assert time.time() - t0 < 5 and fake.dir.joinpath("calls.jsonl").exists() is False
    assert case.meta()["failure"] == "aborted" and case.meta()["resumable"] is True


def test_the_guard_checks_the_route_each_agent_takes(monkeypatch):
    from econoclast.sicarius.region import proxy_from_env

    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:7891")
    assert proxy_from_env("claude") is None  # Claude Code does not use SOCKS: it goes out directly
    assert proxy_from_env("codex") == "socks5://127.0.0.1:7891"
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")
    assert proxy_from_env("claude") == proxy_from_env("codex") == "http://127.0.0.1:7890"



# ------------------------------------------------------------------ what the verification found
def test_stop_during_a_region_check_starts_no_agent(fake):
    s = fake(["verdict"])
    s.region_guard, s.region_check_s = True, 0.05
    case = Case.create(paper="p")
    h = Hunt(case, s)

    def slow_lookup() -> str:
        time.sleep(0.6)
        return "US"
    h.guard = RegionGuard(["CN"], lookup=slow_lookup)
    threading.Timer(0.2, h.abort).start()
    assert h.run() == "aborted"
    assert not (fake.dir / "calls.jsonl").exists(), "an agent started after Stop"


def test_a_verdict_wins_over_a_stop_that_comes_after_it(fake):
    from econoclast.arsenal.tools import Arsenal

    case = Case.create(paper="p")
    Arsenal(case).pronounce_verdict("Stands.", "Nothing landed.", "n/a", [])
    h = Hunt(case, fake(["verdict"]))
    h.aborted = True  # as if Stop landed while the agent wrote its final message
    assert h._close(143, [], "aborted") == "done"
    closed = case.events()[-1]
    assert closed["status"] == "done" and closed["resumable"] is False


def test_one_time_budget_covers_the_nudges(fake):
    s = fake(["stop", "slow"])
    s.time_limit_min = 1 / 60  # a 1.5 s budget for the whole run
    case = Case.create(paper="p")
    t0 = time.time()
    assert Hunt(case, s).run() == "failed"
    assert time.time() - t0 < 6, "the nudged attempt was given a fresh budget"
    meta = case.meta()
    assert meta["failure"] == "time_limit" and meta["resumable"] is True


def test_a_case_from_before_resumes_existed_resumes_as_attempt_two(fake):
    case = Case.create(paper="p")
    case.update_meta(status="failed", started=time.time() - 60, session_id="s1", backend_used="claude")
    assert Hunt(case, fake(["verdict"])).run(resume="manual") == "done"
    assert next(e for e in case.events() if e["kind"] == "case.resumed")["attempt"] == 2


def test_two_resumes_at_once_claim_the_case_once():
    case = Case.create(paper="p")
    case.update_meta(status="failed")
    wins: list[bool] = []
    gate = threading.Barrier(8)

    def go() -> None:
        gate.wait()
        wins.append(case.claim())
    threads = [threading.Thread(target=go) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert wins.count(True) == 1 and case.meta()["status"] == "starting"


def test_reap_orphans_closes_a_starting_case_whose_runner_died():
    from econoclast.sicarius import reap_orphans

    dead = Case.create(paper="p")
    dead.update_meta(status="starting", runner_pid=999999, claimed=time.time() - 5)
    fresh = Case.create(paper="q")
    assert fresh.claim()  # claimed a moment ago, runner not started yet
    assert reap_orphans() == [dead.id]
    assert dead.meta()["status"] == "interrupted" and dead.meta()["resumable"] is True
    assert fresh.meta()["status"] == "starting"


def test_config_shapes_people_actually_write(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text("blocked_regions: CN, hk\nresume_backoff: 45\nauto_resume: null\nregion_guard: 'off'\n")
    s = Settings.load(cfg)
    assert s.blocked_regions == ["CN", "HK"] and s.resume_backoff == [45] and s.auto_resume == 3
    assert s.region_guard is False
    cfg.write_text("blocked_regions: [CN, mainland]\n")
    assert Settings.load(cfg).blocked_regions == ["CN"]


def test_an_explicit_agent_path_never_falls_back_to_another_program(monkeypatch):
    import econoclast.config as config

    monkeypatch.setattr(config, "_CODEX_FALLBACKS", ("/bin/sh",))  # pretend a stand-in exists
    s = Settings()
    s.codex_binary = "/nonexistent/codex"
    assert s.codex_path() is None
    s.codex_binary = "off"
    assert s.codex_path() is None
    s.codex_binary = "codex-not-on-path"
    assert s.codex_path() == "/bin/sh"  # a bare name still finds the usual install


def test_stream_errors_carry_their_message():
    from econoclast.sicarius.streams import ClaudeStream, CodexStream

    ev = CodexStream().feed({"type": "error", "message": "Reconnecting... 2/5 (stream disconnected)"})
    assert ev == [{"kind": "agent.error", "text": "Reconnecting... 2/5 (stream disconnected)"}]
    assert CodexStream().feed({"type": "turn.failed", "error": {"message": "boom"}})[0]["text"] == "boom"
    synthetic = {"type": "assistant", "error": "server_error", "is_api_error_message": True,
                 "message": {"model": "<synthetic>", "content": [{"type": "text", "text": "API Error: ..."}]}}
    assert ClaudeStream().feed(synthetic) == []  # not the Sicarius speaking
    res = ClaudeStream().feed({"type": "result", "is_error": True, "result": "API Error: Connection error."})
    assert [e["kind"] for e in res] == ["usage", "agent.error"]


def test_no_proxy_sends_the_check_direct_like_the_agent(monkeypatch):
    from econoclast.sicarius.region import proxy_from_env

    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("NO_PROXY", "api.anthropic.com")
    assert proxy_from_env("claude") is None
    assert proxy_from_env("codex") == "http://127.0.0.1:7890"


def test_an_empty_region_list_turns_the_guard_off(fake):
    s = fake(["verdict"])
    s.region_guard, s.blocked_regions = True, []
    assert Hunt(Case.create(paper="p"), s).guard is None
