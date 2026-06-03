"""Deterministic statistical forensics.

Every function here runs offline (NumPy/SciPy) on numbers harvested from the
paper. ``run_forensics`` runs the whole battery and returns one
:class:`ForensicResult` per test.
"""

from __future__ import annotations

from econoclast.forensics.base import Flag, ForensicResult
from econoclast.forensics.benford import collect_numbers, run_benford
from econoclast.forensics.caliper import run_caliper
from econoclast.forensics.grim import run_grim
from econoclast.forensics.grimmer import run_grimmer
from econoclast.forensics.pcurve import run_pcurve
from econoclast.forensics.rounding import run_rounding
from econoclast.forensics.statcheck import run_statcheck
from econoclast.forensics.tiva import run_tiva
from econoclast.logging import get_logger

log = get_logger("forensics")

__all__ = [
    "ForensicResult",
    "Flag",
    "run_forensics",
    "run_forensics_on_claims",
    "run_statcheck",
    "run_grim",
    "run_grimmer",
    "run_pcurve",
    "run_caliper",
    "run_tiva",
    "run_benford",
    "run_rounding",
]


def run_forensics_on_claims(claims: list) -> list[ForensicResult]:
    results = [
        run_statcheck(claims),
        run_grim(claims),
        run_grimmer(claims),
        run_pcurve(claims),
        run_caliper(claims),
        run_tiva(claims),
        run_benford(collect_numbers(claims)),
        run_rounding(claims),
    ]
    flagged = [r for r in results if r.verdict == "suspicious"]
    log.info("Forensics complete: %d/%d tests ran, %d flagged something",
             sum(1 for r in results if r.ran), len(results), len(flagged))
    return results


def run_forensics(paper) -> list[ForensicResult]:  # noqa: ANN001
    return run_forensics_on_claims(paper.claims)
