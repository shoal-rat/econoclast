# Examples

## `demo_paper.txt` — a synthetic stress-test

A short, **fake** paper with **deliberately planted** problems, so you can see Econoclast catch
things with zero configuration and no API keys:

- a p-value that contradicts its reported test statistic (statcheck decision error),
- two impossible descriptive statistics (GRIM and GRIMMER),
- six significant p-values clustered just below .05 (a flat p-curve),
- a pile of t-statistics bunched just above 1.96 (caliper),
- plus over-claiming and "we did not report the dangerous robustness checks" prose for the LLM attacks.

Run it:

```bash
# Offline, instant, no keys — the deterministic battery:
econoclast forensics examples/demo_paper.txt

# Full review (still works offline; add a key to enable the LLM attacks):
econoclast review examples/demo_paper.txt -o examples/demo-report
```

Expected: **fragility ≈ 78/100 "Fragile"** with an integrity flag and five forensic flags.

It is not a real study — every number was chosen to trip a specific test.

## Bring your own paper

Point Econoclast at any `.pdf`, `.tex`, or `.txt`:

```bash
econoclast review my_paper.pdf -o report/
```

LaTeX source is the easiest to attack (numbers and tables survive verbatim). For PDFs, install the
better extractor with `pip install "econoclast[pdf]"`, or pre-convert hard layouts with GROBID/marker
and feed the text.
