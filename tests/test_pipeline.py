"""Fragility and end-to-end pipeline tests (with an injected fake backend)."""

from __future__ import annotations

from pathlib import Path

from _fake import FakeBackend
from econoclast.agent.harness import Econoclast
from econoclast.attacks.base import Finding
from econoclast.attacks.designs import detect_designs
from econoclast.config import Settings
from econoclast.report.fragility import compute_fragility

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_paper.txt"


def test_design_detection():
    designs = detect_designs("We use a regression discontinuity design with bandwidth h and a McCrary test.")
    assert "rdd" in designs


def test_fragility_score_and_band():
    findings = [
        Finding(attack="reporting-check", title="A reported statistic is impossible",
                category="reporting_inconsistency", severity="high", detail="", confidence=0.95),
    ]
    frag = compute_fragility(findings)
    assert frag["integrity_violation"] is True
    assert frag["score"] > 0 and frag["band"] in (
        "Minor concerns", "Material concerns", "Fragile", "Severe"
    )


def test_fragility_empty_is_robust():
    frag = compute_fragility([])
    assert frag["score"] == 0 and frag["band"] == "Robust"
    assert frag["integrity_violation"] is False


def test_end_to_end_demo_with_fake_backend():
    assert DEMO.exists()
    eco = Econoclast(settings=Settings(), backend=FakeBackend())
    report = eco.review(DEMO, use_literature=False)
    # The run completes and serialises cleanly even when the model finds nothing.
    assert report.meta["backend"] == "fake"
    assert isinstance(report.fragility["score"], (int, float))
    assert report.fragility["band"] in (
        "Robust", "Minor concerns", "Material concerns", "Fragile", "Severe"
    )
    assert report.to_json().startswith("{")
    # No forensic battery exists any more.
    assert "forensics" not in report.to_dict()
