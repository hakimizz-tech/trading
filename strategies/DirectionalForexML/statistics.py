"""Statistical validation helpers for Directional Forex ML research."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StatisticalTestResult:
    """Compact statistical test output for report tables."""

    statistic: float | None
    p_value: float | None
    significant: bool | None


def paired_return_tests(
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    *,
    alpha: float = 0.05,
) -> dict[str, StatisticalTestResult]:
    """Run paired t-test and Wilcoxon test against a benchmark return stream."""
    aligned = pd.concat(
        [strategy_returns.rename("strategy"), benchmark_returns.rename("benchmark")],
        axis=1,
    ).dropna()
    if aligned.empty:
        return {
            "paired_t": StatisticalTestResult(None, None, None),
            "wilcoxon": StatisticalTestResult(None, None, None),
        }
    diff = aligned["strategy"] - aligned["benchmark"]
    return {
        "paired_t": _paired_t_test(diff, alpha=alpha),
        "wilcoxon": _wilcoxon_signed_rank(diff, alpha=alpha),
    }


def bootstrap_confidence_interval(
    values: pd.Series,
    *,
    samples: int = 1_000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> tuple[float | None, float | None]:
    """Return a bootstrap confidence interval for the mean."""
    clean = values.dropna().astype(float).to_numpy()
    if clean.size == 0:
        return None, None
    rng = np.random.default_rng(random_state)
    boot = np.array([rng.choice(clean, size=clean.size, replace=True).mean() for _ in range(samples)])
    lower = (1.0 - confidence) / 2.0
    upper = 1.0 - lower
    return float(np.quantile(boot, lower)), float(np.quantile(boot, upper))


def superior_predictive_ability_test(
    strategy_returns: pd.DataFrame,
    benchmark_returns: pd.Series,
    *,
    samples: int = 1_000,
    random_state: int = 42,
) -> dict[str, float | int | None]:
    """Approximate Hansen-style SPA bootstrap over model excess returns.

    This is a practical bootstrap screen, not a full econometric SPA package.
    It controls for multiple tested models by bootstrapping the maximum t-stat.
    """
    aligned = strategy_returns.join(benchmark_returns.rename("benchmark"), how="inner").dropna()
    if aligned.empty or len(aligned.columns) <= 1:
        return {"best_t_stat": None, "bootstrap_critical_value_95": None, "significant_models": 0}
    excess = aligned.drop(columns=["benchmark"]).sub(aligned["benchmark"], axis=0)
    std = excess.std(ddof=1).replace(0.0, np.nan)
    t_stats = (excess.mean() / (std / np.sqrt(len(excess)))).dropna()
    if t_stats.empty:
        return {"best_t_stat": None, "bootstrap_critical_value_95": None, "significant_models": 0}
    rng = np.random.default_rng(random_state)
    centered = excess - excess.mean()
    max_stats = []
    for _ in range(samples):
        sample = centered.iloc[rng.integers(0, len(centered), len(centered))]
        sample_std = sample.std(ddof=1).replace(0.0, np.nan)
        boot_t = (sample.mean() / (sample_std / np.sqrt(len(sample)))).dropna()
        if not boot_t.empty:
            max_stats.append(float(boot_t.max()))
    critical = None if not max_stats else float(np.quantile(max_stats, 0.95))
    best = float(t_stats.max())
    significant = 0 if critical is None else int((t_stats > critical).sum())
    return {
        "best_t_stat": best,
        "bootstrap_critical_value_95": critical,
        "significant_models": significant,
    }


def _paired_t_test(diff: pd.Series, *, alpha: float) -> StatisticalTestResult:
    clean = diff.dropna().astype(float)
    if len(clean) < 2 or clean.std(ddof=1) == 0:
        return StatisticalTestResult(None, None, None)
    try:
        from scipy import stats

        statistic, p_value = stats.ttest_1samp(clean, 0.0)
        return StatisticalTestResult(float(statistic), float(p_value), bool(p_value < alpha))
    except ImportError:
        statistic = float(clean.mean() / (clean.std(ddof=1) / np.sqrt(len(clean))))
        return StatisticalTestResult(statistic, None, None)


def _wilcoxon_signed_rank(diff: pd.Series, *, alpha: float) -> StatisticalTestResult:
    clean = diff.dropna().astype(float)
    clean = clean[clean != 0.0]
    if len(clean) < 2:
        return StatisticalTestResult(None, None, None)
    try:
        from scipy import stats

        statistic, p_value = stats.wilcoxon(clean)
        return StatisticalTestResult(float(statistic), float(p_value), bool(p_value < alpha))
    except ImportError:
        return StatisticalTestResult(None, None, None)

