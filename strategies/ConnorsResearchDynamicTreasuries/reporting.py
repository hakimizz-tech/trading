"""Reporting wrapper for Connors Research Dynamic Treasuries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from reporting import DEFAULT_REPORT_DIR, StrategyReport, generate_strategy_report
from reporting.strategy_report import frame_to_markdown
from strategies.ConnorsResearchDynamicTreasuries.core import (
    DynamicTreasuriesBacktestResult,
    build_rebalance_events,
    summarize_rebalances,
)
from visualization import (
    DARK_THEME,
    plot_correlation_heatmap,
    plot_return_distribution,
    save_figure,
)


def generate_dynamic_treasuries_report(
    result: DynamicTreasuriesBacktestResult,
    *,
    name: str = "dynamic_treasuries",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
) -> StrategyReport:
    """Create a standard report plus Dynamic Treasuries allocation exports."""
    report_result = _to_generic_report_result(result)
    report = generate_strategy_report(
        report_result,
        name=name,
        title=title or "Connors Research Dynamic Treasuries",
        output_dir=output_dir,
        render_charts=render_charts,
        price_chart_filename="equity_rebalances.png",
    )
    rebalance_events = build_rebalance_events(result)
    rebalance_summary = summarize_rebalances(rebalance_events)
    exports = {
        "rebalance_events": rebalance_events,
        "rebalance_summary": rebalance_summary,
        "target_weights": result.target_weights,
        "execution_weights": result.weights,
        "momentum_returns": result.momentum_returns,
        "positive_signal_counts": result.positive_signal_counts,
        "duration_exposure": result.duration_exposure.to_frame(),
        "asset_performance": result.asset_performance,
    }
    for key, frame in exports.items():
        path = report.output_dir / f"{key}.csv"
        frame.to_csv(path)
        report.paths[key] = path

    if render_charts:
        report.paths.update(_render_dynamic_treasuries_charts(result, report.output_dir, title or "Connors Research Dynamic Treasuries"))
    report.paths["markdown"].write_text(
        _dynamic_treasuries_markdown(report.name, report.metrics, rebalance_summary, report.paths),
        encoding="utf-8",
    )
    return report


def _to_generic_report_result(result: DynamicTreasuriesBacktestResult) -> Any:
    equity_growth = result.equity / float(result.config.initial_cash)
    data = pd.DataFrame(
        {
            "close": equity_growth,
            "equity": equity_growth,
            "drawdown": result.drawdown,
            "position": result.weights.abs().sum(axis=1),
        },
        index=result.equity.index,
    )
    trades = pd.DataFrame(columns=["trade_id", "timestamp", "action", "price", "side", "size", "pnl", "return_pct", "status", "reason"])
    return SimpleNamespace(data=data, trades=trades, equity=equity_growth, drawdown=result.drawdown, metrics=result.metrics)


def _dynamic_treasuries_markdown(
    name: str,
    metrics: dict[str, Any],
    rebalance_summary: pd.DataFrame,
    paths: dict[str, Path],
) -> str:
    lines = [f"# {name} Report", "", "## Metrics", ""]
    for key, value in metrics.items():
        lines.append(f"- **{key}**: {value}")
    lines.extend(
        [
            "",
            "## Rebalance Summary",
            "",
            frame_to_markdown(rebalance_summary),
            "",
            "## Report Note",
            "",
            "Dynamic Treasuries is a continuous allocation strategy, not a paired entry/exit trade strategy. "
            "Closed-trade win rate is therefore not applicable; use rebalance turnover, duration exposure, equity, drawdown, and asset contribution instead.",
            "",
            "## Artifacts",
            "",
        ]
    )
    for label, path in paths.items():
        lines.append(f"- **{label}**: `{path}`")
    return "\n".join(lines) + "\n"


def _render_dynamic_treasuries_charts(
    result: DynamicTreasuriesBacktestResult,
    output_dir: Path,
    title: str,
) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["allocation_chart"] = save_figure(
        _plot_target_allocations(result.target_weights, title=f"{title} Target Allocations"),
        output_dir / "target_allocations.png",
    )
    paths["duration_chart"] = save_figure(
        _plot_duration_exposure(result.duration_exposure, title=f"{title} Duration Exposure"),
        output_dir / "duration_exposure.png",
    )
    paths["asset_growth_chart"] = save_figure(
        _plot_asset_growth(result.prices, result.equity, title=f"{title} Asset Growth vs Strategy"),
        output_dir / "asset_growth.png",
    )
    paths["asset_contribution_chart"] = save_figure(
        _plot_asset_contribution(result.asset_performance, title=f"{title} Asset Contribution"),
        output_dir / "asset_contribution.png",
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
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    fig.tight_layout()
    return fig


def _plot_duration_exposure(duration: pd.Series, *, title: str) -> Any:
    plt = _require_pyplot()
    clean = duration.astype(float).dropna()
    fig, ax = plt.subplots(figsize=(14, 5))
    _style_axis(fig, ax)
    ax.plot(clean.index, clean, color=DARK_THEME["info"], linewidth=1.3)
    ax.fill_between(clean.index, clean.to_numpy(dtype=float), 0.0, color=DARK_THEME["info"], alpha=0.25)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Effective duration", fontsize=11, color=DARK_THEME["text"])
    fig.tight_layout()
    return fig


def _plot_asset_growth(prices: pd.DataFrame, equity: pd.Series, *, title: str) -> Any:
    plt = _require_pyplot()
    normalized_assets = prices.astype(float).divide(prices.astype(float).iloc[0]).replace([pd.NA, float("inf"), -float("inf")], pd.NA)
    normalized_equity = equity.astype(float) / float(equity.iloc[0])
    fig, ax = plt.subplots(figsize=(14, 7))
    _style_axis(fig, ax)
    for column in normalized_assets.columns:
        ax.plot(normalized_assets.index, normalized_assets[column], linewidth=0.9, alpha=0.58, label=column)
    ax.plot(normalized_equity.index, normalized_equity, color=DARK_THEME["profit"], linewidth=2.0, label="Strategy")
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Growth of $1", fontsize=11, color=DARK_THEME["text"])
    ax.legend(loc="upper left", ncol=2, fontsize=8)
    fig.tight_layout()
    return fig


def _plot_asset_contribution(asset_performance: pd.DataFrame, *, title: str) -> Any:
    plt = _require_pyplot()
    fig, ax = plt.subplots(figsize=(11, 6))
    _style_axis(fig, ax)
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
