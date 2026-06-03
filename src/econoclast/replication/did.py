"""DiD replication checks: event-study leads (pre-trends) and a placebo.

A clean parallel-trends assumption implies the pre-treatment 'lead' coefficients
are jointly indistinguishable from zero. We estimate an event-study with unit and
time fixed effects and test the leads. (For staggered adoption, confirm with
Callaway-Sant'Anna / Sun-Abraham — TWFE event studies can be biased.)
"""

from __future__ import annotations

import numpy as np


def event_study(df, *, unit: str, time: str, outcome: str, treated: str,
                treat_time, max_leads: int = 5, max_lags: int = 5) -> dict:
    """Estimate an event-study and test pre-trends (joint significance of leads)."""
    import statsmodels.formula.api as smf

    d = df[[unit, time, outcome, treated]].replace([np.inf, -np.inf], np.nan).dropna().copy()
    d["_rel"] = d[time] - treat_time
    # Only treated units get event time; controls stay at a reference bin.
    d.loc[d[treated] == 0, "_rel"] = np.nan

    leads, lags = [], []
    terms = []
    for k in range(1, max_leads + 1):
        col = f"_lead{k}"
        d[col] = (d["_rel"] == -k).astype(int)
        if d[col].sum() > 0:
            leads.append(col)
            terms.append(col)
    for k in range(0, max_lags + 1):
        col = f"_lag{k}"
        d[col] = (d["_rel"] == k).astype(int)
        if d[col].sum() > 0:
            lags.append(col)
            terms.append(col)
    if not leads:
        return {"ran": False, "reason": "no pre-treatment periods (leads) available"}

    rhs = " + ".join(terms + [f"C(Q('{unit}'))", f"C(Q('{time}'))"])
    try:
        res = smf.ols(f"Q('{outcome}') ~ {rhs}", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": d[unit]})
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "reason": f"estimation failed: {exc}"}

    lead_coefs = {c: {"coef": round(float(res.params.get(c, np.nan)), 6),
                      "p": round(float(res.pvalues.get(c, np.nan)), 4)} for c in leads}
    # Joint Wald test that all leads are zero.
    try:
        wald = res.f_test(" , ".join(f"{c} = 0" for c in leads))
        joint_p = float(np.ravel(wald.pvalue))
    except Exception:  # noqa: BLE001
        joint_p = float("nan")
    any_sig_lead = any(v["p"] < 0.05 for v in lead_coefs.values())
    return {
        "ran": True,
        "leads": lead_coefs,
        "joint_pretrend_p": round(joint_p, 4) if joint_p == joint_p else None,
        "pretrend_violated": (joint_p < 0.05) if joint_p == joint_p else any_sig_lead,
        "lags": {c: round(float(res.params.get(c, np.nan)), 6) for c in lags},
    }
