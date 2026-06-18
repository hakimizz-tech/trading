"""Bollinger-specific report wrapper around shared strategy reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from strategies.BollingerBand.core import calculate_bollinger_bands
from reporting import (
    DEFAULT_REPORT_DIR,
    StrategyReport as BollingerStrategyReport,
    build_strategy_report_frame,
    generate_strategy_report,
    normalize_report_trades,
    summarize_report_trades,
)


def generate_bollinger_strategy_report(
    result: Any,
    *,
    name: str = "bollinger_strategy",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
) -> BollingerStrategyReport:
    """Create a standard report with Bollinger overlays."""
    return generate_strategy_report(
        result,
        name=name,
        title=title,
        output_dir=output_dir,
        render_charts=render_charts,
        overlay_builder=bollinger_overlays,
        frame_enricher=ensure_bollinger_bands,
        price_chart_filename="price_bollinger_trades.png",
    )


def build_bollinger_report_frame(result: Any) -> pd.DataFrame:
    """Build report data enriched with Bollinger bands."""
    return build_strategy_report_frame(result, frame_enricher=ensure_bollinger_bands)


def normalize_bollinger_report_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper for the shared trade normalizer."""
    return normalize_report_trades(trades)


def summarize_bollinger_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Compatibility wrapper for the shared trade summary."""
    return summarize_report_trades(trades)


def ensure_bollinger_bands(data: pd.DataFrame) -> pd.DataFrame:
    """Ensure report data contains Bollinger band columns."""
    if {"bb_middle", "bb_upper", "bb_lower"}.issubset(data.columns):
        return data
    return calculate_bollinger_bands(data)


def bollinger_overlays(data: pd.DataFrame) -> dict[str, pd.Series]:
    """Return Bollinger overlay series for the shared price chart."""
    overlays: dict[str, pd.Series] = {}
    for column, label in (
        ("bb_upper", "BB upper"),
        ("bb_middle", "BB middle"),
        ("bb_lower", "BB lower"),
    ):
        if column in data.columns:
            overlays[label] = data[column].astype(float)
    return overlays
