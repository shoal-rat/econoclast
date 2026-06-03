"""Literature layer: keyless online search + local corpus + keyword retrieval."""

from __future__ import annotations

import re
from collections import Counter

from econoclast.config import LiteratureConfig
from econoclast.literature.corpus import load_local_corpus
from econoclast.literature.models import LitRef
from econoclast.literature.sources import SOURCES
from econoclast.logging import get_logger

log = get_logger("literature")

__all__ = ["LitRef", "LiteratureSearcher", "load_local_corpus"]

_WORD = re.compile(r"[a-z]{3,}")
_STOP = set(
    "the and for that with this from are was were has have not but can may our their these those "
    "into over under more most such than then them they when which while also about across among".split()
)


def _tokens(text: str) -> Counter:
    return Counter(w for w in _WORD.findall(text.lower()) if w not in _STOP)


class LiteratureSearcher:
    """Search online sources + a local corpus, then rank by keyword overlap."""

    def __init__(self, config: LiteratureConfig | None = None) -> None:
        self.config = config or LiteratureConfig()
        self._local: list[tuple[LitRef, str]] = []
        if self.config.local_dirs:
            self._local = load_local_corpus(self.config.local_dirs)

    def search(self, query: str, *, limit: int | None = None, sources: list[str] | None = None) -> list[LitRef]:
        limit = limit or self.config.max_results
        sources = sources or self.config.sources
        per_source = max(3, limit // max(len(sources), 1) + 2)

        found: list[LitRef] = []
        for name in sources:
            fn = SOURCES.get(name)
            if fn is None:
                log.warning("Unknown literature source '%s'", name)
                continue
            try:
                found.extend(fn(query, per_source))
            except Exception as exc:  # noqa: BLE001
                log.warning("source %s failed: %s", name, exc)

        found.extend(self._local_matches(query, per_source))
        ranked = self._rank(query, _dedupe(found))
        return ranked[:limit]

    def _local_matches(self, query: str, limit: int) -> list[LitRef]:
        if not self._local:
            return []
        qt = _tokens(query)
        scored = []
        for ref, text in self._local:
            overlap = sum((qt & _tokens(text[:6000])).values())
            if overlap:
                ref.score = float(overlap)
                scored.append(ref)
        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    def _rank(self, query: str, refs: list[LitRef]) -> list[LitRef]:
        qt = _tokens(query)
        for r in refs:
            text = f"{r.title} {r.abstract}"
            overlap = sum((qt & _tokens(text)).values())
            cite_boost = 0.0
            if r.citations:
                cite_boost = min(0.5, r.citations / 2000.0)
            r.score = overlap + cite_boost
        refs.sort(key=lambda r: r.score, reverse=True)
        return refs


def _dedupe(refs: list[LitRef]) -> list[LitRef]:
    seen: dict[str, LitRef] = {}
    for r in refs:
        k = r.key()
        if k not in seen:
            seen[k] = r
        elif r.citations and (seen[k].citations or 0) < r.citations:
            seen[k] = r
    return list(seen.values())
