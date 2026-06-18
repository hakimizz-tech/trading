#!/usr/bin/env python3
"""Fetch MT5 rates and save canonical OHLCV for strategy research.

Run this on Windows where MetaTrader 5 and the official MetaTrader5 Python
package are available. The script is read-only: it fetches bars, normalizes
them, writes CSV, and shuts the terminal connection down.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_data.ohlcv import process_ohlcv, quality_report, to_ohlcv_frame


def main() -> int:
    args = _parse_args()
    mt5 = _import_mt5()
    timeframe = _resolve_timeframe(mt5, args.timeframe)
    utc_from = _parse_utc(args.date_from)
    utc_to = _parse_utc(args.date_to)
    output = args.output or Path("datasets") / args.symbol / f"{args.symbol}_{args.timeframe}_{utc_from:%Y%m%d}_{utc_to:%Y%m%d}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)

    if not mt5.initialize(path=str(args.terminal_path) if args.terminal_path else None):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        _ensure_symbol(mt5, args.symbol)
        rates = mt5.copy_rates_range(args.symbol, timeframe, utc_from, utc_to)
        if rates is None:
            raise RuntimeError(f"copy_rates_range failed: {mt5.last_error()}")
        if len(rates) == 0:
            raise RuntimeError("No bars returned. Check symbol, timeframe, date range, and terminal chart history.")

        raw = to_ohlcv_frame(rates, source=f"mt5:{args.symbol}:{args.timeframe}", symbol=args.symbol)
        raw.attrs["timeframe"] = args.timeframe
        processed = process_ohlcv(raw, expected_freq=args.expected_freq, fill_gaps=args.fill_gaps, flag_quality=args.with_flags)
        processed.to_csv(output)
        report = quality_report(processed, source=str(output), symbol=args.symbol, timeframe=args.timeframe)
        print(f"Saved {len(processed)} normalized bars to {output}")
        print(report.as_dict())
        return 0
    finally:
        mt5.shutdown()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch MT5 rates and save canonical strategy-ready OHLCV.")
    parser.add_argument("--symbol", required=True, help="Broker symbol, e.g. EURUSD, EURUSDm, XAUUSD.pro")
    parser.add_argument("--timeframe", default="H1", help="MT5 timeframe suffix, e.g. M1, M15, H1, H4, D1")
    parser.add_argument("--from", dest="date_from", required=True, help="UTC ISO date, e.g. 2024-01-01T00:00:00Z")
    parser.add_argument("--to", dest="date_to", required=True, help="UTC ISO date, e.g. 2024-02-01T00:00:00Z")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--terminal-path", type=Path, default=None, help="Optional terminal64.exe path")
    parser.add_argument("--expected-freq", default=None, help="Optional pandas frequency for gap filling, e.g. 15min, 1h")
    parser.add_argument("--fill-gaps", action="store_true", help="Forward-fill short gaps and mark is_filled")
    parser.add_argument("--with-flags", action="store_true", help="Add anomaly/is_filled columns to output")
    return parser.parse_args()


def _import_mt5():
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:  # pragma: no cover - depends on Windows MT5 environment.
        raise RuntimeError(
            "MetaTrader5 is not installed. Run this on Windows with MetaTrader 5 "
            "and install the official package in that environment."
        ) from exc
    return mt5


def _resolve_timeframe(mt5, value: str) -> int:
    attr = f"TIMEFRAME_{value.strip().upper()}"
    timeframe = getattr(mt5, attr, None)
    if timeframe is None:
        raise ValueError(f"Unsupported MT5 timeframe: {value!r}")
    return timeframe


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_symbol(mt5, symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol not found: {symbol}. Broker symbols may use suffixes like EURUSDm or XAUUSD.pro.")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select symbol {symbol}: {mt5.last_error()}")


if __name__ == "__main__":
    raise SystemExit(main())
