<p align="center">
  <img src="docs/assets/banner.svg" alt="Econoclast" width="820">
</p>

<p align="center">
  <a href="https://github.com/shoal-rat/econoclast/actions/workflows/ci.yml"><img src="https://github.com/shoal-rat/econoclast/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/lint-ruff-261230.svg" alt="ruff"></a>
</p>

A lot of empirical papers are, underneath, a search. You pick a sample, a window, a set of controls,
a way to cluster the errors, and you keep the version that comes out significant. Then you write the
story forward as if that path was the only sensible one. Econoclast plays the other side of that
game. It re-derives the numbers in the paper, looks for the choices that were quietly made, checks
the result against the data when the data is available, and tells you how much of the headline
survives.

It works at two levels.

The first is a battery of statistical checks that run offline with no API key and no network:
statcheck (recompute every p-value from its test statistic), GRIM and GRIMMER (means and SDs that are
impossible for integer data), p-curve, bunching of z-statistics at 1.96, TIVA, Benford, and
terminal-digit tests. These are arithmetic. A flag here is hard to argue with.

The second is a set of adversarial critiques written by a model: specification search, cherry-picked
samples and windows, weak identification, missing robustness checks, hypotheses that look invented
after the fact, and claims the evidence does not support. Every one has to quote the paper, and a
separate referee pass turns the whole pile into a single fragility score.

You can stop at the first level (instant, free) or add the second with any backend: OpenAI,
Anthropic, Google, OpenRouter, a local model through Ollama, or your existing Claude Code or Codex
subscription with no separate key at all.

## The short version

If you have Claude Code or Codex installed, you do not need an API key or a single flag. Install once,
let the agent set itself up, then hand it a paper.

```bash
pip install "econoclast[all] @ git+https://github.com/shoal-rat/econoclast"
econoclast setup
```

After that, inside Claude Code or Codex, say:

> verify https://arxiv.org/abs/2401.12345

Econoclast downloads the paper, runs the forensics and the critique, looks in the paper for a public
dataset (Zenodo, a Dataverse, OSF, a GitHub repo, a direct file), downloads it, works out which
regression is the headline result, and re-runs it across hundreds of defensible specifications. You
get a fragility score and a list of specific, quotable problems. If the data is already on your
machine, point at it with `--data`.

```bash
econoclast verify paper.pdf --data replication/panel.csv
```

## Install and run

```bash
# Until the PyPI release, install from the repo:
pip install "git+https://github.com/shoal-rat/econoclast"
# everything (PDF, web UI, MCP, replication, LiteLLM):
pip install "econoclast[all] @ git+https://github.com/shoal-rat/econoclast"
```

Run the offline checks on the bundled demo. No keys needed:

```bash
econoclast forensics examples/demo_paper.txt
```

```text
                          Minimum Wages and Teen Employment (synthetic)
 Test       Verdict      N   Summary
 statcheck  suspicious   2   2/2 reported p-values disagree with the recomputed value, 2 flip
                             significance at .05
 grim       suspicious   1   1/1 reported means are impossible for integer data of that N
 grimmer    suspicious   1   1/1 (mean, SD, N) triples are impossible for integer data
 p-curve    suspicious   6   p-curve is flat/left-skewed: consistent with p-hacking
 caliper    suspicious  18   test statistics bunch just above the significance thresholds
```

The full review, with an API key for the model attacks:

```bash
export ANTHROPIC_API_KEY=...      # or OPENAI_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY
econoclast review path/to/paper.pdf -o report/
```

Or open the web UI:

```bash
pip install "econoclast[ui]"
econoclast ui
```

## Inside Claude Code and Codex

If you already run one of these agents, Econoclast can use its subscription, so there is no second
API key to manage. Three ways to wire it up, from least to most automatic.

Drive it from the terminal through your login:

```bash
econoclast review paper.pdf --backend claude     # uses your Claude Code login
econoclast review paper.pdf --backend codex      # uses your Codex / ChatGPT login
```

