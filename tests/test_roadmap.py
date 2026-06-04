"""Tests for the roadmap modules: McCrary, staggered DiD, ensemble, references, runner."""

from __future__ import annotations

import numpy as np
import pytest

from econoclast.attacks.base import Finding
from econoclast.attacks.ensemble import vote_findings
from econoclast.ingest.models import Paper
from econoclast.ingest.references import extract_references
from econoclast.replication.runner import detect_entrypoint, run_replication_package


# ------------------------------------------------------------------- ensemble
def _f(title, sev="medium", conf=0.7, cat="specification_search"):
    return Finding(attack="x", title=title, category=cat, severity=sev, detail="", confidence=conf)


def test_ensemble_keeps_majority_drops_singletons():
    runs = [
        [_f("Sample period is cherry-picked"), _f("Only one robustness check")],
        [_f("Sample period looks cherry picked"), _f("Weak instrument concern")],
        [_f("The sample period is cherry-picked"), _f("Random unique finding")],
    ]
    kept = vote_findings(runs)
    titles = " ".join(f.title.lower() for f in kept)
    assert "sample period" in titles  # appeared in all 3 runs -> kept
    assert "random unique" not in titles  # singleton -> dropped
    assert all("ensemble_votes" in f.data for f in kept)


# ----------------------------------------------------------------- references
def test_extract_references_splits_entries():
    body = (
        "1. Smith, J. (2019). A study of widgets. Journal of Things, 4(2), 1-20.\n"
        "2. Doe, A. and Roe, B. (2021). Another paper about gadgets. Econ Review.\n"
        "3. Lee, C. (2015). Yet more evidence on sprockets. Working Paper 123.\n"
    )
    paper = Paper(title="t", text="Body text.\n\nReferences\n" + body)
    refs = extract_references(paper)
    assert len(refs) >= 3
    assert any("widgets" in r for r in refs)


# --------------------------------------------------------------------- runner
def test_runner_off_by_default():
    res = run_replication_package(".", allow_code=False)
    assert res["ran"] is False and "off" in res["reason"]


def test_runner_detects_entrypoint(tmp_path):
    (tmp_path / "master.do").write_text("display 1")
    found = detect_entrypoint(tmp_path)
    assert found is not None and found[1] == "stata"


# ----------------------------------------------------- McCrary + staggered DiD
def test_mccrary_calibration():
    """A screening density test should rarely flag clean data and usually flag manipulation."""
    pytest.importorskip("scipy")
    from econoclast.replication.rdd import mccrary_density_test

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
    pd = pytest.importorskip("pandas")
    pytest.importorskip("statsmodels")
    from econoclast.replication.staggered import bacon_diagnostic, callaway_santanna

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
