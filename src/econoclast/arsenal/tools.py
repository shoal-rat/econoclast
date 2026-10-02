"""What the Sicarius carries: plain functions over a Case, wrapped as MCP tools in server.py.

Every tool does real work (reading, downloading, estimating) *and* leaves an event in the
case log, which is what moves the figures on the mosaic. Keeping them plain functions
means the tests can call them without an MCP transport.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from econoclast.case.models import Parry, Wound
from econoclast.case.score import compute_fragility
from econoclast.case.store import Case
from econoclast.log import get_logger
from econoclast.world import BLADE_KEYS, STATION_KEYS, blade

log = get_logger("arsenal")


class Arsenal:
    def __init__(self, case: Case) -> None:
        self.case = case
        self._paper = None

    # ------------------------------------------------------------ helpers
    def _resolve(self, path: str) -> Path:
        p = Path(path).expanduser()
        return p if p.is_absolute() else self.case.root / p

    def _rel(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.case.root.resolve()))
        except ValueError:
            return str(p)

    def paper(self):  # noqa: ANN201
        if self._paper is None:
            cached = self.case.path("paper", "source.txt")
            if cached.exists():
                self._paper = _load(cached.read_text(encoding="utf-8").strip())
        return self._paper

    # ------------------------------------------------------------- walk
    def proclaim(self, station: str, note: str = "") -> dict[str, Any]:
        from econoclast.arsenal.doctrine import STATION_ORDERS

        station = station.strip().lower()
        if station not in STATION_KEYS:
            return {"error": f"unknown station {station!r}; use one of {', '.join(STATION_KEYS)}"}
        self.case.emit("station", station=station, note=note[:400])
        self.case.update_meta(station=station)
        return {"station": station, "orders": STATION_ORDERS[station]}

    # ------------------------------------------------------------ classis
    def fetch_paper(self, url_or_doi: str) -> dict[str, Any]:
        from econoclast.tesserae.fetch import FetchBlocked, resolve_source

        try:
            local = resolve_source(url_or_doi.strip(), cache_dir=str(self.case.path("paper")))
        except FetchBlocked as exc:
            self.case.emit("acquired", what="paper", ok=False, note=str(exc)[:300])
            return {"ok": False, "blocked": True, "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            self.case.emit("acquired", what="paper", ok=False, note=str(exc)[:300])
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        p = Path(local)
        kind = p.suffix.lower().lstrip(".")
        self.case.emit("acquired", what="paper", ok=True, file=self._rel(p), filetype=kind)
        hint = ("This is the text of a landing page, not the paper: check it, then get the PDF."
                if kind == "txt" else "Now read_paper(path).")
        return {"ok": True, "path": self._rel(p), "kind": kind, "next": hint}

    # -------------------------------------------------------- scriptorium
    def read_paper(self, path: str) -> dict[str, Any]:
        from econoclast.bibliotheca.datalinks import find_dataset_links
        from econoclast.tesserae.designs import detect_designs, detect_methods

        src = self._resolve(path)
        paper = _load(str(src))
        self._paper = paper
        self.case.path("paper", "source.txt").write_text(str(src), encoding="utf-8")
        self.case.path("paper", "paper.txt").write_text(paper.text, encoding="utf-8")
        designs = sorted(detect_designs(paper.text))
        methods = sorted(detect_methods(paper.text))
        links = [{"kind": d.kind, "url": d.url, "context": d.context} for d in find_dataset_links(paper)[:8]]
        injections = paper.meta.get("injection_warnings") or []
        outline = [{"i": i, "name": s.name, "chars": len(s.text)} for i, s in enumerate(paper.sections)]
        self.case.update_meta(title=paper.title)
        self.case.emit("intel", about="paper", title=paper.title, abstract=paper.abstract[:900],
                       designs=designs, methods=methods, n_stats=len(paper.claims),
                       n_tables=len(paper.tables), n_sections=len(paper.sections),
                       n_pages=paper.meta.get("n_pages"), n_chars=len(paper.text),
                       data_links=[link["url"] for link in links], injections=len(injections))
        return {
            "title": paper.title,
            "abstract": paper.abstract[:2000],
            "full_text": "paper/paper.txt",
            "outline": outline,
            "designs_detected": designs,
            "methods_detected": methods,
            "n_statistics_extracted": len(paper.claims),
            "sample_statistics": [c.short() for c in paper.claims[:25]],
            "data_links_in_text": links,
            "hidden_instructions_found": injections,
            "next": "Read paper/paper.txt for the claim-bearing sections, then mark_target(...).",
        }

    def paper_section(self, index: int) -> dict[str, Any]:
        paper = self.paper()
        if paper is None:
            return {"error": "read_paper first"}
        if not 0 <= index < len(paper.sections):
            return {"error": f"index out of range (0..{len(paper.sections) - 1})"}
        s = paper.sections[index]
        return {"name": s.name, "text": s.text[:30000]}

    def mark_target(self, claim: str, design: str = "", table: str = "", coefficient: float | None = None,
                    std_error: float | None = None, outcome: str = "", treatment: str = "",
                    sample: str = "", estimator: str = "", data_availability: str = "",
                    paper_title: str = "") -> dict[str, Any]:
        if paper_title.strip():
            self.case.update_meta(title=paper_title.strip()[:300])
        tgt = {k: v for k, v in {
            "claim": claim, "paper_title": paper_title.strip(), "design": design, "table": table, "coefficient": coefficient,
            "std_error": std_error, "outcome": outcome, "treatment": treatment, "sample": sample,
            "estimator": estimator, "data_availability": data_availability}.items() if v not in ("", None)}
        self.case.emit("intel", about="target", **tgt)
        self.case.update_meta(target=claim[:300])
        return {"recorded": True, "target": tgt}

    def verify_quote(self, quote: str) -> dict[str, Any]:
        from econoclast.tesserae.sanitize import normalize_for_match, quote_supported

        paper = self.paper()
        if paper is None:
            return {"error": "read_paper first"}
        norm = normalize_for_match(paper.text)
        found = quote_supported(norm, quote)
        out: dict[str, Any] = {"found": found}
        if not found:
            out["closest"] = _closest(paper.text, quote)
            out["advice"] = "Copy the sentence exactly from paper/paper.txt (PDF line breaks are fine)."
        return out

    def abacus(self) -> dict[str, Any]:
        from econoclast.tesserae.abacus import check

        paper = self.paper()
        if paper is None:
            return {"error": "read_paper first"}
        flags = check(paper.claims)
        self.case.emit("intel", about="abacus", n_checked=len(paper.claims), n_flags=len(flags))
        return {"checked": len(paper.claims), "flags": flags[:40],
                "next": "Judge each flag in context: inflict an abacus wound or parry('abacus', ...)."}

    # ----------------------------------------------------- integrity (falsum, fucus, palimpsestus)
    def forensics_paper(self) -> dict[str, Any]:
        from econoclast.tesserae.forensics import abstract_numbers, scan

        paper = self.paper()
        if paper is None:
            return {"error": "read_paper first"}
        res = scan(paper.claims, paper.text)
        body = paper.text.replace(paper.abstract, "") if paper.abstract else paper.text
        res["abstract_numbers"] = abstract_numbers(paper.abstract or paper.text[:2500], body)
        self._save("forensics_paper.json", res)
        self.case.emit("intel", about="forensics", scope="paper", n_flags=len(res["flags"]),
                       tests=[f["test"] for f in res["flags"]],
                       abstract_missing=len(res["abstract_numbers"]["not_in_body"]))
        res["artifact"] = "out/forensics_paper.json"
        res["next"] = ("Judge each flag in context. Real fabrication signals -> falsum wound (computation, cite "
                       "the artifact); abstract numbers no table supports -> fucus; otherwise parry.")
        return res

    def forensics_data(self, path: str, treatment: str = "", covariates: list[str] | None = None,
                       id_columns: list[str] | None = None, columns: list[str] | None = None) -> dict[str, Any]:
        from econoclast.viae.forensics import scan
        from econoclast.viae.io import load_table

        p = self._resolve(path)
        try:
            df = load_table(str(p))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        res = scan(df, treatment=treatment, covariates=covariates or [], id_cols=id_columns or [],
                   columns=columns)
        name = f"forensics_data_{p.stem}.json"
        self._save(name, res)
        self.case.emit("intel", about="forensics", scope="data", file=self._rel(p), n_flags=len(res["flags"]),
                       tests=[f["test"] for f in res["flags"]])
        res["artifact"] = f"out/{name}"
        res["next"] = ("A flag is a question, not a verdict: look at the rows behind it. Inflict falsum only for "
                       "patterns an innocent process cannot explain; cite the artifact.")
        return res

    def compare_versions(self, earlier: str, later: str, earlier_label: str = "earlier",
                         later_label: str = "later") -> dict[str, Any]:
        from econoclast.tesserae.versions import compare

        texts = []
        for src in (earlier, later):
            p = self._resolve(src)
            if p.suffix.lower() in (".pdf", ".tex", ".html", ".htm") or not p.suffix:
                texts.append(_load(str(p)).text)
            else:
                texts.append(p.read_text(encoding="utf-8", errors="replace"))
        res = compare(texts[0], texts[1], old_label=earlier_label, new_label=later_label)
        self._save("versions.json", res)
        self.case.emit("intel", about="versions", earlier=earlier_label, later=later_label,
                       rewritten=len(res["rewritten"]), removed=len(res["removed"]), added=len(res["added"]),
                       estimates_changed=len(res["estimates_only_in_old"]))
        res["artifact"] = "out/versions.json"
        res["next"] = ("Changes are normal. Look for undisclosed ones that favour the headline: a switched primary "
                       "outcome, a dropped null, a new sample cut, a rewritten hypothesis -> palimpsestus wound.")
        return res

    def audit_code(self, folder: str = "data") -> dict[str, Any]:
        from econoclast.bibliotheca.codeaudit import audit

        res = audit(self._resolve(folder))
        self._save("code_audit.json", res)
        self.case.emit("intel", about="code", n_files=res["n_files"], n_steps=len(res["steps"]),
                       by_kind=res["by_kind"])
        res["artifact"] = "out/code_audit.json"
        res["next"] = ("Compare every drop/filter/recode/trim step with the paper's own description. An "
                       "undisclosed step that moves the headline is a speculum wound; quote the code line.")
        return res

    def _save(self, name: str, obj: Any) -> None:
        self.case.path("out").mkdir(exist_ok=True)
        self.case.path("out", name).write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str),
                                               encoding="utf-8")

    # ------------------------------------------------------- bibliotheca
    def search_literature(self, query: str, limit: int = 8) -> dict[str, Any]:
        from econoclast.bibliotheca.literature import LiteratureSearcher

        refs = LiteratureSearcher().search(query, limit=max(1, min(limit, 20)))
        self.case.emit("intel", about="literature", query=query[:200], n=len(refs))
        return {"results": [{"title": r.title, "authors": r.authors[:4], "year": r.year,
                             "venue": r.venue, "doi": r.doi, "url": r.url, "citations": r.citations,
                             "abstract": r.abstract[:700]} for r in refs]}

    def check_references(self, limit: int = 30) -> dict[str, Any]:
        from econoclast.tesserae.references import extract_references, verify_references

        paper = self.paper()
        if paper is None:
            return {"error": "read_paper first"}
        refs = paper.references or extract_references(paper)
        checks = verify_references(refs, max_refs=max(1, min(limit, 60)))
        bad = [c for c in checks if not c.resolved]
        self.case.emit("intel", about="references", n=len(checks), unresolved=len(bad))
        return {"checked": len(checks),
                "unresolved": [{"reference": c.text[:300], "best_match": c.matched_title, "score": c.score,
                                "reason": c.reason} for c in bad[:25]],
                "note": "Unresolved is not fabricated: books and working papers often lack DOIs."}

    # -------------------------------------------------------------- forum
    def field_notes(self, field: str, setting: str, actors: list[str] | None = None,
                    claimed_mechanism: str = "", real_mechanism: str = "", institutions: str = "",
                    magnitudes: str = "", theory: str = "", theory_assumptions: list[str] | None = None,
                    rival_explanations: list[str] | None = None, sources: list[str] | None = None) -> dict[str, Any]:
        notes = {"field": field.strip(), "setting": setting.strip(), "actors": list(actors or []),
                 "claimed_mechanism": claimed_mechanism.strip(), "real_mechanism": real_mechanism.strip(),
                 "institutions": institutions.strip(), "magnitudes": magnitudes.strip(), "theory": theory.strip(),
                 "theory_assumptions": list(theory_assumptions or []),
                 "rival_explanations": list(rival_explanations or []), "sources": list(sources or [])}
        d = self.case.path("notes")
        d.mkdir(exist_ok=True)
        (d / "field.json").write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
        md = [f"# {notes['field']}", "", notes["setting"], ""]
        for key, title in (("claimed_mechanism", "Mechanism the paper claims"), ("real_mechanism",
                           "How the real actors behave"), ("institutions", "Institutions and timing"),
                           ("magnitudes", "Magnitudes"), ("theory", "Theory")):
            if notes[key]:
                md += [f"## {title}", "", notes[key], ""]
        for key, title in (("actors", "Actors"), ("theory_assumptions", "Theory's key assumptions"),
                           ("rival_explanations", "Rival explanations"), ("sources", "Sources")):
            if notes[key]:
                md += [f"## {title}", ""] + [f"- {x}" for x in notes[key]] + [""]
        (d / "field.md").write_text("\n".join(md), encoding="utf-8")
        self.case.emit("intel", about="field", field=notes["field"], setting=notes["setting"][:300],
                       actors=notes["actors"][:8], rivals=len(notes["rival_explanations"]),
                       n_sources=len(notes["sources"]))
        return {"recorded": "notes/field.md",
                "next": "Now swing inversio, theoria, novacula and mundus against the paper, each a wound or a parry."}

    def novacula(self, data: str, outcome: str, simple_terms: list[str], extra_terms: list[str],
                 cluster: str = "", folds: int = 5) -> dict[str, Any]:
        """Occam's razor on the data: what does the paper's extra machinery buy over the plain model?"""
        from econoclast.viae.razor import compare_models

        try:
            res = compare_models(str(self._resolve(data)), outcome, simple_terms, extra_terms,
                                 cluster=cluster, folds=folds)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        self._save("novacula.json", res)
        self.case.emit("intel", about="razor", verdict=res["verdict"], extra=len(extra_terms),
                       delta_bic=res["delta_bic"], cv_gain=res["cv_rmse_gain"])
        res["artifact"] = "out/novacula.json"
        res["next"] = ("If the extra terms add little (BIC prefers the plain model, no out-of-sample gain), the "
                       "theory's machinery is not doing work: a novacula computation wound citing the artifact. "
                       "If they earn their keep, parry novacula.")
        return res

    # ------------------------------------------------------------ horreum
    def find_data_links(self) -> dict[str, Any]:
        from econoclast.bibliotheca.datalinks import find_dataset_links

        paper = self.paper()
        if paper is None:
            return {"error": "read_paper first"}
        links = find_dataset_links(paper)
        return {"links": [{"kind": d.kind, "ref": d.ref, "url": d.url, "context": d.context,
                           "needs_login": not d.supported} for d in links[:12]]}

    def fetch_dataset(self, url: str) -> dict[str, Any]:
        from econoclast.bibliotheca.acquire import acquire_dataset, tabular_files
        from econoclast.bibliotheca.datalinks import DataLink, classify_url

        kind, ref = classify_url(url)
        link = DataLink(kind=kind, ref=ref, url=url, supported=kind != "icpsr")
        try:
            files = acquire_dataset(link, self.case.path("data"))
        except Exception as exc:  # noqa: BLE001
            self.case.emit("acquired", what="data", ok=False, url=url, note=str(exc)[:300])
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}",
                    "next": "Try your browser or curl with cookies, another mirror, or plea the traveller."}
        tables = tabular_files(files)
        self.case.emit("acquired", what="data", ok=True, url=url, n_files=len(files),
                       tables=[self._rel(t) for t in tables[:12]])
        return {"ok": True, "files": [self._rel(f) for f in files[:80]],
                "tables": [self._rel(t) for t in tables[:30]], "n_files": len(files)}

    def public_series(self, source: str, series: str, countries: str = "all", start: str = "",
                      end: str = "") -> dict[str, Any]:
        from econoclast.bibliotheca.public import fred_series, worldbank_indicator

        dest = self.case.path("data", "public")
        try:
            if source.lower() == "fred":
                out = fred_series(series, dest, start=start, end=end)
            elif source.lower() in ("worldbank", "world_bank", "wb"):
                out = worldbank_indicator(series, dest, countries=countries, start=start, end=end)
            else:
                return {"ok": False, "message": "source must be 'fred' or 'worldbank'"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        self.case.emit("acquired", what="data", ok=True, url=f"{source}:{series}", n_files=1,
                       tables=[self._rel(out)])
        return {"ok": True, "path": self._rel(out)}

    def inspect_dataset(self, path: str) -> dict[str, Any]:
        from econoclast.viae.io import load_table

        p = self._resolve(path)
        try:
            df = load_table(str(p))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
        cols = []
        for c in list(df.columns)[:120]:
            s = df[c]
            entry: dict[str, Any] = {"name": str(c), "dtype": str(s.dtype),
                                     "missing": round(float(s.isna().mean()), 3),
                                     "unique": int(s.nunique(dropna=True))}
            if entry["unique"] <= 12:
                entry["values"] = [str(v) for v in s.dropna().unique()[:12]]
            elif str(s.dtype).startswith(("int", "float")):
                d = s.describe()
                entry.update({"mean": _f(d.get("mean")), "min": _f(d.get("min")), "max": _f(d.get("max"))})
            cols.append(entry)
        labels = {}
        if p.suffix.lower() == ".dta":
            try:
                import pandas as pd

                with pd.io.stata.StataReader(str(p)) as rd:
                    labels = {k: v for k, v in rd.variable_labels().items() if v}
            except Exception:  # noqa: BLE001
                labels = {}
        self.case.emit("intel", about="dataset", file=self._rel(p), rows=int(len(df)), cols=int(df.shape[1]))
        return {"ok": True, "path": self._rel(p), "rows": int(len(df)), "n_columns": int(df.shape[1]),
                "columns": cols, "variable_labels": dict(list(labels.items())[:120]),
                "head": df.head(5).to_dict(orient="records")}

    # ------------------------------------------------------------ fabrica
    def fabrica_build(self, extra_packages: list[str] | None = None) -> dict[str, Any]:
        from econoclast import fabrica

        self.case.emit("forge", step="build", status="start", extra=extra_packages or [])
        res = fabrica.build(extra_packages)
        self.case.emit("forge", step="build", status="done", ok=res["ready"], seconds=res["seconds"],
                       missing=res["missing"])
        res["how_to_run"] = ("Write scripts under code/ and run them with fabrica_run('code/x.py'), or "
                             f"directly with {res['python']}.")
        return res

    def fabrica_run(self, script: str, timeout_sec: int = 900, args: list[str] | None = None) -> dict[str, Any]:
        from econoclast import fabrica

        self.case.emit("forge", step="run", status="start", script=script)
        res = fabrica.run_script(script, cwd=self.case.root, timeout=float(timeout_sec), args=args)
        self.case.emit("forge", step="run", status="done", script=script, ok=res.get("ok", False),
                       seconds=res.get("seconds"), new_files=res.get("new_files", [])[:10])
        return res

    def reproduce(self, what: str, paper_value: float, reproduced_value: float,
                  paper_se: float | None = None, reproduced_se: float | None = None,
                  script: str = "", note: str = "") -> dict[str, Any]:
        gap = reproduced_value - paper_value
        rel = abs(gap) / max(abs(paper_value), 1e-12)
        same_sign = (paper_value >= 0) == (reproduced_value >= 0)
        if rel <= 0.02:
            verdict = "match"
        elif rel <= 0.15 and same_sign:
            verdict = "close"
        else:
            verdict = "mismatch"
        rec = {"what": what, "paper_value": paper_value, "reproduced_value": reproduced_value,
               "paper_se": paper_se, "reproduced_se": reproduced_se, "relative_gap": round(rel, 4),
               "same_sign": same_sign, "verdict": verdict, "script": script, "note": note[:400]}
        self.case.emit("speculum", **rec)
        nxt = {"match": "Record parry('speculum', ...).",
               "close": "Explain the small gap (rounding, sample, version); parry or a low speculum wound.",
               "mismatch": "Before wounding, check sample, weights, clustering and data vintage. If the "
                           "gap survives, inflict a speculum computation wound citing the script."}
        rec["next"] = nxt[verdict]
        return rec

    # --------------------------------------------------------------- aula
    def mille_viae(self, spec: dict[str, Any]) -> dict[str, Any]:
        from econoclast.viae import SpecConfig, run_replication, viae_wounds
        from econoclast.viae.models import SpecCurve
        from econoclast.viae.plot import plot_spec_curve

        spec = dict(spec)
        spec["data"] = str(self._resolve(str(spec.get("data", ""))))
        self.case.emit("viae", status="start", outcome=spec.get("outcome"), treatment=spec.get("treatment"))
        try:
            cfg = SpecConfig.from_dict(spec)
            result = run_replication(cfg)
        except Exception as exc:  # noqa: BLE001
            self.case.emit("viae", status="failed", note=str(exc)[:300])
            return {"ok": False, "message": f"{type(exc).__name__}: {exc}",
                    "next": "Fix the spec (column names, filters) and call mille_viae again."}
        out_dir = self.case.path("out")
        (out_dir / "viae.json").write_text(json.dumps(result, default=str, indent=1), encoding="utf-8")
        curve = SpecCurve.from_dict(result["spec_curve"])
        png = plot_spec_curve(curve, str(out_dir / "spec_curve.png"))
        wounds = viae_wounds(result, artifact="out/viae.json")
        for w in wounds:
            self._record(w, verified=None)
        summary = result["spec_curve"]["summary"]
        points = sorted(result["spec_curve"]["results"], key=lambda r: r["coef"])
        step = max(1, len(points) // 400)
        pts = [{"c": r["coef"], "se": r["se"], "p": r["p"]} for r in points[::step]]
        pref = result["spec_curve"].get("preferred") or {}
        design = {k: v for k, v in result.items() if k != "spec_curve"}
        self.case.emit("viae", status="done", summary=summary, points=pts,
                       preferred={"c": pref.get("coef"), "se": pref.get("se"), "p": pref.get("p")},
                       design_checks=sorted(design), n_wounds=len(wounds))
        return {"ok": True, "summary": summary, "design_checks": _brief_design(design),
                "plot": self._rel(Path(png)) if png else None,
                "wounds_recorded": [w.title for w in wounds],
                "next": ("These computed wounds are recorded. Add your own judgement on top; if the curve "
                         "holds, parry('mille_viae', ...).") if wounds else
                        "The result holds across the roads: parry('mille_viae', note=...)."}

    # ------------------------------------------------------------ wounds
    def inflict_wound(self, blade_key: str, title: str, severity: str, detail: str,
                      confidence: float = 0.6, quote: str = "", location: str = "", remedy: str = "",
                      evidence_kind: str = "text", artifacts: list[str] | None = None) -> dict[str, Any]:
        if blade_key not in BLADE_KEYS:
            return {"error": f"unknown blade {blade_key!r}; use one of {', '.join(BLADE_KEYS)}"}
        w = Wound(blade=blade_key, title=title, severity=severity, detail=detail, confidence=confidence,
                  quote=quote, location=location, remedy=remedy, evidence_kind=evidence_kind,
                  artifacts=list(artifacts or []))
        verified = None
        if w.quote.strip():
            verified = bool(self.verify_quote(w.quote).get("found")) if self.paper() is not None else None
        if w.evidence_kind == "computation":
            missing = [a for a in w.artifacts if not self._resolve(a).exists()]
            if missing:
                return {"error": f"artifacts not found: {missing}. Point at files you actually produced."}
        self._record(w, verified=verified)
        score = compute_fragility(self.case.wounds())
        out: dict[str, Any] = {"id": w.id, "verified": w.verified,
                               "effective_confidence": round(w.effective_confidence, 2),
                               "running_score": score["score"], "running_band": score["band_en"]}
        if verified is False:
            out["warning"] = ("The quote is not in the paper, so this wound counts for little. "
                              "Re-inflict with an exact quote if you can find one.")
        return out

    def _record(self, w: Wound, *, verified: bool | None) -> None:
        w.verified = verified if w.evidence_kind == "text" else (True if w.artifacts else None)
        b = blade(w.blade)
        self.case.emit("wound", wound=w.to_dict(), blade_latin=b.latin if b else w.blade)

    def parry(self, blade_key: str, note: str, quote: str = "") -> dict[str, Any]:
        if blade_key not in BLADE_KEYS:
            return {"error": f"unknown blade {blade_key!r}; use one of {', '.join(BLADE_KEYS)}"}
        p = Parry(blade=blade_key, note=note[:600], quote=quote[:400])
        self.case.emit("parry", parry=p.to_dict())
        return {"recorded": True}

    # ------------------------------------------------------------- plea
    def plea_open(self, what: str, why: str, accept: str = "file", where: str = "") -> str:
        plea_id = uuid.uuid4().hex[:8]
        self.case.emit("plea", plea_id=plea_id, what=what[:300], why=why[:600], accept=accept, where=where[:400])
        self.case.update_meta(waiting_plea=plea_id)
        return plea_id

    def plea_poll(self, plea_id: str) -> dict[str, Any] | None:
        path = self.case.offering_path(plea_id)
        if not path.exists():
            return None
        try:
            ans = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        self.case.update_meta(waiting_plea=None)
        ans["files"] = [self._rel(Path(f)) for f in ans.get("files", [])]
        return ans

    def plea_timeout(self, plea_id: str) -> dict[str, Any]:
        self.case.emit("plea.answered", plea_id=plea_id, timeout=True)
        self.case.update_meta(waiting_plea=None)
        return {"status": "timeout", "next": "No answer. Continue with what you have and say so in the verdict."}

    # ----------------------------------------------------------- verdict
    def pronounce_verdict(self, headline: str, assessment: str, change_my_mind: str,
                          survived: list[str] | None = None) -> dict[str, Any]:
        from econoclast.case.tabula import write_tabula

        wounds = self.case.wounds()
        frag = compute_fragility(wounds)
        verdict = {
            "fragility": frag,
            "headline": headline.strip(),
            "assessment": assessment.strip(),
            "change_my_mind": change_my_mind.strip(),
            "survived": [s for s in (survived or []) if s],
            "n_parries": len(self.case.parries()),
            "pronounced": time.time(),
        }
        self.case.path("verdict.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        files = write_tabula(self.case)
        self.case.emit("verdict", verdict=verdict)
        return {"score": frag["score"], "band": frag["band_en"], "latin": frag["band_latin"],
                "report": files, "next": "Write your final message for the traveller."}


# ---------------------------------------------------------------- helpers
def _load(path: str):  # noqa: ANN202
    from econoclast.tesserae.paper import load_paper

    return load_paper(path)


def _f(x: Any) -> float | None:
    try:
        v = float(x)
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _closest(text: str, quote: str, window: int = 220) -> str:
    """The stretch of the paper sharing the most words with the quote (a hint, not a match)."""
    import re

    words = [w for w in re.findall(r"[a-z0-9]{4,}", quote.lower())][:12]
    if not words:
        return ""
    low = text.lower()
    best, best_hits = 0, -1
    for m in re.finditer(re.escape(words[0]), low):
        seg = low[max(0, m.start() - 40): m.start() + window]
        hits = sum(1 for w in words if w in seg)
        if hits > best_hits:
            best, best_hits = m.start(), hits
    return re.sub(r"\s+", " ", text[max(0, best - 40): best + window]).strip() if best_hits > 0 else ""


def _brief_design(design: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in design.items():
        if isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in v.items() if not isinstance(vv, (list, dict))}
    return out
