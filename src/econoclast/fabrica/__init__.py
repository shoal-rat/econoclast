"""The Fabrica: a local quant workshop the Sicarius forges its blades in.

One shared Python environment under ``~/.econoclast/fabrica/venv`` with a lean
econometrics stack preinstalled (pandas, statsmodels, linearmodels, rdrobust, ...). The agent adds whatever else a paper needs, writes its replication
scripts into the case folder, and runs them here, so its own code never touches the
interpreter Econoclast itself runs in. Built with ``uv`` when present (seconds), else
with ``venv`` + ``pip``.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from econoclast.case.store import home
from econoclast.log import get_logger

log = get_logger("fabrica")

# Lean by default; heavy extras (pyfixest + numba, pyarrow, scikit-learn, doubleml, ...) are installed on
# demand with fabrica_build(extra_packages=[...]) so the shared workshop stays small.
BASE_PACKAGES = (
    "numpy", "pandas", "scipy", "statsmodels", "linearmodels", "matplotlib", "pyreadstat", "openpyxl",
    "rdrobust", "rddensity", "httpx",
)
PYTHON_VERSION = "3.12"


def root() -> Path:
    p = home() / "fabrica"
    p.mkdir(parents=True, exist_ok=True)
    return p


def venv_dir() -> Path:
    return root() / "venv"


def python_path() -> Path:
    v = venv_dir()
    return v / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _uv() -> str | None:
    return shutil.which("uv")


def status() -> dict:
    py = python_path()
    info = {
        "ready": py.exists(),
        "python": str(py) if py.exists() else None,
        "root": str(root()),
        "uv": _uv(),
        "rscript": shutil.which("Rscript"),
        "stata": shutil.which("stata-mp") or shutil.which("stata-se") or shutil.which("stata"),
        "node": shutil.which("npx"),
    }
    manifest = root() / "manifest.json"
    if manifest.exists():
        try:
            info["packages"] = json.loads(manifest.read_text()).get("packages", [])
        except (OSError, json.JSONDecodeError):
            pass
    return info


def build(extra: list[str] | None = None, *, timeout: float = 1200.0) -> dict:
    """Create the workshop if needed and install the base stack plus ``extra``."""
    started = time.time()
    extra = [p for p in (extra or []) if p and not p.startswith("-")]
    py = python_path()
    log_lines: list[str] = []
    uv = _uv()

    if venv_dir().exists() and not _healthy(py):
        # Its base interpreter is gone (moved app, removed Python): rebuild rather than patch it.
        log_lines.append(f"workshop at {venv_dir()} no longer runs; rebuilding it")
        shutil.rmtree(venv_dir(), ignore_errors=True)
    if not py.exists():
        if uv:
            cmd = [uv, "venv", "--python", PYTHON_VERSION, str(venv_dir())]
        else:
            cmd = [sys.executable, "-m", "venv", str(venv_dir())]
        log_lines.append(_run(cmd, timeout)[1])
        if not py.exists():  # uv could not fetch 3.12: fall back to whatever runs us
            log_lines.append(_run([sys.executable, "-m", "venv", "--clear", str(venv_dir())], timeout)[1])

    have = set(_installed().keys())
    want = [p for p in (*BASE_PACKAGES, *extra) if _norm(p) not in have]
    if want:
        if uv:
            cmd = [uv, "pip", "install", "-p", str(py), *want]
        else:
            cmd = [str(py), "-m", "pip", "install", "-q", *want]
        rc, out = _run(cmd, timeout)
        log_lines.append(out)
        if rc != 0 and len(want) > 1:
            # One bad package (uv resolves all or nothing) must not sink the rest: retry one by one.
            for pkg in want:
                single = [uv, "pip", "install", "-p", str(py), pkg] if uv else \
                    [str(py), "-m", "pip", "install", "-q", pkg]
                log_lines.append(_run(single, timeout / 4)[1])

    installed = _installed()
    manifest = {"python": str(py), "packages": sorted(installed), "built": time.time()}
    (root() / "manifest.json").write_text(json.dumps(manifest, indent=1))
    missing = [p for p in (*BASE_PACKAGES, *extra) if _norm(p) not in installed]
    return {
        "python": str(py),
        "ready": py.exists(),
        "installed_now": [p for p in want if _norm(p) in installed],
        "missing": missing,
        "seconds": round(time.time() - started, 1),
        "rscript": shutil.which("Rscript"),
        "log_tail": "\n".join(log_lines)[-1500:],
    }


def run_script(script: str | Path, *, cwd: str | Path, timeout: float = 900.0,
               args: list[str] | None = None) -> dict:
    """Run a script inside the workshop. ``.py`` uses the workshop Python, ``.R`` Rscript."""
    script = Path(script)
    if not script.is_absolute():
        script = Path(cwd) / script
    if not script.exists():
        return {"ok": False, "error": f"no such script: {script}"}
    suffix = script.suffix.lower()
    if suffix == ".py":
        if not python_path().exists():
            build()
        cmd = [str(python_path()), str(script)]
    elif suffix == ".r":
        rs = shutil.which("Rscript")
        if not rs:
            return {"ok": False, "error": "Rscript is not installed; translate the script to Python."}
        cmd = [rs, str(script)]
    elif suffix == ".sh":
        cmd = ["bash", str(script)]
    else:
        return {"ok": False, "error": f"unsupported script type {suffix} (use .py, .R or .sh)"}
    cmd += list(args or [])

    before = _snapshot(Path(cwd))
    started = time.time()
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONUNBUFFERED": "1"}
    try:
        # Its own session, so a timeout takes down everything the script started, not just the script.
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    except OSError as exc:
        return {"ok": False, "error": f"cannot start {cmd[0]}: {exc}. Run fabrica_build() to repair the workshop."}
    try:
        out_b, err_b = proc.communicate(timeout=timeout)
        rc, note = proc.returncode, ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        out_b, err_b = proc.communicate()
        rc, note = -9, f"\n[timed out after {timeout:g}s; the script and its children were stopped]"
    out = out_b.decode("utf-8", errors="replace")
    err = err_b.decode("utf-8", errors="replace") + note
    after = _snapshot(Path(cwd))
    new_files = sorted(str(p.relative_to(cwd)) for p, m in after.items() if before.get(p) != m)
    return {
        "ok": rc == 0,
        "returncode": rc,
        "seconds": round(time.time() - started, 1),
        "stdout_tail": out[-6000:],
        "stderr_tail": err[-3000:],
        "new_files": new_files[:50],
    }


# ------------------------------------------------------------------ helpers
def _run(cmd: list[str], timeout: float) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return -1, f"{cmd[0]} failed: {exc}"


def _healthy(py: Path) -> bool:
    try:
        return subprocess.run([str(py), "-c", "import sys"], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _installed() -> dict[str, str]:
    py = python_path()
    if not py.exists():
        return {}
    uv = _uv()
    cmd = [uv, "pip", "list", "-p", str(py), "--format", "json"] if uv else \
        [str(py), "-m", "pip", "list", "--format", "json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
        return {_norm(d["name"]): d["version"] for d in json.loads(out or "[]")}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def _norm(name: str) -> str:
    for sep in ("==", ">=", "<=", "~=", "[", "<", ">"):
        name = name.split(sep)[0]
    return name.strip().lower().replace("_", "-")


def _snapshot(base: Path) -> dict[Path, float]:
    snap: dict[Path, float] = {}
    for sub in ("out", "code", "data"):
        d = base / sub
        if d.exists():
            for p in d.rglob("*"):
                if p.is_file():
                    try:
                        snap[p] = p.stat().st_mtime
                    except OSError:
                        pass
    return snap
