"""The orchestrator: load -> read -> gather literature -> attack -> synthesise.

This is a deliberately *bounded* pipeline rather than an open-ended ReAct loop:
the attack set is fixed and design-gated, every attack is grounded in the paper,
and the run is reproducible. The model reads the paper, the LLM attacks run
concurrently, and the referee synthesises a verdict last.
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
from econoclast.llm.backend import Backend, detect_backend
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
        backend: Backend | None = None,
    ) -> None:
        self.settings = settings or Settings.load(config_path)
        # `backend` injection is for tests; normally we find Claude Code or Codex.
        self.backend = backend or detect_backend(self.settings)
        self.searcher: LiteratureSearcher | None = None
        if self.settings.literature.enabled:
            self.searcher = LiteratureSearcher(self.settings.literature)

    # ------------------------------------------------------------------ api
    def review(
        self,
        paper_path: str | Path,
        *,
        attack_names: list[str] | None = None,
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

        # The model reads the paper and decides design, methods, claim, and data.
        comp = comprehension
        if comp is None:
            if progress:
                progress("reading the paper")
            comp = comprehend(paper, self.backend)
        if comp:
            designs = merge_designs(designs, comp)
        log.info("Design(s): %s | method(s): %s", design_label(designs), ", ".join(sorted(methods)) or "-")

        ctx = AttackContext(
            paper=paper,
            settings=self.settings,
            backend=self.backend,
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

        run_names: list[str] = []
        skipped: list[str] = []
        to_run: list[Attack] = []
        for a in select_attacks(attack_names):
            if not a.gate(ctx):
                skipped.append(f"{a.name} (n/a)")
                continue
            run_names.append(a.name)
            to_run.append(a)

        findings: list[Finding] = []
        if to_run:
            with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futs = {pool.submit(self._safe_run, a, ctx): a for a in to_run}
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

        fragility = compute_fragility(findings)
        referee = synthesize_referee(ctx, findings, fragility)

        report = Report(
            paper_title=paper.title,
            paper_path=str(paper.path),
            source_format=paper.source_format,
            designs=sorted(designs),
            n_claims=len(paper.claims),
            findings=findings,
            fragility=fragility,
            referee=referee,
            meta={
                "version": __version__,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "backend": self.backend.label,
                "blind_review": blind,
                "deep": deep,
                "methods": sorted(methods),
                "usage": self.backend.summary(),
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
        from econoclast.agent.comprehend import comprehend
        from econoclast.ingest.fetch import resolve_source
        from econoclast.ingest.paper import load_paper

        paper_file = resolve_source(str(source), cache_dir=self.settings.cache_dir, backend=self.backend)
        paper = load_paper(paper_file)

        # Read the paper once with the model; reuse it for data discovery and the review.
        if progress:
            progress("reading the paper")
        comp = comprehend(paper, self.backend)

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

            cfg = generate_spec_config(paper, data_path, self.backend)
            if cfg is not None:
                spec_path = str(self.settings.cache_path() / "auto_spec.yaml")
                Path(spec_path).write_text(cfg.to_yaml(), encoding="utf-8")
                info["autoconfig"] = True
            else:
                info["note"] = "Found data but could not map its columns to the paper's specification."
        else:
            info["note"] = "No public dataset link found in the paper; ran the critique on the text only."

        report = self.review(
            paper_file, use_literature=use_literature, blind=blind,
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

        # A search query for the browser fallback, when a direct link is blocked or absent.
        avail = (comp or {}).get("data_availability") or ""
        query = f"{paper.title} {avail}".strip()[:200]

        # Prefer the data links the model found, then the keyword-detected ones.
        links = [DataLink(kind="direct", ref=u, url=u, score=3.0)
                 for u in (comp or {}).get("data_links", [])[:4]
                 if isinstance(u, str) and u.lower().startswith("http")]
        links += find_dataset_links(paper)
        work = self.settings.cache_path() / "data"
        for link in links[:5]:
            if progress:
                progress(f"fetching dataset: {link.kind} {link.ref[:40]}")
            try:
                files = acquire_dataset(link, work, query=query, backend=self.backend)
            except Exception as exc:  # noqa: BLE001
                log.warning("acquire failed for %s: %s", link.url, exc)
                continue
            main = pick_main_table(find_tabular_files(files), paper)
            if main is not None:
                log.info("Using dataset %s (from %s)", main.name, link.url)
                return str(main), link.url

        # No usable link worked: let the browser search the web for the dataset.
        if query:
            if progress:
                progress("searching the web for the dataset")
            try:
                files = acquire_dataset(DataLink(kind="direct", ref="", url="", supported=True),
                                        work, query=query, backend=self.backend)
                main = pick_main_table(find_tabular_files(files), paper)
                if main is not None:
                    log.info("Using dataset %s (from a web search)", main.name)
                    return str(main), "web search"
            except Exception as exc:  # noqa: BLE001
                log.warning("dataset web search failed: %s", exc)
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
