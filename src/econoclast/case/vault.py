"""The vault: a closed hunt's heavy material, packed tight.

Replication packages and raw datasets can run to gigabytes. When a hunt closes, everything
heavy in the case folder (downloaded data, browser downloads, PDFs, large outputs, the
agent's raw log) goes into one ``vault.tar.xz`` and the originals are removed. What the
app and the report need stays as it was: the event log, the Tabula, the verdict, the
field brief, the agent's scripts, and every small artifact a wound cites.
``unpack`` restores the folder exactly.
"""

from __future__ import annotations

import hashlib
import json
import tarfile
import time
from pathlib import Path

from econoclast.case.store import Case

KEEP_NAMES = {"case.json", "events.jsonl", "verdict.json", "tabula.html", "tabula.md", "tabula.json",
              "MANDATE.md", "mcp.json", "vault.json", ".meta.lock"}
ALWAYS_PACK_DIRS = ("data", "out/browser")
SMALL = 512 * 1024  # files under this stay unpacked outside the data folders (scripts, JSON artifacts)


def _size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.is_dir() else p.stat().st_size


# Rebuildable clutter: deleted outright rather than archived (the workshop can recreate any of it).
DISPOSABLE_DIRS = {".venv", "venv", "env", "__pycache__", "node_modules", ".ipynb_checkpoints", ".pytest_cache",
                   ".mypy_cache", ".ruff_cache", ".cache", ".Rproj.user", "renv", ".npm", ".uv-cache"}
KEEP_SMALL_DIRS = ("code", "notes", "out")  # small scripts, the field brief, JSON artifacts wounds cite
KEEP_FILES = {"paper/paper.txt", "paper/source.txt"}


def _disposable(case: Case) -> list[Path]:
    found: list[Path] = []
    for d in sorted(case.root.rglob("*")):
        if d.is_dir() and d.name in DISPOSABLE_DIRS and not any(p in found for p in d.parents):
            found.append(d)
    return found


def _candidates(case: Case, skip: list[Path]) -> list[Path]:
    root = case.root
    out: list[Path] = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or any(s in f.parents for s in skip):
            continue
        rel = f.relative_to(root)
        posix = rel.as_posix()
        if posix in KEEP_NAMES or rel.name in KEEP_NAMES or rel.name.startswith("vault") or posix in KEEP_FILES:
            continue
        if any(posix.startswith(d + "/") for d in ALWAYS_PACK_DIRS):
            out.append(f)
        elif rel.parts[0] in KEEP_SMALL_DIRS and f.stat().st_size < SMALL and \
                f.suffix.lower() not in (".csv", ".dta", ".parquet", ".zip", ".xlsx", ".sav", ".pdf", ".log"):
            continue
        elif len(rel.parts) == 1 and f.stat().st_size < SMALL and not f.suffix.lower() == ".log":
            continue
        else:
            out.append(f)
    return out


def pack(case: Case, *, emit: bool = True) -> dict:
    """Move the heavy files into a vault and delete rebuildable clutter (virtualenvs, caches)."""
    import shutil

    disposable = _disposable(case)
    removed = [{"path": d.relative_to(case.root).as_posix(), "bytes": _size(d)} for d in disposable]
    files = _candidates(case, disposable)
    for d in disposable:
        shutil.rmtree(d, ignore_errors=True)
    freed = sum(r["bytes"] for r in removed)
    if not files:
        if removed and emit:
            case.emit("packed", files=0, before_mb=round(freed / 1e6, 1), after_mb=0.0,
                      removed=[r["path"] for r in removed])
        return {"packed": 0, "before_bytes": freed, "after_bytes": 0, "removed": removed}
    before = sum(f.stat().st_size for f in files) + freed
    n_old = len(list(case.root.glob("vault*.tar.xz")))
    vault = case.path("vault.tar.xz" if n_old == 0 else f"vault.{n_old + 1}.tar.xz")
    manifest_path = case.path("vault.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": [], "vaults": []}
    tmp = vault.with_suffix(".tmp")
    with tarfile.open(tmp, "w:xz", preset=6) as tar:
        for f in files:
            tar.add(f, arcname=f.relative_to(case.root).as_posix())
    tmp.replace(vault)
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        manifest["files"].append({"path": f.relative_to(case.root).as_posix(), "bytes": f.stat().st_size,
                                  "sha256": h})
        f.unlink()
    for d in sorted((p for p in case.root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if d.name in ("paper", "data", "code", "out", "offerings", "notes"):
            continue
        if not any(d.iterdir()):
            d.rmdir()
    after = vault.stat().st_size
    manifest["vaults"] = manifest.get("vaults", []) + [vault.name]
    manifest["removed"] = manifest.get("removed", []) + removed
    manifest.update({"packed_at": time.time(), "vault_bytes": sum(v.stat().st_size for v in case.root.glob("vault*.tar.xz"))})
    manifest_path.write_text(json.dumps(manifest, indent=1))
    res = {"packed": len(files), "before_bytes": before, "after_bytes": after, "removed": removed}
    if emit:
        case.emit("packed", files=len(files), before_mb=round(before / 1e6, 1), after_mb=round(after / 1e6, 1),
                  removed=[r["path"] for r in removed])
    return res


def unpack(case: Case) -> int:
    """Restore every packed file to its place and remove the vaults."""
    root = case.root.resolve()
    n = 0
    for vault in sorted(case.root.glob("vault*.tar.xz")):
        with tarfile.open(vault, "r:xz") as tar:
            for m in tar.getmembers():
                target = (root / m.name).resolve()
                if not str(target).startswith(str(root)) or not m.isfile():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as src, open(target, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                n += 1
        vault.unlink()
    case.path("vault.json").unlink(missing_ok=True)
    return n


def footprint(case: Case) -> int:
    return _size(case.root)
