# Handling methods we don't hardcode

Empirical economics uses too many methods to hardcode a checker for each one. New estimators arrive
every year, and any single paper can combine several. So Econoclast does not try to own every method.
It does what a good referee does when they hit something unfamiliar: look it up, then verify.

This is the design rule for the whole project, not just for econometrics.

## The agent researches; the engine checks

Econoclast hands the research to a real agent and keeps the checking mechanical. The Sicarius (Claude Code or
Codex) reads, searches, downloads, writes code and argues; the arsenal holds it to rules it cannot talk its
way around: quotes are verified against the paper, computed wounds must point at files that exist, the score
and the seal are computed, not written.

## When the method is not covered

For a method with no built-in check (synthetic control, bunching, shift-share, structural models, double
machine learning), the agent does what a careful referee does with an unfamiliar method: it looks up the
method's identifying assumptions and standard diagnostics with `search_literature` and the web, checks the
paper against them, and, with the data in hand, writes and runs the diagnostic itself in the Fabrica. The
doctrine's rule is the same everywhere: do not guess; lean on sources; say what could not be verified.

## When the method is fine and the story is not

Many weak papers have clean regressions and a wrong story. That is why the walk passes through the Forum
before the palace: the agent learns how the market in the paper actually works (its institutions, the people
who decide, the magnitudes, the theory's assumptions and critiques) and only then judges whether causality
runs the way the paper says (Inversio), whether the theory fits the setting (Theoria), and whether real
people would behave as the mechanism requires (Mundus).

## When the data is honest and the paper is not

Fabrication is rare; bending honest data toward a conclusion is not. A quiet sample cut, an outcome switched
after the pre-analysis plan, a null left in the appendix, a number in the abstract that no table supports.
The integrity blades hunt these with deterministic screens (forensics on the reported numbers and on the
data, version diffs, code audits) that the agent must interpret, and the seal reports them apart from how
fragile the result is.
