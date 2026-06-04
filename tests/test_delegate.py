"""Tests for the agent-delegated download (the boss/employee handoff)."""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from _fake import FakeBackend, FakeProvider
from econoclast.ingest import fetch
from econoclast.ingest.fetch import _agent_paper, resolve_source
from econoclast.llm.backend import Backend, _fetch_order
from econoclast.replication.acquire import _agent_dataset


def test_fetch_order_is_a_clear_work_order():
    order = _fetch_order("/tmp/work", url="https://x/paper.pdf", what="the paper PDF")
    assert "https://x/paper.pdf" in order and "/tmp/work" in order
    assert "the paper PDF" in order
    assert "FAILED" in order  # the agent is told how to report failure
    assert "browser" in order.lower()  # it is told it may drive a browser


def test_backend_fetch_into_returns_the_saved_file(tmp_path):
    be = Backend(FakeProvider(writes=[("paper.pdf", b"%PDF-1.4 hi")]), "fake")
    new = be.fetch_into(tmp_path, url="https://x/p.pdf", what="a paper")
    assert [p.name for p in new] == ["paper.pdf"]


def test_backend_fetch_into_empty_when_nothing_written(tmp_path):
    be = Backend(FakeProvider(writes=[]), "fake")
    assert be.fetch_into(tmp_path, url="https://x") == []


def test_agent_paper_returns_pdf(tmp_path):
    be = FakeBackend(downloads=[("got.pdf", b"%PDF-1.5")])
    out = _agent_paper("https://x/p.pdf", tmp_path, be)
    assert out and out.endswith("got.pdf")
    assert be.fetch_orders  # the agent was actually asked


def test_agent_paper_none_without_backend(tmp_path):
    assert _agent_paper("https://x/p.pdf", tmp_path, None) is None


def test_agent_dataset_ingests_a_direct_csv(tmp_path):
    be = FakeBackend(downloads=[("data.csv", "a,b\n1,2\n")])
    files = _agent_dataset("https://x/d.csv", tmp_path, query="some paper", backend=be)
    assert len(files) == 1 and files[0].suffix == ".csv"


def test_agent_dataset_unzips_what_the_agent_saved(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("panel.csv", "x,y\n3,4\n")
    be = FakeBackend(downloads=[("pkg.zip", buf.getvalue())])
    files = _agent_dataset("https://x/pkg.zip", tmp_path, query="t", backend=be)
    assert any(p.name == "panel.csv" for p in files)


def test_agent_dataset_empty_without_backend(tmp_path):
    assert _agent_dataset("https://x/d.csv", tmp_path, query="t", backend=None) == []


def test_resolve_source_raises_when_blocked_and_no_agent(monkeypatch):
    def boom(url, out_dir):  # noqa: ANN001
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr(fetch, "_http_fetch", boom)
    with pytest.raises(RuntimeError):
        resolve_source("https://blocked.example/p.pdf", backend=None)
