"""The Report object produced by a full review."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from econoclast.attacks.base import SEVERITY_WEIGHT, Finding


@dataclass
class Report:
    paper_title: str
    paper_path: str
    source_format: str
    designs: list[str]
    n_claims: int
    forensic_results: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    fragility: dict = field(default_factory=dict)
    referee: dict = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def findings_sorted(self) -> list[Finding]:
        return sorted(
            self.findings,
            key=lambda f: (f.weight, SEVERITY_WEIGHT.get(f.severity, 0), f.confidence),
            reverse=True,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "econoclast.report/v1",
            "paper": {
                "title": self.paper_title,
                "path": self.paper_path,
                "source_format": self.source_format,
                "designs": self.designs,
                "n_claims": self.n_claims,
            },
            "fragility": self.fragility,
            "referee": self.referee,
            "findings": [f.to_dict() for f in self.findings_sorted()],
            "forensics": self.forensic_results,
            "meta": self.meta,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
