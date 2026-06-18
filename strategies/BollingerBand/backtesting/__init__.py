"""Backtesting adapters for the Bollinger Band strategy."""

from strategies.BollingerBand.backtesting.signals import PreparedSignals, prepare_bollinger_signals
from strategies.BollingerBand.backtesting.vectorbt_engine import (
    VectorBTBacktestConfig,
    VectorBTBacktestResult,
    optimize_bollinger_vectorbt,
    run_bollinger_vectorbt,
    run_bollinger_vectorbt_train_test,
)

__all__ = [
    "PreparedSignals",
    "VectorBTBacktestConfig",
    "VectorBTBacktestResult",
    "optimize_bollinger_vectorbt",
    "prepare_bollinger_signals",
    "run_bollinger_vectorbt",
    "run_bollinger_vectorbt_train_test",
]
