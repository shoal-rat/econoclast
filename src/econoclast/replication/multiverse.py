"""Specification-curve / multiverse analysis.

Enumerate the cross-product of plausible analytic choices — which controls, which
fixed effects, which clustering, which sample — run the focal regression for each,
and summarise how stable the headline coefficient is. A result that is only
significant in a small fraction of equally-defensible specifications is fragile.

Reference: Simonsohn, Simmons & Nelson (2020), "Specification curve analysis",
Nature Human Behaviour; Steegen et al. (2016), "Increasing transparency through a
multiverse analysis", Perspectives on Psychological Science.
"""

from __future__ import annotations

import itertools
import random
import statistics

import numpy as np

from econoclast.logging import get_logger
from econoclast.replication.estimators import fit_spec
from econoclast.replication.models import SpecConfig, SpecCurve, SpecResult

log = get_logger("replication.multiverse")


def _load(path: str):
    import pandas as pd

    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    if path.endswith(".dta"):
        return pd.read_stata(path)
    return pd.read_csv(path)


def _control_options(pool: list[str], mode: str) -> list[list[str]]:
    if not pool:
        return [[]]
    if mode == "allnone":
        return [[], list(pool)]
    if mode == "incremental":
        return [list(pool[:k]) for k in range(len(pool) + 1)]
    if mode == "powerset" or (mode == "auto" and len(pool) <= 6):
        opts = []
        for r in range(len(pool) + 1):
            opts.extend([list(c) for c in itertools.combinations(pool, r)])
        return opts
    # auto, large pool: none / each single / all-but-one / all
    opts: list[list[str]] = [[], list(pool)]
    opts += [[c] for c in pool]
    opts += [[c for c in pool if c != drop] for drop in pool]
    return opts


def _dedup(seqs: list[list[str]]) -> list[list[str]]:
    seen, out = set(), []
    for s in seqs:
        key = tuple(sorted(s))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


def run_multiverse(config: SpecConfig) -> SpecCurve:
    df = _load(config.data)
    missing = [c for c in [config.outcome, config.treatment] if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in data: {missing}")

    control_opts = _dedup(_control_options(config.controls_pool, config.controls_mode))
    fe_opts = config.fixed_effects or [[]]
    if [] not in fe_opts and config.fixed_effects:
        fe_opts = [[], *fe_opts]
    cluster_opts = config.cluster or [""]
    if "" not in cluster_opts:
        cluster_opts = ["", *cluster_opts]
    filter_opts = config.sample_filters or [""]
    if "" not in filter_opts:
        filter_opts = ["", *filter_opts]

    combos = list(itertools.product(control_opts, fe_opts, cluster_opts, filter_opts))
    random.seed(0)
    if len(combos) > config.max_specs:
        log.warning("Multiverse has %d specs; sampling %d (seed=0).", len(combos), config.max_specs)
        combos = random.sample(combos, config.max_specs)

    results: list[SpecResult] = []
    filtered_cache: dict[str, object] = {"": df}
    for controls, fe, cluster, filt in combos:
        if filt not in filtered_cache:
            try:
                filtered_cache[filt] = df.query(filt)
            except Exception:  # noqa: BLE001
                filtered_cache[filt] = None
        sub = filtered_cache[filt]
        if sub is None or len(sub) < 20:
            continue
        spec = {"controls": controls, "fe": fe, "cluster": cluster or "robust", "filter": filt or "full"}
        r = fit_spec(sub, outcome=config.outcome, treatment=config.treatment,
                     controls=controls, fixed_effects=fe, cluster=cluster,
                     estimator=config.estimator, instruments=config.instruments,
                     endogenous=config.endogenous, spec=spec)
        if r is not None and np.isfinite(r.coef) and np.isfinite(r.p):
            results.append(r)

    if not results:
        raise RuntimeError("No specification could be estimated — check the config and data.")

    coefs = [r.coef for r in results]
    pref_sign = config.preferred_sign or (1 if statistics.median(coefs) > 0 else -1)
    n_sig = sum(1 for r in results if r.significant)
    n_sig_expected = sum(1 for r in results if r.significant and r.sign == pref_sign)
    k = len(results)

    summary = {
        "n_specs_run": k,
        "n_specs_enumerated": len(combos),
        "share_significant": round(n_sig / k, 3),
        "share_significant_expected_sign": round(n_sig_expected / k, 3),
        "share_same_sign_as_preferred": round(sum(1 for r in results if r.sign == pref_sign) / k, 3),
        "preferred_sign": pref_sign,
        "median_coef": round(statistics.median(coefs), 6),
        "mean_coef": round(statistics.fmean(coefs), 6),
        "min_coef": round(min(coefs), 6),
        "max_coef": round(max(coefs), 6),
        "coef_iqr": [round(np.percentile(coefs, 25), 6), round(np.percentile(coefs, 75), 6)],
        "median_p": round(statistics.median([r.p for r in results]), 4),
    }

    # Reference spec: all controls, first FE option, first cluster, full sample.
    preferred = fit_spec(df, outcome=config.outcome, treatment=config.treatment,
                         controls=config.controls_pool, fixed_effects=fe_opts[-1],
                         cluster=(config.cluster[0] if config.cluster else ""),
                         estimator=config.estimator, instruments=config.instruments,
                         endogenous=config.endogenous,
                         spec={"controls": "all", "fe": fe_opts[-1], "note": "reference"})

    log.info("Multiverse: %d specs run; %.0f%% significant in the expected direction.",
             k, 100 * summary["share_significant_expected_sign"])
    return SpecCurve(results=results, summary=summary, preferred=preferred)
