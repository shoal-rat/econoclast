"""Tests for the conversational intake and the comprehension merge."""

from __future__ import annotations

from _fake import FakeBackend
from econoclast.agent.comprehend import merge_designs
from econoclast.agent.intake import (
    build_intake,
    default_plan,
    needed_questions,
    understand_request,
)


def _backend(paper="", kind="none", data="", claim=""):
    js = (f'{{"paper": "{paper}", "paper_kind": "{kind}", '
          f'"data": "{data}", "claim": "{claim}"}}')
    return FakeBackend(responses={"extractor": js})


def test_understand_request_uses_the_backend():
    s = understand_request("check this for me", _backend("https://arxiv.org/abs/2401.12345", "url"))
    assert s["paper"].startswith("https://arxiv.org/abs/") and s["paper_kind"] == "url"


def test_understand_request_separates_paper_and_data():
    s = understand_request("paper + data", _backend("paper.pdf", "path", "d.csv"))
    assert s["paper"] == "paper.pdf" and s["paper_kind"] == "path"
    assert s["data"] == "d.csv"


def test_understand_request_empty_on_backend_failure():
    class Boom(FakeBackend):
        def complete(self, *a, **k):  # noqa: ANN001
            raise RuntimeError("no model")

    s = understand_request("anything", Boom())
    assert s == {"paper": "", "paper_kind": "none", "data": "", "claim": ""}


def test_needed_questions_asks_for_paper_first():
    qs = needed_questions({"paper": "", "data": "", "claim": ""})
    assert len(qs) == 1 and qs[0]["required"] is True


def test_needed_questions_optional_when_paper_present():
    qs = needed_questions({"paper": "p.pdf", "data": "", "claim": ""})
    assert qs and all(q["required"] is False for q in qs)


def test_build_intake_ready_states_a_plan_and_no_blocking_question():
    out = build_intake("review it", backend=_backend("https://example.org/p.pdf", "url"))
    assert out["ready"] is True and out["next"] == "verify"
    assert out["plan"] and out["blocking_question"] == ""


def test_build_intake_not_ready_asks_for_the_paper():
    out = build_intake("can you check a paper?", backend=_backend())
    assert out["ready"] is False and out["next"] == "ask_user"
    assert out["plan"] == "" and out["blocking_question"]


def test_default_plan_reflects_data_and_claim_defaults():
    no_data = default_plan({"paper": "p.pdf", "data": "", "claim": ""})
    assert "main result" in no_data and "public data" in no_data
    with_data = default_plan({"paper": "p.pdf", "data": "d.csv", "claim": "the wage effect"})
    assert "the wage effect" in with_data and "dataset you gave me" in with_data


def test_merge_designs_adds_model_reading():
    merged = merge_designs({"panel_fe"}, {"design": "regression discontinuity", "methods": ["McCrary test"]})
    assert "rdd" in merged and "panel_fe" in merged
    assert merge_designs({"did"}, None) == {"did"}  # no comprehension -> unchanged
