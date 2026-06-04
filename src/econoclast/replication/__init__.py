"""Replication mode: re-estimate the result across a multiverse of specifications.

Unlike the PDF-only forensics, this needs the dataset. Given a `SpecConfig`
(which the agent fills in after reading the paper + the data columns), it runs a
specification-curve / multiverse analysis and, when relevant, RDD manipulation
and DiD pre-trend checks — then turns the result into `Finding`s.
"""

from __future__ import annotations

from typing import Any

from econoclast.attacks.base import Finding
from econoclast.logging import get_logger
from econoclast.replication.did import event_study
from econoclast.replication.models import SpecConfig, SpecCurve, SpecResult
from econoclast.replication.multiverse import run_multiverse
from econoclast.replication.rdd import mccrary_density_test, rdd_estimate
from econoclast.replication.staggered import bacon_diagnostic, sun_abraham

log = get_logger("replication")

__all__ = [
    "SpecConfig",
    "SpecCurve",
    "SpecResult",
    "run_multiverse",
    "run_replication",
    "replication_findings",
    "template_config",
]


def run_replication(config: SpecConfig) -> dict[str, Any]:
    """Run every applicable replication check and return a structured result."""
    out: dict[str, Any] = {}
    curve = run_multiverse(config)
    out["spec_curve"] = curve.to_dict()

    if config.running_var and config.cutoff is not None:
        df = _load(config.data)
        out["rdd_manipulation"] = mccrary_density_test(df[config.running_var], float(config.cutoff))
        out["rdd_sensitivity"] = rdd_estimate(df, config.outcome, config.running_var, float(config.cutoff))

    # Staggered DiD: prefer a cohort column; otherwise synthesise one from a
    # single treatment time + a treated indicator.
    cohort_col = _resolve_cohort(config)
    if cohort_col is not None and config.unit and config.time:
        df = _load(config.data)
        if cohort_col == "_cohort" and "_cohort" not in df.columns:
            df["_cohort"] = (df[config.treated] > 0).astype(float) * float(config.treat_time)
        out["did_callaway_santanna"] = bacon_diagnostic(
            df, unit=config.unit, time=config.time, outcome=config.outcome, cohort=cohort_col)
        out["did_sun_abraham"] = sun_abraham(
            df, unit=config.unit, time=config.time, outcome=config.outcome, cohort=cohort_col)
    elif config.unit and config.time and config.treated and config.treat_time is not None:
        df = _load(config.data)
        out["did_event_study"] = event_study(
            df, unit=config.unit, time=config.time, outcome=config.outcome,
            treated=config.treated, treat_time=config.treat_time)

    return out


def _resolve_cohort(config: SpecConfig) -> str | None:
    if config.cohort:
        return config.cohort
    if config.unit and config.time and config.treated and config.treat_time is not None:
        return "_cohort"
    return None


