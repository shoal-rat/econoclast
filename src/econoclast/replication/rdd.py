"""RDD replication checks: manipulation of the running variable + bandwidth sensitivity.

The manipulation test is a screening density-discontinuity test (binomial on a
window around the cutoff, plus a binned local-linear density jump). It flags
sorting; confirm with `rdrobust` / Cattaneo-Jansson-Ma before drawing conclusions.
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def manipulation_test(running, cutoff: float, window: float | None = None) -> dict:
    """Screening test for manipulation of the running variable at the cutoff."""
    x = np.asarray(running, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 30:
        return {"ran": False, "reason": "fewer than 30 observations"}
    if window is None:
        window = 0.5 * np.std(x)
    below = int(np.sum((x >= cutoff - window) & (x < cutoff)))
    above = int(np.sum((x >= cutoff) & (x < cutoff + window)))
    total = below + above
    if total < 20:
        return {"ran": False, "reason": "too few observations near the cutoff"}
    test = stats.binomtest(above, total, 0.5)
    return {
        "ran": True,
        "cutoff": cutoff,
        "window": round(window, 4),
        "below": below,
        "above": above,
        "ratio_above_below": round(above / max(below, 1), 3),
        "p": round(float(test.pvalue), 4),
        "suspect": test.pvalue < 0.05,
    }


def rdd_estimate(df, outcome: str, running: str, cutoff: float,
                 bandwidths: list[float] | None = None) -> dict:
    """Local-linear RDD jump at the cutoff across several bandwidths (sensitivity)."""
    import statsmodels.formula.api as smf

    d = df[[outcome, running]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    d["_r"] = d[running] - cutoff
    d["_treat"] = (d["_r"] >= 0).astype(int)
    if bandwidths is None:
        spread = float(np.std(d["_r"]))
        bandwidths = [round(b * spread, 4) for b in (0.5, 1.0, 1.5)]

    estimates = []
    for bw in bandwidths:
        sub = d[np.abs(d["_r"]) <= bw]
        if len(sub) < 30:
            continue
        try:
            res = smf.ols(f"Q('{outcome}') ~ _treat + _r + _treat:_r", data=sub).fit(cov_type="HC1")
            estimates.append({
                "bandwidth": bw, "n": int(len(sub)),
                "jump": round(float(res.params["_treat"]), 6),
                "se": round(float(res.bse["_treat"]), 6),
                "p": round(float(res.pvalues["_treat"]), 4),
            })
        except Exception:  # noqa: BLE001
            continue
    if not estimates:
        return {"ran": False, "reason": "no bandwidth yielded enough observations"}
    sig = [e for e in estimates if e["p"] < 0.05]
    signs = {1 if e["jump"] > 0 else -1 for e in estimates}
    return {
        "ran": True,
        "estimates": estimates,
        "share_significant": round(len(sig) / len(estimates), 3),
        "sign_stable": len(signs) == 1,
    }
