#!/usr/bin/env python3
"""Run Bollinger Band research results on local OHLCV datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.BollingerBand.backtesting.vectorbt_engine import VectorBTBacktestConfig, run_bollinger_vectorbt
from strategies.BollingerBand.core import AdaptiveRegimeConfig, ExitPlan
from strategies.BollingerBand.reporting import generate_bollinger_strategy_report
from strategies.BollingerBand.research.datasets import load_market_csv
from strategies.BollingerBand.research.walk_forward import (
    WalkForwardConfig,
    run_bollinger_walk_forward,
    summarize_walk_forward,
)


DEFAULT_DATASETS = [
    "datasets/GBPUSD/GBPUSD_PERIOD_D1.csv",
    "datasets/EURUSD/EUR_USD Historical Data3.csv",
    "datasets/xauusd/XAU_1d_data.csv",
]


def main() -> None:
    args = _parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    adaptive_config = AdaptiveRegimeConfig(
        max_spread=args.max_spread,
        session_start=args.session_start,
        session_end=args.session_end,
    )
    exit_plan = ExitPlan()

    rows: list[dict[str, Any]] = []
    for dataset in args.datasets:
        data = load_market_csv(dataset)
        if args.tail and len(data) > args.tail:
            data = data.tail(args.tail)
        symbol = str(data.attrs.get("symbol", Path(dataset).parent.name))
        timeframe = str(data.attrs.get("timeframe") or "")
        vectorbt_config = VectorBTBacktestConfig(
            init_cash=args.init_cash,
            fees=args.fees,
            slippage=args.slippage,
            size=args.size,
            freq=_vectorbt_freq(args.freq, timeframe),
        )

        single = run_bollinger_vectorbt(
            data,
            strategy=args.strategy,
            adaptive_config=adaptive_config,
            exit_plan=exit_plan,
            config=vectorbt_config,
        )
        report_path = ""
        if args.generate_reports:
            report = generate_bollinger_strategy_report(
                single,
                name=f"{symbol}_{timeframe}_{args.strategy}".replace("/", "_"),
                title=f"{symbol} {timeframe} {args.strategy}",
                output_dir=args.report_dir,
                render_charts=not args.skip_report_charts,
            )
            report_path = str(report.output_dir)
        walk_config = _walk_config_for_rows(len(data), args)
        walk = run_bollinger_walk_forward(
            data,
            walk_config=walk_config,
            base_adaptive_config=adaptive_config,
            exit_plan=exit_plan,
            vectorbt_config=vectorbt_config,
            strategy=args.strategy,
            parameter_grid={
                "bb_window": [20, 30],
                "bb_num_std": [2.0],
                "wide_quantile": [0.55, 0.60],
                "squeeze_quantile": [0.20],
            },
            optimize_by=args.optimize_by,
        )
        walk_path = output_dir / f"{symbol}_{timeframe}_{args.strategy}_walk_forward.csv".replace("/", "_")
        walk.to_csv(walk_path, index=False)

        summary = summarize_walk_forward(walk)
        rows.append(
            {
                "dataset": str(dataset),
                "strategy": args.strategy,
                "symbol": symbol,
                "timeframe": timeframe,
                "rows": len(data),
                "start": data.index.min(),
                "end": data.index.max(),
                "single_total_return": single.metrics.get("total_return"),
                "single_sharpe_ratio": single.metrics.get("sharpe_ratio"),
                "single_max_drawdown": single.metrics.get("max_drawdown"),
                "single_win_rate": single.metrics.get("win_rate"),
                "single_profit_factor": single.metrics.get("profit_factor"),
                "single_trade_count": single.metrics.get("trade_count"),
                **summary,
                "walk_forward_csv": str(walk_path),
                "report_path": report_path,
            }
        )

    summary_df = pd.DataFrame(rows)
    summary_csv = output_dir / f"{args.summary_name}.csv"
    summary_md = output_dir / f"{args.summary_name}.md"
    summary_df.to_csv(summary_csv, index=False)
    summary_md.write_text(_to_markdown(summary_df), encoding="utf-8")
    print(f"Wrote {summary_csv}")
    print(f"Wrote {summary_md}")


def _walk_config_for_rows(rows: int, args: argparse.Namespace) -> WalkForwardConfig:
    train_size = args.train_size
    test_size = args.test_size
    step_size = args.step_size or test_size
    min_required = train_size + args.purge_size + args.embargo_size + test_size
    if rows >= min_required:
        return WalkForwardConfig(
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            window_type=args.window_type,
            purge_size=args.purge_size,
            embargo_size=args.embargo_size,
        )

    fallback_train = max(120, int(rows * 0.55))
    fallback_test = max(30, int(rows * 0.15))
    fallback_step = fallback_test
    return WalkForwardConfig(
        train_size=fallback_train,
        test_size=fallback_test,
        step_size=fallback_step,
        window_type=args.window_type,
        purge_size=min(args.purge_size, max(0, fallback_train // 10)),
        embargo_size=min(args.embargo_size, max(0, fallback_test // 10)),
    )


def _vectorbt_freq(freq: str, timeframe: str) -> str:
    if freq != "auto":
        return freq
    normalized = timeframe.upper()
    if normalized.startswith("M") and normalized[1:].isdigit():
        return f"{int(normalized[1:])}min"
    if normalized.startswith("H") and normalized[1:].isdigit():
        return f"{int(normalized[1:])}h"
    if normalized in {"D1", "1D"}:
        return "1d"
    if normalized in {"W1", "1W"}:
        return "1w"
    return "1d"


def _to_markdown(data: pd.DataFrame) -> str:
    display = data.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    headers = [str(column) for column in display.columns]
    rows = [[str(value) for value in row] for row in display.fillna("").to_numpy()]
    separator = ["---"] * len(headers)
    lines = [_markdown_row(headers), _markdown_row(separator)]
    lines.extend(_markdown_row(row) for row in rows)
    return "\n".join(lines) + "\n"


def _markdown_row(values: list[str]) -> str:
    escaped = [value.replace("|", "\\|") for value in values]
    return "| " + " | ".join(escaped) + " |"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Bollinger vectorbt and walk-forward research.")
    parser.add_argument("datasets", nargs="*", type=Path, default=[Path(path) for path in DEFAULT_DATASETS])
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/research"))
    parser.add_argument("--summary-name", default="bollinger_research_summary")
    parser.add_argument(
        "--strategy",
        choices=("adaptive", "adaptive_mean_reversion", "adaptive_breakout"),
        default="adaptive",
    )
    parser.add_argument("--init-cash", type=float, default=10_000.0)
    parser.add_argument("--fees", type=float, default=0.0002)
    parser.add_argument("--slippage", type=float, default=0.0001)
    parser.add_argument("--size", type=float, default=0.95)
    parser.add_argument("--freq", default="auto", help="vectorbt frequency, or 'auto' to infer from dataset timeframe.")
    parser.add_argument("--tail", type=int, default=0, help="Use only the most recent N rows when non-zero.")
    parser.add_argument("--train-size", type=int, default=750)
    parser.add_argument("--test-size", type=int, default=250)
    parser.add_argument("--step-size", type=int, default=0)
    parser.add_argument("--window-type", choices=("rolling", "expanding"), default="rolling")
    parser.add_argument("--purge-size", type=int, default=5)
    parser.add_argument("--embargo-size", type=int, default=5)
    parser.add_argument("--optimize-by", default="sharpe_ratio")
    parser.add_argument("--max-spread", type=float, default=None, help="Maximum allowed spread column value.")
    parser.add_argument("--session-start", default=None, help="Entry session start time, for example 07:00.")
    parser.add_argument("--session-end", default=None, help="Entry session end time, for example 17:00.")
    parser.add_argument("--generate-reports", action="store_true", help="Create per-dataset strategy reports under --report-dir.")
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/reports"))
    parser.add_argument("--skip-report-charts", action="store_true", help="Write report tables/markdown without rendering PNG charts.")
    return parser.parse_args()


if __name__ == "__main__":
    main()
