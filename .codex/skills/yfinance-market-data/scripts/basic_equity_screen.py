#!/usr/bin/env python3
"""Run a simple yfinance EquityQuery screen and save JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a basic yfinance equity screen.")
    parser.add_argument("--region", default="us", help="Region filter. Default: us")
    parser.add_argument("--min-market-cap", type=float, default=10_000_000_000, help="Minimum intraday market cap.")
    parser.add_argument("--size", type=int, default=25, help="Number of results.")
    parser.add_argument("--sort-field", default="intradaymarketcap", help="Sort field.")
    parser.add_argument("--ascending", action="store_true", help="Sort ascending.")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except Exception as exc:
        print(f"ERROR: Could not import yfinance: {exc}", file=sys.stderr)
        return 1

    query = yf.EquityQuery("and", [
        yf.EquityQuery("eq", ["region", args.region]),
        yf.EquityQuery("gt", ["intradaymarketcap", args.min_market_cap]),
    ])

    try:
        result = yf.screen(
            query,
            size=args.size,
            sortField=args.sort_field,
            sortAsc=args.ascending,
        )
    except Exception as exc:
        print(f"ERROR: Screen failed: {exc}", file=sys.stderr)
        return 2

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Saved screen result to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
