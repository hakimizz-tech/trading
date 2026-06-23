"""Scalper Major report wrapper around shared strategy reporting."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from reporting import DEFAULT_REPORT_DIR, StrategyReport, generate_strategy_report
from strategies.ScalperMajorHighVolatility.core import (
    ScalperMajorResult,
    compute_scalper_major_indicators,
)


def generate_scalper_major_report(
    result: ScalperMajorResult | Any,
    *,
    name: str = "scalper_major_high_volatility",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
) -> StrategyReport:
    """Create a standard Scalper Major report with price, trades, and risk charts."""
    report_result = _to_report_result(result)
    return generate_strategy_report(
        report_result,
        name=name,
        title=title or "Scalper Major High Volatility",
        output_dir=output_dir,
        render_charts=render_charts,
        overlay_builder=scalper_major_overlays,
        frame_enricher=ensure_scalper_major_indicators,
        price_chart_filename="price_sma_trades.png",
    )


def ensure_scalper_major_indicators(data: pd.DataFrame) -> pd.DataFrame:
    """Ensure report data contains Scalper Major indicators and signal columns."""
    result = data.copy()
    if "sma" not in result.columns or "rsi" not in result.columns:
        indicators = compute_scalper_major_indicators(result)
        for column in indicators.columns:
            if column not in result.columns:
                result[column] = indicators[column]
    return result


def scalper_major_overlays(data: pd.DataFrame) -> dict[str, pd.Series]:
    """Return price overlays for the Scalper Major chart."""
    overlays: dict[str, pd.Series] = {}
    if "sma" in data.columns:
        overlays["SMA 20"] = data["sma"].astype(float)
    return overlays


def _to_report_result(result: ScalperMajorResult | Any) -> Any:
    data = getattr(result, "data", pd.DataFrame()).copy()
    indicators = getattr(result, "indicators", pd.DataFrame())
    signals = getattr(result, "signals", pd.DataFrame())
    for frame in (indicators, signals):
        if isinstance(frame, pd.DataFrame):
            for column in frame.columns:
                if column not in data.columns:
                    data[column] = frame[column].reindex(data.index)
    data["equity"] = getattr(result, "equity", pd.Series(1.0, index=data.index)).reindex(data.index)
    data["drawdown"] = getattr(result, "drawdown", pd.Series(0.0, index=data.index)).reindex(data.index)
    data["position"] = _position_from_trades(data.index, getattr(result, "trades", pd.DataFrame()))
    return SimpleNamespace(
        data=data,
        trades=_event_trades(getattr(result, "trades", pd.DataFrame())),
        equity=data["equity"],
        drawdown=data["drawdown"],
        metrics=getattr(result, "metrics", {}),
    )


def _event_trades(trades: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_id", "timestamp", "action", "price", "side", "size", "pnl", "return_pct", "status", "reason"]
    rows: list[dict[str, Any]] = []
    if trades.empty:
        return pd.DataFrame(columns=columns)
    for trade_id, row in trades.reset_index(drop=True).iterrows():
        direction = str(row.get("direction", "")).lower()
        side = "short" if direction == "short" else "long"
        entry_action = "ENTER_SHORT" if side == "short" else "ENTER_LONG"
        exit_action = "EXIT_SHORT" if side == "short" else "EXIT_LONG"
        rows.append(
            {
                "trade_id": trade_id,
                "timestamp": row.get("entry_timestamp"),
                "action": entry_action,
                "price": row.get("entry_price"),
                "side": side,
                "size": row.get("weight", row.get("volume", pd.NA)),
                "pnl": pd.NA,
                "return_pct": pd.NA,
                "status": "open",
                "reason": "entry",
            }
        )
        rows.append(
            {
                "trade_id": trade_id,
                "timestamp": row.get("exit_timestamp"),
                "action": exit_action,
                "price": row.get("exit_price"),
                "side": side,
                "size": row.get("weight", row.get("volume", pd.NA)),
                "pnl": row.get("pnl", pd.NA),
                "return_pct": row.get("return_pct", pd.NA),
                "status": "closed",
                "reason": row.get("exit_reason", "exit"),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("timestamp").reset_index(drop=True)


def _position_from_trades(index: pd.Index, trades: pd.DataFrame) -> pd.Series:
    position = pd.Series(0.0, index=index)
    if trades.empty:
        return position
    for _, row in trades.iterrows():
        direction = -1.0 if str(row.get("direction", "")).lower() == "short" else 1.0
        entry = pd.Timestamp(row.get("entry_timestamp"))
        exit_ = pd.Timestamp(row.get("exit_timestamp"))
        position.loc[(position.index >= entry) & (position.index <= exit_)] = direction
    return position
