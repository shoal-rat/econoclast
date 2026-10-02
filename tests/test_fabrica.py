"""The Fabrica: the workshop the agent equips itself in. Package installs are faked (no network)."""

from __future__ import annotations

import os
import sys
import time

import pytest

from econoclast import fabrica


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
def test_timeout_stops_the_script_and_its_children_and_keeps_output(tmp_path):
    (tmp_path / "slow.sh").write_text("echo started\nsleep 60 &\necho $! > child.pid\nwait\n")
    res = fabrica.run_script("slow.sh", cwd=tmp_path, timeout=1.5)
    assert res["ok"] is False and res["returncode"] == -9
    assert "started" in res["stdout_tail"] and "timed out" in res["stderr_tail"]
    child = int((tmp_path / "child.pid").read_text())
    for _ in range(50):
        if not _alive(child):
            break
        time.sleep(0.1)
    assert not _alive(child), "the script's background child outlived the timeout"


def test_missing_interpreter_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(fabrica, "python_path", lambda: tmp_path / "gone" / "python")
    monkeypatch.setattr(fabrica, "build", lambda *a, **k: {})
    (tmp_path / "x.py").write_text("print(1)\n")
    res = fabrica.run_script("x.py", cwd=tmp_path)
    assert res["ok"] is False and "fabrica_build" in res["error"]


def test_one_bad_package_does_not_sink_the_rest(tmp_path, monkeypatch):
    py = tmp_path / "python"
    py.write_text("")
    installed: dict[str, str] = {}

    def fake_run(cmd, timeout):  # noqa: ANN001, ANN202 - uv resolves all or nothing, and never says "error"
        pkgs = cmd[cmd.index(str(py)) + 1:]
        if "no-such-pkg" in pkgs:
            return 1, "× No solution found when resolving dependencies"
        installed.update(dict.fromkeys(pkgs, "1.0"))
        return 0, ""

    monkeypatch.setattr(fabrica, "python_path", lambda: py)
    monkeypatch.setattr(fabrica, "_healthy", lambda p: True)
    monkeypatch.setattr(fabrica, "_uv", lambda: "uv")
    monkeypatch.setattr(fabrica, "BASE_PACKAGES", ("six",))
    monkeypatch.setattr(fabrica, "_run", fake_run)
    monkeypatch.setattr(fabrica, "_installed", lambda: dict(installed))
    res = fabrica.build(["no-such-pkg"])
    assert res["installed_now"] == ["six"] and res["missing"] == ["no-such-pkg"]


def test_a_workshop_whose_python_vanished_is_rebuilt(monkeypatch):
    monkeypatch.setattr(fabrica, "BASE_PACKAGES", ())
    monkeypatch.setattr(fabrica, "_uv", lambda: None)  # the `python -m venv` fallback
    bindir = fabrica.python_path().parent
    bindir.mkdir(parents=True)
    fabrica.python_path().symlink_to("/nonexistent/python3")  # the app it was built from moved
    res = fabrica.build()
    assert res["ready"] and fabrica._healthy(fabrica.python_path())
