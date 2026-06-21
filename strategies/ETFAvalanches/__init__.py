"""ETF Avalanches strategy package."""

from strategies.ETFAvalanches.core import (
    ETF_AVALANCHES_CORE_UNIVERSE,
    ETF_AVALANCHES_RESEARCH_UNIVERSE,
    ETFAvalanchesConfig,
    ETFAvalanchesResult,
    backtest_etf_avalanches,
    build_etf_avalanche_closed_trades,
    compute_asset_performance,
    compute_historical_volatility,
    compute_rsi,
    compute_trailing_returns,
    generate_etf_avalanche_target_weights,
    generate_live_short_orders,
    load_etf_avalanche_ohlcv,
    validate_live_readiness,
)

__all__ = [
    "ETF_AVALANCHES_CORE_UNIVERSE",
    "ETF_AVALANCHES_RESEARCH_UNIVERSE",
    "ETFAvalanchesConfig",
    "ETFAvalanchesResult",
    "backtest_etf_avalanches",
    "build_etf_avalanche_closed_trades",
    "compute_asset_performance",
    "compute_historical_volatility",
    "compute_rsi",
    "compute_trailing_returns",
    "generate_etf_avalanche_target_weights",
    "generate_live_short_orders",
    "load_etf_avalanche_ohlcv",
    "validate_live_readiness",
]
