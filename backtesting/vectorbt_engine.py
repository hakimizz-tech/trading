"""Shared vectorbt runner for validated prepared signals."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pandas as pd

from backtesting.signals import PreparedSignals


@dataclass(frozen=True)
class VectorBTConfig:
    init_cash: float = 10_000.0
    fees: float = 0.0
    fixed_fees: float = 0.0
    slippage: float = 0.0
    size: float = 0.95
    size_type: str = "percent"
    freq: str | None = None
    accumulate: bool = False
    cash_sharing: bool = False
    upon_opposite_entry: str = "close"
    use_stops: bool = True


@dataclass(frozen=True)
class VectorBTResult:
    portfolio: Any
    signals: PreparedSignals
    stats: pd.Series
    trades: pd.DataFrame
    equity: pd.Series
    returns: pd.Series
    drawdown: pd.Series


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

    portfolio = vbt.Portfolio.from_signals(**kwargs)
    equity = _series(portfolio.value)
    returns = _series(portfolio.returns)
    drawdown = (equity / equity.cummax() - 1.0).rename("drawdown")
    return VectorBTResult(
        portfolio=portfolio,
        signals=signals,
        stats=portfolio.stats(),
        trades=portfolio.trades.records_readable,
        equity=equity,
        returns=returns,
        drawdown=drawdown,
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
