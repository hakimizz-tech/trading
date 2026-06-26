"""Reporting wrapper for Rising Assets."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from reporting import DEFAULT_REPORT_DIR, StrategyReport, generate_strategy_report
from reporting.strategy_report import markdown_report
from strategies.RisingAssest.core import RisingAssetsBacktestResult
from visualization import (
    DARK_THEME,
    plot_correlation_heatmap,
    plot_return_distribution,
    save_figure,
)


def generate_rising_assets_report(
    result: RisingAssetsBacktestResult,
    *,
    name: str = "rising_assets",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
) -> StrategyReport:
    """Create a standard report plus Rising Assets allocation exports."""
    report_result = _to_generic_report_result(result)
    report = generate_strategy_report(
        report_result,
        name=name,
        title=title or "Rising Assets",
        output_dir=output_dir,
        render_charts=render_charts,
        price_chart_filename="equity_trades.png",
    )
    weights_path = report.output_dir / "target_weights.csv"
    momentum_path = report.output_dir / "momentum_scores.csv"
    result.target_weights.to_csv(weights_path)
    result.momentum.to_csv(momentum_path)
    report.paths["target_weights"] = weights_path
    report.paths["momentum"] = momentum_path
    if render_charts:
        report.paths.update(_render_rising_assets_charts(result, report.output_dir, title or "Rising Assets"))
        report.paths["markdown"].write_text(
            markdown_report(report.name, report.metrics, report.trade_summary, report.paths),
            encoding="utf-8",
        )
    return report


def _to_generic_report_result(result: RisingAssetsBacktestResult) -> Any:
    data = pd.DataFrame(
        {
            "close": result.equity,
            "equity": result.equity,
            "drawdown": result.drawdown,
            "position": result.weights.abs().sum(axis=1),
        },
        index=result.equity.index,
    )
    trades = result.trades.rename(columns={"symbol": "asset"}).copy()
    if not trades.empty:
        trades["trade_id"] = trades["timestamp"].astype(str) + ":" + trades["asset"].astype(str)
        trades["side"] = "long"
        trades["size"] = trades["weight_change"].abs()
        trades["pnl"] = pd.NA
        trades["return_pct"] = pd.NA
        trades["status"] = "rebalance"
    return SimpleNamespace(data=data, trades=trades, metrics=result.metrics)


def _render_rising_assets_charts(
    result: RisingAssetsBacktestResult,
    output_dir: Path,
    title: str,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["allocation_chart"] = save_figure(
        _plot_target_allocations(result.target_weights, title=f"{title} Target Allocations"),
        output_dir / "target_allocations.png",
    )
    paths["asset_growth_chart"] = save_figure(
        _plot_asset_growth(result.prices, result.equity, title=f"{title} Asset Growth vs Strategy"),
        output_dir / "asset_growth.png",
    )
    paths["return_distribution"] = save_figure(
        plot_return_distribution(result.returns, title=f"{title} Return Distribution"),
        output_dir / "return_distribution.png",
    )
    paths["asset_correlation"] = save_figure(
        plot_correlation_heatmap(result.prices.pct_change(fill_method=None).dropna(how="all"), title=f"{title} Asset Return Correlation"),
        output_dir / "asset_correlation.png",
    )
    return paths


def _plot_target_allocations(weights: pd.DataFrame, *, title: str) -> Any:
    plt = _require_pyplot()
    clean = weights.astype(float).fillna(0.0)
    fig, ax = plt.subplots(figsize=(14, 7))
    _style_axis(fig, ax)
    ax.stackplot(clean.index, [clean[column].to_numpy(dtype=float) for column in clean.columns], labels=clean.columns, alpha=0.88)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Target weight", fontsize=11, color=DARK_THEME["text"])
    ax.set_ylim(0.0, max(1.0, float(clean.sum(axis=1).max()) * 1.05))
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


def _require_pyplot() -> Any:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - depends on local environment
        raise RuntimeError(
            "matplotlib is required for chart rendering. Install visualization dependencies "
            "with `python -m pip install -r requirements.txt`."
        ) from exc
    return plt