def replication_findings(result: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    curve = result.get("spec_curve", {})
    summ = curve.get("summary", {})
    if summ:
        share = summ.get("share_significant_expected_sign", 0.0)
        k = summ.get("n_specs_run", 0)
        if share < 0.5:
            sev = "high" if share < 0.25 else "medium"
            findings.append(Finding(
                attack="multiverse",
                title=f"Headline result is significant in only {share:.0%} of {k} plausible specifications",
                category="specification_search",
                severity=sev,
                confidence=0.9,
                detail=(f"Across {k} equally-defensible specifications (controls × fixed effects × "
                        f"clustering × sample), the focal coefficient is significant in the expected "
                        f"direction in {share:.0%}. Coef ranges [{summ.get('min_coef')}, "
                        f"{summ.get('max_coef')}] with median {summ.get('median_coef')}."),
                recommendation="Report the full specification curve, not a single hand-picked specification.",
                data=summ,
            ))
        elif share < 0.8:
            findings.append(Finding(
                attack="multiverse", title=f"Result significant in {share:.0%} of specifications (some fragility)",
                category="robustness", severity="low", confidence=0.8,
                detail=f"{share:.0%} of {k} specifications are significant in the expected direction.",
                data=summ))

    rdd = result.get("rdd_manipulation", {})
    if rdd.get("ran") and rdd.get("suspect"):
        findings.append(Finding(
            attack="rdd-manipulation",
            title="Density of the running variable jumps at the cutoff (McCrary test)",
            category="identification", severity="high", confidence=0.75,
            detail=(f"McCrary density test: log-density jump theta={rdd['theta']} "
                    f"(z={rdd['z']}, p={rdd['p']}). A discontinuity in the density is evidence of "
                    f"sorting/manipulation around the threshold, which invalidates the RDD."),
            recommendation="Confirm with rddensity (Cattaneo-Jansson-Ma) and check covariate continuity at the cutoff.",
            data=rdd))
    sens = result.get("rdd_sensitivity", {})
    if sens.get("ran") and (not sens.get("sign_stable") or sens.get("share_significant", 1) < 0.5):
        findings.append(Finding(
            attack="rdd-bandwidth", title="RDD estimate is sensitive to bandwidth",
            category="robustness", severity="medium", confidence=0.75,
            detail=f"The jump's significance/sign is not stable across bandwidths: {sens['estimates']}",
            recommendation="Report the CCT optimal bandwidth and a bandwidth-sensitivity plot.",
            data=sens))

    # Staggered DiD via Callaway-Sant'Anna + the TWFE-vs-CS (Goodman-Bacon) check.
    bac = result.get("did_callaway_santanna", {})
    if bac.get("twfe_biased"):
        findings.append(Finding(
            attack="did-twfe-bias",
            title="TWFE estimate diverges from Callaway-Sant'Anna (negative-weight bias)",
            category="identification", severity="high", confidence=0.8,
            detail=(f"The plain two-way fixed-effects estimate is {bac.get('twfe')}, but the "
                    f"Callaway-Sant'Anna overall ATT is {bac.get('cs_overall')} "
                    f"(gap {bac.get('gap')}{', sign flip' if bac.get('sign_flip') else ''}). With "
                    f"staggered timing, TWFE uses already-treated units as controls and can be badly biased."),
            recommendation="Report a heterogeneity-robust estimator (Callaway-Sant'Anna / Sun-Abraham), not plain TWFE.",
            data={k: bac.get(k) for k in ("twfe", "cs_overall", "cs_se", "gap", "sign_flip")}))
    if bac.get("cs_pretrend_violated"):
        findings.append(Finding(
            attack="did-pretrends",
            title="Pre-trends: Callaway-Sant'Anna lead effects are non-zero",
            category="identification", severity="high", confidence=0.75,
            detail="Pre-treatment event-study effects are significantly different from zero, which "
                   "undercuts the parallel-trends assumption.",
            recommendation="Show the event-study plot and justify parallel trends.",
            data={"event_study": bac.get("event_study")}))

    did = result.get("did_event_study", {})
    if did.get("ran") and did.get("pretrend_violated") and not bac:
        findings.append(Finding(
            attack="did-pretrends",
            title="Pre-trends: lead coefficients are jointly non-zero",
            category="identification", severity="high", confidence=0.7,
            detail=f"The event-study leads reject parallel trends (joint p={did.get('joint_pretrend_p')}).",
            recommendation="Show the event-study plot; use Callaway-Sant'Anna / Sun-Abraham for staggered timing.",
            data={"leads": did.get("leads")}))

    return findings


def template_config(data_path: str) -> SpecConfig:
    """Generate a starter config by inspecting the dataset's columns."""
    df = _load(data_path)
    cols = list(df.columns)
    numeric = [c for c in cols if str(df[c].dtype).startswith(("int", "float"))]
    return SpecConfig(
        data=data_path,
        outcome=numeric[0] if numeric else (cols[0] if cols else "OUTCOME"),
        treatment=numeric[1] if len(numeric) > 1 else "TREATMENT",
        controls_pool=numeric[2:8],
        fixed_effects=[],
        cluster=[],
        sample_filters=[],
    )


def _load(path: str):
    import pandas as pd

    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    if path.endswith(".dta"):
        return pd.read_stata(path)
    return pd.read_csv(path)
