"""Research-then-verify the paper's estimation method.

Econoclast cannot hardcode a check for every estimator. When a paper uses a
method it does not cover (synthetic control, bunching, shift-share, a structural
model, double machine learning, and so on), this attack falls back to the right
behaviour: figure out what the method is, pull its assumptions and standard
diagnostics from the literature, and check the paper against them, instead of
guessing from the model's memory. With --deep it runs several verification
strategies and a judge merges the best.
"""

from __future__ import annotations

from econoclast.attacks.base import AttackContext, Finding
from econoclast.attacks.designs import design_label, detect_methods, method_coverage
from econoclast.attacks.llm import LLMAttack, _paper_brief
from econoclast.logging import get_logger

log = get_logger("attacks.methodology")

_METHOD_NAMES = {
    "synthetic_control": "synthetic control",
    "bunching": "bunching / notch estimator",
    "event_study": "event-study",
    "shift_share": "shift-share (Bartik) instrument",
    "regression_kink": "regression kink design",
    "gmm": "GMM",
    "ml_causal": "causal machine learning (DML / causal forest / lasso)",
    "structural": "structural / demand estimation",
    "did": "difference-in-differences",
    "rdd": "regression discontinuity",
    "iv": "instrumental variables",
    "matching": "matching / weighting",
}


class MethodologyAuditAttack(LLMAttack):
    name = "methodology-audit"
    category = "identification"
    description = "Research the paper's estimator and verify its assumptions and diagnostics."
    system_prompt = (
        "You audit the econometric METHOD a paper uses. You know that you do not know every estimator, "
        "so you rely on the retrieved methodology for any method you are not fully sure of, and you check "
        "the paper against that method's actual identifying assumptions and standard diagnostics."
    )

    def gate(self, ctx: AttackContext) -> bool:
        return bool(detect_methods(ctx.paper.text))

    def _methods_block(self, ctx: AttackContext) -> str:
        methods = ctx.methods or detect_methods(ctx.paper.text)
        cov = method_coverage(methods)
        names = [_METHOD_NAMES.get(m, m) for m in sorted(methods)]
        lines = [f"DETECTED METHOD(S): {', '.join(names) or 'unclear'}"]
        if cov["needs_research"]:
            lines.append("Methods WITHOUT a built-in check (rely on the literature, do not guess): "
                         + ", ".join(_METHOD_NAMES.get(m, m) for m in cov["needs_research"]))
        if ctx.methodology:
            lines.append("\nRETRIEVED METHODOLOGY (use this for assumptions/diagnostics):")
            for method, refs in ctx.methodology.items():
                lines.append(f"[{_METHOD_NAMES.get(method, method)}]\n{refs[:1800]}")
        return "\n".join(lines)

    def build_user_prompt(self, ctx: AttackContext) -> str:
        return (
            f"This paper's design is {design_label(ctx.designs)}. Audit its estimation method.\n\n"
            f"{self._methods_block(ctx)}\n\n"
            "For each method, state its identifying assumptions and the standard diagnostics a careful "
            "referee expects (grounded in the retrieved methodology where given). Then check the paper: "
            "which assumptions are argued or tested, which are asserted, and which standard diagnostic is "
            "missing? Raise a finding for any assumption left unchecked or any standard test the paper "
            "omits, especially for a method Econoclast does not cover automatically. Quote the paper.\n\n"
            + _paper_brief(ctx)
        )

    def run(self, ctx: AttackContext) -> list[Finding]:
        if not ctx.llm_live:
            return []
        if not ctx.deep:
            return super().run(ctx)
        # Deep mode: branch into several verification strategies and judge-merge.
        from econoclast.agent.branches import branch_and_merge

        brief = self._methods_block(ctx) + "\n\n" + _paper_brief(ctx)
        strategies = [
            ("assumptions", "List this method's identifying assumptions (from the retrieved methodology "
                            "if given), then check each against the paper. Flag any that are merely "
                            "asserted.\n\n" + brief),
            ("diagnostics", "List the standard robustness/diagnostic tests for this exact method, mark "
                            "each present or missing in the paper, and flag missing ones that matter.\n\n" + brief),
            ("failure-modes", "Describe the known ways THIS method fails (from the literature) and check "
                              "whether the paper is exposed to each.\n\n" + brief),
        ]
        return branch_and_merge(ctx, strategies=strategies, system=self.system_prompt,
                                default_category=self.category, attack_name=self.name)
