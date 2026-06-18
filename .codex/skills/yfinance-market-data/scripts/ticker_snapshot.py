#!/usr/bin/env python3
"""Create a compact JSON snapshot for one ticker using yfinance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timezone


def safe_json(value):
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create yfinance ticker snapshot JSON.")
    parser.add_argument("--ticker", required=True, help="Yahoo Finance ticker, e.g. MSFT")
    parser.add_argument("--period", default="1y", help="History period. Default: 1y")
    parser.add_argument("--interval", default="1d", help="History interval. Default: 1d")
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--include-news", action="store_true", help="Include recent news payload.")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except Exception as exc:
        print(f"ERROR: Could not import yfinance: {exc}", file=sys.stderr)
        return 1

    t = yf.Ticker(args.ticker)

    try:
        info = t.info or {}
    except Exception as exc:
        info = {"error": f"Failed to load info: {exc}"}

    try:
        fast_info = dict(t.fast_info)
    except Exception as exc:
        fast_info = {"error": f"Failed to load fast_info: {exc}"}

    try:
        hist = t.history(period=args.period, interval=args.interval)
        history_summary = {
            "rows": int(len(hist)),
            "start": str(hist.index.min()) if not hist.empty else None,
            "end": str(hist.index.max()) if not hist.empty else None,
            "last_row": hist.tail(1).reset_index().to_dict(orient="records")[0] if not hist.empty else None,
        }
    except Exception as exc:
        history_summary = {"error": f"Failed to load history: {exc}"}

    try:
        options = list(t.options)
    except Exception:
        options = []

    payload = {
        "ticker": args.ticker,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "yfinance_version": getattr(yf, "__version__", "unknown"),
        "fast_info": {k: safe_json(v) for k, v in fast_info.items()} if isinstance(fast_info, dict) else safe_json(fast_info),
        "info_subset": {
            k: safe_json(info.get(k)) if isinstance(info, dict) else None
            for k in [
                "shortName", "longName", "symbol", "currency", "exchange",
                "quoteType", "sector", "industry", "marketCap", "trailingPE",
                "forwardPE", "dividendYield", "beta",
            ]
        },
        "history": history_summary,
        "options_expirations": options,
    }

    if args.include_news:
        try:
            payload["news"] = t.news
        except Exception as exc:
            payload["news"] = {"error": f"Failed to load news: {exc}"}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Saved snapshot to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
