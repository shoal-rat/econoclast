"""Detect which identification strategies a paper uses.

Used to *gate* design-specific attacks (don't run the RDD critique on a paper
with no running variable) and to tailor LLM prompts.
"""

from __future__ import annotations

import re

_PATTERNS: dict[str, list[str]] = {
    "did": [
        r"difference[- ]in[- ]differences", r"\bDiD\b", r"\bDID\b", r"parallel trends?",
        r"two[- ]way fixed effects", r"\bTWFE\b", r"event[- ]stud(y|ies)", r"staggered (adoption|treatment)",
        r"Callaway.{0,5}Sant'?Anna", r"Goodman[- ]Bacon", r"Sun.{0,5}Abraham",
    ],
    "rdd": [
        r"regression discontinuity", r"\bRDD?\b", r"running variable", r"forcing variable",
        r"bandwidth", r"McCrary", r"\bcutoff\b", r"\brdrobust\b", r"local (linear|polynomial)",
        r"manipulation test",
    ],
    "iv": [
        r"instrumental variabl", r"\bIV\b", r"two[- ]stage least squares", r"\b2SLS\b",
        r"exclusion restriction", r"first[- ]stage", r"weak instrument", r"Stock.{0,5}Yogo",
        r"Hansen J", r"over[- ]identif", r"Kleibergen.{0,5}Paap",
    ],
    "matching": [
        r"propensity score", r"\bmatching\b", r"nearest neighbou?r", r"inverse probability",
        r"\bIPW\b", r"entropy balancing", r"synthetic control",
    ],
    "panel_fe": [
        r"fixed effects", r"random effects", r"panel data", r"within estimator", r"clustered standard errors",
    ],
    "rct": [
        r"randomi[sz]ed controlled trial", r"\bRCT\b", r"randomi[sz]ation", r"treatment arm",
        r"field experiment", r"randomly assigned",
    ],
    "structural": [
        r"\bBLP\b", r"nested logit", r"discrete choice", r"GMM", r"structural (model|estimation)",
        r"demand estimation", r"random coefficients",
    ],
}


def detect_designs(text: str) -> set[str]:
    low = text
    found = set()
    for design, pats in _PATTERNS.items():
        for p in pats:
            if re.search(p, low, re.IGNORECASE):
                found.add(design)
                break
    return found


def design_label(designs: set[str]) -> str:
    names = {
        "did": "difference-in-differences",
        "rdd": "regression discontinuity",
        "iv": "instrumental variables",
        "matching": "matching/weighting",
        "panel_fe": "panel fixed effects",
        "rct": "randomised experiment",
        "structural": "structural estimation",
    }
    if not designs:
        return "unclear / descriptive"
    return ", ".join(names.get(d, d) for d in sorted(designs))
