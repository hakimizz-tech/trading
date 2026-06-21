"""Backtesting adapters for ETF Avalanches."""

from strategies.ETFAvalanches.backtesting.vectorbt_engine import (
    ETFAvalanchesVectorBTConfig,
    ETFAvalanchesVectorBTResult,
    run_etf_avalanches_vectorbt,
)

__all__ = [
    "ETFAvalanchesVectorBTConfig",
    "ETFAvalanchesVectorBTResult",
    "run_etf_avalanches_vectorbt",
]
