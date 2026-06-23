"""Walk-forward validation for Directional Forex ML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from market_data.ohlcv import validate_ohlcv
from strategies.DirectionalForexML.core import (
    DirectionalForexMLConfig,
    backtest_directional_forex_ml,
)


@dataclass(frozen=True)
class DirectionalForexMLWalkForwardConfig:
    """Rolling/expanding validation setup for forex ML research."""

    train_size: int = 1_000
    test_size: int = 250
    step_size: int = 250
    purge_size: int = 1
    embargo_size: int = 1
    window_type: Literal["rolling", "expanding"] = "rolling"

    def __post_init__(self) -> None:
        if self.train_size <= 0 or self.test_size <= 0 or self.step_size <= 0:
            raise ValueError("train_size, test_size, and step_size must be positive")
        if self.purge_size < 0 or self.embargo_size < 0:
            raise ValueError("purge_size and embargo_size must not be negative")
        if self.window_type not in {"rolling", "expanding"}:
            raise ValueError("window_type must be 'rolling' or 'expanding'")


def split_walk_forward(
    data: pd.DataFrame,
    config: DirectionalForexMLWalkForwardConfig,
) -> list[tuple[slice, slice]]:
    """Return train/test slices with purge and embargo between them."""
    rows = len(validate_ohlcv(data))
    folds: list[tuple[slice, slice]] = []
    train_start = 0
    train_end = config.train_size
    while True:
        test_start = train_end + config.purge_size + config.embargo_size
        test_end = test_start + config.test_size
        if test_end > rows:
            break
        folds.append((slice(train_start, train_end), slice(test_start, test_end)))
        train_end += config.step_size
        if config.window_type == "rolling":
            train_start += config.step_size
    return folds


def run_directional_forex_ml_walk_forward(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    walk_config: DirectionalForexMLWalkForwardConfig | None = None,
    strategy_config: DirectionalForexMLConfig | None = None,
    macro: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, dict[str, float | int | None]]:
    """Run fold-by-fold OOS validation."""
    data = validate_ohlcv(ohlcv)
    wf_cfg = walk_config or DirectionalForexMLWalkForwardConfig()
    strategy_cfg = strategy_config or DirectionalForexMLConfig()
    rows: list[dict[str, object]] = []
    for fold_id, (train_slice, test_slice) in enumerate(split_walk_forward(data, wf_cfg), start=1):
        train = data.iloc[train_slice]
        test = data.iloc[test_slice]
        combined = pd.concat([train, test])
        fold_macro = macro.reindex(combined.index) if macro is not None else None
        split_fraction = len(train) / len(combined)
        try:
            result = backtest_directional_forex_ml(
                combined,
                symbol=symbol,
                config=strategy_cfg,
                macro=fold_macro,
                train_fraction=split_fraction,
            )
            row = {
                "fold": fold_id,
                "train_start": train.index.min(),
                "train_end": train.index.max(),
                "test_start": test.index.min(),
                "test_end": test.index.max(),
                "train_rows": len(train),
                "test_rows": len(test),
                **result.metrics,
            }
        except ValueError as exc:
            row = {
                "fold": fold_id,
                "train_start": train.index.min(),
                "train_end": train.index.max(),
                "test_start": test.index.min(),
                "test_end": test.index.max(),
                "train_rows": len(train),
                "test_rows": len(test),
                "error": str(exc),
            }
        rows.append(row)
    frame = pd.DataFrame(rows)
    return frame, summarize_walk_forward(frame)


def summarize_walk_forward(results: pd.DataFrame) -> dict[str, float | int | None]:
    """Aggregate OOS fold metrics."""
    if results.empty:
        return {
            "folds": 0,
            "oos_total_return_mean": None,
            "oos_sharpe_mean": None,
            "oos_max_drawdown_worst": None,
            "oos_trades_total": 0,
            "profitable_folds": 0,
        }
    valid = results[results.get("error", pd.Series(index=results.index, dtype=object)).isna()].copy()
    if valid.empty:
        return {
            "folds": int(len(results)),
            "oos_total_return_mean": None,
            "oos_sharpe_mean": None,
            "oos_max_drawdown_worst": None,
            "oos_trades_total": 0,
            "profitable_folds": 0,
        }
    total_returns = pd.to_numeric(valid.get("total_return"), errors="coerce")
    sharpes = pd.to_numeric(valid.get("sharpe_ratio"), errors="coerce")
    drawdowns = pd.to_numeric(valid.get("max_drawdown"), errors="coerce")
    trade_counts = pd.to_numeric(valid.get("trade_count"), errors="coerce").fillna(0)
    return {
        "folds": int(len(results)),
        "valid_folds": int(len(valid)),
        "oos_total_return_mean": _safe_mean(total_returns),
        "oos_sharpe_mean": _safe_mean(sharpes),
        "oos_max_drawdown_worst": None if drawdowns.dropna().empty else float(drawdowns.min()),
        "oos_trades_total": int(trade_counts.sum()),
        "profitable_folds": int((total_returns > 0).sum()),
    }


def _safe_mean(values: pd.Series) -> float | None:
    clean = values.dropna()
    return None if clean.empty else float(np.mean(clean))
