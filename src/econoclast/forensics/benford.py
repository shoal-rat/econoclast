"""Benford's-law first-digit analysis.

Naturally occurring numbers that span several orders of magnitude follow
Benford's law: leading digit ``d`` appears with probability log10(1 + 1/d).
Large deviations can indicate fabrication or heavy manipulation.

Big caveat (printed in the summary): regression coefficients and standardised
statistics do *not* always span enough magnitudes to be Benford-distributed, so
treat a deviation as a prompt to look closer, never as proof.

Reference: Nigrini (2012), "Benford's Law"; Diekmann (2007) on regression
coefficients.
"""

from __future__ import annotations

import math

from econoclast.forensics.base import Flag, ForensicResult

REFERENCE = "Nigrini (2012); Diekmann (2007, J. Applied Statistics)"

BENFORD = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def _leading_digit(x: float) -> int | None:
    x = abs(x)
    if x == 0 or math.isinf(x) or math.isnan(x):
        return None
    while x < 1:
        x *= 10
    while x >= 10:
        x /= 10
    d = int(x)
    return d if 1 <= d <= 9 else None


def collect_numbers(claims: list) -> list[float]:
    nums: list[float] = []
    for c in claims:
        for v in (c.coef, c.se, c.stat_value, c.mean, c.sd):
            if v is not None:
                nums.append(float(v))
    return nums


def run_benford(numbers: list[float]) -> ForensicResult:
    digits = [d for d in (_leading_digit(x) for x in numbers) if d is not None]
    k = len(digits)
    if k < 40:
        return ForensicResult.insufficient(
            "benford",
            f"Only {k} numbers available; Benford analysis needs ≥40 (ideally hundreds).",
            REFERENCE,
        )

    observed = {d: digits.count(d) for d in range(1, 10)}
    chi2 = sum((observed[d] - k * BENFORD[d]) ** 2 / (k * BENFORD[d]) for d in range(1, 10))
    mad = sum(abs(observed[d] / k - BENFORD[d]) for d in range(1, 10)) / 9
    # Nigrini MAD conformity bands for first digit.
    if mad < 0.006:
        conformity = "close"
    elif mad < 0.012:
        conformity = "acceptable"
    elif mad < 0.015:
        conformity = "marginal"
    else:
        conformity = "nonconforming"

    from scipy import stats  # local import keeps module import cheap

    p = float(stats.chi2.sf(chi2, df=8))
    suspicious = conformity == "nonconforming" and p < 0.01
    flags: list[Flag] = []
    if suspicious:
        flags.append(Flag(
            detail=f"Leading-digit distribution departs from Benford (MAD={mad:.4f}, χ²={chi2:.1f}, p={p:.4f}).",
            severity="low",
            data={"observed": observed},
        ))

    return ForensicResult(
        name="benford",
        ran=True,
        verdict="suspicious" if suspicious else "clean",
        severity="low" if suspicious else "info",
        summary=(
            f"First-digit MAD={mad:.4f} ({conformity}); χ²(8)={chi2:.1f}, p={p:.4f} over {k} numbers. "
            "[caveat: coefficients need not be Benford — exploratory signal only]"
        ),
        n_inputs=k,
        stats={"chi2": round(chi2, 2), "mad": round(mad, 5), "p": round(p, 4),
               "conformity": conformity, "observed": observed},
        flags=flags,
        reference=REFERENCE,
    )
