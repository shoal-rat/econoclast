"""Literature reference model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LitRef:
    title: str
    source: str  # "openalex" | "arxiv" | "semantic_scholar" | "crossref" | "local"
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    abstract: str = ""
    venue: str = ""
    doi: str | None = None
    url: str | None = None
    citations: int | None = None
    score: float = 0.0
    local_path: str | None = None

    def key(self) -> str:
        if self.doi:
            return self.doi.lower().strip()
        return "".join(ch for ch in self.title.lower() if ch.isalnum())[:80]

    def citation_line(self) -> str:
        who = self.authors[0].split()[-1] if self.authors else "Anon"
        if len(self.authors) > 1:
            who += " et al."
        yr = self.year or "n.d."
        venue = f" — {self.venue}" if self.venue else ""
        return f"{who} ({yr}). {self.title}{venue}."

    def context_block(self, max_abstract: int = 600) -> str:
        abs_ = self.abstract[:max_abstract] + ("…" if len(self.abstract) > max_abstract else "")
        cites = f" | citations: {self.citations}" if self.citations is not None else ""
        return f"[{self.source}] {self.citation_line()}{cites}\n{abs_}".strip()
