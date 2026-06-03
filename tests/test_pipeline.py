"""Router, fragility, and end-to-end pipeline tests (all offline)."""

from __future__ import annotations

from pathlib import Path

from econoclast.agent.harness import Econoclast
from econoclast.attacks.base import Finding
from econoclast.attacks.designs import detect_designs
from econoclast.config import Settings
from econoclast.llm.base import Message
from econoclast.llm.router import ModelRouter
from econoclast.report.fragility import compute_fragility

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_paper.txt"


def test_router_mock_is_offline():
    router = ModelRouter(Settings(), force_mock=True)
    assert router.is_live() is False
    resp = router.complete("attacker", [Message(role="user", content="hello")])
    assert resp.provider == "mock" and resp.text


def test_design_detection():
    designs = detect_designs("We use a regression discontinuity design with bandwidth h and a McCrary test.")
    assert "rdd" in designs


def test_fragility_score_and_band():
    findings = [
        Finding(attack="statcheck", title="x", category="reporting_inconsistency",
                severity="high", detail="", confidence=0.95),
    ]
    forensic = [{"name": "statcheck", "verdict": "suspicious", "stats": {"decision_errors": 1}}]
    frag = compute_fragility(findings, forensic)
    assert frag["integrity_violation"] is True
    assert frag["score"] > 0 and frag["band"] in (
        "Minor concerns", "Material concerns", "Fragile", "Severe"
    )


def test_end_to_end_demo_offline():
    assert DEMO.exists()
    eco = Econoclast(force_mock=True)
    report = eco.review(DEMO, use_llm=False, use_literature=False)
    # The planted issues must surface.
    flagged = {r["name"] for r in report.forensic_results if r["verdict"] == "suspicious"}
    assert {"statcheck", "grim"} <= flagged
    assert report.fragility["integrity_violation"] is True
    assert report.fragility["score"] >= 40
    # Report serialises cleanly.
    assert report.to_json().startswith("{")
