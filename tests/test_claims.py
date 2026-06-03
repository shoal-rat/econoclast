"""Tests for statistical-claim extraction."""

from __future__ import annotations

from econoclast.ingest.claims import extract_statistics


def test_extracts_test_stat_with_p():
    claims = extract_statistics("The effect was significant, t(34) = 2.10, p = .03.")
    tstat = [c for c in claims if c.test_type == "t"]
    assert tstat and tstat[0].df1 == 34 and abs(tstat[0].stat_value - 2.10) < 1e-9
    assert tstat[0].p_value == 0.03 and tstat[0].p_comparator == "="


def test_extracts_f_with_two_df():
    claims = extract_statistics("We find F(2, 95) = 4.50, p < 0.01.")
    f = [c for c in claims if c.test_type == "f"][0]
    assert f.df1 == 2 and f.df2 == 95 and f.p_comparator == "<"


def test_extracts_coefficient_and_se_and_stars():
    claims = extract_statistics("The coefficient is 0.123*** (0.045).")
    coef = [c for c in claims if c.coef is not None][0]
    assert abs(coef.coef - 0.123) < 1e-9 and abs(coef.se - 0.045) < 1e-9 and coef.stars == 3


def test_extracts_mean_sd_and_n():
    claims = extract_statistics("Mean was M = 3.45, SD = 1.20 across N = 1,234 subjects.")
    md = [c for c in claims if c.mean is not None][0]
    assert md.mean == 3.45 and md.sd == 1.20 and md.n == 1234 and md.decimals == 2


def test_handles_negative_and_unicode_minus():
    claims = extract_statistics("placebo estimate is -0.004 (0.052) and z = 1.97.")
    assert any(c.coef is not None and c.coef < 0 for c in claims)
    assert any(c.test_type == "z" for c in claims)
