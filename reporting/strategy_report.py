"""Generic strategy report exports used by strategy-specific wrappers."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from visualization import plot_equity_drawdown, plot_price_with_trades, save_figure


DEFAULT_REPORT_DIR = Path("trade_results/reports")

OverlayBuilder = Callable[[pd.DataFrame], dict[str, pd.Series]]
FrameEnricher = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True)
class StrategyReport:
    """Paths and summary artifacts created for a strategy report."""

    name: str
    output_dir: Path
    metrics: dict[str, Any]
    trade_summary: pd.DataFrame
    trades: pd.DataFrame
    paths: dict[str, Path] = field(default_factory=dict)


def generate_strategy_report(
    result: Any,
    *,
    name: str,
    title: str | None = None,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    render_charts: bool = True,
    overlay_builder: OverlayBuilder | None = None,
    frame_enricher: FrameEnricher | None = None,
    price_chart_filename: str = "price_trades.png",
) -> StrategyReport:
    """Create a standard strategy report from a backtest-result-like object."""
    report_name = safe_report_name(name)
    report_dir = Path(output_dir) / report_name
    report_dir.mkdir(parents=True, exist_ok=True)

    data = build_strategy_report_frame(result, frame_enricher=frame_enricher)
    trades = normalize_report_trades(getattr(result, "trades", pd.DataFrame()))
    trade_summary = summarize_report_trades(trades)
    metrics = clean_metrics(getattr(result, "metrics", {}))

    data_path = report_dir / "report_data.csv"
    trades_path = report_dir / "trades.csv"
    summary_path = report_dir / "trade_summary.csv"
    metrics_path = report_dir / "metrics.json"
    markdown_path = report_dir / "report.md"

    data.to_csv(data_path)
    trades.to_csv(trades_path, index=False)
    trade_summary.to_csv(summary_path, index=False)
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    paths = {
        "data": data_path,
        "trades": trades_path,
        "trade_summary": summary_path,
        "metrics": metrics_path,
        "markdown": markdown_path,
    }

    if render_charts:
        price_fig = plot_price_with_trades(
            data,
            trades,
            title=title or f"{report_name} Price and Trades",
            overlays=overlay_builder(data) if overlay_builder is not None else None,
        )
        paths["price_chart"] = save_figure(price_fig, report_dir / price_chart_filename)

        equity_fig = plot_equity_drawdown(data["equity"], title=title or f"{report_name} Equity and Drawdown")
        paths["equity_drawdown"] = save_figure(equity_fig, report_dir / "equity_drawdown.png")

    markdown_path.write_text(markdown_report(report_name, metrics, trade_summary, paths), encoding="utf-8")
    return StrategyReport(
        name=report_name,
        output_dir=report_dir,
        metrics=metrics,
        trade_summary=trade_summary,
        trades=trades,
        paths=paths,
    )


def build_strategy_report_frame(result: Any, *, frame_enricher: FrameEnricher | None = None) -> pd.DataFrame:
    """Build the common time-series frame used by strategy reports."""
    signals = getattr(result, "signals", None)
    data = getattr(signals, "data", None)
    if not isinstance(data, pd.DataFrame):
        data = getattr(result, "data", None)
    if not isinstance(data, pd.DataFrame):
        raise TypeError("result must expose a pandas DataFrame at result.signals.data or result.data")

    report = data.copy()
    if frame_enricher is not None:
        report = frame_enricher(report)

    equity = series_from_result(result, "equity", report.index)
    if equity is None:
        equity = pd.Series(1.0, index=report.index, dtype=float)
    report["equity"] = equity.reindex(report.index).ffill().bfill().astype(float)

    drawdown = series_from_result(result, "drawdown", report.index)
    if drawdown is None:
        peak = report["equity"].cummax()
        drawdown = report["equity"] / peak - 1.0
    report["drawdown"] = drawdown.reindex(report.index).ffill().fillna(0.0).astype(float)

    if "position" not in report.columns:
        report["position"] = position_from_signal_columns(report)
    return report


def normalize_report_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize internal or vectorbt-readable trades into chart/report rows."""
    columns = [
        "trade_id",
        "timestamp",
        "action",
        "price",
        "side",
        "size",
        "pnl",
        "return_pct",
        "status",
        "reason",
    ]
    if trades is None or trades.empty:
        return pd.DataFrame(columns=columns)
    if {"timestamp", "action", "price"}.issubset(trades.columns):
        normalized = trades.copy()
        normalized["side"] = normalized.get("side", normalized["action"].map(side_from_action))
        normalized["return_pct"] = return_pct_column(normalized)
        for column in columns:
            if column not in normalized.columns:
                normalized[column] = "" if column in {"trade_id", "status", "reason"} else pd.NA
        return normalized[columns].sort_values("timestamp").reset_index(drop=True)
    if {"Entry Timestamp", "Avg Entry Price", "Direction"}.issubset(trades.columns):
        return normalize_vectorbt_trades(trades, columns)
    raise ValueError("trades must be either action-based or vectorbt records_readable format")


