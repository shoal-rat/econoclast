"""Download a discovered dataset and locate its main tabular file.

Best-effort and fail-soft: each source is tried with a timeout, archives are
unzipped, and the tabular file most likely to be the analysis dataset is chosen.
openICPSR (the AEA archive) needs a login and is reported as unsupported.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx

from econoclast.logging import get_logger
from econoclast.replication.discover import DataLink

log = get_logger("replication.acquire")

_TABULAR = (".csv", ".dta", ".tsv", ".parquet", ".xlsx")
_TIMEOUT = 120.0
_MAX_BYTES = 500 * 1024 * 1024  # 500 MB cap


def acquire_dataset(link: DataLink, dest_dir: str | Path, *, query: str | None = None,
                    backend=None) -> list[Path]:  # noqa: ANN001
    """Download a dataset link and return its tabular files.

    Tries the plain HTTP path first. If that is blocked or the link is dead, it
    falls back to a real browser, and then to a browser web search (with the model
    ranking the hits) so an anti-crawler wall does not end the run. ``query`` is the
    paper's title/availability text used for that search.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    if link.supported:
        try:
            with httpx.Client(follow_redirects=True, timeout=_TIMEOUT,
                              headers={"User-Agent": "Econoclast/0.1"}) as client:
                files = _dispatch(client, link, dest)
        except Exception as exc:  # noqa: BLE001
            log.warning("Dataset download failed for %s: %s", link.url, exc)
    else:
        log.warning("%s deposits need a login; trying the browser/search fallback (%s).",
                    link.kind, link.ref)
    if files:
        return files
    return _browser_dataset(link.url, dest, query=query, backend=backend)


def _dispatch(client, link: DataLink, dest: Path) -> list[Path]:  # noqa: ANN001
    if link.kind == "zenodo":
        return _zenodo(client, link.ref, dest)
    if link.kind == "github":
        return _github(client, link.ref, dest)
    if link.kind in ("direct", "dataverse"):
        return _download_any(client, link.url, dest)
    if link.kind == "osf":
        return _osf(client, link.ref, dest)
    return []


def _browser_dataset(url: str, dest: Path, *, query: str | None, backend) -> list[Path]:  # noqa: ANN001
    """Browser fallback: render the link past any anti-crawler wall, then search if it's dead."""
    from econoclast.ingest.browser import (
        browser_available,
        browser_fetch_file,
        browser_search,
        rank_candidates,
    )

    if not browser_available():
        return []
    want = _TABULAR + (".zip",)
    if url:
        files = _ingest_bytes(browser_fetch_file(url, prefer_ext=want), dest, url)
        if files:
            log.info("Acquired dataset via the browser from %s", url)
            return files
    if query:
        candidates = browser_search(f"{query} dataset replication files")
        for cand in rank_candidates(query, candidates, backend)[:5]:
            files = _ingest_bytes(browser_fetch_file(cand, prefer_ext=want), dest, cand)
            if files:
                log.info("Acquired dataset via a browser search from %s", cand)
                return files
    return []


def _ingest_bytes(got, dest: Path, url: str) -> list[Path]:  # noqa: ANN001
    """Save (bytes, content_type) from the browser and return any tabular files."""
    if not got:
        return []
    body, ctype = got
    if len(body) > _MAX_BYTES:
        return []
    name = _name_from_url(url, ctype)
    if "." not in name and (body[:2] == b"PK" or "zip" in ctype):
        name += ".zip"
    return _save_and_maybe_unzip(body, dest, name)


def _zenodo(client, rid: str, dest: Path) -> list[Path]:
    r = client.get(f"https://zenodo.org/api/records/{rid}")
    r.raise_for_status()
    files = r.json().get("files", [])
    out: list[Path] = []
    # Prefer tabular files and archives; cap how many we pull.
    files.sort(key=lambda f: (0 if str(f.get("key", "")).lower().endswith(_TABULAR + (".zip",)) else 1))
    for f in files[:6]:
        url = (f.get("links", {}) or {}).get("self") or f.get("links", {}).get("download")
        if url:
            out += _download_any(client, url, dest, name=f.get("key"))
    return out


def _github(client, repo: str, dest: Path) -> list[Path]:
    for branch in ("main", "master"):
        url = f"https://github.com/{repo}/archive/refs/heads/{branch}.zip"
        try:
            resp = client.get(url)
            if resp.status_code < 400:
                return _save_and_maybe_unzip(resp.content, dest, name=f"{repo.split('/')[-1]}.zip")
        except httpx.HTTPError:
            continue
    return []


def _osf(client, oid: str, dest: Path) -> list[Path]:
    # OSF: download the whole storage as a zip.
    url = f"https://files.osf.io/v1/resources/{oid}/providers/osfstorage/?zip="
    resp = client.get(url)
    resp.raise_for_status()
    return _save_and_maybe_unzip(resp.content, dest, name=f"osf_{oid}.zip")


def _download_any(client, url: str, dest: Path, name: str | None = None) -> list[Path]:
    resp = client.get(url)
    resp.raise_for_status()
    content = resp.content
    if len(content) > _MAX_BYTES:
        log.warning("Dataset at %s exceeds the size cap; skipping.", url)
        return []
    fname = name or _name_from_url(url, resp.headers.get("content-type", ""))
    return _save_and_maybe_unzip(content, dest, name=fname)


def _save_and_maybe_unzip(content: bytes, dest: Path, name: str) -> list[Path]:
    if name.lower().endswith(".zip") or content[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            extracted = []
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                if Path(member).suffix.lower() in _TABULAR:
                    target = dest / Path(member).name
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    extracted.append(target)
            return extracted
        except zipfile.BadZipFile:
            pass
    target = dest / name
    target.write_bytes(content)
    return [target] if target.suffix.lower() in _TABULAR else []


def find_tabular_files(paths: list[Path]) -> list[Path]:
    return [p for p in paths if p.suffix.lower() in _TABULAR]


def pick_main_table(tables: list[Path], paper) -> Path | None:  # noqa: ANN001
    """Choose the table most likely to be the analysis dataset.

    Heuristic: prefer the file whose column names overlap most with words in the
    paper's empirical sections; break ties by size.
    """
    if not tables:
        return None
    if len(tables) == 1:
        return tables[0]
    import re

    words = set(re.findall(r"[a-z]{3,}", (paper.section_text("data", "result", "estimat") or paper.text).lower()))
    best, best_score = tables[0], -1.0
    for t in tables:
        try:
            cols = _columns(t)
        except Exception:  # noqa: BLE001
            continue
        overlap = sum(1 for c in cols if c.lower() in words)
        size = t.stat().st_size if t.exists() else 0
        score = overlap + min(size / 1e7, 2.0)
        if score > best_score:
            best, best_score = t, score
    return best


def _columns(path: Path) -> list[str]:
    import pandas as pd

    suf = path.suffix.lower()
    if suf == ".csv":
        return list(pd.read_csv(path, nrows=5).columns)
    if suf == ".tsv":
        return list(pd.read_csv(path, sep="\t", nrows=5).columns)
    if suf == ".dta":
        return list(pd.read_stata(path, convert_categoricals=False).columns)
    if suf == ".parquet":
        return list(pd.read_parquet(path).columns)
    if suf == ".xlsx":
        return list(pd.read_excel(path, nrows=5).columns)
    return []


def _name_from_url(url: str, ctype: str) -> str:
    base = url.split("?")[0].rstrip("/").split("/")[-1] or "dataset"
    if "." not in base:
        if "zip" in ctype:
            base += ".zip"
        elif "csv" in ctype:
            base += ".csv"
    return base
