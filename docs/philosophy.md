# Handling methods we don't hardcode

Empirical economics uses too many methods to hardcode a checker for each one. New estimators arrive
every year, and any single paper can combine several. So Econoclast does not try to own every method.
It owns a fast path of built-in checks and, for everything else, it does what a good referee does when
they hit something unfamiliar: look it up, then verify.

This is the design rule for the whole project, not just for econometrics.

## The fast path

A handful of checks are coded directly because they are exact and cheap: statcheck, GRIM and GRIMMER,
p-curve, the caliper test, TIVA, Benford, the McCrary density test, and the Callaway-Sant'Anna and
Sun-Abraham estimators. When a paper uses one of these designs, Econoclast runs the real test and the
result is reproducible to the digit. These are the methods in `COVERED_METHODS`.

## When the method is not covered

`detect_methods` reads the paper and `method_coverage` splits what it finds into covered methods and
methods that need research. For an uncovered method (synthetic control, a bunching estimator, a
shift-share instrument, a structural model, double machine learning, and so on), three things happen.

First, Econoclast retrieves the method's literature. It searches OpenAlex, Semantic Scholar, and arXiv
for the method's identifying assumptions and standard diagnostics and puts the results in front of the
model. The `methodology-audit` attack then derives the assumptions and the expected tests from that
retrieved material and checks the paper against them, rather than relying on the model's memory.

Second, every model prompt carries an epistemic rule: do not guess about a method or a fact you are
unsure of; lean on the retrieved sources; mark anything you could not verify as needing a check and
give it low confidence; prefer a few grounded findings to many speculative ones. The grounding gate
and the referee both discount unverified points.

Third, with `--deep`, the audit branches. It runs several independent verification strategies for the
same question (one derives the assumptions, one lists the diagnostics, one works through the method's
known failure modes), and a judge merges them: it keeps the best-supported points, drops duplicates,
and prefers the approach most appropriate to the paper's actual method. This is the "try a few ways
and keep the best" idea applied at the level of a single hard question.

## Building the check on the fly

If the data is available and the paper uses a method with no built-in estimator, `--allow-code` lets
the agent go one step further. It writes a single Python diagnostic for that method (a placebo or
permutation test, a balance or continuity check, a weak-identification statistic), runs it, and turns
the result into a finding. This executes model-written code, so it is off by default, runs only with
the explicit flag, and should be used inside a container. A crude denylist blocks obvious file,
network, and shell calls, but it is not a sandbox.

## Why it is built this way

A tool that only knows the methods its authors thought to code would be wrong about most papers within
a year. Tying every model claim to a quote or a retrieved source, marking what could not be verified,
and trying more than one approach when the answer is not obvious is what keeps the reviews honest as
the set of methods keeps growing. The built-in checks are a fast path, not the limit of what
Econoclast can question.
