import os
import sys

import numpy as np
import pandas as pd
import pytest
from scipy import stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from bi_stats import chi_squared_2x2, ols_robust, welch_t_test  # noqa: E402


def test_ols_recovers_known_coefficients():
    rng = np.random.default_rng(0)
    n = 20_000
    df = pd.DataFrame({"x": rng.normal(size=n), "g": rng.choice(["a", "b", "c"], size=n)})
    effect = {"a": 0.0, "b": 0.5, "c": -1.0}
    df["y"] = 2.0 + 3.0 * df["x"] + df["g"].map(effect) + rng.normal(scale=1 + abs(df["x"]), size=n)
    res = ols_robust(df, "y", ["x"], categorical=["g"])
    assert res.loc["x", "coef"] == pytest.approx(3.0, abs=0.05)
    assert res.loc["g_b", "coef"] == pytest.approx(0.5, abs=0.08)
    assert res.loc["g_c", "coef"] == pytest.approx(-1.0, abs=0.08)
    assert res.loc["x", "ci_low"] < 3.0 < res.loc["x", "ci_high"]


def test_welch_matches_scipy():
    rng = np.random.default_rng(1)
    a, b = rng.normal(4, 1, 500), rng.normal(3.5, 2, 300)
    r = welch_t_test(a, b)
    t, p = stats.ttest_ind(b, a, equal_var=False)
    assert r["t"] == pytest.approx(t) and r["p_value"] == pytest.approx(p)
    assert r["ci_low"] < r["diff"] < r["ci_high"]


def test_chi_squared_rates_and_independence():
    group = pd.Series([0] * 100 + [1] * 100)
    same = pd.Series(([1] * 10 + [0] * 90) * 2)
    r = chi_squared_2x2(group, same)
    assert r["rate_group0"] == pytest.approx(0.10) and r["rate_group1"] == pytest.approx(0.10)
    assert r["p_value"] == pytest.approx(1.0)
    differ = pd.Series([1] * 10 + [0] * 90 + [1] * 60 + [0] * 40)
    assert chi_squared_2x2(group, differ)["p_value"] < 1e-10
