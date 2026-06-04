# The attack catalog

Every Econoclast attack runs on the intelligence of the native agent (Claude Code or Codex), driven
through that CLI as a subprocess. There is no offline path: the verdict comes from grounded LLM
critiques, a research-then-verify methodology audit, a citation check against Crossref, and the
specification-curve replication when the data is public.

Each attack returns `Finding`s with a `severity` (info->critical) and a `confidence` (0–1). The
fragility score weights them by `severity × confidence`, saturating so a couple of decisive findings
dominate a pile of weak ones, with an *integrity override* for high-confidence reporting
inconsistencies.

---

## LLM-reasoning attacks

All are grounded (a verbatim quote is required for every finding) and return an empty list when the
paper is clean on that dimension. Unquoted findings are discounted, and a referee pass writes the
synthesis.

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

## Methodology audit

### methodology-audit: research-then-verify
Econoclast cannot hardcode a check for every estimator. When a paper uses a method it does not cover
(synthetic control, bunching, shift-share, a structural model, double machine learning, and so on),
this attack figures out what the method is, pulls its assumptions and standard diagnostics from the
literature, and checks the paper against them instead of guessing from memory. With `--deep` it runs
several verification strategies and a judge merges the best.

---

## Network checks

### citation-check
Splits the bibliography into entries and asks Crossref's reference matcher whether each one
corresponds to a real work. A high share of unmatched references is worth checking against fabricated
or garbled citations. Books, working papers, and datasets without a DOI are reported as unresolved
rather than fabricated, so the confidence is moderate. Runs only when literature retrieval is on.

## Ensemble voting

With `--ensemble N`, every LLM attack runs N times, varying the sampling temperature across runs.
Near-duplicate findings are clustered by category and title overlap, and only those that recur in a
majority of runs survive. Singletons are dropped as likely noise. The surviving confidence is scaled
by how many runs supported the finding.

## Roadmap (replication-based)

McCrary / Cattaneo-Jansson-Ma RDD density tests; Goodman-Bacon / Callaway-Sant'Anna / Sun-Abraham
staggered-DiD re-estimation; first-stage F / Stock-Yogo / Hansen J for IV; specification-curve over
the headline coefficient; PET-PEESE and Andrews-Kasy selection models for meta-analyses.
