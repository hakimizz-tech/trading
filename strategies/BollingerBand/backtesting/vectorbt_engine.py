"""vectorbt backtesting adapter.

This module is optional at runtime. Linux research can still use the pandas
backtester without vectorbt installed; calling this adapter gives a clear error
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from itertools import product
from typing import Any

import pandas as pd

from backtesting import VectorBTConfig, run_vectorbt
from strategies.BollingerBand.backtesting.signals import PreparedSignals, prepare_bollinger_signals
from strategies.BollingerBand.core import AdaptiveRegimeConfig, ExitPlan


@dataclass(frozen=True)
class VectorBTBacktestConfig:
    init_cash: float = 10_000.0
    fees: float = 0.003
    fixed_fees: float = 0.0
    slippage: float = 0.001
    size: float = 0.95
    size_type: str = "percent"
    freq: str | None = None
    use_stops: bool = True
    accumulate: bool = False
    cash_sharing: bool = False
    min_size: float | None = None
    max_size: float | None = None
    size_granularity: float | None = None
    upon_opposite_entry: str = "close"


@dataclass(frozen=True)
class VectorBTBacktestResult:
    portfolio: Any
    signals: PreparedSignals
    stats: pd.Series
    metrics: dict[str, float | int | None]
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series


def run_bollinger_vectorbt(
    data: pd.DataFrame,
    *,
    strategy: str = "adaptive",
    adaptive_config: AdaptiveRegimeConfig | None = None,
    exit_plan: ExitPlan | None = None,
    config: VectorBTBacktestConfig | None = None,
) -> VectorBTBacktestResult:
    """Run the Bollinger strategy through vectorbt Portfolio.from_signals."""
    cfg = config or VectorBTBacktestConfig()
    signals = prepare_bollinger_signals(
        data,
        strategy=strategy,
        adaptive_config=adaptive_config,
        exit_plan=exit_plan,
    )
    shared = run_vectorbt(signals, config=_to_shared_vectorbt_config(cfg))
    return VectorBTBacktestResult(
        portfolio=shared.portfolio,
        signals=shared.signals,
        stats=shared.stats,
        metrics=shared.metrics,
        trades=shared.trades,
        equity=shared.equity,
        returns=shared.returns,
        drawdown=shared.drawdown,
    )


def optimize_bollinger_vectorbt(
    data: pd.DataFrame,
    parameter_grid: Mapping[str, Sequence[Any]],
    *,
    strategy: str = "adaptive",
    base_adaptive_config: AdaptiveRegimeConfig | None = None,
    exit_plan: ExitPlan | None = None,
    config: VectorBTBacktestConfig | None = None,
    sort_by: str = "sharpe_ratio",
    ascending: bool = False,
) -> pd.DataFrame:
    """Run a parameter grid against the vectorbt adapter and return ranked metrics.

    The grid keys must be fields on ``AdaptiveRegimeConfig``. This keeps the
    optimizer reusable while preserving the strategy configuration as the single
    source of truth.
    """
    _validate_parameter_grid(parameter_grid)
    base_config = base_adaptive_config or AdaptiveRegimeConfig()
    records: list[dict[str, Any]] = []

    for values in product(*(parameter_grid[name] for name in parameter_grid)):
        params = dict(zip(parameter_grid.keys(), values))
        adaptive_config = replace(base_config, **params)
        result = run_bollinger_vectorbt(
            data,
            strategy=strategy,
            adaptive_config=adaptive_config,
            exit_plan=exit_plan,
            config=config,
        )
        records.append({**params, **result.metrics})

    ranked = pd.DataFrame(records)
    if sort_by in ranked.columns:
        ranked = ranked.sort_values(sort_by, ascending=ascending, na_position="last")
    return ranked.reset_index(drop=True)


def run_bollinger_vectorbt_train_test(
    data: pd.DataFrame,
    *,
    train_fraction: float = 0.7,
    strategy: str = "adaptive",
    adaptive_config: AdaptiveRegimeConfig | None = None,
    exit_plan: ExitPlan | None = None,
    config: VectorBTBacktestConfig | None = None,
) -> pd.DataFrame:
    """Evaluate the same vectorbt setup on chronological train and test splits."""
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    if len(data) < 2:
        raise ValueError("data must contain at least two rows")

    split_at = max(1, min(len(data) - 1, int(len(data) * train_fraction)))
    splits = {"train": data.iloc[:split_at], "test": data.iloc[split_at:]}
    records: list[dict[str, Any]] = []

    for split_name, split_data in splits.items():
        result = run_bollinger_vectorbt(
            split_data,
            strategy=strategy,
            adaptive_config=adaptive_config,
            exit_plan=exit_plan,
            config=config,
        )
        records.append({"split": split_name, "rows": len(split_data), **result.metrics})

    return pd.DataFrame(records)


def _to_shared_vectorbt_config(config: VectorBTBacktestConfig) -> VectorBTConfig:
    return VectorBTConfig(
        init_cash=config.init_cash,
        fees=config.fees,
        fixed_fees=config.fixed_fees,
        slippage=config.slippage,
        size=config.size,
        size_type=config.size_type,
        freq=config.freq,
        accumulate=config.accumulate,
        cash_sharing=config.cash_sharing,
        upon_opposite_entry=config.upon_opposite_entry,
        use_stops=config.use_stops,
        min_size=config.min_size,
        max_size=config.max_size,
        size_granularity=config.size_granularity,
    )


def _validate_parameter_grid(parameter_grid: Mapping[str, Sequence[Any]]) -> None:
    if not parameter_grid:
        raise ValueError("parameter_grid must not be empty")
    valid_names = {field.name for field in fields(AdaptiveRegimeConfig)}
    invalid_names = [name for name in parameter_grid if name not in valid_names]
    if invalid_names:
        raise ValueError(f"Unknown AdaptiveRegimeConfig parameter(s): {invalid_names}")
    empty_names = [name for name, values in parameter_grid.items() if len(values) == 0]
    if empty_names:
        raise ValueError(f"Parameter grid values must not be empty: {empty_names}")
