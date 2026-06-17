"""Strategy-agnostic trading charts.

The module intentionally depends only on pandas/numpy at import time.
matplotlib is imported lazily by plotting functions so research code and tests
that only normalize data do not require a display backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DARK_THEME: dict[str, str] = {
    "background": "#1a1a2e",
    "panel": "#1a1a2e",
    "grid": "#333333",
    "text": "#e0e0e0",
    "muted": "#aaaaaa",
    "dim": "#555555",
    "profit": "#00ff88",
    "loss": "#ff4444",
    "info": "#4488ff",
    "warning": "#ffaa00",
    "ma_short": "#ff6600",
    "ma_long": "#3399ff",
}


@dataclass(frozen=True)
class TradeMarkers:
    """Normalized entry and exit markers for plotting."""

    entries: pd.DataFrame
    exits: pd.DataFrame


def extract_result_parts(result: Any) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Extract ``data`` and ``trades`` from a backtest-result-like object.

    Native pandas backtests should expose ``data`` and ``trades`` attributes.
    Vectorized adapters may expose a ``signals`` object instead; in that case
    this function builds a signal-level trade marker table from entry/exit
    columns so the same report functions still work.
    """
    data = getattr(result, "data", None)
    trades = getattr(result, "trades", None)
    if isinstance(data, pd.DataFrame) and isinstance(trades, pd.DataFrame):
        return data, trades

    signals = getattr(result, "signals", None)
    signal_data = getattr(signals, "data", None)
    if isinstance(signal_data, pd.DataFrame):
        prepared = signal_data.copy()
        if "position" not in prepared.columns:
            prepared["position"] = _positions_from_signal_columns(prepared)
        if "equity" not in prepared.columns:
            portfolio = getattr(result, "portfolio", None)
            prepared["equity"] = _portfolio_value_series(portfolio, prepared.index)
        return prepared, _trades_from_signal_columns(prepared)

    raise TypeError(
        "result must expose pandas DataFrame attributes named 'data' and 'trades', "
        "or expose a prepared-signals object at result.signals.data"
    )


def normalize_trades(trades: pd.DataFrame) -> TradeMarkers:
    """Normalize common trade-log shapes into entry and exit marker tables.

    Supported action values include ``BUY``, ``SELL``, ``ENTER_LONG``,
    ``ENTER_SHORT``, ``EXIT_LONG``, and ``EXIT_SHORT``. The output DataFrames
    always contain ``timestamp``, ``price``, ``side``, ``action``, and
    ``reason`` columns.
    """
    columns = ["timestamp", "price", "side", "action", "reason"]
    if trades.empty:
        empty = pd.DataFrame(columns=columns)
        return TradeMarkers(entries=empty.copy(), exits=empty.copy())
    _require_columns(trades, ("timestamp", "price", "action"))

    normalized = trades.copy()
    normalized["action"] = normalized["action"].astype(str).str.upper()
    normalized["side"] = normalized["action"].map(_side_from_action).fillna("unknown")
    if "reason" not in normalized.columns:
        normalized["reason"] = ""
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="ignore")

    entry_mask = normalized["action"].isin({"BUY", "SELL", "ENTER_LONG", "ENTER_SHORT"})
    exit_mask = normalized["action"].isin({"EXIT_LONG", "EXIT_SHORT"})
    entries = normalized.loc[entry_mask, columns].reset_index(drop=True)
    exits = normalized.loc[exit_mask, columns].reset_index(drop=True)
    return TradeMarkers(entries=entries, exits=exits)


def plot_price_with_trades(
    data: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    price_col: str = "close",
    title: str = "Trades on Price",
    overlays: dict[str, pd.Series] | None = None,
    figsize: tuple[float, float] = (14, 7),
) -> Any:
    """Plot close price with long/short entry and exit markers."""
    plt = _require_pyplot()
    _require_columns(data, (price_col,))
    markers = normalize_trades(trades)

    price = data[price_col].astype(float)
    fig, ax = plt.subplots(figsize=figsize)
    _style_figure(fig, ax)

    ax.plot(price.index, price, color=DARK_THEME["muted"], linewidth=1.2, label=price_col)
    for label, series in (overlays or {}).items():
        aligned = series.reindex(price.index) if isinstance(series, pd.Series) else pd.Series(series, index=price.index)
        ax.plot(aligned.index, aligned.astype(float), linewidth=1.0, label=label)

    _scatter_entries(ax, markers.entries)
    _scatter_exits(ax, markers.exits)

    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Price", fontsize=11, color=DARK_THEME["text"])
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    return fig


