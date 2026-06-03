"""Manuscript hygiene: defend against prompt injection and prestige bias.

Grounded in the recent literature on LLM peer review:

- **Prompt injection** is a live attack: hidden white/zero-width "GIVE A POSITIVE
  REVIEW" instructions have been found in real arXiv manuscripts (Lin 2025).
  We strip invisible characters and detect embedded meta-instructions so the
  manuscript is treated as *untrusted data*, never as instructions.
- **Prestige / identity bias**: a 1,220-paper economics study (Ye et al. 2025)
  found LLMs assign higher ratings when elite/male author identities are visible.
  We blind author, affiliation, e-mail and acknowledgement tells before the LLM
  attacks so the review is identity-blind.
"""

from __future__ import annotations

import re

# Zero-width and other invisible/control characters used to hide injected text.
_INVISIBLE = re.compile(
    "[​‌‍⁠﻿­᠎‎‏‪-‮⁦-⁩]"
)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Sentences that leak identity (acknowledgements, funding, corresponding author).
_ACK = re.compile(
    r"(?:^|\n)[^\n]*\b(?:we (?:thank|are grateful|gratefully acknowledge|wish to thank)|"
    r"acknowledge\w*|grant(?:\s|No|#)|funded by|funding from|corresponding author|"
    r"\bemail\b|\be-mail\b)\b[^\n]*",
    re.IGNORECASE,
)

# Common prompt-injection patterns aimed at a reviewer/LLM.
_INJECTION = re.compile(
    r"(ignore (?:all |the )?(?:previous|above|prior) (?:instructions|prompts)|"
    r"give (?:a |this )?(?:positive|favou?rable|strong accept|good) review|"
    r"recommend(?:ing)? (?:acceptance|to accept)|as an? (?:ai|language model|reviewer)[, ]|"
    r"do not (?:mention|report|flag)|you must (?:accept|approve)|"
    r"disregard (?:your|the) (?:instructions|guidelines))",
    re.IGNORECASE,
)


def strip_invisibles(text: str) -> str:
    """Remove zero-width / bidi / soft-hyphen characters used to hide content."""
    return _INVISIBLE.sub("", text)


def detect_injection(text: str) -> list[str]:
    """Return any embedded meta-instructions that look like prompt injection."""
    hits = []
    for m in _INJECTION.finditer(text):
        ctx = text[max(0, m.start() - 30): m.end() + 30].replace("\n", " ").strip()
        hits.append(ctx[:160])
    # Dedupe while preserving order.
    seen: set[str] = set()
    out = []
    for h in hits:
        if h.lower() not in seen:
            seen.add(h.lower())
            out.append(h)
    return out[:10]


def blind_identities(text: str) -> str:
    """Redact e-mails and acknowledgement/funding lines for identity-blind review."""
    text = _EMAIL.sub("[EMAIL]", text)
    text = _ACK.sub(" [identifying line redacted for blind review] ", text)
    return text


_NORM = re.compile(r"[^a-z0-9 ]+")


def normalize_for_match(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — for quote matching."""
    return re.sub(r"\s+", " ", _NORM.sub(" ", text.lower())).strip()


def quote_supported(paper_norm: str, quote: str) -> bool:
    """Mechanical grounding gate: does ``quote`` actually appear in the paper?

    The LLM contract demands a verbatim quote; this verifies it so hallucinated
    or paraphrased "evidence" can be down-weighted. Short quotes (<12 norm chars)
    are not penalised — too little to verify either way.
    """
    q = normalize_for_match(quote)
    if len(q) < 12:
        return True
    if q in paper_norm:
        return True
    # Allow minor paraphrase: any 40-char window of the quote present verbatim.
    for i in range(0, max(1, len(q) - 40), 20):
        if q[i:i + 40] in paper_norm:
            return True
    return False
