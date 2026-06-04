"""GROBID ingestion for hard PDF layouts.

GROBID turns a PDF into structured TEI XML with a clean body, tables, and a
parsed bibliography. It needs a running GROBID server; point Econoclast at one
with the ``ECONOCLAST_GROBID_URL`` environment variable (for example
``http://localhost:8070``). When set, PDF ingestion tries GROBID first and falls
back to PyMuPDF/pypdf if it is unreachable.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import httpx

from econoclast.ingest.models import Table
from econoclast.logging import get_logger

log = get_logger("ingest.grobid")

_TEI = {"t": "http://www.tei-c.org/ns/1.0"}


def grobid_url() -> str | None:
    return os.getenv("ECONOCLAST_GROBID_URL")


def extract_grobid(path: str, base_url: str) -> dict:
    base = base_url.rstrip("/")
    with open(path, "rb") as fh:
        files = {"input": (os.path.basename(path), fh, "application/pdf")}
        data = {"consolidateHeader": "1", "consolidateCitations": "0"}
        resp = httpx.post(f"{base}/api/processFulltextDocument", files=files, data=data, timeout=180.0)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    title = _text(root.find(".//t:titleStmt/t:title", _TEI))
    abstract = _join(root.findall(".//t:profileDesc/t:abstract//t:p", _TEI))

    body_parts: list[str] = []
    body = root.find(".//t:text/t:body", _TEI)
    if body is not None:
        for div in body.findall("t:div", _TEI):
            head = _text(div.find("t:head", _TEI))
            if head:
                body_parts.append(f"\n{head}\n")
            for p in div.findall("t:p", _TEI):
                t = _flatten(p)
                if t:
                    body_parts.append(t)

    tables: list[Table] = []
    for i, fig in enumerate(root.findall(".//t:figure[@type='table']", _TEI)):
        label = _text(fig.find("t:head", _TEI)) or f"tab{i + 1}"
        rows = []
        for row in fig.findall(".//t:row", _TEI):
            cells = [_flatten(c) for c in row.findall("t:cell", _TEI)]
            rows.append("\t".join(cells))
        if rows:
            tables.append(Table(label=label, caption=label, raw="\n".join(rows)))

    references = _references(root)
    text = "\n\n".join(body_parts)
    if references:
        text += "\n\nReferences\n" + "\n".join(references)

    return {
        "text": text or abstract,
        "pages": [],
        "tables": tables,
        "title": title,
        "abstract": abstract,
        "references": references,
        "n_pages": None,
        "backend": "grobid",
    }


def _references(root) -> list[str]:
    refs = []
    for bib in root.findall(".//t:listBibl/t:biblStruct", _TEI):
        authors = []
        for pers in bib.findall(".//t:author/t:persName", _TEI):
            sur = _text(pers.find("t:surname", _TEI))
            if sur:
                authors.append(sur)
        title = _text(bib.find(".//t:title[@level='a']", _TEI)) or _text(bib.find(".//t:title", _TEI))
        date = bib.find(".//t:date", _TEI)
        year = (date.get("when", "")[:4] if date is not None else "")
        venue = _text(bib.find(".//t:title[@level='j']", _TEI)) or _text(bib.find(".//t:title[@level='m']", _TEI))
        parts = []
        if authors:
            parts.append(", ".join(authors[:4]))
        if year:
            parts.append(f"({year})")
        if title:
            parts.append(title)
        if venue:
            parts.append(venue)
        line = ". ".join(parts).strip()
        if len(line) > 15:
            refs.append(line)
    return refs


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _flatten(el) -> str:
    if el is None:
        return ""
    return " ".join("".join(el.itertext()).split())


def _join(els) -> str:
    return "\n".join(_flatten(e) for e in els if _flatten(e))
