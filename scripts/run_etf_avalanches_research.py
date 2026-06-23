#!/usr/bin/env python3
"""Run ETF Avalanches on local OHLCV CSVs."""

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

from strategies.ETFAvalanches import (
    ETF_AVALANCHES_CORE_UNIVERSE,
    ETFAvalanchesConfig,
    backtest_etf_avalanches,
    load_etf_avalanche_ohlcv,
    validate_live_readiness,
)
from strategies.ETFAvalanches.backtesting import (
    ETFAvalanchesVectorBTConfig,
    run_etf_avalanches_vectorbt,
)
from strategies.ETFAvalanches.reporting import generate_etf_avalanches_report
from strategies.ETFAvalanches.research import (
    ETFAvalanchesWalkForwardConfig,
    run_etf_avalanches_walk_forward,
)


def main() -> int:
    args = _parse_args()
    dataset_paths = _resolve_dataset_paths(args)
    prices, highs, _ = load_etf_avalanche_ohlcv(dataset_paths, join=args.join)
    config = ETFAvalanchesConfig(
        cash_symbol=args.cash_symbol.upper(),
        long_lookback=args.long_lookback,
        intermediate_lookback=args.intermediate_lookback,
        entry_rsi=args.entry_rsi,
        exit_rsi=args.exit_rsi,
        limit_entry_pct=args.limit_entry_pct,
        volatility_lookback=args.volatility_lookback,
        max_positions=args.max_positions,
        initial_cash=args.initial_cash,
        trading_cost=args.fees,
        live_required_symbols=tuple(symbol.upper() for symbol in args.symbols),
    )
    if args.use_vectorbt:
        result = run_etf_avalanches_vectorbt(
            prices,
            highs,
            strategy_config=config,
            vectorbt_config=ETFAvalanchesVectorBTConfig(
                init_cash=args.initial_cash,
                fees=args.fees,
                slippage=args.slippage,
                freq="1d",
            ),
        ).pandas_result
    else:
        result = backtest_etf_avalanches(prices, highs, config)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result.equity.rename("equity").to_csv(args.output_dir / f"{args.name}_equity.csv")
    result.drawdown.rename("drawdown").to_csv(args.output_dir / f"{args.name}_drawdown.csv")
    result.trades.to_csv(args.output_dir / f"{args.name}_trades.csv", index=False)
    result.closed_trades.to_csv(args.output_dir / f"{args.name}_closed_trades.csv", index=False)
    result.target_weights.to_csv(args.output_dir / f"{args.name}_target_weights.csv")
    result.asset_performance.to_csv(args.output_dir / f"{args.name}_asset_performance.csv", index=False)
    readiness = validate_live_readiness(
        prices,
        highs,
        config,
        broker_symbol_map=_broker_symbol_map(args),
        shortable_symbols=set(symbol.upper() for symbol in args.shortable_symbols),
    )
    readiness_path = args.output_dir / f"{args.name}_live_readiness.json"
    readiness_path.write_text(json.dumps(readiness, indent=2, sort_keys=True), encoding="utf-8")

    metrics_path = args.output_dir / f"{args.name}_metrics.json"
    metrics: dict[str, Any] = dict(result.metrics)
    metrics["symbols"] = list(prices.columns)
    metrics["generated_at"] = datetime.now(tz=UTC).isoformat()
    metrics["average_short_exposure"] = float(
        result.weights.drop(columns=[config.cash_symbol], errors="ignore").clip(upper=0.0).abs().sum(axis=1).mean()
    )
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")

    if not args.skip_report:
        report = generate_etf_avalanches_report(
            result,
            name=args.name,
            output_dir=args.report_dir,
            render_charts=not args.skip_report_charts,
        )
        print(f"Wrote report to {report.output_dir}")

    if args.walk_forward:
        walk_config = ETFAvalanchesWalkForwardConfig(
            train_size=args.wf_train_size,
            test_size=args.wf_test_size,
            step_size=args.wf_step_size,
            window_type=args.wf_window_type,
            purge_size=args.wf_purge_size,
            embargo_size=args.wf_embargo_size,
        )
        wf_results, wf_assets, wf_summary = run_etf_avalanches_walk_forward(
            prices,
            highs,
            walk_config=walk_config,
            strategy_config=config,
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

    print(f"Ran ETF Avalanches on {len(prices.columns)} symbols and {len(prices)} rows")
    print(f"Wrote metrics to {metrics_path}")
    print(f"Wrote live readiness to {readiness_path}")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest ETF Avalanches on local datasets.")
    parser.add_argument("--symbols", nargs="+", default=[*ETF_AVALANCHES_CORE_UNIVERSE, "SHY"])
    parser.add_argument(
        "--dataset",
        action="append",
        default=[],
        metavar="SYMBOL=PATH",
        help="Override or add a dataset path, e.g. SPY=datasets/SPY/SPY_1d_yfinance.csv",
    )
    parser.add_argument("--broker-symbol", dest="broker_symbols", nargs=2, action="append", metavar=("SYMBOL", "BROKER_SYMBOL"))
    parser.add_argument("--shortable-symbols", nargs="+", default=[])
    parser.add_argument("--join", choices=["inner", "outer"], default="inner")
    parser.add_argument("--cash-symbol", default="SHY")
    parser.add_argument("--long-lookback", type=int, default=252)
    parser.add_argument("--intermediate-lookback", type=int, default=21)
    parser.add_argument("--entry-rsi", type=float, default=70.0)
    parser.add_argument("--exit-rsi", type=float, default=15.0)
    parser.add_argument("--limit-entry-pct", type=float, default=0.03)
    parser.add_argument("--volatility-lookback", type=int, default=100)
    parser.add_argument("--max-positions", type=int, default=5)
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--fees", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--use-vectorbt", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/research"))
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/reports"))
    parser.add_argument("--name", default="etf_avalanches_local_dev")
    parser.add_argument("--skip-report", action="store_true")
    parser.add_argument("--skip-report-charts", action="store_true")
    parser.add_argument("--walk-forward", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--wf-train-size", type=int, default=756)
    parser.add_argument("--wf-test-size", type=int, default=126)
    parser.add_argument("--wf-step-size", type=int, default=126)
    parser.add_argument("--wf-window-type", choices=["rolling", "expanding"], default="rolling")
    parser.add_argument("--wf-purge-size", type=int, default=0)
    parser.add_argument("--wf-embargo-size", type=int, default=5)
    parsed = parser.parse_args()
    if parsed.broker_symbols:
        parsed.broker_symbols = [value for pair in parsed.broker_symbols for value in pair]
    return parsed


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


def _broker_symbol_map(args: argparse.Namespace) -> dict[str, str]:
    if not args.broker_symbols:
        return {}
    if len(args.broker_symbols) % 2:
        raise ValueError("--broker-symbol values must be SYMBOL BROKER_SYMBOL pairs")
    items = iter(args.broker_symbols)
    return {symbol.upper(): broker_symbol for symbol, broker_symbol in zip(items, items)}


if __name__ == "__main__":
    raise SystemExit(main())
