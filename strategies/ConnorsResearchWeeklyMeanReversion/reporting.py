"""Reporting wrapper for Connors Research Weekly Mean Reversion."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from reporting import DEFAULT_REPORT_DIR, StrategyReport, generate_strategy_report
from reporting.strategy_report import markdown_report
from strategies.ConnorsResearchWeeklyMeanReversion.core import (
    ConnorsWeeklyMeanReversionResult,
    build_connors_closed_trades,
    compute_asset_performance,
)
from visualization import (
    DARK_THEME,
    plot_price_with_trades,
    plot_return_distribution,
    save_figure,
)


def generate_connors_report(
    result: ConnorsWeeklyMeanReversionResult,
    *,
    name: str = "connors_weekly_mean_reversion",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
    max_symbol_trade_charts: int | None = 50,
) -> StrategyReport:
    """Create a standard report plus Connors-specific research exports."""
    report_result = _to_generic_report_result(result)
    report = generate_strategy_report(
        report_result,
        name=name,
        title=title or "Connors Weekly Mean Reversion",
        output_dir=output_dir,
        render_charts=render_charts,
        price_chart_filename="equity_trades.png",
    )
    closed_trades = build_connors_closed_trades(result.trades, initial_cash=result.config.initial_cash)
    exports = {
        "signal_trades": result.trades,
        "closed_trades": closed_trades,
        "target_weights": result.target_weights,
        "weekly_rsi": result.weekly_rsi,
        "regime": result.regime.to_frame(),
        "volatility": result.volatility,
        "average_dollar_volume": result.average_dollar_volume,
        "asset_performance": compute_asset_performance(result),
    }
    for key, frame in exports.items():
        path = report.output_dir / f"{key}.csv"
        frame.to_csv(path)
        report.paths[key] = path

    if render_charts:
        report.paths.update(
            _render_connors_charts(
                result,
                report.output_dir,
                title or "Connors Weekly Mean Reversion",
                max_symbol_trade_charts=max_symbol_trade_charts,
            )
        )
        report.paths["markdown"].write_text(
            markdown_report(report.name, report.metrics, report.trade_summary, report.paths),
            encoding="utf-8",
        )
    return report


def _to_generic_report_result(result: ConnorsWeeklyMeanReversionResult) -> Any:
    equity_growth = result.equity / float(result.config.initial_cash)
    data = pd.DataFrame(
        {
            "close": equity_growth,
            "equity": equity_growth,
            "drawdown": result.drawdown,
            "position": result.weights.drop(columns=[result.config.cash_symbol], errors="ignore").abs().sum(axis=1),
        },
        index=result.equity.index,
    )
    trades = _closed_trade_events_for_report(result, equity_growth)
    return SimpleNamespace(data=data, trades=trades, equity=equity_growth, drawdown=result.drawdown, metrics=result.metrics)


def _closed_trade_events_for_report(
    result: ConnorsWeeklyMeanReversionResult,
    equity_growth: pd.Series,
) -> pd.DataFrame:
    closed_trades = build_connors_closed_trades(result.trades, initial_cash=result.config.initial_cash)
    columns = ["trade_id", "timestamp", "action", "price", "side", "size", "pnl", "return_pct", "status", "reason"]
    if closed_trades.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for _, trade in closed_trades.iterrows():
        entry_time = pd.Timestamp(trade["entry_timestamp"])
        exit_time = pd.Timestamp(trade["exit_timestamp"])
        rows.append(
            {
                "trade_id": trade["trade_id"],
                "timestamp": entry_time,
                "action": "ENTER_LONG",
                "price": _equity_marker_price(equity_growth, entry_time),
                "side": "long",
                "size": trade["size"],
                "pnl": pd.NA,
                "return_pct": pd.NA,
                "status": "open",
                "reason": "weekly_rsi_entry",
            }
        )
        rows.append(
            {
                "trade_id": trade["trade_id"],
                "timestamp": exit_time,
                "action": "EXIT_LONG",
                "price": _equity_marker_price(equity_growth, exit_time),
                "side": "long",
                "size": trade["size"],
                "pnl": trade["pnl"],
                "return_pct": trade["return_pct"],
                "status": "closed",
                "reason": trade["exit_reason"],
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("timestamp").reset_index(drop=True)


def _render_connors_charts(
    result: ConnorsWeeklyMeanReversionResult,
    output_dir: Path,
    title: str,
    *,
    max_symbol_trade_charts: int | None,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["stock_allocation_chart"] = save_figure(
        _plot_stock_allocations(result.target_weights.drop(columns=[result.config.cash_symbol], errors="ignore"), title=f"{title} Stock Allocations"),
        output_dir / "stock_allocations.png",
    )
    paths["asset_growth_chart"] = save_figure(
        _plot_asset_growth(result.prices, result.equity, title=f"{title} Asset Growth vs Strategy"),
        output_dir / "asset_growth.png",
    )
    paths["return_distribution"] = save_figure(
        plot_return_distribution(result.returns, title=f"{title} Return Distribution"),
        output_dir / "return_distribution.png",
    )
    paths["asset_contribution_chart"] = save_figure(
        _plot_asset_contribution(compute_asset_performance(result), title=f"{title} Asset Contribution"),
        output_dir / "asset_contribution.png",
    )
    paths.update(_render_symbol_trade_charts(result, output_dir, title, max_symbol_trade_charts=max_symbol_trade_charts))
    return paths


def _render_symbol_trade_charts(
    result: ConnorsWeeklyMeanReversionResult,
    output_dir: Path,
    title: str,
    *,
    max_symbol_trade_charts: int | None,
) -> dict[str, Path]:
    """Render per-symbol price charts with explicit entry and exit markers."""
    paths: dict[str, Path] = {}
    trades = _chart_trade_actions(result.trades)
    if trades.empty:
        return paths
    traded_symbols = [symbol for symbol in trades["symbol"].dropna().astype(str).drop_duplicates() if symbol in result.prices.columns]
    if max_symbol_trade_charts is not None:
        traded_symbols = traded_symbols[:max_symbol_trade_charts]

    chart_dir = output_dir / "symbol_trades"
    for symbol in traded_symbols:
        symbol_data = pd.DataFrame({"close": result.prices[symbol]}, index=result.prices.index)
        symbol_trades = trades.loc[trades["symbol"].astype(str) == symbol].copy()
        path = chart_dir / f"{_safe_filename(symbol)}_trades.png"
        paths[f"symbol_trade_chart_{symbol}"] = save_figure(
            plot_price_with_trades(
                symbol_data,
                symbol_trades,
                title=f"{title} {symbol} Entries and Exits",
            ),
            path,
        )
    return paths


def _chart_trade_actions(trades: pd.DataFrame) -> pd.DataFrame:
    """Convert Connors long-only BUY/SELL rows into chart-explicit actions."""
    if trades.empty:
        return trades.copy()
    chart_trades = trades.copy()
    chart_trades["action"] = chart_trades["action"].replace({"BUY": "ENTER_LONG", "SELL": "EXIT_LONG"})
    chart_trades["side"] = "long"
    return chart_trades


def _equity_marker_price(equity_growth: pd.Series, timestamp: pd.Timestamp) -> float:
    if timestamp in equity_growth.index:
        return float(equity_growth.loc[timestamp])
    return float(equity_growth.reindex([timestamp], method="ffill").iloc[0])


def _plot_stock_allocations(weights: pd.DataFrame, *, title: str) -> Any:
    plt = _require_pyplot()
    clean = weights.astype(float).fillna(0.0)
    fig, ax = plt.subplots(figsize=(14, 7))
    _style_axis(fig, ax)
    if clean.empty:
        ax.plot([], [])
    else:
        ax.stackplot(clean.index, [clean[column].to_numpy(dtype=float) for column in clean.columns], labels=clean.columns, alpha=0.88)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Stock target weight", fontsize=11, color=DARK_THEME["text"])
    ax.set_ylim(0.0, max(1.0, float(clean.sum(axis=1).max()) * 1.05) if not clean.empty else 1.0)
    if not clean.empty:
        ax.legend(loc="upper left", ncol=min(4, max(1, len(clean.columns) // 3)), fontsize=8)
    fig.tight_layout()
    return fig


def _plot_asset_growth(prices: pd.DataFrame, equity: pd.Series, *, title: str) -> Any:
    plt = _require_pyplot()
    normalized_assets = prices.astype(float).divide(prices.astype(float).iloc[0]).replace([pd.NA, float("inf"), -float("inf")], pd.NA)
    normalized_equity = equity.astype(float) / float(equity.iloc[0])
    fig, ax = plt.subplots(figsize=(14, 7))
    _style_axis(fig, ax)
    for column in normalized_assets.columns:
        ax.plot(normalized_assets.index, normalized_assets[column], linewidth=0.8, alpha=0.45, label=column)
    ax.plot(normalized_equity.index, normalized_equity, color=DARK_THEME["profit"], linewidth=2.0, label="Strategy")
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Growth of $1", fontsize=11, color=DARK_THEME["text"])
    ax.legend(loc="upper left", ncol=min(4, max(1, len(normalized_assets.columns) // 3)), fontsize=8)
    fig.tight_layout()
    return fig


def _plot_asset_contribution(asset_performance: pd.DataFrame, *, title: str) -> Any:
    plt = _require_pyplot()
    fig, ax = plt.subplots(figsize=(12, 7))
    _style_axis(fig, ax)
    if asset_performance.empty:
        ax.bar([], [])
    else:
        clean = asset_performance.sort_values("strategy_contribution_return", ascending=True)
        colors = [
            DARK_THEME["profit"] if value >= 0 else DARK_THEME["loss"]
            for value in clean["strategy_contribution_return"].to_numpy(dtype=float)
        ]
        ax.barh(clean["symbol"], clean["strategy_contribution_return_pct"], color=colors, alpha=0.82)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_xlabel("Contribution to strategy return (%)", fontsize=11, color=DARK_THEME["text"])
    fig.tight_layout()
    return fig


def _style_axis(fig: Any, ax: Any) -> None:
    fig.patch.set_facecolor(DARK_THEME["background"])
    ax.set_facecolor(DARK_THEME["panel"])
    ax.grid(True, alpha=0.35, color=DARK_THEME["grid"], linestyle="--")
    ax.tick_params(axis="both", colors=DARK_THEME["muted"], labelsize=9)
    ax.xaxis.label.set_color(DARK_THEME["text"])
    ax.yaxis.label.set_color(DARK_THEME["text"])
    for side in ("bottom", "left"):
        ax.spines[side].set_color(DARK_THEME["grid"])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _safe_filename(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned.strip("_") or "symbol"


def _require_pyplot() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "matplotlib is required for chart rendering. Install visualization dependencies "
            "with `python -m pip install -r requirements-visualization.txt`."
        ) from exc
    return plt
