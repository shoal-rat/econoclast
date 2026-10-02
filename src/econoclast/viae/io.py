"""Load any table a replication package is likely to ship."""

from __future__ import annotations

from pathlib import Path


def load_table(path: str):  # noqa: ANN201 - returns a pandas DataFrame
    import pandas as pd

    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".parquet":
        return pd.read_parquet(p)
    if suf == ".dta":
        return pd.read_stata(p, convert_categoricals=False)
    if suf in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if suf == ".tsv" or suf == ".tab":
        return pd.read_csv(p, sep="\t")
    if suf == ".feather":
        return pd.read_feather(p)
    if suf == ".sav":
        return pd.read_spss(p)
    if suf in (".rds", ".rdata"):
        raise ValueError("R data files: convert with Rscript (write.csv) first")
    if suf in (".csv", ".txt", ".dat", ""):
        return pd.read_csv(p, sep=None, engine="python")
    return pd.read_csv(p)
