"""Backtesting adapters for the Bollinger Band strategy."""

from BollingerBand.backtesting.signals import PreparedSignals, prepare_bollinger_signals
from BollingerBand.backtesting.vectorbt_engine import VectorBTBacktestConfig, VectorBTBacktestResult, run_bollinger_vectorbt

__all__ = [
    "PreparedSignals",
    "VectorBTBacktestConfig",
    "VectorBTBacktestResult",
    "prepare_bollinger_signals",
    "run_bollinger_vectorbt",
]
