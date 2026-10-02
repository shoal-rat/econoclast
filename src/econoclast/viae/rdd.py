"""RDD replication checks: manipulation of the running variable + bandwidth sensitivity.

The manipulation test is a screening density-discontinuity test (binomial on a
window around the cutoff, plus a binned local-linear density jump). It flags
sorting; confirm with `rdrobust` / Cattaneo-Jansson-Ma before drawing conclusions.
"""

from __future__ import annotations

import math

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


def mccrary_density_test(running, cutoff: float, b: float | None = None,
                         h: float | None = None) -> dict:
    """McCrary (2008) density-discontinuity test.

    Bins the running variable so the cutoff is a bin edge, smooths the histogram
    with a triangular-kernel local linear regression on each side, and tests the
    log-density jump theta = log f(+) - log f(-). For publication use rddensity
    (Cattaneo-Jansson-Ma); this is a faithful screening version with a
    rule-of-thumb bandwidth, plus a sensitivity scan.

    Reference: McCrary (2008), "Manipulation of the running variable in the
    regression discontinuity design", Journal of Econometrics.
    """
    z = np.asarray(running, dtype=float)
    z = z[np.isfinite(z)] - cutoff
    n = z.size
    if n < 50:
        return {"ran": False, "reason": "fewer than 50 observations"}
    sd = float(np.std(z))
    iqr = float(np.subtract(*np.percentile(z, [75, 25])))
    if b is None:
        b = 2.0 * sd * n ** -0.5  # McCrary default bin width
    if b <= 0:
        return {"ran": False, "reason": "degenerate running variable"}

    def _theta_se(bw: float) -> dict | None:
        k = np.floor(z / b).astype(int)
        uniq, counts = np.unique(k, return_counts=True)
        mids = (uniq + 0.5) * b
        dens = counts / (n * b)
        f_plus = _local_linear(mids[mids >= 0], dens[mids >= 0], bw)
        f_minus = _local_linear(mids[mids < 0], dens[mids < 0], bw)
        if not f_plus or not f_minus or f_plus <= 0 or f_minus <= 0:
            return None
        theta = math.log(f_plus) - math.log(f_minus)
        se = math.sqrt((1.0 / (n * bw)) * (24.0 / 5.0) * (1.0 / f_plus + 1.0 / f_minus))
        zstat = theta / se if se > 0 else 0.0
        p = 2.0 * (1.0 - stats.norm.cdf(abs(zstat)))
        return {"bandwidth": round(bw, 4), "f_plus": round(f_plus, 4), "f_minus": round(f_minus, 4),
                "theta": round(theta, 4), "se": round(se, 4), "z": round(zstat, 3), "p": round(p, 4)}

    h0 = h if h is not None else max(2 * b, 1.06 * min(sd, iqr / 1.349 if iqr > 0 else sd) * n ** -0.2)
    main = _theta_se(h0)
    if main is None:
        return {"ran": False, "reason": "could not estimate density at the cutoff"}
    scan = [r for r in (_theta_se(h0 * m) for m in (0.5, 1.0, 1.5, 2.0)) if r]
    return {
        "ran": True, "cutoff": cutoff, "binwidth": round(b, 4),
        "theta": main["theta"], "se": main["se"], "z": main["z"], "p": main["p"],
        # Conservative flag: the local-linear estimator has boundary bias, so we
        # require strong significance AND a non-trivial jump to avoid false alarms.
        "suspect": bool(main["p"] < 0.01 and abs(main["theta"]) > 0.2),
        "bandwidth_scan": scan,
    }


def _local_linear(x, y, h: float) -> float | None:
    """Triangular-kernel local linear fit of y on x, evaluated at 0."""
    if len(x) < 2:
        return None
    w = np.maximum(0.0, 1.0 - np.abs(x) / h)
    if w.sum() <= 0:
        return None
    X = np.column_stack([np.ones_like(x), x])
    W = np.diag(w)
    try:
        beta = np.linalg.lstsq(W @ X, W @ y, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None
    return float(beta[0])  # intercept = density at x=0


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
