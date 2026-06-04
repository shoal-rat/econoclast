"""Tests for the research-then-verify and branch-and-merge machinery."""

from __future__ import annotations

from econoclast.attacks.base import AttackContext, Finding
from econoclast.attacks.designs import COVERED_METHODS, detect_methods, method_coverage
from econoclast.attacks.dynamic import _BANNED, DynamicCheckAttack
from econoclast.attacks.methodology import MethodologyAuditAttack
from econoclast.config import Settings
from econoclast.ingest.models import Paper
from econoclast.llm.router import ModelRouter


def _ctx(text, **kw):
    s = Settings()
    return AttackContext(paper=Paper(title="t", text=text), settings=s,
                         router=ModelRouter(s, force_mock=True), **kw)


def test_detect_methods_and_coverage():
    methods = detect_methods("We use a synthetic control method and a bunching estimator.")
    assert "synthetic_control" in methods and "bunching" in methods
    cov = method_coverage(methods)
    # Neither is covered by a built-in deterministic check -> both need research.
    assert "synthetic_control" in cov["needs_research"]
    assert "bunching" in cov["needs_research"]


def test_covered_methods_dont_need_research():
    methods = detect_methods("A regression discontinuity design with a running variable.")
    cov = method_coverage(methods)
    assert "rdd" in cov["covered"] and "rdd" in COVERED_METHODS
    assert "rdd" not in cov["needs_research"]


def test_methodology_audit_gates_on_method():
    a = MethodologyAuditAttack()
    assert a.gate(_ctx("We estimate a synthetic control model.")) is True
    assert a.gate(_ctx("This is a purely descriptive note with no estimator.")) is False


def test_dynamic_check_gated_off_by_default():
    a = DynamicCheckAttack()
    ctx = _ctx("We use a bunching estimator.", methods={"bunching"}, data_path="d.csv")
    assert a.gate(ctx) is False  # allow_code defaults False
    ctx2 = _ctx("We use a bunching estimator.", methods={"bunching"}, data_path="d.csv", allow_code=True)
    assert a.gate(ctx2) is True


def test_dynamic_check_denylist():
    assert _BANNED.search("import os; os.system('rm -rf /')")
    assert _BANNED.search("import requests")
    assert _BANNED.search("open('out.csv','w')")
    assert not _BANNED.search("import pandas as pd; df = pd.read_csv(path); print(df.mean())")


def test_branch_dedup_collapses_similar():
    from econoclast.agent.branches import _dedup

    f1 = Finding(attack="x", title="The sample period is cherry-picked", category="cherry_picking",
                 severity="high", detail="", confidence=0.6)
    f2 = Finding(attack="x", title="Sample period looks cherry picked", category="cherry_picking",
                 severity="high", detail="", confidence=0.8)
    f3 = Finding(attack="x", title="Weak instrument", category="identification",
                 severity="medium", detail="", confidence=0.5)
    kept = _dedup([f1, f2, f3])
    assert len(kept) == 2  # f1/f2 collapse, f3 distinct
    assert any(abs(f.confidence - 0.8) < 1e-9 for f in kept)  # higher-confidence rep kept
