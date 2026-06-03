"""Regression estimators for the multiverse (statsmodels-based).

We fit each specification ourselves rather than re-running author code, so the
results are safe and reproducible. OLS (with FE dummies and cluster-robust SEs),
logit, and a manual 2SLS for IV.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from econoclast.replication.models import SpecResult


def _q(name: str) -> str:
    return f"Q('{name}')"


def _focal_key(df: pd.DataFrame, treatment: str) -> str:
    return _q(treatment)


def fit_spec(
    df: pd.DataFrame,
    *,
    outcome: str,
    treatment: str,
    controls: list[str],
    fixed_effects: list[str],
    cluster: str,
    estimator: str = "ols",
    instruments: list[str] | None = None,
    endogenous: str = "",
    spec: dict | None = None,
) -> SpecResult | None:
    """Fit one specification; return the focal coefficient's stats (or None on failure)."""
    import statsmodels.formula.api as smf

    cols = [outcome, treatment, *controls, *fixed_effects]
    if cluster:
        cols.append(cluster)
    if estimator == "iv":
        cols += list(instruments or [])
    cols = [c for c in dict.fromkeys(cols) if c]
    data = df[[c for c in cols if c in df.columns]].copy()
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < max(20, len(cols) + 5):
        return None

    try:
        if estimator == "iv":
            return _fit_iv(data, outcome, treatment, controls, fixed_effects,
                           instruments or [], endogenous or treatment, cluster, spec)
        rhs = " + ".join([_q(treatment), *[_q(c) for c in controls],
                          *[f"C({_q(fe)})" for fe in fixed_effects]]) or "1"
        formula = f"{_q(outcome)} ~ {rhs}"
        model = smf.logit(formula, data=data) if estimator == "logit" else smf.ols(formula, data=data)
        if cluster and estimator != "logit":
            res = model.fit(cov_type="cluster", cov_kwds={"groups": data[cluster]}, disp=0)
        elif estimator == "logit":
            res = model.fit(disp=0)
        else:
            res = model.fit(cov_type="HC1")
        return _extract(res, treatment, len(data), spec)
    except Exception:  # noqa: BLE001 — a failed spec is dropped, not fatal
        return None


def _extract(res, treatment: str, n: int, spec: dict | None) -> SpecResult | None:
    key = _q(treatment)
    if key not in res.params.index:
        # patsy may have renamed; find the param mentioning the treatment.
        cands = [k for k in res.params.index if treatment in k]
        if not cands:
            return None
        key = cands[0]
    coef = float(res.params[key])
    se = float(res.bse[key])
    t = float(res.tvalues[key])
    p = float(res.pvalues[key])
    return SpecResult(coef=coef, se=se, t=t, p=p, n=n, spec=spec or {})


def _fit_iv(data, outcome, treatment, controls, fixed_effects, instruments,
            endogenous, cluster, spec) -> SpecResult | None:
    """Manual 2SLS: first-stage fitted endogenous, then OLS with cluster SEs."""
    import statsmodels.formula.api as smf

    exog = [_q(c) for c in controls] + [f"C({_q(fe)})" for fe in fixed_effects]
    instr = [_q(i) for i in instruments]
    if not instr:
        return None
    # First stage: endogenous ~ instruments + exog
    fs_rhs = " + ".join(instr + exog) or "1"
    fs = smf.ols(f"{_q(endogenous)} ~ {fs_rhs}", data=data).fit()
    data = data.copy()
    data["_endog_hat"] = fs.fittedvalues
    # Second stage: outcome ~ endog_hat + exog
    ss_rhs = " + ".join(["_endog_hat", *exog]) or "1"
    model = smf.ols(f"{_q(outcome)} ~ {ss_rhs}", data=data)
    res = (model.fit(cov_type="cluster", cov_kwds={"groups": data[cluster]})
           if cluster else model.fit(cov_type="HC1"))
    if "_endog_hat" not in res.params.index:
        return None
    return SpecResult(coef=float(res.params["_endog_hat"]), se=float(res.bse["_endog_hat"]),
                      t=float(res.tvalues["_endog_hat"]), p=float(res.pvalues["_endog_hat"]),
                      n=len(data), spec=spec or {})
