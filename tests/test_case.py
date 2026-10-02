"""The case on disk: events, wounds, the score and the report."""

from __future__ import annotations

import json

from econoclast import world
from econoclast.case import Case, Wound, compute_fragility, list_cases
from econoclast.case.tabula import write_tabula


def test_world_lexicon_is_consistent():
    d = world.as_dict()
    assert [s["key"] for s in d["stations"]] == ["classis", "scriptorium", "forum", "horreum", "fabrica",
                                                 "palatium", "aula", "curia"]
    assert len(d["blades"]) == 17 and all(b["zh"] and b["latin"] for b in d["blades"])
    assert [x["key"] for x in d["seals"]] == ["integrum", "dubium", "fractum"]
    assert {"inversio", "theoria", "novacula", "mundus"} <= {b["key"] for b in d["blades"]}
    assert world.band_for(0).key == "stat"
    assert world.band_for(50).key == "vulneratus"
    assert world.band_for(99.9).key == "cecidit"


def test_events_round_trip_and_derived_views():
    case = Case.create(paper="https://arxiv.org/abs/1234.5678", lang="zh")
    case.emit("station", station="classis")
    w = Wound(blade="persona", title="Parallel trends untested", severity="high", detail="d",
              quote="We estimate", verified=True, confidence=0.8)
    case.emit("wound", wound=w.to_dict())
    case.emit("parry", parry={"blade": "tuba", "note": "claims are modest"})
    evs = case.events()
    assert [e["seq"] for e in evs] == [0, 1, 2]
    assert case.events(2)[0]["kind"] == "parry"
    assert case.wounds()[0].title == "Parallel trends untested"
    assert case.parries()[0].blade == "tuba"
    assert list_cases()[0]["id"] == case.id
    assert case.meta()["lang"] == "zh"


def test_grounding_gate_discounts_ungrounded_wounds():
    grounded = Wound(blade="persona", title="a", severity="high", detail="", quote="x" * 20,
                     verified=True, confidence=0.9)
    unquoted = Wound(blade="persona", title="b", severity="high", detail="", confidence=0.9)
    fake = Wound(blade="persona", title="c", severity="high", detail="", quote="y" * 20,
                 verified=False, confidence=0.9)
    computed_no_artifact = Wound(blade="mille_viae", title="d", severity="high", detail="",
                                 evidence_kind="computation", confidence=0.9)
    assert grounded.effective_confidence == 0.9
    assert unquoted.effective_confidence == 0.4
    assert fake.effective_confidence == 0.3
    assert computed_no_artifact.effective_confidence == 0.5


def test_fragility_saturates_and_integrity_floor():
    scratches = [Wound(blade="tuba", title=f"s{i}", severity="low", detail="", quote="q" * 20,
                       verified=True, confidence=0.5) for i in range(4)]
    assert compute_fragility(scratches)["band"] in ("stat", "laesus")
    deep = [Wound(blade="speculum", title="does not reproduce", severity="critical", detail="",
                  evidence_kind="computation", artifacts=["out/x.txt"], confidence=0.9)]
    f = compute_fragility(deep)
    assert f["integrity"] is True and f["score"] >= 45
    many = [Wound(blade="persona", title=f"w{i}", severity="critical", detail="", quote="q" * 20,
                  verified=True, confidence=1) for i in range(10)]
    assert compute_fragility(many)["score"] <= 100


def test_tabula_written_in_both_languages():
    for lang in ("en", "zh"):
        case = Case.create(paper="p", lang=lang)
        case.emit("wound", wound=Wound(blade="labyrinthus", title="Forking paths", severity="medium",
                                       detail="many specs", quote="We estimate a model",
                                       verified=True).to_dict())
        case.path("verdict.json").write_text(json.dumps({
            "fragility": compute_fragility(case.wounds()), "headline": "Shaky.",
            "assessment": "a", "change_my_mind": "b", "survived": ["c"]}))
        files = write_tabula(case)
        html = case.path(files["html"]).read_text()
        md = case.path(files["markdown"]).read_text()
        assert "Forking paths" in html and "Labyrinthus" in html
        assert ("伤口" in md) == (lang == "zh")


def test_seal_reads_integrity_wounds():
    ok = compute_fragility([Wound(blade="tuba", title="t", severity="high", detail="", quote="q" * 20,
                                  verified=True, confidence=0.9)])
    assert ok["seal"] == "integrum"
    spin = compute_fragility([Wound(blade="fucus", title="t", severity="medium", detail="", quote="q" * 20,
                                    verified=True)])
    assert spin["seal"] == "dubium"
    forged = compute_fragility([Wound(blade="falsum", title="dup rows", severity="high", detail="",
                                      evidence_kind="computation", artifacts=["out/f.json"], confidence=0.8)])
    assert forged["seal"] == "fractum" and forged["score"] >= 45


def test_vault_packs_heavy_files_and_restores_them():
    from econoclast.case.vault import pack, unpack

    case = Case.create(paper="p")
    big = case.path("data", "pkg", "panel.csv")
    big.parent.mkdir(parents=True)
    big.write_text("a,b\n" + "1,2\n" * 300000)
    case.path("out", "viae.json").write_text("{}")
    case.path("paper", "paper.txt").write_text("text")
    case.path("agent.log").write_text("x" * 600000)
    case.path("tabula.html").write_text("<html>")
    venv = case.path(".venv", "lib", "site-packages", "numpy")
    venv.mkdir(parents=True)
    (venv / "core.so").write_bytes(b"0" * 300000)
    case.path("scratch").mkdir()
    case.path("scratch", "tmp.csv").write_text("a\n1\n")
    before = big.stat().st_size
    res = pack(case)
    assert res["packed"] == 3 and res["after_bytes"] < before / 10
    assert not case.path(".venv").exists() and [r["path"] for r in res["removed"]] == [".venv"]
    assert not case.path("scratch", "tmp.csv").exists()
    assert not big.exists() and not case.path("agent.log").exists()
    assert case.path("out", "viae.json").exists() and case.path("paper", "paper.txt").exists()
    assert case.path("tabula.html").exists() and case.path("vault.tar.xz").exists()
    assert [e for e in case.events() if e["kind"] == "packed"]
    assert unpack(case) == 3 and big.stat().st_size == before and not case.path("vault.tar.xz").exists()


def test_score_follows_depth_not_count():
    def w(sev, i):
        return Wound(blade="persona", title=f"{sev}{i}", severity=sev, detail="", quote="q" * 20, verified=True,
                     confidence=0.8)
    many_medium = compute_fragility([w("medium", i) for i in range(12)])
    one_high = compute_fragility([w("high", 0)])
    three_crit = compute_fragility([w("critical", i) for i in range(3)] + [w("high", i) for i in range(3)])
    assert many_medium["band"] in ("laesus", "vulneratus")        # a pile of mediums does not fell anyone
    assert one_high["band"] == "laesus"
    assert three_crit["band"] in ("moribundus", "cecidit") and three_crit["score"] > many_medium["score"] + 15
