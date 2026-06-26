"""Reporting wrapper for ETF Avalanches."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd

from reporting import DEFAULT_REPORT_DIR, StrategyReport, generate_strategy_report
from reporting.strategy_report import frame_to_markdown
from strategies.ETFAvalanches.core import ETFAvalanchesResult
from visualization import (
    DARK_THEME,
    plot_correlation_heatmap,
    plot_return_distribution,
    save_figure,
)


def generate_etf_avalanches_report(
    result: ETFAvalanchesResult,
    *,
    name: str = "etf_avalanches",
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
) -> StrategyReport:
    """Create a standard report plus ETF Avalanches exports."""
    report = generate_strategy_report(
        _to_generic_report_result(result),
        name=name,
        title=title or "ETF Avalanches",
        output_dir=output_dir,
        render_charts=render_charts,
        price_chart_filename="equity_short_events.png",
    )
    exports = {
        "closed_trades": result.closed_trades,
        "target_weights": result.target_weights,
        "execution_weights": result.weights,
        "candidate_signals": result.candidate_signals,
        "rsi": result.rsi,
        "long_returns": result.long_returns,
        "intermediate_returns": result.intermediate_returns,
        "volatility": result.volatility,
        "asset_performance": result.asset_performance,
        "short_exposure": result.weights.drop(columns=[result.config.cash_symbol], errors="ignore").abs().sum(axis=1).rename("short_exposure").to_frame(),
    }
    for key, frame in exports.items():
        path = report.output_dir / f"{key}.csv"
        frame.to_csv(path, index=False if key in {"closed_trades", "asset_performance", "candidate_signals"} else True)
        report.paths[key] = path

    if render_charts:
        report.paths.update(_render_etf_avalanches_charts(result, report.output_dir, title or "ETF Avalanches"))
    report.paths["markdown"].write_text(
        _etf_avalanches_markdown(report.name, report.metrics, report.trade_summary, result, report.paths),
        encoding="utf-8",
    )
    return report


def _to_generic_report_result(result: ETFAvalanchesResult) -> Any:
    equity_growth = result.equity / float(result.config.initial_cash)
    data = pd.DataFrame(
        {
            "close": equity_growth,
            "equity": equity_growth,
            "drawdown": result.drawdown,
            "position": -result.weights.drop(columns=[result.config.cash_symbol], errors="ignore").abs().sum(axis=1),
        },
        index=result.equity.index,
    )
    return SimpleNamespace(data=data, trades=result.trades, equity=equity_growth, drawdown=result.drawdown, metrics=result.metrics)


def _etf_avalanches_markdown(
    name: str,
    metrics: dict[str, Any],
    trade_summary: pd.DataFrame,
    result: ETFAvalanchesResult,
    paths: dict[str, Path],
) -> str:
    lines = [f"# {name} Report", "", "## Metrics", ""]
    for key, value in metrics.items():
        lines.append(f"- **{key}**: {value}")
    lines.extend(["", "## Trade Summary", "", frame_to_markdown(trade_summary)])
    if not result.asset_performance.empty:
        lines.extend(["", "## Asset Contribution", "", frame_to_markdown(result.asset_performance.head(12))])
    lines.extend(
        [
            "",
            "## Report Note",
            "",
            "ETF Avalanches is a short-only allocation strategy. Entries are sell-short limit fills; exits are buy-to-cover events. "
            "Evaluate it primarily by crisis behavior, OOS Sharpe, max drawdown, profit factor, short exposure, and portfolio diversification benefit.",
            "",
            "## Artifacts",
            "",
        ]
    )
    for label, path in paths.items():
        lines.append(f"- **{label}**: `{path}`")
    return "\n".join(lines) + "\n"


def _render_etf_avalanches_charts(result: ETFAvalanchesResult, output_dir: Path, title: str) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    paths["short_exposure_chart"] = save_figure(
        _plot_short_exposure(result.weights, result.config.cash_symbol, title=f"{title} Short Exposure"),
        output_dir / "short_exposure.png",
    )
    paths["asset_contribution_chart"] = save_figure(
        _plot_asset_contribution(result.asset_performance, title=f"{title} Asset Contribution"),
        output_dir / "asset_contribution.png",
    )
    paths["trade_counts_chart"] = save_figure(
        _plot_trade_counts(result.closed_trades, title=f"{title} Closed Short Trades"),
        output_dir / "trade_counts.png",
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


def _plot_short_exposure(weights: pd.DataFrame, cash_symbol: str, *, title: str) -> Any:
    plt = _require_pyplot()
    short_exposure = weights.drop(columns=[cash_symbol], errors="ignore").clip(upper=0.0).abs().sum(axis=1)
    cash_weight = weights[cash_symbol] if cash_symbol in weights.columns else pd.Series(0.0, index=weights.index)
    fig, ax = plt.subplots(figsize=(14, 5))
    _style_axis(fig, ax)
    ax.plot(short_exposure.index, short_exposure, color=DARK_THEME["loss"], linewidth=1.4, label="Short exposure")
    ax.plot(cash_weight.index, cash_weight, color=DARK_THEME["info"], linewidth=1.0, label=cash_symbol)
    ax.fill_between(short_exposure.index, short_exposure.to_numpy(dtype=float), 0.0, color=DARK_THEME["loss"], alpha=0.25)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Portfolio weight", fontsize=11, color=DARK_THEME["text"])
    ax.set_ylim(0.0, 1.05)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    return fig


def _plot_asset_contribution(asset_performance: pd.DataFrame, *, title: str) -> Any:
    plt = _require_pyplot()
    clean = asset_performance.sort_values("strategy_contribution_return", ascending=True)
    fig, ax = plt.subplots(figsize=(11, 6))
    _style_axis(fig, ax)
    colors = [DARK_THEME["profit"] if value >= 0 else DARK_THEME["loss"] for value in clean["strategy_contribution_return"].to_numpy(dtype=float)]
    ax.barh(clean["symbol"], clean["strategy_contribution_return_pct"], color=colors, alpha=0.82)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_xlabel("Contribution to strategy return (%)", fontsize=11, color=DARK_THEME["text"])
    fig.tight_layout()
    return fig


def _plot_trade_counts(closed_trades: pd.DataFrame, *, title: str) -> Any:
    plt = _require_pyplot()
    fig, ax = plt.subplots(figsize=(11, 6))
    _style_axis(fig, ax)
    if closed_trades.empty:
        counts = pd.Series(dtype=int)
    else:
        counts = closed_trades["symbol"].value_counts().sort_values(ascending=True)
    ax.barh(counts.index.astype(str), counts.to_numpy(dtype=float), color=DARK_THEME["warning"], alpha=0.82)
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_xlabel("Closed trades", fontsize=11, color=DARK_THEME["text"])
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
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "matplotlib is required for chart rendering. Install visualization dependencies "
            "with `python -m pip install -r requirements.txt`."
        ) from exc
    return plt
