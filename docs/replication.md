# Mille Viae: a thousand roads

Reading the paper can't tell you whether the headline result *survives* alternative analytic
choices, for that you need the data. Replication mode re-estimates the result across a **multiverse**
of equally-defensible specifications and reports how fragile it is. In a hunt the Sicarius builds the
spec in the Aula from the degrees of freedom it collected while reading, and calls the `mille_viae` tool;
you can also run it yourself.

## 1. Write a spec

```yaml
data: data.csv
outcome: log_downloads      # dependent variable
treatment: post_reform      # the focal regressor, its coefficient is "the result"
controls_pool: [size, age, prior_downloads, category]   # controls to toggle on/off
fixed_effects: [[unit], [unit, week]]                    # FE options to try
cluster: [week, unit]                                    # clustering options ("" = robust)
sample_filters: ["", "year >= 2020"]                     # sample options ("" = full)
estimator: ols              # ols | iv | logit
preferred_sign: 1           # the paper's claimed direction (+1 / -1)

# Optional design-specific checks:
running_var: page_rank      # RDD: forcing variable ...
cutoff: 0.0                 # ... and its threshold
unit: model_id              # DiD: unit / time / treated indicator / onset
time: week
treated: is_treated
treat_time: 26
```

## 2. Run the multiverse

```bash
econoclast replicate spec.yaml -o out/
```

In a hunt the same spec goes to `mille_viae(spec)` as a dict; the curve is drawn on the throne-hall wall as
roads of tesserae (gold where the result is significant in the paper's direction) and again in the Tabula.

Econoclast enumerates the cross-product of `controls × fixed_effects × cluster × sample` (capped at
`max_specs`, sampled with a fixed seed), fits each, and reports:

- **share significant in the expected direction**, the headline number. If the result is significant
  in only, say, 22% of plausible specifications, it's fragile.
- the coefficient's median, range and IQR across specifications;
- a **reference spec** (all controls) for comparison;
- a **specification-curve plot** (`spec_curve.png`).

## Design-specific estimators

When the config carries the relevant columns, replication mode also runs the proper design checks.

For RDD (`running_var`, `cutoff`), it runs the **McCrary (2008) density test**: it bins the running
variable so the cutoff is a bin edge, fits a triangular-kernel local linear to the histogram on each
side, and tests the log-density jump `theta = log f(+) - log f(-)` with McCrary's standard error. A
significant jump is evidence of sorting at the threshold. It also reports a bandwidth-sensitivity
scan. For publication, confirm with `rddensity` (Cattaneo-Jansson-Ma); the local-linear estimator has
boundary bias, so the flag is deliberately conservative.

For staggered DiD, give a `cohort` column (each unit's first treated period, 0 for never-treated) or
the single-treatment fields (`unit`, `time`, `treated`, `treat_time`). It then computes:

- **Callaway and Sant'Anna (2021)** group-time effects ATT(g, t) from clean 2x2 comparisons against
  not-yet-treated units, aggregated into an overall effect and an event study, with a clustered
  bootstrap for standard errors and a pre-trend check on the leads.
- **Sun and Abraham (2021)** interaction-weighted event study, as an independent cross-check.
- A **Goodman-Bacon style** contrast: the plain two-way fixed-effects estimate against the
  Callaway-Sant'Anna overall effect. A large gap or a sign flip flags the negative-weights bias that
  makes TWFE unreliable under staggered timing, and Econoclast raises a finding for it.

## The authors' own code

Econoclast no longer runs replication packages blindly. In the Fabrica the agent reads the authors' code
(`audit_code` lists every drop, filter, recode, trim, merge and weight), copies their choices into its own
script, and runs that inside the workshop; R scripts run with Rscript when it is installed. Undisclosed data
steps that move the estimate become Speculum wounds.

## What it is and isn't

- It runs *your* (or the agent's) specification of the multiverse: garbage in, garbage out. The agent
  should derive `outcome`/`treatment`/`controls` from the paper, not guess.
- The estimators are OLS / 2SLS / logit with FE dummies and cluster-robust SEs, good for screening,
  not a substitute for the authors' exact pipeline.
- RDD/DiD checks are **screening** tests; confirm with `rdrobust` and Callaway-Sant'Anna / Sun-Abraham.
- Re-running the authors' actual code in a sandbox is on the roadmap (it requires the package and is
  inherently untrusted-code execution).

**References:** Simonsohn, Simmons & Nelson (2020, *Nat. Hum. Behav.*, specification curve);
Steegen et al. (2016, multiverse analysis).
