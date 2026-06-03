"""p-curve — the distribution of significant p-values.

A set of true, adequately-powered effects produces a right-skewed p-curve (many
more p < .01 than p just below .05). p-hacking flattens or left-skews it.

We compute (a) a binomial test comparing the share of p < .025 to .025-.05, and
(b) a Stouffer right-skew test on pp-values. Caveat printed in the summary:
p-curve assumes independent tests of a common hypothesis, which p-values lifted
from one paper rarely satisfy — read this as a descriptive signal, not a verdict.

Reference: Simonsohn, Nelson & Simmons (2014), "p-Curve: A Key to the
File-Drawer", JEP: General.
"""

from __future__ import annotations

from scipy import stats

from econoclast.forensics.base import Flag, ForensicResult

REFERENCE = "Simonsohn, Nelson & Simmons (2014), JEP:General (p-curve)"


def _exact_sig_pvalues(claims: list) -> list[float]:
    out = []
    for c in claims:
        if c.p_value is None:
            continue
        if c.p_comparator != "=":
            continue
        if 0 < c.p_value < 0.05:
            out.append(c.p_value)
    return out


def run_pcurve(claims: list) -> ForensicResult:
    ps = _exact_sig_pvalues(claims)
    k = len(ps)
    if k < 5:
        return ForensicResult.insufficient(
            "p-curve",
            f"Only {k} exact significant p-values (<.05) found; need ≥5 for a p-curve.",
            REFERENCE,
        )

    below = sum(1 for p in ps if p < 0.025)
    binom = stats.binomtest(below, k, 0.5, alternative="greater")

    # Stouffer right-skew test: pp = p/.05 ~ U(0,1) under H0; right skew -> small pp.
    zs = []
    for p in ps:
        pp = min(max(p / 0.05, 1e-6), 1 - 1e-6)
        zs.append(stats.norm.ppf(pp))
    stouffer_z = sum(zs) / (k ** 0.5)
    right_skew_p = float(stats.norm.cdf(stouffer_z))  # left tail = right-skew

    right_skewed = right_skew_p < 0.05
    flat_or_left = right_skew_p > 0.95 or (not right_skewed and binom.pvalue > 0.5)

    if right_skewed:
        verdict, severity = "clean", "info"
        summary = (
            f"p-curve is right-skewed (Stouffer p={right_skew_p:.3f}; {below}/{k} of "
            f"significant p < .025): consistent with evidential value."
        )
        flags: list[Flag] = []
    elif flat_or_left:
        verdict, severity = "suspicious", "medium"
        summary = (
            f"p-curve is flat/left-skewed (Stouffer p={right_skew_p:.3f}; only {below}/{k} "
            f"of significant p < .025): consistent with p-hacking or lack of evidential value."
        )
        flags = [Flag(
            detail="Significant p-values cluster just below .05 rather than near 0.",
            severity="medium",
            data={"p_values": sorted(ps)},
        )]
    else:
        verdict, severity = "inconclusive", "info"
        summary = f"p-curve is ambiguous (Stouffer right-skew p={right_skew_p:.3f}, k={k})."
        flags = []

    return ForensicResult(
        name="p-curve",
        ran=True,
        verdict=verdict,
        severity=severity,
        summary=summary + "  [caveat: assumes independent tests of one hypothesis]",
        n_inputs=k,
        stats={
            "k": k,
            "share_below_.025": round(below / k, 3),
            "binomial_p": round(binom.pvalue, 4),
            "stouffer_z": round(stouffer_z, 3),
            "right_skew_p": round(right_skew_p, 4),
        },
        flags=flags,
        reference=REFERENCE,
    )