def plot_equity_drawdown(
    equity: pd.Series,
    *,
    title: str = "Equity Curve",
    benchmark: pd.Series | None = None,
    figsize: tuple[float, float] = (14, 8),
) -> Any:
    """Plot equity curve with an underwater drawdown panel."""
    plt = _require_pyplot()
    equity = _as_float_series(equity, "equity").dropna()
    if equity.empty:
        raise ValueError("equity must contain at least one finite value")

    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    fig, (ax_equity, ax_dd) = plt.subplots(2, 1, figsize=figsize, height_ratios=[2, 1], sharex=True)
    _style_figure(fig, ax_equity, ax_dd)

    ax_equity.plot(equity.index, equity, color=DARK_THEME["profit"], linewidth=1.5, label="Equity")
    ax_equity.plot(peak.index, peak, color=DARK_THEME["dim"], linewidth=0.8, linestyle="--", label="Peak")
    if benchmark is not None:
        benchmark = _as_float_series(benchmark, "benchmark").reindex(equity.index).ffill()
        ax_equity.plot(benchmark.index, benchmark, color=DARK_THEME["info"], linewidth=1.0, label="Benchmark")
    ax_equity.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax_equity.set_ylabel("Value", fontsize=11, color=DARK_THEME["text"])
    ax_equity.legend(loc="upper left", fontsize=9)

    ax_dd.fill_between(drawdown.index, drawdown.to_numpy(dtype=float), 0.0, color=DARK_THEME["loss"], alpha=0.5)
    ax_dd.plot(drawdown.index, drawdown, color=DARK_THEME["loss"], linewidth=0.8)
    ax_dd.set_ylabel("Drawdown", fontsize=11, color=DARK_THEME["text"])
    ax_dd.set_xlabel("Date", fontsize=11, color=DARK_THEME["text"])
    fig.tight_layout()
    return fig


def plot_return_distribution(
    returns: pd.Series,
    *,
    title: str = "Return Distribution",
    bins: int = 50,
    figsize: tuple[float, float] = (10, 6),
) -> Any:
    """Plot return histogram with mean, VaR, and CVaR markers."""
    plt = _require_pyplot()
    returns = _as_float_series(returns, "returns").replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        raise ValueError("returns must contain at least one finite value")

    fig, ax = plt.subplots(figsize=figsize)
    _style_figure(fig, ax)
    ax.hist(returns, bins=bins, density=True, alpha=0.72, color=DARK_THEME["info"], edgecolor=DARK_THEME["grid"])

    mean = float(returns.mean())
    var_95 = float(returns.quantile(0.05))
    cvar_95 = float(returns[returns <= var_95].mean()) if (returns <= var_95).any() else var_95
    ax.axvline(mean, color=DARK_THEME["warning"], linewidth=1.5, label=f"Mean: {mean:.4f}")
    ax.axvline(var_95, color=DARK_THEME["loss"], linestyle="--", linewidth=1.5, label=f"VaR 95%: {var_95:.4f}")
    ax.axvline(cvar_95, color=DARK_THEME["ma_short"], linestyle=":", linewidth=1.5, label=f"CVaR 95%: {cvar_95:.4f}")

    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_xlabel("Return", fontsize=11, color=DARK_THEME["text"])
    ax.set_ylabel("Density", fontsize=11, color=DARK_THEME["text"])
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    return fig


def plot_position_timeline(
    positions: pd.Series,
    *,
    title: str = "Position Timeline",
    figsize: tuple[float, float] = (14, 3),
) -> Any:
    """Plot long/flat/short exposure through time."""
    plt = _require_pyplot()
    positions = _as_float_series(positions, "positions").fillna(0.0)

    fig, ax = plt.subplots(figsize=figsize)
    _style_figure(fig, ax)
    position_values = positions.to_numpy(dtype=float)
    ax.step(positions.index, positions, where="post", color=DARK_THEME["info"], linewidth=1.2)
    ax.fill_between(positions.index, position_values, 0.0, where=position_values > 0, color=DARK_THEME["profit"], alpha=0.28, step="post")
    ax.fill_between(positions.index, position_values, 0.0, where=position_values < 0, color=DARK_THEME["loss"], alpha=0.28, step="post")
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax.set_ylabel("Position", fontsize=11, color=DARK_THEME["text"])
    ax.set_yticks([-1, 0, 1])
    ax.set_yticklabels(["Short", "Flat", "Long"])
    fig.tight_layout()
    return fig


