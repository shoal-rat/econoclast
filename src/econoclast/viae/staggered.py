"""Staggered difference-in-differences estimators that avoid the TWFE bias.

A two-way fixed-effects regression with staggered treatment timing can put
negative weights on already-treated comparisons, so its single coefficient can
even have the wrong sign. These estimators fix that:

- Callaway & Sant'Anna (2021): build group-time effects ATT(g, t) from clean 2x2
  comparisons against not-yet-treated units, then aggregate. Inference here is by
  a clustered (block-on-unit) bootstrap.
- Sun & Abraham (2021): a saturated cohort-by-relative-time event study,
  aggregated with cohort shares.
- A Goodman-Bacon style check that contrasts the plain TWFE estimate with the
  Callaway-Sant'Anna overall effect; a large gap flags the negative-weights bias.

The data needs a unit id, a time index, an outcome, and a `cohort` column giving
each unit's first treated period (0 for never-treated).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _wmean(values, weights) -> float:
    w = np.asarray(weights, dtype=float)
    v = np.asarray(values, dtype=float)
    s = w.sum()
    return float((v * w).sum() / s) if s > 0 else float("nan")


def callaway_santanna(
    df: pd.DataFrame, *, unit: str, time: str, outcome: str, cohort: str,
    control: str = "notyet", bootstrap: int = 200, seed_offset: int = 0,
) -> dict:
    wide = df.pivot_table(index=unit, columns=time, values=outcome, aggfunc="mean")
    coh = df.groupby(unit)[cohort].first().reindex(wide.index)
    times = sorted(c for c in wide.columns if pd.notna(c))
    cohorts = sorted({g for g in coh.dropna().unique() if g and g > 0 and (g - 1) in times and g <= max(times)})
    if not cohorts:
        return {"ran": False, "reason": "no usable treated cohorts (need cohort, base period g-1, and post periods)"}

    units = np.array(wide.index)
    coh_vals = coh.to_numpy(dtype=float)

    def att_gt(mult: np.ndarray) -> dict[tuple, tuple]:
        out = {}
        for g in cohorts:
            base = g - 1
            treated = coh_vals == g
            for t in times:
                if t == base:
                    continue
                ref = max(t, base)
                if control == "never":
                    comp = (coh_vals == 0) | np.isnan(coh_vals)
                else:
                    comp = (coh_vals > ref) | (coh_vals == 0) | np.isnan(coh_vals)
                diff = (wide[t] - wide[base]).to_numpy()
                ok = np.isfinite(diff)
                tr = treated & ok
                co = comp & ok
                if mult[tr].sum() < 2 or mult[co].sum() < 2:
                    continue
                att = _wmean(diff[tr], mult[tr]) - _wmean(diff[co], mult[co])
                out[(g, t)] = (att, float(mult[tr].sum()))
        return out

    def aggregate(gt: dict) -> tuple[float, dict]:
        es: dict[int, list] = {}
        for (g, t), (att, wgt) in gt.items():
            es.setdefault(int(t - g), []).append((att, wgt))
        es_agg = {e: _wmean([a for a, _ in v], [w for _, w in v]) for e, v in es.items()}
        post = [(a, w) for (g, t), (a, w) in gt.items() if t >= g]
        overall = _wmean([a for a, _ in post], [w for _, w in post]) if post else float("nan")
        return overall, es_agg

    ones = np.ones(len(units))
    overall, es = aggregate(att_gt(ones))

    # Clustered bootstrap over units.
    rng = np.random.default_rng(12345 + seed_offset)
    boot_overall, boot_es = [], {e: [] for e in es}
    n = len(units)
    for _ in range(max(0, bootstrap)):
        idx = rng.integers(0, n, n)
        mult = np.bincount(idx, minlength=n).astype(float)
        o, e_agg = aggregate(att_gt(mult))
        if np.isfinite(o):
            boot_overall.append(o)
        for e, val in e_agg.items():
            if e in boot_es and np.isfinite(val):
                boot_es[e].append(val)

    se = float(np.std(boot_overall)) if len(boot_overall) > 5 else float("nan")
    from scipy import stats
    p = float(2 * (1 - stats.norm.cdf(abs(overall / se)))) if se and np.isfinite(se) and se > 0 else None

    event_study = {}
    for e in sorted(es):
        ese = float(np.std(boot_es[e])) if len(boot_es[e]) > 5 else float("nan")
        event_study[int(e)] = {"att": round(es[e], 5),
                               "se": round(ese, 5) if np.isfinite(ese) else None}
    pre = [v for e, v in event_study.items() if e < 0 and v["se"]]
    pretrend_violated = any(abs(v["att"]) > 1.96 * v["se"] for v in pre) if pre else False

    return {
        "ran": True, "estimator": "callaway_santanna", "control": control,
        "overall_att": round(overall, 5), "se": round(se, 5) if np.isfinite(se) else None, "p": p,
        "n_cohorts": len(cohorts), "event_study": event_study,
        "pretrend_violated": pretrend_violated,
    }


def twfe_static(df, *, unit, time, outcome, cohort) -> dict:
    """Plain static TWFE estimate of the post-treatment indicator (for contrast)."""
    import statsmodels.formula.api as smf

    d = df[[unit, time, outcome, cohort]].dropna().copy()
    d["_D"] = ((d[cohort] > 0) & (d[time] >= d[cohort])).astype(int)
    try:
        res = smf.ols(f"Q('{outcome}') ~ _D + C(Q('{unit}')) + C(Q('{time}'))", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": d[unit]})
        return {"twfe": round(float(res.params["_D"]), 5), "se": round(float(res.bse["_D"]), 5),
                "p": round(float(res.pvalues["_D"]), 4)}
    except Exception as exc:  # noqa: BLE001
        return {"twfe": None, "reason": str(exc)[:80]}


def bacon_diagnostic(df, *, unit, time, outcome, cohort) -> dict:
    """Contrast TWFE with Callaway-Sant'Anna; a large gap signals negative-weight bias."""
    cs = callaway_santanna(df, unit=unit, time=time, outcome=outcome, cohort=cohort, bootstrap=120)
    tw = twfe_static(df, unit=unit, time=time, outcome=outcome, cohort=cohort)
    out = {"twfe": tw.get("twfe"), "cs_overall": cs.get("overall_att"),
           "cs_se": cs.get("se"), "cs_pretrend_violated": cs.get("pretrend_violated"),
           "event_study": cs.get("event_study")}
    if tw.get("twfe") is not None and cs.get("overall_att") is not None:
        gap = tw["twfe"] - cs["overall_att"]
        denom = max(abs(cs["overall_att"]), 1e-9)
        se = cs.get("se") or 0.0
        out["gap"] = round(gap, 5)
        out["sign_flip"] = (tw["twfe"] * cs["overall_att"] < 0)
        # Flag when TWFE diverges from CS by >30% or by more than 2 CS standard errors.
        out["twfe_biased"] = bool(out["sign_flip"] or abs(gap) / denom > 0.3
                                  or (se > 0 and abs(gap) > 2 * se))
    return out


