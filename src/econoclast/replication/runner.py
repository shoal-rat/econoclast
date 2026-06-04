"""Run an author's replication package (opt-in, best-effort).

This executes the authors' own code so you can compare their reported numbers to
what their scripts actually produce. It is off by default and you must pass
``allow_code=True``. It is NOT a real sandbox: it runs in a subprocess with a
timeout and a working directory, nothing more. Only run packages you trust, and
prefer a container or a throwaway VM. With no interpreter installed, or with the
flag off, it returns a clear reason instead of running anything.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from econoclast.logging import get_logger

log = get_logger("replication.runner")

# Entry-point filenames in rough priority order, with their interpreter.
_ENTRYPOINTS = [
    ("master.do", "stata"), ("main.do", "stata"), ("run.do", "stata"),
    ("master.R", "R"), ("main.R", "R"), ("run.R", "R"), ("00_master.R", "R"),
    ("master.py", "python"), ("main.py", "python"), ("run.py", "python"),
    ("Makefile", "make"), ("makefile", "make"),
]
_INTERPRETERS = {
    "stata": ["stata-mp", "stata-se", "stata"],
    "R": ["Rscript"],
    "python": ["python", "python3"],
    "make": ["make"],
}


def detect_entrypoint(package_dir: str | Path) -> tuple[Path, str] | None:
    base = Path(package_dir)
    if base.is_file():
        return (base, _kind_from_suffix(base))
    for name, kind in _ENTRYPOINTS:
        for hit in base.rglob(name):
            return (hit, kind)
    # Otherwise the single obvious script.
    scripts = [p for p in base.rglob("*") if p.suffix.lower() in (".do", ".r", ".py")]
    if len(scripts) == 1:
        return (scripts[0], _kind_from_suffix(scripts[0]))
    return None


def _kind_from_suffix(p: Path) -> str:
    return {".do": "stata", ".r": "R", ".py": "python"}.get(p.suffix.lower(), "python")


def _command(kind: str, script: Path) -> list[str] | None:
    exe = next((shutil.which(c) for c in _INTERPRETERS.get(kind, []) if shutil.which(c)), None)
    if exe is None:
        return None
    if kind == "stata":
        return [exe, "-b", "do", script.name]
    if kind == "R":
        return [exe, script.name]
    if kind == "make":
        return [exe]
    return [exe, script.name]


def run_replication_package(
    package_dir: str | Path,
    *,
    allow_code: bool = False,
    timeout: float = 900.0,
) -> dict:
    base = Path(package_dir)
    if not base.exists():
        return {"ran": False, "reason": f"path not found: {base}"}
    if not allow_code:
        return {"ran": False, "reason": "code execution is off; pass allow_code=True to run untrusted author code"}

    found = detect_entrypoint(base)
    if not found:
        return {"ran": False, "reason": "no recognisable entry point (master.do / run.R / main.py / Makefile)"}
    script, kind = found
    cmd = _command(kind, script)
    if cmd is None:
        return {"ran": False, "reason": f"no interpreter for {kind} on PATH", "entrypoint": str(script), "kind": kind}

    workdir = script.parent
    log.warning("Executing UNTRUSTED replication code: %s (in %s)", " ".join(cmd), workdir)
    try:
        proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ran": False, "reason": f"timed out after {timeout}s", "entrypoint": str(script), "kind": kind}
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "reason": f"execution failed: {exc}", "entrypoint": str(script), "kind": kind}

    out = (proc.stdout or "")[-4000:]
    return {
        "ran": True,
        "entrypoint": str(script),
        "kind": kind,
        "returncode": proc.returncode,
        "succeeded": proc.returncode == 0,
        "stdout_tail": out,
        "stderr_tail": (proc.stderr or "")[-2000:],
    }
