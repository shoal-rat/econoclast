"""Turn a paper + a dataset into a replication spec, automatically.

This is the bridge that lets an economist say only "verify this paper": the model
reads the empirical section and the dataset's columns, then writes the
specification-curve config (which column is the outcome, which is the treatment,
what to vary). If the columns can't be mapped to the paper's specification we skip
rather than fabricate one.
"""

from __future__ import annotations

from econoclast.llm.base import Message
from econoclast.logging import get_logger
from econoclast.replication.models import SpecConfig

log = get_logger("agent.autoconfig")

_SYSTEM = (
    "You set up a specification-curve replication for an empirical economics paper. "
    "You are given the paper's empirical strategy and the columns of its dataset. Map the "
    "paper's headline result onto the data: identify the outcome, the focal treatment "
    "regressor, sensible controls to toggle, fixed-effects/clustering options, and the design. "
    "Use ONLY column names from the provided list; never invent one."
)

_CONTRACT = (
    'Return ONLY JSON: {"outcome": col, "treatment": col, "controls_pool": [cols], '
    '"fixed_effects": [[cols], ...], "cluster": [cols], "sample_filters": [pandas-query strings], '
    '"estimator": "ols|iv|logit", "preferred_sign": 1 or -1, '
    '"running_var": col_or_empty, "cutoff": number_or_null, '
    '"unit": col_or_empty, "time": col_or_empty, "treated": col_or_empty, "treat_time": number_or_null, '
    '"cohort": col_or_empty}. '
    "cohort is the per-unit first-treated period column for STAGGERED DiD (0 = never treated). "
    "Omit RDD/DiD fields (leave empty/null) unless the paper clearly uses that design."
)


def _data_preview(data_path: str, n: int = 3) -> tuple[list[str], str]:
    import pandas as pd

    suf = data_path.lower()
    if suf.endswith(".dta"):
        df = pd.read_stata(data_path, convert_categoricals=False)
        head = df.head(n)
    elif suf.endswith(".parquet"):
        df = pd.read_parquet(data_path)
        head = df.head(n)
    elif suf.endswith(".xlsx"):
        df = pd.read_excel(data_path, nrows=200)
        head = df.head(n)
    elif suf.endswith(".tsv"):
        df = pd.read_csv(data_path, sep="\t", nrows=200)
        head = df.head(n)
    else:
        df = pd.read_csv(data_path, nrows=200)
        head = df.head(n)
    cols = [str(c) for c in df.columns]
    dtypes = {str(c): str(df[c].dtype) for c in df.columns}
    preview = "columns (name:dtype):\n" + ", ".join(f"{c}:{dtypes[c]}" for c in cols)
    preview += "\n\nsample rows:\n" + head.to_csv(index=False)[:1500]
    return cols, preview


def generate_spec_config(paper, data_path: str, backend) -> SpecConfig | None:  # noqa: ANN001
    try:
        cols, preview = _data_preview(data_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read dataset columns: %s", exc)
        return None

    empirical = paper.section_text("strateg", "identif", "method", "data", "result", "estimat") or paper.text
    user = (
        f"PAPER (empirical sections, truncated):\n{empirical[:10000]}\n\n"
        f"DATASET {data_path}\n{preview}\n\n{_CONTRACT}"
    )
    try:
        resp = backend.complete("attacker", [
            Message(role="system", content=_SYSTEM + "\n\n" + _CONTRACT),
            Message(role="user", content=user),
        ], response_format="json")
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Auto-config LLM call failed: %s", exc)
        return None

    return _validate(data, cols, data_path)


def _validate(data, cols: list[str], data_path: str) -> SpecConfig | None:
    if not isinstance(data, dict):
        return None
    colset = set(cols)

    def _col(name) -> str:
        if not name:
            return ""
        if name in colset:
            return name
        # case-insensitive / fuzzy fallback
        low = {c.lower(): c for c in cols}
        if str(name).lower() in low:
            return low[str(name).lower()]
        return ""

    outcome = _col(data.get("outcome"))
    treatment = _col(data.get("treatment"))
    if not outcome or not treatment:
        log.warning("Auto-config could not map outcome/treatment to dataset columns.")
        return None

    controls = [c for c in (_col(x) for x in data.get("controls_pool", [])) if c and c not in (outcome, treatment)]
    fe = []
    for group in data.get("fixed_effects", []) or []:
        g = [c for c in (_col(x) for x in (group if isinstance(group, list) else [group])) if c]
        if g:
            fe.append(g)
    cluster = [c for c in (_col(x) for x in data.get("cluster", [])) if c]
    filters = [str(f) for f in data.get("sample_filters", []) if isinstance(f, str)]

    return SpecConfig(
        data=data_path,
        outcome=outcome,
        treatment=treatment,
        controls_pool=controls[:10],
        fixed_effects=fe[:4],
        cluster=cluster[:3],
        sample_filters=filters[:4],
        estimator=str(data.get("estimator", "ols")) if data.get("estimator") in ("ols", "iv", "logit") else "ols",
        preferred_sign=int(data.get("preferred_sign", 0) or 0),
        running_var=_col(data.get("running_var")),
        cutoff=_num(data.get("cutoff")),
        unit=_col(data.get("unit")),
        time=_col(data.get("time")),
        treated=_col(data.get("treated")),
        treat_time=_num(data.get("treat_time")),
        cohort=_col(data.get("cohort")),
    )


def _num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None
