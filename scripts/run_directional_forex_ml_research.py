#!/usr/bin/env python3
"""Run Directional Forex ML research on local OHLCV datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data.ohlcv import load_ohlcv_csv
from strategies.DirectionalForexML import (
    DirectionalForexMLConfig,
    DirectionalForexMLWalkForwardConfig,
    backtest_directional_forex_ml,
    generate_directional_forex_ml_model_comparison_charts,
    generate_directional_forex_ml_report,
    invert_usd_base_quote,
    load_treasury_macro_csv,
    run_cost_sensitivity,
    run_directional_forex_ml_walk_forward,
    run_future_validation,
    run_regime_period_validation,
    run_var_backtests,
)
from strategies.DirectionalForexML.core import USD_BASE_TO_PAPER_SYMBOL


DEFAULT_SYMBOLS = ("EURUSD", "AUDUSD", "USDJPY", "USDCHF", "USDCNY", "USDMXN", "USDZAR", "USDTRY")
DEFAULT_MODELS = ("logistic_madl", "logistic")
PAPER_MODELS = ("logistic", "logistic_madl", "decision_tree", "random_forest", "gradient_boosting", "adaboost", "xgboost", "mlp")


def main() -> int:
    args = _parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    datasets = _discover_datasets(args)
    macro = (
        load_treasury_macro_csv(
            args.macro_csv,
            date_column=args.macro_date_column,
            rate_5y_column=args.macro_rate_5y_column,
            rate_13w_column=args.macro_rate_13w_column,
        )
        if args.macro_csv
        else None
    )
    for symbol, path in datasets.items():
        data = load_ohlcv_csv(path, symbol=symbol)
        research_symbol = symbol
        if args.invert_usd_base_to_paper and symbol.upper() in USD_BASE_TO_PAPER_SYMBOL:
            data = invert_usd_base_quote(data)
            research_symbol = USD_BASE_TO_PAPER_SYMBOL[symbol.upper()]
        if args.start:
            data = data.loc[data.index >= pd.Timestamp(args.start, tz="UTC")]
        if args.end:
            data = data.loc[data.index <= pd.Timestamp(args.end, tz="UTC")]
        if args.tail and len(data) > args.tail:
            data = data.tail(args.tail)
        for model_name in args.models:
            config = DirectionalForexMLConfig(
                model_name=model_name,
                feature_set=args.feature_set,
                probability_threshold=args.threshold,
                cost_buffer_pct=args.cost_buffer_pct,
                initial_cash=args.initial_cash,
                train_fraction=args.train_fraction,
                random_search_iterations=args.random_search_iterations,
                enable_hyperparameter_search=not args.disable_hyperparameter_search,
                use_macro_features=macro is not None and args.use_macro_features,
            )
            data_macro = macro.reindex(data.index) if macro is not None else None
            try:
                result = backtest_directional_forex_ml(data, symbol=research_symbol, config=config, macro=data_macro)
            except ValueError as exc:
                rows.append(
                    {
                        "symbol": symbol,
                        "research_symbol": research_symbol,
                        "model": model_name,
                        "path": str(path),
                        "error": str(exc),
                    }
                )
                continue
            report_path = ""
            if args.generate_reports:
                report = generate_directional_forex_ml_report(
                    result,
                    name=f"{args.name}_{symbol}_{model_name}",
                    title=f"Directional Forex ML {research_symbol} {model_name}",
                    output_dir=args.report_dir,
                    render_charts=not args.skip_report_charts,
                )
                report_path = str(report.output_dir)
            rows.append(
                {
                    "symbol": symbol,
                    "research_symbol": research_symbol,
                    "model": model_name,
                    "path": str(path),
                    "rows": len(data),
                    "test_rows": len(result.returns),
                    "start": data.index.min(),
                    "end": data.index.max(),
                    **result.metrics,
                    "report_path": report_path,
                }
            )
            if args.walk_forward:
                walk_config = DirectionalForexMLWalkForwardConfig(
                    train_size=args.train_size,
                    test_size=args.test_size,
                    step_size=args.step_size,
                    purge_size=args.purge_size,
                    embargo_size=args.embargo_size,
                    window_type=args.window_type,
                )
                walk, walk_summary = run_directional_forex_ml_walk_forward(
                    data,
                    symbol=research_symbol,
                    walk_config=walk_config,
                    strategy_config=config,
                    macro=data_macro,
                )
                walk_path = args.output_dir / f"{args.name}_{symbol}_{model_name}_walk_forward.csv"
                walk.to_csv(walk_path, index=False)
                rows[-1].update(
                    {
                        **walk_summary,
                        "walk_forward_csv": str(walk_path),
                    }
                )
            if args.regime_validation:
                regime = run_regime_period_validation(data, symbol=research_symbol, config=config, macro=data_macro)
                regime_path = args.output_dir / f"{args.name}_{symbol}_{model_name}_regimes.csv"
                regime.to_csv(regime_path, index=False)
                rows[-1]["regime_validation_csv"] = str(regime_path)
            if args.future_validation:
                try:
                    future = run_future_validation(
                        data,
                        symbol=research_symbol,
                        config=config,
                        train_end=args.future_train_end,
                        future_start=args.future_start,
                        macro=data_macro,
                    )
                    rows[-1].update({f"future_{key}": value for key, value in future.items()})
                except ValueError as exc:
                    rows[-1]["future_error"] = str(exc)
            if args.cost_sensitivity:
                sensitivity = run_cost_sensitivity(
                    data,
                    symbol=research_symbol,
                    config=config,
                    multipliers=tuple(args.cost_multipliers),
                    macro=data_macro,
                )
                sensitivity_path = args.output_dir / f"{args.name}_{symbol}_{model_name}_cost_sensitivity.csv"
                sensitivity.to_csv(sensitivity_path, index=False)
                rows[-1]["cost_sensitivity_csv"] = str(sensitivity_path)
            if args.var_backtest:
                var = run_var_backtests(result.returns, window=args.var_window)
                var_path = args.output_dir / f"{args.name}_{symbol}_{model_name}_var_backtest.csv"
                var.to_csv(var_path, index=False)
                rows[-1]["var_backtest_csv"] = str(var_path)

    summary = pd.DataFrame(rows)
    summary_csv = args.output_dir / f"{args.name}_summary.csv"
    summary_md = args.output_dir / f"{args.name}_summary.md"
    summary.to_csv(summary_csv, index=False)
    summary_md.write_text(_to_markdown(summary), encoding="utf-8")
    if args.generate_comparison_charts:
        chart_paths = generate_directional_forex_ml_model_comparison_charts(
            summary,
            output_dir=args.report_dir / f"{args.name}_comparison",
        )
        charts_md = args.output_dir / f"{args.name}_charts.md"
        charts_md.write_text(_charts_to_markdown(chart_paths), encoding="utf-8")
    print(f"Wrote {summary_csv}")
    print(f"Wrote {summary_md}")
    return 0


def _discover_datasets(args: argparse.Namespace) -> dict[str, Path]:
    if args.datasets:
        return {_infer_symbol(path): path for path in args.datasets}
    found: dict[str, Path] = {}
    for symbol in args.symbols:
        symbol_dir = args.datasets_dir / symbol
        candidates = sorted(symbol_dir.glob("*d1*.csv")) + sorted(symbol_dir.glob("*D1*.csv")) + sorted(symbol_dir.glob("*.csv"))
        if candidates:
            found[symbol] = candidates[0]
    return found


def _infer_symbol(path: Path) -> str:
    parent = path.parent.name.upper().replace("_", "")
    if parent and parent != "DATASETS":
        return parent
    return path.stem.split("_")[0].upper().replace("_", "")


def _to_markdown(data: pd.DataFrame) -> str:
    if data.empty:
        return "No results.\n"
    display = data.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    headers = [str(column) for column in display.columns]
    rows = [[str(value) for value in row] for row in display.fillna("").to_numpy()]
    lines = [_markdown_row(headers), _markdown_row(["---"] * len(headers))]
    lines.extend(_markdown_row(row) for row in rows)
    return "\n".join(lines) + "\n"


def _charts_to_markdown(paths: dict[str, Path]) -> str:
    if not paths:
        return "No charts generated.\n"
    lines = ["# Directional Forex ML Charts", ""]
    for name, path in paths.items():
        lines.append(f"- {name}: `{path}`")
    return "\n".join(lines) + "\n"


def _markdown_row(values: list[str]) -> str:
    return "| " + " | ".join(value.replace("|", "\\|") for value in values) + " |"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backtest Directional Forex ML models.")
    parser.add_argument("datasets", nargs="*", type=Path)
    parser.add_argument("--datasets-dir", type=Path, default=Path("datasets"))
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--paper-models", action="store_true", help="Run the paper's full model set, including XGBoost.")
    parser.add_argument("--name", default="directional_forex_ml")
    parser.add_argument("--output-dir", type=Path, default=Path("trade_results/research"))
    parser.add_argument("--report-dir", type=Path, default=Path("trade_results/reports"))
    parser.add_argument("--generate-reports", action="store_true")
    parser.add_argument("--generate-comparison-charts", action="store_true")
    parser.add_argument("--skip-report-charts", action="store_true")
    parser.add_argument("--feature-set", choices=("paper_technical", "extended"), default="paper_technical")
    parser.add_argument("--macro-csv", type=Path)
    parser.add_argument("--macro-date-column", default="date")
    parser.add_argument("--macro-rate-5y-column", default="rate_5y")
    parser.add_argument("--macro-rate-13w-column", default="rate_13w")
    parser.add_argument("--use-macro-features", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.54)
    parser.add_argument("--cost-buffer-pct", type=float, default=0.0)
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    parser.add_argument("--train-fraction", type=float, default=0.75)
    parser.add_argument("--random-search-iterations", type=int, default=10)
    parser.add_argument("--disable-hyperparameter-search", action="store_true")
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--regime-validation", action="store_true")
    parser.add_argument("--future-validation", action="store_true")
    parser.add_argument("--future-train-end", default="2022-12-31")
    parser.add_argument("--future-start", default="2023-01-01")
    parser.add_argument("--cost-sensitivity", action="store_true")
    parser.add_argument("--cost-multipliers", nargs="+", type=float, default=[0.5, 1.0, 1.5, 2.0])
    parser.add_argument("--var-backtest", action="store_true")
    parser.add_argument("--var-window", type=int, default=250)
    parser.add_argument("--invert-usd-base-to-paper", action="store_true")
    parser.add_argument("--train-size", type=int, default=1_000)
    parser.add_argument("--test-size", type=int, default=250)
    parser.add_argument("--step-size", type=int, default=250)
    parser.add_argument("--purge-size", type=int, default=1)
    parser.add_argument("--embargo-size", type=int, default=1)
    parser.add_argument("--window-type", choices=("rolling", "expanding"), default="rolling")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--tail", type=int)
    args = parser.parse_args()
    if args.paper_models:
        args.models = list(PAPER_MODELS)
    return args


if __name__ == "__main__":
    raise SystemExit(main())
