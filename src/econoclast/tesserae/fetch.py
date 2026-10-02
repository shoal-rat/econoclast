"""Resolve a path OR a URL into a local file Econoclast can read.

A local path, a direct PDF link, an arXiv abstract page, a DOI, or a generic paper
webpage. This is the polite first try. When a publisher blocks it (a 403, a Cloudflare
or JavaScript wall), the error says so plainly and the Sicarius takes over with its own
browser, curl with cookies, or a search for an open mirror.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import httpx

from econoclast.log import get_logger

log = get_logger("ingest.fetch")

_ARXIV_ABS = re.compile(r"arxiv\.org/abs/([\w.\-/]+)", re.IGNORECASE)
_ARXIV_PDF = re.compile(r"arxiv\.org/pdf/([\w.\-/]+?)(?:\.pdf)?$", re.IGNORECASE)
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36 Econoclast/2"),
    "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
}


def is_url(s: str) -> bool:
    return s.lower().startswith(("http://", "https://"))


class FetchBlocked(RuntimeError):
    """The plain download was refused; a browser or a mirror is needed."""


def resolve_source(path_or_url: str, cache_dir: str | None = None) -> str:
    """Return a local file path for ``path_or_url`` (downloading if it's a URL)."""
    if not is_url(path_or_url):
        return path_or_url

    out_dir = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir())
    out_dir.mkdir(parents=True, exist_ok=True)
    url = _canonicalize(path_or_url)
    log.info("Fetching %s", url)

    try:
        return _http_fetch(url, out_dir)
    except httpx.HTTPError as exc:
        raise FetchBlocked(f"Plain download of {url} failed ({exc}). Use a browser, curl with a "
                           "browser User-Agent, or find an open mirror (arXiv, SSRN, NBER, RePEc, "
                           "the author's page).") from exc


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



def _canonicalize(url: str) -> str:
    if url.lower().startswith("doi:"):
        url = "https://doi.org/" + url[4:].strip()
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
