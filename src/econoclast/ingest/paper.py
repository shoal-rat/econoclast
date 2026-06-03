"""Load a paper from PDF / LaTeX / plain text into the `Paper` model."""

from __future__ import annotations

import re
from pathlib import Path

from econoclast.ingest.claims import extract_claims_from_paper
from econoclast.ingest.latex import extract_latex
from econoclast.ingest.models import Paper, Section
from econoclast.ingest.pdf import extract_pdf
from econoclast.ingest.sanitize import detect_injection, strip_invisibles
from econoclast.logging import get_logger

log = get_logger("ingest.paper")

# Section headers we expect in an empirical economics paper.
_HEADING_RE = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)\.?\s+)?"
    r"(abstract|introduction|related work|literature|background|data|"
    r"institutional|empirical strateg\w*|identification|methodolog\w*|model|"
    r"estimation|results?|findings?|robustness|heterogeneity|mechanisms?|"
    r"discussion|limitations?|conclusion|appendix|references)\b.*$",
    re.IGNORECASE,
)
_NUMBERED_RE = re.compile(r"^\s*(\d+(?:\.\d+){0,2})\.?\s+[A-Z][A-Za-z].{0,60}$")


def load_paper(path: str | Path) -> Paper:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    suffix = p.suffix.lower()

    if suffix == ".pdf":
        data = extract_pdf(str(p))
        sections = _segment(data["text"])
        paper = Paper(
            title=data.get("title") or _guess_title(data["text"]),
            text=data["text"],
            path=str(p),
            source_format="pdf",
            sections=sections,
            tables=data["tables"],
            meta={"n_pages": data.get("n_pages")},
        )
    elif suffix in (".tex", ".latex"):
        data = extract_latex(str(p))
        sections = _segment(data["text"])
        paper = Paper(
            title=data.get("title") or _guess_title(data["text"]),
            text=data["text"],
            path=str(p),
            source_format="latex",
            abstract=data.get("abstract", ""),
            sections=sections,
            tables=data["tables"],
            meta={"raw_latex_len": len(data.get("raw_latex", ""))},
        )
    else:
        text = p.read_text(encoding="utf-8", errors="ignore")
        paper = Paper(
            title=_guess_title(text),
            text=text,
            path=str(p),
            source_format="text",
            sections=_segment(text),
        )

    # Manuscript hygiene: strip invisible/zero-width characters (injection vector)
    # and re-segment on the clean text before extracting claims.
    paper.text = strip_invisibles(paper.text)
    paper.sections = _segment(paper.text)
    injections = detect_injection(paper.text)
    if injections:
        log.warning("Possible prompt-injection text found in manuscript: %d hit(s)", len(injections))
    paper.meta["injection_warnings"] = injections

    if not paper.abstract:
        paper.abstract = _guess_abstract(paper.text)
    paper.claims = extract_claims_from_paper(paper)
    log.info(
        "Loaded '%s' (%s): %d sections, %d tables, %d statistical claims",
        Path(paper.path).name,
        paper.source_format,
        len(paper.sections),
        len(paper.tables),
        len(paper.claims),
    )
    return paper


def _segment(text: str) -> list[Section]:
    """Split text into sections on detected headings."""
    lines = text.splitlines(keepends=True)
    marks: list[tuple[int, str, int]] = []  # (char_offset, name, level)
    offset = 0
    for line in lines:
        stripped = line.strip()
        if 0 < len(stripped) <= 80:
            m = _HEADING_RE.match(stripped)
            if m:
                name = re.sub(r"\s+", " ", stripped)[:80]
                level = 1 + (m.group(1).count(".") if m.group(1) else 0)
                marks.append((offset, name, level))
            elif _NUMBERED_RE.match(stripped):
                marks.append((offset, stripped[:80], 1 + stripped.split()[0].count(".")))
        offset += len(line)

    if not marks:
        return [Section(name="body", text=text, level=1, start_char=0)]

    sections: list[Section] = []
    if marks[0][0] > 0:
        sections.append(Section(name="frontmatter", text=text[: marks[0][0]], start_char=0))
    for i, (start, name, level) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        sections.append(Section(name=name, text=text[start:end], level=level, start_char=start))
    return sections


def _guess_title(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if len(s) > 12 and not s.lower().startswith(("abstract", "draft", "working paper")):
            return s[:200]
    return "(untitled)"


def _guess_abstract(text: str) -> str:
    m = re.search(r"\babstract\b[:\s]*(.{50,2500}?)(?:\n\n|\bkeywords\b|\bJEL\b|\b1\.?\s+introduction\b)",
                  text, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
