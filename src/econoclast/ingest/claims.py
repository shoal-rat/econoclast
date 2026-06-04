"""Extract reported statistics from paper text and tables.

With nothing but the PDF/LaTeX this recovers the numbers the critique reasons
over: test statistics and p-values, means and N, coefficients and standard
errors, and reported sample sizes.

The regexes are intentionally conservative: a false negative (a missed stat) is
cheaper than a false positive (a fabricated stat).
"""

from __future__ import annotations

import re

from econoclast.ingest.models import StatClaim

# --------------------------------------------------------------------------- #
# Primitive patterns
# --------------------------------------------------------------------------- #
_NUM = r"-?−?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

# p-values:  p < .05 ,  p = 0.032 ,  p-value of 0.04 ,  P ≤ 0.001
P_RE = re.compile(
    r"\bp(?:[\s-]?value)?\s*([=<>≤≥])\s*(" + _NUM + r"|\.\d+)",
    re.IGNORECASE,
)

# Test statistics with degrees of freedom:  t(34) = 2.10 ,  F(2, 95) = 4.50 ,
# r(48) = .31 ,  chi2(1) = 3.84 ,  z = 1.97
TESTDF_RE = re.compile(
    r"\b(t|F|r|z|χ2|χ²|chi2|chi-?square|chisq)\s*"
    r"(?:\(\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\))?\s*"
    r"([=<>])\s*(" + _NUM + r"|\.\d+)",
    re.IGNORECASE,
)

# Regression cell:  0.123*** (0.045)  — coefficient, stars, SE in parentheses.
COEF_SE_RE = re.compile(
    r"(?<![\w.])(-?−?\d+\.\d+)\s*(\*{1,3}|†|‡)?\s*\(\s*(\d+\.\d+)\s*\)"
)

# Mean / SD:  M = 3.45, SD = 1.20
MEAN_SD_RE = re.compile(
    r"\bM(?:ean)?\s*=\s*(-?\d+\.\d+)\s*[,;]?\s*(?:SD|s\.?d\.?)\s*=\s*(\d+\.\d+)",
    re.IGNORECASE,
)

# Sample size:  N = 1,234 ,  n = 58 ,  1,234 observations
N_RE = re.compile(r"\b[nN]\s*=\s*([\d,]{1,9})(?!\.)\b")
OBS_RE = re.compile(r"\b([\d,]{2,12})\s+(?:observations|obs\.?)\b", re.IGNORECASE)


def _to_float(s: str) -> float | None:
    if s is None:
        return None
    s = s.replace("−", "-").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(s: str) -> int | None:
    f = _to_float(s)
    return int(f) if f is not None else None


def _decimals(num_str: str) -> int:
    num_str = num_str.replace("−", "-").strip()
    if "." in num_str and "e" not in num_str.lower():
        return len(num_str.split(".")[1])
    return 0


def _norm_comparator(c: str) -> str:
    return {"≤": "<", "≥": ">"}.get(c, c)


def _norm_test_type(t: str) -> str:
    t = t.lower()
    if t.startswith("chi") or "χ" in t:
        return "chi2"
    return t


def extract_statistics(
    text: str,
    *,
    section: str = "",
    source: str = "text",
    page: int | None = None,
    table: str | None = None,
) -> list[StatClaim]:
    """Extract every recognisable statistic from a chunk of text."""
    claims: list[StatClaim] = []
    consumed: list[tuple[int, int]] = []  # spans already turned into a claim

    def _ctx(start: int, end: int) -> StatClaim:
        lo = max(0, start - 60)
        hi = min(len(text), end + 60)
        return StatClaim(
            raw=text[lo:hi].replace("\n", " ").strip(),
            section=section,
            source=source,
            page=page,
            table=table,
            char_offset=start,
        )

    # --- test statistics (optionally paired with a nearby p-value) -----------
    p_matches = list(P_RE.finditer(text))
    for tm in TESTDF_RE.finditer(text):
        ttype = _norm_test_type(tm.group(1))
        df1 = _to_float(tm.group(2))
        df2 = _to_float(tm.group(3))
        value = _to_float(tm.group(5))
        if value is None:
            continue
        claim = _ctx(tm.start(), tm.end())
        claim.test_type = ttype
        claim.df1 = df1
        claim.df2 = df2
        claim.stat_value = value
        # Look for the closest p-value within 80 chars to the right.
        near = _nearest_p(p_matches, tm.end(), window=80)
        if near is not None:
            claim.p_value = _to_float(near.group(2))
            claim.p_comparator = _norm_comparator(near.group(1))
            consumed.append((near.start(), near.end()))
        claims.append(claim)

    # --- standalone p-values -------------------------------------------------
    for pm in p_matches:
        if any(s <= pm.start() < e for s, e in consumed):
            continue
        claim = _ctx(pm.start(), pm.end())
        claim.p_value = _to_float(pm.group(2))
        claim.p_comparator = _norm_comparator(pm.group(1))
        claims.append(claim)

    # --- coefficient / standard-error cells ----------------------------------
    for cm in COEF_SE_RE.finditer(text):
        coef = _to_float(cm.group(1))
        se = _to_float(cm.group(3))
        if coef is None or se is None:
            continue
        claim = _ctx(cm.start(), cm.end())
        claim.coef = coef
        claim.se = se
        claim.stars = len(cm.group(2)) if cm.group(2) and cm.group(2)[0] in "*" else 0
        claims.append(claim)

    # --- means + SDs ---------------------------------------------------------
    for mm in MEAN_SD_RE.finditer(text):
        claim = _ctx(mm.start(), mm.end())
        claim.mean = _to_float(mm.group(1))
        claim.sd = _to_float(mm.group(2))
        claim.decimals = _decimals(mm.group(1))
        claims.append(claim)

    # --- sample sizes (attach to nearest preceding claim if any) -------------
    n_value = _first_sample_size(text)
    if n_value is not None:
        for c in claims:
            if c.n is None:
                c.n = n_value

    return claims


def _nearest_p(p_matches, after: int, window: int):
    best = None
    best_d = window + 1
    for pm in p_matches:
        if pm.start() >= after:
            d = pm.start() - after
            if d < best_d:
                best_d, best = d, pm
    return best if best_d <= window else None


def _first_sample_size(text: str) -> int | None:
    m = N_RE.search(text)
    if m:
        return _to_int(m.group(1))
    m = OBS_RE.search(text)
    if m:
        return _to_int(m.group(1))
    return None


def extract_claims_from_paper(paper) -> list[StatClaim]:  # noqa: ANN001 (Paper, avoid cycle)
    """Run extraction across a Paper's sections and tables."""
    claims: list[StatClaim] = []
    if paper.sections:
        for sec in paper.sections:
            claims.extend(extract_statistics(sec.text, section=sec.name, source="text"))
    else:
        claims.extend(extract_statistics(paper.text, source="text"))
    for tbl in paper.tables:
        claims.extend(extract_statistics(tbl.raw, table=tbl.label, source="table"))
    return _dedupe(claims)


def _dedupe(claims: list[StatClaim]) -> list[StatClaim]:
    seen: set[tuple] = set()
    out: list[StatClaim] = []
    for c in claims:
        key = (
            round(c.p_value, 6) if c.p_value is not None else None,
            c.test_type,
            c.stat_value,
            c.coef,
            c.se,
            c.mean,
            c.section,
            c.char_offset,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
