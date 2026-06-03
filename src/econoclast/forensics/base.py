"""Shared types and statistical helpers for the deterministic forensics.

Every forensic module returns a :class:`ForensicResult`. These run with no API
keys and no network — pure NumPy/SciPy on numbers lifted out of the paper.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from scipy import stats

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


@dataclass
class Flag:
    """A single suspicious item surfaced by a forensic test."""

    detail: str
    severity: str = "medium"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ForensicResult:
    name: str
    ran: bool
    verdict: str  # "clean" | "suspicious" | "inconclusive" | "insufficient_data"
    summary: str
    severity: str = "info"
    n_inputs: int = 0
    stats: dict[str, Any] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)
    reference: str = ""

    @classmethod
    def insufficient(cls, name: str, why: str, reference: str = "") -> ForensicResult:
        return cls(
            name=name,
            ran=False,
            verdict="insufficient_data",
            summary=why,
            severity="info",
            reference=reference,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ran": self.ran,
            "verdict": self.verdict,
            "severity": self.severity,
            "summary": self.summary,
            "n_inputs": self.n_inputs,
            "stats": self.stats,
            "reference": self.reference,
            "flags": [{"detail": f.detail, "severity": f.severity, **({"data": f.data} if f.data else {})}
                      for f in self.flags],
        }


# --------------------------------------------------------------------------- #
# Conversions between test statistics and p-values.
# --------------------------------------------------------------------------- #
def p_from_t(t: float, df: float, tail: int = 2) -> float:
    p = float(stats.t.sf(abs(t), df))
    return p * 2 if tail == 2 else p


def p_from_z(z: float, tail: int = 2) -> float:
    p = float(stats.norm.sf(abs(z)))
    return p * 2 if tail == 2 else p


def p_from_f(f: float, df1: float, df2: float) -> float:
    return float(stats.f.sf(f, df1, df2))


def p_from_chi2(x: float, df: float) -> float:
    return float(stats.chi2.sf(x, df))


def p_from_r(r: float, df: float, tail: int = 2) -> float:
    if abs(r) >= 1:
        return 0.0
    t = r * math.sqrt(df / (1 - r * r))
    return p_from_t(t, df, tail=tail)


def z_from_p(p: float, tail: int = 2) -> float:
    """Two-sided p -> |z|."""
    p = min(max(p, 1e-12), 1 - 1e-12)
    if tail == 2:
        return float(stats.norm.isf(p / 2))
    return float(stats.norm.isf(p))


def z_abs_from_claim(claim) -> float | None:  # noqa: ANN001
    """Best-effort |z| for bunching / p-curve from any claim shape."""
    if claim.test_type == "z" and claim.stat_value is not None:
        return abs(claim.stat_value)
    if claim.test_type == "t" and claim.stat_value is not None and (claim.df1 or 0) >= 30:
        return abs(claim.stat_value)
    if claim.implied_t is not None and (claim.n or 0) >= 30:
        return abs(claim.implied_t)
    if claim.p_value is not None and claim.p_comparator == "=":
        return z_from_p(claim.p_value, tail=claim.tail)
    return None


def max_severity(severities: list[str]) -> str:
    if not severities:
        return "info"
    return max(severities, key=lambda s: SEVERITY_ORDER.get(s, 0))
