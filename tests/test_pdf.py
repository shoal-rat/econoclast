"""Reading a real PDF with the backend every default install has (pypdf; PyMuPDF is an opt-in extra)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")


def _paper_pdf(path) -> None:  # noqa: ANN001
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    pages = [["Minimum Wages and Teen Employment", "Abstract",
              "Employment rose by 2.8 percentage points in treated counties."],
             ["Table 2 reports the main estimate, 2.8 (1.1), with N = 410 restaurants."]]
    with plt.rc_context({"pdf.fonttype": 42}), PdfPages(path) as pdf:
        for lines in pages:
            fig = plt.figure(figsize=(8.5, 11))
            for i, line in enumerate(lines):
                fig.text(0.1, 0.9 - 0.05 * i, line, fontsize=16 if i == 0 else 11)
            pdf.savefig(fig)
            plt.close(fig)


def test_reads_a_pdf_without_pymupdf(tmp_path, monkeypatch):
    from econoclast.tesserae import pdf as reader

    def no_pymupdf(path):  # noqa: ANN001, ANN202
        raise ImportError("PyMuPDF is an opt-in extra")

    monkeypatch.setattr(reader, "_extract_pymupdf", no_pymupdf)
    monkeypatch.delenv("ECONOCLAST_GROBID_URL", raising=False)
    path = tmp_path / "paper.pdf"
    _paper_pdf(path)
    out = reader.extract_pdf(str(path))
    assert out["backend"] == "pypdf" and out["n_pages"] == 2
    assert "2.8 percentage points" in out["text"] and "N = 410" in out["pages"][1]
