"""Value-at-risk backtesting for Directional Forex ML research."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def historical_var_series(returns: pd.Series, *, window: int = 250, alpha: float = 0.05) -> pd.Series:
    """Rolling historical VaR as a negative return threshold."""
    return returns.rolling(window).quantile(alpha).rename("historical_var")


def parametric_var_series(returns: pd.Series, *, window: int = 250, alpha: float = 0.05) -> pd.Series:
    """Rolling normal VaR as a negative return threshold."""
    z_value = _normal_ppf(alpha)
    mean = returns.rolling(window).mean()
    std = returns.rolling(window).std(ddof=0)
    return (mean + z_value * std).rename("parametric_var")


def ewma_var_series(returns: pd.Series, *, lambda_: float = 0.94, alpha: float = 0.05) -> pd.Series:
    """EWMA RiskMetrics-style VaR as a negative return threshold."""
    z_value = _normal_ppf(alpha)
    variance = returns.pow(2).ewm(alpha=1.0 - lambda_, adjust=False).mean()
    return (z_value * np.sqrt(variance)).rename("ewma_var")


def backtest_var(
    returns: pd.Series,
    var: pd.Series,
    *,
    alpha: float = 0.05,
) -> dict[str, float | int | None]:
    """Backtest VaR violations with Kupiec and Christoffersen diagnostics."""
    aligned = pd.concat([returns.rename("returns"), var.rename("var")], axis=1).dropna()
    if aligned.empty:
        return {
            "observations": 0,
            "violations": 0,
            "violation_rate": None,
            "kupiec_lr": None,
            "kupiec_p_value": None,
            "christoffersen_lr": None,
            "christoffersen_p_value": None,
        }
    violations = aligned["returns"] < aligned["var"]
    kupiec_lr, kupiec_p = kupiec_pof_test(int(violations.sum()), int(len(violations)), alpha=alpha)
    christ_lr, christ_p = christoffersen_independence_test(violations)
    return {
        "observations": int(len(violations)),
        "violations": int(violations.sum()),
        "violation_rate": float(violations.mean()),
        "kupiec_lr": kupiec_lr,
        "kupiec_p_value": kupiec_p,
        "christoffersen_lr": christ_lr,
        "christoffersen_p_value": christ_p,
    }


def run_var_backtests(
    returns: pd.Series,
    *,
    window: int = 250,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """Run historical, parametric, and EWMA VaR backtests."""
    models = {
        "historical": historical_var_series(returns, window=window, alpha=alpha),
        "parametric": parametric_var_series(returns, window=window, alpha=alpha),
        "ewma": ewma_var_series(returns, alpha=alpha),
    }
    rows = []
    for name, var in models.items():
        rows.append({"var_model": name, **backtest_var(returns, var, alpha=alpha)})
    return pd.DataFrame(rows)


def kupiec_pof_test(violations: int, observations: int, *, alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Kupiec proportion-of-failures likelihood-ratio test."""
    if observations <= 0:
        return None, None
    p_hat = violations / observations
    if p_hat <= 0 or p_hat >= 1:
        return None, None
    lr = -2.0 * (
        (observations - violations) * math.log((1.0 - alpha) / (1.0 - p_hat))
        + violations * math.log(alpha / p_hat)
    )
    return float(lr), _chi2_sf_1(lr)


def christoffersen_independence_test(violations: pd.Series) -> tuple[float | None, float | None]:
    """Christoffersen first-order independence test for clustered VaR breaches."""
    x = violations.astype(int).to_numpy()
    if len(x) < 2:
        return None, None
    n00 = n01 = n10 = n11 = 0
    for prev, curr in zip(x[:-1], x[1:]):
        if prev == 0 and curr == 0:
            n00 += 1
        elif prev == 0 and curr == 1:
            n01 += 1
        elif prev == 1 and curr == 0:
            n10 += 1
        else:
            n11 += 1
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    if any(value in {0.0, 1.0} for value in (pi, pi0, pi1)):
        return None, None
    unrestricted = ((1 - pi0) ** n00) * (pi0**n01) * ((1 - pi1) ** n10) * (pi1**n11)
    restricted = ((1 - pi) ** (n00 + n10)) * (pi ** (n01 + n11))
    if unrestricted <= 0 or restricted <= 0:
        return None, None
    lr = -2.0 * math.log(restricted / unrestricted)
    return float(lr), _chi2_sf_1(lr)


def _normal_ppf(alpha: float) -> float:
    try:
        from scipy import stats

        return float(stats.norm.ppf(alpha))
    except ImportError:
        return -1.6448536269514729 if alpha == 0.05 else float(np.quantile(np.random.default_rng(1).normal(size=100_000), alpha))


def _chi2_sf_1(value: float) -> float | None:
    try:
        from scipy import stats

        return float(stats.chi2.sf(value, 1))
    except ImportError:
        return None

