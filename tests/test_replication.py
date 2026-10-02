"""Replication / multiverse tests (skipped if statsmodels/pandas absent)."""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("statsmodels")

import numpy as np  # noqa: E402

from econoclast.viae import (  # noqa: E402
    run_multiverse,
    template_config,
    viae_wounds,
)
from econoclast.viae.models import SpecConfig  # noqa: E402


def _fragile_dataset(path):
    rng = np.random.default_rng(0)
    n = 500
    c1 = rng.standard_normal(n)
    c2 = rng.standard_normal(n)
    treat = 0.7 * c1 + rng.standard_normal(n)  # treat confounded with c1
    y = 1.2 * c1 + 0.0 * treat + 0.4 * c2 + rng.standard_normal(n)  # true effect = 0
    pd.DataFrame({"y": y, "treat": treat, "c1": c1, "c2": c2}).to_csv(path, index=False)


def test_multiverse_flags_fragile_effect(tmp_path):
    data = tmp_path / "d.csv"
    _fragile_dataset(data)
    cfg = SpecConfig(data=str(data), outcome="y", treatment="treat",
                     controls_pool=["c1", "c2"], controls_mode="powerset", preferred_sign=1)
    curve = run_multiverse(cfg)
    s = curve.summary
    # Specs that omit the confounder c1 are spuriously significant; those that
    # include it are null -> the result is NOT robust across the multiverse.
    assert s["n_specs_run"] >= 4
    assert s["share_significant_expected_sign"] < 1.0
    # The all-controls reference spec recovers the true null.
    assert curve.preferred is not None and curve.preferred.p > 0.05


def test_replication_findings_on_fragile(tmp_path):
    data = tmp_path / "d.csv"
    _fragile_dataset(data)
    cfg = SpecConfig(data=str(data), outcome="y", treatment="treat",
                     controls_pool=["c1", "c2"], controls_mode="powerset", preferred_sign=1)
    curve = run_multiverse(cfg)
    wounds = viae_wounds({"spec_curve": curve.to_dict()}, artifact="out/viae.json")
    assert any(w.blade == "mille_viae" and w.evidence_kind == "computation" for w in wounds)
    assert all(w.artifacts == ["out/viae.json"] for w in wounds)


def test_template_config(tmp_path):
    data = tmp_path / "d.csv"
    _fragile_dataset(data)
    cfg = template_config(str(data))
    assert cfg.outcome in ("y", "treat", "c1", "c2")
    assert cfg.data == str(data)


# ----------------------------------------------------- McCrary + staggered DiD
def test_mccrary_calibration():
    """A screening density test should rarely flag clean data and usually flag manipulation."""
    pytest.importorskip("scipy")
    from econoclast.viae.rdd import mccrary_density_test

    def clean(seed):
        return np.random.default_rng(seed).normal(0, 1, 6000)

    def manipulated(seed):
        rng = np.random.default_rng(seed)
        x = rng.normal(0, 1, 6000)
        m = (x > -0.3) & (x < 0) & (rng.random(6000) < 0.7)
        x[m] = np.abs(x[m])
        return x

    false_pos = sum(mccrary_density_test(clean(s), 0.0)["suspect"] for s in range(20))
    power = sum(mccrary_density_test(manipulated(s), 0.0)["suspect"] for s in range(20))
    assert false_pos <= 3   # low false-positive rate
    assert power >= 18      # high power against real manipulation


def test_callaway_santanna_recovers_dynamic_effect():
    from econoclast.viae.staggered import bacon_diagnostic, callaway_santanna

    rng = np.random.default_rng(7)
    rows = []
    for i in range(250):
        g = rng.choice([4, 7, 0], p=[0.4, 0.4, 0.2])
        ufe = rng.normal(0, 1)
        for t in range(1, 11):
            eff = 2.0 * (t - g + 1) if (g > 0 and t >= g) else 0.0
            rows.append((i, t, g, ufe + 0.1 * t + eff + rng.normal(0, 1)))
    df = pd.DataFrame(rows, columns=["id", "t", "cohort", "y"])
    cs = callaway_santanna(df, unit="id", time="t", outcome="y", cohort="cohort", bootstrap=60)
    assert cs["ran"] and abs(cs["event_study"][0]["att"] - 2.0) < 0.6  # truth at e=0 is 2
    assert cs["pretrend_violated"] is False
    bac = bacon_diagnostic(df, unit="id", time="t", outcome="y", cohort="cohort")
    assert bac["twfe_biased"] is True  # dynamic effects bias TWFE


def test_spec_config_from_dict_requires_core_fields():
    with pytest.raises(ValueError):
        SpecConfig.from_dict({"data": "x.csv", "outcome": "y"})
    cfg = SpecConfig.from_dict({"data": "x.csv", "outcome": "y", "treatment": "d",
                                "fixed_effects": ["state", ["state", "year"]]})
    assert cfg.fixed_effects == [["state"], ["state", "year"]]