def summarize_report_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Return a one-row trade table summary from normalized report trades."""
    if trades.empty:
        return pd.DataFrame(
            [
                {
                    "trades": 0,
                    "closed_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "win_rate": 0.0,
                    "total_pnl": 0.0,
                    "avg_return_pct": 0.0,
                    "best_trade_pct": 0.0,
                    "worst_trade_pct": 0.0,
                }
            ]
        )

    exits = trades[trades["action"].astype(str).str.startswith("EXIT")].copy()
    closed = exits[exits["pnl"].notna() | exits["return_pct"].notna()]
    pnl = pd.to_numeric(closed["pnl"], errors="coerce")
    returns = pd.to_numeric(closed["return_pct"], errors="coerce")
    wins = int((pnl > 0).sum()) if pnl.notna().any() else int((returns > 0).sum())
    losses = int((pnl < 0).sum()) if pnl.notna().any() else int((returns < 0).sum())
    closed_count = int(len(closed))
    return pd.DataFrame(
        [
            {
                "trades": int(trades["trade_id"].replace("", pd.NA).dropna().nunique() or closed_count),
                "closed_trades": closed_count,
                "wins": wins,
                "losses": losses,
                "win_rate": wins / closed_count if closed_count else 0.0,
                "total_pnl": float(pnl.fillna(0.0).sum()) if closed_count else 0.0,
                "avg_return_pct": safe_mean(returns),
                "best_trade_pct": safe_max(returns),
                "worst_trade_pct": safe_min(returns),
            }
        ]
    )


def normalize_vectorbt_trades(trades: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for fallback_id, row in trades.iterrows():
        trade_id = row.get("Exit Trade Id", row.get("Position Id", fallback_id))
        side = str(row.get("Direction", "")).strip().lower() or "unknown"
        entry_time = row.get("Entry Timestamp")
        exit_time = row.get("Exit Timestamp")
        return_pct = to_float(row.get("Return"))
        return_pct = return_pct * 100.0 if return_pct is not None else None

        rows.append(
            {
                "trade_id": trade_id,
                "timestamp": entry_time,
                "action": "ENTER_SHORT" if side == "short" else "ENTER_LONG",
                "price": row.get("Avg Entry Price"),
                "side": side,
                "size": row.get("Size"),
                "pnl": pd.NA,
                "return_pct": pd.NA,
                "status": str(row.get("Status", "")),
                "reason": "entry",
            }
        )
        if pd.notna(exit_time):
            rows.append(
                {
                    "trade_id": trade_id,
                    "timestamp": exit_time,
                    "action": "EXIT_SHORT" if side == "short" else "EXIT_LONG",
                    "price": row.get("Avg Exit Price"),
                    "side": side,
                    "size": row.get("Size"),
                    "pnl": row.get("PnL"),
                    "return_pct": return_pct,
                    "status": str(row.get("Status", "")),
                    "reason": "exit",
                }
            )
    normalized = pd.DataFrame(rows, columns=columns)
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce")
    return normalized.sort_values("timestamp").reset_index(drop=True)


def series_from_result(result: Any, name: str, index: pd.Index) -> pd.Series | None:
    value = getattr(result, name, None)
    if isinstance(value, pd.Series):
        return value.reindex(index).astype(float)
    if isinstance(value, pd.DataFrame) and value.shape[1] == 1:
        return value.iloc[:, 0].reindex(index).astype(float)
    return None


def position_from_signal_columns(data: pd.DataFrame) -> pd.Series:
    position = 0
    values: list[int] = []
    for _, row in data.iterrows():
        if position == 1 and bool(row.get("long_exit", False)):
            position = 0
        elif position == -1 and bool(row.get("short_exit", False)):
            position = 0
        if position == 0 and bool(row.get("long_entry", False)):
            position = 1
        elif position == 0 and bool(row.get("short_entry", False)):
            position = -1
        values.append(position)
    return pd.Series(values, index=data.index, dtype=float)


def clean_metrics(metrics: Any) -> dict[str, Any]:
    if isinstance(metrics, pd.Series):
        metrics = metrics.to_dict()
    if not isinstance(metrics, dict):
        return {}
    return {str(key): json_safe(value) for key, value in metrics.items()}


def markdown_report(
    name: str,
    metrics: dict[str, Any],
    trade_summary: pd.DataFrame,
    paths: dict[str, Path],
) -> str:
    lines = [f"# {name} Report", "", "## Metrics", ""]
    if metrics:
        for key, value in metrics.items():
            lines.append(f"- **{key}**: {value}")
    else:
        lines.append("- No metrics supplied.")
    lines.extend(["", "## Trade Summary", "", frame_to_markdown(trade_summary), "", "## Artifacts", ""])
    for label, path in paths.items():
        lines.append(f"- **{label}**: `{path}`")
    return "\n".join(lines) + "\n"


def frame_to_markdown(data: pd.DataFrame) -> str:
    display = data.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    headers = [str(column) for column in display.columns]
    rows = [[str(value) for value in row] for row in display.fillna("").to_numpy()]
    separator = ["---"] * len(headers)
    return "\n".join([markdown_row(headers), markdown_row(separator), *(markdown_row(row) for row in rows)])


def markdown_row(values: list[str]) -> str:
    escaped = [value.replace("|", "\\|") for value in values]
    return "| " + " | ".join(escaped) + " |"


def return_pct_column(data: pd.DataFrame) -> pd.Series:
    if "return_pct" in data.columns:
        return pd.to_numeric(data["return_pct"], errors="coerce")
    if "return" in data.columns:
        return pd.to_numeric(data["return"], errors="coerce") * 100.0
    return pd.Series(pd.NA, index=data.index)


def side_from_action(action: Any) -> str:
    text = str(action).upper()
    if "SHORT" in text or text == "SELL":
        return "short"
    if "LONG" in text or text == "BUY":
        return "long"
    return "unknown"


def safe_report_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return cleaned.strip("_") or "strategy"


def to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def json_safe(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def safe_mean(values: pd.Series) -> float:
    clean = values.dropna()
    return float(clean.mean()) if len(clean) else 0.0


def safe_max(values: pd.Series) -> float:
    clean = values.dropna()
    return float(clean.max()) if len(clean) else 0.0


def safe_min(values: pd.Series) -> float:
    clean = values.dropna()
    return float(clean.min()) if len(clean) else 0.0