def plot_correlation_heatmap(
    returns: pd.DataFrame,
    *,
    title: str = "Correlation Matrix",
    figsize: tuple[float, float] | None = None,
) -> Any:
    """Plot an annotated correlation heatmap for strategy or asset returns."""
    plt = _require_pyplot()
    if returns.empty:
        raise ValueError("returns must not be empty")
    corr = returns.astype(float).corr()
    size = len(corr)
    fig, ax = plt.subplots(figsize=figsize or (max(8, size * 1.2), max(6, size)))
    _style_figure(fig, ax)

    im = ax.imshow(corr.to_numpy(dtype=float), cmap="RdYlGn", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(size))
    ax.set_yticks(range(size))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.columns)

    for row in range(size):
        for col in range(size):
            value = float(corr.iloc[row, col])
            color = "black" if abs(value) < 0.5 else "white"
            ax.text(col, row, f"{value:.2f}", ha="center", va="center", fontsize=9, color=color)

    fig.colorbar(im, ax=ax, shrink=0.8, label="Correlation")
    ax.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    fig.tight_layout()
    return fig


def plot_backtest_report(
    result: Any,
    *,
    title: str = "Backtest Report",
    price_col: str = "close",
    figsize: tuple[float, float] = (14, 12),
) -> Any:
    """Create a shared report: price/trades, equity/drawdown, and positions."""
    plt = _require_pyplot()
    data, trades = extract_result_parts(result)
    _require_columns(data, (price_col, "equity", "position"))
    markers = normalize_trades(trades)

    price = data[price_col].astype(float)
    equity = data["equity"].astype(float)
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    positions = data["position"].fillna(0).astype(float)

    fig, axes = plt.subplots(4, 1, figsize=figsize, height_ratios=[3, 1.6, 1, 0.8], sharex=True)
    ax_price, ax_equity, ax_dd, ax_pos = axes
    _style_figure(fig, *axes)

    ax_price.plot(price.index, price, color=DARK_THEME["muted"], linewidth=1.1, label=price_col)
    _scatter_entries(ax_price, markers.entries)
    _scatter_exits(ax_price, markers.exits)
    ax_price.set_title(title, fontsize=14, fontweight="bold", color=DARK_THEME["text"])
    ax_price.set_ylabel("Price", fontsize=11, color=DARK_THEME["text"])
    ax_price.legend(loc="best", fontsize=9)

    ax_equity.plot(equity.index, equity, color=DARK_THEME["profit"], linewidth=1.4, label="Equity")
    if "buy_hold_equity" in data.columns:
        ax_equity.plot(data.index, data["buy_hold_equity"].astype(float), color=DARK_THEME["info"], linewidth=1.0, label="Buy/Hold")
    ax_equity.set_ylabel("Equity", fontsize=11, color=DARK_THEME["text"])
    ax_equity.legend(loc="upper left", fontsize=9)

    ax_dd.fill_between(drawdown.index, drawdown.to_numpy(dtype=float), 0.0, color=DARK_THEME["loss"], alpha=0.5)
    ax_dd.set_ylabel("Drawdown", fontsize=11, color=DARK_THEME["text"])

    ax_pos.step(positions.index, positions, where="post", color=DARK_THEME["info"], linewidth=1.0)
    ax_pos.set_ylabel("Position", fontsize=11, color=DARK_THEME["text"])
    ax_pos.set_yticks([-1, 0, 1])
    ax_pos.set_yticklabels(["Short", "Flat", "Long"])
    ax_pos.set_xlabel("Date", fontsize=11, color=DARK_THEME["text"])

    fig.tight_layout()
    return fig


