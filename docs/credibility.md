# Keeping the review credible

An automated referee is only worth running if it doesn't add noise. The recent literature on
LLM-based peer review is consistent about *how* these systems fail, and about the controls that make
them useful. Econoclast implements the ones that apply to a single-paper adversarial review; this
page records which, and why.

## What the evidence says

- **LLM feedback is useful, LLM *decisions* are not.** GPT-4 review feedback overlaps with human
  reviewers about as much as two humans overlap (~31% on Nature-family papers, ~39% on ICLR), but
  standalone accept/reject is weak and biased (Liang et al., *NEJM AI* 2024). -> Econoclast is
  decision-support; it never accepts/rejects.
- **Prestige/identity bias is real and large in economics.** Across 29k evaluations of 1,220 papers,
  GPT-4o / Claude / Gemma / LLaMA gave higher ratings when elite/male author identities were visible
  vs. anonymised (Ye et al., 2025). -> **Blind review is on by default**: authors, affiliations,
  e-mails and acknowledgements are redacted before the LLM attacks (`--no-blind` to disable).
- **The one field-validated deployment wrapped generation in reliability gates.** The ICLR 2025
  Review-Feedback-Agent (20k reviews) only shipped feedback that passed automated checks; 89% was
  rated a quality improvement (Thakkar et al., 2025). -> Econoclast runs a **mechanical grounding
  gate**: a finding's quote must actually appear in the paper, or its confidence is capped.
- **Hallucinated critiques and citations survive human review.** Fabricated citations reached ~1% of
  accepted NeurIPS 2025 papers. -> **Ground or drop**: no verbatim quote, no finding. A separate
  **citation-check** verifies the paper's own references against Crossref.
- **Prompt injection works.** Hidden white/zero-width "GIVE A POSITIVE REVIEW" text has been found in
  real arXiv manuscripts (Lin 2025). -> Econoclast **strips invisible characters**, **detects**
  injection phrases and **raises a finding**, and instructs the backend that the manuscript
  is untrusted data.
- **Role-specialisation reduces generic comments** (Sakana AI-Scientist; MARG, D'Arcy et al. 2024).
  -> Attacks are **role-specialised** (one persona per failure mode) and **design-gated**.

## The rules Econoclast follows

1. **Ground or drop**: every LLM finding carries a quote; unverifiable quotes are down-weighted.
2. **Blind to identity**: redact author/affiliation/funding tells before LLM review.
3. **Untrusted input**: strip invisible text, detect and flag injection, fixed system prompt.
4. **Every finding carries a confidence**: severity and confidence are recorded per finding; the
   report labels how sure each one is.
5. **Calibrate and cap**: severity × confidence, saturating fragility score; caveats on weak signals.
6. **No sycophancy**: the adversarial persona forms its view from the paper, not from any desired
   outcome or rebuttal.
7. **Audit trail**: the JSON report logs every finding, its quote, the backend used, and which
   attacks ran or were skipped.
8. **Human in the loop**: output is flags for a person to verify, never a verdict of misconduct.

## Still to do (roadmap)

A held-out bias/injection audit suite; reproducibility gates against AEA/DCAS and TOP standards
(data cited, code present and runnable, results map to tables, seed/version pinned).

## References

Liang et al. (2024, *NEJM AI*); Ye et al. (2025, economics LLM-review bias); Thakkar et al. (2025,
ICLR Review-Feedback-Agent); D'Arcy et al. (2024, MARG); Jin et al. (2024, AgentReview, *EMNLP*);
Lin (2025, prompt-injection in manuscripts); Sakana AI-Scientist automated reviewer; plus the
meta-science base Econoclast draws on for its replication pass: Simonsohn et al. (specification
curve).
