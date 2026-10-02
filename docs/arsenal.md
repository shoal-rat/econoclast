# The arsenal

The arsenal is Econoclast's MCP server (27 tools). Every hunt attaches it to the agent, bound to that hunt's case folder;
you can also attach it to your own session (`claude mcp add econoclast -- econoclast arsenal`), in which case it
opens a fresh case folder for the session. Every tool does real work and leaves an event in the case log.

| Tool | Station | What it does |
|---|---|---|
| `proclaim(station, note)` | all | enter a station; returns that station's orders |
| `fetch_paper(url_or_doi)` | Classis | download a paper (arXiv, DOI, landing pages with `citation_pdf_url`); says plainly when blocked |
| `read_paper(path)` | Scriptorium | outline, extracted statistics, detected designs and methods, dataset links, hidden reviewer instructions |
| `paper_section(index)` | Scriptorium | one section's text |
| `mark_target(claim, ...)` | Scriptorium | record the decree: the headline coefficient, table, design, sample, data availability, real title |
| `verify_quote(quote)` | all | is this quote really in the paper? |
| `abacus()` | Scriptorium | reported numbers that cannot all be true (stars vs coef/SE, p vs test statistic) |
| `forensics_paper()` | Scriptorium | GRIM, caliper tests on p and t, p-curve, repeated estimates, terminal digits, abstract numbers absent from the body |
| `compare_versions(earlier, later)` | Scriptorium | diff two versions or a pre-analysis plan: rewritten claims, dropped results, changed estimates, outcomes, sample sizes |
| `field_notes(...)` | Forum | the field brief: actors and incentives, claimed vs real mechanism, institutions, magnitudes, theory, rivals, sources |
| `novacula(data, outcome, simple_terms, extra_terms)` | Forum | Occam's razor on the data: the plain model vs the paper's richer one (AIC, BIC, LR test, cross-validated RMSE) |
| `search_literature(query)` | Forum, Palatium | OpenAlex, Semantic Scholar, arXiv, Crossref |
| `check_references()` | Palatium | references that do not resolve in Crossref |
| `find_data_links()` | Horreum | Zenodo, Dataverse, openICPSR, OSF, GitHub and direct links in the text |
| `fetch_dataset(url)` | Horreum | download and unpack a package (code included) |
| `public_series(source, series)` | Horreum | FRED series and World Bank indicators, no key needed |
| `inspect_dataset(path)` | Horreum | columns, types, missingness, ranges, Stata labels, first rows |
| `fabrica_build(extra_packages)` | Fabrica | build or extend the shared quant workshop |
| `fabrica_run(script)` | Fabrica | run `.py` / `.R` / `.sh` inside the workshop; returns output tails and new files |
| `reproduce(what, paper_value, reproduced_value, ...)` | Fabrica | record the Speculum comparison |
| `audit_code(folder)` | Fabrica | every drop, filter, recode, trim, merge and weight in the authors' Stata, R and Python |
| `forensics_data(path, ...)` | Fabrica | duplicate and near-duplicate rows, terminal digits, Benford, heaping, impossible values, Carlisle balance test |
| `mille_viae(spec)` | Aula | the specification curve plus RDD and DiD design checks; records computed wounds itself |
| `inflict_wound(blade, ...)` | all | record a finding; text wounds must quote the paper, computation wounds must cite artifacts |
| `parry(blade, note)` | all | record a line of attack the paper withstood |
| `plea(what, why, ...)` | all | ask the traveller for a file; waits for the answer |
| `pronounce_verdict(...)` | Curia | compute the score and the seal, write the Tabula |

The station orders live in `arsenal/doctrine.py`; `proclaim` hands each one over at the moment the agent
enters, so the instructions arrive when they are needed and survive context compaction.
