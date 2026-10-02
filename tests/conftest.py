from __future__ import annotations

import pytest

PAPER = """Minimum Wages and Teen Employment: Evidence from a Border Design

Abstract
We estimate the effect of a state minimum wage increase on teen employment using a
difference-in-differences design. Employment rose by 2.8 percentage points in treated
counties. The data are available at https://zenodo.org/records/1234567 for replication.

1. Introduction
We are the first to study this question with county-level border pairs. Our results show
that minimum wages cause higher employment for all workers in every state.

2. Data
We restrict the sample to counties surveyed in both waves between 1992 and 1993.

3. Empirical Strategy
We estimate a two-way fixed effects model with standard errors clustered by county.
The coefficient on treatment is 0.12*** (0.10) in the preferred specification.
Another estimate gives t(48) = 2.10, p = .40 for the placebo.

4. Results
Table 2 reports the main estimate, 2.8 (1.1), with N = 410 restaurants.

5. Conclusion
Minimum wages unambiguously raise employment.
"""


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECONOCLAST_HOME", str(tmp_path / "home"))
    yield


@pytest.fixture
def paper_file(tmp_path):
    p = tmp_path / "minwage.txt"
    p.write_text(PAPER, encoding="utf-8")
    return p
