"""The arsenal tools, called directly (no MCP transport)."""

from __future__ import annotations

import json
import threading
import time

import numpy as np
import pandas as pd
import pytest

from econoclast.arsenal.tools import Arsenal
from econoclast.case import Case


@pytest.fixture
def armed(paper_file):
    case = Case.create(paper=str(paper_file))
    a = Arsenal(case)
    a.read_paper(str(paper_file))
    return case, a


def test_proclaim_returns_orders_and_emits(armed):
    case, a = armed
    res = a.proclaim("scriptorium", "reading")
    assert "mark_target" in res["orders"]
    assert a.proclaim("rome")["error"]
    st = [e for e in case.events() if e["kind"] == "station"]
    assert st[-1]["station"] == "scriptorium" and case.meta()["station"] == "scriptorium"


def test_read_paper_reports_structure(armed, paper_file):
    case, a = armed
    res = a.read_paper(str(paper_file))
    assert res["title"].startswith("Minimum Wages")
    assert "did" in res["designs_detected"]
    assert any("zenodo" in link["url"] for link in res["data_links_in_text"])
    assert case.path("paper", "paper.txt").exists()
    intel = [e for e in case.events() if e["kind"] == "intel" and e["about"] == "paper"]
    assert intel and intel[-1]["n_stats"] > 0
    assert case.meta()["title"].startswith("Minimum Wages")


def test_quotes_are_checked_and_wounds_graded(armed):
    case, a = armed
    assert a.verify_quote("Minimum wages unambiguously raise employment.")["found"] is True
    miss = a.verify_quote("Minimum wages destroy every job in the economy forever.")
    assert miss["found"] is False
    good = a.inflict_wound("tuba", "Causal language overreaches", "high", "The design cannot show this.",
                           confidence=0.8, quote="Minimum wages unambiguously raise employment.")
    bad = a.inflict_wound("tuba", "Invented quote", "high", "x", confidence=0.8,
                          quote="Minimum wages destroy every job in the economy forever.")
    assert good["verified"] is True and good["effective_confidence"] == 0.8
    assert bad["verified"] is False and bad["effective_confidence"] == 0.3 and "warning" in bad
    assert a.inflict_wound("sword", "t", "high", "d")["error"]
    assert a.inflict_wound("speculum", "t", "high", "d", evidence_kind="computation",
                           artifacts=["out/nope.txt"])["error"]
    assert len(case.wounds()) == 2


def test_abacus_flags_impossible_stars_and_p(armed):
    _, a = armed
    flags = a.abacus()["flags"]
    issues = " ".join(f["issue"] for f in flags)
    assert "|t| = 1.20" in issues  # 0.12*** (0.10)
    assert "implies p" in issues  # t(48) = 2.10 but p = .40


def test_reproduce_grades_the_gap(armed):
    case, a = armed
    assert a.reproduce("main", 2.8, 2.79)["verdict"] == "match"
    assert a.reproduce("main", 2.8, 2.5)["verdict"] == "close"
    assert a.reproduce("main", 2.8, -0.4)["verdict"] == "mismatch"
    assert len([e for e in case.events() if e["kind"] == "speculum"]) == 3


def test_mille_viae_runs_and_records_wounds(armed):
    case, a = armed
    rng = np.random.default_rng(0)
    n = 500
    c1, c2 = rng.standard_normal(n), rng.standard_normal(n)
    treat = 0.7 * c1 + rng.standard_normal(n)
    y = 1.2 * c1 + 0.4 * c2 + rng.standard_normal(n)
    pd.DataFrame({"y": y, "treat": treat, "c1": c1, "c2": c2}).to_csv(case.path("data", "d.csv"), index=False)
    ins = a.inspect_dataset("data/d.csv")
    assert ins["rows"] == n and {c["name"] for c in ins["columns"]} == {"y", "treat", "c1", "c2"}
    res = a.mille_viae({"data": "data/d.csv", "outcome": "y", "treatment": "treat",
                        "controls_pool": ["c1", "c2"], "controls_mode": "powerset", "preferred_sign": 1})
    assert res["ok"] and res["summary"]["n_specs_run"] >= 4
    assert case.path("out", "viae.json").exists()
    done = [e for e in case.events() if e["kind"] == "viae" and e["status"] == "done"]
    assert done and len(done[0]["points"]) == res["summary"]["n_specs_run"]
    assert any(w.blade == "mille_viae" for w in case.wounds())
    bad = a.mille_viae({"data": "data/d.csv", "outcome": "nope", "treatment": "treat"})
    assert bad["ok"] is False


