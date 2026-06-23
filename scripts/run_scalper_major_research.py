#!/usr/bin/env python3
"""Run Scalper Major research on local Dukascopy/Yahoo OHLCV datasets."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data.ohlcv import load_ohlcv_csv
from strategies.ScalperMajorHighVolatility import (
    RecoveryConfig,
    ScalperMajorConfig,
    backtest_scalper_major,
    backtest_scalper_major_recovery,
    generate_scalper_major_report,
)
from strategies.ScalperMajorHighVolatility.research import (
    ScalperMajorWalkForwardConfig,
    run_scalper_major_walk_forward,
)


DEFAULT_SYMBOLS = ("EURUSD", "GBPUSD", "USDCAD", "USDCHF")
DEFAULT_TIMEFRAMES = ("m1", "m5", "m15", "m30", "h1", "d1")


def main() -> int:
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    strategy_config = ScalperMajorConfig(
        initial_cash=args.initial_cash,
        risk_fraction=args.risk_fraction,
        stop_atr_multiple=args.stop_atr_multiple,
        take_profit_atr_multiple=args.take_profit_atr_multiple,
        max_holding_bars=args.max_holding_bars,
        commission_per_turnover=args.fees,
        slippage=args.slippage,
        use_talib=not args.no_talib,
    )

    rows: list[dict[str, Any]] = []
    for (symbol, timeframe), paths in _discover_datasets(args).items():
        data = _load_dataset_chunks(paths, symbol=symbol)
        if args.tail and len(data) > args.tail:
            data = data.tail(args.tail)
        if len(data) < strategy_config.required_history + 2:
            continue

        result = _run_backtest(data, strategy_config, args)
        report_path = ""
        if args.generate_reports:
            report = generate_scalper_major_report(
                result,
                name=f"{args.name}_{symbol}_{timeframe}_{args.mode}",
                title=f"Scalper Major {symbol} {timeframe.upper()} {args.mode}",
                output_dir=args.report_dir,
                render_charts=not args.skip_report_charts,
            )
            report_path = str(report.output_dir)
        walk_config = _walk_config_for_rows(len(data), timeframe, args)
        walk_csv = ""
        walk_summary: dict[str, float | int | None] = {
            "folds": 0,
            "oos_total_return_mean": None,
            "oos_total_return_compound": None,
            "oos_sharpe_mean": None,
            "oos_max_drawdown_worst": None,
            "oos_trades_total": 0,
            "profitable_folds": 0,
        }
        if args.mode == "signal_only" and walk_config is not None:
            walk, walk_summary = run_scalper_major_walk_forward(
                data,
                walk_config=walk_config,
                strategy_config=strategy_config,
            )
            walk_path = args.output_dir / f"{args.name}_{symbol}_{timeframe}_walk_forward.csv"
            walk.to_csv(walk_path, index=False)
            walk_csv = str(walk_path)

        row = {
            "symbol": symbol,
            "timeframe": timeframe.upper(),
            "mode": args.mode,
            "paths": len(paths),
            "rows": len(data),
            "start": data.index.min(),
            "end": data.index.max(),
            "backend": result.indicators["indicator_backend"].iloc[-1],
            "total_return": result.metrics.get("total_return"),
            "annualized_return": result.metrics.get("annualized_return"),
            "annualized_volatility": result.metrics.get("annualized_volatility"),
            "sharpe_ratio": result.metrics.get("sharpe_ratio"),
            "max_drawdown": result.metrics.get("max_drawdown"),
            "profit_factor": result.metrics.get("profit_factor"),
            "expected_payoff": result.metrics.get("expected_payoff"),
            "recovery_factor": result.metrics.get("recovery_factor"),
            "gross_profit": result.metrics.get("gross_profit"),
            "gross_loss": result.metrics.get("gross_loss"),
            "net_profit": result.metrics.get("net_profit"),
            "win_rate": result.metrics.get("win_rate"),
            "trade_count": result.metrics.get("trade_count"),
            **walk_summary,
            "walk_forward_csv": walk_csv,
            "report_path": report_path,
        }
        rows.append(row)

    summary = pd.DataFrame(rows).sort_values(["symbol", "timeframe"], ignore_index=True)
    summary_csv = args.output_dir / f"{args.name}_summary.csv"
    summary_md = args.output_dir / f"{args.name}_summary.md"
    summary.to_csv(summary_csv, index=False)
    summary_md.write_text(_to_markdown(summary), encoding="utf-8")
    print(f"Wrote {summary_csv}")
    print(f"Wrote {summary_md}")
    return 0


def _discover_datasets(args: argparse.Namespace) -> dict[tuple[str, str], list[Path]]:
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    if args.datasets:
        for path in args.datasets:
            symbol, timeframe = _infer_symbol_timeframe(path)
            if symbol in args.symbols and timeframe in args.timeframes:
                groups[(symbol, timeframe)].append(path)
        return {key: sorted(paths) for key, paths in groups.items()}

    for symbol in args.symbols:
        symbol_dir = args.datasets_dir / symbol
        for timeframe in args.timeframes:
            pattern = f"{symbol}_{timeframe}_*_*.csv"
            groups[(symbol, timeframe)].extend(symbol_dir.glob(pattern))
    return {key: sorted(paths) for key, paths in groups.items() if paths}


def _load_dataset_chunks(paths: list[Path], *, symbol: str) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path, symbol=symbol) for path in paths]
    data = pd.concat(frames).sort_index()
    data = data.loc[~data.index.duplicated(keep="last")]
    data.attrs["symbol"] = symbol
    return data


def _run_backtest(
    data: pd.DataFrame,
    strategy_config: ScalperMajorConfig,
    args: argparse.Namespace,
):
    if args.mode == "basket_recovery":
        return backtest_scalper_major_recovery(
            data,
            strategy_config,
            RecoveryConfig(
                initial_cash=args.initial_cash,
                base_lot=args.base_lot,
                max_positions_per_direction=args.max_recovery_positions,
                grid_atr_multiple=args.grid_atr_multiple,
                profit_to_loss_ratio=args.profit_to_loss_ratio,
                pip_size=args.pip_size,
                pip_value_per_lot=args.pip_value_per_lot,
                commission_per_lot=args.commission_per_lot,
                contract_size=args.contract_size,
                leverage=args.leverage,
                max_global_drawdown=args.max_global_drawdown,
                allow_hedged_baskets=not args.no_hedged_baskets,
            ),
        )
    return backtest_scalper_major(data, strategy_config)


def _infer_symbol_timeframe(path: Path) -> tuple[str, str]:
    name = path.stem.upper()
    parts = name.split("_")
    symbol = parts[0]
    timeframe = next((part.lower() for part in parts if part.lower() in DEFAULT_TIMEFRAMES), "")
    if not timeframe:
        raise ValueError(f"Could not infer timeframe from {path}")
    return symbol, timeframe


def _walk_config_for_rows(
    rows: int,
    timeframe: str,
    args: argparse.Namespace,
) -> ScalperMajorWalkForwardConfig | None:
    train_size = args.train_size or _default_train_size(timeframe)
    test_size = args.test_size or _default_test_size(timeframe)
    step_size = args.step_size or test_size
    min_required = train_size + args.purge_size + args.embargo_size + test_size
    if rows < min_required:
        return None
    return ScalperMajorWalkForwardConfig(
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        window_type=args.window_type,
        purge_size=args.purge_size,
        embargo_size=args.embargo_size,
    )


def _default_train_size(timeframe: str) -> int:
    return {
        "m1": 20_000,
        "m5": 8_000,
        "m15": 4_000,
        "m30": 3_000,
        "h1": 2_000,
        "d1": 750,
    }.get(timeframe.lower(), 1_000)


def _default_test_size(timeframe: str) -> int:
    return {
        "m1": 5_000,
        "m5": 2_000,
        "m15": 1_000,
        "m30": 750,
        "h1": 500,
        "d1": 250,
    }.get(timeframe.lower(), 250)


def _to_markdown(data: pd.DataFrame) -> str:
    display = data.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    headers = [str(column) for column in display.columns]
    rows = [[str(value) for value in row] for row in display.fillna("").to_numpy()]
    lines = [_markdown_row(headers), _markdown_row(["---"] * len(headers))]
    lines.extend(_markdown_row(row) for row in rows)
    return "\n".join(lines) + "\n"


def _markdown_row(values: list[str]) -> str:
    return "| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest Scalper Major across local OHLCV timeframes.")
    parser.add_argument("datasets", nargs="*", type=Path, help="Optional explicit dataset CSV paths.")
    parser.add_argument("--datasets-dir", type=Path, default=Path("datasets"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframes", nargs="+", default=list(DEFAULT_TIMEFRAMES))
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/research"))
    parser.add_argument("--name", default="scalper_major_high_volatility")
    parser.add_argument("--mode", choices=("signal_only", "basket_recovery"), default="signal_only")
    parser.add_argument("--initial-cash", type=float, default=20_000.0)
    parser.add_argument("--risk-fraction", type=float, default=0.01)
    parser.add_argument("--stop-atr-multiple", type=float, default=1.5)
    parser.add_argument("--take-profit-atr-multiple", type=float, default=1.0)
    parser.add_argument("--max-holding-bars", type=int, default=12)
    parser.add_argument("--fees", type=float, default=0.00007)
    parser.add_argument("--slippage", type=float, default=0.00005)
    parser.add_argument("--tail", type=int, default=0)
    parser.add_argument("--train-size", type=int, default=0)
    parser.add_argument("--test-size", type=int, default=0)
    parser.add_argument("--step-size", type=int, default=0)
    parser.add_argument("--window-type", choices=("rolling", "expanding"), default="rolling")
    parser.add_argument("--purge-size", type=int, default=0)
    parser.add_argument("--embargo-size", type=int, default=0)
    parser.add_argument("--no-talib", action="store_true", help="Disable TA-Lib backend and use pandas fallback.")
    parser.add_argument("--generate-reports", action="store_true", help="Create visualization reports under --report-dir.")
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/reports"))
    parser.add_argument("--skip-report-charts", action="store_true")
    parser.add_argument("--base-lot", type=float, default=0.01)
    parser.add_argument("--max-recovery-positions", type=int, default=14)
    parser.add_argument("--grid-atr-multiple", type=float, default=1.0)
    parser.add_argument("--profit-to-loss-ratio", type=float, default=3.0)
    parser.add_argument("--pip-size", type=float, default=0.0001)
    parser.add_argument("--pip-value-per-lot", type=float, default=10.0)
    parser.add_argument("--commission-per-lot", type=float, default=7.0)
    parser.add_argument("--contract-size", type=float, default=100_000.0)
    parser.add_argument("--leverage", type=float, default=100.0)
    parser.add_argument("--max-global-drawdown", type=float, default=0.25)
    parser.add_argument("--no-hedged-baskets", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
