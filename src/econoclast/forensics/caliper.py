"""Caliper / z-statistic bunching test.

If results were selected (or specifications searched) to clear a significance
threshold, test statistics pile up *just above* the critical value. The caliper
test counts |z| in a narrow window below vs above a threshold (1.96, 1.645,
2.576) and tests for excess above. This is the single-paper analogue of the
test-statistic bunching documented across economics by Brodeur et al.

References:
- Gerber & Malhotra (2008), "Publication Bias in Empirical Sociological
  Research" / "Do Statistical Reporting Standards Affect What Is Published?"
- Brodeur, Lé, Sangnier & Zylberberg (2016), "Star Wars: The Empirics Strike
  Back", AEJ: Applied; Brodeur, Cook & Heyes (2020), "Methods Matter", AER.
"""

from __future__ import annotations

from scipy import stats

from econoclast.forensics.base import Flag, ForensicResult, z_abs_from_claim

REFERENCE = "Gerber & Malhotra (2008); Brodeur et al. (2016, 2020)"

# Narrow windows keep the local-flatness assumption defensible. The z-density is
# itself decreasing in this range, so a 50/50 null over a *wide* window would
# over-flag; we also require the window to be interior to the data (observations
# on both sides) so a sample boundary can't masquerade as bunching.
THRESHOLDS = (1.96, 1.645, 2.576)
WINDOWS = (0.05, 0.10, 0.15)


def _collect_z(claims: list) -> list[float]:
    zs = []
    for c in claims:
        z = z_abs_from_claim(c)
        if z is not None and 0 < z < 12:
            zs.append(z)
    return zs


def run_caliper(claims: list) -> ForensicResult:
    zs = _collect_z(claims)
    if len(zs) < 12:
        return ForensicResult.insufficient(
            "caliper",
            f"Only {len(zs)} usable z-statistics found; need ≥12 to test for bunching.",
            REFERENCE,
        )

    flags: list[Flag] = []
    tested = []
    worst_severity = "info"
    suspicious = False

    for zc in THRESHOLDS:
        for h in WINDOWS:
            below = sum(1 for z in zs if zc - h <= z < zc)
            above = sum(1 for z in zs if zc <= z < zc + h)
            total = below + above
            if total < 8:
                continue
            # Require the window to be interior to the data on both sides, so a
            # hard sample boundary inside the window can't look like bunching.
            if not (any(z < zc - h for z in zs) and any(z >= zc + h for z in zs)):
                continue
            test = stats.binomtest(above, total, 0.5, alternative="greater")
            ratio = above / max(below, 1)
            entry = {
                "threshold": zc,
                "window": h,
                "below": below,
                "above": above,
                "p": round(test.pvalue, 4),
                "above_below_ratio": round(ratio, 2),
            }
            tested.append(entry)
            if test.pvalue < 0.05 and above > below:
                suspicious = True
                sev = "high" if (test.pvalue < 0.01 and ratio >= 2) else "medium"
                worst_severity = sev if sev == "high" else worst_severity or sev
                flags.append(
                    Flag(
                        detail=(
                            f"Excess of |z| just above {zc}: {above} above vs {below} below "
                            f"within ±{h} (binomial p={test.pvalue:.3f})."
                        ),
                        severity=sev,
                        data=entry,
                    )
                )

    if not tested:
        return ForensicResult.insufficient(
            "caliper", "Too few z-statistics fell near the tested thresholds.", REFERENCE
        )

    if suspicious:
        verdict = "suspicious"
        severity = "high" if any(f.severity == "high" for f in flags) else "medium"
        summary = "Test statistics bunch just above conventional significance thresholds — a signature of selective reporting or specification search."
    else:
        verdict, severity = "clean", "info"
        summary = "No significant bunching of z-statistics just above 1.96/1.645/2.576."

    return ForensicResult(
        name="caliper",
        ran=True,
        verdict=verdict,
        severity=severity,
        summary=summary,
        n_inputs=len(zs),
        stats={"n_z": len(zs), "windows": tested},
        flags=flags,
        reference=REFERENCE,
    )
