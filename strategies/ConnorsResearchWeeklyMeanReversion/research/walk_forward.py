"""Walk-forward validation for Connors Weekly Mean Reversion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from strategies.ConnorsResearchWeeklyMeanReversion.core import (
    ConnorsWeeklyMeanReversionConfig,
    backtest_connors_weekly_mean_reversion,
    compute_asset_performance,
    compute_portfolio_metrics,
)


@dataclass(frozen=True)
class ConnorsWalkForwardConfig:
    """Chronological walk-forward split settings."""

    train_size: int = 756
    test_size: int = 126
    step_size: int = 126
    window_type: Literal["rolling", "expanding"] = "rolling"
    purge_size: int = 0
    embargo_size: int = 5


@dataclass(frozen=True)
class ConnorsWalkForwardFold:
    """One chronological train/test fold."""

    fold: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def split_walk_forward(data: pd.DataFrame, config: ConnorsWalkForwardConfig) -> list[ConnorsWalkForwardFold]:
    """Create chronological train/test folds with optional purge and embargo gaps."""
    _validate_walk_forward_config(config)
    min_required = config.train_size + config.purge_size + config.embargo_size + config.test_size
    if len(data) < min_required:
        raise ValueError(f"Need at least {min_required} rows for walk-forward validation, got {len(data)}")

    folds: list[ConnorsWalkForwardFold] = []
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
        if effective_train_end <= train_start:
            raise ValueError("purge_size removes the entire train window")

        train_indices = np.arange(train_start, effective_train_end)
        test_indices = np.arange(test_start, test_end)
        folds.append(
            ConnorsWalkForwardFold(
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


def run_connors_walk_forward(
    prices: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    walk_config: ConnorsWalkForwardConfig | None = None,
    strategy_config: ConnorsWeeklyMeanReversionConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int | None]]:
    """Evaluate Connors on unseen test windows using train data as warmup."""
    wf_config = walk_config or ConnorsWalkForwardConfig()
    strategy_cfg = strategy_config or ConnorsWeeklyMeanReversionConfig()
    clean_prices = prices.sort_index().astype(float).ffill()
    clean_volumes = volumes.reindex(clean_prices.index).sort_index().astype(float).ffill().fillna(0.0)
    records: list[dict[str, object]] = []
    asset_records: list[pd.DataFrame] = []

    for fold in split_walk_forward(clean_prices, wf_config):
        train_prices = clean_prices.iloc[fold.train_indices]
        train_volumes = clean_volumes.iloc[fold.train_indices]
        context_start = int(fold.train_indices[0])
        context_end = int(fold.test_indices[-1]) + 1
        context_prices = clean_prices.iloc[context_start:context_end]
        context_volumes = clean_volumes.iloc[context_start:context_end]
        test_index = clean_prices.index[fold.test_indices]

        train_result = backtest_connors_weekly_mean_reversion(train_prices, train_volumes, strategy_cfg)
        context_result = backtest_connors_weekly_mean_reversion(
            context_prices,
            context_volumes,
            strategy_cfg,
            trade_start=fold.test_start,
        )
        test_returns = context_result.returns.reindex(test_index).fillna(0.0)
        test_equity = strategy_cfg.initial_cash * (1.0 + test_returns).cumprod()
        test_drawdown = test_equity / test_equity.cummax() - 1.0
        test_trades = context_result.trades.loc[
            (pd.to_datetime(context_result.trades["timestamp"]) >= fold.test_start)
            & (pd.to_datetime(context_result.trades["timestamp"]) <= fold.test_end)
        ] if not context_result.trades.empty else context_result.trades
        test_metrics = compute_portfolio_metrics(test_returns, test_equity, test_drawdown, test_trades, strategy_cfg)

        records.append(
            {
                "fold": fold.fold,
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "train_rows": len(train_prices),
                "test_rows": len(test_index),
                "train_total_return": train_result.metrics.get("total_return"),
                "train_sharpe_ratio": train_result.metrics.get("sharpe_ratio"),
                "train_max_drawdown": train_result.metrics.get("max_drawdown"),
                "train_trade_count": train_result.metrics.get("trade_count"),
                "test_total_return": test_metrics.get("total_return"),
                "test_sharpe_ratio": test_metrics.get("sharpe_ratio"),
                "test_max_drawdown": test_metrics.get("max_drawdown"),
                "test_trade_count": test_metrics.get("trade_count"),
            }
        )

        test_context_result = replace(
            context_result,
            prices=context_result.prices.reindex(test_index),
            volumes=context_result.volumes.reindex(test_index),
            target_weights=context_result.target_weights.reindex(test_index).fillna(0.0),
            weights=context_result.weights.reindex(test_index).fillna(0.0),
            returns=test_returns,
            equity=test_equity,
            drawdown=test_drawdown,
            trades=test_trades,
        )
        fold_asset_performance = compute_asset_performance(test_context_result)
        fold_asset_performance.insert(0, "fold", fold.fold)
        fold_asset_performance.insert(1, "test_start", fold.test_start)
        fold_asset_performance.insert(2, "test_end", fold.test_end)
        asset_records.append(fold_asset_performance)

    results = pd.DataFrame(records)
    assets = pd.concat(asset_records, ignore_index=True) if asset_records else pd.DataFrame()
    return results, assets, summarize_walk_forward(results)


def summarize_walk_forward(results: pd.DataFrame) -> dict[str, float | int | None]:
    """Aggregate fold-level out-of-sample metrics."""
    if results.empty:
        return {
            "folds": 0,
            "oos_total_return_mean": None,
            "oos_total_return_compound": None,
            "oos_sharpe_mean": None,
            "oos_max_drawdown_worst": None,
            "oos_trade_count_total": 0,
            "profitable_folds": 0,
            "train_test_sharpe_ratio": None,
        }
    test_returns = pd.to_numeric(results["test_total_return"], errors="coerce").dropna()
    test_sharpes = pd.to_numeric(results["test_sharpe_ratio"], errors="coerce").dropna()
    train_sharpes = pd.to_numeric(results["train_sharpe_ratio"], errors="coerce").dropna()
    mean_train_sharpe = float(train_sharpes.mean()) if len(train_sharpes) else None
    mean_test_sharpe = float(test_sharpes.mean()) if len(test_sharpes) else None
    return {
        "folds": int(len(results)),
        "oos_total_return_mean": _mean_or_none(results["test_total_return"]),
        "oos_total_return_compound": float((1.0 + test_returns).prod() - 1.0) if len(test_returns) else None,
        "oos_sharpe_mean": mean_test_sharpe,
        "oos_max_drawdown_worst": _min_or_none(results["test_max_drawdown"]),
        "oos_trade_count_total": int(pd.to_numeric(results["test_trade_count"], errors="coerce").fillna(0).sum()),
        "profitable_folds": int((pd.to_numeric(results["test_total_return"], errors="coerce").fillna(0.0) > 0.0).sum()),
        "train_test_sharpe_ratio": (
            mean_test_sharpe / mean_train_sharpe
            if mean_train_sharpe is not None and mean_train_sharpe != 0 and mean_test_sharpe is not None
            else None
        ),
    }


def _validate_walk_forward_config(config: ConnorsWalkForwardConfig) -> None:
    if config.train_size < 50:
        raise ValueError("train_size must be at least 50")
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
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.mean()) if len(clean) else None


def _min_or_none(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.min()) if len(clean) else None
