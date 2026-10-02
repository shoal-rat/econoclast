"""Palimpsestus: what was scraped off the parchment and written over.

Compares two versions of a paper (a working paper and the published article, two arXiv
versions, a pre-analysis plan and the final text) and reports what changed where it
matters: sentences that carry claims or numbers, the reported estimates, the sample sizes,
and the outcomes named in each. Changes are normal; undisclosed changes that move the
headline are what the Sicarius is looking for.
"""

from __future__ import annotations

import difflib
import re

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")
_CLAIM = re.compile(r"\b(we find|we show|results? (?:show|suggest|indicate)|significant|effect|increase|"
                    r"decrease|reduce|raise|causal|impact|outcome|primary|hypothes|sample|robust)\b", re.I)
_OUTCOME = re.compile(r"\b(?:primary|main|secondary)\s+outcomes?\b[^.]{0,160}", re.I)
_N = re.compile(r"\b[Nn]\s*=\s*([\d,]{2,9})")


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in _SENT.split(text) if 25 <= len(s.strip()) <= 600]


def compare(old_text: str, new_text: str, *, old_label: str = "earlier", new_label: str = "later") -> dict:
    old_s, new_s = _sentences(old_text), _sentences(new_text)
    old_set, new_set = set(old_s), set(new_s)
    removed = [s for s in old_s if s not in new_set and (_CLAIM.search(s) or re.search(r"\d", s))]
    added = [s for s in new_s if s not in old_set and (_CLAIM.search(s) or re.search(r"\d", s))]

    # pair up rewritten sentences so the traveller sees before -> after
    rewritten = []
    for s in removed[:200]:
        match = difflib.get_close_matches(s, added, n=1, cutoff=0.6)
        if match:
            rewritten.append({"before": s, "after": match[0]})
    paired_after = {r["after"] for r in rewritten}
    paired_before = {r["before"] for r in rewritten}

    from econoclast.tesserae.claims import extract_statistics

    def estimates(t: str) -> set[tuple]:
        return {(c.coef, c.se) for c in extract_statistics(t) if c.coef is not None}

    est_old, est_new = estimates(old_text), estimates(new_text)
    return {
        "old": old_label, "new": new_label,
        "similarity": round(difflib.SequenceMatcher(None, old_text[:200000], new_text[:200000]).quick_ratio(), 3),
        "rewritten": rewritten[:30],
        "removed": [s for s in removed if s not in paired_before][:30],
        "added": [s for s in added if s not in paired_after][:30],
        "estimates_only_in_old": sorted(est_old - est_new, key=str)[:30],
        "estimates_only_in_new": sorted(est_new - est_old, key=str)[:30],
        "outcomes_old": [m.group(0) for m in _OUTCOME.finditer(old_text)][:10],
        "outcomes_new": [m.group(0) for m in _OUTCOME.finditer(new_text)][:10],
        "sample_sizes_old": sorted({m.group(1) for m in _N.finditer(old_text)})[:20],
        "sample_sizes_new": sorted({m.group(1) for m in _N.finditer(new_text)})[:20],
    }
