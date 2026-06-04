"""Citation-verification attack: check the bibliography against Crossref."""

from __future__ import annotations

from econoclast.attacks.base import Attack, AttackContext, Finding
from econoclast.ingest.references import extract_references, verify_references
from econoclast.logging import get_logger

log = get_logger("attacks.citations")


class CitationVerificationAttack(Attack):
    name = "citation-check"
    category = "literature"
    kind = "network"  # needs the internet, but no model
    requires_llm = False
    description = "Verify the paper's references resolve to real works in Crossref."

    def gate(self, ctx: AttackContext) -> bool:
        return ctx.searcher is not None and not ctx.settings.offline

    def run(self, ctx: AttackContext) -> list[Finding]:
        refs = extract_references(ctx.paper)
        if len(refs) < 8:
            log.info("Citation check skipped: only %d references parsed.", len(refs))
            return []
        checks = verify_references(refs)
        if not checks:
            return []
        unresolved = [c for c in checks if not c.resolved]
        rate = len(unresolved) / len(checks)
        if rate <= 0.35:
            return []  # most references resolve; nothing to report
        examples = [c.text[:120] for c in unresolved[:5]]
        severity = "medium" if rate > 0.6 else "low"
        return [Finding(
            attack=self.name,
            title=f"{len(unresolved)}/{len(checks)} references did not match a Crossref record",
            category="literature",
            severity=severity,
            confidence=0.45,
            detail=("These references could not be matched to a real work via Crossref's reference "
                    "matcher. Some will be books, working papers, or datasets without a DOI, but a high "
                    "unresolved rate is worth checking against fabricated or garbled citations."),
            evidence=examples,
            recommendation="Confirm each unmatched reference exists and is cited correctly.",
            data={"checked": len(checks), "unresolved": len(unresolved), "rate": round(rate, 2)},
        )]
