"""Resolve a path OR a URL into a local file Econoclast can read.

So a user (or an agent) can hand over a local path, a direct PDF link, an arXiv
abstract page, or a generic paper webpage — and Econoclast figures out the rest.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import httpx

from econoclast.logging import get_logger

log = get_logger("ingest.fetch")

_ARXIV_ABS = re.compile(r"arxiv\.org/abs/([\w.\-/]+)", re.IGNORECASE)
_ARXIV_PDF = re.compile(r"arxiv\.org/pdf/([\w.\-/]+?)(?:\.pdf)?$", re.IGNORECASE)
_HEADERS = {"User-Agent": "Econoclast/0.1 (+https://github.com/shoal-rat/econoclast)"}


def is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


def resolve_source(path_or_url: str, cache_dir: str | None = None, *, backend=None) -> str:  # noqa: ANN001
    """Return a local file path for ``path_or_url`` (downloading if it's a URL).

    Tries a plain HTTP fetch first. If that is blocked (403, Cloudflare, a JS-gated
    page), it hands the download to the agent (``backend``): the agent uses its own
    browser or tools to get past the wall and save the file.
    """
    if not is_url(path_or_url):
        return path_or_url

    out_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)
    url = _canonicalize(path_or_url)
    log.info("Fetching %s", url)

    try:
        return _http_fetch(url, out_dir)
    except httpx.HTTPError as exc:
        log.warning("Direct fetch failed (%s); asking the agent to fetch it.", exc)

    got = _agent_paper(url, out_dir, backend)
    if got:
        return got
    raise RuntimeError(f"Could not fetch {url} (the direct path and the agent fallback both failed).")


def _http_fetch(url: str, out_dir: Path) -> str:
    with httpx.Client(follow_redirects=True, timeout=60.0, headers=_HEADERS) as client:
        resp = client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "").lower()

        if "pdf" in ctype or url.lower().endswith(".pdf"):
            dest = out_dir / (_safe_name(url) + ".pdf")
            dest.write_bytes(resp.content)
            return str(dest)

        html = resp.text
        # If it's a landing page, try to find a PDF link and follow it.
        pdf_link = _find_pdf_link(html, str(resp.url))
        if pdf_link:
            try:
                pr = client.get(pdf_link)
                if pr.status_code < 400 and "pdf" in pr.headers.get("content-type", "").lower():
                    dest = out_dir / (_safe_name(pdf_link) + ".pdf")
                    dest.write_bytes(pr.content)
                    return str(dest)
            except httpx.HTTPError:
                pass
        # Fall back to readable text from the HTML.
        dest = out_dir / (_safe_name(url) + ".txt")
        dest.write_text(_html_to_text(html), encoding="utf-8")
        return str(dest)


def _agent_paper(url: str, out_dir: Path, backend=None) -> str | None:  # noqa: ANN001
    """Delegate a blocked paper download to the agent; return the file it saved."""
    if backend is None:
        log.warning("No agent backend available to fetch the blocked URL.")
        return None
    new = backend.fetch_into(out_dir, url=url, what=f"the full-text PDF of the paper at {url}")
    pdfs = [p for p in new if p.suffix.lower() == ".pdf"]
    if pdfs:
        return str(pdfs[0])
    readable = [p for p in new if p.suffix.lower() in (".txt", ".html", ".htm", ".tex", ".md")]
    if readable:
        return str(readable[0])
    return None


def _canonicalize(url: str) -> str:
    m = _ARXIV_ABS.search(url)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}.pdf"
    m = _ARXIV_PDF.search(url)
    if m and not url.lower().endswith(".pdf"):
        return f"https://arxiv.org/pdf/{m.group(1)}.pdf"
    return url


def _find_pdf_link(html: str, base: str) -> str | None:
    # citation_pdf_url meta tag (used by most journals/repositories).
    m = re.search(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']',
                  html, re.IGNORECASE)
    if m:
        return _abs_url(m.group(1), base)
    m = re.search(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE)
    if m:
        return _abs_url(m.group(1), base)
    return None


def _abs_url(link: str, base: str) -> str:
    from urllib.parse import urljoin

    return urljoin(base, link)


def _html_to_text(html: str) -> str:
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    from html import unescape

    text = unescape(html)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _safe_name(url: str) -> str:
    name = re.sub(r"[^\w.\-]+", "_", url.split("//", 1)[-1])
    return ("econoclast_" + name)[:80]
