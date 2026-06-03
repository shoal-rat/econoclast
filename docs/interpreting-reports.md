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
a deterministic test proves a number impossible or a p-value flips significance.

## What each signal does and does NOT mean

- **statcheck / GRIM / GRIMMER inconsistency** -> a number is internally impossible or mismatched. This
  is high-confidence *as arithmetic*, but the cause could be a typo, a rounding convention, or a
  transcription error — **not necessarily fabrication.** It always warrants a correction.
- **p-curve flat, caliper bunching, TIVA low variance** -> distributional signals of selective
  reporting. They are **weak on small samples** and assume conditions (independent tests of one
  hypothesis, local density smoothness) a single paper may violate. Capped at modest confidence and
  printed with caveats. Treat as "look harder here," not proof.
- **Benford / terminal-digit** -> exploratory only. Regression coefficients need not be Benford.
- **LLM findings** (specification search, cherry-picking, identification, …) -> reasoning that *can be
  wrong or over-confident.* Every one carries a verbatim quote so you can check it against the paper
  in seconds. If the quote doesn't support the claim, discard it.

## Confidence

Each finding's confidence reflects how sure the attack is that the problem is *real and material*.
Deterministic impossibilities are ~0.9–0.95; statistical signals ~0.5–0.6; exploratory ~0.35;
ungrounded LLM claims are auto-capped at 0.35.

## Good uses

- Stress-test **your own** paper before submission.
- Referee more thoroughly — generate a structured first pass, then verify each flag.
- Teach what robustness actually requires.

## Bad uses

- Don't paste a fragility score into a public accusation. Verify findings, talk to authors, and
  remember the base rate: many flagged inconsistencies are honest errors.
