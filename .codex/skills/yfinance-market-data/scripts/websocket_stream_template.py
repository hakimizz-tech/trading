#!/usr/bin/env python3
"""Template for yfinance WebSocket streaming. Stop with Ctrl+C."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream live prices using yfinance WebSocket.")
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols to subscribe to, e.g. AAPL MSFT")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except Exception as exc:
        print(f"ERROR: Could not import yfinance: {exc}", file=sys.stderr)
        return 1

    ws = yf.WebSocket()
    ws.subscribe(args.symbols)
    print(f"Subscribed to: {', '.join(args.symbols)}")
    print("Listening. Press Ctrl+C to stop.")
    try:
        ws.listen()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
