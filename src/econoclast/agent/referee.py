"""Final referee synthesis: turn a pile of findings into a verdict.

The model sees the structured findings and writes an executive assessment, like an
area chair's meta-review. If the model call fails outright, a terse deterministic
summary keeps the report coherent.
"""

from __future__ import annotations

import json

from econoclast.attacks.base import AttackContext, Finding
from econoclast.attacks.designs import design_label
from econoclast.llm.base import Message
from econoclast.logging import get_logger

log = get_logger("agent.referee")

_SYSTEM = (
    "You are the area chair writing the meta-review for an adversarial referee report on an "
    "empirical economics paper. You are given the structured findings. Weigh them honestly: do not "
    "inflate weak statistical signals, but do not excuse internal inconsistencies. Trust grounded, "
    "verified findings (those with a quote) over speculative ones, and discount any finding flagged as "
    "unverified. Decide whether the central empirical claim is robust, has material concerns, or is "
    "fragile."
)

_CONTRACT = (
    'Return ONLY JSON: {"headline": str (one sentence verdict), '
    '"assessment": str (2-4 sentences, specific to THIS paper, citing the most important '
    'findings by their effect on the headline result), '
    '"what_would_change_my_mind": str (the single most decisive additional test or disclosure)}'
)


def synthesize_referee(
    ctx: AttackContext, findings: list[Finding], fragility: dict
) -> dict:
    top = [f.to_dict() for f in sorted(findings, key=lambda f: f.weight, reverse=True)[:12]]
    payload = {
        "title": ctx.paper.title,
        "design": design_label(ctx.designs),
        "fragility": fragility,
        "top_findings": top,
    }
    messages = [
        Message(role="system", content=_SYSTEM + "\n\n" + _CONTRACT),
        Message(role="user", content="Here is the evidence:\n" + json.dumps(payload, ensure_ascii=False)[:14000]),
    ]
    try:
        resp = ctx.backend.complete("referee", messages, response_format="json")
        data = resp.json()
        if isinstance(data, dict) and data.get("headline"):
            return {
                "headline": str(data.get("headline", ""))[:400],
                "assessment": str(data.get("assessment", ""))[:2000],
                "what_would_change_my_mind": str(data.get("what_would_change_my_mind", ""))[:800],
                "generated_by": "llm",
            }
    except Exception as exc:  # noqa: BLE001
        log.warning("Referee synthesis failed, using fallback: %s", exc)
    return _fallback(ctx, findings, fragility)


def _fallback(ctx: AttackContext, findings: list[Finding], fragility: dict) -> dict:
    band = fragility.get("band", "Unknown")
    score = fragility.get("score", 0)
    top = sorted(findings, key=lambda f: f.weight, reverse=True)[:3]
    if top:
        bullets = "; ".join(f"{f.title} ({f.severity})" for f in top)
        assessment = f"The most consequential issues: {bullets}."
    else:
        assessment = "No material findings were raised."
    if fragility.get("integrity_violation"):
        assessment += " A reported statistic is internally impossible or inconsistent, which by itself warrants correction."
    return {
        "headline": f"{band}: fragility {score}/100 from {len(findings)} finding(s).",
        "assessment": assessment,
        "what_would_change_my_mind": (
            "A pre-registered or specification-curve analysis showing the headline estimate is "
            "stable across the plausible researcher degrees of freedom."
        ),
        "generated_by": "deterministic",
    }
