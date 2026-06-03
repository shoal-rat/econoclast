"""Paper ingestion: PDF/LaTeX/text -> structured `Paper` with extracted claims."""

from econoclast.ingest.claims import extract_claims_from_paper, extract_statistics
from econoclast.ingest.models import Paper, Section, StatClaim, Table
from econoclast.ingest.paper import load_paper

__all__ = [
    "Paper",
    "Section",
    "StatClaim",
    "Table",
    "extract_claims_from_paper",
    "extract_statistics",
    "load_paper",
]
