"""Falsum, in the data: fingerprints of fabricated or doctored observations.

Screens a dataset for what made-up or edited data tends to leave behind: duplicated and
near-duplicated rows, last digits that are not uniform, first digits that ignore Benford
where Benford should hold, heaping on round numbers, values that cannot exist, and
randomisation balance that is too good to be true (Carlisle's test). Each flag carries
the evidence and a caveat; the Sicarius decides what is a wound.
"""

from __future__ import annotations

import math
from collections import Counter

import numpy as np


def _numeric(s) -> bool:  # noqa: ANN001
    from pandas.api.types import is_bool_dtype, is_numeric_dtype

    return is_numeric_dtype(s) and not is_bool_dtype(s)


def _chi2_p(chi2: float, df: int) -> float:
    try:
        from scipy.stats import chi2 as c

        return float(c.sf(chi2, df))
    except ImportError:  # pragma: no cover
        return math.exp(-chi2 / 2)


def duplicates(df, id_cols: list[str] | None = None) -> dict:  # noqa: ANN001
    """Exact copies, and rows identical to another on every column but one (copy-and-tweak)."""
    cols = [c for c in df.columns if c not in (id_cols or [])]
    sub = df[cols]
    exact_mask = sub.duplicated(keep=False)
    near_mask = exact_mask & False
    if 4 <= len(cols) <= 80 and len(sub) <= 200000:
        for c in cols:
            near_mask |= sub.drop(columns=[c]).duplicated(keep=False)
        near_mask &= ~exact_mask
    return {"rows": int(len(df)), "exact_duplicate_rows": int(exact_mask.sum()),
            "near_duplicate_rows": int(near_mask.sum())}


def last_digits(series) -> dict:  # noqa: ANN001
    """Mosimann-style terminal-digit test, only where the last digit should be noise.

    Applies to measurements with 3+ significant digits and many distinct values. Prices,
    half-unit counts and other naturally heaped columns are skipped rather than flagged.
    """
    x = series.dropna()
    if len(x) < 100 or x.nunique() < 50:
        return {"n": int(len(x)), "ran": False, "reason": "too few distinct values"}
    vals = x.astype(float)
    strs = [repr(v) for v in vals.tolist()]  # the shortest form: the precision the data was recorded at
    decimals = max((len(t.split(".")[1]) if "." in t and not t.endswith(".0") else 0) for t in strs)
    if decimals <= 2 and vals.abs().max() < 100:
        return {"n": int(len(x)), "ran": False, "reason": "price-like values (two decimals): last digits heap by design"}
    if decimals >= 6:
        return {"n": int(len(x)), "ran": False, "reason": "computed values (full float precision)"}
    strs = [f"{v:.{decimals}f}" for v in vals.tolist()]  # one precision for all, so trailing zeros count
    sig = [s.replace("-", "").replace(".", "").lstrip("0") for s in strs]
    digs = [d[-1] for d in sig if len(d) >= 3]
    n = len(digs)
    if n < 100:
        return {"n": n, "ran": False, "reason": "values have fewer than 3 significant digits"}
    cnt = Counter(digs)
    if set(cnt) <= {"0", "5"} or set(cnt) <= {"0", "2", "4", "6", "8"}:
        # a measurement grid (halves, fifths): heaping by construction, not a digit preference
        return {"n": n, "ran": False, "reason": "values sit on a coarse grid"}
    exp = n / 10
    chi2 = sum((cnt.get(str(d), 0) - exp) ** 2 / exp for d in range(10))
    p = _chi2_p(chi2, 9)
    return {"n": n, "ran": True, "chi2": round(chi2, 1), "p": round(p, 8), "suspect": p < 1e-4,
            "counts": {str(d): cnt.get(str(d), 0) for d in range(10)}}


def benford(series) -> dict:  # noqa: ANN001
    x = series.dropna().astype(float)
    x = x[x > 0]
    if len(x) < 200 or (x.max() / max(x.min(), 1e-12)) < 1000:
        return {"ran": False, "reason": "needs 200+ positive values spanning 3+ orders of magnitude"}
    first = (x / 10 ** np.floor(np.log10(x))).astype(int).clip(1, 9)
    cnt = Counter(first.tolist())
    n = len(first)
    chi2 = sum((cnt.get(d, 0) - n * math.log10(1 + 1 / d)) ** 2 / (n * math.log10(1 + 1 / d)) for d in range(1, 10))
    p = _chi2_p(chi2, 8)
    return {"ran": True, "n": n, "chi2": round(chi2, 1), "p": round(p, 5), "suspect": p < 0.001}


def heaping(series) -> dict:  # noqa: ANN001
    x = series.dropna()
    if len(x) < 100 or not _numeric(x):
        return {"ran": False}
    xi = x[(x == x.round()) & (x.abs() >= 10)]
    if len(xi) < 50:
        return {"ran": False}
    share5 = float((xi % 5 == 0).mean())
    share10 = float((xi % 10 == 0).mean())
    return {"ran": True, "n": int(len(xi)), "share_multiple_of_5": round(share5, 3),
            "share_multiple_of_10": round(share10, 3), "suspect": share5 > 0.6}


_CHANGE = ("chg", "change", "diff", "delta", "pch", "gap", "growth", "dlog", "resid")


