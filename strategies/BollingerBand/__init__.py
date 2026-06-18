"""Bollinger Band strategy package.

Canonical layout for a strategy package:
- ``core``: indicators, signal generation, pandas research backtest
- ``backtesting``: vectorbt/backtrader adapters and signal normalization
- ``execution``: aiomql adapter used by bots
- ``reporting``: standard strategy reports and chart exports
- ``tests``: strategy-specific tests
"""

from importlib import import_module
from typing import Any

__all__ = [
    "BUY",
    "SELL",
    "FLAT",
    "AdaptiveRegimeConfig",
    "BacktestResult",
    "ExitPlan",
    "add_atr",
    "add_entry_filters",
    "add_ema",
    "add_macd",
    "add_rsi",
    "backtest_entries_with_exits",
    "backtest_signals",
    "calculate_bollinger_bands",
    "generate_adaptive_bollinger_signals",
    "generate_bb_rsi_signals",
    "generate_bbma_signals",
    "generate_mean_reversion_signals",
    "generate_bollinger_strategy_report",
    "load_ohlcv_csv",
    "optimize_bollinger_parameters",
    "run_strategy",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        if name == "generate_bollinger_strategy_report":
            return getattr(import_module("strategies.BollingerBand.reporting"), name)
        return getattr(import_module("strategies.BollingerBand.core"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
