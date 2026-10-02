"""Falsum, on paper: fingerprints of fabrication and p-hacking in the reported numbers.

Each test is a screen, not a verdict. A failed GRIM test is often a typo or a non-integer
item; bunching just past p = .05 is evidence about a literature as much as about one
paper. The Sicarius reads these flags in context and decides what deserves a wound.

References: Brown & Heathers (2017) GRIM; Gerber & Malhotra (2008) caliper test;
Simonsohn, Nelson & Simmons (2014) p-curve; Brodeur et al. (2016, 2020) bunching in
economics; Mosimann et al. (1995) terminal digits.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from econoclast.tesserae.models import StatClaim


def _norm_p_two(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def _binom_upper(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    if n == 0:
        return 1.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def grim(mean: float, n: int, decimals: int, items: int = 1) -> bool:
    """True when a mean of integer data (n respondents x items) can produce the reported value."""
    if n <= 0 or decimals is None:
        return True
    total = n * items
    if total >= 10 ** decimals:  # GRIM has no power once n*items exceeds the precision
        return True
    tol = 0.5 * 10 ** (-decimals) + 1e-9
    k = round(mean * total)
    return any(abs(c / total - mean) <= tol for c in (k - 1, k, k + 1))


def caliper(values: list[float], threshold: float, width: float) -> dict:
    """Counts just over vs just under a threshold, with the one-sided binomial p-value."""
    over = sum(1 for v in values if threshold <= v < threshold + width)
    under = sum(1 for v in values if threshold - width <= v < threshold)
    n = over + under
    return {"over": over, "under": under, "n": n, "p_excess": round(_binom_upper(over, n), 4) if n else None}


def p_curve(ps: list[float]) -> dict:
    """Among significant p-values, the share below .025 (true effects make the curve right-skewed)."""
    sig = [p for p in ps if 0 < p < 0.05]
    low = sum(1 for p in sig if p < 0.025)
    n = len(sig)
    return {"n_significant": n, "share_below_025": round(low / n, 3) if n else None,
            "flat_or_left_skewed": bool(n >= 8 and low / n <= 0.5),
            "p_right_skew": round(_binom_upper(low, n), 4) if n else None}


def terminal_digits(numbers: list[str]) -> dict:
    """Chi-square test of uniform last digits for numbers printed with >= 2 decimals."""
    digits = [s[-1] for s in numbers if re.fullmatch(r"-?\d+\.\d{2,}", s)]
    n = len(digits)
    if n < 50:
        return {"n": n, "ran": False}
    counts = Counter(digits)
    exp = n / 10
    chi2 = sum((counts.get(str(d), 0) - exp) ** 2 / exp for d in range(10))
    try:
        from scipy.stats import chi2 as chi2d

        p = float(chi2d.sf(chi2, 9))
    except ImportError:  # pragma: no cover
        p = math.exp(-chi2 / 2)
    return {"n": n, "ran": True, "chi2": round(chi2, 2), "p": round(p, 4),
            "counts": {str(d): counts.get(str(d), 0) for d in range(10)}, "suspect": p < 0.01}


def scan(claims: list[StatClaim], text: str) -> dict:
    """Run every paper-level screen and return flags with the evidence behind each."""
    flags: list[dict] = []

    # GRIM on reported means with N (the Sicarius must confirm the item is integer-valued)
    grim_fail = []
    for c in claims:
        if c.mean is not None and c.n and c.decimals and not grim(c.mean, c.n, c.decimals):
            grim_fail.append({"where": c.table or c.section, "raw": c.raw, "mean": c.mean, "n": c.n})
    if grim_fail:
        flags.append({"test": "GRIM", "hint": "medium",
                      "issue": f"{len(grim_fail)} reported mean(s) cannot come from integer data of that N",
                      "evidence": grim_fail[:12],
                      "caveat": "Only meaningful if the variable is integer-valued (counts, Likert items)."})

    # p-values: reported, and implied by coef/se
    ps = [c.p_value for c in claims if c.p_value is not None and c.p_comparator == "=" and 0 < c.p_value < 1]
    ts = [abs(c.coef / c.se) for c in claims if c.coef is not None and c.se and c.se > 0]
    ps_all = ps + [_norm_p_two(t) for t in ts]
    # for p-values the suspicious side is just *under* .05: count [.04,.05) against [.05,.06)
    just_sig = sum(1 for p in ps_all if 0.04 <= p < 0.05)
    just_not = sum(1 for p in ps_all if 0.05 <= p < 0.06)
    n_p = just_sig + just_not
    cal_t = caliper(ts, 1.96, 0.20)
    if cal_t["n"] >= 8 and cal_t["p_excess"] is not None and cal_t["p_excess"] < 0.05:
        flags.append({"test": "caliper-t", "hint": "medium",
                      "issue": (f"{cal_t['over']} t-statistics in [1.96, 2.16) against {cal_t['under']} in "
                                f"[1.76, 1.96): bunching just past significance (p = {cal_t['p_excess']})"),
                      "evidence": cal_t,
                      "caveat": "Bunching is a property of a body of results; a single paper has few tests."})
    if n_p >= 8 and _binom_upper(just_sig, n_p) < 0.05:
        flags.append({"test": "caliper-p", "hint": "medium",
                      "issue": f"{just_sig} p-values in [.04,.05) against {just_not} in [.05,.06)",
                      "evidence": {"just_significant": just_sig, "just_not": just_not}})
    pc = p_curve(ps_all)
    if pc["flat_or_left_skewed"]:
        flags.append({"test": "p-curve", "hint": "low",
                      "issue": (f"significant p-values are not right-skewed ({pc['share_below_025']:.0%} below "
                                f".025 of {pc['n_significant']}), the shape p-hacking leaves"),
                      "evidence": pc})

    # the same coefficient and standard error printed in different places
    pairs = Counter((c.coef, c.se) for c in claims if c.coef is not None and c.se is not None and c.coef != 0)
    dup = [{"coef": k[0], "se": k[1], "times": v} for k, v in pairs.items() if v >= 3]
    if dup:
        flags.append({"test": "repeated-estimates", "hint": "low",
                      "issue": f"{len(dup)} coefficient/SE pair(s) appear three or more times",
                      "evidence": dup[:10],
                      "caveat": "Often legitimate (a baseline repeated across tables); check the columns differ."})

    # terminal digits of printed decimals
    nums = re.findall(r"(?<![\w.])-?\d+\.\d{2,}(?![\d])", text)
    td = terminal_digits(nums)
    if td.get("suspect"):
        flags.append({"test": "terminal-digits", "hint": "low",
                      "issue": f"last digits of {td['n']} printed numbers are far from uniform (p = {td['p']})",
                      "evidence": td["counts"],
                      "caveat": "Weak on its own: rounding conventions and repeated numbers distort it."})

    return {"n_claims": len(claims), "n_p_values": len(ps_all), "flags": flags,
            "summary": {"caliper_t": cal_t, "caliper_p": {"just_significant": just_sig, "just_not": just_not},
                        "p_curve": pc, "terminal_digits": {k: v for k, v in td.items() if k != "counts"}}}


# ---------------------------------------------------------------- fucus
_NUM = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(%|percent|per cent|percentage points?|pp\b)?", re.I)


def abstract_numbers(abstract: str, body: str) -> dict:
    """Numbers the abstract advertises that appear nowhere in the rest of the paper."""
    def norm(x: str) -> set[str]:
        out = {x}
        try:
            v = float(x)
            out |= {f"{v:g}", f"{v:.1f}", f"{v:.2f}", f"{v:.3f}", f"{v / 100:.3f}", f"{v / 100:.2f}"}
        except ValueError:
            pass
        return out

    body_nums = set(re.findall(r"-?\d+(?:\.\d+)?", body))
    found, missing = [], []
    for m in _NUM.finditer(abstract):
        x = m.group(1)
        if re.fullmatch(r"(19|20)\d{2}", x) or (x.isdigit() and int(x) < 10):
            continue  # years and small counts
        ctx = abstract[max(0, m.start() - 70): m.end() + 40].replace("\n", " ")
        unit = f" {m.group(2)}" if m.group(2) else ""
        (found if norm(x) & body_nums else missing).append({"number": x + unit, "context": ctx})
    return {"checked": len(found) + len(missing), "not_in_body": missing, "in_body": len(found)}