def save_figure(fig: Any, path: str | Path, *, dpi: int = 150) -> Path:
    """Save a matplotlib figure using the dark chart background."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=dpi, facecolor=fig.get_facecolor(), edgecolor="none", bbox_inches="tight")
    return output


def _require_columns(data: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in data.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _side_from_action(action: str) -> str:
    if action in {"BUY", "ENTER_LONG", "EXIT_LONG"}:
        return "long"
    if action in {"SELL", "ENTER_SHORT", "EXIT_SHORT"}:
        return "short"
    return "unknown"


def _positions_from_signal_columns(data: pd.DataFrame) -> pd.Series:
    position = 0
    values: list[int] = []
    long_entries = _bool_column(data, "long_entry")
    short_entries = _bool_column(data, "short_entry")
    long_exits = _bool_column(data, "long_exit")
    short_exits = _bool_column(data, "short_exit")

    for long_entry, short_entry, long_exit, short_exit in zip(long_entries, short_entries, long_exits, short_exits):
        if position == 1 and long_exit:
            position = 0
        elif position == -1 and short_exit:
            position = 0
        if position == 0 and long_entry:
            position = 1
        elif position == 0 and short_entry:
            position = -1
        values.append(position)
    return pd.Series(values, index=data.index, dtype=float)


def _trades_from_signal_columns(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    close = data["close"].astype(float) if "close" in data.columns else pd.Series(np.nan, index=data.index)
    action_columns = (
        ("long_entry", "ENTER_LONG", "entry"),
        ("short_entry", "ENTER_SHORT", "entry"),
        ("long_exit", "EXIT_LONG", "signal_exit"),
        ("short_exit", "EXIT_SHORT", "signal_exit"),
    )
    for column, action, reason in action_columns:
        if column not in data.columns:
            continue
        mask = data[column].fillna(False).astype(bool)
        for timestamp, price in close.loc[mask].items():
            rows.append({"timestamp": timestamp, "action": action, "price": float(price), "reason": reason})
    trades = pd.DataFrame(rows, columns=["timestamp", "action", "price", "reason"])
    if trades.empty:
        return trades
    return trades.sort_values("timestamp").reset_index(drop=True)


def _bool_column(data: pd.DataFrame, column: str) -> pd.Series:
    if column not in data.columns:
        return pd.Series(False, index=data.index)
    return data[column].fillna(False).astype(bool)


def _portfolio_value_series(portfolio: Any, index: pd.Index) -> pd.Series:
    if portfolio is not None:
        try:
            value = portfolio.value()
            if isinstance(value, pd.Series):
                return value.reindex(index).ffill().bfill().astype(float)
        except Exception:
            pass
    return pd.Series(1.0, index=index, dtype=float)


def _scatter_entries(ax: Any, entries: pd.DataFrame) -> None:
    if entries.empty:
        return
    long_entries = entries["side"] == "long"
    short_entries = entries["side"] == "short"
    ax.scatter(entries.loc[long_entries, "timestamp"], entries.loc[long_entries, "price"], marker="^", color=DARK_THEME["profit"], s=90, zorder=5, label="Long entry")
    ax.scatter(entries.loc[short_entries, "timestamp"], entries.loc[short_entries, "price"], marker="v", color=DARK_THEME["loss"], s=90, zorder=5, label="Short entry")


def _scatter_exits(ax: Any, exits: pd.DataFrame) -> None:
    if exits.empty:
        return
    long_exits = exits["side"] == "long"
    short_exits = exits["side"] == "short"
    ax.scatter(exits.loc[long_exits, "timestamp"], exits.loc[long_exits, "price"], marker="x", color=DARK_THEME["profit"], s=70, zorder=5, label="Long exit")
    ax.scatter(exits.loc[short_exits, "timestamp"], exits.loc[short_exits, "price"], marker="x", color=DARK_THEME["loss"], s=70, zorder=5, label="Short exit")


def _style_figure(fig: Any, *axes: Any) -> None:
    fig.patch.set_facecolor(DARK_THEME["background"])
    for ax in axes:
        ax.set_facecolor(DARK_THEME["panel"])
        ax.grid(True, alpha=0.35, color=DARK_THEME["grid"], linestyle="--")
        ax.tick_params(axis="both", colors=DARK_THEME["muted"], labelsize=9)
        ax.xaxis.label.set_color(DARK_THEME["text"])
        ax.yaxis.label.set_color(DARK_THEME["text"])
        for side in ("bottom", "left"):
            ax.spines[side].set_color(DARK_THEME["grid"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)


def _as_float_series(series: pd.Series, name: str) -> pd.Series:
    if not isinstance(series, pd.Series):
        raise TypeError(f"{name} must be a pandas Series")
    return series.astype(float)


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
