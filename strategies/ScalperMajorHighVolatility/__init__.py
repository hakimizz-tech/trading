"""Scalper Major high-volatility research strategy."""

from strategies.ScalperMajorHighVolatility.core import (
    ScalperMajorConfig,
    ScalperMajorResult,
    backtest_scalper_major,
    compute_scalper_major_indicators,
    generate_scalper_major_signals,
    generate_scalper_major_ml_filtered_signals,
    progressive_lot_size,
    recovery_lot_sequence,
    resample_ohlcv_timeframes,
)
from strategies.ScalperMajorHighVolatility.recovery import RecoveryConfig, backtest_scalper_major_recovery
from strategies.ScalperMajorHighVolatility.execution import ScalperMajorAiomqlStrategy
from strategies.ScalperMajorHighVolatility.reporting import generate_scalper_major_report

__all__ = [
    "RecoveryConfig",
    "ScalperMajorConfig",
    "ScalperMajorAiomqlStrategy",
    "ScalperMajorResult",
    "backtest_scalper_major",
    "backtest_scalper_major_recovery",
    "compute_scalper_major_indicators",
    "generate_scalper_major_signals",
    "generate_scalper_major_ml_filtered_signals",
    "generate_scalper_major_report",
    "progressive_lot_size",
    "recovery_lot_sequence",
    "resample_ohlcv_timeframes",
]
