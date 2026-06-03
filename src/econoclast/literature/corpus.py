"""Local literature corpus.

Point Econoclast at folders of PDFs/notes you already have ("the things a referee
in this field would know") and it indexes them for keyword retrieval alongside the
online sources.
"""

from __future__ import annotations

from pathlib import Path

from econoclast.literature.models import LitRef
from econoclast.logging import get_logger

log = get_logger("literature.corpus")

_EXTS = {".pdf", ".txt", ".md", ".tex"}


def load_local_corpus(dirs: list[str]) -> list[tuple[LitRef, str]]:
    """Return (reference, full_text) for every readable doc under ``dirs``."""
    out: list[tuple[LitRef, str]] = []
    for d in dirs:
        base = Path(d)
        if not base.exists():
            log.warning("Local corpus dir not found: %s", d)
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix.lower() not in _EXTS or not path.is_file():
                continue
            text = _read(path)
            if not text:
                continue
            ref = LitRef(
                title=path.stem.replace("_", " ")[:200],
                source="local",
                abstract=text[:800],
                local_path=str(path),
            )
            out.append((ref, text))
    log.info("Loaded %d local documents from %d dir(s)", len(out), len(dirs))
    return out


def _read(path: Path) -> str:
    try:
        if path.suffix.lower() == ".pdf":
            from econoclast.ingest.pdf import extract_pdf

            return extract_pdf(str(path)).get("text", "")
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read %s: %s", path, exc)
        return ""
