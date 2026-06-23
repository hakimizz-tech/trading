"""Standard report wrapper for Directional Forex ML."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from reporting import DEFAULT_REPORT_DIR, StrategyReport, generate_strategy_report
from strategies.DirectionalForexML.core import DirectionalForexMLResult


def generate_directional_forex_ml_report(
    result: DirectionalForexMLResult,
    *,
    name: str = "directional_forex_ml",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
) -> StrategyReport:
    """Create a standard report with price, ML probabilities, trades, and risk."""
    return generate_strategy_report(
        _to_report_result(result),
        name=name,
        title=title or "Directional Forex ML",
        output_dir=output_dir,
        render_charts=render_charts,
        overlay_builder=_overlays,
        frame_enricher=_enrich_frame,
        price_chart_filename="price_ml_trades.png",
    )


def generate_directional_forex_ml_model_comparison_charts(
    summary: pd.DataFrame,
    *,
    output_dir: str | Path = DEFAULT_REPORT_DIR / "directional_forex_ml_comparison",
) -> dict[str, Path]:
    """Create model/strategy comparison charts from a research summary table."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return paths
    if summary.empty:
        return paths

    data = summary.copy()
    if {"model", "symbol", "total_return"}.issubset(data.columns):
        pivot = data.pivot_table(index="symbol", columns="model", values="total_return", aggfunc="mean")
        if not pivot.empty:
            fig, ax = plt.subplots(figsize=(10, 5))
            pivot.plot(kind="bar", ax=ax)
            ax.set_title("Directional Forex ML Total Return by Pair and Model")
            ax.set_ylabel("Total return")
            ax.axhline(0, color="black", linewidth=0.8)
            fig.tight_layout()
            path = output / "model_total_return.png"
            fig.savefig(path, dpi=150)
            plt.close(fig)
            paths["model_total_return"] = path

    if {"model", "symbol", "sharpe_ratio"}.issubset(data.columns):
        pivot = data.pivot_table(index="symbol", columns="model", values="sharpe_ratio", aggfunc="mean")
        if not pivot.empty:
            fig, ax = plt.subplots(figsize=(10, 5))
            image = ax.imshow(pivot.fillna(0.0).to_numpy(), aspect="auto", cmap="RdYlGn")
            ax.set_title("Sharpe Ratio Heatmap")
            ax.set_xticks(range(len(pivot.columns)), labels=pivot.columns, rotation=45, ha="right")
            ax.set_yticks(range(len(pivot.index)), labels=pivot.index)
            fig.colorbar(image, ax=ax)
            fig.tight_layout()
            path = output / "model_sharpe_heatmap.png"
            fig.savefig(path, dpi=150)
            plt.close(fig)
            paths["model_sharpe_heatmap"] = path

    if {"cost_multiplier", "total_return"}.issubset(data.columns):
        fig, ax = plt.subplots(figsize=(8, 4))
        data.sort_values("cost_multiplier").plot(x="cost_multiplier", y="total_return", marker="o", ax=ax)
        ax.set_title("Cost Sensitivity")
        ax.set_ylabel("Total return")
        ax.axhline(0, color="black", linewidth=0.8)
        fig.tight_layout()
        path = output / "cost_sensitivity.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        paths["cost_sensitivity"] = path

    return paths


def _to_report_result(result: DirectionalForexMLResult) -> Any:
    data = result.data.copy()
    for frame in (result.features, result.signals):
        for column in frame.columns:
            if column not in data.columns:
                data[column] = frame[column].reindex(data.index)
    data["equity"] = result.equity.reindex(data.index)
    data["drawdown"] = result.drawdown.reindex(data.index)
    data["position"] = _position_from_trades(data.index, result.trades)
    return SimpleNamespace(
        data=data,
        trades=_event_trades(result.trades),
        equity=result.equity,
        drawdown=result.drawdown,
        metrics=result.metrics,
    )


def _enrich_frame(data: pd.DataFrame) -> pd.DataFrame:
    return data


def _overlays(data: pd.DataFrame) -> dict[str, pd.Series]:
    overlays: dict[str, pd.Series] = {}
    if "probability_up" in data.columns:
        overlays["ML probability up"] = data["probability_up"].astype(float)
    return overlays


def _event_trades(trades: pd.DataFrame) -> pd.DataFrame:
    columns = ["trade_id", "timestamp", "action", "price", "side", "size", "pnl", "return_pct", "status", "reason"]
    rows: list[dict[str, Any]] = []
    if trades.empty:
        return pd.DataFrame(columns=columns)
    for trade_id, row in trades.reset_index(drop=True).iterrows():
        side = str(row.get("direction", "long")).lower()
        rows.append(
            {
                "trade_id": trade_id,
                "timestamp": row.get("entry_timestamp"),
                "action": "ENTER_SHORT" if side == "short" else "ENTER_LONG",
                "price": row.get("entry_price"),
                "side": side,
                "size": 1.0,
                "pnl": pd.NA,
                "return_pct": pd.NA,
                "status": "open",
                "reason": "ml_entry",
            }
        )
        rows.append(
            {
                "trade_id": trade_id,
                "timestamp": row.get("exit_timestamp"),
                "action": "EXIT_SHORT" if side == "short" else "EXIT_LONG",
                "price": row.get("exit_price"),
                "side": side,
                "size": 1.0,
                "pnl": row.get("pnl", pd.NA),
                "return_pct": row.get("return_pct", pd.NA),
                "status": "closed",
                "reason": row.get("exit_reason", "horizon_exit"),
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
