"""vectorbt backtesting adapter.

This module is optional at runtime. Linux research can still use the pandas
backtester without vectorbt installed; calling this adapter gives a clear error
until `vectorbt` is installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any

import pandas as pd

from BollingerBand.backtesting.signals import PreparedSignals, prepare_bollinger_signals
from BollingerBand.core import AdaptiveRegimeConfig, ExitPlan


@dataclass(frozen=True)
class VectorBTBacktestConfig:
    init_cash: float = 10_000.0
    fees: float = 0.003
    slippage: float = 0.001
    size: float = 0.95
    size_type: str = "percent"
    freq: str | None = None
    use_stops: bool = True
    accumulate: bool = False


@dataclass(frozen=True)
class VectorBTBacktestResult:
    portfolio: Any
    signals: PreparedSignals
    stats: pd.Series
    metrics: dict[str, float | int | None]


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
        "slippage": cfg.slippage,
        "size": cfg.size,
        "size_type": cfg.size_type,
        "accumulate": cfg.accumulate,
        "direction": "both",
    }
    if cfg.freq is not None:
        kwargs["freq"] = cfg.freq
    if cfg.use_stops and signals.stop_loss is not None and signals.take_profit is not None:
        kwargs["sl_stop"] = signals.stop_loss
        kwargs["tp_stop"] = signals.take_profit

    portfolio = vbt.Portfolio.from_signals(**kwargs)
    stats = portfolio.stats()
    metrics = _portfolio_metrics(portfolio)
    return VectorBTBacktestResult(portfolio=portfolio, signals=signals, stats=stats, metrics=metrics)


def _require_vectorbt() -> Any:
    try:
        return import_module("vectorbt")
    except ImportError as exc:
        raise RuntimeError(
            "vectorbt is not installed. Install the research backtesting extras with "
            "`python -m pip install -r requirements-backtest.txt`."
        ) from exc


def _portfolio_metrics(portfolio: Any) -> dict[str, float | int | None]:
    return {
        "total_return": _safe_float(portfolio.total_return),
        "max_drawdown": _safe_float(portfolio.max_drawdown),
        "sharpe_ratio": _safe_float(portfolio.sharpe_ratio),
        "trade_count": _safe_int(portfolio.trades.count),
        "win_rate": _safe_float(portfolio.trades.win_rate),
        "profit_factor": _safe_float(portfolio.trades.profit_factor),
    }


def _safe_float(fn: Any) -> float | None:
    try:
        value = fn()
    except Exception:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(fn: Any) -> int | None:
    try:
        value = fn()
    except Exception:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
