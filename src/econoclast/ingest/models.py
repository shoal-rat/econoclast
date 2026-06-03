"""Core data model for an ingested paper."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Section:
    name: str
    text: str
    level: int = 1
    start_char: int = 0


@dataclass
class Table:
    label: str
    caption: str = ""
    raw: str = ""
    # Flattened numeric cells we could parse out, with their string form.
    numbers: list[float] = field(default_factory=list)


@dataclass
class StatClaim:
    """One reported statistic with enough context to attack it.

    Most fields are optional; a given claim populates only what it carries. The
    forensic modules filter the claim list for the fields they need (statcheck
    wants a test statistic + p; GRIM wants mean + n; p-curve wants p-values).
    """

    raw: str
    section: str = ""
    page: int | None = None
    table: str | None = None
    source: str = "text"  # "text" | "table"
    char_offset: int = 0

    # Regression-style
    coef: float | None = None
    se: float | None = None
    stars: int = 0

    # Test statistics (for statcheck / p-curve / bunching)
    test_type: str | None = None  # "t", "F", "r", "z", "chi2"
    stat_value: float | None = None
    df1: float | None = None
    df2: float | None = None
    tail: int = 2  # 1 or 2 tailed

    # p-values
    p_value: float | None = None
    p_comparator: str = "="  # "=", "<", ">"

    # Descriptives (for GRIM / GRIMMER)
    mean: float | None = None
    sd: float | None = None
    decimals: int | None = None
    n: int | None = None

    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def implied_t(self) -> float | None:
        """t = coef / se when both are present."""
        if self.coef is not None and self.se not in (None, 0):
            return self.coef / self.se  # type: ignore[operator]
        return None

    def short(self) -> str:
        loc = self.table or self.section or self.source
        return f"[{loc}] {self.raw.strip()[:140]}"


@dataclass
class Paper:
    title: str
    text: str
    path: str = ""
    source_format: str = "text"  # "pdf" | "latex" | "text"
    abstract: str = ""
    sections: list[Section] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    claims: list[StatClaim] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def section_text(self, *keywords: str) -> str:
        """Concatenate sections whose name contains any keyword (case-insensitive)."""
        keys = [k.lower() for k in keywords]
        out = []
        for sec in self.sections:
            low = sec.name.lower()
            if any(k in low for k in keys):
                out.append(sec.text)
        return "\n\n".join(out)

    def excerpt(self, max_chars: int = 18000) -> str:
        """A compact excerpt for LLM context: abstract + section heads + tails."""
        if len(self.text) <= max_chars:
            return self.text
        head = self.text[: max_chars // 2]
        tail = self.text[-max_chars // 2 :]
        return f"{head}\n\n[... truncated {len(self.text) - max_chars} chars ...]\n\n{tail}"
