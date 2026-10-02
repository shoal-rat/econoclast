"""Download a discovered dataset and locate its main tabular file.

Best-effort and fail-soft: each source is tried with a timeout, archives are
unzipped, and the tabular file most likely to be the analysis dataset is chosen.
openICPSR (the AEA archive) needs a login: the Sicarius is told to try its browser
and, failing that, to ask the traveller for the package.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx

from econoclast.bibliotheca.datalinks import DataLink
from econoclast.log import get_logger

log = get_logger("replication.acquire")

_TABULAR = (".csv", ".dta", ".tsv", ".parquet", ".xlsx", ".xls", ".sav", ".rds", ".rdata", ".feather")
_HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 Econoclast/2")}
_TIMEOUT = 120.0
_MAX_BYTES = 500 * 1024 * 1024  # 500 MB cap


def acquire_dataset(link: DataLink, dest_dir: str | Path) -> list[Path]:
    """Download a dataset link into ``dest_dir`` and return every file it produced.

    Archives are unpacked whole (code included) so the Sicarius can read the authors'
    scripts; ``tabular_files`` picks out the tables.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    if not link.supported:
        raise PermissionError(f"{link.kind} deposits need a login ({link.url}).")
    with httpx.Client(follow_redirects=True, timeout=_TIMEOUT, headers=_HEADERS) as client:
        return _dispatch(client, link, dest)


def _dispatch(client, link: DataLink, dest: Path) -> list[Path]:  # noqa: ANN001
    if link.kind == "zenodo":
        return _zenodo(client, link.ref, dest)
    if link.kind == "github":
        return _github(client, link.ref, dest)
    if link.kind == "dataverse":
        host = "dataverse.harvard.edu"
        if "://" in link.url and "dataverse" in link.url.split("/")[2]:
            host = link.url.split("/")[2]
        doi = link.ref if link.ref.lower().startswith("10.") else link.ref.replace("doi:", "")
        url = f"https://{host}/api/access/dataset/:persistentId/?persistentId=doi:{doi}"
        return _download_any(client, url, dest, name=f"dataverse_{doi.split('/')[-1]}.zip")
    if link.kind == "direct":
        return _download_any(client, link.url, dest)
    if link.kind == "osf":
        return _osf(client, link.ref, dest)
    return []



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
    """Save a download; unpack archives whole (guarding against path traversal)."""
    if name.lower().endswith(".zip") or content[:2] == b"PK":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
        except zipfile.BadZipFile:
            zf = None
        if zf is not None:
            root = (dest / Path(name).stem).resolve()
            extracted = []
            for member in zf.infolist():
                if member.is_dir() or member.filename.startswith("__MACOSX"):
                    continue
                target = (root / member.filename).resolve()
                if not str(target).startswith(str(root)):
                    continue  # zip-slip
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                extracted.append(target)
            return extracted
    target = dest / name
    target.write_bytes(content)
    return [target]


def tabular_files(paths: list[Path]) -> list[Path]:
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
    if suf in (".sav", ".rds", ".rdata", ".feather", ".xls"):
        return []
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
