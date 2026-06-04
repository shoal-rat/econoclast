"""Tests for the conversational intake and the comprehension merge (offline paths)."""

from __future__ import annotations

from econoclast.agent.comprehend import merge_designs
from econoclast.agent.intake import build_intake, needed_questions, understand_request


def test_understand_request_finds_url():
    s = understand_request("can you check https://arxiv.org/abs/2401.12345 for me?", router=None)
    assert s["paper"].startswith("https://arxiv.org/abs/") and s["paper_kind"] == "url"


def test_understand_request_separates_paper_and_data():
    s = understand_request("the paper is at paper.pdf and my data is at /home/d.csv", router=None)
    assert s["paper"].endswith("paper.pdf") and s["paper_kind"] == "path"
    assert s["data"].endswith("d.csv")


def test_needed_questions_asks_for_paper_first():
    qs = needed_questions({"paper": "", "data": "", "claim": ""})
    assert len(qs) == 1 and qs[0]["required"] is True


def test_needed_questions_optional_when_paper_present():
    qs = needed_questions({"paper": "p.pdf", "data": "", "claim": ""})
    assert qs and all(q["required"] is False for q in qs)


def test_build_intake_ready_when_paper_present():
    out = build_intake("review https://example.org/p.pdf", settings=None)
    assert out["ready"] is True and out["next"] == "verify"
    out2 = build_intake("can you check a paper for me?", settings=None)
    assert out2["ready"] is False and out2["next"] == "ask_user"


def test_merge_designs_adds_model_reading():
    merged = merge_designs({"panel_fe"}, {"design": "regression discontinuity", "methods": ["McCrary test"]})
    assert "rdd" in merged and "panel_fe" in merged
    assert merge_designs({"did"}, None) == {"did"}  # no comprehension -> unchanged
