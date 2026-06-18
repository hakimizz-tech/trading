"""Walk-forward validation for the Bollinger Band strategy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
import pandas as pd

from strategies.BollingerBand.backtesting.vectorbt_engine import (
    VectorBTBacktestConfig,
    optimize_bollinger_vectorbt,
    run_bollinger_vectorbt,
)
from strategies.BollingerBand.core import AdaptiveRegimeConfig, ExitPlan


@dataclass(frozen=True)
class WalkForwardConfig:
    train_size: int
    test_size: int
    step_size: int
    window_type: Literal["rolling", "expanding"] = "rolling"
    purge_size: int = 0
    embargo_size: int = 0


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


DEFAULT_PARAMETER_GRID: dict[str, list[Any]] = {
    "bb_window": [20],
    "bb_num_std": [2.0],
    "squeeze_quantile": [0.20],
    "wide_quantile": [0.60],
}


def split_walk_forward(data: pd.DataFrame, config: WalkForwardConfig) -> list[WalkForwardFold]:
    """Create chronological train/test folds with optional purge and embargo gaps."""
    _validate_walk_forward_config(config)
    min_required = config.train_size + config.purge_size + config.embargo_size + config.test_size
    if len(data) < min_required:
        raise ValueError(f"Need at least {min_required} rows for walk-forward validation, got {len(data)}")

    folds: list[WalkForwardFold] = []
    offset = 0
    while True:
        if config.window_type == "rolling":
            train_start = offset
            train_end = offset + config.train_size
        else:
            train_start = 0
            train_end = config.train_size + offset

        effective_train_end = train_end - config.purge_size
        test_start = train_end + config.embargo_size
        test_end = test_start + config.test_size
        if test_end > len(data):
            break

        train_indices = np.arange(train_start, effective_train_end)
        test_indices = np.arange(test_start, test_end)
        folds.append(
            WalkForwardFold(
                fold=len(folds),
                train_indices=train_indices,
                test_indices=test_indices,
                train_start=pd.Timestamp(data.index[train_indices[0]]),
                train_end=pd.Timestamp(data.index[train_indices[-1]]),
                test_start=pd.Timestamp(data.index[test_indices[0]]),
                test_end=pd.Timestamp(data.index[test_indices[-1]]),
            )
        )
        offset += config.step_size

    return folds


def run_bollinger_walk_forward(
    data: pd.DataFrame,
    *,
    walk_config: WalkForwardConfig,
    parameter_grid: dict[str, list[Any]] | None = None,
    base_adaptive_config: AdaptiveRegimeConfig | None = None,
    exit_plan: ExitPlan | None = None,
    vectorbt_config: VectorBTBacktestConfig | None = None,
    strategy: str = "adaptive",
    optimize_by: str = "sharpe_ratio",
) -> pd.DataFrame:
    """Optimize on each training window and evaluate the best params OOS."""
    grid = parameter_grid or DEFAULT_PARAMETER_GRID
    base_config = base_adaptive_config or AdaptiveRegimeConfig()
    records: list[dict[str, Any]] = []

    for fold in split_walk_forward(data, walk_config):
        train = data.iloc[fold.train_indices]
        test = data.iloc[fold.test_indices]
        train_results = optimize_bollinger_vectorbt(
            train,
            grid,
            strategy=strategy,
            base_adaptive_config=base_config,
            exit_plan=exit_plan,
            config=vectorbt_config,
            sort_by=optimize_by,
            ascending=False,
        )
        best = train_results.iloc[0].to_dict()
        selected_params = {name: best[name] for name in grid}
        selected_config = replace(base_config, **selected_params)

        test_result = run_bollinger_vectorbt(
            test,
            strategy=strategy,
            adaptive_config=selected_config,
            exit_plan=exit_plan,
            config=vectorbt_config,
        )

        records.append(
            {
                "fold": fold.fold,
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "train_rows": len(train),
                "test_rows": len(test),
                **{f"param_{name}": value for name, value in selected_params.items()},
                "train_total_return": best.get("total_return"),
                "train_sharpe_ratio": best.get("sharpe_ratio"),
                "train_max_drawdown": best.get("max_drawdown"),
                "train_trade_count": best.get("trade_count"),
                "test_total_return": test_result.metrics.get("total_return"),
                "test_sharpe_ratio": test_result.metrics.get("sharpe_ratio"),
                "test_max_drawdown": test_result.metrics.get("max_drawdown"),
                "test_win_rate": test_result.metrics.get("win_rate"),
                "test_profit_factor": test_result.metrics.get("profit_factor"),
                "test_trade_count": test_result.metrics.get("trade_count"),
                "test_end_value": test_result.metrics.get("end_value"),
            }
        )

    return pd.DataFrame(records)


def summarize_walk_forward(results: pd.DataFrame) -> dict[str, float | int | None]:
    """Aggregate fold-level out-of-sample metrics."""
    if results.empty:
        return {
            "folds": 0,
            "oos_total_return_mean": None,
            "oos_sharpe_mean": None,
            "oos_max_drawdown_worst": None,
            "oos_trade_count_total": 0,
            "profitable_folds": 0,
        }
    return {
        "folds": int(len(results)),
        "oos_total_return_mean": _mean_or_none(results["test_total_return"]),
        "oos_sharpe_mean": _mean_or_none(results["test_sharpe_ratio"]),
        "oos_max_drawdown_worst": _min_or_none(results["test_max_drawdown"]),
        "oos_trade_count_total": int(results["test_trade_count"].fillna(0).sum()),
        "profitable_folds": int((results["test_total_return"].fillna(0.0) > 0.0).sum()),
    }


def _validate_walk_forward_config(config: WalkForwardConfig) -> None:
    if config.train_size < 10:
        raise ValueError("train_size must be at least 10")
    if config.test_size < 1:
        raise ValueError("test_size must be positive")
    if config.step_size < 1:
        raise ValueError("step_size must be positive")
    if config.purge_size < 0:
        raise ValueError("purge_size must not be negative")
    if config.embargo_size < 0:
        raise ValueError("embargo_size must not be negative")
    if config.window_type not in {"rolling", "expanding"}:
        raise ValueError("window_type must be 'rolling' or 'expanding'")


def _mean_or_none(values: pd.Series) -> float | None:
    clean = values.dropna()
    return float(clean.mean()) if len(clean) else None


def _min_or_none(values: pd.Series) -> float | None:
    clean = values.dropna()
    return float(clean.min()) if len(clean) else None
