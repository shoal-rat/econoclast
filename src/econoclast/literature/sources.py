"""Keyless literature-search clients.

All four sources work with no API key (Semantic Scholar and OpenAlex give higher
rate limits if you supply a key / contact e-mail). Each client fails soft:
network or parse errors return an empty list and log a warning so the agent
degrades gracefully offline.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import httpx

from econoclast.literature.models import LitRef
from econoclast.logging import get_logger

log = get_logger("literature")

_TIMEOUT = 25.0


def _ua() -> dict[str, str]:
    email = os.getenv("ECONOCLAST_CONTACT_EMAIL", "")
    ua = "Econoclast/0.1 (research-integrity tool)"
    if email:
        ua += f" mailto:{email}"
    return {"User-Agent": ua}


def search_openalex(query: str, limit: int = 10) -> list[LitRef]:
    params = {"search": query, "per-page": min(limit, 25)}
    email = os.getenv("ECONOCLAST_CONTACT_EMAIL")
    if email:
        params["mailto"] = email
    try:
        r = httpx.get("https://api.openalex.org/works", params=params, headers=_ua(), timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("OpenAlex search failed: %s", exc)
        return []

    out = []
    for w in data.get("results", [])[:limit]:
        out.append(LitRef(
            title=w.get("title") or "(untitled)",
            source="openalex",
            authors=[a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")][:8],
            year=w.get("publication_year"),
            abstract=_deinvert(w.get("abstract_inverted_index")),
            venue=((w.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
            doi=(w.get("doi") or "").replace("https://doi.org/", "") or None,
            url=w.get("doi") or (w.get("primary_location") or {}).get("landing_page_url"),
            citations=w.get("cited_by_count"),
        ))
    return out


def search_arxiv(query: str, limit: int = 10) -> list[LitRef]:
    params = {"search_query": f"all:{query}", "start": 0, "max_results": limit}
    try:
        r = httpx.get("http://export.arxiv.org/api/query", params=params, headers=_ua(), timeout=_TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as exc:  # noqa: BLE001
        log.warning("arXiv search failed: %s", exc)
        return []

    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in root.findall("a:entry", ns):
        title = (e.findtext("a:title", default="", namespaces=ns) or "").strip()
        summary = (e.findtext("a:summary", default="", namespaces=ns) or "").strip()
        published = e.findtext("a:published", default="", namespaces=ns) or ""
        url = e.findtext("a:id", default="", namespaces=ns)
        authors = [a.findtext("a:name", default="", namespaces=ns) for a in e.findall("a:author", ns)]
        year = int(published[:4]) if published[:4].isdigit() else None
        out.append(LitRef(title=title, source="arxiv", authors=[a for a in authors if a][:8],
                          year=year, abstract=summary, venue="arXiv", url=url))
    return out


def search_semantic_scholar(query: str, limit: int = 10) -> list[LitRef]:
    fields = "title,abstract,year,authors,venue,externalIds,citationCount,url"
    headers = _ua()
    key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if key:
        headers["x-api-key"] = key
    try:
        r = httpx.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "limit": min(limit, 25), "fields": fields},
            headers=headers,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Semantic Scholar search failed: %s", exc)
        return []

    out = []
    for p in data.get("data", [])[:limit]:
        ext = p.get("externalIds") or {}
        out.append(LitRef(
            title=p.get("title") or "(untitled)",
            source="semantic_scholar",
            authors=[a.get("name", "") for a in p.get("authors", [])][:8],
            year=p.get("year"),
            abstract=p.get("abstract") or "",
            venue=p.get("venue") or "",
            doi=ext.get("DOI"),
            url=p.get("url"),
            citations=p.get("citationCount"),
        ))
    return out


def search_crossref(query: str, limit: int = 10) -> list[LitRef]:
    params = {"query": query, "rows": limit}
    email = os.getenv("ECONOCLAST_CONTACT_EMAIL")
    if email:
        params["mailto"] = email
    try:
        r = httpx.get("https://api.crossref.org/works", params=params, headers=_ua(), timeout=_TIMEOUT)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
    except Exception as exc:  # noqa: BLE001
        log.warning("Crossref search failed: %s", exc)
        return []

    out = []
    for it in items[:limit]:
        title = (it.get("title") or ["(untitled)"])[0]
        authors = [f"{a.get('given','')} {a.get('family','')}".strip() for a in it.get("author", [])]
        year = None
        parts = (it.get("issued") or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
        out.append(LitRef(
            title=title, source="crossref", authors=authors[:8], year=year,
            abstract=it.get("abstract", "") or "",
            venue=(it.get("container-title") or [""])[0],
            doi=it.get("DOI"), url=it.get("URL"),
            citations=it.get("is-referenced-by-count"),
        ))
    return out


SOURCES = {
    "openalex": search_openalex,
    "arxiv": search_arxiv,
    "semantic_scholar": search_semantic_scholar,
    "crossref": search_crossref,
}


def _deinvert(inverted: dict | None) -> str:
    """OpenAlex returns abstracts as an inverted index; rebuild the text."""
    if not inverted:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)[:4000]
