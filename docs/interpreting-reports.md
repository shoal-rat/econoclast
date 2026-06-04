# Interpreting an Econoclast report

**Read this before you quote a finding.** Econoclast is a *screening* tool. It surfaces hypotheses for
a human to verify, not verdicts of misconduct.

## The fragility score

A 0–100 number with a band:

| Band | Score | Meaning |
|---|---|---|
| Robust | < 15 | nothing material surfaced |
| Minor concerns | 15–35 | small issues; headline probably safe |
| Material concerns | 35–60 | real weaknesses; may not survive scrutiny |
| Fragile | 60–80 | central claim looks fragile to plausible alternatives |
| Severe | 80+ | treat the central claim as unsupported until addressed |

The score is the saturating sum of `severity × confidence` over all findings. It **saturates** so a
few decisive findings dominate a pile of weak ones. An **integrity override** lifts the band whenever
a high-confidence reporting-inconsistency finding shows a reported number is internally impossible or
inconsistent.

## What each signal does and does NOT mean

Every finding is a grounded LLM judgment carrying a verbatim quote, so you can check it against the
paper in seconds. If the quote doesn't support the claim, discard it.

- **reporting-inconsistency** -> a reported number looks internally impossible or mismatched (a mean
  outside its scale, a t-statistic that doesn't match its coefficient and standard error). The cause
  could be a typo, a rounding convention, or a transcription error, **not necessarily fabrication.** It
  always warrants a correction. A high-confidence one triggers the integrity override.
- **specification-search, cherry-picking, identification, robustness-coverage, HARKing, over-claiming,
  literature-contradiction** -> reasoning about the choices behind the result. This *can be wrong or
  over-confident.* Read the quote and decide for yourself.
- **methodology audit** -> for a method Econoclast does not cover, it researches the method's literature
  first, then checks the paper against what that literature expects.
- **citation-check** -> references resolved against Crossref. A low resolve rate is a flag to look
  harder at the bibliography, not proof of a problem.

## Confidence

Each finding's confidence reflects how sure the attack is that the problem is *real and material*. A
finding whose quote does not actually appear in the paper is treated as ungrounded and auto-capped at
0.35. A referee pass writes the synthesis over the surviving findings.

## Good uses

- Stress-test **your own** paper before submission.
- Referee more thoroughly: generate a structured first pass, then verify each flag.
- Teach what robustness actually requires.

## Bad uses

- Don't paste a fragility score into a public accusation. Verify findings, talk to authors, and
  remember the base rate: many flagged inconsistencies are honest errors.