Let the agent call it as a tool. The agent does the reasoning, Econoclast supplies the statistics:

```bash
pip install "econoclast[mcp,pdf]"
claude mcp add econoclast -- econoclast mcp       # Claude Code
# Codex: add the snippet in integrations/codex/config-snippet.toml to ~/.codex/config.toml
```

Install it as a Claude Code plugin with a slash command:

```text
/plugin marketplace add shoal-rat/econoclast
/plugin install econoclast@econoclast
/econoclast paper.pdf
```

The setup wizard handles most of this for you. There is also an `/econoclast-setup` command that asks
two or three questions and runs `econoclast setup` itself. See [integrations/README.md](integrations/README.md).

One caveat: driving a CLI carries that agent's own system-prompt cost on every call, so for large
batches a direct API key is cheaper.

## What you get

A fragility score from 0 to 100 with a verdict band, the list of findings (each with a severity, a
confidence, the quote it rests on, and a suggested fix), the full forensic battery, and a short
referee summary of what would change the verdict. It renders to Markdown, JSON, and a self-contained
HTML page.

```text
+-- Minimum Wages and Teen Employment -------------------------------+
| Fragility 77.9/100  Fragile                                        |
| The central claim looks fragile to plausible alternative choices.  |
| Integrity flag: a reported statistic is internally impossible.     |
+----------------------------- did, panel_fe ------------------------+
```

## The checks

Every check returns the same kind of finding, so statistics and model reasoning land in one report
and one score. The deterministic ones need no key. The model ones must quote the paper, and they only
fire when the design matches (the RDD critique does not run on a paper without a running variable).

| Check | Kind | What it catches | Needs a model |
|---|---|---|---|
| statcheck | deterministic | a reported p that disagrees with its own test statistic, especially when it flips significance | no |
| GRIM | deterministic | means that no integer data of that N can produce | no |
| GRIMMER | deterministic | (mean, SD, N) triples that are impossible for integer data | no |
| p-curve | deterministic | a flat or left-skewed curve of significant p-values | no |
| caliper | deterministic | z-statistics piled up just above 1.96, 1.645, or 2.576 | no |
| TIVA, R-index | deterministic | z-scores too alike to be independent; an inflated success rate | no |
| Benford | deterministic | first-digit anomalies across the reported numbers | no |
| terminal-digit | deterministic | rounding and heaping on 0 and 5 | no |
| specification search | model | researcher degrees of freedom and a headline spec chosen from many | yes |
| cherry-picking | model | selective samples, windows, subgroups, outcomes, and dropped data | yes |
| identification | model | parallel-trends and staggered-DiD problems, RDD manipulation and bandwidth, IV exclusion and weak instruments | yes |
| robustness coverage | model | the standard checks that are conveniently missing | yes |
| HARKing | model | mechanisms and hypotheses that read as post-hoc | yes |
| over-claiming | model | abstract and conclusion claims the design cannot support | yes |
| literature contradiction | model | novelty and positioning claims checked against retrieved related work | yes |

Run `econoclast attacks` for the list, or `--attacks statcheck,caliper` for a subset. The algorithms
and references are in [docs/attacks.md](docs/attacks.md).

## Replication mode

The checks above read the PDF. They cannot tell you whether the result holds under a different but
equally reasonable specification. For that you need the data. Give Econoclast the dataset and it
re-estimates the headline coefficient across the multiverse of choices (which controls, which fixed
effects, which clustering, which sample) and reports the share that survive. It runs the regressions
itself with statsmodels. It never executes the authors' code.

```bash
pip install "econoclast[replication]"
econoclast replicate --init data.csv -o spec.yaml   # scaffold a config from the columns
econoclast replicate spec.yaml -o out/              # spec-curve plot, JSON, findings
```

"Significant in 22% of 1,800 plausible specifications" says more than any single regression table.
With the right fields set it also runs an RDD manipulation and bandwidth check and a DiD pre-trend
test. More in [docs/replication.md](docs/replication.md). The `verify` command does all of this for
you, including finding and downloading the dataset.

