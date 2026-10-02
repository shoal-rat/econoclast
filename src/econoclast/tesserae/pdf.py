"""PDF extraction.

Uses PyMuPDF (``pip install econoclast[pdf]``) when available because it
recovers text and tables better, and falls back to the BSD-licensed ``pypdf`` so
the default install stays permissive. For hard layouts, pre-convert with GROBID
or marker and feed the resulting text/markdown instead.
"""

from __future__ import annotations

import re

from econoclast.log import get_logger
from econoclast.tesserae.models import Table

log = get_logger("ingest.pdf")


def extract_pdf(path: str) -> dict:
    from econoclast.tesserae.grobid import extract_grobid, grobid_url

    base = grobid_url()
    if base:
        try:
            log.info("Using GROBID at %s", base)
            return extract_grobid(path, base)
        except Exception as exc:  # noqa: BLE001
            log.warning("GROBID failed (%s); falling back to local extraction.", exc)
    try:
        return _extract_pymupdf(path)
    except ImportError:
        log.debug("PyMuPDF not installed; falling back to pypdf.")
    try:
        return _extract_pypdf(path)
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "No PDF backend available. Install one with `pip install econoclast[pdf]` "
            "(PyMuPDF, better) or `pip install pypdf`, or pre-convert the PDF to text."
        ) from exc


_BOILERPLATE = re.compile(
    r"(working paper|discussion paper|nber|preliminary|draft|not for citation|do not cite|journal of|"
    r"volume|issn|doi|http|www\.|copyright|©|abstract|university|department|electronic copy|ssrn|"
    r"microsoft word|untitled|^\s*\d+\s*$)", re.IGNORECASE)


def clean_title(t: str) -> str:
    t = re.sub(r"\s+", " ", t or "").strip()
    if len(t) < 8 or _BOILERPLATE.search(t) or t.lower().endswith((".pdf", ".doc", ".docx", ".tex")):
        return ""
    return t[:300]


def _largest_text(doc) -> str:  # noqa: ANN001
    """The title is usually the biggest type on the first page or two (cover pages aside)."""
    best: tuple[float, str] = (0.0, "")
    for page in list(doc)[:2]:
        lines: list[tuple[float, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                text = "".join(sp.get("text", "") for sp in line.get("spans", [])).strip()
                size = max((sp.get("size", 0) for sp in line.get("spans", [])), default=0)
                if text:
                    lines.append((round(size, 1), text))
        candidates = [ln for ln in lines if not _BOILERPLATE.search(ln[1]) and len(ln[1]) > 3]
        if not candidates:
            continue
        sizes = sorted(sz for sz, _ in lines)
        median = sizes[len(sizes) // 2]
        top = max(sz for sz, _ in candidates)
        joined = " ".join(t for sz, t in candidates if sz >= top - 0.5)
        if top >= 1.3 * median and 8 <= len(joined) <= 220 and top > best[0]:
            best = (top, joined)
    return best[1]


def _extract_pymupdf(path: str) -> dict:
    import fitz  # type: ignore  # raises ImportError if PyMuPDF is absent

    doc = fitz.open(path)
    pages: list[str] = []
    tables: list[Table] = []
    for i, page in enumerate(doc):
        pages.append(page.get_text("text"))
        finder = getattr(page, "find_tables", None)
        if finder is None:
            continue
        try:
            found = finder()
        except Exception:  # noqa: BLE001
            continue
        for j, tbl in enumerate(getattr(found, "tables", []) or []):
            try:
                rows = tbl.extract()
            except Exception:  # noqa: BLE001
                continue
            raw = "\n".join("\t".join("" if c is None else str(c) for c in row) for row in rows)
            tables.append(Table(label=f"p{i + 1}.t{j + 1}", raw=raw))

    meta = doc.metadata or {}
    title = clean_title(meta.get("title") or "") or _largest_text(doc)
    n_pages = len(pages)
    doc.close()
    return {"text": "\n\n".join(pages), "pages": pages, "tables": tables,
            "title": title, "n_pages": n_pages, "backend": "pymupdf"}


def _extract_pypdf(path: str) -> dict:
    from pypdf import PdfReader  # raises ImportError if pypdf is absent

    reader = PdfReader(path)
    pages = [(p.extract_text() or "") for p in reader.pages]
    title = ""
    try:
        title = clean_title(reader.metadata.title or "") if reader.metadata else ""
    except Exception:  # noqa: BLE001
        title = ""
    return {"text": "\n\n".join(pages), "pages": pages, "tables": [],
            "title": title, "n_pages": len(pages), "backend": "pypdf"}
