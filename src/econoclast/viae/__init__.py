"""Mille Viae, a thousand roads: re-estimate the result across every defensible specification.

This is the strike in the Throne Hall. It needs the data. Given a ``SpecConfig`` (which
the Sicarius fills in after reading the paper and the dataset's columns) it runs a
specification curve and, when the design calls for it, the McCrary density test,
bandwidth sensitivity, Callaway-Sant'Anna, Sun-Abraham and the Goodman-Bacon contrast,
then turns what it finds into wounds.
"""

from __future__ import annotations

from typing import Any

from econoclast.case.models import Wound
from econoclast.log import get_logger
from econoclast.viae.did import event_study
from econoclast.viae.io import load_table as _load
from econoclast.viae.models import SpecConfig, SpecCurve, SpecResult
from econoclast.viae.multiverse import run_multiverse
from econoclast.viae.rdd import mccrary_density_test, rdd_estimate
from econoclast.viae.staggered import bacon_diagnostic, sun_abraham

log = get_logger("replication")

__all__ = [
    "SpecConfig",
    "SpecCurve",
    "SpecResult",
    "run_multiverse",
    "run_replication",
    "viae_wounds",
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


def viae_wounds(result: dict[str, Any], artifact: str = "") -> list[Wound]:
    """Turn a replication result into computation wounds (empty when the result holds)."""
    arts = [artifact] if artifact else []
    findings: list[Wound] = []
    curve = result.get("spec_curve", {})
    summ = curve.get("summary", {})
    if summ:
        share = summ.get("share_significant_expected_sign", 0.0)
        k = summ.get("n_specs_run", 0)
        if share < 0.5:
            sev = "high" if share < 0.25 else "medium"
            findings.append(Wound(
                blade="mille_viae", evidence_kind="computation", artifacts=arts,
                title=f"Headline result is significant in only {share:.0%} of {k} plausible specifications",
                severity=sev,
                confidence=0.9,
                detail=(f"Across {k} equally-defensible specifications (controls × fixed effects × "
                        f"clustering × sample), the focal coefficient is significant in the expected "
                        f"direction in {share:.0%}. Coef ranges [{summ.get('min_coef')}, "
                        f"{summ.get('max_coef')}] with median {summ.get('median_coef')}."),
                remedy="Report the full specification curve, not a single hand-picked specification.",
                data=summ,
            ))
        elif share < 0.8:
            findings.append(Wound(
                blade="mille_viae", evidence_kind="computation", artifacts=arts, title=f"Result significant in {share:.0%} of specifications (some fragility)", severity="low", confidence=0.8,
                detail=f"{share:.0%} of {k} specifications are significant in the expected direction.",
                data=summ))

    rdd = result.get("rdd_manipulation", {})
    if rdd.get("ran") and rdd.get("suspect"):
        findings.append(Wound(
            blade="persona", evidence_kind="computation", artifacts=arts,
            title="Density of the running variable jumps at the cutoff (McCrary test)", severity="high", confidence=0.75,
            detail=(f"McCrary density test: log-density jump theta={rdd['theta']} "
                    f"(z={rdd['z']}, p={rdd['p']}). A discontinuity in the density is evidence of "
                    f"sorting/manipulation around the threshold, which invalidates the RDD."),
            remedy="Confirm with rddensity (Cattaneo-Jansson-Ma) and check covariate continuity at the cutoff.",
            data=rdd))
    sens = result.get("rdd_sensitivity", {})
    if sens.get("ran") and (not sens.get("sign_stable") or sens.get("share_significant", 1) < 0.5):
        findings.append(Wound(
            blade="scutum", evidence_kind="computation", artifacts=arts, title="RDD estimate is sensitive to bandwidth", severity="medium", confidence=0.75,
            detail=f"The jump's significance/sign is not stable across bandwidths: {sens['estimates']}",
            remedy="Report the CCT optimal bandwidth and a bandwidth-sensitivity plot.",
            data=sens))

    # Staggered DiD via Callaway-Sant'Anna + the TWFE-vs-CS (Goodman-Bacon) check.
    bac = result.get("did_callaway_santanna", {})
    if bac.get("twfe_biased"):
        findings.append(Wound(
            blade="persona", evidence_kind="computation", artifacts=arts,
            title="TWFE estimate diverges from Callaway-Sant'Anna (negative-weight bias)", severity="high", confidence=0.8,
            detail=(f"The plain two-way fixed-effects estimate is {bac.get('twfe')}, but the "
                    f"Callaway-Sant'Anna overall ATT is {bac.get('cs_overall')} "
                    f"(gap {bac.get('gap')}{', sign flip' if bac.get('sign_flip') else ''}). With "
                    f"staggered timing, TWFE uses already-treated units as controls and can be badly biased."),
            remedy="Report a heterogeneity-robust estimator (Callaway-Sant'Anna / Sun-Abraham), not plain TWFE.",
            data={k: bac.get(k) for k in ("twfe", "cs_overall", "cs_se", "gap", "sign_flip")}))
    if bac.get("cs_pretrend_violated"):
        findings.append(Wound(
            blade="persona", evidence_kind="computation", artifacts=arts,
            title="Pre-trends: Callaway-Sant'Anna lead effects are non-zero", severity="high", confidence=0.75,
            detail="Pre-treatment event-study effects are significantly different from zero, which "
                   "undercuts the parallel-trends assumption.",
            remedy="Show the event-study plot and justify parallel trends.",
            data={"event_study": bac.get("event_study")}))

    did = result.get("did_event_study", {})
    if did.get("ran") and did.get("pretrend_violated") and not bac:
        findings.append(Wound(
            blade="persona", evidence_kind="computation", artifacts=arts,
            title="Pre-trends: lead coefficients are jointly non-zero", severity="high", confidence=0.7,
            detail=f"The event-study leads reject parallel trends (joint p={did.get('joint_pretrend_p')}).",
            remedy="Show the event-study plot; use Callaway-Sant'Anna / Sun-Abraham for staggered timing.",
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

