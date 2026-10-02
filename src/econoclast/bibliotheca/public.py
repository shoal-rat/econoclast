"""Keyless public data the Sicarius can pull to rebuild a paper's data.

FRED series come from the public ``fredgraph.csv`` endpoint (no API key); World Bank
indicators from the open v2 API. Both land as tidy CSVs in the case's ``data/``.
Anything else (BLS, Census, Eurostat, OECD, IMF, a statistics office) the agent fetches
with its own tools.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (compatible; Econoclast/2; research replication)"}


def fred_series(series_id: str, dest: Path, *, start: str = "", end: str = "") -> Path:
    sid = re.sub(r"[^A-Za-z0-9_.-]", "", series_id).upper()
    if not sid:
        raise ValueError("empty FRED series id")
    params = {"id": sid}
    if start:
        params["cosd"] = start
    if end:
        params["coed"] = end
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params=params, headers=_UA,
                  timeout=60, follow_redirects=True)
    r.raise_for_status()
    if not r.text.lower().startswith(("observation_date", "date")):
        raise ValueError(f"FRED returned no CSV for {sid} (is the id right?)")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"fred_{sid}.csv"
    out.write_text(r.text, encoding="utf-8")
    return out


def worldbank_indicator(indicator: str, dest: Path, *, countries: str = "all",
                        start: str = "", end: str = "") -> Path:
    ind = re.sub(r"[^A-Za-z0-9_.]", "", indicator)
    ctry = re.sub(r"[^A-Za-z;]", "", countries) or "all"
    params = {"format": "json", "per_page": 20000}
    if start or end:
        params["date"] = f"{start or 1960}:{end or 2100}"
    url = f"https://api.worldbank.org/v2/country/{ctry}/indicator/{ind}"
    r = httpx.get(url, params=params, headers=_UA, timeout=90, follow_redirects=True)
    r.raise_for_status()
    payload = r.json()
    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        raise ValueError(f"World Bank returned no rows for {ind} ({payload[:1] if payload else 'empty'})")
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"wb_{ind}_{ctry.replace(';', '-')}.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["country", "iso3", "year", ind])
        for row in payload[1]:
            w.writerow([(row.get("country") or {}).get("value"), row.get("countryiso3code"),
                        row.get("date"), row.get("value")])
    return out
