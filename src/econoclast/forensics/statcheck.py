"""statcheck — recompute p-values from reported test statistics.

Reimplements the core idea of Nuijten et al. (2016): for every reported
``stat(df) = value, p = ...`` triple, recompute the p-value and compare it to
the one the authors printed. A mismatch is an *inconsistency*; a mismatch that
flips the significance verdict at .05 is a *decision (gross) inconsistency* —
the kind that changes what a reader believes.

Reference: Nuijten, Hartgerink, van Assen, Epskamp & Wicherts (2016),
"The prevalence of statistical reporting errors in psychology (1985-2013)",
Behavior Research Methods.
"""

from __future__ import annotations

from econoclast.forensics.base import (
    Flag,
    ForensicResult,
    p_from_chi2,
    p_from_f,
    p_from_r,
    p_from_t,
    p_from_z,
)

REFERENCE = "Nuijten et al. (2016), Behavior Research Methods (statcheck)"


def _compute_p(claim) -> float | None:  # noqa: ANN001
    t = claim.test_type
    v = claim.stat_value
    if v is None:
        return None
    try:
        if t == "t" and claim.df1:
            return p_from_t(v, claim.df1, tail=claim.tail)
        if t == "f" and claim.df1 and claim.df2:
            return p_from_f(v, claim.df1, claim.df2)
        if t == "r" and claim.df1:
            return p_from_r(v, claim.df1, tail=claim.tail)
        if t == "chi2" and claim.df1:
            return p_from_chi2(v, claim.df1)
        if t == "z":
            return p_from_z(v, tail=claim.tail)
    except Exception:  # noqa: BLE001
        return None
    return None


def _matches(reported: float, comparator: str, computed: float, decimals: int) -> bool:
    """statcheck-style comparison honouring the reported rounding & comparator."""
    tol = 0.5 * 10 ** (-decimals) if decimals else 0.005
    if comparator == "=":
        return abs(round(computed, decimals) - reported) <= tol or abs(computed - reported) <= tol
    if comparator == "<":
        return computed < reported + tol
    if comparator == ">":
        return computed > reported - tol
    return False


def run_statcheck(claims: list) -> ForensicResult:
    candidates = [
        c for c in claims
        if c.test_type in ("t", "f", "r", "chi2", "z")
        and c.stat_value is not None
        and c.p_value is not None
    ]
    if not candidates:
        return ForensicResult.insufficient(
            "statcheck",
            "No reported `test-statistic + p-value` pairs were found to recompute.",
            REFERENCE,
        )

    flags: list[Flag] = []
    n_inconsistent = 0
    n_decision = 0
    checked = 0
    for c in candidates:
        computed = _compute_p(c)
        if computed is None:
            continue
        checked += 1
        decimals = _decimals_of(c.p_value)
        # statcheck tries the reported tail and the other tail; consistent if either matches.
        ok = _matches(c.p_value, c.p_comparator, computed, decimals)
        if not ok and c.test_type in ("t", "r", "z"):
            other = computed / 2 if c.tail == 2 else computed * 2
            ok = _matches(c.p_value, c.p_comparator, other, decimals)
        if ok:
            continue
        reported_sig = c.p_value < 0.05 if c.p_comparator in ("=", "<") else False
        computed_sig = computed < 0.05
        decision_error = reported_sig != computed_sig
        n_inconsistent += 1
        if decision_error:
            n_decision += 1
        flags.append(
            Flag(
                detail=(
                    f"{c.test_type}={c.stat_value} (df={_fmt_df(c)}) implies p≈{computed:.4f}, "
                    f"but the paper reports p{c.p_comparator}{c.p_value}"
                    + ("  ← flips significance at .05" if decision_error else "")
                ),
                severity="high" if decision_error else "medium",
                data={
                    "section": c.section,
                    "table": c.table,
                    "reported_p": c.p_value,
                    "computed_p": round(computed, 5),
                    "decision_error": decision_error,
                    "raw": c.raw[:160],
                },
            )
        )

    if checked == 0:
        return ForensicResult.insufficient("statcheck", "Could not recompute any p-values.", REFERENCE)

    if n_inconsistent == 0:
        verdict, severity = "clean", "info"
        summary = f"All {checked} recomputable p-values are internally consistent."
    else:
        verdict = "suspicious"
        severity = "high" if n_decision else "medium"
        summary = (
            f"{n_inconsistent}/{checked} reported p-values disagree with the recomputed value"
            + (f", {n_decision} of them flipping significance at .05." if n_decision else ".")
        )

    return ForensicResult(
        name="statcheck",
        ran=True,
        verdict=verdict,
        severity=severity,
        summary=summary,
        n_inputs=checked,
        stats={"checked": checked, "inconsistent": n_inconsistent, "decision_errors": n_decision},
        flags=flags,
        reference=REFERENCE,
    )


def _decimals_of(p: float) -> int:
    s = f"{p:.10f}".rstrip("0")
    return len(s.split(".")[1]) if "." in s else 2


def _fmt_df(c) -> str:  # noqa: ANN001
    if c.df1 and c.df2:
        return f"{c.df1:g},{c.df2:g}"
    if c.df1:
        return f"{c.df1:g}"
    return "—"
