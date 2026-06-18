#!/usr/bin/env python3
"""Fetch MetaTrader5 bars and export them to CSV."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ensure_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol not found: {symbol}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol {symbol}: {mt5.last_error()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export MT5 historical bars to CSV.")
    parser.add_argument("--symbol", required=True, help="Broker symbol, e.g. EURUSD or XAUUSD")
    parser.add_argument("--timeframe", default="H1", choices=sorted(TIMEFRAMES))
    parser.add_argument("--from", dest="date_from", required=True, help="UTC ISO date, e.g. 2024-01-01T00:00:00Z")
    parser.add_argument("--to", dest="date_to", required=True, help="UTC ISO date, e.g. 2024-02-01T00:00:00Z")
    parser.add_argument("--out", default=None, help="Output CSV path")
    args = parser.parse_args()

    utc_from = parse_utc(args.date_from)
    utc_to = parse_utc(args.date_to)
    output = Path(args.out or f"{args.symbol}_{args.timeframe}_{utc_from:%Y%m%d}_{utc_to:%Y%m%d}.csv")

    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        ensure_symbol(args.symbol)
        rates = mt5.copy_rates_range(args.symbol, TIMEFRAMES[args.timeframe], utc_from, utc_to)
        if rates is None:
            raise RuntimeError(f"copy_rates_range failed: {mt5.last_error()}")
        if len(rates) == 0:
            raise RuntimeError("No bars returned. Check symbol, timeframe, date range, and terminal chart history.")

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.to_csv(output, index=False)
        print(f"Saved {len(df)} bars to {output}")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
