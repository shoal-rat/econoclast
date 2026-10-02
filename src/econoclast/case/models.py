"""The records a hunt leaves behind: wounds, parries and the verdict."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any

from econoclast.world import BLADE_KEYS, SEVERITIES, SEVERITY_WEIGHT

EVIDENCE_KINDS = ("text", "computation")


@dataclass
class Wound:
    """One grounded finding: a blade that landed.

    ``text`` wounds rest on a verbatim quote from the paper, which the arsenal checks
    mechanically. ``computation`` wounds rest on something the Sicarius ran (a
    re-estimate, a spec curve, a diagnostic) and must point at the artifact it produced.
    """

    blade: str
    title: str
    severity: str
    detail: str
    confidence: float = 0.6
    quote: str = ""
    location: str = ""
    remedy: str = ""
    evidence_kind: str = "text"
    artifacts: list[str] = field(default_factory=list)
    verified: bool | None = None  # quote found in the paper (None = nothing to check)
    data: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        self.blade = self.blade if self.blade in BLADE_KEYS else "scutum"
        self.severity = self.severity if self.severity in SEVERITIES else "medium"
        self.evidence_kind = self.evidence_kind if self.evidence_kind in EVIDENCE_KINDS else "text"
        try:
            self.confidence = max(0.0, min(1.0, float(self.confidence)))
        except (TypeError, ValueError):
            self.confidence = 0.6
        if not self.id:
            h = hashlib.sha1(f"{self.blade}:{self.title}".encode()).hexdigest()[:8]
            self.id = f"{self.blade}-{h}"

    @property
    def effective_confidence(self) -> float:
        """Confidence after the grounding gate.

        A text wound without a quote, or with a quote that is not in the paper, cannot
        count for much: that is the rule that keeps the Sicarius from inventing blood.
        """
        c = self.confidence
        if self.evidence_kind == "text":
            if not self.quote.strip():
                c = min(c, 0.4)
            elif self.verified is False:
                c = min(c, 0.3)
        elif not self.artifacts:
            c = min(c, 0.5)
        return c

    @property
    def weight(self) -> float:
        return SEVERITY_WEIGHT.get(self.severity, 0.0) * self.effective_confidence

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["effective_confidence"] = round(self.effective_confidence, 2)
        d["weight"] = round(self.weight, 2)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Wound:
        keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in keys})


@dataclass
class Parry:
    """A blade that was tried and turned aside: the paper defends itself on this front."""

    blade: str
    note: str
    quote: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
