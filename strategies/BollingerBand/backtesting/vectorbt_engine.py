"""vectorbt backtesting adapter.

This module is optional at runtime. Linux research can still use the pandas
backtester without vectorbt installed; calling this adapter gives a clear error
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from itertools import product
from importlib import import_module
from typing import Any

import pandas as pd

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
    vbt = _require_vectorbt()
    cfg = config or VectorBTBacktestConfig()
    signals = prepare_bollinger_signals(
        data,
        strategy=strategy,
        adaptive_config=adaptive_config,
        exit_plan=exit_plan,
    )

    kwargs: dict[str, Any] = {
        "close": signals.close,
        "entries": signals.long_entries,
        "exits": signals.long_exits,
        "short_entries": signals.short_entries,
        "short_exits": signals.short_exits,
        "init_cash": cfg.init_cash,
        "fees": cfg.fees,
        "fixed_fees": cfg.fixed_fees,
        "slippage": cfg.slippage,
        "size": cfg.size,
        "size_type": cfg.size_type,
        "accumulate": cfg.accumulate,
        "cash_sharing": cfg.cash_sharing,
        "upon_opposite_entry": cfg.upon_opposite_entry,
    }
    if cfg.freq is not None:
        kwargs["freq"] = cfg.freq
    if cfg.min_size is not None:
        kwargs["min_size"] = cfg.min_size
    if cfg.max_size is not None:
        kwargs["max_size"] = cfg.max_size
    if cfg.size_granularity is not None:
        kwargs["size_granularity"] = cfg.size_granularity
    if cfg.use_stops and signals.stop_loss is not None and signals.take_profit is not None:
        kwargs["sl_stop"] = signals.stop_loss
        kwargs["tp_stop"] = signals.take_profit

    portfolio = vbt.Portfolio.from_signals(**kwargs)
    stats = portfolio.stats()
    metrics = _portfolio_metrics(portfolio)
    equity = _portfolio_series(portfolio.value)
    returns = _portfolio_series(portfolio.returns)
    drawdown = _drawdown_from_equity(equity)
    trades = _portfolio_trades(portfolio)
    return VectorBTBacktestResult(
        portfolio=portfolio,
        signals=signals,
        stats=stats,
        metrics=metrics,
        trades=trades,
        equity=equity,
        returns=returns,
        drawdown=drawdown,
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


def _require_vectorbt() -> Any:
    try:
        return import_module("vectorbt")
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Install the research backtesting extras with "
            "`python -m pip install -r requirements-backtest.txt`."
        ) from exc


def _portfolio_metrics(portfolio: Any) -> dict[str, float | int | None]:
    trades = portfolio.trades
    return {
        "total_return": _safe_float_method(portfolio, "total_return"),
        "total_return_pct": _pct_method(portfolio, "total_return"),
        "end_value": _last_series_value(portfolio.value),
        "max_drawdown": _safe_float_method(portfolio, "max_drawdown"),
        "max_drawdown_pct": _pct_method(portfolio, "max_drawdown"),
        "annualized_return": _safe_float_method(portfolio, "annualized_return"),
        "annualized_volatility": _safe_float_method(portfolio, "annualized_volatility"),
        "sharpe_ratio": _safe_float_method(portfolio, "sharpe_ratio"),
        "sortino_ratio": _safe_float_method(portfolio, "sortino_ratio"),
        "calmar_ratio": _safe_float_method(portfolio, "calmar_ratio"),
        "value_at_risk": _safe_float_method(portfolio, "value_at_risk"),
        "trade_count": _safe_int_method(trades, "count"),
        "win_rate": _safe_float_method(trades, "win_rate"),
        "win_rate_pct": _pct_method(trades, "win_rate"),
        "profit_factor": _safe_float_method(trades, "profit_factor"),
        "expectancy": _safe_float_method(trades, "expectancy"),
        "avg_winning_trade": _safe_float_method(trades, "avg_winning_trade"),
        "avg_losing_trade": _safe_float_method(trades, "avg_losing_trade"),
    }


def _safe_float_method(obj: Any, name: str) -> float | None:
    fn = getattr(obj, name, None)
    if fn is None:
        return None
    return _safe_float(fn)


def _safe_int_method(obj: Any, name: str) -> int | None:
    fn = getattr(obj, name, None)
    if fn is None:
        return None
    return _safe_int(fn)


def _safe_float(fn: Any) -> float | None:
    try:
        value = fn()
    except Exception:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _safe_int(fn: Any) -> int | None:
    try:
        value = fn()
    except Exception:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pct_method(obj: Any, name: str) -> float | None:
    value = _safe_float_method(obj, name)
    return value * 100.0 if value is not None else None


def _portfolio_series(fn: Any) -> pd.Series:
    try:
        value = fn()
    except Exception:
        return pd.Series(dtype=float)
    if isinstance(value, pd.DataFrame):
        if value.shape[1] == 1:
            return value.iloc[:, 0].astype(float)
        return value.mean(axis=1).astype(float)
    if isinstance(value, pd.Series):
        return value.astype(float)
    return pd.Series(value, dtype=float)


def _last_series_value(fn: Any) -> float | None:
    series = _portfolio_series(fn)
    if series.empty:
        return None
    value = float(series.iloc[-1])
    return value if math.isfinite(value) else None


def _drawdown_from_equity(equity: pd.Series) -> pd.Series:
    if equity.empty:
        return pd.Series(dtype=float)
    running_max = equity.cummax()
    return (equity / running_max - 1.0).fillna(0.0)


def _portfolio_trades(portfolio: Any) -> pd.DataFrame:
    readable = getattr(portfolio.trades, "records_readable", None)
    try:
        records = readable() if callable(readable) else readable
    except Exception:
        return pd.DataFrame()
    if isinstance(records, pd.DataFrame):
        return records.copy()
    return pd.DataFrame(records)


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
