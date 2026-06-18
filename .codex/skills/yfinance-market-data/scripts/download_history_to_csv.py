#!/usr/bin/env python3
"""Download historical market data with yfinance and save to CSV or parquet."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
        df = df.copy()
        df.columns = ["_".join(str(part) for part in col if str(part)) for col in df.columns]
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description="Download yfinance historical data.")
    parser.add_argument("--tickers", nargs="+", required=True, help="One or more Yahoo Finance tickers.")
    parser.add_argument("--start", help="Start date, e.g. 2020-01-01.")
    parser.add_argument("--end", help="End date, e.g. 2025-01-01.")
    parser.add_argument("--period", help="Alternative to start/end, e.g. 1y, 5y, max.")
    parser.add_argument("--interval", default="1d", help="Interval, e.g. 1d, 1h, 15m. Default: 1d")
    parser.add_argument("--auto-adjust", action="store_true", help="Use adjusted OHLC.")
    parser.add_argument("--raw", action="store_true", help="Set auto_adjust=False explicitly.")
    parser.add_argument("--actions", action="store_true", help="Include dividends and stock splits when available.")
    parser.add_argument("--repair", action="store_true", help="Attempt yfinance price repair.")
    parser.add_argument("--flatten", action="store_true", help="Flatten MultiIndex columns before saving.")
    parser.add_argument("--output", required=True, help="Output .csv or .parquet path.")
    parser.add_argument("--no-threads", action="store_true", help="Disable threaded downloads.")
    args = parser.parse_args()

    if not args.period and not (args.start or args.end):
        print("ERROR: Provide --period or --start/--end.", file=sys.stderr)
        return 2

    if args.auto_adjust and args.raw:
        print("ERROR: Choose either --auto-adjust or --raw, not both.", file=sys.stderr)
        return 2

    auto_adjust = True if args.auto_adjust else False if args.raw else None

    try:
        import yfinance as yf
    except Exception as exc:
        print(f"ERROR: Could not import yfinance: {exc}", file=sys.stderr)
        return 1

    params = {
        "tickers": args.tickers,
        "start": args.start,
        "end": args.end,
        "period": args.period,
        "interval": args.interval,
        "actions": args.actions,
        "repair": args.repair,
        "threads": not args.no_threads,
        "progress": False,
    }
    if auto_adjust is not None:
        params["auto_adjust"] = auto_adjust

    params = {k: v for k, v in params.items() if v is not None}
    data = yf.download(**params)

    if data is None or data.empty:
        print("ERROR: No data returned. Check tickers, date range, interval, and network.", file=sys.stderr)
        return 3

    if args.flatten:
        data = flatten_columns(data)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.suffix.lower() == ".parquet":
        data.to_parquet(output)
    elif output.suffix.lower() == ".csv":
        data.to_csv(output)
    else:
        print("ERROR: Output must end with .csv or .parquet.", file=sys.stderr)
        return 2

    print(f"Saved {len(data):,} rows and {len(data.columns):,} columns to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
