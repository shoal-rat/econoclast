"""The Abacus: reported numbers that cannot all be true at once.

Pure arithmetic over the statistics the extractor pulled from the paper, in the spirit
of statcheck. It flags; the Sicarius judges (an inconsistency can be a typo, a
one-sided test, or an unusual star convention).
"""

from __future__ import annotations

import math

from econoclast.tesserae.models import StatClaim

# Most lenient |t| each star count could mean across the usual conventions
# (economics: * .10, ** .05, *** .01; some fields: * .05, ** .01, *** .001).
_STAR_MIN_T = {1: 1.645, 2: 1.96, 3: 2.576}
_SLACK = 0.92  # allow for rounding of the printed coefficient and SE


def _norm_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


def _p_from_stat(c: StatClaim) -> float | None:
    v = c.stat_value
    if v is None:
        return None
    try:
        from scipy import stats
    except ImportError:  # pragma: no cover - scipy ships with the replication extra
        stats = None
    t = (c.test_type or "").lower()
    if t == "z" or (t == "t" and stats is None):
        return _norm_p(v)
    if stats is None:
        return None
    if t == "t" and c.df1:
        return float(2 * stats.t.sf(abs(v), c.df1))
    if t == "f" and c.df1 and c.df2:
        return float(stats.f.sf(v, c.df1, c.df2))
    if t == "chi2" and c.df1:
        return float(stats.chi2.sf(v, c.df1))
    if t == "r" and c.df1 and abs(v) < 1:
        tt = v * math.sqrt(c.df1 / max(1e-9, 1 - v * v))
        return float(2 * stats.t.sf(abs(tt), c.df1))
    return None


def check(claims: list[StatClaim]) -> list[dict]:
    flags: list[dict] = []
    for c in claims:
        where = c.table or c.section or c.source
        if c.se is not None and c.se < 0:
            flags.append({"where": where, "raw": c.raw, "issue": "negative standard error",
                          "hint": "high"})
        if c.p_value is not None and not (0 <= c.p_value <= 1):
            flags.append({"where": where, "raw": c.raw, "issue": f"p-value {c.p_value} outside [0, 1]",
                          "hint": "high"})
        if c.coef is not None and c.se not in (None, 0) and c.stars:
            t = abs(c.coef / c.se)
            need = _STAR_MIN_T.get(min(c.stars, 3), 1.645)
            if t < need * _SLACK:
                flags.append({
                    "where": where, "raw": c.raw,
                    "issue": (f"{'*' * c.stars} but coef/se = {c.coef}/{c.se} gives |t| = {t:.2f}, "
                              f"below the {need} that even the most lenient convention needs"),
                    "implied_p": round(_norm_p(t), 4), "hint": "medium" if t > 1.3 else "high",
                })
        if c.p_value is not None and c.stat_value is not None and c.p_comparator == "=":
            p = _p_from_stat(c)
            if p is not None and c.p_value > 0:
                crosses = (p < 0.05) != (c.p_value < 0.05)
                ratio = max(p, c.p_value) / max(1e-12, min(p, c.p_value))
                if crosses and ratio > 1.5 or ratio > 10:
                    flags.append({
                        "where": where, "raw": c.raw,
                        "issue": (f"reported p = {c.p_value} but {c.test_type}"
                                  f"{'(' + str(c.df1) + (', ' + str(c.df2) if c.df2 else '') + ')' if c.df1 else ''}"
                                  f" = {c.stat_value} implies p = {p:.4f}"),
                        "implied_p": round(p, 4), "hint": "high" if crosses else "low",
                    })
    return flags
