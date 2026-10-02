"""The arsenal as an MCP server: what Claude Code or Codex sees as tools.

Launched by the agent itself (stdio) with the case folder it serves:

    python -m econoclast arsenal --case ~/.econoclast/cases/<id>

You can also attach it to your own Claude Code or Codex session to use the tools by hand
(``econoclast arsenal --case <dir>``), but normally the hunt wires it up.
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any

import anyio

from econoclast.arsenal.tools import Arsenal
from econoclast.case.store import Case
from econoclast.version import __version__


def _server_class():  # noqa: ANN202
    try:  # MCP Python SDK 2.x
        from mcp.server.mcpserver import MCPServer

        return functools.partial(MCPServer, version=__version__)
    except ImportError:  # SDK 1.x
        from mcp.server.fastmcp import FastMCP

        return FastMCP


def build_server(case_dir: str):  # noqa: ANN201
    arsenal = Arsenal(Case(case_dir))
    mcp = _server_class()("econoclast-arsenal", instructions=(
        "Econoclast's arsenal for testing an empirical paper. Walk the stations with proclaim(); record "
        "every finding with inflict_wound() or parry(); finish with pronounce_verdict()."))

    async def thread(fn, *a, **kw):  # noqa: ANN001, ANN202
        return await anyio.to_thread.run_sync(lambda: fn(*a, **kw))

    # ------------------------------------------------------------- walk
    @mcp.tool()
    def proclaim(station: str, note: str = "") -> dict:
        """Enter a station of the walk and get its orders.

        Stations, in order: classis (get the paper), scriptorium (read it), forum (learn the real world the
        paper describes; swing the reality blades inversio, theoria, mundus), horreum (find the data),
        fabrica (build the quant workshop, reproduce the headline), palatium (the seven text blades),
        aula (the thousand-road multiverse), curia (the verdict). `note` is a one-line status the
        traveller sees (e.g. "skipping: no data").
        """
        return arsenal.proclaim(station, note)

    # ---------------------------------------------------------- classis
    @mcp.tool()
    async def fetch_paper(url_or_doi: str) -> dict:
        """Download a paper into paper/ from a URL, an arXiv link, a DOI (doi:10.x/..) or a landing page.

        Returns the local path. If the publisher blocks it, the result says so: then use your browser,
        curl with a real User-Agent, or an open mirror.
        """
        return await thread(arsenal.fetch_paper, url_or_doi)

    # ------------------------------------------------------ scriptorium
    @mcp.tool()
    async def read_paper(path: str) -> dict:
        """Parse a paper (PDF, LaTeX, text, HTML) into an outline, extracted statistics, detected
        designs/methods, dataset links and any hidden reviewer instructions. Writes paper/paper.txt."""
        return await thread(arsenal.read_paper, path)

    @mcp.tool()
    def paper_section(index: int) -> dict:
        """Return the text of one section of the outline read_paper returned."""
        return arsenal.paper_section(index)

    @mcp.tool()
    def mark_target(claim: str, design: str = "", table: str = "", coefficient: float | None = None,
                    std_error: float | None = None, outcome: str = "", treatment: str = "", sample: str = "",
                    estimator: str = "", data_availability: str = "", paper_title: str = "") -> dict:
        """Record the headline claim under attack (the Emperor's decree): the one coefficient the paper's
        story rests on, where it is reported, how it was estimated, and where the data is said to be.
        paper_title: the paper's real title (PDF metadata often gets it wrong)."""
        return arsenal.mark_target(claim, design, table, coefficient, std_error, outcome, treatment,
                                   sample, estimator, data_availability, paper_title)

    @mcp.tool()
    def verify_quote(quote: str) -> dict:
        """Check that a quote really appears in the paper (whitespace and punctuation tolerant)."""
        return arsenal.verify_quote(quote)

    @mcp.tool()
    async def abacus() -> dict:
        """Arithmetic check of the extracted statistics: stars that coef/se cannot support, p-values that
        disagree with their test statistic, impossible values. Flags only; you judge each one."""
        return await thread(arsenal.abacus)

    # ------------------------------------------------------------ forum
    @mcp.tool()
    def field_notes(field: str, setting: str, actors: list[str] | None = None, claimed_mechanism: str = "",
                    real_mechanism: str = "", institutions: str = "", magnitudes: str = "", theory: str = "",
                    theory_assumptions: list[str] | None = None, rival_explanations: list[str] | None = None,
                    sources: list[str] | None = None) -> dict:
        """Record the field brief from the Forum: what you learned about the real world the paper describes.

        actors: who decides (with their incentives); claimed_mechanism vs real_mechanism: the story the paper
        tells vs how the real actors behave; institutions: laws, regulators, contracts, timing; magnitudes:
        sector size, prices, plausible elasticities; theory + theory_assumptions; rival_explanations; sources:
        URLs or references you relied on. It is the evidence base for the inversio, theoria and mundus blades.
        """
        return arsenal.field_notes(field, setting, actors, claimed_mechanism, real_mechanism, institutions,
                                   magnitudes, theory, theory_assumptions, rival_explanations, sources)

    # --------------------------------------------- integrity: falsum, fucus, palimpsestus
    @mcp.tool()
    async def forensics_paper() -> dict:
        """Fabrication and spin screens on the paper's reported numbers: GRIM on means, bunching of p-values
        and t-statistics just past significance (caliper tests), p-curve shape, coefficient/SE pairs repeated
        across tables, terminal digits, and abstract numbers that appear nowhere in the body. Flags only."""
        return await thread(arsenal.forensics_paper)

    @mcp.tool()
    async def forensics_data(path: str, treatment: str = "", covariates: list[str] | None = None,
                             id_columns: list[str] | None = None, columns: list[str] | None = None) -> dict:
        """Fabrication screens on a dataset: exact and near-duplicate rows, last-digit and Benford tests,
        heaping, impossible values, and (with treatment + baseline covariates) Carlisle's test for balance
        that is too good for a randomisation. Flags with evidence and caveats; writes an artifact in out/."""
        return await thread(arsenal.forensics_data, path, treatment, covariates, id_columns, columns)

    @mcp.tool()
    async def compare_versions(earlier: str, later: str, earlier_label: str = "earlier",
                               later_label: str = "later") -> dict:
        """Diff two versions of the paper (working paper vs published, arXiv v1 vs v3, pre-analysis plan vs
        paper): rewritten claim sentences, removed and added results, estimates that changed, outcomes and
        sample sizes in each. Paths to PDFs or text files you downloaded."""
        return await thread(arsenal.compare_versions, earlier, later, earlier_label, later_label)

    @mcp.tool()
    async def audit_code(folder: str = "data") -> dict:
        """List every data-shaping line (drop/keep/filter, recode/replace, winsorise/trim, merge, weights) in the
        authors' Stata, R and Python code under folder, with file and line, to compare with the paper."""
        return await thread(arsenal.audit_code, folder)

    @mcp.tool()
    async def novacula(data: str, outcome: str, simple_terms: list[str], extra_terms: list[str],
                       cluster: str = "", folds: int = 5) -> dict:
        """Occam's razor on the data. Fits the plain model (outcome ~ simple_terms) and the paper's richer one
        (simple_terms + extra_terms: the theory's added mechanisms, interactions, channels) and compares AIC,
        BIC, adjusted R2, a likelihood-ratio test and k-fold out-of-sample RMSE. Terms are column names or
        patsy expressions (e.g. "x:z", "I(x**2)")."""
        return await thread(arsenal.novacula, data, outcome, simple_terms, extra_terms, cluster, folds)

    # ------------------------------------------------------ bibliotheca
    @mcp.tool()
    async def search_literature(query: str, limit: int = 8) -> dict:
        """Search OpenAlex, Semantic Scholar, arXiv and Crossref. Use it for novelty claims, contradicting
        findings, and the identifying assumptions and diagnostics of any method you do not know cold."""
        return await thread(arsenal.search_literature, query, limit)

    @mcp.tool()
    async def check_references(limit: int = 30) -> dict:
        """Resolve the paper's reference list against Crossref; returns the entries that do not resolve."""
        return await thread(arsenal.check_references, limit)

    # ---------------------------------------------------------- horreum
    @mcp.tool()
    def find_data_links() -> dict:
        """Dataset pointers found in the paper text (Zenodo, Dataverse, openICPSR, OSF, GitHub, direct files)."""
        return arsenal.find_data_links()

    @mcp.tool()
    async def fetch_dataset(url: str) -> dict:
        """Download a dataset or replication package into data/ (Zenodo, Harvard Dataverse, OSF, GitHub,
        direct links; archives are unpacked whole, code included). openICPSR needs a login."""
        return await thread(arsenal.fetch_dataset, url)

    @mcp.tool()
    async def public_series(source: str, series: str, countries: str = "all", start: str = "",
                            end: str = "") -> dict:
        """Pull a keyless public series into data/public/: source='fred' with a FRED series id (e.g. UNRATE),
        or source='worldbank' with an indicator code (e.g. NY.GDP.PCAP.KD) and ISO3 countries 'USA;CHN'."""
        return await thread(arsenal.public_series, source, series, countries, start, end)

    @mcp.tool()
    async def inspect_dataset(path: str) -> dict:
        """Columns, types, missingness, value ranges, Stata variable labels and the first rows of a table."""
        return await thread(arsenal.inspect_dataset, path)

    # ---------------------------------------------------------- fabrica
    @mcp.tool()
    async def fabrica_build(extra_packages: list[str] | None = None) -> dict:
        """Create (once) and extend the local quant workshop: a lean Python venv with pandas, statsmodels,
        linearmodels, rdrobust, rddensity, plus extra_packages you ask for (pyfixest, pyarrow, scikit-learn,
        doubleml, differences, pysyncon, ...). Returns its path."""
        return await thread(arsenal.fabrica_build, extra_packages)

    @mcp.tool()
    async def fabrica_run(script: str, timeout_sec: int = 900, args: list[str] | None = None) -> dict:
        """Run a script from the case folder inside the workshop (.py with the workshop Python, .R with
        Rscript, .sh with bash). Returns stdout/stderr tails and the files it created."""
        return await thread(arsenal.fabrica_run, script, timeout_sec, args)

    @mcp.tool()
    def reproduce(what: str, paper_value: float, reproduced_value: float, paper_se: float | None = None,
                  reproduced_se: float | None = None, script: str = "", note: str = "") -> dict:
        """Record the Speculum comparison: the paper's reported estimate vs the one your script produced."""
        return arsenal.reproduce(what, paper_value, reproduced_value, paper_se, reproduced_se, script, note)

    # ------------------------------------------------------------- aula
    @mcp.tool()
    async def mille_viae(spec: dict[str, Any]) -> dict:
        """Run the thousand roads: the specification curve over every defensible choice, plus design checks.

        spec keys: data (path), outcome, treatment, controls_pool [cols], controls_mode
        (auto|powerset|allnone|incremental), fixed_effects [[cols], ...], cluster [col, ...],
        sample_filters [pandas query strings], estimator (ols|iv|logit), instruments, endogenous,
        preferred_sign (+1/-1), max_specs; RDD: running_var, cutoff; DiD: unit, time, treated, treat_time,
        or cohort (first-treated period, 0 = never). Computed wounds are recorded automatically.
        """
        return await thread(arsenal.mille_viae, spec)

    # ----------------------------------------------------------- wounds
    @mcp.tool()
    def inflict_wound(blade: str, title: str, severity: str, detail: str, confidence: float = 0.6,
                      quote: str = "", location: str = "", remedy: str = "", evidence_kind: str = "text",
                      artifacts: list[str] | None = None) -> dict:
        """Record a finding. blade: labyrinthus | canistrum | persona | inversio | theoria | novacula | mundus | scutum |
        augur | tuba | bibliotheca | falsum | palimpsestus | fucus | abacus | speculum | mille_viae. severity: low | medium | high | critical. evidence_kind 'text' needs
        a verbatim quote from the paper (it is checked); 'computation' needs artifacts (paths of the script
        and output you produced). title: one line; detail: why it matters; remedy: what the authors should do."""
        return arsenal.inflict_wound(blade, title, severity, detail, confidence, quote, location, remedy,
                                     evidence_kind, artifacts)

    @mcp.tool()
    def parry(blade: str, note: str, quote: str = "") -> dict:
        """Record that a blade was tried and the paper defended itself on that front (say which defence held)."""
        return arsenal.parry(blade, note, quote)

    # ------------------------------------------------------------- plea
    @mcp.tool()
    async def plea(what: str, why: str, accept: str = "file", where: str = "", wait_minutes: int = 15) -> dict:
        """Ask the traveller (the human) for something you could not get yourself, e.g. a paywalled PDF or a
        login-gated replication package. Name exactly what and where it lives. Waits up to wait_minutes for
        their answer: uploaded files (paths in offerings/), a URL, or a refusal."""
        plea_id = arsenal.plea_open(what, why, accept, where)
        deadline = time.time() + max(1, min(wait_minutes, 120)) * 60
        while time.time() < deadline:
            ans = arsenal.plea_poll(plea_id)
            if ans is not None:
                status = "declined" if ans.get("declined") else "answered"
                return {"status": status, **ans}
            await asyncio.sleep(1.5)
        return arsenal.plea_timeout(plea_id)

    # ----------------------------------------------------------- curia
    @mcp.tool()
    async def pronounce_verdict(headline: str, assessment: str, change_my_mind: str,
                                survived: list[str] | None = None) -> dict:
        """Close the hunt: computes the fragility score from the recorded wounds and writes the report
        (tabula.html / tabula.md / tabula.json in the case folder)."""
        return await thread(arsenal.pronounce_verdict, headline, assessment, change_my_mind, survived)

    return mcp


def main(case_dir: str) -> None:
    build_server(case_dir).run()