## How it works

<p align="center">
  <img src="docs/assets/pipeline.svg" alt="Econoclast pipeline" width="940">
</p>

The pipeline is fixed and ordered rather than an open-ended loop. The attack set is design-gated,
every model finding is tied to a quote, and a separate model writes the final synthesis. It trades
some autonomy for being auditable, which is the right trade for a tool whose job is rigour. Notes in
[docs/architecture.md](docs/architecture.md).

Models are addressed by role, not by name. An attack asks for `extractor`, `attacker`, or `referee`,
and the router resolves it to a model with a fallback and keeps a running cost. You configure it in
`econoclast.yaml`:

```yaml
models:
  extractor: anthropic:claude-haiku-4-5-20251001
  attacker:
    - anthropic:claude-opus-4-8
    - openai:gpt-4o
  referee: anthropic:claude-opus-4-8
literature:
  enabled: true
  local_dirs: ["~/papers/io-reading-list"]
```

Point a role at a local model with `{ provider: ollama, model: "llama3.1:70b" }`, or hand everything
to [LiteLLM](https://github.com/BerriAI/litellm) for its provider list. Details in [docs/models.md](docs/models.md).

## Keeping the review honest

Automated reviewers fail in known ways, and the research on LLM peer review is fairly consistent about
which ones. Econoclast builds in the countermeasures it recommends. The detail and the citations are
in [docs/credibility.md](docs/credibility.md).

Findings are grounded. Each model finding carries a verbatim quote, and a mechanical check confirms
the quote is actually in the paper before the finding counts for much. Reviews are run identity-blind,
because a 1,220-paper study in economics found that models rate elite and visible authors higher; the
author block, affiliations, emails, and acknowledgements are redacted before the model sees the text.
The manuscript is treated as data and never as instructions, so invisible text is stripped and any
embedded "give a positive review" line is caught and flagged. The score is calibrated by severity and
confidence and saturates, so a couple of real problems outweigh a long list of nitpicks. And the
output is a set of flags for a person to check. A statistical inconsistency can be an honest typo, and
Econoclast does not accuse anyone of anything.

## Limitations

Read [docs/interpreting-reports.md](docs/interpreting-reports.md) before you quote a finding.

The distribution tests (p-curve, caliper, TIVA, Benford) are weak on small samples and assume things a
single paper may not satisfy; they are capped at low confidence and printed with their caveats. Model
findings can be wrong or overconfident, which is why each one ships with the quote it rests on. The
replication runs your specification of the multiverse, so the agent has to read the variables off the
paper correctly, and the estimators are screening tools rather than a copy of the authors' exact
pipeline. Do not paste a fragility score into a public accusation.

## Roadmap

- [x] Specification-curve and multiverse replication, re-estimated in process
- [x] RDD manipulation and bandwidth checks, DiD pre-trend screening
- [x] One-line `verify`: fetch the paper, find and download the data, run everything
- [x] Runs inside Claude Code and Codex, no API key
- [x] Takes a path or a URL (arXiv, a PDF, a journal page)
- [ ] Sandboxed re-execution of the authors' actual code
- [ ] Full McCrary / Cattaneo-Jansson-Ma density and Callaway-Sant'Anna / Sun-Abraham estimators
- [ ] Mechanical citation verification; voting across several models
- [ ] GROBID ingestion for hard PDF layouts; batch mode over a folder or a whole issue

## Contributing

Adding a check is small: subclass `Attack`, return findings, register it. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/shoal-rat/econoclast && cd econoclast
pip install -e ".[dev,pdf,replication]"
pytest && ruff check src tests
```

## Citation

```bibtex
@software{econoclast,
  title  = {Econoclast: an adversarial AI referee for empirical economics},
  year   = {2026},
  url    = {https://github.com/shoal-rat/econoclast}
}
```

## License

MIT. See [LICENSE](LICENSE).