def test_plea_round_trip(armed):
    case, a = armed
    pid = a.plea_open("the replication package", "openICPSR needs a login", where="https://openicpsr.org/x")
    assert a.plea_poll(pid) is None and case.meta()["waiting_plea"] == pid
    up = case.path("offerings", "pkg.zip")
    up.write_bytes(b"PK")

    def answer():
        time.sleep(0.2)
        case.answer_plea(pid, files=[str(up)])

    threading.Thread(target=answer).start()
    ans = None
    for _ in range(50):
        ans = a.plea_poll(pid)
        if ans:
            break
        time.sleep(0.05)
    assert ans and ans["files"] == ["offerings/pkg.zip"]
    assert case.meta()["waiting_plea"] is None
    kinds = [e["kind"] for e in case.events()]
    assert "plea" in kinds and "plea.answered" in kinds


def test_verdict_writes_the_tabula(armed):
    case, a = armed
    a.inflict_wound("persona", "Parallel trends never shown", "high", "No event study.", confidence=0.8,
                    quote="We estimate a two-way fixed effects model with standard errors clustered by county.")
    a.parry("augur", "Hypothesis stated before results.")
    res = a.pronounce_verdict("The decree bleeds.", "One deep wound.", "An event study.", ["the data work"])
    assert res["score"] > 0 and res["report"]["html"] == "tabula.html"
    v = json.loads(case.path("verdict.json").read_text())
    assert v["headline"] == "The decree bleeds." and v["n_parries"] == 1
    assert case.path("tabula.html").exists() and case.path("tabula.md").exists()
    assert [e for e in case.events() if e["kind"] == "verdict"]


def test_tools_without_paper_say_so(tmp_path):
    a = Arsenal(Case.create(paper="x"))
    assert "error" in a.verify_quote("anything at all here")
    assert "error" in a.abacus()


def test_field_notes_feed_the_reality_blades(armed):
    case, a = armed
    orders = a.proclaim("forum")["orders"]
    assert "inversio" in orders and "theoria" in orders and "mundus" in orders
    res = a.field_notes("Labour economics: minimum wages", "Fast food, NJ and PA, 1992",
                        actors=["franchise owners: margins thin, set prices", "teen workers"],
                        claimed_mechanism="monopsony lets employment rise", real_mechanism="owners raise prices",
                        theory="monopsony model", theory_assumptions=["upward-sloping labour supply to the firm"],
                        rival_explanations=["PA-specific downturn"], sources=["https://example.org/survey"])
    assert res["recorded"] == "notes/field.md" and case.path("notes", "field.md").exists()
    ev = [e for e in case.events() if e["kind"] == "intel" and e["about"] == "field"][-1]
    assert ev["n_sources"] == 1 and ev["rivals"] == 1
    w = a.inflict_wound("inversio", "Wages may follow employment", "medium", "detail", confidence=0.6,
                        quote="We restrict the sample to counties surveyed in both waves between 1992 and 1993.")
    assert w["verified"] is True
    a.pronounce_verdict("h", "a", "c")
    from econoclast.case.tabula import tabula_data

    assert tabula_data(case)["field"]["theory"] == "monopsony model"
    assert "The real world" in case.path("tabula.html").read_text()


def test_fetch_paper_records_the_file(tmp_path, monkeypatch):
    from econoclast.tesserae import fetch

    case = Case.create(paper="https://example.org/p.pdf")
    a = Arsenal(case)
    target = case.path("paper", "p.pdf")
    target.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(fetch, "resolve_source", lambda url, cache_dir=None: str(target))
    res = a.fetch_paper("https://example.org/p.pdf")
    assert res["ok"] and res["path"] == "paper/p.pdf"
    ev = [e for e in case.events() if e["kind"] == "acquired"][-1]
    assert ev["filetype"] == "pdf" and ev["ok"] is True
