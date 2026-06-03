"""Specification-curve plot (matplotlib, optional)."""

from __future__ import annotations

from econoclast.replication.models import SpecCurve


def plot_spec_curve(curve: SpecCurve, path: str) -> str | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    results = sorted(curve.results, key=lambda r: r.coef)
    xs = range(len(results))
    coefs = [r.coef for r in results]
    sig = [r.significant for r in results]
    colors = ["#cf222e" if s else "#9aa0a6" for s in sig]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(xs, coefs, c=colors, s=10)
    for x, r in zip(xs, results, strict=False):
        ax.plot([x, x], [r.coef - 1.96 * r.se, r.coef + 1.96 * r.se],
                color=colors[x], alpha=0.25, linewidth=0.6)
    ax.axhline(0, color="black", linewidth=0.8)
    if curve.preferred is not None:
        ax.axhline(curve.preferred.coef, color="#0969da", linewidth=0.8, linestyle="--",
                   label=f"reference spec ({curve.preferred.coef:.3g})")
        ax.legend(loc="best", fontsize=8)
    share = curve.summary.get("share_significant_expected_sign", 0)
    ax.set_title(f"Specification curve — {len(results)} specs, "
                 f"{share:.0%} significant in expected direction")
    ax.set_xlabel("specification (sorted by coefficient)")
    ax.set_ylabel("focal coefficient")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
