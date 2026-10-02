"""Novacula, Occam's razor on the data: does the theory's extra machinery earn its keep?

Fits the plain model and the paper's richer one on the same rows and reports what the
added terms buy: information criteria, adjusted R2, a likelihood-ratio test, and
out-of-sample error under k-fold cross-validation. A theory whose extra mechanisms add
parameters but no predictive or explanatory power is a candidate for the razor.
"""

from __future__ import annotations

import numpy as np

from econoclast.viae.io import load_table


def _q(term: str) -> str:
    """Quote bare column names for patsy; leave expressions alone."""
    t = term.strip()
    return f"Q('{t}')" if t.replace("_", "").replace(".", "").isalnum() else t


def compare_models(data: str, outcome: str, simple_terms: list[str], extra_terms: list[str], *,
                   cluster: str = "", folds: int = 5, seed: int = 0) -> dict:
    import statsmodels.formula.api as smf
    from scipy import stats

    df = load_table(data)
    cols = {c for c in df.columns}
    needed = [outcome] + [t for t in simple_terms + extra_terms if t in cols] + ([cluster] if cluster else [])
    d = df.dropna(subset=[c for c in needed if c in cols]).reset_index(drop=True)
    rhs_s = " + ".join(_q(t) for t in simple_terms) or "1"
    rhs_f = " + ".join(_q(t) for t in simple_terms + extra_terms) or "1"
    f_s, f_f = f"{_q(outcome)} ~ {rhs_s}", f"{_q(outcome)} ~ {rhs_f}"
    m_s, m_f = smf.ols(f_s, data=d).fit(), smf.ols(f_f, data=d).fit()
    k_extra = int(m_f.df_model - m_s.df_model)
    lr = 2 * (m_f.llf - m_s.llf)
    p_lr = float(stats.chi2.sf(lr, max(k_extra, 1)))

    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(d))
    chunks = np.array_split(idx, max(2, folds))
    err_s, err_f = [], []
    for k in range(len(chunks)):
        test = chunks[k]
        train = np.concatenate([c for j, c in enumerate(chunks) if j != k])
        tr, te = d.iloc[train], d.iloc[test]
        try:
            ps = smf.ols(f_s, data=tr).fit().predict(te)
            pf = smf.ols(f_f, data=tr).fit().predict(te)
        except Exception:  # noqa: BLE001 - a fold with a missing category is skipped
            continue
        y = te[outcome].astype(float)
        err_s.append(float(np.sqrt(np.mean((y - ps) ** 2))))
        err_f.append(float(np.sqrt(np.mean((y - pf) ** 2))))
    cv_s = float(np.mean(err_s)) if err_s else None
    cv_f = float(np.mean(err_f)) if err_f else None
    gain = (cv_s - cv_f) / cv_s if cv_s and cv_f is not None else None

    delta_bic = float(m_f.bic - m_s.bic)
    if delta_bic > 2 and (gain is None or gain < 0.01):
        verdict = "shave"  # the extra machinery costs more than it explains
    elif delta_bic < -6 and (gain is None or gain > 0.01):
        verdict = "keep"
    else:
        verdict = "marginal"
    return {
        "rows": int(len(d)), "extra_parameters": k_extra,
        "simple": {"formula": f_s, "aic": round(m_s.aic, 2), "bic": round(m_s.bic, 2), "adj_r2": round(m_s.rsquared_adj, 4)},
        "full": {"formula": f_f, "aic": round(m_f.aic, 2), "bic": round(m_f.bic, 2), "adj_r2": round(m_f.rsquared_adj, 4)},
        "delta_aic": round(float(m_f.aic - m_s.aic), 2), "delta_bic": round(delta_bic, 2),
        "lr_stat": round(float(lr), 3), "lr_p": round(p_lr, 5),
        "cv_rmse_simple": None if cv_s is None else round(cv_s, 5),
        "cv_rmse_full": None if cv_f is None else round(cv_f, 5),
        "cv_rmse_gain": None if gain is None else round(gain, 4),
        "verdict": verdict,
        "reading": {"shave": "BIC prefers the plain model and the extra terms do not predict better out of sample.",
                    "keep": "The extra terms clearly improve fit in sample and out of sample.",
                    "marginal": "The extra terms help a little; judge whether the theory needs them."}[verdict],
    }
