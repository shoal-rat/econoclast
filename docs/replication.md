# Replication mode

The PDF-only forensics can't tell you whether the headline result *survives* alternative analytic
choices — for that you need the data. Replication mode re-estimates the result across a **multiverse**
of equally-defensible specifications and reports how fragile it is. Econoclast runs the regressions
itself (via statsmodels), so nothing executes the authors' code.

```bash
pip install "econoclast[replication]"
```

## 1. Generate a config from your data

```bash
econoclast replicate --init data.csv -o spec.yaml
```

This writes a template by inspecting the columns. Fill it in (the agent does this after reading the
paper):

```yaml
data: data.csv
outcome: log_downloads      # dependent variable
treatment: post_reform      # the focal regressor — its coefficient is "the result"
controls_pool: [size, age, prior_downloads, category]   # controls to toggle on/off
fixed_effects: [[unit], [unit, week]]                    # FE options to try
cluster: [week, unit]                                    # clustering options ("" = robust)
sample_filters: ["", "year >= 2020"]                     # sample options ("" = full)
estimator: ols              # ols | iv | logit
preferred_sign: 1           # the paper's claimed direction (+1 / -1)

# Optional design-specific checks:
running_var: page_rank      # RDD: forcing variable …
cutoff: 0.0                 # … and its threshold
unit: model_id              # DiD: unit / time / treated indicator / onset
time: week
treated: is_treated
treat_time: 26
```

## 2. Run the multiverse

```bash
econoclast replicate spec.yaml -o out/
```

Econoclast enumerates the cross-product of `controls × fixed_effects × cluster × sample` (capped at
`max_specs`, sampled with a fixed seed), fits each, and reports:

- **share significant in the expected direction** — the headline number. If the result is significant
  in only, say, 22% of plausible specifications, it's fragile.
- the coefficient's median, range and IQR across specifications;
- a **reference spec** (all controls) for comparison;
- a **specification-curve plot** (`spec_curve.png`).

If `running_var`/`cutoff` are set it adds an **RDD manipulation test** (density discontinuity) and a
**bandwidth-sensitivity** check; if the DiD fields are set it runs an **event-study pre-trend test**.

## 3. As part of a full review

```bash
econoclast review paper.pdf --replicate spec.yaml -o report/
```

The replication findings fold into the same fragility score as everything else. Inside Claude Code /
Codex, the `econoclast_replicate` MCP tool does the same.

## What it is and isn't

- It runs *your* (or the agent's) specification of the multiverse — garbage in, garbage out. The agent
  should derive `outcome`/`treatment`/`controls` from the paper, not guess.
- The estimators are OLS / 2SLS / logit with FE dummies and cluster-robust SEs — good for screening,
  not a substitute for the authors' exact pipeline.
- RDD/DiD checks are **screening** tests; confirm with `rdrobust` and Callaway-Sant'Anna / Sun-Abraham.
- Re-running the authors' actual code in a sandbox is on the roadmap (it requires the package and is
  inherently untrusted-code execution).

**References:** Simonsohn, Simmons & Nelson (2020, *Nat. Hum. Behav.*, specification curve);
Steegen et al. (2016, multiverse analysis).
