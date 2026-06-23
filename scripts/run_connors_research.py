#!/usr/bin/env python3
"""Run Connors Weekly Mean Reversion research on local OHLCV CSVs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.ConnorsResearchWeeklyMeanReversion import (
    ConnorsWeeklyMeanReversionConfig,
    backtest_connors_weekly_mean_reversion,
    compute_asset_performance,
    load_connors_ohlcv_universe,
)
from strategies.ConnorsResearchWeeklyMeanReversion.backtesting import (
    ConnorsVectorBTConfig,
    run_connors_vectorbt,
)
from strategies.ConnorsResearchWeeklyMeanReversion.reporting import generate_connors_report
from strategies.ConnorsResearchWeeklyMeanReversion.research import ConnorsWalkForwardConfig, run_connors_walk_forward


DEFAULT_SYMBOLS: tuple[str, ...] = ("AAPL", "MSFT", "NVDA", "QQQ", "SPY", "SHY")


def main() -> int:
    args = _parse_args()
    dataset_paths = _resolve_dataset_paths(args)
    prices, volumes = load_connors_ohlcv_universe(dataset_paths, join=args.join)
    strategy_config = ConnorsWeeklyMeanReversionConfig(
        initial_cash=args.initial_cash,
        trading_cost=args.fees,
        liquid_universe_size=args.liquid_universe_size,
        max_positions=args.max_positions,
        stop_loss_pct=args.stop_loss_pct,
    )

    if args.use_vectorbt:
        result = run_connors_vectorbt(
            prices,
            volumes,
            strategy_config=strategy_config,
            vectorbt_config=ConnorsVectorBTConfig(
                init_cash=args.initial_cash,
                fees=args.fees,
                slippage=args.slippage,
                freq="1d",
            ),
        ).pandas_result
    else:
        result = backtest_connors_weekly_mean_reversion(prices, volumes, strategy_config)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.equity.rename("equity").to_csv(args.output_dir / f"{args.name}_equity.csv")
    result.drawdown.rename("drawdown").to_csv(args.output_dir / f"{args.name}_drawdown.csv")
    result.trades.to_csv(args.output_dir / f"{args.name}_trades.csv", index=False)
    result.target_weights.to_csv(args.output_dir / f"{args.name}_target_weights.csv")
    asset_performance = compute_asset_performance(result)
    asset_performance.to_csv(args.output_dir / f"{args.name}_asset_performance.csv", index=False)
    metrics_path = args.output_dir / f"{args.name}_metrics.json"
    metrics: dict[str, Any] = dict(result.metrics)
    metrics["symbols"] = list(prices.columns)
    metrics["generated_at"] = datetime.now(tz=UTC).isoformat()
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    if not args.skip_report:
        report = generate_connors_report(
            result,
            name=args.name,
            output_dir=args.report_dir,
            render_charts=not args.skip_report_charts,
        )
        print(f"Wrote report to {report.output_dir}")

    if args.walk_forward:
        walk_config = ConnorsWalkForwardConfig(
            train_size=args.wf_train_size,
            test_size=args.wf_test_size,
            step_size=args.wf_step_size,
            window_type=args.wf_window_type,
            purge_size=args.wf_purge_size,
            embargo_size=args.wf_embargo_size,
        )
        wf_results, wf_assets, wf_summary = run_connors_walk_forward(
            prices,
            volumes,
            walk_config=walk_config,
            strategy_config=strategy_config,
        )
        wf_results_path = args.output_dir / f"{args.name}_walk_forward.csv"
        wf_assets_path = args.output_dir / f"{args.name}_walk_forward_asset_performance.csv"
        wf_summary_path = args.output_dir / f"{args.name}_walk_forward_summary.json"
        wf_results.to_csv(wf_results_path, index=False)
        wf_assets.to_csv(wf_assets_path, index=False)
        wf_summary_path.write_text(json.dumps(wf_summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote walk-forward folds to {wf_results_path}")
        print(f"Wrote walk-forward asset performance to {wf_assets_path}")
        print(f"Wrote walk-forward summary to {wf_summary_path}")

    print(f"Ran Connors research on {len(prices.columns)} symbols and {len(prices)} rows")
    print(f"Wrote metrics to {metrics_path}")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest Connors Weekly Mean Reversion on local datasets.")
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        metavar="SYMBOL=PATH",
        help="Override or add a dataset path, e.g. AAPL=datasets/AAPL/AAPL_1d_yfinance.csv",
    )
    parser.add_argument("--join", choices=["inner", "outer"], default="inner")
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--fees", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--liquid-universe-size", type=int, default=500)
    parser.add_argument("--max-positions", type=int, default=10)
    parser.add_argument("--stop-loss-pct", type=float, default=0.10)
    parser.add_argument("--use-vectorbt", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/research"))
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/reports"))
    parser.add_argument("--name", default="connors_weekly_mean_reversion")
    parser.add_argument("--skip-report", action="store_true")
    parser.add_argument("--skip-report-charts", action="store_true")
    parser.add_argument("--walk-forward", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--wf-train-size", type=int, default=756)
    parser.add_argument("--wf-test-size", type=int, default=126)
    parser.add_argument("--wf-step-size", type=int, default=126)
    parser.add_argument("--wf-window-type", choices=["rolling", "expanding"], default="rolling")
    parser.add_argument("--wf-purge-size", type=int, default=0)
    parser.add_argument("--wf-embargo-size", type=int, default=5)
    return parser.parse_args()


def _resolve_dataset_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {symbol.upper(): Path("datasets") / symbol.upper() / f"{symbol.upper()}_1d_yfinance.csv" for symbol in args.symbols}
    for item in args.dataset:
        if "=" not in item:
            raise ValueError("--dataset must use SYMBOL=PATH format")
        symbol, path = item.split("=", 1)
        paths[symbol.strip().upper()] = Path(path.strip())
    missing = [f"{symbol}={path}" for symbol, path in paths.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing dataset files. Download them with scripts/download_yfinance_history.py or pass --dataset. "
            f"Missing: {', '.join(missing)}"
        )
    return paths


if __name__ == "__main__":
    raise SystemExit(main())
