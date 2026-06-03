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
        replication_config: str | None = None,
        max_workers: int = 6,
        progress=None,
    ) -> Report:
        paper = load_paper(paper_path)
        designs = detect_designs(paper.text)
        log.info("Detected design(s): %s", design_label(designs))

        ctx = AttackContext(
            paper=paper,
            settings=self.settings,
            router=self.router,
            designs=designs,
            searcher=self.searcher if use_literature else None,
            blind=blind,
        )
        paper_norm = normalize_for_match(paper.text)

        if use_literature and self.searcher is not None:
            ctx.literature = self._gather_literature(paper, designs)

        include_llm = use_llm and self.router.is_live()
        attacks = select_attacks(attack_names, include_llm=True, include_forensic=True)

        run_names: list[str] = []
        skipped: list[str] = []
        forensic_attacks: list[Attack] = []
        llm_attacks: list[Attack] = []
        for a in attacks:
            if not a.gate(ctx):
                skipped.append(f"{a.name} (design n/a)")
                continue
            if a.requires_llm and not include_llm:
                skipped.append(f"{a.name} (no LLM)")
                continue
            run_names.append(a.name)
            (llm_attacks if a.kind == "llm" else forensic_attacks).append(a)

        findings: list[Finding] = []

        # Deterministic forensics first (fast, offline, ordered).
        for a in forensic_attacks:
            if progress:
                progress(f"forensic: {a.name}")
            findings.extend(self._safe_run(a, ctx))

        # LLM attacks concurrently.
        if llm_attacks:
            with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
                futs = {pool.submit(self._safe_run, a, ctx): a for a in llm_attacks}
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

    # -------------------------------------------------------------- helpers
    def _safe_run(self, attack: Attack, ctx: AttackContext) -> list[Finding]:
        try:
            return attack.run(ctx)
        except Exception as exc:  # noqa: BLE001 — one attack must not kill the run
            log.warning("attack '%s' raised: %s", attack.name, exc)
            return []

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
