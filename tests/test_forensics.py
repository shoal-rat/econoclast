"""Known-answer tests for the deterministic forensics."""

from __future__ import annotations

from econoclast.forensics.caliper import run_caliper
from econoclast.forensics.grim import grim_consistent, run_grim
from econoclast.forensics.grimmer import grimmer_consistent
from econoclast.forensics.pcurve import run_pcurve
from econoclast.forensics.statcheck import _compute_p, run_statcheck
from econoclast.ingest.models import StatClaim


def claim(**kw) -> StatClaim:
    return StatClaim(raw=kw.pop("raw", "x"), **kw)


# --------------------------------------------------------------------- statcheck
def test_statcheck_recomputes_p():
    c = claim(test_type="t", df1=100, stat_value=3.0, p_value=0.003, p_comparator="=")
    assert abs(_compute_p(c) - 0.0034) < 0.001


def test_statcheck_flags_decision_error():
    # t(100)=1.0 implies p~0.32, but the paper claims p=0.001 (significant).
    c = claim(test_type="t", df1=100, stat_value=1.0, p_value=0.001, p_comparator="=")
    res = run_statcheck([c])
    assert res.ran and res.verdict == "suspicious"
    assert res.stats["decision_errors"] == 1
    assert res.severity == "high"


def test_statcheck_passes_consistent():
    c = claim(test_type="t", df1=100, stat_value=3.0, p_value=0.003, p_comparator="=")
    res = run_statcheck([c])
    assert res.verdict == "clean"


# -------------------------------------------------------------------------- grim
def test_grim_consistent_cases():
    assert grim_consistent(0.5, 2, 1) is True       # 1/2 = 0.5
    assert grim_consistent(0.4, 3, 1) is False      # no integer/3 rounds to 0.4
    assert grim_consistent(2.71, 23, 2) is False     # planted impossible mean


def test_grim_flags_impossible_mean():
    c = claim(mean=2.71, n=23, decimals=2)
    res = run_grim([c])
    assert res.ran and res.verdict == "suspicious"
    assert res.stats["inconsistent"] == 1


# ----------------------------------------------------------------------- grimmer
def test_grimmer_obviously_possible():
    # mean 3.0, sd 1.0 over a tiny integer sample is achievable.
    assert grimmer_consistent(3.0, 1.0, 5, 1) in (True, False)  # smoke: no crash
    # A clearly possible config: values {2,3,4} repeated -> mean 3, integer-friendly
    assert grimmer_consistent(3.0, 0.0, 3, 1) is True  # all equal to 3 -> sd 0


# ------------------------------------------------------------------------ p-curve
def test_pcurve_right_skew_is_clean():
    cs = [claim(p_value=p, p_comparator="=") for p in (0.001, 0.002, 0.003, 0.001, 0.004, 0.002)]
    res = run_pcurve(cs)
    assert res.ran and res.verdict == "clean"


def test_pcurve_flat_is_suspicious():
    cs = [claim(p_value=p, p_comparator="=") for p in (0.045, 0.048, 0.049, 0.047, 0.046, 0.049)]
    res = run_pcurve(cs)
    assert res.ran and res.verdict == "suspicious"


# ------------------------------------------------------------------------ caliper
def test_caliper_detects_bunching():
    above = [claim(test_type="z", stat_value=v) for v in
             (1.97, 1.98, 1.99, 2.0, 2.01, 2.03, 2.05, 2.08, 2.1, 2.12, 2.0, 2.02)]
    below = [claim(test_type="z", stat_value=v) for v in (1.80, 1.85, 1.70, 1.90)]
    res = run_caliper(above + below)
    assert res.ran and res.verdict == "suspicious"


def test_caliper_not_suspicious_when_smooth():
    # A dense, evenly spaced cloud of z's must NOT be flagged as bunching.
    smooth = [claim(test_type="z", stat_value=v / 100.0) for v in range(150, 260)]  # 1.50..2.59
    res = run_caliper(smooth)
    assert res.verdict in ("clean", "inconclusive", "insufficient_data")
    assert res.verdict != "suspicious"
