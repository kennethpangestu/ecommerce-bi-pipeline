"""Statistical tests used in the analysis, kept small and dependency-light.

* two-by-two chi-squared test (via scipy)
* Welch's t-test (via scipy)
* ordinary least squares with heteroskedasticity-robust (HC1) standard errors,
  written out with NumPy so every step is visible
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def chi_squared_2x2(group: pd.Series, outcome: pd.Series) -> dict:
    """Chi-squared test of independence between two binary columns.
    Returns the table, chi2, p-value, and each group's outcome rate."""
    table = pd.crosstab(group.astype(int), outcome.astype(int))
    chi2, p, dof, _ = stats.chi2_contingency(table, correction=False)
    rates = table[1] / table.sum(axis=1)
    return {"table": table, "chi2": float(chi2), "dof": int(dof), "p_value": float(p),
            "rate_group0": float(rates.loc[0]), "rate_group1": float(rates.loc[1])}


def welch_t_test(a: pd.Series, b: pd.Series) -> dict:
    """Welch's t-test (no equal-variance assumption) for mean(b) - mean(a), with a 95% CI."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    t, p = stats.ttest_ind(b, a, equal_var=False)
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = np.sqrt(va + vb)
    dof = (va + vb) ** 2 / (va ** 2 / (len(a) - 1) + vb ** 2 / (len(b) - 1))
    diff = b.mean() - a.mean()
    crit = stats.t.ppf(0.975, dof)
    return {"mean_a": a.mean(), "mean_b": b.mean(), "diff": diff, "t": float(t), "p_value": float(p),
            "ci_low": diff - crit * se, "ci_high": diff + crit * se}


def ols_robust(df: pd.DataFrame, y: str, x: list[str], categorical: list[str] | None = None) -> pd.DataFrame:
    """OLS of ``y`` on ``x`` (+ one-hot ``categorical`` columns, first level dropped),
    with HC1 robust standard errors. Returns coefficient, SE, t, p and 95% CI per term."""
    data = df[[y] + x + (categorical or [])].dropna()
    X = data[x].astype(float)
    for col in categorical or []:
        X = X.join(pd.get_dummies(data[col], prefix=col, drop_first=True, dtype=float))
    X.insert(0, "intercept", 1.0)
    Xm, ym = X.to_numpy(), data[y].to_numpy(dtype=float)
    n, k = Xm.shape
    beta, *_ = np.linalg.lstsq(Xm, ym, rcond=None)
    resid = ym - Xm @ beta
    xtx_inv = np.linalg.pinv(Xm.T @ Xm)
    meat = (Xm * resid[:, None] ** 2).T @ Xm
    cov = xtx_inv @ meat @ xtx_inv * n / (n - k)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), n - k)
    out = pd.DataFrame({"coef": beta, "se": se, "t": t, "p_value": p,
                        "ci_low": beta - 1.96 * se, "ci_high": beta + 1.96 * se}, index=X.columns)
    out.attrs.update(n=n, r2=1 - (resid @ resid) / ((ym - ym.mean()) @ (ym - ym.mean())))
    return out