def sun_abraham(df, *, unit, time, outcome, cohort, window: int = 6) -> dict:
    """Sun & Abraham (2021) interaction-weighted event study (cross-check for CS).

    Saturate cohort-by-relative-time interactions, then aggregate the cohort-
    specific effects with cohort shares. Point estimates only.
    """
    import statsmodels.formula.api as smf

    d = df[[unit, time, outcome, cohort]].dropna().copy()
    d["_rel"] = np.where(d[cohort] > 0, d[time] - d[cohort], np.nan)
    treated = d[d[cohort] > 0]
    cohorts = sorted(treated[cohort].unique())
    terms, col_map = [], {}
    for g in cohorts:
        for e in range(-window, window + 1):
            if e == -1:
                continue  # reference period
            col = f"_d_{int(g)}_{'m' if e < 0 else 'p'}{abs(e)}"  # valid identifier (no minus)
            d[col] = ((d[cohort] == g) & (d["_rel"] == e)).astype(int)
            if d[col].sum() > 0:
                terms.append(col)
                col_map[(g, e)] = col
    if not terms:
        return {"ran": False, "reason": "no cohort-by-relative-time cells"}
    rhs = " + ".join(terms + [f"C(Q('{unit}'))", f"C(Q('{time}'))"])
    try:
        res = smf.ols(f"Q('{outcome}') ~ {rhs}", data=d).fit(
            cov_type="cluster", cov_kwds={"groups": d[unit]})
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "reason": str(exc)[:80]}

    # Cohort sizes (unique units per cohort) for the interaction weights.
    sizes = treated.groupby(cohort)[unit].nunique().to_dict()
    es = {}
    for e in range(-window, window + 1):
        if e == -1:
            es[-1] = 0.0
            continue
        present = [(g, col_map[(g, e)]) for g in cohorts if (g, e) in col_map]
        if not present:
            continue
        total = sum(sizes.get(g, 0) for g, _ in present)
        if total == 0:
            continue
        es[int(e)] = round(float(sum(sizes.get(g, 0) * res.params.get(col, 0.0)
                                     for g, col in present) / total), 5)
    return {"ran": True, "estimator": "sun_abraham", "event_study": es}

