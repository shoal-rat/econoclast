# The attack catalog

Econoclast attacks fall into three kinds. **Deterministic** checks run offline on numbers harvested
from the paper and are reproducible to the digit. **LLM** checks send a grounded excerpt to a strong
model with a hostile-but-honest referee persona and parse structured, quote-backed findings.
**Replication** checks (roadmap) re-run the authors' analysis.

Each attack returns `Finding`s with a `severity` (info->critical) and a `confidence` (0–1). The
fragility score weights them by `severity × confidence`, saturating so a couple of decisive findings
dominate a pile of weak ones, with an *integrity override* for proven inconsistencies.

---

## Deterministic forensics

### statcheck — reporting consistency
**Catches:** a printed p-value that disagrees with the p recomputed from the reported test statistic
and degrees of freedom. A mismatch that flips significance at .05 is a *decision error* (high severity).
**Inputs:** `test(df) = value, p = …` for t, F, r, z, χ². PDF-only. **Confidence:** 0.95.
**Reference:** Nuijten, Hartgerink, van Assen, Epskamp & Wicherts (2016), *Behavior Research Methods*.

### GRIM — Granularity-Related Inconsistency of Means
**Catches:** a reported mean of N integer-valued observations that no integer total / N can produce.
Diagnostic when `N < 10^decimals`. **Inputs:** mean + N + decimals. PDF-only. **Confidence:** 0.9.
**Reference:** Brown & Heathers (2017), *Social Psychological and Personality Science*.

### GRIMMER — the SD extension of GRIM
**Catches:** an impossible `(mean, SD, N)` triple for integer data. Reconstructs the integer total
(GRIM), then checks whether any integer sum-of-squares inside the SD's rounding interval is
parity-consistent and non-negative. **Inputs:** mean + SD + N + decimals. PDF-only. **Confidence:** 0.9.
**Reference:** Anaya (2016); Allard (2018).

### p-curve — distribution of significant p-values
**Catches:** a flat or left-skewed curve of p < .05 (consistent with p-hacking / no evidential value)
vs the right-skew of true, well-powered effects. Runs a binomial test (share below .025) and a
Stouffer right-skew test. **Inputs:** ≥5 exact significant p-values. PDF-only. **Confidence:** 0.55.
*Caveat:* assumes independent tests of one hypothesis. **Reference:** Simonsohn, Nelson & Simmons (2014),
*JEP: General*.

### caliper / bunching — z-statistics at the threshold
**Catches:** test statistics piled up just above 1.96 / 1.645 / 2.576 — the single-paper analogue of
the economy-wide bunching documented by Brodeur et al. Narrow, interior-only windows keep the test
honest. **Inputs:** ≥12 z-statistics (from z, large-df t, coef/se, or exact p). PDF-only. **Confidence:** 0.6.
**Reference:** Gerber & Malhotra (2008); Brodeur, Lé, Sangnier & Zylberberg (2016, *AEJ:Applied*);
Brodeur, Cook & Heyes (2020, *AER*).

### TIVA + R-index — insufficient variance & inflation
**Catches:** focal z-scores that are *too consistent* to be independent draws (variance ≪ 1), and a
success rate far above the implied median power (poor expected replicability). **Inputs:** ≥5 signed
z (coef/se). PDF-only. **Confidence:** 0.5. **Reference:** Schimmack (2014, 2016).

### Benford — first-digit law
**Catches:** leading-digit distributions far from `log10(1+1/d)`. **Strongly caveated** — coefficients
need not be Benford. **Inputs:** ≥40 numbers. PDF-only. **Confidence:** 0.35. **Reference:** Nigrini (2012);
Diekmann (2007).

### terminal-digit — rounding / heaping
**Catches:** non-uniform last digits and excess 0/5 heaping (hand-transcribed or eyeballed numbers).
**Inputs:** ≥40 terminal digits. PDF-only. **Confidence:** 0.35.

---

## LLM-reasoning attacks

All are grounded (a verbatim quote is required for every finding) and return an empty list when the
paper is clean on that dimension.

| Attack | What it probes |
|---|---|
| **specification-search** | researcher degrees of freedom; whether the headline spec was picked from many |
| **cherry-picking** | selective samples, windows, subgroups, outcomes; dropped observations |
| **identification-critique** | design-gated threats: DiD parallel trends/staggered bias, RDD manipulation/bandwidth, IV exclusion/weak instruments, matching overlap, RCT attrition, structural identification |
| **robustness-coverage** | the standard checks for this design that are present vs conveniently missing |
| **HARKing** | hypotheses/mechanisms that read as post-hoc rationalisations of the significant results |
| **over-claiming** | abstract/conclusion claims the evidence does not support (causal language from correlational designs, external-validity overreach) |
| **literature-contradiction** | novelty/positioning claims and results checked against retrieved related work |

---

## Roadmap (replication-based)

McCrary / Cattaneo-Jansson-Ma RDD density tests; Goodman-Bacon / Callaway-Sant'Anna / Sun-Abraham
staggered-DiD re-estimation; first-stage F / Stock-Yogo / Hansen J for IV; SPRITE / DEBIT
reconstructions; specification-curve over the headline coefficient; PET-PEESE and Andrews-Kasy
selection models for meta-analyses.
