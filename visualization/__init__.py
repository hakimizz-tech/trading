"""Shared trading visualization tools.

These helpers are strategy-agnostic: pass OHLCV data, trade logs, equity
curves, or any object with ``data`` and ``trades`` attributes.
"""

from visualization.charts import (
    DARK_THEME,
    TradeMarkers,
    extract_result_parts,
    normalize_trades,
    plot_backtest_report,
    plot_correlation_heatmap,
    plot_equity_drawdown,
    plot_position_timeline,
    plot_price_with_trades,
    plot_return_distribution,
    save_figure,
)

__all__ = [
    "DARK_THEME",
    "TradeMarkers",
    "extract_result_parts",
    "normalize_trades",
    "plot_backtest_report",
    "plot_correlation_heatmap",
    "plot_equity_drawdown",
    "plot_position_timeline",
    "plot_price_with_trades",
    "plot_return_distribution",
    "save_figure",
]
