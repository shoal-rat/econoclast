"""Browser-backed fetching, for the many sites with anti-crawler defences.

The plain HTTP path (httpx) is fast but bounces off Cloudflare challenges,
JavaScript-gated pages, cookie walls, and plain 403s. When it fails, Econoclast
falls back to a real headless browser (Playwright): it renders the page, carries
the clearance cookies the site set, and pulls the file through the warmed-up
context. When even the direct link is dead, it lets the browser search the web
and the model pick the most likely hit, then downloads that.

The browser is optional. Enable it with:

    pip install "econoclast[browser]"
    playwright install chromium      # or rely on your installed Chrome

Without it, the fallback is skipped with a one-line note and the direct path's
error stands.
"""

from __future__ import annotations

from urllib.parse import parse_qs, quote, urljoin, urlparse

from econoclast.llm.base import Message
from econoclast.logging import get_logger

log = get_logger("ingest.browser")

# A current desktop-Chrome UA; the default Playwright UA is often blocked.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_TIMEOUT_MS = 45000
_SETTLE_MS = 2500  # give a Cloudflare / JS challenge a moment to resolve
_MAX_BYTES = 500 * 1024 * 1024


def browser_available() -> bool:
    """True if Playwright is importable (a browser binary may still be needed)."""
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _hint() -> None:
    log.warning("A site blocked the direct download. Install the browser fallback to get past it: "
                "pip install \"econoclast[browser]\" && playwright install chromium")


# --------------------------------------------------------------------------- #
# Low-level browser session
# --------------------------------------------------------------------------- #
def _launch(p):  # noqa: ANN001
    """Launch headless Chromium, preferring the user's installed Chrome (no download)."""
    last: Exception | None = None
    for kw in ({"channel": "chrome"}, {"channel": "msedge"}, {}):
        try:
            return p.chromium.launch(headless=True, **kw)
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last if last else RuntimeError("could not launch a browser")


def _session(fn):  # noqa: ANN001
    """Run ``fn(page, ctx)`` inside a fresh browser context; return its result or None."""
    if not browser_available():
        _hint()
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _hint()
        return None
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            try:
                ctx = browser.new_context(user_agent=_UA, accept_downloads=True,
                                          ignore_https_errors=True)
                page = ctx.new_page()
                page.set_default_timeout(_TIMEOUT_MS)
                return fn(page, ctx)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("browser session failed: %s", exc)
        return None


def _warm(page, url: str) -> None:  # noqa: ANN001
    """Navigate so the context picks up cookies / clears the bot challenge."""
    try:
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(_SETTLE_MS)
    except Exception as exc:  # noqa: BLE001 - a download/challenge can abort navigation
        log.debug("warm navigation to %s aborted: %s", url, exc)


def _request_bytes(ctx, url: str):  # noqa: ANN001
    """Fetch raw bytes through the warmed context (carries cookies). (bytes, ctype) or None."""
    try:
        r = ctx.request.get(url, timeout=_TIMEOUT_MS)
    except Exception:  # noqa: BLE001
        return None
    if not r.ok:
        return None
    ctype = (r.headers or {}).get("content-type", "").lower()
    try:
        body = r.body()
    except Exception:  # noqa: BLE001
        return None
    if not body or len(body) > _MAX_BYTES:
        return None
    return body, ctype


def _find_file_link(page, prefer_ext: tuple[str, ...]) -> str | None:  # noqa: ANN001
    """Find a likely file link in the rendered DOM (citation_pdf_url meta or a matching href)."""
    try:
        meta = page.query_selector('meta[name="citation_pdf_url"]')
        if meta:
            href = meta.get_attribute("content")
            if href:
                return urljoin(page.url, href)
        exts = prefer_ext or (".pdf",)
        for a in page.query_selector_all("a[href]"):
            href = a.get_attribute("href") or ""
            tail = href.lower().split("?")[0]
            if any(tail.endswith(e) for e in exts):
                return urljoin(page.url, href)
    except Exception:  # noqa: BLE001
        return None
    return None


