"""GRIM — Granularity-Related Inconsistency of Means.

For data that are sums/averages of integers (Likert items, counts), a reported
mean of N observations must equal some integer total divided by N. If no integer
total rounds to the reported mean at the stated precision, the mean is
impossible — a sign of error or fabrication.

Reference: Brown & Heathers (2017), "The GRIM Test", Social Psychological and
Personality Science.
"""

from __future__ import annotations

from econoclast.forensics.base import Flag, ForensicResult

REFERENCE = "Brown & Heathers (2017), GRIM Test, SPPS"


def grim_consistent(mean: float, n: int, decimals: int, n_items: int = 1) -> bool:
    """True if some integer total/(n*n_items) rounds to ``mean`` at ``decimals``."""
    if n <= 0 or decimals < 0:
        return True
    denom = n * n_items
    target = round(mean, decimals)
    base = round(mean * denom)
    for k in (base - 1, base, base + 1):
        if round(k / denom, decimals) == target:
            return True
    return False


def run_grim(claims: list, n_items: int = 1) -> ForensicResult:
    candidates = [
        c for c in claims
        if c.mean is not None and c.n and c.n > 1 and (c.decimals or 0) >= 1
    ]
    if not candidates:
        return ForensicResult.insufficient(
            "grim",
            "No `mean + sample-size` pairs (with decimals) were found. GRIM needs "
            "means of integer-valued data reported to ≥1 decimal place.",
            REFERENCE,
        )

    flags: list[Flag] = []
    checked = 0
    inconsistent = 0
    low_power = 0
    for c in candidates:
        decimals = c.decimals or 1
        # GRIM only has diagnostic power when n < 10**decimals (else nearly every
        # mean is representable). Report but de-weight low-power checks.
        diagnostic = c.n < 10**decimals
        checked += 1
        if grim_consistent(c.mean, c.n, decimals, n_items=n_items):
            if not diagnostic:
                low_power += 1
            continue
        inconsistent += 1
        flags.append(
            Flag(
                detail=(
                    f"mean={c.mean} with N={c.n} (to {decimals} dp) is GRIM-inconsistent: "
                    f"no integer total divided by {c.n} rounds to it."
                ),
                severity="high" if diagnostic else "low",
                data={"section": c.section, "mean": c.mean, "n": c.n, "raw": c.raw[:160]},
            )
        )

    if inconsistent == 0:
        return ForensicResult(
            name="grim",
            ran=True,
            verdict="clean",
            severity="info",
            summary=f"All {checked} testable means are GRIM-consistent."
            + (f" ({low_power} had low diagnostic power because N≥10^decimals.)" if low_power else ""),
            n_inputs=checked,
            stats={"checked": checked, "inconsistent": 0, "low_power": low_power},
            reference=REFERENCE,
        )

    return ForensicResult(
        name="grim",
        ran=True,
        verdict="suspicious",
        severity="high" if any(f.severity == "high" for f in flags) else "low",
        summary=f"{inconsistent}/{checked} reported means are mathematically impossible for integer data of that N.",
        n_inputs=checked,
        stats={"checked": checked, "inconsistent": inconsistent, "low_power": low_power},
        flags=flags,
        reference=REFERENCE,
    )
