"""Speculum, read in the code: every place the authors' scripts drop, filter or rewrite data.

Lists the data-shaping lines in Stata, R and Python replication code so the Sicarius can
compare them with what the paper says it did. A filter the paper never mentions, applied
right before the headline regression, is exactly the kind of quiet choice that moves a
result without faking anything.
"""

from __future__ import annotations

import re
from pathlib import Path

_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "stata": [
        ("drop", r"^\s*drop\s+if\b|^\s*keep\s+if\b|^\s*drop\s+in\b"),
        ("recode", r"^\s*(replace|recode)\b"),
        ("trim", r"winsor|trim|_pctile|xtile|\bcap\b.*p\(\d"),
        ("sample", r"\bif\s+(year|sample|_merge|state|country|age|treat)\b"),
        ("merge", r"^\s*(merge|joinby|append)\b"),
        ("weights", r"\[(a|p|f|i)?w(eight)?\s*="),
    ],
    "r": [
        ("drop", r"\bfilter\(|subset\(|\bdrop_na\(|na\.omit\(|\[\s*!?\w+\s*[<>=!]"),
        ("recode", r"\bmutate\(|\bifelse\(|case_when\(|recode\("),
        ("trim", r"winsor|quantile\(|trim"),
        ("merge", r"\b(left|inner|right|full|anti)_join\(|\bmerge\(|rbind\(|bind_rows\("),
        ("weights", r"weights\s*="),
    ],
    "python": [
        ("drop", r"\.drop(na)?\(|\.query\(|\.loc\[.*[<>=!]=?|\.dropna\("),
        ("recode", r"\.replace\(|np\.where\(|\.map\(|\.clip\("),
        ("trim", r"winsor|quantile\(|clip\("),
        ("merge", r"\.merge\(|pd\.concat\(|\.join\("),
        ("weights", r"weights\s*="),
    ],
}
_EXT = {".do": "stata", ".ado": "stata", ".r": "r", ".rmd": "r", ".qmd": "r", ".py": "python", ".ipynb": "python"}


def audit(root: str | Path, max_hits: int = 400) -> dict:
    root = Path(root)
    hits: list[dict] = []
    files = []
    for p in sorted(root.rglob("*")):
        lang = _EXT.get(p.suffix.lower())
        if not lang or not p.is_file() or p.stat().st_size > 5_000_000:
            continue
        files.append(str(p.relative_to(root)))
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith(("*", "//", "#")):
                continue
            for kind, pat in _PATTERNS[lang]:
                if re.search(pat, s, re.I):
                    hits.append({"file": str(p.relative_to(root)), "line": i, "kind": kind, "code": s[:200]})
                    break
            if len(hits) >= max_hits:
                break
    by_kind: dict[str, int] = {}
    for h in hits:
        by_kind[h["kind"]] = by_kind.get(h["kind"], 0) + 1
    return {"files": files[:200], "n_files": len(files), "steps": hits, "by_kind": by_kind}
