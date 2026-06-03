"""LaTeX source extraction.

LaTeX is *easier* to attack than PDF: the numbers in tables survive verbatim
and section structure is explicit. We resolve one level of ``\\input`` /
``\\include`` so the regression tables that papers keep in separate files are
pulled in.
"""

from __future__ import annotations

import re
from pathlib import Path

from econoclast.ingest.models import Table
from econoclast.logging import get_logger

log = get_logger("ingest.latex")

_COMMENT_RE = re.compile(r"(?<!\\)%.*?$", re.MULTILINE)
_INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
_TABLE_ENV_RE = re.compile(r"\\begin\{(table\*?|tabular\*?|threeparttable)\}.*?\\end\{\1\}", re.DOTALL)
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_CAPTION_RE = re.compile(r"\\caption\{(.+?)\}", re.DOTALL)
_TITLE_RE = re.compile(r"\\title\{(.+?)\}", re.DOTALL)
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_SECTION_RE = re.compile(r"\\(section|subsection|subsubsection)\*?\{([^}]*)\}")


def _resolve_inputs(text: str, base: Path, depth: int = 0) -> str:
    if depth > 3:
        return text

    def repl(m: re.Match) -> str:
        target = m.group(1)
        for cand in (base / target, base / f"{target}.tex"):
            if cand.exists():
                try:
                    inner = cand.read_text(encoding="utf-8", errors="ignore")
                    return _resolve_inputs(inner, cand.parent, depth + 1)
                except OSError:
                    return m.group(0)
        return m.group(0)

    return _INPUT_RE.sub(repl, text)


def extract_latex(path: str) -> dict:
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="ignore")
    raw = _resolve_inputs(raw, p.parent)
    clean = _COMMENT_RE.sub("", raw)

    title_m = _TITLE_RE.search(clean)
    title = _strip_commands(title_m.group(1)) if title_m else ""
    abstract_m = _ABSTRACT_RE.search(clean)
    abstract = _strip_commands(abstract_m.group(1)) if abstract_m else ""

    tables: list[Table] = []
    for tm in _TABLE_ENV_RE.finditer(clean):
        block = tm.group(0)
        label_m = _LABEL_RE.search(block)
        cap_m = _CAPTION_RE.search(block)
        tables.append(
            Table(
                label=label_m.group(1) if label_m else f"tab{len(tables) + 1}",
                caption=_strip_commands(cap_m.group(1)) if cap_m else "",
                raw=_detex_table(block),
            )
        )

    plain = _strip_commands(clean)
    return {
        "text": plain,
        "raw_latex": clean,
        "tables": tables,
        "title": title,
        "abstract": abstract,
    }


def _detex_table(block: str) -> str:
    # Keep numbers and separators; drop layout macros.
    block = re.sub(r"\\(begin|end)\{[^}]*\}", " ", block)
    block = re.sub(r"\\(resizebox|input|include|label|caption|multicolumn|cmidrule|cline)\b[^\n]*", " ", block)
    block = block.replace("&", "  ").replace("\\\\", "\n").replace("\\hline", "")
    block = re.sub(r"\\[a-zA-Z]+\*?", " ", block)
    block = re.sub(r"[{}]", " ", block)
    return re.sub(r"[ \t]{2,}", "  ", block).strip()


def _strip_commands(text: str) -> str:
    text = re.sub(r"\\begin\{(figure|table|tabular|equation|align|thebibliography)\*?\}.*?\\end\{\1\*?\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\(textbf|textit|emph|texttt|mathrm|text)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\(cite[a-z]*|ref|label|input|include|includegraphics)\{[^}]*\}", " ", text)
    text = re.sub(r"\$([^$]*)\$", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = re.sub(r"[{}]", "", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
