"""Walk-forward validation for Connors Research Dynamic Treasuries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
import pandas as pd

from strategies.ConnorsResearchDynamicTreasuries.core import (
    DynamicTreasuriesConfig,
    backtest_dynamic_treasuries,
    compute_asset_performance,
    compute_duration_exposure,
    compute_portfolio_metrics,
)


@dataclass(frozen=True)
class DynamicTreasuriesWalkForwardConfig:
    """Chronological walk-forward split settings."""

    train_size: int = 756
    test_size: int = 126
    step_size: int = 126
    window_type: Literal["rolling", "expanding"] = "rolling"
    purge_size: int = 0
    embargo_size: int = 5


@dataclass(frozen=True)
class DynamicTreasuriesWalkForwardFold:
    """One chronological train/test fold."""

    fold: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def split_walk_forward(data: pd.DataFrame, config: DynamicTreasuriesWalkForwardConfig) -> list[DynamicTreasuriesWalkForwardFold]:
    """Create chronological train/test folds with optional purge and embargo gaps."""
    _validate_walk_forward_config(config)
    min_required = config.train_size + config.purge_size + config.embargo_size + config.test_size
    if len(data) < min_required:
        raise ValueError(f"Need at least {min_required} rows for walk-forward validation, got {len(data)}")

    folds: list[DynamicTreasuriesWalkForwardFold] = []
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
            DynamicTreasuriesWalkForwardFold(
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


def run_dynamic_treasuries_walk_forward(
    prices: pd.DataFrame,
    *,
    walk_config: DynamicTreasuriesWalkForwardConfig | None = None,
    strategy_config: DynamicTreasuriesConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float | int | None]]:
    """Evaluate Dynamic Treasuries on unseen test windows with train warmup."""
    wf_config = walk_config or DynamicTreasuriesWalkForwardConfig()
    strategy_cfg = strategy_config or DynamicTreasuriesConfig()
    clean = prices.sort_index().astype(float).ffill()
    records: list[dict[str, object]] = []
    asset_records: list[pd.DataFrame] = []

    for fold in split_walk_forward(clean, wf_config):
        train = clean.iloc[fold.train_indices]
        context_start = int(fold.train_indices[0])
        context_end = int(fold.test_indices[-1]) + 1
        context = clean.iloc[context_start:context_end]
        test_index = clean.index[fold.test_indices]

        train_result = backtest_dynamic_treasuries(train, strategy_cfg)
        context_result = backtest_dynamic_treasuries(context, strategy_cfg, trade_start=fold.test_start)
        test_returns = context_result.returns.reindex(test_index).fillna(0.0)
        test_equity = strategy_cfg.initial_cash * (1.0 + test_returns).cumprod()
        test_drawdown = test_equity / test_equity.cummax() - 1.0
        test_trades = (
            context_result.trades.loc[
                (pd.to_datetime(context_result.trades["timestamp"]) >= fold.test_start)
                & (pd.to_datetime(context_result.trades["timestamp"]) <= fold.test_end)
            ]
            if not context_result.trades.empty
            else context_result.trades
        )
        test_metrics = compute_portfolio_metrics(test_returns, test_equity, test_drawdown, test_trades, strategy_cfg)

        records.append(
            {
                "fold": fold.fold,
                "train_start": fold.train_start,
                "train_end": fold.train_end,
                "test_start": fold.test_start,
                "test_end": fold.test_end,
                "train_rows": len(train),
                "test_rows": len(test_index),
                "train_total_return": train_result.metrics.get("total_return"),
                "train_sharpe_ratio": train_result.metrics.get("sharpe_ratio"),
                "train_max_drawdown": train_result.metrics.get("max_drawdown"),
                "train_rebalance_count": train_result.metrics.get("rebalance_count"),
                "test_total_return": test_metrics.get("total_return"),
                "test_sharpe_ratio": test_metrics.get("sharpe_ratio"),
                "test_max_drawdown": test_metrics.get("max_drawdown"),
                "test_rebalance_count": test_metrics.get("rebalance_count"),
                "test_avg_duration": float(context_result.duration_exposure.reindex(test_index).mean()),
            }
        )

        test_context_result = replace(
            context_result,
            prices=context_result.prices.reindex(test_index),
            target_weights=context_result.target_weights.reindex(test_index).fillna(0.0),
            weights=context_result.weights.reindex(test_index).fillna(0.0),
            duration_exposure=compute_duration_exposure(context_result.weights.reindex(test_index).fillna(0.0)),
            returns=test_returns,
            equity=test_equity,
            drawdown=test_drawdown,
            trades=test_trades,
            asset_performance=compute_asset_performance(
                context_result.prices.reindex(test_index),
                context_result.weights.reindex(test_index).fillna(0.0),
                strategy_cfg,
            ),
        )
        fold_assets = test_context_result.asset_performance
        fold_assets.insert(0, "fold", fold.fold)
        fold_assets.insert(1, "test_start", fold.test_start)
        fold_assets.insert(2, "test_end", fold.test_end)
        asset_records.append(fold_assets)

    results = pd.DataFrame(records)
    non_empty_assets = [frame.dropna(axis=1, how="all") for frame in asset_records if not frame.empty]
    assets = pd.concat(non_empty_assets, ignore_index=True) if non_empty_assets else pd.DataFrame()
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
            "oos_rebalance_count_total": 0,
            "profitable_folds": 0,
            "mean_oos_duration": None,
        }
    test_returns = pd.to_numeric(results["test_total_return"], errors="coerce").dropna()
    return {
        "folds": int(len(results)),
        "oos_total_return_mean": _mean_or_none(results["test_total_return"]),
        "oos_total_return_compound": float((1.0 + test_returns).prod() - 1.0) if len(test_returns) else None,
        "oos_sharpe_mean": _mean_or_none(results["test_sharpe_ratio"]),
        "oos_max_drawdown_worst": _min_or_none(results["test_max_drawdown"]),
        "oos_rebalance_count_total": int(pd.to_numeric(results["test_rebalance_count"], errors="coerce").fillna(0).sum()),
        "profitable_folds": int((pd.to_numeric(results["test_total_return"], errors="coerce").fillna(0.0) > 0.0).sum()),
        "mean_oos_duration": _mean_or_none(results["test_avg_duration"]),
    }


def _validate_walk_forward_config(config: DynamicTreasuriesWalkForwardConfig) -> None:
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
