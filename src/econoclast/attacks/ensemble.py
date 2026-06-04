"""Ensemble voting over findings.

Run an LLM attack several times (different samples, and different models when the
route has them), then keep only the findings that recur. Singletons are dropped
as likely noise. This is the variance-reduction recipe from the AI-Scientist and
ICLR-2025 review-agent work.
"""

from __future__ import annotations

import math
import re

from econoclast.attacks.base import Finding

_WORD = re.compile(r"[a-z0-9]{3,}")


def _title_tokens(title: str) -> set[str]:
    return set(_WORD.findall(title.lower()))


def _same_issue(a: Finding, b: Finding) -> bool:
    if a.category != b.category:
        return False
    ta, tb = _title_tokens(a.title), _title_tokens(b.title)
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    return jaccard >= 0.45


def vote_findings(runs: list[list[Finding]], *, min_votes: int | None = None) -> list[Finding]:
    """Cluster findings across runs and keep those with majority support."""
    n_runs = len(runs)
    if n_runs <= 1:
        return runs[0] if runs else []
    if min_votes is None:
        min_votes = math.ceil(n_runs / 2)

    clusters: list[dict] = []
    for run_idx, findings in enumerate(runs):
        for f in findings:
            for c in clusters:
                if _same_issue(c["rep"], f):
                    c["members"].append(f)
                    c["runs"].add(run_idx)
                    break
            else:
                clusters.append({"rep": f, "members": [f], "runs": {run_idx}})

    kept: list[Finding] = []
    for c in clusters:
        votes = len(c["runs"])
        if votes < min_votes:
            continue
        rep: Finding = max(c["members"], key=lambda f: f.confidence)
        support = votes / n_runs
        rep.confidence = round(min(1.0, rep.confidence * (0.6 + 0.4 * support)), 3)
        rep.data["ensemble_votes"] = f"{votes}/{n_runs}"
        kept.append(rep)
    return kept
