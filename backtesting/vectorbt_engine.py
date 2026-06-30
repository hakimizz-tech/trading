"""Shared vectorbt runner for validated prepared signals."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from math import isfinite
from typing import Any

import pandas as pd

from backtesting.signals import PreparedSignals


@dataclass(frozen=True)
class VectorBTConfig:
    init_cash: float = 10_000.0
    fees: Any = 0.0
    fixed_fees: Any = 0.0
    slippage: Any = 0.0
    size: float = 0.95
    size_type: str = "percent"
    freq: str | None = None
    accumulate: bool = False
    cash_sharing: bool = False
    upon_opposite_entry: str = "close"
    use_stops: bool = True
    min_size: float | None = None
    max_size: float | None = None
    size_granularity: float | None = None


@dataclass(frozen=True)
class VectorBTResult:
    portfolio: Any
    signals: PreparedSignals
    stats: pd.Series
    metrics: dict[str, float | int | None]
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series


@dataclass(frozen=True)
class VectorBTTargetOrdersConfig:
    init_cash: float = 10_000.0
    fees: Any = 0.0
    fixed_fees: Any = 0.0
    slippage: Any = 0.0
    freq: str | None = None
    direction: str = "longonly"
    cash_sharing: bool = True
    group_by: bool | Any = True


@dataclass(frozen=True)
class VectorBTTargetOrdersResult:
    portfolio: Any
    stats: pd.Series
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series
    metrics: dict[str, float | int | None]


def run_vectorbt(
    signals: PreparedSignals,
    *,
    config: VectorBTConfig | None = None,
) -> VectorBTResult:
    """Run any validated prepared signal set through vectorbt."""
    signals.validate()
    vbt = _require_vectorbt()
    cfg = config or VectorBTConfig()
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
    if cfg.use_stops and signals.stop_loss is not None:
        kwargs["sl_stop"] = signals.stop_loss
    if cfg.use_stops and signals.take_profit is not None:
        kwargs["tp_stop"] = signals.take_profit
    if cfg.min_size is not None:
        kwargs["min_size"] = cfg.min_size
    if cfg.max_size is not None:
        kwargs["max_size"] = cfg.max_size
    if cfg.size_granularity is not None:
        kwargs["size_granularity"] = cfg.size_granularity

    portfolio = vbt.Portfolio.from_signals(**kwargs)
    equity = _series(portfolio.value)
    returns = _series(portfolio.returns)
    drawdown = (equity / equity.cummax() - 1.0).rename("drawdown")
    trades = _trades(portfolio)
    return VectorBTResult(
        portfolio=portfolio,
        signals=signals,
        stats=portfolio.stats(),
        metrics=_metrics(portfolio, equity),
        trades=trades,
        equity=equity,
        returns=returns,
        drawdown=drawdown,
    )


def run_vectorbt_target_orders(
    close: pd.DataFrame,
    target_orders: pd.DataFrame,
    *,
    config: VectorBTTargetOrdersConfig | None = None,
) -> VectorBTTargetOrdersResult:
    """Run target-percent allocation orders through vectorbt."""
    vbt = _require_vectorbt()
    cfg = config or VectorBTTargetOrdersConfig()
    kwargs: dict[str, Any] = {
        "close": close,
        "size": target_orders,
        "size_type": vbt.portfolio.enums.SizeType.TargetPercent,
        "direction": cfg.direction,
        "init_cash": cfg.init_cash,
        "cash_sharing": cfg.cash_sharing,
        "group_by": cfg.group_by,
        "fees": cfg.fees,
        "fixed_fees": cfg.fixed_fees,
        "slippage": cfg.slippage,
    }
    if cfg.freq is not None:
        kwargs["freq"] = cfg.freq

    portfolio = vbt.Portfolio.from_orders(**kwargs)
    equity = _portfolio_equity(portfolio.value)
    returns = equity.pct_change(fill_method=None).fillna(0.0).rename("returns")
    drawdown = (equity / equity.cummax() - 1.0).rename("drawdown")
    return VectorBTTargetOrdersResult(
        portfolio=portfolio,
        stats=portfolio.stats(),
        trades=_trades(portfolio),
        equity=equity,
        returns=returns,
        drawdown=drawdown,
        metrics=_metrics(portfolio, equity),
    )


def _require_vectorbt() -> Any:
    try:
        return import_module("vectorbt")
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Install research dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc


def _series(accessor: Any) -> pd.Series:
    value = accessor()
    if isinstance(value, pd.DataFrame):
        if value.shape[1] != 1:
            raise ValueError("shared vectorbt runner requires a single signal column")
        return value.iloc[:, 0]
    if isinstance(value, pd.Series):
        return value
    return pd.Series(value)


def _portfolio_equity(accessor: Any) -> pd.Series:
    value = accessor()
    if isinstance(value, pd.DataFrame):
        if value.shape[1] == 1:
            return value.iloc[:, 0].astype(float).rename("equity")
        return value.sum(axis=1).astype(float).rename("equity")
    if isinstance(value, pd.Series):
        return value.astype(float).rename("equity")
    return pd.Series(value, dtype=float, name="equity")


def _trades(portfolio: Any) -> pd.DataFrame:
    records = getattr(portfolio.trades, "records_readable", None)
    try:
        value = records() if callable(records) else records
    except Exception:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(value)


def _metrics(portfolio: Any, equity: pd.Series) -> dict[str, float | int | None]:
    trades = portfolio.trades
    return {
        "total_return": _safe_float_method(portfolio, "total_return"),
        "total_return_pct": _pct_method(portfolio, "total_return"),
        "end_value": _last_equity(equity),
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
    try:
        value = fn()
    except Exception:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _safe_int_method(obj: Any, name: str) -> int | None:
    fn = getattr(obj, name, None)
    if fn is None:
        return None
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


def _last_equity(equity: pd.Series) -> float | None:
    if equity.empty:
        return None
    value = float(equity.iloc[-1])
    return value if isfinite(value) else None
