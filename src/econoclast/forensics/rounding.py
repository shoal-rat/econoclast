"""Terminal-digit (rounding / heaping) analysis.

The last decimal digit of a precisely-measured statistic should be roughly
uniform on 0-9. Excess 0s and 5s indicate heaping (rounding, eyeballing) and a
strongly non-uniform terminal digit can indicate hand-edited or fabricated
numbers.

Reference: terminal-digit tests as used in data-forensics (e.g. Mosimann et al.;
Hartgerink's suite).
"""

from __future__ import annotations

from scipy import stats

from econoclast.forensics.base import Flag, ForensicResult

REFERENCE = "Terminal-digit uniformity (Mosimann; Hartgerink)"


def _last_digit(raw: str, value: float) -> int | None:
    # Use the printed string when available to respect reported precision.
    s = f"{value}"
    if "." in s:
        frac = s.split(".")[1]
        if frac:
            return int(frac[-1])
    return None


def run_rounding(claims: list) -> ForensicResult:
    digits: list[int] = []
    for c in claims:
        for v in (c.coef, c.se, c.stat_value, c.mean, c.sd, c.p_value):
            if v is None:
                continue
            d = _last_digit("", float(v))
            if d is not None:
                digits.append(d)

    k = len(digits)
    if k < 40:
        return ForensicResult.insufficient(
            "rounding",
            f"Only {k} terminal digits available; need ≥40 for a uniformity test.",
            REFERENCE,
        )

    counts = [digits.count(d) for d in range(10)]
    expected = k / 10
    chi2 = sum((c - expected) ** 2 / expected for c in counts)
    p = float(stats.chi2.sf(chi2, df=9))
    share_0_5 = (counts[0] + counts[5]) / k
    heaping = share_0_5 > 0.35 and p < 0.05

    flags: list[Flag] = []
    if heaping:
        flags.append(Flag(
            detail=f"Terminal digits heap on 0/5 (share={share_0_5:.2f}, χ²(9)={chi2:.1f}, p={p:.4f}).",
            severity="low",
            data={"counts": dict(enumerate(counts))},
        ))

    return ForensicResult(
        name="rounding",
        ran=True,
        verdict="suspicious" if heaping else "clean",
        severity="low" if heaping else "info",
        summary=(
            f"Terminal-digit χ²(9)={chi2:.1f}, p={p:.4f}; 0/5 share={share_0_5:.2f} over {k} digits."
        ),
        n_inputs=k,
        stats={"chi2": round(chi2, 2), "p": round(p, 4), "counts": dict(enumerate(counts))},
        flags=flags,
        reference=REFERENCE,
    )
