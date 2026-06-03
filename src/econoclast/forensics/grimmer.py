"""GRIMMER — Granularity-Related Inconsistency of Means Mapped to Error Repeats.

Extends GRIM to the standard deviation. For integer data, the sum of squares is
an integer with the same parity as the sum of values. We reconstruct the integer
total from the mean (as in GRIM), then check whether *any* integer sum-of-squares
inside the SD's rounding interval is parity-consistent and yields a non-negative
variance. If none exists, the reported (mean, SD, N) triple is impossible.

Reference: Anaya (2016), "The GRIMMER test"; Allard (2018) refinements.
"""

from __future__ import annotations

import math

from econoclast.forensics.base import Flag, ForensicResult

REFERENCE = "Anaya (2016), GRIMMER test"


def grimmer_consistent(mean: float, sd: float, n: int, decimals: int) -> bool:
    if n <= 1 or sd < 0:
        return True
    denom = n
    base_total = round(mean * denom)
    half = 0.5 * 10 ** (-decimals)
    var_lo = max(0.0, (sd - half)) ** 2
    var_hi = (sd + half) ** 2

    for total in (base_total - 1, base_total, base_total + 1):
        # GRIM gate: this total must reproduce the mean.
        if round(total / denom, decimals) != round(mean, decimals):
            continue
        # SS of deviations = var*(n-1); sum of squares = SS + total^2/n.
        ss_lo = var_lo * (n - 1)
        ss_hi = var_hi * (n - 1)
        sumsq_lo = ss_lo + (total * total) / n
        sumsq_hi = ss_hi + (total * total) / n
        lo_int = math.ceil(sumsq_lo - 1e-9)
        hi_int = math.floor(sumsq_hi + 1e-9)
        for sumsq in range(lo_int, hi_int + 1):
            # Parity: sum(x_i^2) ≡ sum(x_i) (mod 2) for integer x_i.
            if (sumsq - total) % 2 != 0:
                continue
            # Variance non-negativity bound.
            if sumsq >= (total * total) / n - 1e-9:
                return True
    return False


def run_grimmer(claims: list) -> ForensicResult:
    candidates = [
        c for c in claims
        if c.mean is not None and c.sd is not None and c.n and c.n > 1 and (c.decimals or 0) >= 1
    ]
    if not candidates:
        return ForensicResult.insufficient(
            "grimmer",
            "No `mean + SD + N` triples (with decimals) found. GRIMMER needs descriptive "
            "stats of integer-valued data.",
            REFERENCE,
        )

    flags: list[Flag] = []
    checked = 0
    inconsistent = 0
    for c in candidates:
        decimals = c.decimals or 1
        diagnostic = c.n < 10**decimals
        checked += 1
        if grimmer_consistent(c.mean, c.sd, c.n, decimals):
            continue
        inconsistent += 1
        flags.append(
            Flag(
                detail=(
                    f"mean={c.mean}, SD={c.sd}, N={c.n} is GRIMMER-inconsistent: no integer "
                    f"sum-of-squares in the SD's rounding interval is parity-consistent."
                ),
                severity="high" if diagnostic else "low",
                data={"section": c.section, "mean": c.mean, "sd": c.sd, "n": c.n, "raw": c.raw[:160]},
            )
        )

    if inconsistent == 0:
        return ForensicResult(
            name="grimmer",
            ran=True,
            verdict="clean",
            severity="info",
            summary=f"All {checked} testable (mean, SD, N) triples are GRIMMER-consistent.",
            n_inputs=checked,
            stats={"checked": checked, "inconsistent": 0},
            reference=REFERENCE,
        )

    return ForensicResult(
        name="grimmer",
        ran=True,
        verdict="suspicious",
        severity="high" if any(f.severity == "high" for f in flags) else "low",
        summary=f"{inconsistent}/{checked} (mean, SD, N) triples are impossible for integer data.",
        n_inputs=checked,
        stats={"checked": checked, "inconsistent": inconsistent},
        flags=flags,
        reference=REFERENCE,
    )