def impossible(df) -> list[dict]:  # noqa: ANN001
    out = []
    for c in df.columns:
        s = df[c]
        if not _numeric(s):
            continue
        name = str(c).lower()
        if any(k in name for k in _CHANGE) or (name.startswith("d") and len(name) > 2 and name[1:].isalpha()
                                               and any(k in name[1:] for k in ("emp", "wage", "price", "pop"))):
            continue  # changes and differences can be negative
        mn, mx = s.min(), s.max()
        if any(k in name for k in ("count", "num", "emp", "age", "price", "wage", "pop", "hours", "_n")) and mn < 0:
            out.append({"column": str(c), "issue": f"negative values (min {mn})"})
        if any(k in name for k in ("pct", "percent", "share", "rate")) and (mx > 100 or mn < 0):
            out.append({"column": str(c), "issue": f"outside [0, 100] (min {mn}, max {mx})"})
        if "age" in name and mx > 120:
            out.append({"column": str(c), "issue": f"age above 120 (max {mx})"})
    return out


def carlisle(df, treatment: str, covariates: list[str]) -> dict:  # noqa: ANN001
    """Baseline balance p-values should be uniform under randomisation; too many near 1 is suspicious."""
    from scipy import stats

    t = df[treatment]
    groups = sorted(t.dropna().unique())
    if len(groups) != 2:
        return {"ran": False, "reason": "treatment must have two groups"}
    ps = []
    for c in covariates:
        a = df.loc[t == groups[0], c].dropna()
        b = df.loc[t == groups[1], c].dropna()
        if len(a) > 5 and len(b) > 5 and a.std() > 0 and b.std() > 0:
            ps.append(float(stats.ttest_ind(a, b, equal_var=False).pvalue))
    if len(ps) < 4:
        return {"ran": False, "reason": "needs 4+ usable covariates"}
    # Stouffer on 1 - p: very high combined z means balance better than chance allows
    z = sum(stats.norm.isf(1 - p) for p in ps) / math.sqrt(len(ps))
    p_too_good = float(stats.norm.sf(z))
    return {"ran": True, "covariates": len(ps), "p_values": [round(p, 3) for p in ps],
            "p_too_balanced": round(p_too_good, 5), "suspect": p_too_good < 0.01}


def scan(df, *, treatment: str = "", covariates: list[str] | None = None,  # noqa: ANN001
         id_cols: list[str] | None = None, columns: list[str] | None = None) -> dict:
    cols = [c for c in (columns or list(df.columns)) if c in df.columns]
    flags: list[dict] = []
    dup = duplicates(df, id_cols)
    if dup["near_duplicate_rows"] > max(5, 0.02 * dup["rows"]):
        flags.append({"test": "near-duplicate-rows", "hint": "medium",
                      "issue": f"{dup['near_duplicate_rows']} rows match another row on every column but one",
                      "evidence": dup, "caveat": "Panels and coarse categorical data produce some of these."})
    if dup["exact_duplicate_rows"]:
        flags.append({"test": "duplicate-rows", "hint": "high" if dup["exact_duplicate_rows"] > 0.01 * dup["rows"] else "medium",
                      "issue": f"{dup['exact_duplicate_rows']} rows are exact copies of another row (ids aside)",
                      "evidence": dup, "caveat": "Can be legitimate (panels with no variation); check what repeats."})
    per_col = {}
    digit_cols, benford_cols, heap_cols = [], [], []
    for c in cols:
        s = df[c]
        if not _numeric(s):
            continue
        ld, bf, hp = last_digits(s), benford(s), heaping(s)
        per_col[str(c)] = {"last_digits": {k: v for k, v in ld.items() if k != "counts"},
                           "benford": bf, "heaping": hp}
        if ld.get("suspect"):
            digit_cols.append({"column": str(c), "p": ld["p"], "counts": ld["counts"]})
        if bf.get("suspect"):
            benford_cols.append({"column": str(c), "p": bf["p"]})
        if hp.get("suspect"):
            heap_cols.append({"column": str(c), "share_multiple_of_5": hp["share_multiple_of_5"]})
    if digit_cols:
        flags.append({"test": "last-digits", "hint": "medium" if len(digit_cols) >= 2 else "low",
                      "issue": f"last digits far from uniform in {len(digit_cols)} measured column(s): "
                               + ", ".join(d["column"] for d in digit_cols[:8]),
                      "evidence": digit_cols[:8], "caveat": "Rounding, units or instruments can cause this."})
    if benford_cols:
        flags.append({"test": "benford", "hint": "low",
                      "issue": "first digits deviate from Benford in " + ", ".join(b["column"] for b in benford_cols[:8]),
                      "evidence": benford_cols[:8], "caveat": "Many economic variables need not follow Benford."})
    if heap_cols:
        flags.append({"test": "heaping", "hint": "low",
                      "issue": "heaping on multiples of 5 in " + ", ".join(h["column"] for h in heap_cols[:8]),
                      "evidence": heap_cols[:8], "caveat": "Self-reported values heap naturally; check the source."})
    for imp in impossible(df[cols]):
        flags.append({"test": "impossible-values", "hint": "medium", "issue": f"{imp['column']}: {imp['issue']}",
                      "evidence": imp})
    bal = None
    if treatment and covariates:
        bal = carlisle(df, treatment, covariates)
        if bal.get("suspect"):
            flags.append({"test": "carlisle", "hint": "high",
                          "issue": f"baseline balance is better than randomisation allows (p = {bal['p_too_balanced']})",
                          "evidence": bal, "caveat": "Stratified or re-randomised designs balance by construction."})
    return {"rows": int(len(df)), "columns_checked": len(per_col), "flags": flags, "duplicates": dup,
            "balance": bal, "per_column": per_col}
