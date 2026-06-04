"""Attack primitives: the `Finding`, the run context, and the `Attack` ABC.

Every attack — deterministic-statistical, LLM-reasoning, or replication-based —
produces a list of :class:`Finding`. The report builder and the fragility score
consume that single type, so adding an attack never touches downstream code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid import cycles at runtime
    from econoclast.config import Settings
    from econoclast.ingest.models import Paper
    from econoclast.literature import LiteratureSearcher, LitRef
    from econoclast.llm.backend import Backend

SEVERITY_WEIGHT = {"info": 0.0, "low": 1.0, "medium": 2.5, "high": 5.0, "critical": 8.0}

# The QRP taxonomy a finding can belong to.
CATEGORIES = (
    "reporting_inconsistency",
    "p_hacking",
    "cherry_picking",
    "specification_search",
    "identification",
    "robustness",
    "harking",
    "publication_bias",
    "data_integrity",
    "overclaiming",
    "literature",
)


@dataclass
class Finding:
    attack: str
    title: str
    category: str
    severity: str  # info | low | medium | high | critical
    detail: str
    confidence: float = 0.6  # 0..1 — how sure the attack is
    evidence: list[str] = field(default_factory=list)
    recommendation: str = ""
    locations: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            h = hashlib.sha1(f"{self.attack}:{self.title}".encode()).hexdigest()[:8]
            self.id = f"{self.attack}-{h}"
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    @property
    def weight(self) -> float:
        """Contribution to the fragility score: severity x confidence."""
        return SEVERITY_WEIGHT.get(self.severity, 0.0) * self.confidence

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "attack": self.attack,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "confidence": round(self.confidence, 2),
            "detail": self.detail,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "locations": self.locations,
            "weight": round(self.weight, 2),
            **({"data": self.data} if self.data else {}),
        }


@dataclass
class AttackContext:
    paper: Paper
    settings: Settings
    backend: Backend
    designs: set[str] = field(default_factory=set)
    searcher: LiteratureSearcher | None = None
    literature: list[LitRef] = field(default_factory=list)
    run_dir: Path | None = None
    blind: bool = True  # blind author identity to LLM attacks (anti prestige-bias)
    ensemble: int = 1  # run each LLM attack N times and keep findings that recur
    deep: bool = False  # branch-and-merge: try several verification strategies and merge
    allow_code: bool = False  # let the agent write+run analysis code for uncovered methods
    methods: set[str] = field(default_factory=set)  # detected estimation methods
    methodology: dict[str, str] = field(default_factory=dict)  # retrieved method references
    data_path: str | None = None  # dataset, when available (enables dynamic checks)
    notes: dict[str, Any] = field(default_factory=dict)


class Attack:
    """Base class. Subclasses set metadata and implement :meth:`run`."""

    name: str = "attack"
    category: str = "robustness"
    kind: str = "llm"  # "llm" | "network" | "replication"
    requires_llm: bool = True
    description: str = ""

    def gate(self, ctx: AttackContext) -> bool:
        """Return False to skip this attack for this paper (design gating)."""
        return True

    def run(self, ctx: AttackContext) -> list[Finding]:  # pragma: no cover - abstract
        raise NotImplementedError