def _is_file(ctype: str, body: bytes) -> bool:
    """A real downloadable file, not an HTML challenge/landing page."""
    if "html" in ctype or "xml" in ctype and b"<html" in body[:200].lower():
        return False
    if body[:15].lstrip().lower().startswith(b"<!doctype html") or body[:6].lower() == b"<html>":
        return False
    return True


# --------------------------------------------------------------------------- #
# Public: fetch a file, fetch a page, search
# --------------------------------------------------------------------------- #
def browser_fetch_file(url: str, *, prefer_ext: tuple[str, ...] = ()):  # -> (bytes, ctype) | None
    """Open ``url`` in a browser and return a real FILE as (bytes, content_type).

    Returns None if the page only yields HTML or the fetch fails. Use
    :func:`browser_fetch_page` when you want the rendered page text instead.
    """
    def run(page, ctx):  # noqa: ANN001
        _warm(page, url)
        got = _request_bytes(ctx, url)
        if got and _is_file(got[1], got[0]):
            return got
        link = _find_file_link(page, prefer_ext)
        if link:
            got = _request_bytes(ctx, link)
            if got and _is_file(got[1], got[0]):
                return got
        return None
    return _session(run)


def browser_fetch_page(url: str) -> str | None:
    """Open ``url`` in a browser and return the rendered HTML (for paper landing pages)."""
    def run(page, ctx):  # noqa: ANN001
        _warm(page, url)
        try:
            return page.content()
        except Exception:  # noqa: BLE001
            return None
    return _session(run)


def browser_search(query: str, *, limit: int = 8) -> list[tuple[str, str]]:
    """Search the web in a browser and return [(title, url), ...]."""
    def run(page, ctx):  # noqa: ANN001
        out: list[tuple[str, str]] = []
        try:
            page.goto("https://html.duckduckgo.com/html/?q=" + quote(query),
                      wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            for a in page.query_selector_all("a.result__a")[:limit]:
                href = a.get_attribute("href") or ""
                title = (a.inner_text() or "").strip()
                real = _unwrap_ddg(href)
                if real:
                    out.append((title, real))
        except Exception as exc:  # noqa: BLE001
            log.warning("browser search failed: %s", exc)
        return out
    return _session(run) or []


def _unwrap_ddg(href: str) -> str:
    """DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<encoded>; unwrap it."""
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        qs = parse_qs(urlparse(href).query)
        return (qs.get("uddg") or [""])[0]
    return href if href.startswith("http") else ""


# --------------------------------------------------------------------------- #
# Public: let the model pick the best search hit (the native-LLM step)
# --------------------------------------------------------------------------- #
_RANK_SYSTEM = (
    "You are picking which search result most likely hosts a downloadable resource (a paper PDF or a "
    "dataset/replication file) for the request. Prefer official repositories and publisher/author "
    "pages over blogs, summaries, or paywalls."
)


def rank_candidates(query: str, candidates: list[tuple[str, str]], backend=None) -> list[str]:  # noqa: ANN001
    """Order candidate URLs by likelihood of hosting the resource for ``query``.

    With a backend, the model ranks them; otherwise the original order is kept.
    """
    urls = [u for _, u in candidates if u]
    if backend is None or len(urls) <= 1:
        return urls
    listing = "\n".join(f"{i}. {t or '(no title)'} -> {u}" for i, (t, u) in enumerate(candidates) if u)
    contract = ('Return ONLY a JSON array of the URLs, best first, e.g. ["https://a", "https://b"]. '
                "Include only URLs from the list.")
    try:
        resp = backend.complete("extractor", [
            Message(role="system", content=_RANK_SYSTEM + "\n\n" + contract),
            Message(role="user", content=f"Request: {query}\n\nResults:\n{listing}"),
        ], response_format="json")
        data = resp.json()
        if isinstance(data, list):
            ranked = [u for u in data if isinstance(u, str) and u in urls]
            # Append any the model dropped, preserving discovery order.
            ranked += [u for u in urls if u not in ranked]
            return ranked
    except Exception as exc:  # noqa: BLE001
        log.warning("candidate ranking failed, keeping search order: %s", exc)
    return urls
