#!/usr/bin/env python3
"""Validate that yfinance can import and download a small sample."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a small yfinance health check.")
    parser.add_argument("--ticker", default="AAPL", help="Ticker to test. Default: AAPL")
    parser.add_argument("--period", default="5d", help="History period. Default: 5d")
    parser.add_argument("--interval", default="1d", help="History interval. Default: 1d")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except Exception as exc:
        print(f"ERROR: Could not import yfinance: {exc}", file=sys.stderr)
        print("Install with: python -m pip install --upgrade yfinance pandas", file=sys.stderr)
        return 1

    print(f"yfinance version: {getattr(yf, '__version__', 'unknown')}")
    print(f"pandas version: {pd.__version__}")
    print(f"UTC time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Downloading {args.ticker} period={args.period} interval={args.interval}")

    try:
        data = yf.download(args.ticker, period=args.period, interval=args.interval, progress=False)
    except Exception as exc:
        print(f"ERROR: Download failed: {exc}", file=sys.stderr)
        return 2

    if data is None or data.empty:
        print("ERROR: yfinance returned an empty DataFrame.", file=sys.stderr)
        return 3

    print("Download OK")
    print(data.tail())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
