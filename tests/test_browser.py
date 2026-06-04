"""Tests for the browser download fallback (pure logic + graceful degradation)."""

from __future__ import annotations

import io
import zipfile

from _fake import FakeBackend
from econoclast.ingest import browser
from econoclast.replication.acquire import _browser_dataset, _ingest_bytes


def test_unwrap_ddg():
    wrapped = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fdata.csv&rut=abc"
    assert browser._unwrap_ddg(wrapped) == "https://example.org/data.csv"
    assert browser._unwrap_ddg("https://direct.example/x") == "https://direct.example/x"
    assert browser._unwrap_ddg("/relative") == ""


def test_browser_available_is_bool():
    assert isinstance(browser.browser_available(), bool)


def test_rank_candidates_without_backend_keeps_order():
    cands = [("A", "https://a"), ("B", "https://b")]
    assert browser.rank_candidates("q", cands, None) == ["https://a", "https://b"]


def test_rank_candidates_uses_the_backend_then_appends_dropped():
    cands = [("A", "https://a"), ("B", "https://b"), ("C", "https://c")]
    be = FakeBackend(responses={"extractor": '["https://c", "https://a"]'})
    ranked = browser.rank_candidates("q", cands, be)
    assert ranked[:2] == ["https://c", "https://a"]
    assert "https://b" in ranked  # dropped by the model, still appended


def test_browser_fns_graceful_without_playwright(monkeypatch):
    monkeypatch.setattr(browser, "browser_available", lambda: False)
    assert browser.browser_fetch_file("https://x/y.pdf") is None
    assert browser.browser_fetch_page("https://x") is None
    assert browser.browser_search("anything") == []


def test_ingest_bytes_direct_csv(tmp_path):
    got = (b"a,b\n1,2\n", "text/csv")
    files = _ingest_bytes(got, tmp_path, "https://x/d.csv")
    assert len(files) == 1 and files[0].suffix == ".csv"


def test_ingest_bytes_zip_of_csv(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("data.csv", "a,b\n1,2\n")
    files = _ingest_bytes((buf.getvalue(), "application/zip"), tmp_path, "https://x/pkg.zip")
    assert len(files) == 1 and files[0].name == "data.csv"


def test_browser_dataset_searches_when_direct_link_dead(tmp_path, monkeypatch):
    # A direct URL that yields nothing, then a search hit that does.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("panel.csv", "x,y\n3,4\n")
    good_zip = buf.getvalue()

    def fake_fetch(url, *, prefer_ext=()):  # noqa: ANN001
        return (good_zip, "application/zip") if "candidate" in url else None

    monkeypatch.setattr(browser, "browser_available", lambda: True)
    monkeypatch.setattr(browser, "browser_fetch_file", fake_fetch)
    monkeypatch.setattr(browser, "browser_search", lambda q, **k: [("hit", "https://candidate/data.zip")])
    monkeypatch.setattr(browser, "rank_candidates", lambda q, c, b: [u for _, u in c])

    files = _browser_dataset("https://dead.example/blocked", tmp_path,
                             query="some paper title", backend=None)
    assert len(files) == 1 and files[0].name == "panel.csv"


def test_browser_dataset_returns_empty_without_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(browser, "browser_available", lambda: False)
    assert _browser_dataset("https://x/d.csv", tmp_path, query="t", backend=None) == []
