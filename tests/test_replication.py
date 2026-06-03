"""Replication / multiverse tests (skipped if statsmodels/pandas absent)."""

from __future__ import annotations

import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("statsmodels")

import numpy as np  # noqa: E402

from econoclast.replication import (  # noqa: E402
    replication_findings,
    run_multiverse,
    template_config,
)
from econoclast.replication.models import SpecConfig  # noqa: E402


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
    findings = replication_findings({"spec_curve": curve.to_dict()})
    assert any(f.attack == "multiverse" for f in findings)


def test_template_config(tmp_path):
    data = tmp_path / "d.csv"
    _fragile_dataset(data)
    cfg = template_config(str(data))
    assert cfg.outcome in ("y", "treat", "c1", "c2")
    assert cfg.data == str(data)
