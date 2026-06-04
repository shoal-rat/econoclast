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


# Finer-grained estimation methods, beyond the broad design family above. Many of
# these have no built-in deterministic check, which is the point: when Econoclast
# meets one it does not cover, the agent should research it and verify, not guess.
_METHOD_PATTERNS: dict[str, list[str]] = {
    "synthetic_control": [r"synthetic control"],
    "bunching": [r"\bbunching\b", r"excess mass", r"\bnotch(es)?\b"],
    "event_study": [r"event[- ]stud(y|ies)", r"event[- ]time"],
    "shift_share": [r"shift[- ]share", r"\bBartik\b"],
    "regression_kink": [r"regression kink", r"\bRKD\b"],
    "gmm": [r"\bGMM\b", r"generalized method of moments", r"generalised method of moments"],
    "ml_causal": [r"double machine learning", r"\bDML\b", r"causal forest", r"\blasso\b",
                  r"post[- ]double", r"debiased machine learning"],
    "structural": [r"\bBLP\b", r"nested logit", r"random coefficients", r"structural (model|estimation)",
                   r"demand estimation"],
    "did": [r"difference[- ]in[- ]differences", r"\bDiD\b", r"two[- ]way fixed effects", r"\bTWFE\b"],
    "rdd": [r"regression discontinuity", r"\bRDD?\b", r"running variable", r"McCrary"],
    "iv": [r"instrumental variabl", r"\b2SLS\b", r"exclusion restriction"],
    "matching": [r"propensity score", r"\bmatching\b", r"synthetic control"],
}

# Methods Econoclast covers with a built-in deterministic estimator/diagnostic.
# Anything not here triggers the research-then-verify path.
COVERED_METHODS = {"rdd", "did"}


def detect_methods(text: str) -> set[str]:
    found = set()
    for method, pats in _METHOD_PATTERNS.items():
        if any(re.search(p, text, re.IGNORECASE) for p in pats):
            found.add(method)
    return found


def method_coverage(methods: set[str]) -> dict[str, list[str]]:
    """Split detected methods into ones we check deterministically vs ones to research."""
    return {
        "covered": sorted(m for m in methods if m in COVERED_METHODS),
        "needs_research": sorted(m for m in methods if m not in COVERED_METHODS),
    }


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
