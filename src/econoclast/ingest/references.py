"""Extract a paper's reference list and verify each entry against Crossref.

Fabricated or hallucinated citations are a real failure mode (they have slipped
past human reviewers into accepted papers). We split the bibliography into
entries and ask Crossref's reference matcher whether each one corresponds to a
real work. Entries that resolve poorly are flagged for a human to check; entries
without a DOI (many books and working papers) are reported as unresolved, not
fabricated.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

import httpx

from econoclast.logging import get_logger

log = get_logger("ingest.references")

_YEAR = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_NUM_ENTRY = re.compile(r"\n(?=\s*\[?\d{1,3}\]?[.)]\s+[A-Z])")
_NAME_ENTRY = re.compile(r"\n(?=[A-Z][A-Za-z'`-]+,\s+[A-Z])")
_WORD = re.compile(r"[a-z0-9]{2,}")


@dataclass
class RefCheck:
    text: str
    resolved: bool
    score: float
    matched_title: str = ""
    doi: str | None = None
    reason: str = ""


def extract_references(paper) -> list[str]:  # noqa: ANN001
    block = paper.section_text("references", "bibliography", "works cited")
    if not block or len(block) < 80:
        # Fall back to the tail of the document.
        m = re.search(r"\b(references|bibliography)\b", paper.text, re.IGNORECASE)
        block = paper.text[m.start():] if m else ""
    if not block:
        return []

    # Try numbered entries first, then hanging-indent author entries.
    parts = _NUM_ENTRY.split(block)
    if len(parts) < 4:
        parts = _NAME_ENTRY.split(block)
    entries = []
    for p in parts:
        s = re.sub(r"\s+", " ", p).strip(" .\n")
        if len(s) >= 30 and _YEAR.search(s) and len(s) < 600:
            entries.append(s)
    return entries[:60]


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _match_score(ref: str, item: dict) -> float:
    title = (item.get("title") or [""])[0]
    if not title:
        return 0.0
    tt = _tokens(title)
    if not tt:
        return 0.0
    overlap = len(tt & _tokens(ref)) / len(tt)
    # Year agreement is a strong signal.
    year = None
    parts = (item.get("issued") or {}).get("date-parts") or [[None]]
    if parts and parts[0] and parts[0][0]:
        year = str(parts[0][0])
    year_ok = bool(year and year in ref)
    return min(1.0, overlap + (0.15 if year_ok else 0.0))


def verify_references(refs: list[str], *, max_refs: int = 40) -> list[RefCheck]:
    if not refs:
        return []
    email = os.getenv("ECONOCLAST_CONTACT_EMAIL", "")
    headers = {"User-Agent": f"Econoclast/0.1 (mailto:{email})" if email else "Econoclast/0.1"}
    out: list[RefCheck] = []
    with httpx.Client(timeout=20.0, headers=headers) as client:
        for ref in refs[:max_refs]:
            try:
                r = client.get("https://api.crossref.org/works",
                               params={"query.bibliographic": ref[:300], "rows": 1})
                if r.status_code >= 400:
                    out.append(RefCheck(ref, False, 0.0, reason=f"crossref {r.status_code}"))
                    continue
                items = r.json().get("message", {}).get("items", [])
            except Exception as exc:  # noqa: BLE001
                out.append(RefCheck(ref, False, 0.0, reason=str(exc)[:60]))
                continue
            if not items:
                out.append(RefCheck(ref, False, 0.0, reason="no Crossref match"))
                continue
            item = items[0]
            score = _match_score(ref, item)
            out.append(RefCheck(
                text=ref, resolved=score >= 0.6, score=round(score, 2),
                matched_title=(item.get("title") or [""])[0][:160],
                doi=item.get("DOI"),
                reason="" if score >= 0.6 else "weak title/year match",
            ))
            time.sleep(0.05)  # be polite to Crossref
    return out
