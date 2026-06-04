"""Let the model read the paper and decide the things we used to guess at.

Detecting the design and the method by keyword works, but it is brittle and it
cannot tell you what the headline claim actually is or where the data lives.
When a model is available, this reads the paper once and returns a structured
understanding that drives the rest of the run: which design and methods, the
central claim and its direction, the variables, and any dataset link. Without a
model the caller falls back to the regex detectors.
"""

from __future__ import annotations

from econoclast.llm.base import Message
from econoclast.logging import get_logger

log = get_logger("agent.comprehend")

_SYSTEM = (
    "You read an empirical-economics paper and report, factually, what it does. Do not critique it "
    "here; just describe it. If something is not stated, leave it blank rather than guessing."
)

_CONTRACT = (
    'Return ONLY JSON: {"design": str (e.g. difference-in-differences, regression discontinuity, '
    'instrumental variables, synthetic control, structural, RCT, panel FE, descriptive), '
    '"methods": [str], "headline_claim": str (one sentence: the main empirical result), '
    '"claimed_direction": 1 | -1 | 0, "outcome": str (variable, or ""), '
    '"treatment": str (focal regressor, or ""), "data_links": [str (URLs/DOIs to data or code)], '
    '"data_availability": str (the data-availability statement, or ""), "uses_public_data": bool}'
)


def comprehend(paper, router) -> dict | None:  # noqa: ANN001
    if not router.is_live():
        return None
    excerpt = (
        f"TITLE: {paper.title}\nABSTRACT: {paper.abstract[:1200]}\n\n"
        + paper.section_text("strateg", "identif", "method", "data", "result", "estimat", "availab")[:12000]
    ) or paper.excerpt(12000)
    try:
        resp = router.complete("extractor",
                               [Message(role="system", content=_SYSTEM + "\n\n" + _CONTRACT),
                                Message(role="user", content=excerpt)],
                               response_format="json")
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("comprehension failed, falling back to keyword detection: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    log.info("Comprehended: design=%s, methods=%s, claim=%.60s",
             data.get("design"), data.get("methods"), str(data.get("headline_claim", "")))
    return data


def merge_designs(regex_designs: set[str], comp: dict | None) -> set[str]:
    """Combine keyword-detected designs with the model's reading."""
    out = set(regex_designs)
    if not comp:
        return out
    text = (str(comp.get("design", "")) + " " + " ".join(comp.get("methods", []) or [])).lower()
    table = {
        "difference": "did", "diff-in-diff": "did", "twfe": "did",
        "discontinuity": "rdd", "instrument": "iv", "2sls": "iv",
        "matching": "matching", "propensity": "matching", "synthetic control": "matching",
        "randomi": "rct", "experiment": "rct", "structural": "structural",
        "panel": "panel_fe", "fixed effects": "panel_fe",
    }
    for needle, design in table.items():
        if needle in text:
            out.add(design)
    return out
