"""Find the dataset a paper relies on, from the paper itself.

Most empirical papers now carry a data-availability statement pointing at Zenodo,
a Dataverse, OSF, an openICPSR deposit, a GitHub repo, or a direct file. This
module locates those pointers so the dataset can be fetched automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HOST_PATTERNS = [
    ("zenodo", re.compile(r"(?:zenodo\.org/record(?:s)?/(\d+)|10\.5281/zenodo\.(\d+))", re.I)),
    ("dataverse", re.compile(r"(?:doi:|doi\.org/|persistentId=doi:)\s*(10\.7910/DVN/[A-Z0-9]+)", re.I)),
    ("dataverse", re.compile(r"dataverse[\w.]*/dataset\.xhtml\?persistentId=([^\s&\"')]+)", re.I)),
    ("icpsr", re.compile(r"(?:openicpsr\.org/openicpsr/project/(\d+)|10\.3886/E(\d+))", re.I)),
    ("osf", re.compile(r"osf\.io/([a-z0-9]{5})", re.I)),
    ("github", re.compile(r"github\.com/([\w.-]+/[\w.-]+?)(?:\.git|/|\s|$)", re.I)),
    ("direct", re.compile(r"https?://[^\s\"')]+\.(?:csv|dta|xlsx|tsv|parquet|zip)\b", re.I)),
]

# Words that signal we're near a data-availability statement.
_DATA_CTX = re.compile(
    r"\b(data\s+availab|replication|supplementary|deposited|archive|repository|"
    r"data\s+and\s+code|publicly\s+available|dataset)\b", re.I)


@dataclass
class DataLink:
    kind: str  # zenodo | dataverse | icpsr | osf | github | direct
    ref: str  # id, DOI, repo, or url
    url: str
    context: str = ""
    score: float = 0.0
    supported: bool = True


def find_dataset_links(paper) -> list[DataLink]:  # noqa: ANN001 (Paper)
    text = paper.text
    # Prioritise the data-availability section if we can find one.
    da = paper.section_text("data availab", "availability", "replication", "data and code")
    links: list[DataLink] = []
    seen: set[str] = set()

    for kind, pat in _HOST_PATTERNS:
        for m in pat.finditer(text):
            ref, url = _normalise(kind, m)
            if not ref or url in seen:
                continue
            seen.add(url)
            ctx = text[max(0, m.start() - 80): m.end() + 80].replace("\n", " ").strip()
            score = 1.0
            if _DATA_CTX.search(ctx):
                score += 1.5
            if da and ref in da:
                score += 1.5
            links.append(DataLink(kind=kind, ref=ref, url=url, context=ctx[:200],
                                  score=score, supported=kind != "icpsr"))

    links.sort(key=lambda link_: link_.score, reverse=True)
    return links


def _normalise(kind: str, m: re.Match) -> tuple[str, str]:
    if kind == "zenodo":
        rid = m.group(1) or m.group(2)
        return (rid or "", f"https://zenodo.org/records/{rid}")
    if kind == "dataverse":
        raw = m.group(1) or ""
        doi = raw.replace("doi:", "").replace("doi%3A", "").strip()
        url = ("https://dataverse.harvard.edu/api/access/dataset/:persistentId/"
               f"?persistentId=doi:{doi}")
        return (doi, url)
    if kind == "icpsr":
        pid = m.group(1) or m.group(2)
        return (pid or "", f"https://www.openicpsr.org/openicpsr/project/{pid}")
    if kind == "osf":
        oid = m.group(1)
        return (oid, f"https://osf.io/{oid}/")
    if kind == "github":
        repo = m.group(1).rstrip("/")
        return (repo, f"https://github.com/{repo}")
    # direct
    return (m.group(0), m.group(0))
