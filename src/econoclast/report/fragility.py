"""The fragility score.

Aggregates findings into a single 0-100 "fragility" number plus a category
breakdown and a verdict band. The score saturates (many medium findings can't
exceed a couple of decisive ones) and an *integrity override* forces a high band
whenever a deterministic test proves a reported number impossible or a p-value
inconsistency flips significance.
"""

from __future__ import annotations

import math

from econoclast.attacks.base import Finding

BANDS = [
    (15, "Robust", "No material concerns surfaced."),
    (35, "Minor concerns", "Small issues; the headline result is probably safe."),
    (60, "Material concerns", "Real weaknesses; the result may not survive scrutiny."),
    (80, "Fragile", "The central claim looks fragile to plausible alternative choices."),
    (101, "Severe", "Severe problems; treat the central claim as unsupported until addressed."),
]


def _band(score: float, integrity: bool) -> tuple[str, str]:
    for ceiling, label, blurb in BANDS:
        if score < ceiling:
            if integrity and ceiling <= 35:
                # Integrity violations can't be "minor".
                return "Material concerns", "A reported statistic is internally impossible or inconsistent — " + blurb
            return label, blurb
    return BANDS[-1][1], BANDS[-1][2]


def compute_fragility(findings: list[Finding], forensic_results: list[dict]) -> dict:
    raw = sum(f.weight for f in findings)
    score = round(100 * (1 - math.exp(-raw / 12.0)), 1)

    # Integrity override: statcheck decision errors or GRIM/GRIMMER impossibilities.
    integrity = False
    for r in forensic_results:
        if r.get("verdict") == "suspicious" and r.get("name") in ("statcheck", "grim", "grimmer"):
            if r.get("name") == "statcheck" and r.get("stats", {}).get("decision_errors", 0) > 0:
                integrity = True
            elif r.get("name") in ("grim", "grimmer") and r.get("stats", {}).get("inconsistent", 0) > 0:
                integrity = True
    if integrity:
        score = max(score, 45.0)

    band, blurb = _band(score, integrity)

    by_category: dict[str, float] = {}
    by_severity: dict[str, int] = {}
    for f in findings:
        by_category[f.category] = round(by_category.get(f.category, 0.0) + f.weight, 2)
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    return {
        "score": score,
        "band": band,
        "band_blurb": blurb,
        "integrity_violation": integrity,
        "n_findings": len(findings),
        "raw_weight": round(raw, 2),
        "by_category": dict(sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)),
        "by_severity": by_severity,
    }
