"""Connors Research Weekly Mean Reversion strategy package."""

from strategies.ConnorsResearchWeeklyMeanReversion.core import (
    ConnorsWeeklyMeanReversionConfig,
    ConnorsWeeklyMeanReversionResult,
    backtest_connors_weekly_mean_reversion,
    compute_asset_performance,
    compute_average_dollar_volume,
    compute_historical_volatility,
    compute_regime_filter,
    compute_weekly_rsi,
    generate_connors_target_weights,
    generate_live_rebalance_orders,
    load_connors_ohlcv_universe,
    validate_live_readiness,
)

__all__ = [
    "ConnorsWeeklyMeanReversionConfig",
    "ConnorsWeeklyMeanReversionResult",
    "backtest_connors_weekly_mean_reversion",
    "compute_asset_performance",
    "compute_average_dollar_volume",
    "compute_historical_volatility",
    "compute_regime_filter",
    "compute_weekly_rsi",
    "generate_connors_target_weights",
    "generate_live_rebalance_orders",
    "load_connors_ohlcv_universe",
    "validate_live_readiness",
]
