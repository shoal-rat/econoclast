"""Tests for dataset discovery and the archive/table acquisition helpers."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from econoclast.bibliotheca.datalinks import find_dataset_links
from econoclast.tesserae.models import Paper


def _paper(text: str) -> Paper:
    return Paper(title="t", text=text)


def test_discovers_zenodo_and_github_and_direct():
    p = _paper(
        "Data availability: the replication package is archived at "
        "https://zenodo.org/records/1234567 and the code at "
        "https://github.com/jane/replication. The panel is at https://example.org/data/panel.csv."
    )
    links = find_dataset_links(p)
    kinds = {link.kind for link in links}
    assert {"zenodo", "github", "direct"} <= kinds
    z = next(link for link in links if link.kind == "zenodo")
    assert "1234567" in z.url


def test_discovers_dataverse_doi():
    p = _paper("Replication data: doi:10.7910/DVN/ABCDEF available at Harvard Dataverse.")
    links = find_dataset_links(p)
    dv = [link for link in links if link.kind == "dataverse"]
    assert dv and "10.7910/DVN/ABCDEF" in dv[0].url


def test_icpsr_marked_unsupported():
    p = _paper("Data deposited at https://www.openicpsr.org/openicpsr/project/123456/view")
    links = find_dataset_links(p)
    icpsr = [link for link in links if link.kind == "icpsr"]
    assert icpsr and icpsr[0].supported is False


def test_data_availability_context_boosts_score():
    p = _paper(
        "We mention github.com/random/unrelated in passing.\n\n"
        "Data Availability Statement: the dataset is at https://zenodo.org/records/999."
    )
    links = find_dataset_links(p)
    # The zenodo link near the availability statement should outrank the stray repo.
    assert links[0].kind == "zenodo"


def test_zip_extraction_and_table_pick(tmp_path):
    import pytest

    pytest.importorskip("pandas")
    from econoclast.bibliotheca.acquire import (
        _save_and_maybe_unzip,
        pick_main_table,
        tabular_files,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "hello")
        zf.writestr("analysis_panel.csv", "wage,educ,age\n10,12,30\n11,13,31\n")
    out = _save_and_maybe_unzip(buf.getvalue(), tmp_path, "pkg.zip")
    tables = tabular_files([Path(p) for p in out])
    assert any(t.name == "analysis_panel.csv" for t in tables)
    paper = _paper("We regress wage on educ and age.")
    assert pick_main_table(tables, paper).name == "analysis_panel.csv"


def test_zip_slip_is_refused(tmp_path):
    from econoclast.bibliotheca.acquire import _save_and_maybe_unzip

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../../evil.csv", "a\n1\n")
        zf.writestr("ok/data.csv", "a\n1\n")
    out = _save_and_maybe_unzip(buf.getvalue(), tmp_path, "pkg.zip")
    assert [p.name for p in out] == ["data.csv"]
    assert not (tmp_path.parent / "evil.csv").exists()


def test_classify_url():
    from econoclast.bibliotheca.datalinks import classify_url

    assert classify_url("https://zenodo.org/records/123456")[0] == "zenodo"
    assert classify_url("https://doi.org/10.7910/DVN/ABCDEF")[0] == "dataverse"
    assert classify_url("https://github.com/owner/repo")[0] == "github"
    assert classify_url("https://example.org/data.csv")[0] == "direct"
