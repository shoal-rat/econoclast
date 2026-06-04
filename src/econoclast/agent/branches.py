"""Branch-and-merge verification.

When a single approach is not obviously right, the agent should try several and
keep the best. This runs a few independent verification strategies for the same
question, then a judge consolidates them: it drops duplicates and weak points,
and prefers the approach most appropriate to the paper's actual method.
"""

from __future__ import annotations

import json

from econoclast.attacks.base import AttackContext, Finding
from econoclast.attacks.ensemble import _same_issue
from econoclast.attacks.llm import _EPISTEMICS, _JSON_CONTRACT, _UNTRUSTED, _parse_findings
from econoclast.llm.base import Message
from econoclast.logging import get_logger

log = get_logger("agent.branches")

_JUDGE = (
    "You are merging the outputs of several independent verification strategies that all attacked the "
    "same question about an empirical-economics paper. Keep only the findings that are well supported "
    "(grounded in a quote or a clear, correct argument). Drop duplicates and weakly-supported points. "
    "Where the strategies disagree, prefer the one most appropriate to the paper's actual method. "
    "Return the consolidated set of findings."
)


def branch_and_merge(
    ctx: AttackContext,
    *,
    strategies: list[tuple[str, str]],
    system: str,
    default_category: str,
    attack_name: str = "branch-verify",
) -> list[Finding]:
    """Run each (label, user_prompt) strategy, then judge-merge the findings."""
    runs: list[tuple[str, list[Finding]]] = []
    for label, prompt in strategies:
        sys = f"{system}\n\n{_EPISTEMICS}\n\n{_UNTRUSTED}\n\n{_JSON_CONTRACT}"
        try:
            resp = ctx.router.complete(
                "attacker", [Message(role="system", content=sys), Message(role="user", content=prompt)],
                response_format="json")
            runs.append((label, _parse_findings(resp.json(), attack_name, default_category)))
        except Exception as exc:  # noqa: BLE001
            log.warning("branch '%s' failed: %s", label, exc)

    all_findings = [f for _, fs in runs for f in fs]
    if not all_findings:
        return []
    if len(runs) < 2:
        return _dedup(all_findings)

    payload = json.dumps(
        [{"strategy": lbl, "findings": [f.to_dict() for f in fs]} for lbl, fs in runs],
        ensure_ascii=False)[:14000]
    try:
        resp = ctx.router.complete(
            "referee",
            [Message(role="system", content=_JUDGE + "\n\n" + _JSON_CONTRACT),
             Message(role="user", content="Candidate findings by strategy:\n" + payload)],
            response_format="json")
        merged = _parse_findings(resp.json(), attack_name, default_category)
        if merged:
            log.info("branch-merge: %d candidates -> %d consolidated", len(all_findings), len(merged))
            return merged
    except Exception as exc:  # noqa: BLE001
        log.warning("branch-merge judge failed: %s", exc)
    return _dedup(all_findings)


def _dedup(findings: list[Finding]) -> list[Finding]:
    kept: list[Finding] = []
    for f in findings:
        if not any(_same_issue(f, k) for k in kept):
            kept.append(f)
        else:
            # keep the higher-confidence representative
            for i, k in enumerate(kept):
                if _same_issue(f, k) and f.confidence > k.confidence:
                    kept[i] = f
    return kept
