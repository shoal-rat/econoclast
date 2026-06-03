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
from econoclast.replication.rdd import manipulation_test, rdd_estimate

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
        out["rdd_manipulation"] = manipulation_test(df[config.running_var], float(config.cutoff))
        out["rdd_sensitivity"] = rdd_estimate(df, config.outcome, config.running_var, float(config.cutoff))

    if config.unit and config.time and config.treated and config.treat_time is not None:
        df = _load(config.data)
        out["did_event_study"] = event_study(
            df, unit=config.unit, time=config.time, outcome=config.outcome,
            treated=config.treated, treat_time=config.treat_time)

    return out


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
            title="Possible manipulation of the running variable at the cutoff",
            category="identification", severity="high", confidence=0.7,
            detail=(f"Density discontinuity screening: {rdd['above']} observations just above vs "
                    f"{rdd['below']} just below the cutoff (binomial p={rdd['p']}). Sorting around "
                    f"the threshold would invalidate the RDD."),
            recommendation="Run a formal McCrary / Cattaneo-Jansson-Ma density test and inspect covariate continuity.",
            data=rdd))
    sens = result.get("rdd_sensitivity", {})
    if sens.get("ran") and (not sens.get("sign_stable") or sens.get("share_significant", 1) < 0.5):
        findings.append(Finding(
            attack="rdd-bandwidth", title="RDD estimate is sensitive to bandwidth",
            category="robustness", severity="medium", confidence=0.75,
            detail=f"The jump's significance/sign is not stable across bandwidths: {sens['estimates']}",
            recommendation="Report the CCT optimal bandwidth and a bandwidth-sensitivity plot.",
            data=sens))

    did = result.get("did_event_study", {})
    if did.get("ran") and did.get("pretrend_violated"):
        findings.append(Finding(
            attack="did-pretrends",
            title="Pre-trends: lead coefficients are jointly non-zero",
            category="identification", severity="high", confidence=0.75,
            detail=(f"The event-study leads reject the parallel-trends assumption "
                    f"(joint p={did.get('joint_pretrend_p')}). Pre-treatment differences undercut the DiD."),
            recommendation="Show the event-study plot; consider Callaway-Sant'Anna / Sun-Abraham for staggered timing.",
            data={"leads": did.get("leads"), "joint_pretrend_p": did.get("joint_pretrend_p")}))

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
