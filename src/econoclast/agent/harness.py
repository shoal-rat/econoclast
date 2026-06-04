"""The orchestrator: load -> detect design -> gather literature -> attack -> synthesise.

This is a deliberately *bounded* pipeline rather than an open-ended ReAct loop:
the attack set is fixed and design-gated, every attack is grounded in the paper,
and the run is reproducible. Forensics run first (fast, offline); LLM attacks run
concurrently; the referee synthesises a verdict last.
"""

from __future__ import annotations

import concurrent.futures as cf
from datetime import datetime, timezone
from pathlib import Path

from econoclast.agent.referee import synthesize_referee
from econoclast.attacks.base import Attack, AttackContext, Finding
from econoclast.attacks.designs import design_label, detect_designs
from econoclast.attacks.registry import select_attacks
from econoclast.config import Settings
from econoclast.ingest.paper import load_paper
from econoclast.ingest.sanitize import normalize_for_match, quote_supported
from econoclast.literature import LiteratureSearcher
from econoclast.llm.router import ModelRouter
from econoclast.logging import get_logger
from econoclast.report.fragility import compute_fragility
from econoclast.report.models import Report
from econoclast.version import __version__

log = get_logger("agent")


class Econoclast:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        config_path: str | None = None,
        force_mock: bool = False,
    ) -> None:
        self.settings = settings or Settings.load(config_path)
        if force_mock:
            self.settings.offline = True
        self.router = ModelRouter(self.settings, force_mock=force_mock)
        self.searcher: LiteratureSearcher | None = None
        if self.settings.literature.enabled:
            self.searcher = LiteratureSearcher(self.settings.literature)

    # ------------------------------------------------------------------ api
    def review(
        self,
        paper_path: str | Path,
        *,
        attack_names: list[str] | None = None,
        use_llm: bool = True,
        use_literature: bool = True,
        blind: bool = True,
        ensemble: int = 1,
        deep: bool = False,
        allow_code: bool = False,
        data_path: str | None = None,
        comprehension: dict | None = None,
        replication_config: str | None = None,
        max_workers: int = 6,
        progress=None,
    ) -> Report:
        from econoclast.agent.comprehend import comprehend, merge_designs
        from econoclast.attacks.designs import detect_methods

        paper = load_paper(paper_path)
        designs = detect_designs(paper.text)
        methods = detect_methods(paper.text)

        # Let the model read the paper and decide, when one is available.
        comp = comprehension
        if comp is None and use_llm and self.router.is_live():
            if progress:
                progress("reading the paper")
            comp = comprehend(paper, self.router)
        if comp:
            designs = merge_designs(designs, comp)
        log.info("Design(s): %s | method(s): %s", design_label(designs), ", ".join(sorted(methods)) or "-")

        ctx = AttackContext(
            paper=paper,
            settings=self.settings,
            router=self.router,
            designs=designs,
            methods=methods,
            searcher=self.searcher if use_literature else None,
            blind=blind,
            ensemble=max(1, ensemble),
            deep=deep,
            allow_code=allow_code,
            data_path=data_path,
        )
        if comp:
            ctx.notes["comprehension"] = comp
        paper_norm = normalize_for_match(paper.text)

        if use_literature and self.searcher is not None:
            ctx.literature = self._gather_literature(paper, designs)
            ctx.methodology = self._gather_methodology(methods)

        include_llm = use_llm and self.router.is_live()
        attacks = select_attacks(attack_names, include_llm=True, include_forensic=True)

        run_names: list[str] = []
        skipped: list[str] = []
        forensic_attacks: list[Attack] = []
        concurrent_attacks: list[Attack] = []
        for a in attacks:
            if not a.gate(ctx):
                skipped.append(f"{a.name} (n/a)")
                continue
            if a.requires_llm and not include_llm:
                skipped.append(f"{a.name} (no LLM)")
                continue
            run_names.append(a.name)
            # Deterministic forensics run sequentially; LLM and network attacks
            # (e.g. citation-check) run together in the thread pool.
            (forensic_attacks if a.kind == "deterministic" else concurrent_attacks).append(a)

        findings: list[Finding] = []

        # Deterministic forensics first (fast, offline, ordered).
        for a in forensic_attacks:
            if progress:
                progress(f"forensic: {a.name}")
            findings.extend(self._safe_run(a, ctx))

        # LLM + network attacks concurrently.
        if concurrent_attacks:
            with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futs = {pool.submit(self._safe_run, a, ctx): a for a in concurrent_attacks}
                for fut in cf.as_completed(futs):
                    a = futs[fut]
                    if progress:
                        progress(f"attack: {a.name}")
                    findings.extend(_ground(fut.result(), paper_norm))

        # Surface possible prompt injection embedded in the manuscript.
        injections = paper.meta.get("injection_warnings") or []
        if injections:
            findings.append(Finding(
                attack="injection-scan",
                title="Possible prompt-injection text embedded in the manuscript",
                category="data_integrity",
                severity="high",
                confidence=0.8,
                detail="Text resembling instructions to a reviewer/LLM was found in the manuscript. "
                       "It was treated as untrusted data, but its presence is itself a red flag.",
                evidence=injections,
                recommendation="Inspect the manuscript source for hidden/white/zero-width text aimed at influencing an automated reviewer.",
            ))

        # Replication mode: re-estimate the result across a multiverse of specs.
        replication_summary = None
        if replication_config:
            if progress:
                progress("replication: running specification curve")
            try:
                from econoclast.replication import (
                    SpecConfig,
                    replication_findings,
                    run_replication,
                )

                rep = run_replication(SpecConfig.from_yaml(replication_config))
                findings.extend(replication_findings(rep))
                replication_summary = rep.get("spec_curve", {}).get("summary")
                ctx.notes["replication"] = rep
            except Exception as exc:  # noqa: BLE001
                log.warning("Replication failed: %s", exc)

        forensic_dicts = [r.to_dict() for r in _ordered(ctx.forensic_results)]
        fragility = compute_fragility(findings, forensic_dicts)
        referee = synthesize_referee(ctx, findings, fragility)

        report = Report(
            paper_title=paper.title,
            paper_path=str(paper.path),
            source_format=paper.source_format,
            designs=sorted(designs),
            n_claims=len(paper.claims),
            forensic_results=forensic_dicts,
            findings=findings,
            fragility=fragility,
            referee=referee,
            meta={
                "version": __version__,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "llm_live": include_llm,
                "blind_review": blind,
                "deep": deep,
                "methods": sorted(methods),
                "models": self._models_used() if include_llm else [],
                "usage": self.router.summary(),
                "attacks_run": run_names,
                "attacks_skipped": skipped,
                "n_literature": len(ctx.literature),
                "injection_warnings": len(injections),
                "replication": replication_summary,
            },
        )
        log.info("Review complete: fragility %s/100 (%s), %d findings",
                 fragility["score"], fragility["band"], len(findings))
        return report

    # ------------------------------------------------------------- verify
    def verify(
        self,
        source: str,
        *,
        data: str | None = None,
        use_llm: bool = True,
        use_literature: bool = True,
        blind: bool = True,
        deep: bool = False,
        allow_code: bool = False,
        max_workers: int = 6,
        progress=None,
    ) -> Report:
        """One-line verification: fetch the paper, find & download its dataset,
        auto-configure a specification curve, and run the whole review.

        Hand it a path or a URL. If you already have the data, pass ``data``.
        """
        from econoclast.ingest.fetch import resolve_source
        from econoclast.ingest.paper import load_paper

        paper_file = resolve_source(str(source), cache_dir=self.settings.cache_dir)
        paper = load_paper(paper_file)

        # Read the paper once with the model; reuse it for data discovery and the review.
        comp = None
        if use_llm and self.router.is_live():
            from econoclast.agent.comprehend import comprehend

            if progress:
                progress("reading the paper")
            comp = comprehend(paper, self.router)

        info = {"requested": True, "provided": bool(data), "found": bool(data),
                "source": "provided" if data else None, "autoconfig": False, "note": ""}
        data_path = data
        if not data_path:
            if progress:
                progress("looking for the paper's dataset")
            data_path, src = self._acquire_dataset(paper, comp, progress)
            info["found"] = bool(data_path)
            info["source"] = src

        spec_path = None
        if data_path:
            if progress:
                progress("auto-configuring the replication")
            from econoclast.agent.autoconfig import generate_spec_config

            cfg = generate_spec_config(paper, data_path, self.router)
            if cfg is not None:
                spec_path = str(self.settings.cache_path() / "auto_spec.yaml")
                Path(spec_path).write_text(cfg.to_yaml(), encoding="utf-8")
                info["autoconfig"] = True
            else:
                info["note"] = "Found data but could not auto-configure the replication (need a live model)."
        else:
            info["note"] = "No public dataset link found in the paper; ran forensics + critique only."

        report = self.review(
            paper_file, use_llm=use_llm, use_literature=use_literature, blind=blind,
            deep=deep, allow_code=allow_code, data_path=data_path, comprehension=comp,
            replication_config=spec_path, max_workers=max_workers, progress=progress,
        )
        report.meta["dataset"] = info
        return report

    def _acquire_dataset(self, paper, comp, progress) -> tuple[str | None, str | None]:
        from econoclast.replication.acquire import (
            acquire_dataset,
            find_tabular_files,
            pick_main_table,
        )
        from econoclast.replication.discover import DataLink, find_dataset_links

        # Prefer the data links the model found, then the keyword-detected ones.
        links = [DataLink(kind="direct", ref=u, url=u, score=3.0)
                 for u in (comp or {}).get("data_links", [])[:4]
                 if isinstance(u, str) and u.lower().startswith("http")]
        links += find_dataset_links(paper)
        if not links:
            return None, None
        work = self.settings.cache_path() / "data"
        for link in links[:5]:
            if progress:
                progress(f"fetching dataset: {link.kind} {link.ref[:40]}")
            try:
                files = acquire_dataset(link, work)
            except Exception as exc:  # noqa: BLE001
                log.warning("acquire failed for %s: %s", link.url, exc)
                continue
            main = pick_main_table(find_tabular_files(files), paper)
            if main is not None:
                log.info("Using dataset %s (from %s)", main.name, link.url)
                return str(main), link.url
        return None, None

    # -------------------------------------------------------------- helpers
    def _safe_run(self, attack: Attack, ctx: AttackContext) -> list[Finding]:
        try:
            return attack.run(ctx)
        except Exception as exc:  # noqa: BLE001 — one attack must not kill the run
            log.warning("attack '%s' raised: %s", attack.name, exc)
            return []

    def _gather_methodology(self, methods) -> dict[str, str]:
        """Retrieve each uncovered method's assumptions/diagnostics so the agent can
        verify against the literature instead of guessing."""
        if not self.searcher:
            return {}
        from econoclast.attacks.designs import method_coverage

        targets = method_coverage(methods)["needs_research"][:3]
        out: dict[str, str] = {}
        queries = {
            "synthetic_control": "synthetic control method identifying assumptions placebo inference",
            "bunching": "bunching estimator identification assumptions elasticity",
            "shift_share": "shift-share Bartik instrument identification assumptions exogeneity",
            "regression_kink": "regression kink design assumptions smoothness",
            "gmm": "GMM weak identification overidentification test assumptions",
            "ml_causal": "double machine learning causal forest assumptions inference",
            "structural": "structural demand estimation identification BLP instruments assumptions",
        }
        for m in targets:
            try:
                refs = self.searcher.search(queries.get(m, f"{m} econometrics identifying assumptions"), limit=4)
                blocks = "\n\n".join(r.context_block(max_abstract=400) for r in refs[:4])
                if blocks:
                    out[m] = blocks
            except Exception as exc:  # noqa: BLE001
                log.warning("methodology search for %s failed: %s", m, exc)
        if out:
            log.info("Retrieved methodology for: %s", ", ".join(out))
        return out

    def _gather_literature(self, paper, designs):
        topic = paper.title
        if paper.abstract:
            topic = f"{paper.title}. {paper.abstract[:300]}"
        try:
            refs = self.searcher.search(topic)
            log.info("Retrieved %d related works", len(refs))
            return refs
        except Exception as exc:  # noqa: BLE001
            log.warning("Literature search failed: %s", exc)
            return []

    def _models_used(self) -> list[str]:
        names = []
        for role in ("attacker", "referee", "extractor"):
            for ref in self.settings.models_for(role):
                tag = f"{ref.provider}:{ref.model}"
                if tag not in names:
                    names.append(tag)
        return names


def _ground(findings: list[Finding], paper_norm: str) -> list[Finding]:
    """Mechanical grounding gate: down-weight LLM findings whose quote isn't in the paper."""
    for f in findings:
        if not f.evidence:
            f.confidence = min(f.confidence, 0.4)
            continue
        if not any(quote_supported(paper_norm, q) for q in f.evidence):
            f.confidence = min(f.confidence, 0.3)
            f.data["quote_unverified"] = True
    return findings


_FORENSIC_ORDER = ["statcheck", "grim", "grimmer", "p-curve", "caliper", "tiva", "benford", "rounding"]


def _ordered(results):
    rank = {name: i for i, name in enumerate(_FORENSIC_ORDER)}
    return sorted(results, key=lambda r: rank.get(r.name, 99))
