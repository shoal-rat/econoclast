"""Known-answer tests for the integrity screens (falsum, fucus, palimpsestus, code audit)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from econoclast.bibliotheca.codeaudit import audit
from econoclast.tesserae.forensics import (
    abstract_numbers,
    caliper,
    grim,
    p_curve,
    scan,
    terminal_digits,
)
from econoclast.tesserae.models import StatClaim
from econoclast.tesserae.versions import compare
from econoclast.viae import forensics as data_forensics


def test_grim_known_answers():
    assert grim(3.45, 20, 2) is True     # 69/20
    assert grim(3.47, 20, 2) is False    # no integer total over 20 gives .47
    assert grim(2.5, 2000, 1) is True    # GRIM is powerless at large N


def test_caliper_and_pcurve():
    rng = np.random.default_rng(1)
    hacked = list(rng.uniform(1.96, 2.15, 30)) + list(rng.uniform(1.77, 1.95, 4))
    c = caliper(hacked, 1.96, 0.2)
    assert c["over"] == 30 and c["p_excess"] < 0.001
    honest = p_curve(list(rng.uniform(0, 0.01, 20)) + [0.03, 0.04])
    assert honest["flat_or_left_skewed"] is False
    flat = p_curve([0.03, 0.04, 0.045, 0.049, 0.041, 0.038, 0.047, 0.033, 0.012])
    assert flat["flat_or_left_skewed"] is True


def test_paper_scan_flags_bunched_t_stats():
    claims = [StatClaim(raw="x", coef=round(2.0 + 0.01 * i, 3), se=1.0) for i in range(14)]
    claims += [StatClaim(raw="x", coef=1.85, se=1.0)]
    res = scan(claims, "")
    assert any(f["test"] == "caliper-t" for f in res["flags"])


def test_terminal_digits_detects_human_digits():
    rng = np.random.default_rng(2)
    real = [f"{v:.3f}" for v in rng.normal(10, 3, 400)]
    fake = [f"{rng.integers(1, 20)}.{rng.integers(0, 10)}{rng.choice([3, 7])}{rng.choice([3, 7])}" for _ in range(400)]
    assert terminal_digits(real)["suspect"] is False
    assert terminal_digits(fake)["suspect"] is True


def test_abstract_numbers_not_in_body():
    abstract = "Employment rose by 13 percent, and prices rose by 4.1 percent."
    body = "Table 2 shows employment rising by 13 percent (2.76 FTE). Prices are unchanged."
    res = abstract_numbers(abstract, body)
    assert [m["number"] for m in res["not_in_body"]] == ["4.1 percent"]


def test_data_forensics_duplicates_and_balance():
    rng = np.random.default_rng(3)
    n = 400
    df = pd.DataFrame({"id": range(n), "treat": rng.integers(0, 2, n),
                       **{f"x{k}": rng.normal(0, 1, n) for k in range(6)}})
    df.loc[300:339, [f"x{k}" for k in range(6)]] = df.loc[0:39, [f"x{k}" for k in range(6)]].to_numpy()
    df.loc[300:339, "treat"] = df.loc[0:39, "treat"].to_numpy()
    df["name"] = pd.array([f"store {i % 50}" for i in range(n)], dtype="string")  # text columns must not break it
    res = data_forensics.scan(df, id_cols=["id", "name"])
    assert res["duplicates"]["exact_duplicate_rows"] == 80
    assert any(f["test"] == "duplicate-rows" for f in res["flags"])
    # randomisation that is too good: treated and control are near-identical copies
    base = pd.DataFrame({f"x{k}": np.sort(rng.normal(0, 1, 200)) for k in range(8)})
    twin = pd.concat([base.assign(treat=0), base.assign(treat=1)], ignore_index=True)
    bal = data_forensics.carlisle(twin, "treat", [f"x{k}" for k in range(8)])
    assert bal["ran"] and bal["suspect"] is True
    honest = data_forensics.carlisle(df.iloc[:300], "treat", [f"x{k}" for k in range(6)])
    assert honest["suspect"] is False


def test_versions_show_switched_outcome():
    v1 = ("Our primary outcome is total employment measured in FTE. We find no significant effect on total "
          "employment (0.12 (0.40)). Wages rose by 10 percent in treated stores.")
    v2 = ("Our primary outcome is full-time employment. We find a significant increase in full-time employment "
          "(2.76 (1.36)). Wages rose by 10 percent in treated stores.")
    res = compare(v1, v2, old_label="WP 2019", new_label="AER 2021")
    assert res["rewritten"] and "full-time" in res["rewritten"][0]["after"]
    assert (0.12, 0.4) in res["estimates_only_in_old"]
    assert res["outcomes_old"] != res["outcomes_new"]


def test_code_audit_finds_quiet_filters(tmp_path):
    (tmp_path / "main.do").write_text("use data.dta\ndrop if empft > 60\nreplace wage = . if wage < 4\n"
                                      "reg demp nj, robust\n")
    (tmp_path / "clean.R").write_text("d <- filter(d, year >= 1992)\nd <- left_join(d, x)\n")
    res = audit(tmp_path)
    kinds = {(h["file"], h["kind"]) for h in res["steps"]}
    assert ("main.do", "drop") in kinds and ("main.do", "recode") in kinds
    assert ("clean.R", "drop") in kinds and ("clean.R", "merge") in kinds


def test_data_last_digits_flag_invented_measurements_only():
    rng = np.random.default_rng(5)
    real = pd.Series(np.round(rng.normal(250, 40, 600), 3))
    invented = pd.Series([float(f"{rng.integers(150, 350)}.{rng.choice([1, 5])}{rng.choice([5, 7])}{rng.choice([3, 5])}")
                          for _ in range(600)])
    prices = pd.Series(rng.choice([0.99, 1.49, 2.19, 1.05, 3.99], 600))
    assert data_forensics.last_digits(real)["suspect"] is False
    assert data_forensics.last_digits(invented)["suspect"] is True
    assert data_forensics.last_digits(prices)["ran"] is False


def test_razor_shaves_useless_machinery_and_keeps_real_mechanism(tmp_path):
    from econoclast.viae.razor import compare_models

    rng = np.random.default_rng(9)
    n = 600
    x, z, w = rng.normal(0, 1, n), rng.normal(0, 1, n), rng.normal(0, 1, n)
    y = 1.0 + 2.0 * x + rng.normal(0, 1, n)                 # truth: x only
    y2 = 1.0 + 2.0 * x + 1.5 * x * z + rng.normal(0, 1, n)  # truth: x and an interaction
    path = tmp_path / "d.csv"
    pd.DataFrame({"y": y, "y2": y2, "x": x, "z": z, "w": w}).to_csv(path, index=False)
    shave = compare_models(str(path), "y", ["x"], ["z", "w", "x:z", "x:w"])
    assert shave["verdict"] == "shave" and shave["extra_parameters"] == 4
    keep = compare_models(str(path), "y2", ["x", "z"], ["x:z"])
    assert keep["verdict"] == "keep" and keep["lr_p"] < 0.001
