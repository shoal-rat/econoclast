"""TIVA (Test of Insufficient Variance) and the R-index.

TIVA (Schimmack): a set of independent test statistics has z-scores whose
variance should be >= 1. A variance far below 1 means the results are "too
consistent" to be real independent draws — a signature of selective reporting or
QRP. R-index (Schimmack): compares the success rate (share significant) to the
median observed power; a large gap (success rate >> power) signals inflation and
poor expected replicability.

Caveat (printed): both assume the z's come from conceptually-related, roughly
independent focal tests. We use signed z = coef/se from regression cells; if the
paper mixes unrelated effects the tests become conservative.

References: Schimmack (2014, 2016); Renkewitz & Keiner (2019).
"""

from __future__ import annotations

import statistics

from scipy import stats

from econoclast.forensics.base import Flag, ForensicResult

REFERENCE = "Schimmack (2014/2016), TIVA & R-index"


def _signed_z(claims: list) -> list[float]:
    zs = []
    for c in claims:
        if c.coef is not None and c.se not in (None, 0):
            z = c.coef / c.se
            if abs(z) < 12:
                zs.append(z)
    return zs


def run_tiva(claims: list) -> ForensicResult:
    zs = _signed_z(claims)
    k = len(zs)
    if k < 5:
        return ForensicResult.insufficient(
            "tiva",
            f"Only {k} signed z-statistics (coef/se) found; need ≥5 for TIVA.",
            REFERENCE,
        )

    var = statistics.variance(zs)
    # H0: var = 1 ; H1: var < 1. (k-1)*var ~ chi2_{k-1}.
    chi = (k - 1) * var
    tiva_p = float(stats.chi2.cdf(chi, k - 1))

    # R-index on the absolute z's.
    abs_z = [abs(z) for z in zs]
    powers = [float(stats.norm.cdf(z - 1.96)) for z in abs_z]
    median_power = statistics.median(powers)
    success_rate = sum(1 for z in abs_z if z > 1.96) / k
    inflation = success_rate - statistics.mean(powers)
    r_index = max(0.0, median_power - inflation)

    flags: list[Flag] = []
    suspicious = False
    if tiva_p < 0.05:
        suspicious = True
        flags.append(Flag(
            detail=f"Variance of z-scores is {var:.2f} (<1): insufficient variance (TIVA p={tiva_p:.3f}).",
            severity="medium",
            data={"variance": round(var, 3), "k": k},
        ))
    if r_index < 0.5 and success_rate > 0.6:
        flags.append(Flag(
            detail=f"R-index={r_index:.2f} with success rate {success_rate:.0%} vs median power {median_power:.0%}: results look inflated / hard to replicate.",
            severity="low",
            data={"r_index": round(r_index, 3)},
        ))

    verdict = "suspicious" if suspicious else "clean"
    severity = "medium" if suspicious else "info"
    return ForensicResult(
        name="tiva",
        ran=True,
        verdict=verdict,
        severity=severity,
        summary=(
            f"z-score variance={var:.2f} (TIVA p={tiva_p:.3f}); R-index={r_index:.2f} "
            f"(success {success_rate:.0%}, median power {median_power:.0%}). "
            "[caveat: assumes related, independent focal tests]"
        ),
        n_inputs=k,
        stats={
            "k": k,
            "z_variance": round(var, 3),
            "tiva_p": round(tiva_p, 4),
            "r_index": round(r_index, 3),
            "success_rate": round(success_rate, 3),
            "median_power": round(median_power, 3),
        },
        flags=flags,
        reference=REFERENCE,
    )
