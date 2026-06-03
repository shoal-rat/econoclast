"""Wrap the deterministic forensics as `Attack`s.

Each wrapper runs one forensic test, records the raw :class:`ForensicResult` on
the context (so the report can show the full battery table) and converts a
"suspicious" verdict into one or more :class:`Finding`s.
"""

from __future__ import annotations

from collections.abc import Callable

from econoclast.attacks.base import Attack, AttackContext, Finding
from econoclast.forensics.base import ForensicResult
from econoclast.forensics.benford import collect_numbers, run_benford
from econoclast.forensics.caliper import run_caliper
from econoclast.forensics.grim import run_grim
from econoclast.forensics.grimmer import run_grimmer
from econoclast.forensics.pcurve import run_pcurve
from econoclast.forensics.rounding import run_rounding
from econoclast.forensics.statcheck import run_statcheck
from econoclast.forensics.tiva import run_tiva


class ForensicAttack(Attack):
    kind = "deterministic"

    def __init__(
        self,
        name: str,
        category: str,
        fn: Callable,
        *,
        confidence: float,
        description: str,
        uses_numbers: bool = False,
    ) -> None:
        self.name = name
        self.category = category
        self._fn = fn
        self._confidence = confidence
        self.description = description
        self._uses_numbers = uses_numbers

    def run(self, ctx: AttackContext) -> list[Finding]:
        inp = collect_numbers(ctx.paper.claims) if self._uses_numbers else ctx.paper.claims
        result: ForensicResult = self._fn(inp)
        ctx.forensic_results.append(result)
        if result.verdict != "suspicious":
            return []
        evidence = [f.detail for f in result.flags][:8]
        locations = sorted({
            str(f.data.get("section") or f.data.get("table") or "")
            for f in result.flags
            if f.data.get("section") or f.data.get("table")
        })
        return [
            Finding(
                attack=self.name,
                title=f"{self.name}: {result.summary.split('.')[0]}",
                category=self.category,
                severity=result.severity,
                confidence=self._confidence,
                detail=result.summary,
                evidence=evidence,
                locations=[loc for loc in locations if loc],
                recommendation=_RECO.get(self.name, ""),
                data=result.stats,
            )
        ]


_RECO = {
    "statcheck": "Recompute every reported p-value from the test statistic and df; correct or explain each mismatch, especially any that flip significance.",
    "grim": "Re-derive the reported means from the raw integer data; an impossible mean means a typo or a fabricated descriptive.",
    "grimmer": "Re-derive the SD from the raw data; publish the underlying response distribution.",
    "p-curve": "Pre-register the focal test, or report a specification curve; a flat p-curve undercuts the evidential-value claim.",
    "caliper": "Report the full distribution of t/z statistics and disclose every specification tried, not only those that clear 1.96.",
    "tiva": "Show that the focal estimates are independent draws; unusually low z-variance suggests selective reporting.",
    "benford": "Publish the raw data; investigate any table whose digits depart sharply from expectation.",
    "rounding": "Report numbers at full precision from code output rather than hand-transcribing rounded values.",
}


def build_forensic_attacks() -> list[ForensicAttack]:
    return [
        ForensicAttack("statcheck", "reporting_inconsistency", run_statcheck,
                       confidence=0.95,
                       description="Recompute reported p-values from test statistics and flag inconsistencies."),
        ForensicAttack("grim", "data_integrity", run_grim, confidence=0.9,
                       description="Check whether reported means are possible for integer data of the stated N."),
        ForensicAttack("grimmer", "data_integrity", run_grimmer, confidence=0.9,
                       description="Check whether reported (mean, SD, N) triples are possible for integer data."),
        ForensicAttack("p-curve", "p_hacking", run_pcurve, confidence=0.55,
                       description="Test the distribution of significant p-values for evidential value vs p-hacking."),
        ForensicAttack("caliper", "p_hacking", run_caliper, confidence=0.6,
                       description="Test for bunching of z-statistics just above 1.96/1.645/2.576."),
        ForensicAttack("tiva", "p_hacking", run_tiva, confidence=0.5,
                       description="Test of insufficient variance + R-index over focal z-statistics."),
        ForensicAttack("benford", "data_integrity", run_benford, confidence=0.35,
                       description="First-digit (Benford) analysis of reported numbers.", uses_numbers=True),
        ForensicAttack("rounding", "data_integrity", run_rounding, confidence=0.35,
                       description="Terminal-digit uniformity / heaping analysis."),
    ]
