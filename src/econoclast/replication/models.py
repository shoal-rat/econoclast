"""Data model for replication / specification-curve analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SpecConfig:
    """Describes the 'multiverse' of plausible specifications for one result.

    The agent fills this in after reading the paper and the dataset's columns.
    Econoclast then enumerates the cross-product of analytic choices, runs every
    one, and reports how fragile the headline estimate is.
    """

    data: str  # path to a .csv / .parquet / .dta
    outcome: str  # dependent variable
    treatment: str  # the focal regressor whose coefficient is the 'result'
    controls_pool: list[str] = field(default_factory=list)  # optional controls to toggle
    fixed_effects: list[list[str]] = field(default_factory=list)  # FE options (each a list of cols)
    cluster: list[str] = field(default_factory=list)  # cluster-SE options ("" = robust HC1)
    sample_filters: list[str] = field(default_factory=list)  # pandas .query strings ("" = full)
    estimator: str = "ols"  # ols | iv | logit
    instruments: list[str] = field(default_factory=list)  # for iv
    endogenous: str = ""  # for iv; defaults to `treatment`
    controls_mode: str = "auto"  # auto | powerset | allnone | incremental
    max_specs: int = 2000
    preferred_sign: int = 0  # +1 / -1 / 0(unknown): the paper's claimed direction

    # Optional design-specific checks (filled in only when relevant)
    running_var: str = ""  # RDD: the running/forcing variable
    cutoff: float | None = None  # RDD: the threshold
    unit: str = ""  # DiD: unit id column
    time: str = ""  # DiD: time column
    treated: str = ""  # DiD: 0/1 treated-unit indicator
    treat_time: float | None = None  # DiD: treatment onset time

    @classmethod
    def from_yaml(cls, path: str | Path) -> SpecConfig:
        with open(path, encoding="utf-8") as fh:
            d = yaml.safe_load(fh) or {}
        return cls(
            data=d["data"],
            outcome=d["outcome"],
            treatment=d["treatment"],
            controls_pool=list(d.get("controls_pool", [])),
            fixed_effects=[list(x) if isinstance(x, list) else [x] for x in d.get("fixed_effects", [])],
            cluster=list(d.get("cluster", [])),
            sample_filters=list(d.get("sample_filters", [])),
            estimator=d.get("estimator", "ols"),
            instruments=list(d.get("instruments", [])),
            endogenous=d.get("endogenous", ""),
            controls_mode=d.get("controls_mode", "auto"),
            max_specs=int(d.get("max_specs", 2000)),
            preferred_sign=int(d.get("preferred_sign", 0)),
            running_var=d.get("running_var", ""),
            cutoff=d.get("cutoff"),
            unit=d.get("unit", ""),
            time=d.get("time", ""),
            treated=d.get("treated", ""),
            treat_time=d.get("treat_time"),
        )

    def to_yaml(self) -> str:
        return yaml.safe_dump({
            "data": self.data,
            "outcome": self.outcome,
            "treatment": self.treatment,
            "controls_pool": self.controls_pool,
            "fixed_effects": self.fixed_effects,
            "cluster": self.cluster,
            "sample_filters": self.sample_filters,
            "estimator": self.estimator,
            "instruments": self.instruments,
            "endogenous": self.endogenous,
            "controls_mode": self.controls_mode,
            "max_specs": self.max_specs,
            "preferred_sign": self.preferred_sign,
            "running_var": self.running_var,
            "cutoff": self.cutoff,
            "unit": self.unit,
            "time": self.time,
            "treated": self.treated,
            "treat_time": self.treat_time,
        }, sort_keys=False)


@dataclass
class SpecResult:
    coef: float
    se: float
    t: float
    p: float
    n: int
    spec: dict[str, Any]

    @property
    def significant(self) -> bool:
        return self.p < 0.05

    @property
    def sign(self) -> int:
        return 1 if self.coef > 0 else (-1 if self.coef < 0 else 0)


@dataclass
class SpecCurve:
    results: list[SpecResult]
    summary: dict[str, Any]
    preferred: SpecResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "preferred": _res_dict(self.preferred) if self.preferred else None,
            "n_results": len(self.results),
            "results": [_res_dict(r) for r in self.results],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SpecCurve:
        def _r(x):
            return SpecResult(coef=x["coef"], se=x["se"], t=x.get("t", 0.0),
                              p=x["p"], n=x.get("n", 0), spec=x.get("spec", {}))
        pref = d.get("preferred")
        return cls(results=[_r(x) for x in d.get("results", [])],
                   summary=d.get("summary", {}),
                   preferred=_r(pref) if pref else None)


def _res_dict(r: SpecResult) -> dict[str, Any]:
    return {"coef": round(r.coef, 6), "se": round(r.se, 6), "t": round(r.t, 3),
            "p": round(r.p, 5), "n": r.n, "spec": r.spec}
