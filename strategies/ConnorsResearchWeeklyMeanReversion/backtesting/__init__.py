"""Backtesting adapters for Connors Research Weekly Mean Reversion."""

from strategies.ConnorsResearchWeeklyMeanReversion.backtesting.vectorbt_engine import (
    ConnorsVectorBTConfig,
    ConnorsVectorBTResult,
    run_connors_vectorbt,
)

__all__ = [
    "ConnorsVectorBTConfig",
    "ConnorsVectorBTResult",
    "run_connors_vectorbt",
]
