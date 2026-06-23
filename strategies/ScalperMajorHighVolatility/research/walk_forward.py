"""Walk-forward validation for Scalper Major High Volatility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from strategies.ScalperMajorHighVolatility.core import ScalperMajorConfig, backtest_scalper_major


@dataclass(frozen=True)
class ScalperMajorWalkForwardConfig:
    """Chronological train/test split settings."""

    train_size: int = 1_000
    test_size: int = 250
    step_size: int = 250
    window_type: Literal["rolling", "expanding"] = "rolling"
    purge_size: int = 0
    embargo_size: int = 0


@dataclass(frozen=True)
class ScalperMajorWalkForwardFold:
    """One chronological train/test fold."""

    fold: int
    train_indices: np.ndarray
    test_indices: np.ndarray
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def split_walk_forward(data: pd.DataFrame, config: ScalperMajorWalkForwardConfig) -> list[ScalperMajorWalkForwardFold]:
    """Create chronological folds with optional purge and embargo gaps."""
    _validate_config(config)
    min_required = config.train_size + config.purge_size + config.embargo_size + config.test_size
    if len(data) < min_required:
        raise ValueError(f"Need at least {min_required} rows for walk-forward validation, got {len(data)}")
    folds: list[ScalperMajorWalkForwardFold] = []
    offset = 0
    while True:
        train_start = 0 if config.window_type == "expanding" else offset
        train_end = offset + config.train_size
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
            ScalperMajorWalkForwardFold(
                fold=len(folds),
                train_indices=train_indices,
                test_indices=test_indices,
                train_start=_timestamp_at(data.index, int(train_indices[0])),
                train_end=_timestamp_at(data.index, int(train_indices[-1])),
                test_start=_timestamp_at(data.index, int(test_indices[0])),
                test_end=_timestamp_at(data.index, int(test_indices[-1])),
            )
        )
        offset += config.step_size
    return folds


def run_scalper_major_walk_forward(
    ohlcv: pd.DataFrame,
    *,
    walk_config: ScalperMajorWalkForwardConfig | None = None,
    strategy_config: ScalperMajorConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, float | int | None]]:
    """Evaluate the strategy on unseen chronological test windows."""
    wf_cfg = walk_config or ScalperMajorWalkForwardConfig()
    strategy_cfg = strategy_config or ScalperMajorConfig()
    clean = ohlcv.sort_index()
    records: list[dict[str, object]] = []
    for fold in split_walk_forward(clean, wf_cfg):
        train = clean.iloc[fold.train_indices]
        context = clean.iloc[fold.train_indices[0] : fold.test_indices[-1] + 1]
        test_index = clean.index[fold.test_indices]
        train_result = backtest_scalper_major(train, strategy_cfg)
        context_result = backtest_scalper_major(context, strategy_cfg, trade_start=fold.test_start)
        test_returns = context_result.returns.reindex(test_index).fillna(0.0)
        test_equity = strategy_cfg.initial_cash * (1.0 + test_returns).cumprod()
        test_drawdown = test_equity / test_equity.cummax() - 1.0
        test_trades = (
            context_result.trades.loc[pd.to_datetime(context_result.trades["exit_timestamp"]).between(fold.test_start, fold.test_end)]
            if not context_result.trades.empty
            else context_result.trades
        )
        test_metrics = backtest_scalper_major(context.reindex(test_index).dropna(), strategy_cfg).metrics if len(test_index) else {}
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
                "train_trades": train_result.metrics.get("trade_count"),
                "test_total_return": float(test_equity.iloc[-1] / test_equity.iloc[0] - 1.0) if len(test_equity) else None,
                "test_sharpe_ratio": test_metrics.get("sharpe_ratio"),
                "test_max_drawdown": float(test_drawdown.min()) if len(test_drawdown) else None,
                "test_trades": int(len(test_trades)),
            }
        )
    results = pd.DataFrame(records)
    return results, summarize_walk_forward(results)


def summarize_walk_forward(results: pd.DataFrame) -> dict[str, float | int | None]:
    """Aggregate fold-level out-of-sample metrics."""
    if results.empty:
        return {
            "folds": 0,
            "oos_total_return_mean": None,
            "oos_total_return_compound": None,
            "oos_sharpe_mean": None,
            "oos_max_drawdown_worst": None,
            "oos_trades_total": 0,
            "profitable_folds": 0,
        }
    returns = pd.to_numeric(results["test_total_return"], errors="coerce").dropna()
    return {
        "folds": int(len(results)),
        "oos_total_return_mean": _mean_or_none(results["test_total_return"]),
        "oos_total_return_compound": _compound_return_or_none(returns),
        "oos_sharpe_mean": _mean_or_none(results["test_sharpe_ratio"]),
        "oos_max_drawdown_worst": _min_or_none(results["test_max_drawdown"]),
        "oos_trades_total": int(pd.to_numeric(results["test_trades"], errors="coerce").fillna(0).sum()),
        "profitable_folds": int((pd.to_numeric(results["test_total_return"], errors="coerce").fillna(0.0) > 0.0).sum()),
    }


def _validate_config(config: ScalperMajorWalkForwardConfig) -> None:
    if config.train_size < 50:
        raise ValueError("train_size must be at least 50")
    if config.test_size <= 0 or config.step_size <= 0:
        raise ValueError("test_size and step_size must be positive")
    if config.purge_size < 0 or config.embargo_size < 0:
        raise ValueError("purge_size and embargo_size must not be negative")
    if config.window_type not in {"rolling", "expanding"}:
        raise ValueError("window_type must be 'rolling' or 'expanding'")


def _timestamp_at(index: pd.Index, position: int) -> pd.Timestamp:
    values = index.to_numpy()
    return pd.Timestamp(values[position])


def _compound_return_or_none(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return None
    factors = 1.0 + clean.to_numpy(dtype=np.float64)
    return float(np.prod(factors) - 1.0)


def _mean_or_none(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.mean()) if len(clean) else None


def _min_or_none(values: pd.Series) -> float | None:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    return float(clean.min()) if len(clean) else None
