"""Backtesting adapters for Scalper Major High Volatility."""

from strategies.ScalperMajorHighVolatility.backtesting.vectorbt_engine import (
    ScalperMajorVectorBTConfig,
    ScalperMajorVectorBTResult,
    run_scalper_major_vectorbt,
)

__all__ = [
    "ScalperMajorVectorBTConfig",
    "ScalperMajorVectorBTResult",
    "run_scalper_major_vectorbt",
]
