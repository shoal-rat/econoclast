"""PDF extraction.

Uses PyMuPDF (``pip install econoclast[pdf]``) when available because it
recovers text and tables better, and falls back to the BSD-licensed ``pypdf`` so
the default install stays permissive. For hard layouts, pre-convert with GROBID
or marker and feed the resulting text/markdown instead.
"""

from __future__ import annotations

from econoclast.ingest.models import Table
from econoclast.logging import get_logger

log = get_logger("ingest.pdf")


def extract_pdf(path: str) -> dict:
    from econoclast.ingest.grobid import extract_grobid, grobid_url

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
    title = (meta.get("title") or "").strip()
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
        title = (reader.metadata.title or "").strip() if reader.metadata else ""
    except Exception:  # noqa: BLE001
        title = ""
    return {"text": "\n\n".join(pages), "pages": pages, "tables": [],
            "title": title, "n_pages": len(pages), "backend": "pypdf"}
