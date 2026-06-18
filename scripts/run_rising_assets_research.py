#!/usr/bin/env python3
"""Run Rising Assets research on local stock/ETF CSV files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.RisingAssest import RisingAssetsConfig, load_price_universe, validate_live_readiness
from strategies.RisingAssest.backtesting import RisingAssetsVectorBTConfig, run_rising_assets_vectorbt
from strategies.RisingAssest.reporting import generate_rising_assets_report


DEFAULT_DATASETS = {
    "SPY": Path("datasets/SPY/SPYdata.csv"),
    "QQQ": Path("datasets/QQQ/Invesco QQQ 5  Years price Data.csv"),
}


def main() -> None:
    args = _parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    prices = load_price_universe(_dataset_mapping(args))
    strategy_config = RisingAssetsConfig(
        top_n=args.top_n,
        initial_cash=args.init_cash,
        trading_cost=args.fees,
        positive_momentum_only=args.positive_momentum_only,
    )
    vectorbt_config = RisingAssetsVectorBTConfig(
        init_cash=args.init_cash,
        fees=args.fees,
        slippage=args.slippage,
        freq=args.freq,
    )
    result = run_rising_assets_vectorbt(
        prices,
        strategy_config=strategy_config,
        vectorbt_config=vectorbt_config,
    )
    report = generate_rising_assets_report(
        result.pandas_result,
        name=args.report_name,
        output_dir=args.report_dir,
        render_charts=not args.skip_report_charts,
    )

    metrics = pd.DataFrame([{**result.metrics, "rows": len(prices), "assets": ",".join(prices.columns)}])
    metrics_path = output_dir / f"{args.report_name}_metrics.csv"
    weights_path = output_dir / f"{args.report_name}_latest_weights.csv"
    readiness_path = output_dir / f"{args.report_name}_live_readiness.json"
    metrics.to_csv(metrics_path, index=False)
    result.pandas_result.target_weights.tail(1).T.rename(columns={result.pandas_result.target_weights.index[-1]: "target_weight"}).to_csv(weights_path)
    readiness = validate_live_readiness(prices, strategy_config, broker_symbol_map=_broker_symbol_map(args))
    readiness_path.write_text(json.dumps(readiness, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {metrics_path}")
    print(f"Wrote {weights_path}")
    print(f"Wrote {readiness_path}")
    print(f"Wrote report folder {report.output_dir}")


def _dataset_mapping(args: argparse.Namespace) -> dict[str, Path]:
    if not args.datasets:
        return dict(DEFAULT_DATASETS)
    if len(args.datasets) % 2:
        raise ValueError("--dataset values must be SYMBOL PATH pairs")
    items = iter(args.datasets)
    return {symbol.upper(): Path(path) for symbol, path in zip(items, items)}


def _broker_symbol_map(args: argparse.Namespace) -> dict[str, str]:
    if not args.broker_symbols:
        return {}
    if len(args.broker_symbols) % 2:
        raise ValueError("--broker-symbol values must be SYMBOL BROKER_SYMBOL pairs")
    items = iter(args.broker_symbols)
    return {symbol.upper(): broker_symbol for symbol, broker_symbol in zip(items, items)}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Rising Assets vectorbt research on local CSV files.")
    parser.add_argument("--dataset", dest="datasets", nargs=2, action="append", metavar=("SYMBOL", "CSV"))
    parser.add_argument("--broker-symbol", dest="broker_symbols", nargs=2, action="append", metavar=("SYMBOL", "BROKER_SYMBOL"))
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/research"))
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/reports"))
    parser.add_argument("--report-name", default="rising_assets_spy_qqq")
    parser.add_argument("--init-cash", type=float, default=10_000.0)
    parser.add_argument("--fees", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0005)
    parser.add_argument("--freq", default="1d")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--positive-momentum-only", action="store_true")
    parser.add_argument("--skip-report-charts", action="store_true")
    parsed = parser.parse_args()
    if parsed.datasets:
        parsed.datasets = [value for pair in parsed.datasets for value in pair]
    if parsed.broker_symbols:
        parsed.broker_symbols = [value for pair in parsed.broker_symbols for value in pair]
    return parsed


if __name__ == "__main__":
    main()
